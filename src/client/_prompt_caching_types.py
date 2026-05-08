"""提示缓存保护机制 - 数据类型定义

基于 Hermes-Agent 提示缓存保护设计的数据结构。
"""

from dataclasses import dataclass, field


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
    - cached_system_prompt: 会话级缓存
    - cache_enabled: 缓存是否启用
    - provider_supports_caching: Provider 是否支持缓存
    """

    cached_system_prompt: CachedSystemPrompt = field(default_factory=CachedSystemPrompt)
    cache_enabled: bool = True
    provider_supports_caching: bool = False  # Anthropic/Qwen 支持，OpenAI 不支持


__all__ = [
    "CachedSystemPrompt",
    "PromptCachingState",
]