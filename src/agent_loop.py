import asyncio
import json
from typing import List, Dict, Optional, AsyncGenerator
from tools import ToolRegistry
from tools.builtin_tools import run_code, read_file, write_file, list_files
from tools.memory_tools import save_session_history, _generate_session_filename
from client import LLMGateway

def estimate_content_length(content: str) -> int:
    """简单估算内容长度 (字符数 * 1.5 粗略模拟 token 消耗，中英文混排)"""
    if not content:
        return 0
    return len(content)

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
        max_iterations: int = 10,
        summary_interval: int = 10,
        session_id: str = None
    ):
        self.gateway = gateway
        self.model_id = model_id or self._get_primary_model()
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self.summary_interval = summary_interval

        self.history: List[Dict] = []
        self._conversation_rounds: int = 0  # 用户消息计数
        self._last_summary: Optional[str] = None  # 最近一次摘要
        self.session_id: str = session_id or _generate_session_filename()  # 当前会话ID
        self.tools = ToolRegistry()
        from tools.builtin_tools import register_builtin_tools
        from tools.memory_tools import register_memory_tools
        register_builtin_tools(self.tools)
        register_memory_tools(self.tools)
        self._pending_user_input: Optional[str] = None

    def _get_primary_model(self) -> str:
        """从配置获取主模型"""
        return self.gateway.config.agents['defaults'].defaults.primary

    def _build_messages(self) -> List[Dict]:
        """构建完整的消息列表，包含上下文自动截断"""
        self._trim_history()
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.extend(self.history)
        return messages

    def _compress_content(self, content: str, max_len: int = 1500) -> str:
        """截断过长内容以优化上下文，保留首尾关键信息"""
        if len(content) > max_len:
            return content[:max_len//2] + "\n... [Context Truncated] ...\n" + content[-max_len//4:]
        return content

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
        if self._conversation_rounds < self.summary_interval:
            return

        # 生成摘要
        summary = await self._summarize_history()
        if not summary:
            return

        # 保存历史到 L4 raw/sessions (JSONL)
        save_session_history(self.history, summary=summary, session_id=self.session_id)

        # 保留最近2轮对话 + 摘要
        keep_count = 4  # 最近的 user + assistant + tool calls + results
        preserved = self.history[-keep_count:] if len(self.history) > keep_count else self.history

        # 用摘要替换旧历史
        self.history = [
            {"role": "system", "content": f"[对话摘要]\n{summary}"}
        ] + preserved

        self._last_summary = summary
        self._conversation_rounds = 0  # 重置计数

    def _trim_history(self):
        """智能裁剪历史消息：优先压缩工具输出，其次移除旧对话"""
        if not self.history:
            return

        # 1. 预处理：压缩过长的工具调用结果
        for msg in self.history:
            if msg.get('role') == 'tool':
                content = msg.get('content', '')
                if len(content) > 3000:
                    msg['content'] = self._compress_content(content, 2000)

        # 2. 检查长度并移除旧消息
        try:
            model_config = self.gateway.get_model_config(self.model_id)
            max_context = model_config.contextWindow
        except Exception:
            max_context = 8000

        limit = int(max_context * 0.8)
        system_len = estimate_content_length(self.system_prompt) if self.system_prompt else 0
        available = max(500, limit - system_len)

        total_len = sum(estimate_content_length(str(msg)) for msg in self.history)

        if total_len > available:
            removed_count = 0
            while total_len > available and len(self.history) > 1:
                msg = self.history.pop(0)
                total_len -= estimate_content_length(str(msg))
                removed_count += 1

            if removed_count > 0 and self.history:
                first_msg = self.history[0]
                if not (first_msg.get('role') == 'system' and 'truncated' in str(first_msg.get('content', '')).lower()):
                    self.history.insert(0, {
                        "role": "system",
                        "content": "[System Note: Previous conversation history was truncated to manage context window size.]"
                    })

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
                yield {"type": "final", "content": full_content}
                return

    async def _execute_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """批量并行执行工具调用"""
        async def _run_single_call(tool_call: Dict) -> Dict:
            tool_id = tool_call['id']
            tool_name = tool_call['function']['name']
            raw_args = tool_call['function']['arguments']
            if isinstance(raw_args, str):
                tool_args = json.loads(raw_args) if raw_args.strip() else {}
            else:
                tool_args = raw_args if raw_args else {}

            try:
                result = await self.tools.execute(tool_name, **tool_args)
                return {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": str(result)
                }
            except Exception as e:
                return {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": f"Error: {str(e)}"
                }

        return await asyncio.gather(*[_run_single_call(tc) for tc in tool_calls])

    def clear_history(self, save_current: bool = True):
        """清空对话历史，可选保存当前历史到 L4"""
        if save_current and self.history:
            save_session_history(self.history, summary=self._last_summary, session_id=self.session_id)
        self.history.clear()
        self._conversation_rounds = 0
        self._last_summary = None
        self.session_id = _generate_session_filename()  # 新会话ID

    def interrupt(self, user_input: str):
        """中断当前处理,优先响应用户输入"""
        self._pending_user_input = user_input