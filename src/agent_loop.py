"""
Agent 主循环模块

负责:
1. 消息历史管理 (上下文窗口控制、摘要压缩)
2. 工具调用执行 (并发安全、路径重叠检查)
3. 技能加载与匹配 (渐进式披露、Memory Graph 选择)
4. 子代理生命周期管理 (创建、等待、结果聚合)
5. 会话持久化 (SQLite 存储、历史回溯)

核心流程:
- 接收用户输入 → 构建 messages → 调用 LLM → 解析 tool_calls → 执行工具 → 返回结果 → 循环
- 支持流式响应、上下文压缩、双重 System Message 防护

OpenTelemetry 嵌入:
- 工具调用 Span (seed.tool.{name})
- Session Span (seed.session)
"""

import tiktoken
import asyncio
import json
import os
import logging
import time
from typing import List, Dict, Optional, AsyncGenerator, Set
from pathlib import Path
from tools import ToolRegistry
from tools.memory_tools import _save_session_history, _generate_session_filename, _record_skill_outcome
from tools.skill_loader import SkillLoader
from scheduler import TaskScheduler
from client import LLMGateway
from request_queue import RequestPriority
from subagent_manager import SubagentManager

# OpenTelemetry 可观测性
try:
    from observability import (
        get_tracer,
        SPAN_SESSION,
        SPAN_TOOL_PREFIX,
        set_tool_span_attributes,
        traced,
    )
    from opentelemetry.trace import StatusCode
    _OBSERVABILITY_ENABLED = True
except ImportError:
    _OBSERVABILITY_ENABLED = False
    def get_tracer(): return None
    def set_tool_span_attributes(*args, **kwargs): pass
    def traced(*args, **kwargs): return lambda f: f
    SPAN_SESSION = "seed.session"
    SPAN_TOOL_PREFIX = "seed.tool."
    StatusCode = None

logger = logging.getLogger(__name__)


class MaxIterationsExceeded(Exception):
    """超过最大迭代次数异常"""
    pass

class ProviderNotFoundError(Exception):
    """提供商不存在异常"""
    pass

class ToolNotFoundError(Exception):
    """工具不存在异常"""
    pass

