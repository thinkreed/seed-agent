"""
AgentLoop 摘要机制

职责:
- 事件格式化摘要
- LLM 摘要生成
- 摘要触发判断
- 摘要标记创建
"""

import json
import logging

from src.session_event_stream import EventType

logger = logging.getLogger(__name__)


SUMMARY_PROMPT = """请将以下对话历史压缩成简洁的摘要，保留关键信息：
1. 用户的核心需求和意图
2. 已完成的关键操作和结果
3. 重要发现或决策
4. 未完成的任务或待处理事项

对话历史：
{history}

请用简洁的要点形式输出摘要（不超过300字）："""


class Summarizer:
    """摘要管理器"""

    SUMMARY_PROMPT = SUMMARY_PROMPT

    def __init__(
        self,
        session,
        gateway,
        model_id: str,
        context_window: int,
        summary_interval: int = 10,
        encoding=None,
    ):
        self.session = session
        self.gateway = gateway
        self.model_id = model_id
        self.context_window = context_window
        self.summary_interval = summary_interval
        self._encoding = encoding
        self.context_usage_threshold = 0.75
        self._conversation_rounds = 0

    def increment_rounds(self) -> int:
        """增加对话轮数并返回当前值"""
        self._conversation_rounds += 1
        return self._conversation_rounds

    def reset_rounds(self) -> None:
        """重置对话轮数"""
        self._conversation_rounds = 0

    def format_events_for_summary(self) -> str:
        """将事件格式化为摘要文本"""
        events = self.session.get_events_since_last_summary(
            [EventType.USER_INPUT, EventType.LLM_RESPONSE, EventType.TOOL_RESULT]
        )

        lines = []
        for event in events:
            event_type = event["type"]
            data = event["data"]

            if event_type == EventType.USER_INPUT.value:
                lines.append(f"user: {data.get('content', '')}")
            elif event_type == EventType.LLM_RESPONSE.value:
                content = data.get("content", "")
                if data.get("tool_calls"):
                    tc_names = [
                        tc["function"]["name"]
                        for tc in data["tool_calls"]
                        if tc.get("function")
                    ]
                    content = f"[Tool Calls: {', '.join(tc_names)}]"
                if content:
                    lines.append(f"assistant: {content}")
            elif event_type == EventType.TOOL_RESULT.value:
                content = data.get("content", "")[:200]
                lines.append(f"tool: {content}")

        return "\n".join(lines)

    async def summarize_events(self) -> str | None:
        """使用 LLM 总结事件流"""
        events_text = self.format_events_for_summary()
        if not events_text:
            return None

        prompt = self.SUMMARY_PROMPT.format(history=events_text)
        try:
            response = await self.gateway.chat_completion(
                self.model_id, [{"role": "user", "content": prompt}], tools=None
            )
            choices = response.get("choices", [])
            if not choices:
                logger.warning("Summary generation: LLM returned empty choices")
                return None
            summary = choices[0].get("message", {}).get("content", "")
            if not summary:
                return None
            return summary.strip()
        except Exception as e:
            logger.warning(
                f"Summary generation failed: {type(e).__name__}: {str(e)[:100]}"
            )
            return None

    def estimate_context_size(self, system_prompt: str | None = None) -> int:
        """估算当前上下文 Token 数"""
        messages = self.session.build_context_for_llm(system_prompt=system_prompt)
        total = 0

        if system_prompt:
            total += self._encode_text(system_prompt)

        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self._encode_text(content)
            if msg.get("tool_calls"):
                total += self._encode_text(json.dumps(msg["tool_calls"]))

        return total

    def _encode_text(self, text: str) -> int:
        """编码文本返回 token 数"""
        if self._encoding:
            return len(self._encoding.encode(text))
        return int(len(text) * 0.7)

    def should_summarize(self, system_prompt: str | None = None) -> tuple[bool, int, bool]:
        """检查是否需要摘要

        Returns:
            (should_summarize, estimated_tokens, is_context_full)
        """
        estimated_tokens = self.estimate_context_size(system_prompt)
        token_threshold = self.context_window * self.context_usage_threshold
        is_context_full = estimated_tokens > token_threshold
        is_round_limit_reached = self._conversation_rounds >= self.summary_interval
        return (
            (is_context_full or is_round_limit_reached),
            estimated_tokens,
            is_context_full,
        )

    async def create_summary_marker(self, is_context_full: bool, session_id: str) -> None:
        """创建摘要标记 (不截断历史)"""
        summary = await self.summarize_events()
        if not summary:
            return

        current_event_id = self.session.get_event_count()
        self.session.create_summary_marker(
            current_event_id, summary, {"is_context_full": is_context_full}
        )

        from src.tools.memory_tools import _save_session_history
        _save_session_history([], summary=summary, session_id=session_id)

        self.reset_rounds()
        logger.info(f"Summary marker created: covers events 1-{current_event_id}")

    async def maybe_summarize(self, system_prompt: str | None = None, session_id: str = "") -> None:
        """检查并执行摘要"""
        needs_summary, estimated_tokens, is_context_full = self.should_summarize(system_prompt)
        if not needs_summary:
            return

        logger.info(
            f"Summary triggered: tokens={estimated_tokens}/{self.context_window}, "
            f"rounds={self._conversation_rounds}/{self.summary_interval}"
        )

        await self.create_summary_marker(is_context_full, session_id)