"""
LLM 网关客户端模块

架构:
- 子模块在 src/client/ 目录下（私有前缀 _）
- 公共 API 通过此 __init__.py 导出
"""

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Any

# 保持向后兼容的导入（测试依赖这些导入）
from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError

# 从子模块导入
from src.client._execution import (
    chat_completion_with_fallback_internal,
    iterate_fallback_models,
)
from src.client._fallback_chain import FallbackChain
from src.client._init import (
    build_model_config_cache,
    init_clients,
    init_fallback_chain,
    init_rate_limiting,
    init_state_persistence,
)
from src.client._observability import create_llm_span, handle_llm_error
from src.client._persistence import (
    get_persistence_stats,
    restore_state,
    save_state,
    start_persistence_loop,
    stop_persistence_loop,
)
from src.client._queue import (
    get_queue_status,
    request_turn,
    start_queue_dispatcher,
    stop_queue_dispatcher,
)
from src.client._rate_limit_integration import (
    RateLimitTimeoutError,
    execute_with_concurrency_and_rate_limit,
    stream_with_concurrency_and_rate_limit,
    wait_for_turn_and_acquire,
)
from src.client._streaming import (
    stream_chat_completion_single,
    stream_fallback_providers,
    stream_with_retry,
)
from src.client._timeout import TimeoutConfig
from src.client._utils import _resolve_api_key
from src.models import FullConfig, ModelConfig, load_config
from src.rate_limit_db import RateLimitSQLite
from src.rate_limiter import RateLimiter, RateLimitStatus
from src.request_queue import RequestPriority, RequestQueue


