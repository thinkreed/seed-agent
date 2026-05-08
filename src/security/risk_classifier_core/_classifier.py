"""
命令风险分类器 - 核心分类逻辑

根据工具类型、参数内容、用户权限、Sandbox 隔离等级动态评估风险

参考来源: Harness Engineering "工具与权限"
"""

import logging

from src.security.risk_classifier_core._factors import analyze_param_risk
from src.security.risk_classifier_core._history import (
    ClassificationHistory,
    log_classification_result,
)
from src.security.risk_classifier_core._scoring import (
    calculate_final_score,
    get_isolation_risk_modifier,
    get_tool_base_risk,
    get_user_risk_modifier,
    score_to_level,
)
from src.security.risk_classifier_core._types import (
    RISK_LEVEL_CONFIGS,
    ClassificationResult,
)

logger = logging.getLogger(__name__)


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
        self._history = ClassificationHistory(max_history_size)
        logger.info(
            f"CommandRiskClassifier initialized: "
            f"isolation={isolation_level}, user_level={user_permission_level}"
        )

    def classify(self, tool_name: str, args: dict) -> ClassificationResult:
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
        final_score = calculate_final_score(
            base_risk, param_risk, user_modifier, isolation_modifier
        )

        # 6. 映射到风险等级
        risk_level = score_to_level(final_score)
        config = RISK_LEVEL_CONFIGS[risk_level]

        # 7. 创建分类结果
        result = ClassificationResult(
            risk_level=risk_level,
            action=config.action,
            score=final_score,
            tool_name=tool_name,
            args=args,
            factors=factors,
        )

        # 8. 记录并日志
        self._history.record(result)
        log_classification_result(result, config)

        return result

    @property
    def _classification_history(self) -> list[ClassificationResult]:
        """向后兼容：提供对历史记录列表的直接访问"""
        return self._history._history

    def get_classification_stats(self) -> dict:
        """获取分类统计"""
        return self._history.get_stats()

    def get_recent_classifications(self, limit: int = 10) -> list[ClassificationResult]:
        """获取最近的分类记录"""
        return self._history.get_recent(limit)

    def clear_history(self) -> None:
        """清空分类历史"""
        self._history.clear()

    def update_user_level(self, new_level: str) -> None:
        """更新用户权限等级"""
        self._user_permission_level = new_level
        logger.info(f"User permission level updated: {new_level}")

    def update_isolation_level(self, new_level: str) -> None:
        """更新隔离等级"""
        self._isolation_level = new_level
        logger.info(f"Isolation level updated: {new_level}")