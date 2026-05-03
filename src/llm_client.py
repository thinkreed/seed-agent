"""
LLMClient (大脑) 模块

基于 Harness Engineering "三件套解耦架构" 设计：
- LLMClient 是大脑，负责推理
- 本身无状态，只接收上下文并返回推理结果
- 可配置多个模型实例，支持多模型切换
- 从 AgentLoop 中解耦，降低首 Token 延迟

核心职责：
1. 封装 LLM Gateway 的推理调用
2. 提供统一的推理 API (普通/流式)
3. 处理模型配置获取
4. 不持有任何对话状态

性能优化：
- 大脑与容器(Sandbox)分离
- 首 Token 延迟降低 60-90%
- 支持多 Provider 故障转移

使用方式：
    llm = LLMClient(gateway, "qwen/qwen-coder-plus")
    response = await llm.reason(context_messages, tools=tool_schemas)
"""

import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from src.client import LLMGateway
from src.observability import (
    StatusCode,
    get_tracer,
    is_observability_enabled,
    record_llm_span_error,
    record_llm_success,
)
from src.request_queue import RequestPriority

logger = logging.getLogger(__name__)

# OpenTelemetry 状态
_OBSERVABILITY_ENABLED = is_observability_enabled()


def _parse_model_id(model_id: str) -> tuple[str, str]:
    """解析 model_id 为 (provider, model_name)

    Args:
        model_id: 模型标识符，格式如 "provider/model-name"

    Returns:
        (provider, model_name) 元组，若无 provider 则返回 ("unknown", model_id)
    """
    if "/" in model_id:
        parts = model_id.split("/", 1)
        return parts[0], parts[1]
    return "unknown", model_id

try:
    from opentelemetry.trace import Span

    _SPAN_TYPE_AVAILABLE = True
except ImportError:
    Span = None  # type: ignore[misc,assignment]
    _SPAN_TYPE_AVAILABLE = False


class ReasonResult:
    """推理结果封装"""

    def __init__(
        self,
        response: dict[str, Any],
        model_id: str,
        duration_ms: float,
        tokens_used: int | None = None,
    ):
        self.response = response
        self.model_id = model_id
        self.duration_ms = duration_ms
        self.tokens_used = tokens_used

    def get_content(self) -> str:
        """获取响应内容"""
        return (
            self.response.get("choices", [{}])[0].get("message", {}).get("content", "")
        )

    def get_tool_calls(self) -> list[dict] | None:
        """获取工具调用"""
        return (
            self.response.get("choices", [{}])[0].get("message", {}).get("tool_calls")
        )

    def is_tool_call(self) -> bool:
        """是否包含工具调用"""
        return bool(self.get_tool_calls())

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return self.response


