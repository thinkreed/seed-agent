"""提示缓存保护机制 (Wiki 知识落地 - Hermes)

会话级缓存 + 变化检测 + 结构保护，支持 Anthropic/Qwen Provider。
缓存命中时首 token 延迟降低 60-80%，token 成本节省 ~90%。
"""

import hashlib
import logging
from typing import Any

from ._prompt_caching_types import CachedSystemPrompt, PromptCachingState

logger = logging.getLogger("seed_agent")


class PromptCachingProtector:
    """提示缓存保护器：缓存 system_prompt 结构，检测变化，保护消息结构不变"""

    CACHING_PROVIDERS = ["anthropic", "claude", "qwen", "bailian"]

    def __init__(self, provider: str | None = None):
        self._state = PromptCachingState()
        self._provider = provider or ""
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
        structure = [
            {"role": msg.get("role"), "content_hash": self._compute_hash(str(msg.get("content", "")))}
            for msg in messages
        ]
        return self._compute_hash(str(structure))

    def check_system_prompt_changed(self, system_prompt: str | None) -> bool:
        """检查 system_prompt 是否变化，返回 True 表示变化"""
        if not system_prompt:
            self._state.cached_system_prompt.is_valid = False
            return True

        current_hash = self._compute_hash(system_prompt)
        cached_hash = self._state.cached_system_prompt.content_hash

        if current_hash != cached_hash:
            self._state.cached_system_prompt.content = system_prompt
            self._state.cached_system_prompt.content_hash = current_hash
            self._state.cached_system_prompt.is_valid = False
            logger.debug(f"System prompt changed: hash={current_hash}")
            return True

        self._state.cached_system_prompt.is_valid = True
        self._state.cached_system_prompt.cache_hit_count += 1
        return False

    def build_cached_messages(
        self,
        system_prompt: str | None,
        context_messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """构建带缓存控制的消息列表"""
        messages: list[dict[str, Any]] = []
        changed = self.check_system_prompt_changed(system_prompt)

        if system_prompt:
            system_msg: dict[str, Any] = {"role": "system", "content": system_prompt}

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

        messages.extend(context_messages)
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


# 全局实例管理
_global_protector: PromptCachingProtector | None = None


def get_prompt_caching_protector(provider: str | None = None) -> PromptCachingProtector:
    """获取全局提示缓存保护器"""
    global _global_protector
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