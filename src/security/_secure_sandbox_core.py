"""
安全沙盒核心模块

包含 SecureSandbox 主类和公共 API
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.sandbox import IsolationLevel, Sandbox
from src.security._secure_sandbox_execution import (
    execute_single_tool_secure,
)
from src.security._secure_sandbox_types import SecureExecutionResult
from src.security.risk_classifier import (
    ClassificationResult,
    CommandRiskClassifier,
    RiskLevel,
)
from src.security.single_purpose_tools import SinglePurposeToolFactory
from src.security.tool_expander import (
    TOOL_TIER_CONFIGS,
    ProgressiveToolExpander,
    ToolTier,
)

logger = logging.getLogger(__name__)


class SecureSandbox(Sandbox):
    """带风险分类的安全沙盒

    继承自 Sandbox，添加:
    - 风险分类器
    - 渐进式工具扩展器
    - 单用途工具工厂
    - 用户确认机制

    Example:
        sandbox = SecureSandbox(
            isolation_level=IsolationLevel.PROCESS,
            user_permission_level="normal"
        )

        # 注册工具
        sandbox.register_tools(tool_registry)

        # 执行工具（带风险检查）
        result = await sandbox.execute_tools_secure(tool_calls)
    """

    def __init__(
        self,
        isolation_level: IsolationLevel = IsolationLevel.PROCESS,
        file_system_root: Path | None = None,
        workspace_path: Path | None = None,
        user_permission_level: str = "normal",
        enable_progressive_expansion: bool = True,
        enable_single_purpose_tools: bool = True,
        allow_risky_tools: bool = True,
        allow_dangerous_tools: bool = False,
        user_confirmation_callback: Callable[[str, str, dict], bool] | None = None,
    ):
        """初始化安全沙盒

        Args:
            isolation_level: 隔离级别
            file_system_root: 沙盒文件系统根目录
            workspace_path: 工作目录映射
            user_permission_level: 用户权限等级
            enable_progressive_expansion: 是否启用渐进式扩展
            enable_single_purpose_tools: 是否启用单用途工具
            allow_risky_tools: 是否允许 risky 级别工具
            allow_dangerous_tools: 是否允许 dangerous 级别工具
            user_confirmation_callback: 用户确认回调 (tool_name, risk_level, args) -> bool
        """
        super().__init__(
            isolation_level=isolation_level,
            file_system_root=file_system_root,
            workspace_path=workspace_path,
        )

        # 初始化风险分类器
        self._risk_classifier = CommandRiskClassifier(
            isolation_level=isolation_level.value,
            user_permission_level=user_permission_level,
        )

        # 初始化渐进式扩展器
        self._tool_expander: ProgressiveToolExpander | None = None
        if enable_progressive_expansion:
            self._tool_expander = ProgressiveToolExpander()

        # 初始化单用途工具工厂
        self._tool_factory: SinglePurposeToolFactory | None = None
        if enable_single_purpose_tools:
            self._tool_factory = SinglePurposeToolFactory(
                allow_risky_tools=allow_risky_tools,
                allow_dangerous_tools=allow_dangerous_tools,
            )

        # 用户确认回调
        self._user_confirmation_callback = user_confirmation_callback

        # 权限配置
        self._user_permission_level = user_permission_level
        self._allow_risky_tools = allow_risky_tools
        self._allow_dangerous_tools = allow_dangerous_tools

        # 执行历史
        self._secure_execution_history: list[SecureExecutionResult] = []
        self._max_history_size = 1000

        logger.info(
            f"SecureSandbox initialized: "
            f"isolation={isolation_level.value}, "
            f"user_level={user_permission_level}, "
            f"progressive={enable_progressive_expansion}, "
            f"single_purpose={enable_single_purpose_tools}"
        )

    async def execute_tools_secure(
        self,
        tool_calls: list[dict],
        context: dict[str, Any] | None = None,
    ) -> list[SecureExecutionResult]:
        """带风险分类的工具执行

        Args:
            tool_calls: 工具调用列表
            context: 执行上下文（用于渐进式扩展）

        Returns:
            安全执行结果列表
        """
        results: list[SecureExecutionResult] = []

        for tc in tool_calls:
            result = await execute_single_tool_secure(
                tc,
                context,
                self._risk_classifier,
                self._tool_expander,
                self._tool_factory,
                self._tools,
                self._user_confirmation_callback,
                self._user_permission_level,
                self._record_execution,
            )
            results.append(result)

        return results

    def _record_execution(self, result: SecureExecutionResult) -> None:
        """记录执行历史"""
        self._secure_execution_history.append(result)

        # 限制历史大小
        if len(self._secure_execution_history) > self._max_history_size:
            self._secure_execution_history = self._secure_execution_history[
                -self._max_history_size :
            ]

    # === 公共 API ===

    def get_available_tools_secure(
        self, context: dict[str, Any] | None = None
    ) -> set[str]:
        """获取可用工具集（考虑渐进式扩展）"""
        if self._tool_expander and context:
            return self._tool_expander.get_available_tools(context)

        # 默认返回 Tier 1 工具集
        return TOOL_TIER_CONFIGS[ToolTier.TIER_1_BASIC].tools

    def get_current_tool_tier(self) -> ToolTier | None:
        """获取当前工具层级"""
        if self._tool_expander:
            return self._tool_expander.get_current_tier()
        return None

    def get_risk_classification_stats(self) -> dict[str, Any]:
        """获取风险分类统计"""
        return self._risk_classifier.get_classification_stats()

    def get_tool_expansion_stats(self) -> dict[str, Any] | None:
        """获取工具扩展统计"""
        if self._tool_expander:
            return self._tool_expander.get_expansion_stats()
        return None

    def get_secure_execution_stats(self) -> dict[str, Any]:
        """获取安全执行统计"""
        stats: dict[str, Any] = {
            "total_executions": len(self._secure_execution_history),
            "successful": sum(1 for r in self._secure_execution_history if r.success),
            "blocked": sum(1 for r in self._secure_execution_history if r.blocked),
            "cancelled": sum(
                1 for r in self._secure_execution_history if r.user_confirmed is False
            ),
            "by_risk_level": {},
            "average_duration_ms": 0.0,
        }

        # 按风险等级统计
        for level in RiskLevel:
            stats["by_risk_level"][level.value] = sum(
                1 for r in self._secure_execution_history if r.risk_level == level
            )

        # 平均执行时间
        durations = [r.duration_ms for r in self._secure_execution_history]
        if durations:
            stats["average_duration_ms"] = sum(durations) / len(durations)

        return stats

    def get_recent_executions(self, limit: int = 10) -> list[SecureExecutionResult]:
        """获取最近的执行记录"""
        return self._secure_execution_history[-limit:]

    def force_expand_to_tier(self, tier: ToolTier, reason: str = "manual") -> set[str]:
        """强制扩展到指定工具层级"""
        if self._tool_expander:
            return self._tool_expander.force_expand_to_tier(tier, reason)
        return set()

    def reset_tool_tier(self) -> None:
        """重置工具层级到初始状态"""
        if self._tool_expander:
            self._tool_expander.reset_to_initial()

    def set_user_permission_level(self, level: str) -> None:
        """设置用户权限等级"""
        self._user_permission_level = level
        self._risk_classifier.update_user_level(level)
        logger.info(f"User permission level set to: {level}")

    def set_user_confirmation_callback(
        self,
        callback: Callable[[str, str, dict[str, Any]], bool],
    ) -> None:
        """设置用户确认回调"""
        self._user_confirmation_callback = callback

    def set_allow_risky_tools(self, allow: bool) -> None:
        """设置是否允许 risky 工具"""
        self._allow_risky_tools = allow
        if self._tool_factory:
            self._tool_factory.set_allow_risky_tools(allow)
        logger.info(f"Allow risky tools set to: {allow}")

    def set_allow_dangerous_tools(self, allow: bool) -> None:
        """设置是否允许 dangerous 工具"""
        self._allow_dangerous_tools = allow
        if self._tool_factory:
            self._tool_factory.set_allow_dangerous_tools(allow)
        logger.info(f"Allow dangerous tools set to: {allow}")

    def classify_tool_risk(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> ClassificationResult:
        """分类工具风险（不执行）"""
        return self._risk_classifier.classify(tool_name, args)

    def get_single_purpose_tool_schema(self, tool_name: str) -> dict[str, Any] | None:
        """获取单用途工具 schema"""
        if self._tool_factory:
            try:
                return self._tool_factory.get_tool_schema(tool_name)
            except ValueError:
                return None
        return None

    def get_all_single_purpose_tool_schemas(self) -> list[dict[str, Any]]:
        """获取所有单用途工具 schema"""
        if self._tool_factory:
            return self._tool_factory.get_all_tool_schemas()
        return []

    def get_status_secure(self) -> dict[str, Any]:
        """获取安全沙盒完整状态"""
        base_status = self.get_status()

        secure_status: dict[str, Any] = {
            **base_status,
            "user_permission_level": self._user_permission_level,
            "allow_risky_tools": self._allow_risky_tools,
            "allow_dangerous_tools": self._allow_dangerous_tools,
            "progressive_expansion_enabled": self._tool_expander is not None,
            "single_purpose_tools_enabled": self._tool_factory is not None,
        }

        if self._tool_expander:
            secure_status["tool_tier"] = self._tool_expander.get_current_tier().value
            secure_status["available_tools_count"] = len(
                TOOL_TIER_CONFIGS[self._tool_expander.get_current_tier()].tools
            )

        return secure_status

    def clear_history(self) -> None:
        """清空所有历史记录"""
        self._secure_execution_history.clear()
        self._risk_classifier.clear_history()
        logger.info("Secure execution history cleared")