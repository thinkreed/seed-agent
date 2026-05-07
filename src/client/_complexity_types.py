"""
复杂度评分类型定义

包含枚举、dataclass 和配置常量。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ComplexityTier(Enum):
    """复杂度层级"""
    SIMPLE = "simple"      # 简单任务：直接回答、单文件编辑
    STANDARD = "standard"  # 标准任务：多文件编辑、简单分析
    COMPLEX = "complex"    # 复杂任务：重构、架构设计、多模块
    REASONING = "reasoning"  # 推理任务：复杂分析、决策、规划


@dataclass
class ComplexityDimension:
    """复杂度维度"""
    name: str
    weight: float
    value: float = 0.0
    normalized: float = 0.0
    threshold: float = 1.0  # 归一化阈值


@dataclass
class ComplexityScore:
    """复杂度评分结果"""
    tier: ComplexityTier
    raw_score: float
    confidence: float
    dimensions: dict[str, ComplexityDimension] = field(default_factory=dict)
    has_tools: bool = False
    specificity_type: str | None = None
    tier_floor_applied: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


# 23 维度配置
DIMENSION_CONFIGS: dict[str, tuple[float, float]] = {
    # 代码复杂度（5维）
    "file_count": (0.8, 5.0),      # 文件数阈值
    "line_count": (1.0, 500.0),    # 行数阈值
    "function_count": (0.6, 20.0), # 函数数阈值
    "nesting_depth": (0.5, 4.0),   # 嵌套深度阈值
    "dependency_count": (0.7, 10.0), # 依赖数阈值

    # 任务复杂度（6维）
    "step_count": (0.9, 5.0),       # 步骤数阈值
    "decision_points": (1.2, 3.0),  # 决策点阈值
    "parallel_tasks": (1.0, 2.0),   # 并行任务阈值
    "verification_needed": (1.5, 1.0), # 验证需求阈值
    "documentation_needed": (0.8, 1.0), # 文档需求阈值
    "test_needed": (1.0, 1.0),      # 测试需求阈值

    # 上下文复杂度（4维）
    "message_count": (0.5, 10.0),   # 消息数阈值
    "token_count": (0.8, 2000.0),   # Token 数阈值
    "file_references": (0.6, 5.0),  # 文件引用阈值
    "history_length": (0.4, 5.0),   # 历史长度阈值

    # 工具复杂度（4维）
    "tool_count": (0.7, 3.0),       # 工具数阈值
    "tool_types": (1.0, 2.0),       # 工具类型阈值
    "cross_domain_calls": (1.2, 1.0), # 跨域调用阈值
    "permission_level": (0.5, 2.0), # 权限需求阈值

    # 知识复杂度（4维）
    "domain_count": (0.6, 2.0),     # 领域数阈值
    "concept_count": (0.8, 5.0),    # 概念数阈值
    "reasoning_depth": (1.5, 2.0),  # 推理深度阈值
    "uncertainty_level": (1.0, 1.0), # 不确定性阈值
}

# Tier 分值范围
TIER_RANGES: dict[ComplexityTier, tuple[float, float]] = {
    ComplexityTier.SIMPLE: (0.0, 2.0),
    ComplexityTier.STANDARD: (2.0, 5.0),
    ComplexityTier.COMPLEX: (5.0, 10.0),
    ComplexityTier.REASONING: (10.0, 15.0),
}