"""
命令风险分类器 - 核心分类逻辑

根据工具类型、参数内容、用户权限、Sandbox 隔离等级动态评估风险

参考来源: Harness Engineering "工具与权限"
"""

import logging

from src.security.risk_classifier_core._factors import analyze_param_risk
from src.security.risk_classifier_core._types import (
    ClassificationResult,
    ISOLATION_LEVEL_MODIFIERS,
    RiskAction,
    RiskLevel,
    RiskLevelConfig,
    RISK_LEVEL_CONFIGS,
    TOOL_BASE_RISKS,
    USER_LEVEL_MODIFIERS,
)

logger = logging.getLogger(__name__)


def score_to_level(score: float) -> RiskLevel:
    """分数映射到风险等级"""
    if score < 0.3:
        return RiskLevel.SAFE
    if score < 0.6:
        return RiskLevel.CAUTION
    if score < 1.2:
        return RiskLevel.RISKY
    return RiskLevel.DANGEROUS


def get_tool_base_risk(tool_name: str) -> float:
    """获取工具基础风险分数"""
    return TOOL_BASE_RISKS.get(tool_name, TOOL_BASE_RISKS["default"])


def get_user_risk_modifier(user_level: str) -> float:
    """获取用户权限等级风险修正"""
    return USER_LEVEL_MODIFIERS.get(user_level, 0.0)


def get_isolation_risk_modifier(isolation_level: str) -> float:
    """获取 Sandbox 隔离等级风险修正"""
    return ISOLATION_LEVEL_MODIFIERS.get(isolation_level, 0.0)


class CommandRiskClassifier:
    """命令风险分类器

    核心功能:
    - 工具基础风险评估
    - 参数风险分析（路径遍历、危险命令等）
    - 用户权限等级调整
    - Sandbox 隔离等级调整
    - 分类历史记录

    Example:
        classifier = CommandRiskClassifier(isolation_level="process", user_level="normal")
        result = classifier.classify("file_read", {"path": "/tmp/test.txt"})
        # result.risk_level = RiskLevel.SAFE
        # result.action = RiskAction.AUTO_EXECUTE
    """

    def __init__(
        self,
        isolation_level: str = "process",
        user_permission_level: str = "normal",
        max_history_size: int = 1000,
    ):
        """初始化风险分类器

        Args:
            isolation_level: Sandbox 隔离等级 (vm/container/process/none)
            user_permission_level: 用户权限等级 (admin/trusted/normal/guest/restricted)
            max_history_size: 分类历史最大记录数
        """
        self._isolation_level = isolation_level
        self._user_permission_level = user_permission_level
        self._classification_history: list[ClassificationResult] = []
        self._max_history_size = max_history_size

        logger.info(
            f"CommandRiskClassifier initialized: "
            f"isolation={isolation_level}, user_level={user_permission_level}"
        )

    def classify(
        self,
        tool_name: str,
        args: dict,
    ) -> ClassificationResult:
        """分类命令风险

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            ClassificationResult: 分类结果
        """
        factors: list[str] = []

        # 1. 工具基础风险
        base_risk = get_tool_base_risk(tool_name)
        if base_risk > 0:
            factors.append(f"tool_base_risk={base_risk:.2f}")

        # 2. 参数风险分析
        param_risk, param_factors = analyze_param_risk(tool_name, args)
        factors.extend(param_factors)

        # 3. 用户权限等级调整
        user_modifier = get_user_risk_modifier(self._user_permission_level)
        if user_modifier != 0:
            factors.append(f"user_modifier={user_modifier:.2f}")

        # 4. Sandbox 隔离等级调整
        isolation_modifier = get_isolation_risk_modifier(self._isolation_level)
        if isolation_modifier != 0:
            factors.append(f"isolation_modifier={isolation_modifier:.2f}")

        # 5. 综合评估
        final_score = base_risk + param_risk + user_modifier + isolation_modifier
        final_score = max(0.0, final_score)

        # 6. 映射到风险等级
        risk_level = score_to_level(final_score)
        config = RISK_LEVEL_CONFIGS[risk_level]
        action = config.action

        # 7. 创建分类结果
        result = ClassificationResult(
            risk_level=risk_level,
            action=action,
            score=final_score,
            tool_name=tool_name,
            args=args,
            factors=factors,
        )

        # 8. 记录分类历史
        self._record_classification(result)

        # 9. 日志记录
        self._log_classification(result, config)

        return result

    def _record_classification(self, result: ClassificationResult) -> None:
        """记录分类历史"""
        self._classification_history.append(result)

        if len(self._classification_history) > self._max_history_size:
            self._classification_history = self._classification_history[-self._max_history_size:]

    def _log_classification(
        self,
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

    def get_classification_stats(self) -> dict:
        """获取分类统计"""
        stats: dict = {
            "total_classifications": len(self._classification_history),
            "by_level": {},
            "by_action": {},
            "average_score": 0.0,
        }

        for level in RiskLevel:
            stats["by_level"][level.value] = sum(
                1 for c in self._classification_history if c.risk_level == level
            )

        for action in RiskAction:
            stats["by_action"][action.value] = sum(
                1 for c in self._classification_history if c.action == action
            )

        if self._classification_history:
            stats["average_score"] = sum(
                c.score for c in self._classification_history
            ) / len(self._classification_history)

        return stats

    def get_recent_classifications(self, limit: int = 10) -> list[ClassificationResult]:
        """获取最近的分类记录"""
        return self._classification_history[-limit:]

    def clear_history(self) -> None:
        """清空分类历史"""
        self._classification_history.clear()
        logger.info("Classification history cleared")

    def update_user_level(self, new_level: str) -> None:
        """更新用户权限等级"""
        self._user_permission_level = new_level
        logger.info(f"User permission level updated: {new_level}")

    def update_isolation_level(self, new_level: str) -> None:
        """更新隔离等级"""
        self._isolation_level = new_level
        logger.info(f"Isolation level updated: {new_level}")