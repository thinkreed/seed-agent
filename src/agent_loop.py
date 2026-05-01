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

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

import tiktoken

from src.client import LLMGateway
from src.request_queue import RequestPriority
from src.scheduler import TaskScheduler, register_scheduler_tools
from src.subagent_manager import SubagentManager
from src.tools import ToolRegistry
from src.tools.builtin_tools import register_builtin_tools
from src.tools.memory_tools import (
    _generate_session_filename,
    _record_skill_outcome,
    _save_session_history,
    register_memory_tools,
)
from src.tools.ralph_tools import register_ralph_tools
from src.tools.skill_loader import SkillLoader, register_skill_tools
from src.tools.subagent_tools import init_subagent_manager, register_subagent_tools

# OpenTelemetry 可观测性（自动处理 ImportError）
from src.observability import (
    SPAN_TOOL_PREFIX,
    StatusCode,
    get_tracer,
    is_observability_enabled,
    set_tool_span_attributes,
)

_OBSERVABILITY_ENABLED = is_observability_enabled()

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
        model_id: str | None = None,
        system_prompt: str | None = None,
        max_iterations: int = 30,
        summary_interval: int = 10,
        session_id: str | None = None
    ):
        self.gateway = gateway
        self.model_id = model_id or self._get_primary_model()
        self.max_iterations = max_iterations
        self.summary_interval = summary_interval

        self.history: list[dict] = []
        self._conversation_rounds: int = 0  # 用户消息计数
        self._last_summary: str | None = None  # 最近一次摘要
        self.session_id: str = session_id or _generate_session_filename()  # 当前会话ID

        self._setup_internal_state()
        self._setup_tools_and_skills()
        self._setup_subsystems(system_prompt)

        self._encoding = self._get_tokenizer()

    def _setup_internal_state(self) -> None:
        """初始化内部状态与上下文管理"""
        # Memory Graph: Skill 执行跟踪
        self._pending_skill_outcomes: list[dict] = []

        # Context Window Management
        self.context_window = self._get_model_context_window()
        self.context_usage_threshold = 0.75  # Trigger summary at 75% usage

        # Context Token Cache
        self._message_token_cache: list[int] = []
        self._system_prompt_tokens: int = 0
        self._pending_user_input: str | None = None

    def _setup_tools_and_skills(self) -> None:
        """注册工具并加载技能"""
        self.tools = ToolRegistry()

        register_builtin_tools(self.tools)
        register_memory_tools(self.tools)
        register_skill_tools(self.tools)
        register_scheduler_tools(self.tools)
        register_ralph_tools(self.tools)
        register_subagent_tools(self.tools)

        # 加载 skills (渐进式披露: 仅注入索引)
        self.skill_loader = SkillLoader()
        self._available_tools: set[str] | None = None

    def _setup_subsystems(self, system_prompt: str | None = None) -> None:
        """初始化子系统（Subagent、调度器、Prompt）"""
        # 初始化 SubagentManager
        self.subagent_manager = SubagentManager(
            gateway=self.gateway,
            model_id=self.model_id,
        )
        init_subagent_manager(self.subagent_manager)

        # 初始化定时任务调度器
        self.scheduler = TaskScheduler(self)

        # 构建 System Prompt
        skills_prompt = self.skill_loader.get_skills_prompt()
        if system_prompt:
            self.system_prompt = system_prompt + "\n\n" + skills_prompt
        else:
            self.system_prompt = skills_prompt

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

    def _cache_message_tokens(self, msg: dict) -> int:
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

    def _rebuild_token_cache(self) -> None:
        """重建 Token 缓存（用于历史截断后）"""
        self._message_token_cache = []
        self._system_prompt_tokens = 0
        for msg in self.history:
            self._message_token_cache.append(self._cache_message_tokens(msg))
        if self.system_prompt:
            self._system_prompt_tokens = self._encode_text(self.system_prompt)

    def _update_message_token_cache(self) -> None:
        """更新消息 Token 缓存（增量或全量重建）"""
        cache_len = len(self._message_token_cache)
        history_len = len(self.history)

        if cache_len < history_len:
            # 增量：仅编码新增部分
            for msg in self.history[cache_len:]:
                self._message_token_cache.append(self._cache_message_tokens(msg))
        elif cache_len > history_len:
            # 历史被截断：全量重建
            self._rebuild_token_cache()

    def _estimate_context_size(self) -> int:
        """估算当前上下文的 Token 数量"""
        # 缓存 system prompt（仅首次或变化时）
        if self._system_prompt_tokens == 0 and self.system_prompt:
            self._system_prompt_tokens = self._encode_text(self.system_prompt)

        self._update_message_token_cache()
        return self._system_prompt_tokens + sum(self._message_token_cache)

    def _build_messages(self) -> list[dict]:
        """构建完整的消息列表"""
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.extend(self.history)
        return messages

    def _format_history_for_summary(self) -> str:
        """将历史记录格式化为文本"""
        history_text = ""
        for msg in self.history:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            if msg.get('tool_calls'):
                tc_names = [tc['function']['name'] for tc in msg['tool_calls'] if tc.get('function')]
                content = f"[Tool Calls: {', '.join(tc_names)}]"
            if content:
                history_text += f"{role}: {content}\n"
        return history_text.strip()

    async def _summarize_history(self) -> str | None:
        """使用 LLM 总结对话历史"""
        if not self.history:
            return None

        history_text = self._format_history_for_summary()
        if not history_text:
            return None

        prompt = self.SUMMARY_PROMPT.format(history=history_text)
        try:
            response = await self.gateway.chat_completion(
                self.model_id,
                [{"role": "user", "content": prompt}],
                tools=None
            )
            summary = response['choices'][0]['message']['content']
            return summary.strip()
        except Exception as e:
            logger.warning(f"Summary generation failed: {type(e).__name__}: {str(e)[:100]}")
            return None


    def _should_summarize(self) -> tuple[bool, int, bool]:
        """检查是否需要总结
        
        Returns:
            (should_summarize, estimated_tokens, is_context_full)
        """
        estimated_tokens = self._estimate_context_size()
        token_threshold = self.context_window * self.context_usage_threshold
        is_context_full = estimated_tokens > token_threshold
        is_round_limit_reached = self._conversation_rounds >= self.summary_interval
        return (is_context_full or is_round_limit_reached), estimated_tokens, is_context_full


    async def _apply_summary(self, summary: str, is_context_full: bool):
        """应用摘要并截断历史"""
        # Save summary to metadata
        _save_session_history([], summary=summary, session_id=self.session_id)

        # Keep fewer messages if context is very full
        keep_count = 2 if is_context_full else 4
        preserved = self.history[-keep_count:] if len(self.history) > keep_count else self.history

        # Replace history with summary + preserved messages
        self.history = [
            {"role": "user", "content": f"[System Note: 之前对话的摘要，作为当前上下文的参考]\n{summary}"}
        ] + preserved

        self._last_summary = summary
        self._conversation_rounds = 0
    async def _maybe_summarize(self):
        """检查是否需要总结历史并执行总结"""
        # Save current history to L4 session archive
        if self.history:
            _save_session_history(self.history, summary=self._last_summary, session_id=self.session_id)

        # Check if summary is needed
        needs_summary, estimated_tokens, is_context_full = self._should_summarize()
        if not needs_summary:
            return

        logger.info(
            f"Summary triggered: context_tokens={estimated_tokens}/{self.context_window} "
            f"(threshold={self.context_window * self.context_usage_threshold}), "
            f"rounds={self._conversation_rounds}/{self.summary_interval}"
        )

        # Generate summary
        summary = await self._summarize_history()
        if not summary:
            return

        # Apply summary and truncate history
        await self._apply_summary(summary, is_context_full)

    async def _process_run_response(self, response: dict, iteration: int) -> tuple[str | None, int, bool]:
        """处理 LLM 响应并执行相应动作
        
        Returns:
            (next_input, new_iteration, should_return)
        """
        choice = response['choices'][0]
        message = choice['message']
        self.history.append(message)

        if message.get('tool_calls'):
            tool_results = await self._execute_tool_calls(message['tool_calls'])
            self.history.extend(tool_results)
            return None, iteration, False  # Continue loop
        else:
            # 对话完成，检查是否需要总结
            await self._maybe_summarize()
            # Memory Graph: 评估并记录 Skill 执行结果
            self._evaluate_and_record_skill_outcomes(final_success=True)
            return message.get('content', ''), iteration, True  # Return response

    async def _handle_pending_input(self) -> bool:
        """处理中断/新输入
        
        Returns:
            True if a new input was handled (reset iteration), False otherwise.
        """
        if self._pending_user_input:
            new_input = self._pending_user_input
            self._pending_user_input = None
            self.history.append({"role": "user", "content": new_input})
            self._conversation_rounds += 1
            return True
        return False

    async def run(self, user_input: str, priority: int = RequestPriority.CRITICAL) -> str:
        """处理用户输入,返回最终响应"""
        self.history.append({"role": "user", "content": user_input})
        self._conversation_rounds += 1

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            # 处理中断/新输入
            if await self._handle_pending_input():
                iteration = 0
                continue

            messages = self._build_messages()
            response = await self.gateway.chat_completion(
                self.model_id,
                messages,
                priority=priority,
                tools=self.tools.get_schemas()
            )

            final_response, iteration, should_return = await self._process_run_response(response, iteration)
            if should_return:
                return final_response or ""  # 确保返回非空字符串

        raise MaxIterationsExceeded(
            f"Agent exceeded maximum iterations ({self.max_iterations})"
        )

    def _process_tool_delta(self, tc_list: list[dict], accumulator: dict[int, dict]):
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

    async def stream_run(self, user_input: str, priority: int = RequestPriority.CRITICAL) -> AsyncGenerator[dict, None]:
        """流式处理用户输入"""
        self.history.append({"role": "user", "content": user_input})
        self._conversation_rounds += 1

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            # 处理中断/新输入
            if await self._handle_pending_input():
                iteration = 0
                continue

            messages = self._build_messages()

            # 流式调用 LLM 并 yield 内容
            full_content = ""
            tool_calls_accumulator: dict[int, dict] = {}

            async for chunk in self.gateway.stream_chat_completion(
                self.model_id, messages, priority=priority, tools=self.tools.get_schemas()
            ):
                delta = chunk['choices'][0].get('delta', {})
                content = delta.get('content')
                if content:
                    full_content += content
                    yield {"type": "chunk", "content": content}

                tc_list = delta.get('tool_calls')
                if tc_list:
                    self._process_tool_delta(tc_list, tool_calls_accumulator)

            # 累积工具调用
            tool_calls = (
                [tool_calls_accumulator[i] for i in sorted(tool_calls_accumulator.keys())]
                if tool_calls_accumulator else []
            )

            # 记录历史
            self.history.append({
                "role": "assistant",
                "content": full_content or None,
                "tool_calls": tool_calls if tool_calls else None
            })

            if tool_calls:
                # 执行工具调用并继续循环
                tool_results = await self._execute_tool_calls(tool_calls)
                self.history.extend(tool_results)
                # 继续下一轮迭代
            else:
                # 对话完成
                await self._maybe_summarize()
                self._evaluate_and_record_skill_outcomes(final_success=True)
                yield {"type": "final", "content": full_content}
                return

        raise MaxIterationsExceeded(
            f"Agent exceeded maximum iterations ({self.max_iterations})"
        )

    def _check_write_conflicts(self, tool_calls: list[dict]) -> list[dict] | None:
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
                except Exception as e:
                    logger.debug(f"Failed to parse tool args for conflict check: {e}")
                    pass
        return None

    def _parse_tool_args(self, raw_args: Any, tool_name: str) -> dict:
        """鲁棒地解析工具参数"""
        from src.tools.utils import parse_tool_arguments
        return parse_tool_arguments(raw_args)

    def _record_load_skill_outcome(self, tool_args: dict, tool_id: str, result: str, failed: bool = False):
        """记录 load_skill 的执行结果到 Memory Graph"""
        self._pending_skill_outcomes.append({
            'skill_name': tool_args.get('name', ''),
            'tool_call_id': tool_id,
            'result': result,
            'signals': self._extract_signals_from_context(),
            **({'failed': True} if failed else {})
        })

    async def _run_single_tool_call(self, tool_call: dict) -> dict:
        """执行单个工具调用，包含追踪和记录逻辑"""
        tool_id = tool_call['id']
        tool_name = tool_call['function']['name']
        tool_args = self._parse_tool_args(tool_call['function']['arguments'], tool_name)

        span = self._start_tool_span(tool_name, tool_args)
        start_time = time.time()

        try:
            result = await self.tools.execute(tool_name, **tool_args)
            self._finish_tool_span(span, start_time, success=True)

            # Memory Graph 跟踪
            self._record_load_skill_if_needed(tool_name, tool_args, tool_id, str(result), failed=False)

            return {"role": "tool", "tool_call_id": tool_id, "content": str(result)}

        except Exception as e:
            self._finish_tool_span(span, start_time, success=False, error=e)

            # Memory Graph 跟踪 (失败情况)
            self._record_load_skill_if_needed(tool_name, tool_args, tool_id, f"Error: {str(e)}", failed=True)
            return {"role": "tool", "tool_call_id": tool_id, "content": f"Error: {str(e)}"}

    def _record_load_skill_if_needed(self, tool_name: str, tool_args: dict, tool_id: str, content: str, failed: bool):
        """如果是 load_skill 调用，记录其结果到 Memory Graph"""
        if tool_name == 'load_skill':
            self._record_load_skill_outcome(tool_args, tool_id, content, failed)

    def _start_tool_span(self, tool_name: str, tool_args: dict):
        """创建 OpenTelemetry Span"""
        tracer = get_tracer()
        if not (tracer and _OBSERVABILITY_ENABLED):
            return None

        span = tracer.start_span(f"{SPAN_TOOL_PREFIX}{tool_name}")
        set_tool_span_attributes(span, tool_name, file_path=tool_args.get('path', ''))
        return span

    def _finish_tool_span(self, span, start_time: float, success: bool, error: Exception | None = None):
        """完成 Span 并记录指标"""
        if not span:
            return

        duration_ms = (time.time() - start_time) * 1000
        if success:
            span.set_attribute("seed.tool.duration_ms", duration_ms)
            span.set_status(StatusCode.OK)
        else:
            span.record_exception(error)
            span.set_attribute("seed.error.message", str(error)[:500])
            span.set_status(StatusCode.ERROR, str(error)[:200])
        span.end()

    async def _execute_tool_calls(self, tool_calls: list[dict]) -> list[dict]:
        """批量并行执行工具调用 (含 Memory Graph 自动记录 + 路径重叠检查 + OpenTelemetry Tracing)"""
        conflict_result = self._check_write_conflicts(tool_calls)
        if conflict_result:
            return conflict_result

        # 使用 return_exceptions=True 确保单个工具失败不会影响整个批次
        results = await asyncio.gather(
            *[self._run_single_tool_call(tc) for tc in tool_calls],
            return_exceptions=True
        )

        # 处理可能的异常结果，转换为错误响应
        processed_results: list[dict[str, Any]] = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                # CancelledError 应传播，不应转换为错误响应
                if isinstance(result, asyncio.CancelledError):
                    raise result

                tool_name = tool_calls[i].get('function', {}).get('name', 'unknown')
                logger.error(f"Tool call {tool_name} failed: {type(result).__name__}: {result}")
                processed_results.append({
                    "tool_call_id": tool_calls[i].get("id", "unknown"),
                    "role": "tool",
                    "content": f"Error: Tool execution failed - {type(result).__name__}: {str(result)[:200]}"
                })
            else:
                processed_results.append(result)  # type: ignore[misc]  # result is dict here

        return processed_results

    def _extract_signals_from_context(self) -> list[str]:
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

    def _evaluate_skill_outcome(self, result: str, failed: bool, final_success: bool) -> tuple[str, float]:
        """评估单个 Skill 的执行结果
        
        Returns:
            (outcome, score): e.g., ('success', 1.0), ('failed', 0.0)
        """
        result_str = str(result)
        if failed or 'Error' in result_str or 'not found' in result_str.lower():
            return 'failed', 0.0
        elif 'Security Warning' in result_str:
            return 'partial', 0.5
        else:
            return 'success', 1.0 if final_success else 0.8

    def _evaluate_and_record_skill_outcomes(self, final_success: bool = True):
        """评估并记录待处理的 Skill 执行结果"""
        for pending in self._pending_skill_outcomes:
            skill_name = pending.get('skill_name')
            if not skill_name:
                continue

            try:
                outcome, score = self._evaluate_skill_outcome(
                    pending.get('result', ''),
                    pending.get('failed', False),
                    final_success
                )
                _record_skill_outcome(
                    skill_name=skill_name,
                    outcome=outcome,
                    score=score,
                    signals=pending.get('signals', []),
                    session_id=self.session_id
                )
            except Exception as e:
                logger.warning(f"Failed to record skill outcome: {type(e).__name__}: {e}")

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
