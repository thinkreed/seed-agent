"""
复杂度评分核心模块

基于 23 维度评估任务复杂度，决定模型路由 Tier。

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
from typing import Any

from src.client._complexity_types import (
    DIMENSION_CONFIGS,
    TIER_RANGES,
    ComplexityDimension,
    ComplexityScore,
    ComplexityTier,
)

logger = logging.getLogger("seed_agent")


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
        code_context = context.get("code_context", {}) if context else {}

        # 从上下文或消息推断
        if code_context:
            self._set_dimension("file_count", code_context.get("file_count", 0))
            self._set_dimension("line_count", code_context.get("line_count", 0))
            self._set_dimension("function_count", code_context.get("function_count", 0))
            self._set_dimension("nesting_depth", code_context.get("nesting_depth", 0))
            self._set_dimension("dependency_count", code_context.get("dependency_count", 0))
        else:
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
            len(msg.get("content", "").split()) * 1.5
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
        tool_context = context.get("tool_context", {}) if context else {}

        # 工具数
        tool_count = tool_context.get("tool_count", 0)
        if has_tools and tool_count == 0:
            tool_count = 1
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
            dim.normalized = min(value / dim.threshold, 1.0)

    def _sigmoid_confidence(self, score: float) -> float:
        """Sigmoid 置信度平滑"""
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