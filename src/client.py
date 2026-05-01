"""
LLM 网关客户端模块

负责:
1. 多提供商 API 调用 (OpenAI 兼容接口、配置化路由)
2. 智能重试机制 (指数退避、429 限流处理、超时重试)
3. 请求队列管理 (优先级调度、并发控制、背压处理)
4. 限流保护 (Token Bucket、Rolling Window、SQLite 持久化)
5. 流式响应处理 (Server-Sent Events、Tool Call 累积)

核心特性:
- 支持多提供商故障转移
- 动态超时调整 (基于负载因子)
- 完整的错误分类与日志记录
- OpenTelemetry 可观测性 (Token/Metrics/Tracing)
"""

import asyncio
import logging
import os
import random
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError

from src.models import FullConfig, ModelConfig, RateLimitConfig, load_config
from src.rate_limit_db import RateLimitSQLite
from src.rate_limiter import (
    RateLimiter,
    RateLimitStatus,
    RollingWindowState,
    TokenBucketState,
)
from src.request_queue import (
    QueueConfig,
    RequestPriority,
    RequestQueue,
    TurnTicket,
    TurnWaitTimeout,
)


# 使用自定义限流异常，避免 OpenAI SDK 的类型限制
class RateLimitTimeoutError(Exception):
    """自定义限流等待超时异常"""
    pass

# OpenTelemetry 可观测性
try:
    from opentelemetry import trace
    from opentelemetry.trace import StatusCode

    from src.observability import (
        SPAN_LLM_REQUEST,
        add_fallback_event,
        classify_error,
        get_tracer,
        record_llm_error,
        record_llm_span_error,
        record_llm_success,
        set_llm_span_attributes,
    )
    _OBSERVABILITY_ENABLED = True
except ImportError:
    _OBSERVABILITY_ENABLED = False
    # Fallback: 创建 dummy 函数（使用 type: ignore 避免签名不一致警告）
    from opentelemetry import trace as _trace
    from opentelemetry.trace import Span as _Span
    from opentelemetry.trace import StatusCode as _StatusCode
    from opentelemetry.trace import Tracer as _Tracer

    def get_tracer() -> _Tracer:  # type: ignore[misc]
        return _trace.NoOpTracer()

    def record_llm_success(provider: str, model: str, input_tokens: int, output_tokens: int, duration_ms: float) -> None:  # type: ignore[misc]
        pass

    def record_llm_error(provider: str, model: str, duration_ms: float, error_type: str) -> None:  # type: ignore[misc]
        pass

    def classify_error(error: Exception) -> str:
        return "api_error"

    def record_llm_span_error(span: _Span, error: Exception) -> str:  # type: ignore[misc]
        return "api_error"

    def set_llm_span_attributes(span: _Span, model: str, provider: str, streaming: bool = False, input_tokens: Optional[int] = None, output_tokens: Optional[int] = None) -> None:  # type: ignore[misc]
        pass

    def add_fallback_event(span: _Span, from_provider: str, to_provider: str, reason: str, attempt: int) -> None:  # type: ignore[misc]
        pass

    SPAN_LLM_REQUEST = "seed.llm.request"
    StatusCode = _StatusCode  # type: ignore[misc,assignment]
    trace = _trace  # type: ignore[misc,assignment]

logger = logging.getLogger("seed_agent")


@dataclass
class TimeoutConfig:
    """等待超时配置（可动态调整）"""

    # 基础超时（秒）
    base_timeouts: dict[RequestPriority, float] = field(
        default_factory=lambda: {
            RequestPriority.CRITICAL: 30.0,
            RequestPriority.HIGH: 60.0,
            RequestPriority.NORMAL: 120.0,
            RequestPriority.LOW: 300.0,
        }
    )

    # 动态调整参数
    auto_adjust_enabled: bool = True
    load_factor_threshold: float = 0.7
    min_multiplier: float = 0.5
    max_multiplier: float = 2.0

    def get_timeout(self, priority: RequestPriority, load_factor: float) -> float:
        """获取动态超时

        Args:
            priority: 请求优先级
            load_factor: 当前负载因子（0.0-1.0）

        Returns:
            动态超时时间（秒）
        """
        base = self.base_timeouts.get(priority, 120.0)

        if load_factor > self.load_factor_threshold:
            # 高负载：延长超时，给更多等待时间
            excess = load_factor - self.load_factor_threshold
            multiplier = 1.0 + excess * 1.5
            multiplier = min(multiplier, self.max_multiplier)
        else:
            # 低负载：缩短超时，快速处理或快速失败
            deficit = self.load_factor_threshold - load_factor
            multiplier = 1.0 - deficit * 0.5
            multiplier = max(multiplier, self.min_multiplier)

        return base * multiplier


