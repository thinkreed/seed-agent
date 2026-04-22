import os
import time
import asyncio
import logging
from typing import List, Dict, AsyncGenerator, Any, Optional, Tuple
from openai import AsyncOpenAI, APIConnectionError, RateLimitError, APIStatusError
from models import load_config, FullConfig, ProviderConfig, ModelConfig, RateLimitConfig
from rate_limiter import RateLimiter, RateLimitStatus, TokenBucketState, RollingWindowState
from request_queue import (
    RequestQueue, RequestPriority, QueueFullError, TurnWaitTimeout,
    TurnTicket, QueueConfig
)
from rate_limit_db import RateLimitSQLite, RateLimitState
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from dataclasses import dataclass, field

logger = logging.getLogger("seed_agent")


@dataclass
class TimeoutConfig:
    """等待超时配置（可动态调整）"""

    # 基础超时（秒）
    base_timeouts: Dict[RequestPriority, float] = field(
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

    def __init__(self, providers: List[str], clients: Dict[str, AsyncOpenAI]):
        self._providers = providers  # 优先级列表：[primary, fallback1, fallback2, ...]
        self._clients = clients
        self._active_provider: Optional[str] = None  # 当前活跃的 provider
        self._status: str = "healthy"  # healthy, degraded, unavailable

    def get_active_client(self) -> tuple[str, AsyncOpenAI]:
        """获取当前活跃的 provider 和 client"""
        if self._active_provider and self._active_provider in self._clients:
            return self._active_provider, self._clients[self._active_provider]

        # 尝试第一个可用 provider
        for provider in self._providers:
            if provider in self._clients:
                self._active_provider = provider
                return provider, self._clients[provider]

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
        self._status = "unavailable"
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
        self.clients: Dict[str, AsyncOpenAI] = {}
        self._fallback_chain: Optional[FallbackChain] = None

        # 限流组件
        self._rate_limiter: Optional[RateLimiter] = None
        self._rate_config: Optional[RateLimitConfig] = None
        self._request_semaphore: Optional[asyncio.Semaphore] = None

        # 请求队列（TurnTicket 模式）
        self._request_queue: Optional[RequestQueue] = None
        self._queue_config: Optional[QueueConfig] = None
        self._timeout_config: TimeoutConfig = TimeoutConfig()
        self._queue_started = False

        # 活跃请求数（用于负载因子计算）
        self._active_count: int = 0
        self._active_count_lock = asyncio.Lock()

        # 状态持久化
        self._state_db: Optional[RateLimitSQLite] = None
        self._persistence_task: Optional[asyncio.Task] = None
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
                await self._state_db.cleanup_old_history(max_age=86400.0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Persistence loop error: {e}")
                await asyncio.sleep(5.0)

    async def get_persistence_stats(self) -> Optional[Dict[str, Any]]:
        """获取持久化统计信息"""
        if self._state_db:
            return await self._state_db.get_stats()
        return None

    def _resolve_api_key(self, api_key: str) -> str:
        """解析 API Key,支持环境变量引用"""
        if api_key.startswith("${") and api_key.endswith("}"):
            env_var = api_key[2:-1]
            return os.environ.get(env_var, "").strip()
        return api_key.strip()

    def get_client(self, model_id: str = None) -> AsyncOpenAI:
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

    def get_rate_limit_config(self) -> Optional[RateLimitConfig]:
        """获取当前限流配置"""
        return self._rate_config

    def _get_fallback_model_id(self, original_model_id: str, fallback_provider: str) -> Optional[str]:
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

    def get_rate_limit_status(self) -> Optional[RateLimitStatus]:
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

    def get_queue_status(self) -> Optional[Dict[str, Any]]:
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

    async def _execute_three_phase(
        self,
        model_id: str,
        messages: List[Dict],
        priority: RequestPriority,
        **kwargs
    ) -> Dict:
        """三阶段等待执行（非流式）

        阶段1：排队入场（request_turn + wait_for_turn）
        阶段2：抢执行位置（semaphore）
        阶段3：限流检查（rate_limiter）
        阶段4：执行（execute with fallback）
        """
        # 获取动态超时
        turn_timeout = self.get_dynamic_timeout(priority)

        # 阶段1：排队入场
        ticket = await self.request_turn(priority)
        logger.debug(f"Ticket {ticket.id}: submitted (priority={priority.name})")

        try:
            await ticket.wait_for_turn(timeout=turn_timeout)
        except TurnWaitTimeout as e:
            logger.warning(f"Ticket {ticket.id}: turn wait timeout ({turn_timeout:.1f}s)")
            raise
        except asyncio.CancelledError:
            logger.info(f"Ticket {ticket.id}: cancelled during turn wait")
            raise

        logger.debug(f"Ticket {ticket.id}: turn assigned (wait={ticket.get_wait_duration():.2f}s)")

        # 阶段2-4：执行（带 semaphore 和限流）
        async with self._request_semaphore:
            logger.debug(f"Ticket {ticket.id}: concurrent acquired")

            # 活跃计数
            async with self._active_count_lock:
                self._active_count += 1

            try:
                # 阶段3：限流检查（CRITICAL 不等待）
                if self._rate_limiter:
                    max_wait = 0.0 if priority == RequestPriority.CRITICAL else 60.0
                    acquired = await self._rate_limiter.wait_and_acquire(max_wait=max_wait)
                    if not acquired:
                        raise RateLimitError(
                            "Rate limit wait timeout, please retry later",
                            response=None,
                            body=None
                        )

                logger.debug(f"Ticket {ticket.id}: rate limit acquired")

                # 阶段4：执行
                result = await self._chat_completion_with_fallback_internal(model_id, messages, **kwargs)
                logger.debug(f"Ticket {ticket.id}: execution completed")
                return result

            finally:
                async with self._active_count_lock:
                    self._active_count -= 1

    async def _stream_three_phase(
        self,
        model_id: str,
        messages: List[Dict],
        priority: RequestPriority,
        **kwargs
    ) -> AsyncGenerator[Dict, None]:
        """三阶段等待执行（流式）

        返回 generator，由调用者迭代
        """
        # 获取动态超时
        turn_timeout = self.get_dynamic_timeout(priority)

        # 阶段1：排队入场
        ticket = await self.request_turn(priority)
        logger.debug(f"Ticket {ticket.id}: submitted (priority={priority.name}, stream=True)")

        try:
            await ticket.wait_for_turn(timeout=turn_timeout)
        except TurnWaitTimeout as e:
            logger.warning(f"Ticket {ticket.id}: turn wait timeout ({turn_timeout:.1f}s)")
            raise
        except asyncio.CancelledError:
            logger.info(f"Ticket {ticket.id}: cancelled during turn wait")
            raise

        logger.debug(f"Ticket {ticket.id}: turn assigned (wait={ticket.get_wait_duration():.2f}s)")

        # 阶段2-4：返回 generator（调度器不介入）
        async def actual_stream():
            async with self._request_semaphore:
                logger.debug(f"Ticket {ticket.id}: concurrent acquired (stream)")

                async with self._active_count_lock:
                    self._active_count += 1

                try:
                    if self._rate_limiter:
                        max_wait = 0.0 if priority == RequestPriority.CRITICAL else 60.0
                        acquired = await self._rate_limiter.wait_and_acquire(max_wait=max_wait)
                        if not acquired:
                            raise RateLimitError(
                                "Rate limit wait timeout, please retry later",
                                response=None,
                                body=None
                            )

                    logger.debug(f"Ticket {ticket.id}: rate limit acquired (stream)")

                    async for chunk in self._stream_chat_completion_with_fallback_internal(model_id, messages, **kwargs):
                        yield chunk

                    logger.debug(f"Ticket {ticket.id}: stream completed")

                finally:
                    async with self._active_count_lock:
                        self._active_count -= 1

        return actual_stream()

    # ==================== 核心聊天接口（TurnTicket 模式） ====================

    async def chat_completion(
        self,
        model_id: str,
        messages: List[Dict],
        priority: int = RequestPriority.NORMAL,
        **kwargs
    ) -> Dict:
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
        messages: List[Dict],
        priority: int = RequestPriority.NORMAL,
        **kwargs
    ) -> AsyncGenerator[Dict, None]:
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

        async for chunk in self._stream_three_phase(model_id, messages, priority, **kwargs):
            yield chunk

    # ==================== 执行层（带降级） ====================

    async def _chat_completion_with_fallback_internal(
        self,
        model_id: str,
        messages: List[Dict],
        **kwargs
    ) -> Dict:
        """内部方法：带跨 Provider 降级的非流式聊天补全"""
        provider_id = model_id.split('/')[0]

        # 尝试当前 provider（带重试）
        for attempt in range(3):
            try:
                result = await self._chat_completion_single(model_id, messages, **kwargs)
                if self._fallback_chain:
                    self._fallback_chain.mark_healthy(provider_id)
                return result
            except (APIConnectionError, RateLimitError, APIStatusError) as e:
                if attempt < 2:
                    wait_time = 2 ** attempt
                    logger.warning(f"Retry {attempt+1}/3 after {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.warning(f"Provider {provider_id} exhausted retries")
                    break

        # 触发降级
        if self._fallback_chain:
            self._fallback_chain.mark_degraded(provider_id)

            for fallback_provider in self._fallback_chain._providers:
                if fallback_provider == provider_id:
                    continue
                if fallback_provider not in self.clients:
                    continue

                fallback_model_id = self._get_fallback_model_id(model_id, fallback_provider)
                if not fallback_model_id:
                    continue

                try:
                    logger.info(f"Trying fallback: {fallback_model_id}")
                    result = await self._chat_completion_single(fallback_model_id, messages, **kwargs)
                    self._fallback_chain.mark_healthy(fallback_provider)
                    return result
                except Exception as fallback_e:
                    logger.warning(f"Fallback {fallback_provider} failed: {fallback_e}")
                    self._fallback_chain.mark_degraded(fallback_provider)

        raise APIConnectionError("All providers failed")

    async def _chat_completion_single(
        self,
        model_id: str,
        messages: List[Dict],
        **kwargs
    ) -> Dict:
        """单 provider 调用"""
        client = self.get_client(model_id)
        model_config = self.get_model_config(model_id)

        # 清理空 tools 数组（部分 API 不允许空数组）
        tools = kwargs.get('tools')
        if not tools:
            kwargs.pop('tools', None)

        response = await client.chat.completions.create(
            model=model_config.id,
            messages=messages,
            max_tokens=model_config.maxTokens,
            **kwargs
        )
        return response.model_dump()

    async def _stream_chat_completion_with_fallback_internal(
        self,
        model_id: str,
        messages: List[Dict],
        **kwargs
    ) -> AsyncGenerator[Dict, None]:
        """内部方法：带跨 Provider 降级的流式聊天补全"""
        provider_id = model_id.split('/')[0]
        last_error = None

        # 尝试当前 provider（带重试）
        for attempt in range(3):
            try:
                async for chunk in self._stream_chat_completion_single(model_id, messages, **kwargs):
                    yield chunk
                if self._fallback_chain:
                    self._fallback_chain.mark_healthy(provider_id)
                return
            except (APIConnectionError, RateLimitError, APIStatusError) as e:
                last_error = e
                if attempt < 2:
                    wait_time = 2 ** attempt
                    logger.warning(f"Retry {attempt+1}/3 after {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.warning(f"Provider {provider_id} exhausted retries")
                    break

        # 触发降级
        if self._fallback_chain:
            self._fallback_chain.mark_degraded(provider_id)

            for fallback_provider in self._fallback_chain._providers:
                if fallback_provider == provider_id:
                    continue
                if fallback_provider not in self.clients:
                    continue

                fallback_model_id = self._get_fallback_model_id(model_id, fallback_provider)
                if not fallback_model_id:
                    continue

                try:
                    logger.info(f"Trying fallback stream: {fallback_model_id}")
                    async for chunk in self._stream_chat_completion_single(fallback_model_id, messages, **kwargs):
                        yield chunk
                    self._fallback_chain.mark_healthy(fallback_provider)
                    return
                except Exception as fallback_e:
                    logger.warning(f"Fallback {fallback_provider} failed: {fallback_e}")
                    self._fallback_chain.mark_degraded(fallback_provider)

        if last_error:
            raise last_error

    async def _stream_chat_completion_single(
        self,
        model_id: str,
        messages: List[Dict],
        **kwargs
    ) -> AsyncGenerator[Dict, None]:
        """单 provider 流式调用"""
        client = self.get_client(model_id)
        model_config = self.get_model_config(model_id)

        # 清理空 tools 数组（部分 API 不允许空数组）
        tools = kwargs.get('tools')
        if not tools:
            kwargs.pop('tools', None)

        response = await client.chat.completions.create(
            model=model_config.id,
            messages=messages,
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
                yield str(response)
            return

        async for chunk in stream:
            try:
                chunk_dict = chunk.model_dump()
                if chunk_dict.get('choices'):
                    yield chunk_dict
            except Exception:
                continue