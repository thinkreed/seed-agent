"""
智能上下文裁剪模块

根据当前任务相关性裁剪不相关历史。

模块拆分:
- _pruner_core/_entity_extraction.py: 实体提取
- _pruner_core/_relevance.py: 相关性计算

核心特性：
- 保留高相关性消息
- 添加裁剪说明
- 最小保留数量保护
"""

import logging
from typing import TYPE_CHECKING, Any

from src.context._config import PruningConfig
from src.context._pruner_core import (
    EntityExtractionMixin,
    RelevanceMixin,
)

if TYPE_CHECKING:
    from src.client import LLMGateway

logger = logging.getLogger(__name__)


class IntelligentContextPruner(EntityExtractionMixin, RelevanceMixin):
    """智能上下文裁剪

    使用 Mixin 组合拆分后的功能模块。
    """

    def __init__(
        self,
        gateway: "LLMGateway | None" = None,
        model_id: str | None = None,
        config: PruningConfig | None = None,
    ):
        """初始化裁剪器"""
        self._gateway = gateway
        self._model_id = model_id
        self._config = config or PruningConfig()

    def prune_for_task(
        self, history: list[dict[str, Any]], current_task: str
    ) -> list[dict[str, Any]]:
        """根据当前任务裁剪不相关上下文"""
        # 1. 系统消息和摘要消息总是保留
        always_preserve = [
            m for m in history
            if m["role"] == "system" or "摘要" in m.get("content", "")
        ]

        # 2. 可裁剪的消息
        prunable = [
            m for m in history
            if m["role"] != "system" and "摘要" not in m.get("content", "")
        ]

        if not prunable:
            return history

        # 3. 提取任务关键实体
        entities = self._extract_entities(current_task)

        if not entities:
            return history

        # 4. 计算相关性分数
        relevance_scores = self._compute_relevance(prunable, entities)

        # 5. 保留高相关性消息
        pruned = []
        for msg, score in zip(prunable, relevance_scores, strict=True):
            if score > self._config.relevance_threshold:
                pruned.append(msg)

        # 6. 最小保留保护
        if len(pruned) < self._config.min_preserve_count:
            scored_msgs = sorted(
                zip(prunable, relevance_scores, strict=True),
                key=lambda x: x[1],
                reverse=True,
            )
            pruned = [m for m, s in scored_msgs[:self._config.min_preserve_count]]

        # 7. 合并结果
        result = always_preserve + pruned

        # 8. 添加裁剪说明
        if len(result) < len(history):
            filtered_count = len(history) - len(result)
            result.append({
                "role": "system",
                "content": f"[裁剪说明: 已过滤 {filtered_count} 条低相关性历史，保留 {len(result)} 条]",
            })

        logger.info(
            f"Context pruned for task: {len(history)} -> {len(result)} messages"
        )

        return result

    async def prune_with_semantic_relevance(
        self, history: list[dict[str, Any]], current_task: str
    ) -> list[dict[str, Any]]:
        """使用语义相关性裁剪（LLM 评估）"""
        if not self._gateway or not self._model_id:
            return self.prune_for_task(history, current_task)

        always_preserve = [
            m for m in history
            if m["role"] == "system" or "摘要" in m.get("content", "")
        ]

        prunable = [
            m for m in history
            if m["role"] != "system" and "摘要" not in m.get("content", "")
        ]

        if not prunable:
            return history

        semantic_scores = await self._compute_semantic_relevance(prunable, current_task)

        pruned = []
        for msg, score in zip(prunable, semantic_scores, strict=True):
            if score > self._config.relevance_threshold:
                pruned.append(msg)

        if len(pruned) < self._config.min_preserve_count:
            scored_msgs = sorted(
                zip(prunable, semantic_scores, strict=True),
                key=lambda x: x[1],
                reverse=True,
            )
            pruned = [m for m, s in scored_msgs[:self._config.min_preserve_count]]

        result = always_preserve + pruned

        if len(result) < len(history):
            filtered_count = len(history) - len(result)
            result.append({
                "role": "system",
                "content": f"[语义裁剪: 已过滤 {filtered_count} 条，保留 {len(result)} 条]",
            })

        return result


__all__ = ["IntelligentContextPruner"]