class FallbackChain:
    """跨 Provider 降级链：primary 失败时自动切换到 fallback

    借鉴 CodeBrain 架构设计的优雅降级机制。
    """

    def __init__(self, providers: list[str], clients: dict[str, AsyncOpenAI]):
        self._providers = providers  # 优先级列表：[primary, fallback1, fallback2, ...]
        self._clients = clients
        self._active_provider: str | None = None  # 当前活跃的 provider
        self._status: str = "healthy"  # healthy, degraded, unavailable

    def get_active_client(self) -> tuple[str, AsyncOpenAI]:
        """获取当前活跃的 provider 和 client

        优化：使用缓存避免每次遍历
        """
        # 快速路径：已缓存活跃 provider
        if self._active_provider and self._active_provider in self._clients:
            return self._active_provider, self._clients[self._active_provider]

        # 尝试第一个可用 provider（仅首次或切换后）
        if self._providers:
            first_provider = self._providers[0]
            if first_provider in self._clients:
                self._active_provider = first_provider
                return first_provider, self._clients[first_provider]

        raise ValueError("No available provider")

    def mark_degraded(self, failed_provider: str):
        """标记 provider 失败，切换到下一个"""
        logger.warning(f"Provider {failed_provider} failed, attempting fallback")

        # 找到下一个可用 provider
        failed_idx = self._providers.index(failed_provider) if failed_provider in self._providers else -1
        for i, provider in enumerate(self._providers):
            if i > failed_idx and provider in self._clients:
                self._active_provider = provider
                self._status = "degraded"
                logger.info(f"Switched to fallback provider: {provider}")
                return

        # 无可用 fallback
        self._active_provider = None
        self._status = "unavailable"
        # 移除失败的 provider 防止 get_active_client 重新选中
        if failed_provider in self._providers:
            self._providers.remove(failed_provider)
        logger.error("All providers failed, no fallback available")

    def mark_healthy(self, provider: str):
        """标记 provider 健康"""
        self._active_provider = provider
        self._status = "healthy"

    @property
    def status(self) -> str:
        return self._status