class LLMGateway:
    """通用 LLM 网关，支持跨 Provider 降级和请求限流"""

    def __init__(self, config_path: str, vault=None, credential_proxy=None) -> None:
        self.config = load_config(config_path)
        self._vault = vault
        self._credential_proxy = credential_proxy
        self._credential_security_enabled = vault is not None

        # 使用初始化模块（传入主模块的类以支持测试 mock）
        self.clients = init_clients(self.config, vault, AsyncOpenAI)
        self._model_config_cache = build_model_config_cache(self.config)
        self._fallback_chain = init_fallback_chain(self.clients)
        (self._rate_config, self._request_semaphore, self._rate_limiter,
         self._request_queue, self._timeout_config) = init_rate_limiting(
            self.config, RateLimiter, RequestQueue
        )
        self._state_db = init_state_persistence()

        # 运行时状态
        self._queue_started = False
        self._active_count = 0
        self._active_count_lock = asyncio.Lock()
        self._load_factor_cache = 0.0
        self._load_factor_cache_time = 0.0
        self._load_factor_cache_ttl = 5.0
        self._persistence_task: asyncio.Task[None] | None = None
        self._persistence_interval = 60.0

    # ==================== 状态持久化 API ====================

    async def restore_state(self) -> None:
        await restore_state(self._state_db, self._rate_limiter)

    async def save_state(self) -> None:
        await save_state(self._state_db, self._rate_limiter)

    async def start_persistence_loop(self) -> None:
        self._persistence_task = await start_persistence_loop(
            self._state_db, self._rate_limiter, self._persistence_interval, self._persistence_task
        )

    async def stop_persistence_loop(self) -> None:
        await stop_persistence_loop(self._persistence_task, self._state_db, self._rate_limiter)
        self._persistence_task = None

    async def get_persistence_stats(self) -> dict[str, Any] | None:
        return await get_persistence_stats(self._state_db)

    # ==================== 客户端与配置查询 ====================

    async def get_client(self, model_id: str | None = None):
        if model_id:
            provider_id = model_id.split("/")[0]
            if provider_id in self.clients:
                return self.clients[provider_id]
            raise ValueError(f"Unknown provider: {provider_id}")
        if self._fallback_chain:
            _, client = await self._fallback_chain.get_active_client()
            return client
        if self.clients:
            return next(iter(self.clients.values()))
        raise ValueError("No clients initialized")

    async def get_active_provider(self) -> str:
        if self._fallback_chain:
            provider, _ = await self._fallback_chain.get_active_client()
            return provider
        return next(iter(self.clients.keys())) if self.clients else ""

    def get_model_config(self, model_id: str) -> ModelConfig:
        if model_id in self._model_config_cache:
            return self._model_config_cache[model_id]
        provider_id, model_name = model_id.split("/", 1)
        provider = self.config.models.get(provider_id)
        if not provider:
            raise ValueError(f"Unknown provider: {provider_id}")
        for model in provider.models:
            if model.id == model_name:
                self._model_config_cache[model_id] = model
                return model
        raise ValueError(f"Unknown model: {model_name}")

    def get_rate_limit_config(self):
        return self._rate_config

    def get_rate_limit_status(self) -> RateLimitStatus | None:
        return self._rate_limiter.get_status() if self._rate_limiter else None

    def is_rate_limited(self) -> bool:
        return self._rate_limiter.get_status().window_usage_ratio > 0.9 if self._rate_limiter else False

    # ==================== 负载因子与动态超时 ====================

    def get_load_factor(self) -> float:
        now = time.time()
        if now - self._load_factor_cache_time < self._load_factor_cache_ttl:
            return self._load_factor_cache
        q = self._request_queue.get_total_fill_ratio() if self._request_queue else 0.0
        w = self._rate_limiter.get_status().window_usage_ratio if self._rate_limiter else 0.0
        self._load_factor_cache = q * 0.4 + w * 0.6
        self._load_factor_cache_time = now
        return self._load_factor_cache

    def get_dynamic_timeout(self, priority: RequestPriority) -> float:
        return self._timeout_config.get_timeout(priority, self.get_load_factor())

    # ==================== 队列管理 ====================

    async def start_queue_dispatcher(self) -> None:
        self._queue_started = await start_queue_dispatcher(self._request_queue, self._queue_started)

    async def stop_queue_dispatcher(self) -> None:
        self._queue_started = not await stop_queue_dispatcher(self._request_queue, self._queue_started)

    def get_queue_status(self) -> dict[str, Any] | None:
        return get_queue_status(self._request_queue)

    async def request_turn(self, priority: RequestPriority = RequestPriority.NORMAL):
        return await request_turn(self._request_queue, self._queue_started, self.start_queue_dispatcher, priority)

    # ==================== 核心聊天接口 ====================

    async def chat_completion(self, model_id: str, messages: list[dict], priority: int = RequestPriority.NORMAL, **kwargs) -> dict:
        if isinstance(priority, int):
            priority = RequestPriority(priority)
        return await self._execute_three_phase(model_id, messages, priority, **kwargs)

    async def stream_chat_completion(self, model_id: str, messages: list[dict], priority: int = RequestPriority.NORMAL, **kwargs) -> AsyncGenerator[dict, None]:
        if isinstance(priority, int):
            priority = RequestPriority(priority)
        async for chunk in self._stream_three_phase(model_id, messages, priority, **kwargs):
            yield chunk

    # ==================== 内部执行方法 ====================

    async def _execute_three_phase(self, model_id: str, messages: list[dict], priority: RequestPriority, **kwargs) -> dict:
        ticket = await wait_for_turn_and_acquire(
            self._request_queue, self._queue_started, self.start_queue_dispatcher,
            self.get_dynamic_timeout, self.request_turn, priority
        )
        async def _run():
            return await chat_completion_with_fallback_internal(
                model_id, messages, self._fallback_chain, self.clients, self.config.models,
                self.get_client, self.get_model_config, self.get_active_provider, **kwargs
            )
        return await execute_with_concurrency_and_rate_limit(
            self._request_semaphore, self._rate_limiter, self._active_count_lock,
            self._active_count, ticket, priority, _run
        )

    async def _stream_three_phase(self, model_id: str, messages: list[dict], priority: RequestPriority, **kwargs) -> AsyncGenerator[dict, None]:
        ticket = await wait_for_turn_and_acquire(
            self._request_queue, self._queue_started, self.start_queue_dispatcher,
            self.get_dynamic_timeout, self.request_turn, priority
        )
        async def _stream():
            async for chunk in self._stream_internal(model_id, messages, **kwargs):
                yield chunk
        async for chunk in stream_with_concurrency_and_rate_limit(
            self._request_semaphore, self._rate_limiter, self._active_count_lock,
            self._active_count, ticket, priority, _stream
        ):
            yield chunk

    async def _stream_internal(self, model_id: str, messages: list[dict], **kwargs) -> AsyncGenerator[dict, None]:
        provider_id = model_id.split("/", maxsplit=1)[0]
        active_provider = await self.get_active_provider()
        start_time = time.time()
        span = create_llm_span(model_id, active_provider, streaming=True)

        try:
            async for chunk in stream_with_retry(
                model_id, messages, self._fallback_chain, self._rate_limiter,
                span, active_provider, start_time,
                self.get_client, self.get_model_config, stream_chat_completion_single, **kwargs
            ):
                yield chunk
            return
        except (APIConnectionError, RateLimitError, APIStatusError) as e:
            if self._fallback_chain:
                await self._fallback_chain.mark_degraded(provider_id)
                async for chunk in stream_fallback_providers(
                    model_id, messages, self._fallback_chain, self.clients, self.config.models,
                    span, active_provider, start_time, provider_id,
                    self.get_client, self.get_model_config,
                    lambda m, p: iterate_fallback_models(m, p, self._fallback_chain, self.clients, self.config.models)[0][1] if iterate_fallback_models(m, p, self._fallback_chain, self.clients, self.config.models) else None,
                    stream_chat_completion_single, **kwargs
                ):
                    yield chunk
                return
            handle_llm_error(span, active_provider, model_id, start_time, e)
            raise
        except Exception as e:
            handle_llm_error(span, active_provider, model_id, start_time, e)
            raise
        finally:
            if span:
                span.end()

    def _iterate_fallback_models(self, model_id: str, exclude_provider: str) -> list[tuple[str, str]]:
        return iterate_fallback_models(model_id, exclude_provider, self._fallback_chain, self.clients, self.config.models)


__all__ = [
    "FallbackChain",
    "FullConfig",
    "LLMGateway",
    "RateLimitSQLite",
    "RateLimitTimeoutError",
    "TimeoutConfig",
    "_resolve_api_key",
]
