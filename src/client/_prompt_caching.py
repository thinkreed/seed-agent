"""提示缓存保护机制 (Wiki 知识落地 - Hermes)

基于 Hermes-Agent 提示缓存保护设计：
- 会话级缓存：_cached_system_prompt 记录结构和 hash
- 变化检测：system_prompt 变化时标记缓存失效
- 结构保护：避免修改已缓存的消息结构

Anthropic 提示缓存要求：
- 系统消息必须放在首位
- 相同内容的消息结构不变
- 缓存标记：{"cache_control": {"type": "ephemeral"}}

性能影响：
- 重复 system_prompt 可节省 ~90% token 成本
- 缓存命中时首 token 延迟降低 60-80%
"""

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("seed_agent")


@dataclass
class CachedSystemPrompt:
    """缓存的 System Prompt 结构

    Attributes:
        content: System prompt 内容
        content_hash: 内容 hash (SHA256)
        messages_hash: 消息列表结构 hash
        cache_hit_count: 缓存命中次数
        last_used_at: 最后使用时间戳
        is_valid: 缓存是否有效
    """

    content: str = ""
    content_hash: str = ""
    messages_hash: str = ""
    cache_hit_count: int = 0
    last_used_at: float = 0.0
    is_valid: bool = True


@dataclass
class PromptCachingState:
    """会话级提示缓存状态

    Wiki 知识落地 (Hermes):
    - _cached_system_prompt: 会话级缓存
    - _cache_valid: 缓存有效性标记
    """

    cached_system_prompt: CachedSystemPrompt = field(default_factory=CachedSystemPrompt)
    cache_enabled: bool = True
    provider_supports_caching: bool = False  # Anthropic/Qwen 支持，OpenAI 不支持


class PromptCachingProtector:
    """提示缓存保护器

    核心职责：
    1. 缓存 system_prompt 结构
    2. 检测内容变化
    3. 保护消息结构不变
    4. 生成缓存控制标记

    Example:
        protector = PromptCachingProtector()

        # 首次构建消息
        messages = protector.build_messages_with_cache(
            system_prompt="You are helpful...",
            events=[...]
        )

        # 后续调用（内容不变，缓存命中）
        messages = protector.build_messages_with_cache(
            system_prompt="You are helpful...",  # 相同内容
            events=[...]
        )
        # messages 结构相同，Anthropic 会使用缓存
    """

    # 支持 Prompt Caching 的 Provider
    CACHING_PROVIDERS = ["anthropic", "claude", "qwen", "bailian"]

    def __init__(self, provider: str | None = None):
        """初始化缓存保护器

        Args:
            provider: LLM Provider 名称（决定是否启用缓存）
        """
        self._state = PromptCachingState()
        self._provider = provider or ""

        # 检测 Provider 是否支持缓存
        self._state.provider_supports_caching = self._check_provider_support()

        logger.info(
            f"PromptCachingProtector initialized: "
            f"provider={provider}, caching_enabled={self._state.provider_supports_caching}"
        )

    def _check_provider_support(self) -> bool:
        """检查 Provider 是否支持提示缓存"""
        provider_lower = self._provider.lower()
        return any(p in provider_lower for p in self.CACHING_PROVIDERS)

    def _compute_hash(self, content: str) -> str:
        """计算内容 hash"""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def _compute_messages_hash(self, messages: list[dict[str, Any]]) -> str:
        """计算消息结构 hash"""
        # 只计算结构关键部分
        structure = []
        for msg in messages:
            structure.append({
                "role": msg.get("role"),
                # 不计算完整内容，只计算 hash
                "content_hash": self._compute_hash(str(msg.get("content", ""))),
            })
        return self._compute_hash(str(structure))

    def check_system_prompt_changed(self, system_prompt: str | None) -> bool:
        """检查 system_prompt 是否变化

        Args:
            system_prompt: 当前 system prompt

        Returns:
            True 如果内容变化，False 如果相同
        """
        if not system_prompt:
            # 空 prompt，标记缓存失效
            self._state.cached_system_prompt.is_valid = False
            return True

        current_hash = self._compute_hash(system_prompt)
        cached_hash = self._state.cached_system_prompt.content_hash

        if current_hash != cached_hash:
            # 内容变化，更新缓存
            self._state.cached_system_prompt.content = system_prompt
            self._state.cached_system_prompt.content_hash = current_hash
            self._state.cached_system_prompt.is_valid = False
            logger.debug(f"System prompt changed: hash={current_hash}")
            return True

        # 内容相同，缓存有效
        self._state.cached_system_prompt.is_valid = True
        self._state.cached_system_prompt.cache_hit_count += 1
        return False

    def build_cached_messages(
        self,
        system_prompt: str | None,
        context_messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """构建带缓存控制的消息列表

        Args:
            system_prompt: System prompt
            context_messages: 上下文消息（不含 system）

        Returns:
            带 cache_control 标记的消息列表（如果 Provider 支持）
        """
        messages: list[dict[str, Any]] = []

        # 检查 system_prompt 是否变化
        changed = self.check_system_prompt_changed(system_prompt)

        # 构建 system 消息
        if system_prompt:
            system_msg: dict[str, Any] = {
                "role": "system",
                "content": system_prompt,
            }

            # 如果 Provider 支持缓存且内容未变化，添加缓存控制
            if (
                self._state.provider_supports_caching
                and not changed
                and self._state.cached_system_prompt.cache_hit_count > 0
            ):
                system_msg["cache_control"] = {"type": "ephemeral"}
                logger.debug(
                    f"Prompt cache hit: count={self._state.cached_system_prompt.cache_hit_count}"
                )

            messages.append(system_msg)

        # 添加上下文消息
        messages.extend(context_messages)

        # 记录消息结构 hash
        self._state.cached_system_prompt.messages_hash = self._compute_messages_hash(messages)

        return messages

    def invalidate_cache(self) -> None:
        """手动失效缓存"""
        self._state.cached_system_prompt.is_valid = False
        self._state.cached_system_prompt.cache_hit_count = 0
        logger.debug("Prompt cache invalidated")

    def get_cache_stats(self) -> dict[str, Any]:
        """获取缓存统计"""
        return {
            "provider": self._provider,
            "caching_enabled": self._state.provider_supports_caching,
            "cache_valid": self._state.cached_system_prompt.is_valid,
            "cache_hit_count": self._state.cached_system_prompt.cache_hit_count,
            "content_hash": self._state.cached_system_prompt.content_hash,
        }

    def set_provider(self, provider: str) -> None:
        """设置 Provider"""
        self._provider = provider
        self._state.provider_supports_caching = self._check_provider_support()
        if not self._state.provider_supports_caching:
            self.invalidate_cache()
        logger.info(f"Provider set: {provider}, caching={self._state.provider_supports_caching}")


# 全局实例（可选使用）
_global_protector: PromptCachingProtector | None = None


def get_prompt_caching_protector(provider: str | None = None) -> PromptCachingProtector:
    """获取全局提示缓存保护器"""
    if _global_protector is None:
        _global_protector = PromptCachingProtector(provider)
    elif provider and provider != _global_protector._provider:
        _global_protector.set_provider(provider)
    return _global_protector


def reset_prompt_caching_protector() -> None:
    """重置全局保护器"""
    global _global_protector
    _global_protector = None


__all__ = [
    "CachedSystemPrompt",
    "PromptCachingProtector",
    "PromptCachingState",
    "get_prompt_caching_protector",
    "reset_prompt_caching_protector",
]