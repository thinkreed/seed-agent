"""
LLM 调用钩子

包含：
- LLM 调用钩子：llm_call_before, llm_call_after
- 流式响应钩子：llm_stream_start, llm_stream_chunk, llm_stream_end
"""

import logging
from typing import Any

from src.lifecycle_hooks import HookPoint, LifecycleHookRegistry

logger = logging.getLogger(__name__)


def register_llm_hooks(registry: LifecycleHookRegistry) -> None:
    """注册 LLM 调用钩子"""

    @registry.register(HookPoint.LLM_CALL_BEFORE, priority=0, name="llm_log_call")
    def llm_log_call(context: dict[str, Any]) -> None:
        """记录 LLM 调用"""
        model_id = context.get("model_id", "unknown")
        messages_count = len(context.get("messages", []))
        tools_count = len(context.get("tools", []))

        logger.debug(
            f"LLM call: model={model_id}, "
            f"messages={messages_count}, tools={tools_count}"
        )

    @registry.register(HookPoint.LLM_CALL_BEFORE, priority=1, name="llm_context_check")
    def llm_context_check(context: dict[str, Any]) -> None:
        """检查上下文大小"""
        messages = context.get("messages", [])
        context_window = context.get("context_window", 100000)

        # 简单估算 token 数
        total_chars = sum(
            len(m.get("content", "")) if isinstance(m.get("content"), str) else 0
            for m in messages
        )
        estimated_tokens = int(total_chars * 0.5)

        if estimated_tokens > context_window * 0.75:
            logger.warning(
                f"Context near limit: estimated={estimated_tokens}, "
                f"window={context_window}"
            )
            context["context_near_limit"] = True

    @registry.register(
        HookPoint.LLM_CALL_AFTER, priority=0, name="llm_validate_response"
    )
    def llm_validate_response(context: dict[str, Any]) -> None:
        """验证 LLM 响应"""
        response = context.get("response")

        if response is None:
            raise ValueError("LLM response is None")

        choices = response.get("choices", [])
        if not choices:
            raise ValueError("LLM response has no choices")

        # 检查是否有效内容
        message = choices[0].get("message", {})
        has_content = message.get("content") is not None
        has_tool_calls = message.get("tool_calls") is not None

        if not has_content and not has_tool_calls:
            logger.warning("LLM response has neither content nor tool_calls")

    @registry.register(HookPoint.LLM_CALL_AFTER, priority=1, name="llm_log_response")
    def llm_log_response(context: dict[str, Any]) -> None:
        """记录 LLM 响应"""
        response = context.get("response")
        duration_ms = context.get("duration_ms", 0)

        choices = response.get("choices", []) if response else []
        message = choices[0].get("message", {}) if choices else {}

        content_preview = str(message.get("content") or "")[:50]
        tool_calls_count = len(message.get("tool_calls") or [])

        logger.debug(
            f"LLM response: duration={duration_ms:.2f}ms, "
            f"content={content_preview}..., tool_calls={tool_calls_count}"
        )

    @registry.register(
        HookPoint.LLM_STREAM_START, priority=0, name="llm_log_stream_start"
    )
    def llm_log_stream_start(context: dict[str, Any]) -> None:
        """记录流式响应开始"""
        model_id = context.get("model_id", "unknown")
        logger.debug(f"LLM stream started: model={model_id}")

    @registry.register(
        HookPoint.LLM_STREAM_CHUNK, priority=0, name="llm_accumulate_chunk"
    )
    def llm_accumulate_chunk(context: dict[str, Any]) -> None:
        """累积流式响应块"""
        chunk = context.get("chunk")
        accumulator = context.get("accumulator")

        if accumulator is not None and chunk:
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            content = delta.get("content", "")
            if content:
                accumulator["content"] = accumulator.get("content", "") + content

    @registry.register(HookPoint.LLM_STREAM_END, priority=0, name="llm_log_stream_end")
    def llm_log_stream_end(context: dict[str, Any]) -> None:
        """记录流式响应结束"""
        duration_ms = context.get("duration_ms", 0)
        total_chunks = context.get("total_chunks", 0)

        logger.debug(
            f"LLM stream ended: duration={duration_ms:.2f}ms, chunks={total_chunks}"
        )