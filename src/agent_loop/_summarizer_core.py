"""
AgentLoop 摘要核心逻辑

Summarizer 类实现，聚合格式化和上下文估算。
"""

import json
import logging

from src.agent_loop._summarizer_context import estimate_context_size, should_summarize
from src.agent_loop._summarizer_formatting import format_events_for_summary
from src.agent_loop._summarizer_types import SUMMARY_PROMPT

logger = logging.getLogger(__name__)


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
        """增加对话轮数"""
        self._conversation_rounds += 1
        return self._conversation_rounds

    def reset_rounds(self) -> None:
        """重置对话轮数"""
        self._conversation_rounds = 0

    def format_events_for_summary(self) -> str:
        """将事件格式化为摘要文本"""
        events = self.session.get_events_since_last_summary(
            [type("EventType", (), {"USER_INPUT": "user_input", "LLM_RESPONSE": "llm_response", "TOOL_RESULT": "tool_result"})]
        )
        return format_events_for_summary(events)

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
            logger.warning(f"Summary generation failed: {type(e).__name__}: {str(e)[:100]}")
            return None

    def estimate_context_size(self, system_prompt: str | None = None) -> int:
        """估算当前上下文 Token 数"""
        messages = self.session.build_context_for_llm(system_prompt=system_prompt)
        return estimate_context_size(messages, system_prompt, self._encoding)

    def should_summarize(self, system_prompt: str | None = None) -> tuple[bool, int, bool]:
        """检查是否需要摘要"""
        estimated_tokens = self.estimate_context_size(system_prompt)
        is_context_full, needs_summary = should_summarize(
            estimated_tokens, self._conversation_rounds,
            self.context_window, self.summary_interval, self.context_usage_threshold
        )
        return needs_summary, estimated_tokens, is_context_full

    async def create_summary_marker(self, is_context_full: bool, session_id: str) -> None:
        """创建摘要标记"""
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


__all__ = ["Summarizer"]