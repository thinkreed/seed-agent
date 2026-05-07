"""
复杂度评分路由模块

借鉴 manifest-architecture 设计的智能模型路由器。

核心功能:
- 23 维度复杂度评分
- 四级 Tier 路由（simple/standard/complex/reasoning）
- Sigmoid 置信度平滑
- Tier Floor 机制（有 Tools 时提升）

参考 manifest-architecture:
- 三层路由优先级：Header Tiers → Specificity → Complexity
- 23 维度评分 → 四级 Tier
- Sigmoid 置信度计算：平滑 Tier 边界过渡
- Tier Floor 机制：有 Tools 时强制提升 Tier

维度设计:
1. 代码复杂度（5维）：文件数、行数、函数数、嵌套深度、依赖数
2. 任务复杂度（6维）：步骤数、决策点、并行任务、验证需求、文档需求、测试需求
3. 上下文复杂度（4维）：消息数、Token 数、文件引用、历史长度
4. 工具复杂度（4维）：工具数、工具类型、跨域调用、权限需求
5. 知识复杂度（4维）：领域数、概念数、推理深度、不确定性
"""

import logging
import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("seed_agent")


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


class ComplexityScorer:
    """复杂度评分器

    基于 23 维度评估任务复杂度，决定模型路由 Tier。

    使用方式:
    ```python
    scorer = ComplexityScorer()

    # 分析消息列表
    score = scorer.score_messages(messages, has_tools=True)

    # 根据 Tier 选择模型
    model = select_model_for_tier(score.tier)
    ```

    Tier Floor 机制：
    - 有 Tools 时强制提升到至少 STANDARD
    - 多个 Tools 时提升到 COMPLEX
    - 复杂工具（执行、沙箱）时提升到 REASONING
    """

    def __init__(self):
        self._dimensions = self._init_dimensions()

    def _init_dimensions(self) -> dict[str, ComplexityDimension]:
        """初始化维度"""
        return {
            name: ComplexityDimension(
                name=name,
                weight=weight,
                threshold=threshold,
            )
            for name, (weight, threshold) in DIMENSION_CONFIGS.items()
        }

    def score_messages(
        self,
        messages: list[dict],
        has_tools: bool = False,
        specificity_type: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ComplexityScore:
        """评分消息列表

        Args:
            messages: LLM 消息列表
            has_tools: 是否有工具调用
            specificity_type: 特定类型（coding, analysis 等）
            context: 额外上下文

        Returns:
            ComplexityScore 评分结果
        """
        # 分析维度
        self._analyze_code_complexity(messages, context)
        self._analyze_task_complexity(messages, context)
        self._analyze_context_complexity(messages, context)
        self._analyze_tool_complexity(messages, has_tools, context)
        self._analyze_knowledge_complexity(messages, context)

        # 计算总分
        raw_score = sum(
            dim.normalized * dim.weight
            for dim in self._dimensions.values()
        )

        # Sigmoid 置信度平滑
        confidence = self._sigmoid_confidence(raw_score)

        # 确定 Tier
        tier = self._determine_tier(raw_score)

        # 应用 Tier Floor
        tier, tier_floor_applied = self._apply_tier_floor(
            tier, has_tools, self._get_tool_complexity_score()
        )

        return ComplexityScore(
            tier=tier,
            raw_score=raw_score,
            confidence=confidence,
            dimensions=dict(self._dimensions),
            has_tools=has_tools,
            specificity_type=specificity_type,
            tier_floor_applied=tier_floor_applied,
            metadata=context or {},
        )

    def _analyze_code_complexity(
        self,
        messages: list[dict],
        context: dict[str, Any] | None,
    ) -> None:
        """分析代码复杂度"""
        # 从上下文或消息中提取代码信息
        code_context = context.get("code_context", {})

        # 文件数
        file_count = code_context.get("file_count", 0)
        self._set_dimension("file_count", file_count)

        # 行数
        line_count = code_context.get("line_count", 0)
        self._set_dimension("line_count", line_count)

        # 函数数
        function_count = code_context.get("function_count", 0)
        self._set_dimension("function_count", function_count)

        # 嵌套深度（从代码分析）
        nesting_depth = code_context.get("nesting_depth", 0)
        self._set_dimension("nesting_depth", nesting_depth)

        # 依赖数
        dependency_count = code_context.get("dependency_count", 0)
        self._set_dimension("dependency_count", dependency_count)

        # 如果没有提供上下文，从消息推断
        if not code_context:
            self._infer_code_complexity(messages)

    def _infer_code_complexity(self, messages: list[dict]) -> None:
        """从消息推断代码复杂度"""
        total_content = ""
        for msg in messages:
            if msg.get("role") in ["user", "assistant"]:
                total_content += msg.get("content", "") + "\n"

        # 文件数：查找文件路径引用
        file_refs = re.findall(r'[\w/]+\.(py|js|ts|java|go|rs)', total_content)
        self._set_dimension("file_count", len(set(file_refs)))

        # 行数：代码块行数
        code_blocks = re.findall(r'```[\w]*\n(.*?)```', total_content, re.DOTALL)
        total_lines = sum(len(block.split('\n')) for block in code_blocks)
        self._set_dimension("line_count", total_lines)

        # 函数数：def/function 声明
        functions = re.findall(r'(def |function |func )', total_content)
        self._set_dimension("function_count", len(functions))

    def _analyze_task_complexity(
        self,
        messages: list[dict],
        context: dict[str, Any] | None,
    ) -> None:
        """分析任务复杂度"""
        user_message = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_message += msg.get("content", "") + "\n"

        # 步骤数：查找步骤指示词
        steps = re.findall(r'(首先|然后|接着|最后|first|second|then|finally)', user_message.lower())
        self._set_dimension("step_count", len(steps) // 2 + 1)

        # 决策点：查找条件词
        decisions = re.findall(r'(如果|否则|判断|if|else|when|condition)', user_message.lower())
        self._set_dimension("decision_points", len(decisions))

        # 并行任务
        parallel_keywords = re.findall(r'(并行|同时|parallel|concurrent)', user_message.lower())
        self._set_dimension("parallel_tasks", len(parallel_keywords))

        # 验证需求
        if "验证" in user_message or "verify" in user_message.lower():
            self._set_dimension("verification_needed", 1.0)

        # 文档需求
        if "文档" in user_message or "document" in user_message.lower():
            self._set_dimension("documentation_needed", 1.0)

        # 测试需求
        if "测试" in user_message or "test" in user_message.lower():
            self._set_dimension("test_needed", 1.0)

    def _analyze_context_complexity(
        self,
        messages: list[dict],
        context: dict[str, Any] | None,
    ) -> None:
        """分析上下文复杂度"""
        # 消息数
        self._set_dimension("message_count", len(messages))

        # Token 数（估算）
        total_tokens = sum(
            len(msg.get("content", "").split()) * 1.5  # 估算 Token
            for msg in messages
        )
        self._set_dimension("token_count", total_tokens)

        # 文件引用
        total_content = ""
        for msg in messages:
            total_content += msg.get("content", "") + "\n"
        file_refs = re.findall(r'[\w/]+\.[\w]+', total_content)
        self._set_dimension("file_references", len(set(file_refs)))

        # 历史长度
        history_length = context.get("history_length", 0) if context else 0
        self._set_dimension("history_length", history_length)

    def _analyze_tool_complexity(
        self,
        messages: list[dict],
        has_tools: bool,
        context: dict[str, Any] | None,
    ) -> None:
        """分析工具复杂度"""
        tool_context = context.get("tool_context", {})

        # 工具数
        tool_count = tool_context.get("tool_count", 0)
        if has_tools and tool_count == 0:
            tool_count = 1  # 有工具但未指定数量，假设至少 1
        self._set_dimension("tool_count", tool_count)

        # 工具类型
        tool_types = tool_context.get("tool_types", 1)
        self._set_dimension("tool_types", tool_types)

        # 跨域调用
        cross_domain = tool_context.get("cross_domain", False)
        self._set_dimension("cross_domain_calls", 1.0 if cross_domain else 0.0)

        # 权限需求
        permission_level = tool_context.get("permission_level", 0)
        self._set_dimension("permission_level", permission_level)

    def _analyze_knowledge_complexity(
        self,
        messages: list[dict],
        context: dict[str, Any] | None,
    ) -> None:
        """分析知识复杂度"""
        user_message = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_message += msg.get("content", "") + "\n"

        # 领域数
        domain_keywords = re.findall(
            r'(架构|设计|安全|性能|测试|architecture|security|performance|testing)',
            user_message.lower()
        )
        self._set_dimension("domain_count", len(set(domain_keywords)))

        # 概念数
        concepts = re.findall(r'(概念|原理|机制|concept|principle|mechanism)', user_message.lower())
        self._set_dimension("concept_count", len(concepts))

        # 推理深度
        reasoning_keywords = re.findall(
            r'(分析|推断|推理|判断|analyze|infer|reason|judge)',
            user_message.lower()
        )
        self._set_dimension("reasoning_depth", len(reasoning_keywords))

        # 不确定性
        uncertainty_keywords = re.findall(
            r'(不确定|可能|假设|假设|uncertain|maybe|assume|hypothesis)',
            user_message.lower()
        )
        self._set_dimension("uncertainty_level", len(uncertainty_keywords))

    def _set_dimension(self, name: str, value: float) -> None:
        """设置维度值"""
        if name in self._dimensions:
            dim = self._dimensions[name]
            dim.value = value
            dim.normalized = min(value / dim.threshold, 1.0)  # 归一化到 [0, 1]

    def _sigmoid_confidence(self, score: float) -> float:
        """Sigmoid 置信度平滑"""
        # 使用 Sigmoid 函数平滑置信度
        k = 0.3  # 增益系数
        x0 = 5.0  # 中点
        return 1.0 / (1.0 + math.exp(-k * (score - x0)))

    def _determine_tier(self, score: float) -> ComplexityTier:
        """确定 Tier"""
        for tier, (low, high) in TIER_RANGES.items():
            if low <= score < high:
                return tier
        return ComplexityTier.REASONING

    def _apply_tier_floor(
        self,
        tier: ComplexityTier,
        has_tools: bool,
        tool_score: float,
    ) -> tuple[ComplexityTier, bool]:
        """应用 Tier Floor 机制"""
        if not has_tools:
            return tier, False

        # 有 Tools 时强制提升
        tier_order = list(ComplexityTier)
        current_idx = tier_order.index(tier)

        # 工具数 >= 3 或复杂工具时提升到 REASONING
        if tool_score >= 2.0 or self._dimensions["tool_count"].value >= 3:
            min_tier = ComplexityTier.REASONING
        # 工具数 >= 1 时提升到至少 STANDARD
        elif self._dimensions["tool_count"].value >= 1:
            min_tier = ComplexityTier.STANDARD
        else:
            return tier, False

        min_idx = tier_order.index(min_tier)
        if min_idx > current_idx:
            return min_tier, True

        return tier, False

    def _get_tool_complexity_score(self) -> float:
        """获取工具复杂度得分"""
        return (
            self._dimensions["tool_count"].normalized +
            self._dimensions["tool_types"].normalized +
            self._dimensions["cross_domain_calls"].normalized +
            self._dimensions["permission_level"].normalized
        )


def select_model_for_tier(
    tier: ComplexityTier,
    model_mapping: dict[ComplexityTier, str] | None = None,
) -> str:
    """根据 Tier 选择模型

    Args:
        tier: 复杂度层级
        model_mapping: Tier 到模型的映射

    Returns:
        模型 ID
    """
    default_mapping = {
        ComplexityTier.SIMPLE: "gpt-4o-mini",
        ComplexityTier.STANDARD: "gpt-4o",
        ComplexityTier.COMPLEX: "claude-3-5-sonnet",
        ComplexityTier.REASONING: "claude-3-opus",
    }
    mapping = model_mapping or default_mapping
    return mapping.get(tier, default_mapping[ComplexityTier.STANDARD])