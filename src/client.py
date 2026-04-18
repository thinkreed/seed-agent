import os
import asyncio
import logging
from typing import List, Dict, AsyncGenerator, Any, Optional
from openai import AsyncOpenAI, APIConnectionError, RateLimitError, APIStatusError
from models import load_config, FullConfig, ProviderConfig, ModelConfig
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
    """通用 LLM 网关，支持跨 Provider 降级"""

    def __init__(self, config_path: str):
        self.config: FullConfig = load_config(config_path)
        self.clients: Dict[str, AsyncOpenAI] = {}
        self._fallback_chain: Optional[FallbackChain] = None
        self._init_clients()
        self._init_fallback_chain()

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

    async def chat_completion_with_fallback(
        self,
        model_id: str,
        messages: List[Dict],
        **kwargs
    ) -> Dict:
        """带跨 Provider 降级的非流式聊天补全"""
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

        if not kwargs.get('tools'):
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
        **kwargs
    ) -> Dict:
        """非流式聊天补全（使用降级机制）"""
        return await self.chat_completion_with_fallback(model_id, messages, **kwargs)

    async def stream_chat_completion_with_fallback(
        self,
        model_id: str,
        messages: List[Dict],
        **kwargs
    ) -> AsyncGenerator[Dict, None]:
        """带跨 Provider 降级的流式聊天补全"""
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

        if not kwargs.get('tools'):
            kwargs.pop('tools', None)

        stream = await client.chat.completions.create(
            model=model_config.id,
            messages=messages,
            stream=True,
            max_tokens=model_config.maxTokens,
            **kwargs
        )

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
        **kwargs
    ) -> AsyncGenerator[Dict, None]:
        """流式聊天补全（使用降级机制）"""
        async for chunk in self.stream_chat_completion_with_fallback(model_id, messages, **kwargs):
            yield chunk