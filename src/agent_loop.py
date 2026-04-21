import asyncio
import json
import os
import logging
from typing import List, Dict, Optional, AsyncGenerator, Set
from pathlib import Path
from tools import ToolRegistry
from tools.memory_tools import _save_session_history, _generate_session_filename, _record_skill_outcome
from tools.skill_loader import SkillLoader
from scheduler import TaskScheduler
from client import LLMGateway
from subagent_manager import SubagentManager

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

    def _get_primary_model(self) -> str:
        """从配置获取主模型"""
        return self.gateway.config.agents['defaults'].defaults.primary

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

    def _estimate_context_size(self) -> int:
        """估算当前上下文的 Token 数量 (粗略估算: 字符数 * 0.7)"""
        # 包含 system prompt 和 history
        total_chars = len(self.system_prompt) if self.system_prompt else 0
        for msg in self.history:
            content = msg.get('content', '')
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                # For multimodal content, estimate text length
                for item in content:
                    if isinstance(item, dict) and 'text' in item:
                        total_chars += len(item['text'])
        
        # 简单的 heuristic: 1 token ≈ 1.5 characters for mixed text, or 1 char ≈ 0.7 tokens for Chinese
        # Using 0.7 as a safe upper bound for token count relative to chars
        return int(total_chars * 0.7)

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

        # 用摘要替换旧历史
        self.history = [
            {"role": "system", "content": f"[对话摘要]\n{summary}"}
        ] + preserved

        self._last_summary = summary
        self._conversation_rounds = 0  # 重置计数

    async def run(self, user_input: str) -> str:
        """处理用户输入,返回最终响应"""
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

    async def stream_run(self, user_input: str) -> AsyncGenerator[Dict, None]:
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
                tools=self.tools.get_schemas()
            ):
                delta = chunk['choices'][0].get('delta', {})
                content = delta.get('content')
                if content:
                    full_content += content
                    yield {"type": "chunk", "content": content}

                tc_list = delta.get('tool_calls')
                if tc_list:
                    for tc in tc_list:
                        idx = tc.get('index', 0)
                        if idx not in tool_calls_accumulator:
                            tool_calls_accumulator[idx] = {
                                'id': tc.get('id'),
                                'type': tc.get('type', 'function'),
                                'function': {'name': '', 'arguments': ''}
                            }
                        acc = tool_calls_accumulator[idx]
                        if tc.get('id'):
                            acc['id'] = tc['id']
                        if tc.get('type'):
                            acc['type'] = tc['type']
                        func = tc.get('function', {})
                        if func.get('name'):
                            acc['function']['name'] = func['name']
                        if func.get('arguments'):
                            acc['function']['arguments'] += func['arguments']

            tool_calls = [tool_calls_accumulator[i] for i in sorted(tool_calls_accumulator.keys())] if tool_calls_accumulator else []

            assistant_message = {
                "role": "assistant",
                "content": full_content or None,
                "tool_calls": tool_calls if tool_calls else None
            }
            self.history.append(assistant_message)

            if tool_calls:
                yield {"type": "tool_call", "calls": tool_calls}
                tool_results = await self._execute_tool_calls(tool_calls)
                self.history.extend(tool_results)
            else:
                # 对话完成，检查是否需要总结
                await self._maybe_summarize()
                # Memory Graph: 评估并记录 Skill 执行结果
                self._evaluate_and_record_skill_outcomes(final_success=True)
                yield {"type": "final", "content": full_content}
                return

    async def _execute_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """批量并行执行工具调用 (含 Memory Graph 自动记录)"""
        async def _run_single_call(tool_call: Dict) -> Dict:
            tool_id = tool_call['id']
            tool_name = tool_call['function']['name']
            raw_args = tool_call['function']['arguments']

            # 鲁棒的 JSON 解析：处理空字符串、无效 JSON 等边界情况
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

            try:
                result = await self.tools.execute(tool_name, **tool_args)

                # Memory Graph: 跟踪 skill 执行
                if tool_name == 'load_skill':
                    skill_name = tool_args.get('name', '')
                    self._pending_skill_outcomes.append({
                        'skill_name': skill_name,
                        'tool_call_id': tool_id,
                        'result': result,
                        'signals': self._extract_signals_from_context()
                    })

                return {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": str(result)
                }
            except Exception as e:
                # Memory Graph: 记录失败
                if tool_name == 'load_skill':
                    skill_name = tool_args.get('name', '')
                    self._pending_skill_outcomes.append({
                        'skill_name': skill_name,
                        'tool_call_id': tool_id,
                        'result': f"Error: {str(e)}",
                        'signals': self._extract_signals_from_context(),
                        'failed': True
                    })

                return {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": f"Error: {str(e)}"
                }

        results = await asyncio.gather(*[_run_single_call(tc) for tc in tool_calls])
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
        self.session_id = _generate_session_filename()  # 新会话ID

    def interrupt(self, user_input: str):
        """中断当前处理,优先响应用户输入"""
        self._pending_user_input = user_input