class LLMClient:
    """LLM 大脑 - 负责推理，无状态

    三件套解耦架构中的"大脑"层：
    - 接收上下文 messages (从 Session 构建)
    - 调用 LLM Gateway 执行推理
    - 返回推理结果 (响应 + 可能的 tool_calls)
    - 不持有任何状态

    性能优化：
    - 大脑与容器(Sandbox)分离
    - 首 Token 延迟降低 60-90%
    - 支持 Provider 故障转移

    关键特性：
    - 无状态：不存储对话历史
    - 可替换：随时创建/销毁
    - 可观测：OpenTelemetry 集成
    """

    def __init__(
        self,
        gateway: LLMGateway,
        model_id: str,
        default_priority: int = RequestPriority.NORMAL,
    ):
        """初始化 LLMClient

        Args:
            gateway: LLM Gateway 实例
            model_id: 模型 ID (格式: provider/model)
            default_priority: 默认请求优先级
        """
        self.gateway = gateway
        self.model_id = model_id
        self.default_priority = default_priority

        # 缓存模型配置（避免重复查询）
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
        """执行推理

        Args:
            context: 上下文消息列表 (从 Session 构建)
            tools: 可用工具 schema 列表
            priority: 请求优先级 (默认使用 default_priority)
            **kwargs: 其他 LLM 参数

        Returns:
            推理结果 dict，包含:
            - choices: 响应选择列表
            - usage: Token 使用统计
            - model: 使用的模型 ID
        """
        if priority is None:
            priority = self.default_priority

        start_time = time.time()

        logger.debug(
            f"LLMClient.reason: model={self.model_id}, "
            f"context_len={len(context)}, tools={len(tools) if tools else 0}"
        )

        # OpenTelemetry Span
        span = self._start_llm_span(context, tools)

        try:
            response = await self.gateway.chat_completion(
                self.model_id, context, priority=priority, tools=tools, **kwargs
            )

            duration_ms = (time.time() - start_time) * 1000

            # 记录成功指标
            if _OBSERVABILITY_ENABLED:
                usage = response.get("usage", {})
                provider, model_name = _parse_model_id(self.model_id)
                record_llm_success(
                    provider,
                    model_name,
                    usage.get("prompt_tokens", 0),
                    usage.get("completion_tokens", 0),
                    duration_ms,
                )

            self._finish_llm_span(span, start_time, success=True)

            return response

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            logger.error(f"LLMClient.reason failed: {type(e).__name__}: {e}")

            # 记录错误
            if span:
                record_llm_span_error(span, e)

            self._finish_llm_span(span, start_time, success=False, error=e)

            raise

    async def stream_reason(
        self,
        context: list[dict[str, Any]],
        tools: list[dict] | None = None,
        priority: int | None = None,
        **kwargs,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """流式推理

        Args:
            context: 上下文消息列表
            tools: 可用工具 schema
            priority: 请求优先级
            **kwargs: 其他 LLM 参数

        Yields:
            流式响应 chunk
        """
        if priority is None:
            priority = self.default_priority

        start_time = time.time()
        chunk_count = 0

        logger.debug(
            f"LLMClient.stream_reason: model={self.model_id}, "
            f"context_len={len(context)}, tools={len(tools) if tools else 0}"
        )

        # OpenTelemetry Span
        span = self._start_llm_span(context, tools, is_stream=True)

        try:
            async for chunk in self.gateway.stream_chat_completion(
                self.model_id, context, priority=priority, tools=tools, **kwargs
            ):
                chunk_count += 1
                yield chunk

            duration_ms = (time.time() - start_time) * 1000

            # 记录成功指标（估算 token 数）
            if _OBSERVABILITY_ENABLED:
                estimated_tokens = chunk_count * 10  # 每chunk约10 tokens
                provider, model_name = _parse_model_id(self.model_id)
                record_llm_success(
                    provider,
                    model_name,
                    estimated_tokens // 2,  # 估算输入 tokens
                    estimated_tokens // 2,  # 估算输出 tokens
                    duration_ms,
                )

            self._finish_llm_span(span, start_time, success=True)

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            logger.error(f"LLMClient.stream_reason failed: {type(e).__name__}: {e}")

            if span:
                record_llm_span_error(span, e)

            self._finish_llm_span(span, start_time, success=False, error=e)

            raise

    # === 辅助方法 ===

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
        """获取当前活跃的 Provider（通过 Gateway）"""
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

    # === OpenTelemetry ===

    def _start_llm_span(
        self,
        context: list[dict[str, Any]],
        tools: list[dict] | None,
        is_stream: bool = False,
    ) -> "Span | None":
        """创建 LLM Span"""
        tracer = get_tracer()
        if not (tracer and _OBSERVABILITY_ENABLED):
            return None

        span = tracer.start_span("seed.llm.reason")
        span.set_attribute("seed.llm.model_id", self.model_id)
        span.set_attribute("seed.llm.context_length", len(context))
        span.set_attribute("seed.llm.tools_count", len(tools) if tools else 0)
        span.set_attribute("seed.llm.is_stream", is_stream)
        return span

    def _finish_llm_span(
        self,
        span: "Span | None",
        start_time: float,
        success: bool,
        error: Exception | None = None,
    ) -> None:
        """完成 LLM Span"""
        if not span:
            return

        duration_ms = (time.time() - start_time) * 1000
        span.set_attribute("seed.llm.duration_ms", duration_ms)

        if success:
            span.set_status(StatusCode.OK)
        elif error:
            span.record_exception(error)
            span.set_attribute("seed.error.message", str(error)[:500])
            span.set_status(StatusCode.ERROR, str(error)[:200])
        span.end()


class LLMClientPool:
    """LLM 客户端池 - 支持多模型实例

    用于管理多个 LLMClient 实例，支持：
    - 多模型并行推理
    - 模型故障转移
    - 负载均衡

    使用场景：
    - 多模型协作
    - 故障转移
    - A/B 测试
    """

    def __init__(self, gateway: LLMGateway):
        """初始化 LLMClientPool

        Args:
            gateway: LLM Gateway 实例
        """
        self._gateway = gateway
        self._clients: dict[str, LLMClient] = {}
        self._primary_model: str | None = None

        logger.info("LLMClientPool initialized")

    def add_client(
        self,
        model_id: str,
        is_primary: bool = False,
        priority: int = RequestPriority.NORMAL,
    ) -> LLMClient:
        """添加 LLM 客户端

        Args:
            model_id: 模型 ID
            is_primary: 是否为主模型
            priority: 默认优先级

        Returns:
            LLMClient 实例
        """
        client = LLMClient(self._gateway, model_id, priority)
        self._clients[model_id] = client

        if is_primary:
            self._primary_model = model_id

        logger.info(f"LLMClient added: model={model_id}, primary={is_primary}")
        return client

    def get_client(self, model_id: str | None = None) -> LLMClient:
        """获取 LLM 客户端

        Args:
            model_id: 模型 ID，如不指定则使用主模型

        Returns:
            LLMClient 实例
        """
        if model_id:
            if model_id not in self._clients:
                raise ValueError(f"Model not in pool: {model_id}")
            return self._clients[model_id]

        if not self._primary_model:
            raise ValueError("No primary model set")

        return self._clients[self._primary_model]

    def get_primary_client(self) -> LLMClient:
        """获取主模型客户端"""
        if not self._primary_model:
            raise ValueError("No primary model set")
        return self._clients[self._primary_model]

    def list_models(self) -> list[str]:
        """列出所有模型"""
        return list(self._clients.keys())

    def remove_client(self, model_id: str) -> bool:
        """移除客户端"""
        if model_id in self._clients:
            del self._clients[model_id]
            if self._primary_model == model_id:
                self._primary_model = next(iter(self._clients.keys()), None)
            logger.info(f"LLMClient removed: model={model_id}")
            return True
        return False

    async def reason_with_fallback(
        self,
        context: list[dict[str, Any]],
        tools: list[dict] | None = None,
        priority: int | None = None,
        fallback_models: list[str] | None = None,
    ) -> dict[str, Any]:
        """带故障转移的推理

        Args:
            context: 上下文消息
            tools: 工具 schema
            priority: 优先级
            fallback_models: 故障转移模型列表

        Returns:
            推理结果
        """
        models_to_try = [self._primary_model] if self._primary_model else []
        if fallback_models:
            models_to_try.extend(fallback_models)

        for model_id in models_to_try:
            if model_id not in self._clients:
                continue

            try:
                client = self._clients[model_id]
                return await client.reason(context, tools, priority)
            except Exception as e:
                logger.warning(f"Model {model_id} failed: {type(e).__name__}: {e}")
                continue

        raise RuntimeError("All models failed, no fallback available")

    def get_pool_status(self) -> dict[str, Any]:
        """获取池状态"""
        return {
            "models": list(self._clients.keys()),
            "primary_model": self._primary_model,
            "clients_count": len(self._clients),
        }
