"""
Specificity 检测模块

借鉴 manifest-architecture 设计的任务类型检测路由机制。

核心功能:
- 任务类型自动检测（coding、data_analysis、web_browsing 等）
- 特定类型路由到专用模型
- Specificity 优先级高于 Complexity

参考 manifest-architecture:
- Specificity 检测：coding/data_analysis/web_browsing 路由特定模型
- Specificity > Complexity 优先级

检测类型:
- coding: 代码编写、重构、调试
- data_analysis: 数据分析、可视化、统计
- web_browsing: 网页浏览、搜索、信息提取
- planning: 规划、设计、决策
- reasoning: 推理、分析、判断
- conversation: 对话、问答、解释
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("seed_agent")


class SpecificityType(Enum):
    """任务特定类型"""
    CODING = "coding"            # 代码编写
    DATA_ANALYSIS = "data_analysis"  # 数据分析
    WEB_BROWSING = "web_browsing"    # 网页浏览
    PLANNING = "planning"        # 规划设计
    REASONING = "reasoning"      # 推理分析
    CONVERSATION = "conversation"    # 对话问答
    GENERAL = "general"          # 通用任务


@dataclass
class SpecificityResult:
    """Specificity 检测结果"""
    detected_type: SpecificityType
    confidence: float
    keywords_matched: list[str] = field(default_factory=list)
    patterns_matched: list[str] = field(default_factory=list)
    model_override: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# 特定类型关键词配置
SPECIFICITY_KEYWORDS: dict[SpecificityType, list[str]] = {
    SpecificityType.CODING: [
        "代码", "函数", "类", "模块", "重构", "调试", "bug",
        "code", "function", "class", "module", "refactor", "debug",
        "implement", "python", "javascript", "typescript", "java", "go",
        "写代码", "修改", "实现", "添加", "删除", "创建",
        "文件", "编辑", "git", "commit", "test", "测试",
    ],
    SpecificityType.DATA_ANALYSIS: [
        "数据", "分析", "统计", "可视化", "图表", "报表",
        "data", "analysis", "statistics", "visualization", "chart",
        "csv", "json", "excel", "pandas", "numpy", "plot",
        "计算", "平均值", "分布", "趋势", "预测",
    ],
    SpecificityType.WEB_BROWSING: [
        "网页", "浏览", "搜索", "网站", "链接", "内容",
        "web", "browse", "search", "website", "link", "content",
        "url", "http", "fetch", "download", "爬取", "抓取",
        "查看", "访问", "获取", "读取网页",
    ],
    SpecificityType.PLANNING: [
        "规划", "计划", "设计", "方案", "架构", "策略",
        "plan", "design", "scheme", "architecture", "strategy",
        "步骤", "流程", "路线", "里程碑", "时间表",
        "如何", "怎么做", "实现方案", "设计方案",
    ],
    SpecificityType.REASONING: [
        "推理", "分析", "判断", "决策", "比较", "评估",
        "reason", "analyze", "judge", "decide", "compare", "evaluate",
        "为什么", "原因", "影响", "后果", "可能性",
        "思考", "考虑", "权衡", "选择", "取舍",
    ],
    SpecificityType.CONVERSATION: [
        "解释", "说明", "介绍", "什么是", "如何理解",
        "explain", "describe", "introduce", "what is", "how to",
        "帮我", "请", "可以", "能否", "帮我理解",
        "问题", "疑问", "困惑", "请教",
    ],
}

# 特定类型模型映射（可覆盖）
SPECIFICITY_MODEL_MAPPING: dict[SpecificityType, str] = {
    SpecificityType.CODING: "claude-3-5-sonnet",      # 代码任务用 Claude
    SpecificityType.DATA_ANALYSIS: "gpt-4o",          # 数据分析用 GPT-4o
    SpecificityType.WEB_BROWSING: "gpt-4o-mini",      # 网页浏览用轻量模型
    SpecificityType.PLANNING: "claude-3-5-sonnet",    # 规划用 Claude
    SpecificityType.REASONING: "claude-3-opus",       # 推理用最强模型
    SpecificityType.CONVERSATION: "gpt-4o-mini",      # 对话用轻量模型
    SpecificityType.GENERAL: "gpt-4o",                # 通用任务用 GPT-4o
}

# 特定类型正则模式
SPECIFICITY_PATTERNS: dict[SpecificityType, list[str]] = {
    SpecificityType.CODING: [
        r'(write|create|implement|modify|edit|fix)\s+(a|the|this)?\s*(function|class|module|script|code)',
        r'(def |function |class |import |from |async def)',
        r'(\.py|\.js|\.ts|\.java|\.go|\.rs)',
        r'(git|commit|push|pull|merge|branch)',
        r'(syntax|error|bug|fix|debug)',
    ],
    SpecificityType.DATA_ANALYSIS: [
        r'(analyze|analysis)\s+(the|this)?\s*(data|dataset|file)',
        r'(csv|json|excel|pandas|numpy)',
        r'(plot|chart|graph|visualize)',
        r'(statistics|average|mean|median|std)',
    ],
    SpecificityType.WEB_BROWSING: [
        r'(browse|visit|fetch|download|scrape)\s+(the|this)?\s*(url|website|page|link)',
        r'(https?://|www\.)',
        r'(web|internet|online)',
    ],
    SpecificityType.PLANNING: [
        r'(plan|design|create)\s+(a|the)?\s*(plan|scheme|architecture|strategy)',
        r'(step|phase|milestone|timeline)',
        r'(roadmap|approach|method)',
    ],
    SpecificityType.REASONING: [
        r'(analyze|analyze|reason|judge|decide)\s+(the|this)?',
        r'(why|reason|cause|impact|effect)',
        r'(compare|evaluate|assess)',
    ],
    SpecificityType.CONVERSATION: [
        r'(explain|describe|introduce)\s+(what|how|why)',
        r'(help\s+me|please\s+help|can\s+you)',
        r'(what\s+is|how\s+to|tell\s+me)',
    ],
}


class SpecificityDetector:
    """任务特定类型检测器

    基于 keywords 和 patterns 检测任务类型，
    用于路由到专用模型。

    使用方式:
    ```python
    detector = SpecificityDetector()

    # 检测消息类型
    result = detector.detect(messages)

    # 获取推荐模型
    model = result.model_override or select_model_for_tier(tier)
    ```

    优先级规则:
    - Specificity > Complexity
    - 明确的 coding/planning 任务路由到专用模型
    - 模糊任务按 Complexity 路由
    """

    def __init__(
        self,
        model_mapping: dict[SpecificityType, str] | None = None,
        min_confidence: float = 0.6,
    ):
        self._model_mapping = model_mapping or SPECIFICITY_MODEL_MAPPING
        self._min_confidence = min_confidence
        self._keywords = SPECIFICITY_KEYWORDS
        self._patterns = SPECIFICITY_PATTERNS

    def detect(
        self,
        messages: list[dict],
        context: dict[str, Any] | None = None,
    ) -> SpecificityResult:
        """检测任务类型

        Args:
            messages: LLM 消息列表
            context: 额外上下文

        Returns:
            SpecificityResult 检测结果
        """
        # 提取用户消息内容
        user_content = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_content += msg.get("content", "") + "\n"

        # 关键词匹配
        keyword_scores: dict[SpecificityType, float] = {}
        matched_keywords: dict[SpecificityType, list[str]] = {}

        for spec_type, keywords in self._keywords.items():
            matches = []
            for kw in keywords:
                if kw.lower() in user_content.lower():
                    matches.append(kw)
            if matches:
                keyword_scores[spec_type] = len(matches) / len(keywords)
                matched_keywords[spec_type] = matches

        # 正则模式匹配
        pattern_scores: dict[SpecificityType, float] = {}
        matched_patterns: dict[SpecificityType, list[str]] = {}

        for spec_type, patterns in self._patterns.items():
            matches = []
            for pattern in patterns:
                try:
                    if re.search(pattern, user_content, re.IGNORECASE):
                        matches.append(pattern)
                except re.error:
                    pass
            if matches:
                pattern_scores[spec_type] = len(matches) / len(patterns) * 0.5  # 模式权重更高
                matched_patterns[spec_type] = matches

        # 合并得分
        total_scores: dict[SpecificityType, float] = {}
        for spec_type in SpecificityType:
            kw_score = keyword_scores.get(spec_type, 0.0)
            pt_score = pattern_scores.get(spec_type, 0.0)
            total_scores[spec_type] = kw_score + pt_score

        # 选择最高得分类型
        if not total_scores:
            return SpecificityResult(
                detected_type=SpecificityType.GENERAL,
                confidence=0.0,
                model_override=self._model_mapping.get(SpecificityType.GENERAL),
            )

        best_type = max(total_scores, key=total_scores.get)
        confidence = total_scores[best_type]

        # 置信度阈值检查
        if confidence < self._min_confidence:
            best_type = SpecificityType.GENERAL
            confidence = 0.0

        # 获取模型覆盖
        model_override = self._model_mapping.get(best_type)

        return SpecificityResult(
            detected_type=best_type,
            confidence=min(confidence, 1.0),
            keywords_matched=matched_keywords.get(best_type, []),
            patterns_matched=matched_patterns.get(best_type, []),
            model_override=model_override,
            metadata=context or {},
        )

    def detect_from_text(self, text: str) -> SpecificityResult:
        """从文本检测类型"""
        return self.detect([{"role": "user", "content": text}])

    def get_model_for_type(
        self,
        spec_type: SpecificityType,
        tier_fallback: str | None = None,
    ) -> str:
        """获取特定类型的模型

        Args:
            spec_type: 特定类型
            tier_fallback: Complexity Tier 备选模型

        Returns:
            模型 ID
        """
        model = self._model_mapping.get(spec_type)
        if model:
            return model
        return tier_fallback or self._model_mapping.get(SpecificityType.GENERAL, "gpt-4o")

    def update_model_mapping(self, spec_type: SpecificityType, model: str) -> None:
        """更新特定类型的模型映射"""
        self._model_mapping[spec_type] = model


class SpecificityRouter:
    """Specificity 路由器

    整合 SpecificityDetector 和 ComplexityScorer，
    实现三层路由优先级：Header Tiers → Specificity → Complexity

    路由顺序:
    1. Header Tier: HTTP 头显式指定 Tier（调试/测试）
    2. Specificity: 任务类型检测路由特定模型
    3. Complexity: 复杂度评分路由 Tier 模型
    """

    def __init__(
        self,
        detector: SpecificityDetector | None = None,
        model_mapping: dict[SpecificityType, str] | None = None,
    ):
        self._detector = detector or SpecificityDetector(model_mapping)

    def route(
        self,
        messages: list[dict],
        header_tier: str | None = None,
        has_tools: bool = False,
        context: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """路由到模型

        Args:
            messages: LLM 消息列表
            header_tier: HTTP 头指定 Tier（显式控制）
            has_tools: 是否有工具调用
            context: 额外上下文

        Returns:
            (model_id, routing_info) 元组
        """
        routing_info: dict[str, Any] = {
            "header_tier": header_tier,
            "specificity": None,
            "complexity": None,
            "route_source": "unknown",
        }

        # 1. Header Tier 优先级最高
        if header_tier:
            model = self._get_model_for_header_tier(header_tier)
            routing_info["route_source"] = "header"
            routing_info["header_tier"] = header_tier
            return model, routing_info

        # 2. Specificity 检测
        spec_result = self._detector.detect(messages, context)
        routing_info["specificity"] = {
            "type": spec_result.detected_type.value,
            "confidence": spec_result.confidence,
            "keywords": spec_result.keywords_matched,
            "patterns": spec_result.patterns_matched,
        }

        # Specificity 置信度足够高时直接路由
        if spec_result.confidence >= self._detector._min_confidence:
            routing_info["route_source"] = "specificity"
            return spec_result.model_override or "gpt-4o", routing_info

        # 3. Complexity 评分
        from src.client._complexity_scorer import ComplexityScorer, ComplexityTier, select_model_for_tier

        scorer = ComplexityScorer()
        comp_result = scorer.score_messages(messages, has_tools, str(spec_result.detected_type), context)

        routing_info["complexity"] = {
            "tier": comp_result.tier.value,
            "score": comp_result.raw_score,
            "confidence": comp_result.confidence,
            "tier_floor_applied": comp_result.tier_floor_applied,
        }
        routing_info["route_source"] = "complexity"

        model = select_model_for_tier(comp_result.tier)
        return model, routing_info

    def _get_model_for_header_tier(self, header_tier: str) -> str:
        """从 Header Tier 获取模型"""
        from src.client._complexity_scorer import ComplexityTier, select_model_for_tier

        tier_map = {
            "simple": ComplexityTier.SIMPLE,
            "standard": ComplexityTier.STANDARD,
            "complex": ComplexityTier.COMPLEX,
            "reasoning": ComplexityTier.REASONING,
        }
        tier = tier_map.get(header_tier.lower(), ComplexityTier.STANDARD)
        return select_model_for_tier(tier)


def get_specificity_detector() -> SpecificityDetector:
    """获取全局 SpecificityDetector"""
    return SpecificityDetector()


def get_specificity_router() -> SpecificityRouter:
    """获取全局 SpecificityRouter"""
    return SpecificityRouter()