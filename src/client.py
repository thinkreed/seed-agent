import os
import time
import asyncio
import logging
from typing import List, Dict, AsyncGenerator, Any, Optional, Tuple
from openai import AsyncOpenAI, APIConnectionError, RateLimitError, APIStatusError
from models import load_config, FullConfig, ProviderConfig, ModelConfig, RateLimitConfig
from rate_limiter import RateLimiter, RateLimitStatus, TokenBucketState, RollingWindowState
from request_queue import RequestQueue, RequestPriority, QueueFullError
from rate_limit_db import RateLimitSQLite, RateLimitState
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger("seed_agent")


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
    """通用 LLM 网关，支持跨 Provider 降级和请求限流"""

    def __init__(self, config_path: str):
        self.config: FullConfig = load_config(config_path)
        self.clients: Dict[str, AsyncOpenAI] = {}
        self._fallback_chain: Optional[FallbackChain] = None

        # 限流组件
        self._rate_limiter: Optional[RateLimiter] = None
        self._rate_config: Optional[RateLimitConfig] = None
        self._request_semaphore: Optional[asyncio.Semaphore] = None

        # 请求队列
        self._request_queue: Optional[RequestQueue] = None
        self._queue_started = False

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

        # 3. Request Queue
        self._request_queue = RequestQueue(
            max_size=config.queueMaxSize,
            dispatch_rate=config.get_effective_rate(),
            backpressure_threshold=config.queueBackpressureThreshold,
        )

        logger.info(
            f"Rate limiting initialized: "
            f"rate={config.get_effective_rate():.3f} req/sec, "
            f"burst={config.burstCapacity}, "
            f"window={config.get_window_limit()}/{config.get_window_duration():.0f}s, "
            f"concurrent={config.maxConcurrent}, "
            f"queue_size={config.queueMaxSize}"
        )

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
            now = time.time()

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

    # ==================== 队列管理 ====================

    async def start_queue_dispatcher(self):
        """启动队列调度器"""
        if self._queue_started:
            logger.warning("Queue dispatcher already running")
            return

        if self._request_queue:
            await self._request_queue.start_dispatcher(self._execute_with_rate_limit)
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

    async def submit_to_queue(
        self,
        model_id: str,
        messages: List[Dict],
        priority: RequestPriority = RequestPriority.NORMAL,
        **kwargs
    ) -> str:
        """提交请求到队列

        Args:
            model_id: 模型 ID
            messages: 消息列表
            priority: 请求优先级
            **kwargs: 其他参数

        Returns:
            request_id: 请求 ID

        Raises:
            QueueFullError: 队列已满
        """
        if not self._request_queue:
            raise ValueError("Request queue not initialized")

        # 确保调度器已启动
        if not self._queue_started:
            await self.start_queue_dispatcher()

        return await self._request_queue.submit(model_id, messages, priority, **kwargs)

    async def wait_for_queue_result(self, request_id: str, timeout: float = 300.0) -> Dict:
        """等待队列请求完成

        Args:
            request_id: 请求 ID
            timeout: 最大等待时间（秒）

        Returns:
            请求结果
        """
        if not self._request_queue:
            raise ValueError("Request queue not initialized")

        return await self._request_queue.wait_for_result(request_id, timeout)

    async def cancel_queue_request(self, request_id: str) -> bool:
        """取消队列请求"""
        if self._request_queue:
            return await self._request_queue.cancel_request(request_id)
        return False

    async def clear_queue(self):
        """清空队列"""
        if self._request_queue:
            await self._request_queue.clear_queue()

    async def _execute_with_rate_limit(
        self,
        model_id: str,
        messages: List[Dict],
        priority: int = RequestPriority.NORMAL,
        **kwargs
    ) -> Dict:
        """带限流的请求执行

        Args:
            model_id: 模型 ID
            messages: 消息列表
            priority: 请求优先级
            **kwargs: 其他参数
        """
        # CRITICAL 优先级跳过限流等待，但仍需并发控制
        max_wait = 0.0 if priority == RequestPriority.CRITICAL else 60.0

        # 1. 并发控制
        async with self._request_semaphore:
            # 2. 限流控制
            if self._rate_limiter:
                acquired = await self._rate_limiter.wait_and_acquire(max_wait=max_wait)
                if not acquired:
                    # 限流超时，抛出异常让上层处理
                    raise RateLimitError(
                        "Rate limit wait timeout, please retry later",
                        response=None,
                        body=None
                    )

            # 3. 执行请求（带降级）
            return await self._chat_completion_with_fallback_internal(model_id, messages, **kwargs)

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

    async def chat_completion(
        self,
        model_id: str,
        messages: List[Dict],
        priority: int = RequestPriority.NORMAL,
        use_queue: bool = False,
        **kwargs
    ) -> Dict:
        """非流式聊天补全（使用限流和降级机制）

        Args:
            model_id: 模型 ID (格式: provider/model)
            messages: 消息列表
            priority: 请求优先级
                - CRITICAL: 用户直接交互，跳过限流等待
                - HIGH: RalphLoop 迭代，优先处理
                - NORMAL: Subagent 任务，标准处理
                - LOW: Scheduler 后台，队列处理
            use_queue: 是否强制使用队列（适用于批量任务）
            **kwargs: 其他参数（如 tools, temperature 等）

        Returns:
            请求结果字典
        """
        # LOW 优先级或强制使用队列 → 走队列
        if priority == RequestPriority.LOW or use_queue:
            request_id = await self.submit_to_queue(model_id, messages, priority, **kwargs)
            return await self.wait_for_queue_result(request_id)

        # 其他优先级 → 直接执行
        return await self._execute_with_rate_limit(model_id, messages, priority, **kwargs)

    # 兼容旧接口
    async def chat_completion_with_fallback(
        self,
        model_id: str,
        messages: List[Dict],
        **kwargs
    ) -> Dict:
        """带跨 Provider 降级的非流式聊天补全（兼容旧接口）"""
        return await self._execute_with_rate_limit(model_id, messages, RequestPriority.NORMAL, **kwargs)

    async def _stream_execute_with_rate_limit(
        self,
        model_id: str,
        messages: List[Dict],
        priority: int = RequestPriority.NORMAL,
        **kwargs
    ) -> AsyncGenerator[Dict, None]:
        """带限流的流式请求执行"""
        max_wait = 0.0 if priority == RequestPriority.CRITICAL else 60.0

        async with self._request_semaphore:
            if self._rate_limiter:
                acquired = await self._rate_limiter.wait_and_acquire(max_wait=max_wait)
                if not acquired:
                    raise RateLimitError(
                        "Rate limit wait timeout, please retry later",
                        response=None,
                        body=None
                    )

            async for chunk in self._stream_chat_completion_with_fallback_internal(model_id, messages, **kwargs):
                yield chunk

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

    async def stream_chat_completion(
        self,
        model_id: str,
        messages: List[Dict],
        priority: int = RequestPriority.NORMAL,
        **kwargs
    ) -> AsyncGenerator[Dict, None]:
        """流式聊天补全（使用限流和降级机制）"""
        async for chunk in self._stream_execute_with_rate_limit(model_id, messages, priority, **kwargs):
            yield chunk

    # 兼容旧接口
    async def stream_chat_completion_with_fallback(
        self,
        model_id: str,
        messages: List[Dict],
        **kwargs
    ) -> AsyncGenerator[Dict, None]:
        """带跨 Provider 降级的流式聊天补全（兼容旧接口）"""
        async for chunk in self._stream_execute_with_rate_limit(model_id, messages, RequestPriority.NORMAL, **kwargs):
            yield chunk