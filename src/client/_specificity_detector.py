"""
Specificity 检测核心模块

基于 keywords 和 patterns 检测任务类型，用于路由到专用模型。

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
from typing import Any

from src.client._specificity_types import (
    SPECIFICITY_KEYWORDS,
    SPECIFICITY_MODEL_MAPPING,
    SPECIFICITY_PATTERNS,
    SpecificityResult,
    SpecificityType,
)

logger = logging.getLogger("seed_agent")


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
                pattern_scores[spec_type] = len(matches) / len(patterns) * 0.5
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
        """获取特定类型的模型"""
        model = self._model_mapping.get(spec_type)
        if model:
            return model
        return tier_fallback or self._model_mapping.get(SpecificityType.GENERAL, "gpt-4o")

    def update_model_mapping(self, spec_type: SpecificityType, model: str) -> None:
        """更新特定类型的模型映射"""
        self._model_mapping[spec_type] = model