class LLMGateway:
    """通用 LLM 网关，支持跨 Provider 降级和请求限流

    TurnTicket 模式：
    - 阶段1：排队入场（request_turn + wait_for_turn）
    - 阶段2：抢执行位置（semaphore）
    - 阶段3：限流检查（rate_limiter）
    - 阶段4：执行（execute with fallback）
    """

    def __init__(self, config_path: str):
        self.config: FullConfig = load_config(config_path)
        self.clients: dict[str, AsyncOpenAI] = {}
        self._fallback_chain: FallbackChain | None = None

        # 限流组件
        self._rate_limiter: RateLimiter | None = None
        self._rate_config: RateLimitConfig | None = None
        self._request_semaphore: asyncio.Semaphore | None = None

        # 请求队列（TurnTicket 模式）
        self._request_queue: RequestQueue | None = None
        self._queue_config: QueueConfig | None = None
        self._timeout_config: TimeoutConfig = TimeoutConfig()
        self._queue_started = False

        # 活跃请求数（用于负载因子计算）
        self._active_count: int = 0
        self._active_count_lock = asyncio.Lock()

        # 状态持久化
        self._state_db: RateLimitSQLite | None = None
        self._persistence_task: asyncio.Task | None = None
        self._persistence_interval = 60.0  # 每分钟持久化一次

        self._init_clients()
        self._init_fallback_chain()
        self._init_rate_limiting()
        self._init_state_persistence()

    def _init_clients(self):
        """为每个 provider 初始化客户端"""
        for provider_id, provider_cfg in self.config.models.items():
            if provider_cfg.api == "openai-completions":
                api_key = self._resolve_api_key(provider_cfg.apiKey)
                self.clients[provider_id] = AsyncOpenAI(
                    base_url=provider_cfg.baseUrl,
                    api_key=api_key
                )

    def _init_fallback_chain(self):
        """初始化降级链"""
        # 从配置获取 provider 优先级（按定义顺序）
        providers = list(self.clients.keys())
        if providers:
            self._fallback_chain = FallbackChain(providers, self.clients)

    def _init_rate_limiting(self):
        """从配置初始化限流组件"""
        # 获取第一个有 rateLimit 配置的 provider
        for provider_id, provider_cfg in self.config.models.items():
            if provider_cfg.rateLimit:
                self._rate_config = provider_cfg.rateLimit
                break

        # 如果没有配置，使用默认百炼规格
        if self._rate_config is None:
            self._rate_config = RateLimitConfig()
            logger.info("Using default rate limit config (Bailian: 6000/5h)")

        config = self._rate_config

        # 1. Semaphore (并发控制)
        self._request_semaphore = asyncio.Semaphore(config.maxConcurrent)

        # 2. Rate Limiter (Token Bucket + Rolling Window)
        self._rate_limiter = RateLimiter(
            rate=config.get_effective_rate(),
            capacity=config.burstCapacity,
            window_limit=config.get_window_limit(),
            window_duration=config.get_window_duration(),
        )

        # 3. Request Queue (TurnTicket 模式)
        # 尝试从配置加载 QueueConfig
        queue_config = self._load_queue_config()
        self._request_queue = RequestQueue(config=queue_config)

        logger.info(
            f"Rate limiting initialized: "
            f"rate={config.get_effective_rate():.3f} req/sec, "
            f"burst={config.burstCapacity}, "
            f"window={config.get_window_limit()}/{config.get_window_duration():.0f}s, "
            f"concurrent={config.maxConcurrent}, "
            f"queue_critical={queue_config.critical_max_size}, "
            f"queue_normal={queue_config.normal_max_size}"
        )

    def _load_queue_config(self) -> QueueConfig:
        """从配置加载 QueueConfig"""
        # 尝试从 FullConfig 的 queue 字段加载
        if hasattr(self.config, 'queue') and self.config.queue:
            return QueueConfig(
                critical_max_size=self.config.queue.critical_max_size,
                critical_backpressure_threshold=self.config.queue.critical_backpressure_threshold,
                critical_dispatch_rate=self.config.queue.critical_dispatch_rate,
                critical_target_wait_time=self.config.queue.critical_target_wait_time,
                normal_max_size=self.config.queue.normal_max_size,
                normal_backpressure_threshold=self.config.queue.normal_backpressure_threshold,
                normal_dispatch_rate=self.config.queue.normal_dispatch_rate,
                normal_target_wait_time=self.config.queue.normal_target_wait_time,
                auto_adjust_enabled=self.config.queue.auto_adjust_enabled,
            )

        # 使用默认值
        return QueueConfig()

    def _init_state_persistence(self):
        """初始化状态持久化"""
        self._state_db = RateLimitSQLite()
        logger.info(f"State persistence initialized: {self._state_db.DB_PATH}")

    async def restore_state(self) -> None:
        """从持久化恢复限流状态"""
        if not self._state_db or not self._rate_limiter:
            return

        try:
            state = await self._state_db.load_state()

            # 恢复 Token Bucket 状态
            bucket_state = TokenBucketState(
                tokens=state.tokens_available,
                last_refill_time=state.last_refill_time
            )
            self._rate_limiter.token_bucket.restore_state(bucket_state)

            # 恢复滚动窗口状态
            window_state = RollingWindowState(
                requests=state.requests_in_window,
                total_requests_lifetime=state.total_requests_lifetime
            )
            self._rate_limiter.window_tracker.restore_state(window_state)

            logger.info(
                f"Rate limit state restored: "
                f"tokens={state.tokens_available:.1f}, "
                f"window_requests={len(state.requests_in_window)}, "
                f"lifetime_requests={state.total_requests_lifetime}"
            )
        except Exception as e:
            logger.warning(f"Failed to restore rate limit state: {e}")

    async def save_state(self) -> None:
        """持久化限流状态"""
        if not self._state_db or not self._rate_limiter:
            return

        try:
            bucket_state, window_state = self._rate_limiter.get_state()

            # 保存 Token Bucket 状态
            await self._state_db.save_bucket_state(bucket_state)

            # 保存滚动窗口状态
            await self._state_db.save_window_state(window_state)

            logger.debug("Rate limit state saved")
        except Exception as e:
            logger.warning(f"Failed to save rate limit state: {e}")

    async def start_persistence_loop(self) -> None:
        """启动状态持久化循环"""
        if self._persistence_task:
            logger.warning("Persistence loop already running")
            return

        # 先恢复状态
        await self.restore_state()

        # 启动定时持久化任务
        self._persistence_task = asyncio.create_task(self._persistence_loop())
        logger.info(f"State persistence loop started (interval: {self._persistence_interval}s)")

    async def stop_persistence_loop(self) -> None:
        """停止状态持久化循环"""
        if self._persistence_task:
            self._persistence_task.cancel()
            try:
                await self._persistence_task
            except asyncio.CancelledError:
                pass
            self._persistence_task = None

            # 最后保存一次状态
            await self.save_state()
            logger.info("State persistence loop stopped")

    async def _persistence_loop(self) -> None:
        """持久化循环"""
        while True:
            try:
                await asyncio.sleep(self._persistence_interval)
                await self.save_state()

                # 定期清理过期历史
                if self._state_db:
                    await self._state_db.cleanup_old_history(max_age=86400.0)

            except asyncio.CancelledError:
                logger.info("Persistence loop cancelled")
                break
            except (OSError, IOError) as e:
                # 文件系统错误（磁盘满、权限问题等）
                logger.error(f"Persistence I/O error: {type(e).__name__}: {e}")
                await asyncio.sleep(10.0)  # 更长等待避免频繁失败
            except Exception as e:
                logger.error(f"Persistence loop unexpected error: {type(e).__name__}: {e}", exc_info=True)
                await asyncio.sleep(5.0)

    async def get_persistence_stats(self) -> dict[str, Any] | None:
        """获取持久化统计信息"""
        if self._state_db:
            return await self._state_db.get_stats()
        return None

    @staticmethod
    def _calc_duration_ms(start_time: float) -> float:
        """计算耗时（毫秒）"""
        return (time.time() - start_time) * 1000

    @staticmethod
    def _estimate_stream_tokens(chunk_count: int) -> int:
        """估算流式响应 token 数（每chunk约10 tokens）"""
        return chunk_count * 10

    def _resolve_api_key(self, api_key: str) -> str:
        """解析 API Key,支持环境变量引用"""
        if api_key.startswith("${") and api_key.endswith("}"):
            env_var = api_key[2:-1]
            return os.environ.get(env_var, "").strip()
        return api_key.strip()

    def get_client(self, model_id: str | None = None) -> AsyncOpenAI:
        """获取客户端，支持降级链

        Args:
            model_id: 可选的 model_id，如不指定则使用活跃 provider
        Returns:
            AsyncOpenAI 实例
        """
        if model_id:
            provider_id = model_id.split('/')[0]
            if provider_id in self.clients:
                return self.clients[provider_id]
            raise ValueError(f"Unknown provider: {provider_id}")

        # 使用降级链获取活跃 client
        if self._fallback_chain:
            _, client = self._fallback_chain.get_active_client()
            return client

        # 无降级链时使用第一个可用 client
        if self.clients:
            return next(iter(self.clients.values()))
        raise ValueError("No clients initialized")

    def get_active_provider(self) -> str:
        """获取当前活跃的 provider"""
        if self._fallback_chain:
            provider, _ = self._fallback_chain.get_active_client()
            return provider
        return next(iter(self.clients.keys())) if self.clients else ""

    def get_model_config(self, model_id: str) -> ModelConfig:
        """获取模型详细配置"""
        provider_id, model_name = model_id.split('/', 1)
        provider = self.config.models[provider_id]
        for model in provider.models:
            if model.id == model_name:
                return model
        raise ValueError(f"Unknown model: {model_id}")

    def get_rate_limit_config(self) -> RateLimitConfig | None:
        """获取当前限流配置"""
        return self._rate_config

    def _get_fallback_model_id(self, original_model_id: str, fallback_provider: str) -> str | None:
        """获取 fallback provider 的等效模型"""
        _, model_name = original_model_id.split('/', 1)

        # 尝试在 fallback provider 找同名模型
        if fallback_provider in self.config.models:
            for model in self.config.models[fallback_provider].models:
                if model.id == model_name:
                    return f"{fallback_provider}/{model_name}"

        # 返回 fallback provider 的第一个模型
        if fallback_provider in self.config.models:
            first_model = self.config.models[fallback_provider].models[0]
            return f"{fallback_provider}/{first_model.id}"

        return None

    def get_rate_limit_status(self) -> RateLimitStatus | None:
        """获取限流状态（供外部查询）"""
        if self._rate_limiter:
            return self._rate_limiter.get_status()
        return None

    def is_rate_limited(self) -> bool:
        """检查是否处于限流状态"""
        if self._rate_limiter:
            status = self._rate_limiter.get_status()
            # 窗口使用率超过 90% 视为限流状态
            return status.window_usage_ratio > 0.9
        return False

    def get_load_factor(self) -> float:
        """计算当前负载因子

        负载因子 = 队列填充率 * 0.4 + 限流窗口使用率 * 0.6
        """
        # 队列填充率
        queue_fill = 0.0
        if self._request_queue:
            queue_fill = self._request_queue.get_total_fill_ratio()

        # 限流窗口使用率
        window_usage = 0.0
        if self._rate_limiter:
            status = self._rate_limiter.get_status()
            window_usage = status.window_usage_ratio

        # 综合负载因子
        load_factor = queue_fill * 0.4 + window_usage * 0.6
        return load_factor

    def get_dynamic_timeout(self, priority: RequestPriority) -> float:
        """获取动态超时

        Args:
            priority: 请求优先级

        Returns:
            动态超时时间（秒）
        """
        load_factor = self.get_load_factor()
        return self._timeout_config.get_timeout(priority, load_factor)

    # ==================== 队列管理（TurnTicket 模式） ====================

    async def start_queue_dispatcher(self):
        """启动队列调度器"""
        if self._queue_started:
            logger.warning("Queue dispatcher already running")
            return

        if self._request_queue:
            await self._request_queue.start_dispatcher()
            self._queue_started = True

    async def stop_queue_dispatcher(self):
        """停止队列调度器"""
        if self._request_queue and self._queue_started:
            await self._request_queue.stop_dispatcher()
            self._queue_started = False

    def get_queue_status(self) -> dict[str, Any] | None:
        """获取队列状态"""
        if self._request_queue:
            return self._request_queue.get_stats()
        return None

    async def request_turn(self, priority: RequestPriority = RequestPriority.NORMAL) -> TurnTicket:
        """申请轮次（TurnTicket 模式核心入口）

        Args:
            priority: 请求优先级

        Returns:
            TurnTicket: 轮次票

        Raises:
            QueueFullError: 队列已满
        """
        if not self._request_queue:
            raise ValueError("Request queue not initialized")

        # 确保调度器已启动
        if not self._queue_started:
            await self.start_queue_dispatcher()

        return await self._request_queue.request_turn(priority)

    async def cancel_ticket(self, ticket_id: str, reason: str = "User cancelled") -> bool:
        """取消 ticket"""
        if self._request_queue:
            return await self._request_queue.cancel_ticket(ticket_id, reason)
        return False

    async def cancel_all_tickets(self, reason: str = "Emergency cleanup"):
        """取消所有 ticket"""
        if self._request_queue:
            await self._request_queue.cancel_all_tickets(reason)

    # ==================== 三阶段等待执行 ====================

    async def _wait_for_turn_and_acquire(self, priority: RequestPriority) -> TurnTicket:
        """阶段 1 & 2 & 3: 排队、等待、获取并发槽位和限流许可"""
        # 获取动态超时
        turn_timeout = self.get_dynamic_timeout(priority)

        # 阶段1：排队入场
        ticket = await self.request_turn(priority)
        logger.debug(f"Ticket {ticket.id}: submitted (priority={priority.name})")

        try:
            await ticket.wait_for_turn(timeout=turn_timeout)
        except TurnWaitTimeout:
            logger.warning(f"Ticket {ticket.id}: turn wait timeout ({turn_timeout:.1f}s)")
            raise
        except asyncio.CancelledError:
            logger.info(f"Ticket {ticket.id}: cancelled during turn wait")
            raise

        logger.debug(f"Ticket {ticket.id}: turn assigned (wait={ticket.get_wait_duration():.2f}s)")
        return ticket

    async def _execute_with_concurrency_and_rate_limit(
        self,
        ticket: TurnTicket,
        priority: RequestPriority,
        execution_func: Callable[[], Any],
        is_stream: bool = False
    ):
        """阶段 2-4: 获取信号量、限流并执行"""
        if not self._request_semaphore:
            raise ValueError("Request semaphore not initialized")

        async with self._request_semaphore:
            logger.debug(f"Ticket {ticket.id}: concurrent acquired{' (stream)' if is_stream else ''}")

            async with self._active_count_lock:
                self._active_count += 1

            try:
                # 阶段3：限流检查（CRITICAL 不等待）
                if self._rate_limiter:
                    max_wait = 0.0 if priority == RequestPriority.CRITICAL else 60.0
                    acquired = await self._rate_limiter.wait_and_acquire(max_wait=max_wait)
                    if not acquired:
                        raise RateLimitTimeoutError(
                            "Rate limit wait timeout, please retry later"
                        )

                logger.debug(f"Ticket {ticket.id}: rate limit acquired{' (stream)' if is_stream else ''}")

                # 阶段4：执行
                return await execution_func()

            finally:
                async with self._active_count_lock:
                    self._active_count -= 1

    async def _stream_with_concurrency_and_rate_limit(
        self,
        ticket: TurnTicket,
        priority: RequestPriority,
        stream_func: Callable[[], AsyncGenerator[dict, None]]
    ) -> AsyncGenerator[dict, None]:
        """阶段 2-4: 获取信号量、限流并执行（流式）

        注意：此方法现在是异步生成器，直接 yield 数据
        """
        # 确保 semaphore 已初始化（mypy 类型窄化）
        assert self._request_semaphore is not None

        async with self._request_semaphore:
            logger.debug(f"Ticket {ticket.id}: concurrent acquired (stream)")

            async with self._active_count_lock:
                self._active_count += 1

            try:
                if self._rate_limiter:
                    max_wait = 0.0 if priority == RequestPriority.CRITICAL else 60.0
                    acquired = await self._rate_limiter.wait_and_acquire(max_wait=max_wait)
                    if not acquired:
                        raise RateLimitTimeoutError(
                            "Rate limit wait timeout, please retry later"
                        )

                logger.debug(f"Ticket {ticket.id}: rate limit acquired (stream)")

                async for chunk in stream_func():
                    yield chunk

                logger.debug(f"Ticket {ticket.id}: stream completed")

            finally:
                async with self._active_count_lock:
                    self._active_count -= 1

    async def _execute_three_phase(
        self,
        model_id: str,
        messages: list[dict],
        priority: RequestPriority,
        **kwargs
    ) -> dict:
        """三阶段等待执行（非流式）"""
        ticket = await self._wait_for_turn_and_acquire(priority)

        async def _run():
            return await self._chat_completion_with_fallback_internal(model_id, messages, **kwargs)

        return await self._execute_with_concurrency_and_rate_limit(ticket, priority, _run)

    async def _stream_three_phase(
        self,
        model_id: str,
        messages: list[dict],
        priority: RequestPriority,
        **kwargs
    ) -> AsyncGenerator[dict, None]:
        """三阶段等待执行（流式）

        直接 yield 数据，是真正的异步生成器
        """
        ticket = await self._wait_for_turn_and_acquire(priority)

        async def _stream():
            async for chunk in self._stream_chat_completion_with_fallback_internal(model_id, messages, **kwargs):
                yield chunk

        # 委托给 _stream_with_concurrency_and_rate_limit，直接 yield 数据
        async for chunk in self._stream_with_concurrency_and_rate_limit(ticket, priority, _stream):
            yield chunk

    # ==================== 核心聊天接口（TurnTicket 模式） ====================

    async def chat_completion(
        self,
        model_id: str,
        messages: list[dict],
        priority: int = RequestPriority.NORMAL,
        **kwargs
    ) -> dict:
        """非流式聊天补全（TurnTicket 模式）

        Args:
            model_id: 模型 ID (格式: provider/model)
            messages: 消息列表
            priority: 请求优先级
                - CRITICAL: 用户直接交互，最高优先级，独立队列
                - HIGH: RalphLoop 迭代，优先处理
                - NORMAL: Subagent 任务，标准处理
                - LOW: Scheduler 后台任务，队列等待
            **kwargs: 其他参数（如 tools, temperature 等）

        Returns:
            请求结果字典

        Raises:
            QueueFullError: 队列已满
            TurnWaitTimeout: 轮次等待超时
        """
        # 转换 priority 类型
        if isinstance(priority, int):
            priority = RequestPriority(priority)

        return await self._execute_three_phase(model_id, messages, priority, **kwargs)

    async def stream_chat_completion(
        self,
        model_id: str,
        messages: list[dict],
        priority: int = RequestPriority.NORMAL,
        **kwargs
    ) -> AsyncGenerator[dict, None]:
        """流式聊天补全（TurnTicket 模式）

        Args:
            model_id: 模型 ID (格式: provider/model)
            messages: 消息列表
            priority: 请求优先级
            **kwargs: 其他参数

        Returns:
            AsyncGenerator[Dict]: 流式结果

        Raises:
            QueueFullError: 队列已满
            TurnWaitTimeout: 轮次等待超时
        """
        # 转换 priority 类型
        if isinstance(priority, int):
            priority = RequestPriority(priority)

        # _stream_three_phase 现在是真正的异步生成器，直接委托
        async for chunk in self._stream_three_phase(model_id, messages, priority, **kwargs):
            yield chunk

    # ==================== 执行层（带降级） ====================

    async def _chat_completion_with_fallback_internal(
        self,
        model_id: str,
        messages: list[dict],
        **kwargs
    ) -> dict:
        """内部方法：带跨 Provider 降级的非流式聊天补全"""
        provider_id = model_id.split('/')[0]
        active_provider = self.get_active_provider()
        start_time = time.time()

        span = self._create_llm_span(model_id, active_provider, streaming=False)

        try:
            # 尝试主 provider（带重试）
            success, result = await self._try_provider_with_retry(model_id, messages, **kwargs)

            if success:
                if self._fallback_chain:
                    self._fallback_chain.mark_healthy(provider_id)

                duration_ms = self._calc_duration_ms(start_time)
                usage = result.get('usage') if result else None
                self._record_success_metrics(span, active_provider, model_id, usage, duration_ms)
                return result  # type: ignore[return-value]  # result is dict here

            # 触发降级
            if self._fallback_chain:
                self._fallback_chain.mark_degraded(provider_id)
                fallback_success, fallback_result = await self._try_fallback_providers(
                    span, model_id, messages, start_time, **kwargs
                )
                if fallback_success and fallback_result:
                    return fallback_result

            raise RuntimeError("All providers failed")

        except Exception as e:
            self._handle_llm_error(span, active_provider, model_id, start_time, e)
            raise
        finally:
            if span:
                span.end()

    def _create_llm_span(self, model_id: str, provider: str, streaming: bool = False):
        """创建 OpenTelemetry LLM Span"""
        tracer = get_tracer()
        if tracer and _OBSERVABILITY_ENABLED:
            span = tracer.start_span(SPAN_LLM_REQUEST)
            set_llm_span_attributes(span, model=model_id, provider=provider, streaming=streaming)
            return span
        return None

    def _record_success_metrics(self, span, provider: str, model_id: str, usage: dict | None, duration_ms: float):
        """记录成功调用的 Metrics 和 Span 属性"""
        if usage is None:
            usage = {}
        if usage:
            input_tokens = usage.get('prompt_tokens', 0)
            output_tokens = usage.get('completion_tokens', 0)

            record_llm_success(
                provider=provider,
                model=model_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms
            )

            if span:
                span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
                span.set_status(StatusCode.OK)

        if span and provider != model_id.split('/')[0]:
            span.set_attribute("seed.provider", provider)

    def _handle_llm_error(self, span, provider: str, model_id: str, start_time: float, e: Exception):
        """记录失败调用的 Metrics 和 Span 错误"""
        duration_ms = self._calc_duration_ms(start_time)
        error_type = classify_error(e)

        record_llm_error(provider=provider, model=model_id, duration_ms=duration_ms, error_type=error_type)

        if span:
            record_llm_span_error(span, e)

    async def _try_provider_with_retry(self, model_id: str, messages: list[dict], **kwargs) -> tuple[bool, dict | None]:
        """尝试单个 provider 调用（带重试）
        
        Returns:
            (success, result) - success为True表示成功，result为响应数据
        """
        for attempt in range(3):
            try:
                result = await self._chat_completion_single(model_id, messages, **kwargs)
                return True, result
            except (APIConnectionError, RateLimitError, APIStatusError) as e:
                if attempt < 2:
                    wait_time = self._get_retry_wait_time(attempt, e)
                    logger.warning(f"Retry {attempt+1}/3 after {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.warning(f"Provider {model_id.split('/')[0]} exhausted retries")
                    break
        return False, None

    async def _try_fallback_providers(self, span, model_id: str, messages: list[dict], start_time: float, **kwargs) -> tuple[bool, dict | None]:
        """尝试所有 fallback providers
        
        Returns:
            (success, result) - success为True表示成功，result为响应数据
        """
        if not self._fallback_chain:
            return False, None

        active_provider = self.get_active_provider()

        for fallback_provider, fallback_model_id in self._iterate_fallback_models(model_id, model_id.split('/')[0]):
            if span:
                add_fallback_event(
                    span,
                    from_provider=active_provider,
                    to_provider=fallback_provider,
                    reason="provider_degraded",
                    attempt=self._fallback_chain._providers.index(fallback_provider)
                )

            try:
                logger.info(f"Trying fallback: {fallback_model_id}")
                result = await self._chat_completion_single(fallback_model_id, messages, **kwargs)
                self._fallback_chain.mark_healthy(fallback_provider)

                duration_ms = self._calc_duration_ms(start_time)
                usage = result.get('usage')
                self._record_success_metrics(span, fallback_provider, fallback_model_id, usage, duration_ms)

                return True, result
            except Exception as fallback_e:
                logger.warning(f"Fallback {fallback_provider} failed: {fallback_e}")
                self._fallback_chain.mark_degraded(fallback_provider)

        return False, None

    async def _chat_completion_single(
        self,
        model_id: str,
        messages: list[dict],
        **kwargs
    ) -> dict:
        """单 provider 调用"""
        client = self.get_client(model_id)
        model_config = self.get_model_config(model_id)

        # 清理空 tools 数组（部分 API 不允许空数组）
        tools = kwargs.get('tools')
        if not tools:
            kwargs.pop('tools', None)

        response = await client.chat.completions.create(
            model=model_config.id,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=model_config.maxTokens,
            **kwargs
        )
        return response.model_dump()

    def _should_continue_retry(self, attempt: int, max_retries: int = 3) -> bool:
        """判断是否应该继续重试"""
        return attempt < max_retries - 1

    def _get_retry_wait_time(self, attempt: int, error: Exception | None = None) -> float:
        """计算重试等待时间 (支持 Retry-After 头解析 + Jitter)"""

        # 1. Check for Retry-After header (common in 429 Rate Limit errors)
        if error and hasattr(error, 'response') and error.response is not None:
            retry_after = error.response.headers.get('retry-after')
            if retry_after:
                try:
                    wait_time = int(retry_after)
                    # Cap at 60s to prevent excessive blocking if server requests long wait
                    return min(float(wait_time), 60.0)
                except (ValueError, TypeError):
                    pass # Fall back to exponential backoff if header is invalid

        # 2. Default exponential backoff with Jitter: 1s, 2s, 4s (+/- 20%)
        # Jitter prevents "thundering herd" problem
        base_wait = 2 ** attempt
        jitter = random.uniform(-0.2, 0.2) * base_wait
        return base_wait + jitter

    def _iterate_fallback_models(self, model_id: str, exclude_provider: str) -> list[tuple[str, str]]:
        """生成fallback provider和model_id列表
        
        Returns:
            List of (fallback_provider, fallback_model_id) tuples
        """
        fallbacks: list[tuple[str, str]] = []
        if not self._fallback_chain:
            return fallbacks

        for fallback_provider in self._fallback_chain._providers:
            if fallback_provider == exclude_provider:
                continue
            if fallback_provider not in self.clients:
                continue

            fallback_model_id = self._get_fallback_model_id(model_id, fallback_provider)
            if fallback_model_id:
                fallbacks.append((fallback_provider, fallback_model_id))

        return fallbacks

    async def _stream_chat_completion_with_fallback_internal(
        self,
        model_id: str,
        messages: list[dict],
        **kwargs
    ) -> AsyncGenerator[dict, None]:
        """内部方法：带跨 Provider 降级的流式聊天补全"""
        provider_id = model_id.split('/')[0]
        active_provider = self.get_active_provider()
        last_error = None
        start_time = time.time()

        span = self._create_llm_span(model_id, active_provider, streaming=True)

        try:
            # 尝试主 provider（带重试）
            async for chunk in self._stream_with_retry(model_id, messages, span, active_provider, start_time, **kwargs):
                yield chunk
            return

        except (APIConnectionError, RateLimitError, APIStatusError) as e:
            last_error = e
            # 触发降级
            if self._fallback_chain:
                self._fallback_chain.mark_degraded(provider_id)
                async for chunk in self._stream_fallback_providers(
                    model_id, messages, span, active_provider, start_time, provider_id, **kwargs
                ):
                    yield chunk
                return

            if last_error:
                self._handle_llm_error(span, active_provider, model_id, start_time, last_error)
                raise last_error

        except Exception as e:
            self._handle_llm_error(span, active_provider, model_id, start_time, e)
            raise
        finally:
            if span:
                span.end()

    async def _stream_with_retry(self, model_id: str, messages: list[dict], span, active_provider: str, start_time: float, **kwargs) -> AsyncGenerator[dict, None]:
        """流式响应重试逻辑"""
        chunk_count = 0  # Initialize before retry loop to avoid UnboundLocalError
        for attempt in range(3):
            try:
                chunk_count = 0  # Reset for each attempt
                async for chunk in self._stream_chat_completion_single(model_id, messages, **kwargs):
                    yield chunk
                    chunk_count += 1

                if self._fallback_chain:
                    self._fallback_chain.mark_healthy(model_id.split('/')[0])

                # 流式 token 估算
                duration_ms = self._calc_duration_ms(start_time)
                estimated_tokens = self._estimate_stream_tokens(chunk_count)

                record_llm_success(
                    provider=active_provider,
                    model=model_id,
                    input_tokens=0,
                    output_tokens=estimated_tokens,
                    duration_ms=duration_ms
                )

                if span:
                    span.set_attribute("gen_ai.usage.output_tokens", estimated_tokens)
                    span.set_attribute("seed.streaming", True)
                    span.set_status(StatusCode.OK)

                return

            except (APIConnectionError, RateLimitError, APIStatusError) as e:
                # Safety check: Do not retry if partial stream was already yielded
                # to avoid duplicate data in the consumer
                if chunk_count > 0:
                    logger.warning(f"Stream failed after {chunk_count} chunks, cannot safely retry")
                    raise

                if self._should_continue_retry(attempt):
                    wait_time = self._get_retry_wait_time(attempt, e)
                    logger.warning(f"Retry {attempt+1}/3 after {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.warning(f"Provider {model_id.split('/')[0]} exhausted retries")
                    raise

    async def _stream_fallback_providers(self, model_id: str, messages: list[dict], span, active_provider: str, start_time: float, exclude_provider: str, **kwargs) -> AsyncGenerator[dict, None]:
        """流式 fallback providers 尝试"""
        # 确保 fallback_chain 已初始化（mypy 类型窄化）
        assert self._fallback_chain is not None

        for fallback_provider, fallback_model_id in self._iterate_fallback_models(model_id, exclude_provider):
            if span:
                add_fallback_event(
                    span,
                    from_provider=active_provider,
                    to_provider=fallback_provider,
                    reason="stream_failure",
                    attempt=self._fallback_chain._providers.index(fallback_provider)
                )

            try:
                logger.info(f"Trying fallback stream: {fallback_model_id}")
                chunk_count = 0
                async for chunk in self._stream_chat_completion_single(fallback_model_id, messages, **kwargs):
                    yield chunk
                    chunk_count += 1

                self._fallback_chain.mark_healthy(fallback_provider)

                # 流式成功 Metrics
                duration_ms = self._calc_duration_ms(start_time)
                estimated_tokens = self._estimate_stream_tokens(chunk_count)

                record_llm_success(
                    provider=fallback_provider,
                    model=fallback_model_id,
                    input_tokens=0,
                    output_tokens=estimated_tokens,
                    duration_ms=duration_ms
                )

                if span:
                    span.set_attribute("gen_ai.usage.output_tokens", estimated_tokens)
                    span.set_attribute("seed.provider", fallback_provider)
                    span.set_status(StatusCode.OK)

                return

            except Exception as fallback_e:
                logger.warning(f"Fallback {fallback_provider} failed: {fallback_e}")
                self._fallback_chain.mark_degraded(fallback_provider)

    async def _stream_chat_completion_single(
        self,
        model_id: str,
        messages: list[dict],
        **kwargs
    ) -> AsyncGenerator[dict, None]:
        """单 provider 流式调用"""
        client = self.get_client(model_id)
        model_config = self.get_model_config(model_id)

        # 清理空 tools 数组（部分 API 不允许空数组）
        tools = kwargs.get('tools')
        if not tools:
            kwargs.pop('tools', None)

        response = await client.chat.completions.create(
            model=model_config.id,
            messages=messages,  # type: ignore[arg-type]
            stream=True,
            max_tokens=model_config.maxTokens,
            **kwargs
        )

        # 兼容不同 SDK 版本：AsyncStream vs 协程包装
        if hasattr(response, '__aiter__'):
            stream = response
        elif asyncio.iscoroutine(response):
            stream = await response
        else:
            # 非流式响应，直接 yield 并返回
            try:
                yield response.model_dump()
            except Exception:
                yield {"error": str(response)}  # type: ignore[misc]
            return

        async for chunk in stream:
            try:
                chunk_dict = chunk.model_dump()
                if chunk_dict.get('choices'):
                    yield chunk_dict
            except Exception as e:
                logger.debug(f"Failed to serialize stream chunk: {type(e).__name__}")
                continue