class AgentLoop:
    """Agent 主循环"""

    SUMMARY_PROMPT = """请将以下对话历史压缩成简洁的摘要，保留关键信息：
1. 用户的核心需求和意图
2. 已完成的关键操作和结果
3. 重要发现或决策
4. 未完成的任务或待处理事项

对话历史：
{history}

请用简洁的要点形式输出摘要（不超过300字）："""

    def __init__(
        self,
        gateway: LLMGateway,
        model_id: str = None,
        system_prompt: str = None,
        max_iterations: int = 30,
        summary_interval: int = 10,
        session_id: str = None
    ):
        self.gateway = gateway
        self.model_id = model_id or self._get_primary_model()
        self.max_iterations = max_iterations
        self.summary_interval = summary_interval

        self.history: List[Dict] = []
        self._conversation_rounds: int = 0  # 用户消息计数
        self._last_summary: Optional[str] = None  # 最近一次摘要
        self.session_id: str = session_id or _generate_session_filename()  # 当前会话ID

        # Memory Graph: Skill 执行跟踪
        self._pending_skill_outcomes: List[Dict] = []  # 待评估的 skill 执行
        
        # Context Window Management
        self.context_window = self._get_model_context_window()
        self.context_usage_threshold = 0.75  # Trigger summary at 75% usage

        # Context Token Cache: 缓存每条消息的 token 计数，避免重复编码
        self._message_token_cache: List[int] = []  # 与 self.history 一一对应
        self._system_prompt_tokens: int = 0

        self.tools = ToolRegistry()
        from tools.builtin_tools import register_builtin_tools
        from tools.memory_tools import register_memory_tools
        from tools.skill_loader import register_skill_tools
        from scheduler import register_scheduler_tools
        from tools.ralph_tools import register_ralph_tools
        from tools.subagent_tools import register_subagent_tools, init_subagent_manager
        register_builtin_tools(self.tools)
        register_memory_tools(self.tools)
        register_skill_tools(self.tools)
        register_scheduler_tools(self.tools)
        register_ralph_tools(self.tools)
        register_subagent_tools(self.tools)

        # 初始化 SubagentManager
        self.subagent_manager = SubagentManager(
            gateway=self.gateway,
            model_id=self.model_id,
        )
        init_subagent_manager(self.subagent_manager)

        # 初始化定时任务调度器
        self.scheduler = TaskScheduler(self)

        # 加载 skills 并注入到 system prompt (渐进式披露: 仅注入索引)
        self.skill_loader = SkillLoader()
        self._available_tools: Optional[Set[str]] = None
        skills_prompt = self.skill_loader.get_skills_prompt()
        if system_prompt:
            self.system_prompt = system_prompt + "\n\n" + skills_prompt
        else:
            self.system_prompt = skills_prompt

        self._pending_user_input: Optional[str] = None

        self._encoding = self._get_tokenizer()

    def _get_primary_model(self) -> str:
        """从配置获取主模型"""
        return self.gateway.config.agents['defaults'].defaults.primary

    def _get_tokenizer(self):
        """获取当前模型的 tokenizer"""
        try:
            # Extract model name from "provider/model" format
            model_name = self.model_id.split('/', 1)[-1] if '/' in self.model_id else self.model_id
            return tiktoken.encoding_for_model(model_name)
        except KeyError:
            # Fallback: try common encodings
            for enc_name in ["cl100k_base", "p50k_base", "r50k_base"]:
                try:
                    return tiktoken.get_encoding(enc_name)
                except KeyError:
                    continue
            return None

    def _get_model_context_window(self) -> int:
        """获取当前模型的上下文窗口大小"""
        # Extract provider_id and model_id from "provider/model" format
        if '/' in self.model_id:
            provider_id, model_id = self.model_id.split('/', 1)
            provider = self.gateway.config.models.get(provider_id)
            if provider:
                for m in provider.models:
                    if m.id == model_id:
                        return m.contextWindow
        return 100000  # Default fallback

    def _encode_text(self, text: str) -> int:
        """编码文本并返回 token 计数"""
        if self._encoding:
            return len(self._encoding.encode(text))
        return int(len(text) * 0.7)

    def _cache_message_tokens(self, msg: Dict) -> int:
        """计算并缓存单条消息的 token 数"""
        content = msg.get('content', '')
        tokens = 0
        if isinstance(content, str):
            tokens = self._encode_text(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and 'text' in item:
                    tokens += self._encode_text(item['text'])
        # tool_calls 也有 token 开销，简单估算
        if msg.get('tool_calls'):
            tc_text = json.dumps(msg['tool_calls'])
            tokens += self._encode_text(tc_text)
        return tokens

    def _estimate_context_size(self) -> int:
        """估算当前上下文的 Token 数量
        
        使用增量缓存：仅对新消息编码，已缓存的消息直接求和。
        """
        # 缓存 system prompt（仅首次或变化时）
        if self._system_prompt_tokens == 0 and self.system_prompt:
            self._system_prompt_tokens = self._encode_text(self.system_prompt)

        # 增量更新 token 缓存
        cache_len = len(self._message_token_cache)
        history_len = len(self.history)
        
        if cache_len < history_len:
            # 有新消息，仅编码新增部分
            for msg in self.history[cache_len:]:
                self._message_token_cache.append(self._cache_message_tokens(msg))
        elif cache_len > history_len:
            # 历史被截断（如 summarize 后），重建缓存
            self._message_token_cache = []
            self._system_prompt_tokens = 0
            for msg in self.history:
                self._message_token_cache.append(self._cache_message_tokens(msg))
            if self.system_prompt:
                self._system_prompt_tokens = self._encode_text(self.system_prompt)

        return self._system_prompt_tokens + sum(self._message_token_cache)

    def _build_messages(self) -> List[Dict]:
        """构建完整的消息列表"""
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.extend(self.history)
        return messages

    async def _summarize_history(self) -> Optional[str]:
        """使用 LLM 总结对话历史"""
        if not self.history:
            return None

        # 格式化历史为文本
        history_text = ""
        for msg in self.history:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            if msg.get('tool_calls'):
                tc_names = [tc['function']['name'] for tc in msg['tool_calls'] if tc.get('function')]
                content = f"[Tool Calls: {', '.join(tc_names)}]"
            if content:
                history_text += f"{role}: {content}\n"

        if not history_text.strip():
            return None

        # 调用 LLM 生成摘要
        prompt = self.SUMMARY_PROMPT.format(history=history_text)
        try:
            response = await self.gateway.chat_completion(
                self.model_id,
                [{"role": "user", "content": prompt}],
                tools=None  # 摘要不需要工具
            )
            summary = response['choices'][0]['message']['content']
            return summary.strip()
        except Exception:
            return None

    async def _maybe_summarize(self):
        """检查是否需要总结历史，并执行总结"""
        # 无论是否达到总结间隔，都先保存会话历史到 L4
        if self.history:
            _save_session_history(self.history, summary=self._last_summary, session_id=self.session_id)

        # Check if context window is getting full (Token-based)
        estimated_tokens = self._estimate_context_size()
        token_threshold = self.context_window * self.context_usage_threshold
        is_context_full = estimated_tokens > token_threshold

        # Or if conversation rounds exceed limit (Count-based)
        is_round_limit_reached = self._conversation_rounds >= self.summary_interval

        if not is_context_full and not is_round_limit_reached:
            return

        logger.info(
            f"Summary triggered: context_tokens={estimated_tokens}/{self.context_window} "
            f"(threshold={token_threshold}), rounds={self._conversation_rounds}/{self.summary_interval}"
        )

        # 生成摘要
        summary = await self._summarize_history()
        if not summary:
            return

        # 更新元数据中的摘要
        _save_session_history([], summary=summary, session_id=self.session_id)

        # 保留最近 2 轮对话 + 摘要 (or fewer if context is critical)
        # If context is very full, keep less history
        keep_count = 4 if not is_context_full else 2 
        
        # 确保保留的部分是完整的 (user + assistant + tool_calls/results)
        # 简单切片，保留最后 keep_count 条
        preserved = self.history[-keep_count:] if len(self.history) > keep_count else self.history

        # 用摘要替换旧历史 (使用 user role 避免双重 system message 问题)
        self.history = [
            {"role": "user", "content": f"[System Note: 以下是之前对话的摘要，请作为当前任务的背景参考]\n{summary}"}
        ] + preserved

        self._last_summary = summary
        self._conversation_rounds = 0  # 重置计数

    async def run(self, user_input: str, priority: int = RequestPriority.CRITICAL) -> str:
        """处理用户输入,返回最终响应
        
        Args:
            user_input: 用户输入文本
            priority: 请求优先级，默认 CRITICAL（用户请求最高优先级）
        """
        self.history.append({"role": "user", "content": user_input})
        self._conversation_rounds += 1

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            if self._pending_user_input:
                new_input = self._pending_user_input
                self._pending_user_input = None
                self.history.append({"role": "user", "content": new_input})
                self._conversation_rounds += 1
                iteration = 0

            messages = self._build_messages()
            response = await self.gateway.chat_completion(
                self.model_id,
                messages,
                priority=priority,  # 使用传入的优先级
                tools=self.tools.get_schemas()
            )

            choice = response['choices'][0]
            message = choice['message']
            self.history.append(message)

            if message.get('tool_calls'):
                tool_results = await self._execute_tool_calls(message['tool_calls'])
                self.history.extend(tool_results)
            else:
                # 对话完成，检查是否需要总结
                await self._maybe_summarize()
                # Memory Graph: 评估并记录 Skill 执行结果
                self._evaluate_and_record_skill_outcomes(final_success=True)
                return message.get('content', '')

        raise MaxIterationsExceeded(
            f"Agent exceeded maximum iterations ({self.max_iterations})"
        )

    def _process_tool_delta(self, tc_list: List[Dict], accumulator: Dict[int, Dict]):
        """处理流式响应中的 Tool Call 增量块"""
        for tc in tc_list:
            idx = tc.get('index', 0)
            if idx not in accumulator:
                accumulator[idx] = {
                    'id': tc.get('id'),
                    'type': tc.get('type', 'function'),
                    'function': {'name': '', 'arguments': ''}
                }
            acc = accumulator[idx]
            if tc.get('id'):
                acc['id'] = tc['id']
            if tc.get('type'):
                acc['type'] = tc['type']
            func = tc.get('function', {})
            if func.get('name'):
                acc['function']['name'] = func['name']
            if func.get('arguments'):
                acc['function']['arguments'] += func['arguments']

    async def _process_final_completion(self, full_content: str):
        """处理对话完成的收尾工作 (总结 + 评估)"""
        await self._maybe_summarize()
        self._evaluate_and_record_skill_outcomes(final_success=True)
        yield {"type": "final", "content": full_content}

    async def stream_run(self, user_input: str, priority: int = RequestPriority.CRITICAL) -> AsyncGenerator[Dict, None]:
        """流式处理用户输入"""
        self.history.append({"role": "user", "content": user_input})
        self._conversation_rounds += 1

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            messages = self._build_messages()
            full_content = ""
            tool_calls_accumulator: Dict[int, Dict] = {}

            async for chunk in self.gateway.stream_chat_completion(
                self.model_id,
                messages,
                priority=priority,
                tools=self.tools.get_schemas()
            ):
                delta = chunk['choices'][0].get('delta', {})
                content = delta.get('content')
                if content:
                    full_content += content
                    yield {"type": "chunk", "content": content}

                tc_list = delta.get('tool_calls')
                if tc_list:
                    self._process_tool_delta(tc_list, tool_calls_accumulator)

            tool_calls = (
                [tool_calls_accumulator[i] for i in sorted(tool_calls_accumulator.keys())]
                if tool_calls_accumulator else []
            )

            self.history.append({
                "role": "assistant",
                "content": full_content or None,
                "tool_calls": tool_calls if tool_calls else None
            })

            if tool_calls:
                yield {"type": "tool_call", "calls": tool_calls}
                tool_results = await self._execute_tool_calls(tool_calls)
                self.history.extend(tool_results)
            else:
                async for final_chunk in self._process_final_completion(full_content):
                    yield final_chunk
                return

    def _check_write_conflicts(self, tool_calls: List[Dict]) -> Optional[List[Dict]]:
        """检查写工具调用的路径重叠，防止并发冲突。
        
        Returns:
            Error response list if conflict detected, None otherwise.
        """
        write_tools = {'file_write', 'file_edit'}
        seen_paths = {}
        for tc in tool_calls:
            if tc['function']['name'] in write_tools:
                try:
                    args = json.loads(tc['function']['arguments']) if isinstance(tc['function']['arguments'], str) else tc['function']['arguments']
                    path = args.get('path', '')
                    if path:
                        if path in seen_paths:
                            logger.warning(f"Concurrent write conflict detected: {path}")
                            return [{"role": "tool", "tool_call_id": tc['id'], "content": f"Error: Concurrent write conflict on '{path}'. Please execute sequentially."} for tc in tool_calls]
                        seen_paths[path] = tc['id']
                except Exception:
                    pass
        return None

    async def _run_single_tool_call(self, tool_call: Dict) -> Dict:
        """执行单个工具调用，包含追踪和记录逻辑"""
        tool_id = tool_call['id']
        tool_name = tool_call['function']['name']
        raw_args = tool_call['function']['arguments']

        # 鲁棒的 JSON 解析
        try:
            if isinstance(raw_args, str):
                raw_args = raw_args.strip()
                tool_args = json.loads(raw_args) if raw_args else {}
            else:
                tool_args = raw_args if raw_args else {}
            if not isinstance(tool_args, dict):
                tool_args = {}
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning(f"Invalid tool args for {tool_name}: {raw_args!r}, using empty dict")
            tool_args = {}

        # OpenTelemetry Span 创建
        tracer = get_tracer()
        span = None
        start_time = time.time()
        if tracer and _OBSERVABILITY_ENABLED:
            span = tracer.start_span(f"{SPAN_TOOL_PREFIX}{tool_name}")
            set_tool_span_attributes(span, tool_name, file_path=tool_args.get('path', ''))

        try:
            result = await self.tools.execute(tool_name, **tool_args)
            duration_ms = (time.time() - start_time) * 1000
            if span:
                span.set_attribute("seed.tool.duration_ms", duration_ms)
                span.set_status(StatusCode.OK)

            # Memory Graph 跟踪
            if tool_name == 'load_skill':
                self._pending_skill_outcomes.append({
                    'skill_name': tool_args.get('name', ''),
                    'tool_call_id': tool_id,
                    'result': result,
                    'signals': self._extract_signals_from_context()
                })

            return {"role": "tool", "tool_call_id": tool_id, "content": str(result)}

        except Exception as e:
            if span:
                span.record_exception(e)
                span.set_attribute("seed.error.message", str(e)[:500])
                span.set_status(StatusCode.ERROR, str(e)[:200])

            if tool_name == 'load_skill':
                self._pending_skill_outcomes.append({
                    'skill_name': tool_args.get('name', ''),
                    'tool_call_id': tool_id,
                    'result': f"Error: {str(e)}",
                    'signals': self._extract_signals_from_context(),
                    'failed': True
                })
            return {"role": "tool", "tool_call_id": tool_id, "content": f"Error: {str(e)}"}
        finally:
            if span:
                span.end()

    async def _execute_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """批量并行执行工具调用 (含 Memory Graph 自动记录 + 路径重叠检查 + OpenTelemetry Tracing)"""
        conflict_result = self._check_write_conflicts(tool_calls)
        if conflict_result:
            return conflict_result

        results = await asyncio.gather(*[self._run_single_tool_call(tc) for tc in tool_calls])
        return results

    def _extract_signals_from_context(self) -> List[str]:
        """从当前上下文提取触发信号"""
        signals = []
        # 从最近几条消息中提取关键词
        for msg in self.history[-3:]:
            content = msg.get('content', '')
            if isinstance(content, str):
                # 简单提取：前 5 个词作为信号
                words = content.split()[:5]
                signals.extend(words)
        return signals[:10]  # 最大 10 个信号

    def _evaluate_and_record_skill_outcomes(self, final_success: bool = True):
        """评估并记录待处理的 Skill 执行结果"""
        for pending in self._pending_skill_outcomes:
            skill_name = pending.get('skill_name')
            result = pending.get('result', '')
            signals = pending.get('signals', [])
            failed = pending.get('failed', False)

            # 简化评估：根据是否有错误判断成功/失败
            if failed or 'Error' in str(result) or 'not found' in str(result).lower():
                outcome = 'failed'
                score = 0.0
            elif 'Security Warning' in str(result):
                outcome = 'partial'
                score = 0.5
            else:
                outcome = 'success'
                score = 1.0 if final_success else 0.8

            # 记录结果
            if skill_name:
                try:
                    _record_skill_outcome(
                        skill_name=skill_name,
                        outcome=outcome,
                        score=score,
                        signals=signals,
                        session_id=self.session_id
                    )
                except Exception as e:
                    logger.warning(f"Failed to record skill outcome: {e}")

        # 清空待处理列表
        self._pending_skill_outcomes.clear()

    def clear_history(self, save_current: bool = True):
        """清空对话历史，可选保存当前历史到 L4"""
        if save_current and self.history:
            _save_session_history(self.history, summary=self._last_summary, session_id=self.session_id)
        self.history.clear()
        self._conversation_rounds = 0
        self._last_summary = None
        self._message_token_cache.clear()
        self._system_prompt_tokens = 0
        self.session_id = _generate_session_filename()  # 新会话ID

    def interrupt(self, user_input: str):
        """中断当前处理,优先响应用户输入"""
        self._pending_user_input = user_input
