"""
上下文工程配置模块

包含压缩和裁剪的配置类及常量。
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum

# 预编译正则表达式（性能优化）
_RE_FILE_PATTERN = re.compile(r"[a-zA-Z_./]+\.[a-zA-Z]+")
_RE_CODE_PATTERN = re.compile(r"[A-Z][a-zA-Z0-9]*|[a-z_][a-z0-9_]*")
_RE_STOP_WORDS = {"the", "for", "and", "with", "this", "that"}

# 相关性阈值
RELEVANCE_THRESHOLD = 0.3


class CompressionTier(StrEnum):
    """压缩层级枚举"""

    TIER_1_FULL = "tier_1_full"  # 最新完整保留
    TIER_2_LIGHT = "tier_2_light"  # 稍旧轻量总结
    TIER_3_ABSTRACT = "tier_3_abstract"  # 更早简短摘要


@dataclass
class TierConfig:
    """层级配置"""

    name: str
    threshold: float  # 容量阈值触发点
    keep_rounds: int  # 保留轮数 (一轮 ≈ 2 条消息)
    method: CompressionTier
    description: str


@dataclass
class CompressionConfig:
    """压缩配置"""

    tiers: dict[CompressionTier, TierConfig] = field(
        default_factory=lambda: {
            CompressionTier.TIER_1_FULL: TierConfig(
                name="recent_full",
                threshold=0.0,
                keep_rounds=5,
                method=CompressionTier.TIER_1_FULL,
                description="最新 5 轮对话完整保留",
            ),
            CompressionTier.TIER_2_LIGHT: TierConfig(
                name="medium_light",
                threshold=0.5,
                keep_rounds=10,
                method=CompressionTier.TIER_2_LIGHT,
                description="稍旧 10 轮轻量总结",
            ),
            CompressionTier.TIER_3_ABSTRACT: TierConfig(
                name="old_abstract",
                threshold=0.75,
                keep_rounds=0,  # 全部压缩
                method=CompressionTier.TIER_3_ABSTRACT,
                description="更早历史简短摘要",
            ),
        }
    )

    # Token 估算系数
    token_per_char: float = 0.5

    # 最大上下文限制
    max_context_messages: int = 50


@dataclass
class PruningConfig:
    """裁剪配置"""

    relevance_threshold: float = RELEVANCE_THRESHOLD

    # 实体类型权重
    entity_weights: dict[str, float] = field(
        default_factory=lambda: {
            "file_path": 1.0,
            "function_name": 0.8,
            "class_name": 0.8,
            "keyword": 0.5,
        }
    )

    # 角色权重
    role_weights: dict[str, float] = field(
        default_factory=lambda: {
            "user": 1.0,
            "assistant": 1.0,
            "tool": 0.7,
            "system": 0.5,
        }
    )

    # 最小保留消息数
    min_preserve_count: int = 5


# 导出正则表达式供其他模块使用
def get_file_pattern() -> re.Pattern:
    """获取文件路径匹配正则"""
    return _RE_FILE_PATTERN


def get_code_pattern() -> re.Pattern:
    """获取代码名称匹配正则"""
    return _RE_CODE_PATTERN


def get_stop_words() -> set[str]:
    """获取停用词集合"""
    return _RE_STOP_WORDS