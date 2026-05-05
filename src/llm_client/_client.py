"""LLMClient 核心模块

LLMClient: 大脑 - 负责推理，无状态
"""

import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from src.client import LLMGateway
from src.observability import record_llm_span_error, record_llm_success
from src.request_queue import RequestPriority

from ._result import parse_model_id
from ._span import finish_llm_span, is_observability_available, start_llm_span

logger = logging.getLogger(__name__)

try:
    from opentelemetry.trace import Span
except ImportError:
    Span = None  # type: ignore[misc,assignment]


class LLMClient:
    """LLM 大脑 - 负责推理，无状态"""

    def __init__(
        self,
        gateway: LLMGateway,
        model_id: str,
        default_priority: int = RequestPriority.NORMAL,
    ):
        self.gateway = gateway
        self.model_id = model_id
        self.default_priority = default_priority
        self._model_config = gateway.get_model_config(model_id)

        logger.info(
            f"LLMClient initialized: model={model_id}, "
            f"context_window={self._model_config.contextWindow}"
        )

    async def reason(
        self,
        context: list[dict[str, Any]],
        tools: list[dict] | None = None,
        priority: int | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """执行推理"""
        if priority is None:
            priority = self.default_priority

        start_time = time.time()
        span = start_llm_span(self.model_id, context, tools)

        try:
            response = await self.gateway.chat_completion(
                self.model_id, context, priority=priority, tools=tools, **kwargs
            )

            duration_ms = (time.time() - start_time) * 1000

            if is_observability_available():
                usage = response.get("usage", {})
                provider, model_name = parse_model_id(self.model_id)
                record_llm_success(
                    provider, model_name,
                    usage.get("prompt_tokens", 0),
                    usage.get("completion_tokens", 0),
                    duration_ms,
                )

            finish_llm_span(span, start_time, success=True)
            return response

        except Exception as e:
            if span:
                record_llm_span_error(span, e)
            finish_llm_span(span, start_time, success=False, error=e)
            raise

    async def stream_reason(
        self,
        context: list[dict[str, Any]],
        tools: list[dict] | None = None,
        priority: int | None = None,
        **kwargs,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """流式推理"""
        if priority is None:
            priority = self.default_priority

        start_time = time.time()
        chunk_count = 0
        span = start_llm_span(self.model_id, context, tools, is_stream=True)

        try:
            async for chunk in self.gateway.stream_chat_completion(
                self.model_id, context, priority=priority, tools=tools, **kwargs
            ):
                chunk_count += 1
                yield chunk

            duration_ms = (time.time() - start_time) * 1000

            if is_observability_available():
                estimated_tokens = chunk_count * 10
                provider, model_name = parse_model_id(self.model_id)
                record_llm_success(
                    provider, model_name,
                    estimated_tokens // 2,
                    estimated_tokens // 2,
                    duration_ms,
                )

            finish_llm_span(span, start_time, success=True)

        except Exception as e:
            if span:
                record_llm_span_error(span, e)
            finish_llm_span(span, start_time, success=False, error=e)
            raise

    def get_context_window(self) -> int:
        """获取模型上下文窗口大小"""
        return self._model_config.contextWindow

    def get_max_output_tokens(self) -> int:
        """获取最大输出 token 数"""
        return getattr(self._model_config, "maxOutputTokens", 4096)

    def get_model_info(self) -> dict[str, Any]:
        """获取模型信息"""
        return {
            "model_id": self.model_id,
            "context_window": self._model_config.contextWindow,
            "max_output_tokens": self.get_max_output_tokens(),
            "provider": self.model_id.split("/", 1)[0]
            if "/" in self.model_id
            else "unknown",
        }

    async def get_active_provider(self) -> str:
        """获取当前活跃的 Provider"""
        return await self.gateway.get_active_provider()

    def get_rate_limit_status(self) -> dict[str, Any] | None:
        """获取限流状态"""
        status = self.gateway.get_rate_limit_status()
        if status:
            return {
                "tokens_available": status.tokens_available,
                "window_usage_ratio": status.window_usage_ratio,
                "is_limited": self.gateway.is_rate_limited(),
            }
        return None