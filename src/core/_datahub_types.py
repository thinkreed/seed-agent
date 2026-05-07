"""
DataHub 类型定义

Topic 格式: category:subcategory:identifier
示例: memory:search:query, tool:execute:file_read

TopicPolicy 管理数据生命周期和策略。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class TopicCategory(Enum):
    """Topic 分类"""

    MEMORY = "memory"
    TOOL = "tool"
    SESSION = "session"
    LLM = "llm"
    AUTONOMOUS = "autonomous"
    LIFECYCLE = "lifecycle"
    CACHE = "cache"


@dataclass
class TopicPolicy:
    """Topic 策略配置"""

    ttl_seconds: int = 30  # 数据过期时间
    refresh_seconds: int = 0  # 自动刷新间隔（0 = 不刷新）
    rate_limit_per_minute: int = 60  # 每分钟最大请求
    max_batch_size: int = 100  # 最大批量大小
    cache_enabled: bool = True  # 是否缓存
    dedup_enabled: bool = True  # 是否去重


@dataclass
class TopicEntry:
    """Topic 缓存条目"""

    topic: str
    data: Any
    timestamp: float
    policy: TopicPolicy = field(default_factory=TopicPolicy)
    subscriber_count: int = 0


@dataclass
class PublishEvent:
    """发布事件"""

    topic: str
    data: Any
    timestamp: float
    source: str | None = None  # 来源标识


# Handler 类型
TopicHandler = Callable[[str, Any], None]  # (topic, data) -> None
PatternHandler = Callable[[str, str, Any], None]  # (pattern, topic, data) -> None


__all__ = [
    "TopicCategory",
    "TopicPolicy",
    "TopicEntry",
    "PublishEvent",
    "TopicHandler",
    "PatternHandler",
]