"""
分类历史记录管理

提供分类历史的记录、统计和查询功能
"""

import logging
from typing import TYPE_CHECKING

from src.security.risk_classifier_core._types import (
    ClassificationResult,
    RiskAction,
    RiskLevel,
    RiskLevelConfig,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ClassificationHistory:
    """分类历史记录管理器

    功能:
    - 记录分类历史
    - 统计分类结果
    - 查询历史记录
    """

    def __init__(self, max_size: int = 1000):
        """初始化历史记录管理器

        Args:
            max_size: 最大记录数
        """
        self._history: list[ClassificationResult] = []
        self._max_size = max_size

    def record(self, result: ClassificationResult) -> None:
        """记录分类结果"""
        self._history.append(result)
        if len(self._history) > self._max_size:
            self._history = self._history[-self._max_size :]

    def get_stats(self) -> dict:
        """获取分类统计"""
        stats: dict = {
            "total_classifications": len(self._history),
            "by_level": {},
            "by_action": {},
            "average_score": 0.0,
        }

        for level in RiskLevel:
            stats["by_level"][level.value] = sum(
                1 for c in self._history if c.risk_level == level
            )

        for action in RiskAction:
            stats["by_action"][action.value] = sum(
                1 for c in self._history if c.action == action
            )

        if self._history:
            stats["average_score"] = sum(c.score for c in self._history) / len(
                self._history
            )

        return stats

    def get_recent(self, limit: int = 10) -> list[ClassificationResult]:
        """获取最近的分类记录"""
        return self._history[-limit:]

    def clear(self) -> None:
        """清空历史记录"""
        self._history.clear()
        logger.info("Classification history cleared")


def log_classification_result(
    result: ClassificationResult,
    config: RiskLevelConfig,
) -> None:
    """日志记录分类结果"""
    log_msg = (
        f"Risk classification: tool={result.tool_name}, "
        f"level={result.risk_level.value}, "
        f"score={result.score:.2f}, "
        f"action={result.action.value}, "
        f"factors=[{', '.join(result.factors)}]"
    )

    if config.log_level == "INFO":
        logger.info(log_msg)
    elif config.log_level == "WARNING":
        logger.warning(log_msg)
    elif config.log_level == "ERROR":
        logger.error(log_msg)