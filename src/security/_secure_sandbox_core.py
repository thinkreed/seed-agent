"""安全沙盒核心模块"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.sandbox import IsolationLevel, Sandbox
from src.security._secure_sandbox_execution import execute_single_tool_secure
from src.security._secure_sandbox_types import SecureExecutionResult
from src.security.risk_classifier import ClassificationResult, CommandRiskClassifier, RiskLevel
from src.security.single_purpose_tools import SinglePurposeToolFactory
from src.security.tool_expander import TOOL_TIER_CONFIGS, ProgressiveToolExpander, ToolTier

logger = logging.getLogger(__name__)


class SecureSandbox(Sandbox):
    """带风险分类的安全沙盒"""

    def __init__(self, isolation_level: IsolationLevel = IsolationLevel.PROCESS, file_system_root: Path | None = None,
                 workspace_path: Path | None = None, user_permission_level: str = "normal",
                 enable_progressive_expansion: bool = True, enable_single_purpose_tools: bool = True,
                 allow_risky_tools: bool = True, allow_dangerous_tools: bool = False,
                 user_confirmation_callback: Callable[[str, str, dict], bool] | None = None):
        super().__init__(isolation_level=isolation_level, file_system_root=file_system_root, workspace_path=workspace_path)

        self._risk_classifier = CommandRiskClassifier(isolation_level=isolation_level.value, user_permission_level=user_permission_level)
        self._tool_expander = ProgressiveToolExpander() if enable_progressive_expansion else None
        self._tool_factory = SinglePurposeToolFactory(allow_risky_tools=allow_risky_tools, allow_dangerous_tools=allow_dangerous_tools) if enable_single_purpose_tools else None
        self._user_confirmation_callback = user_confirmation_callback
        self._user_permission_level = user_permission_level
        self._allow_risky_tools = allow_risky_tools
        self._allow_dangerous_tools = allow_dangerous_tools
        self._secure_execution_history: list[SecureExecutionResult] = []
        self._max_history_size = 1000

        logger.info(f"SecureSandbox initialized: isolation={isolation_level.value}")

    async def execute_tools_secure(self, tool_calls: list[dict], context: dict[str, Any] | None = None) -> list[SecureExecutionResult]:
        results = []
        for tc in tool_calls:
            result = await execute_single_tool_secure(tc, context, self._risk_classifier, self._tool_expander,
                self._tool_factory, self._tools, self._user_confirmation_callback, self._user_permission_level, self._record_execution)
            results.append(result)
        return results

    def _record_execution(self, result: SecureExecutionResult) -> None:
        self._secure_execution_history.append(result)
        if len(self._secure_execution_history) > self._max_history_size:
            self._secure_execution_history = self._secure_execution_history[-self._max_history_size:]

    def get_available_tools_secure(self, context: dict[str, Any] | None = None) -> set[str]:
        if self._tool_expander and context:
            return self._tool_expander.get_available_tools(context)
        return TOOL_TIER_CONFIGS[ToolTier.TIER_1_BASIC].tools

    def get_current_tool_tier(self) -> ToolTier | None:
        return self._tool_expander.get_current_tier() if self._tool_expander else None

    def get_risk_classification_stats(self) -> dict[str, Any]:
        return self._risk_classifier.get_classification_stats()

    def get_tool_expansion_stats(self) -> dict[str, Any] | None:
        return self._tool_expander.get_expansion_stats() if self._tool_expander else None

    def get_secure_execution_stats(self) -> dict[str, Any]:
        stats = {"total_executions": len(self._secure_execution_history), "successful": sum(1 for r in self._secure_execution_history if r.success),
                 "blocked": sum(1 for r in self._secure_execution_history if r.blocked), "cancelled": sum(1 for r in self._secure_execution_history if r.user_confirmed is False),
                 "by_risk_level": {}, "average_duration_ms": 0.0}
        for level in RiskLevel:
            stats["by_risk_level"][level.value] = sum(1 for r in self._secure_execution_history if r.risk_level == level)
        durations = [r.duration_ms for r in self._secure_execution_history]
        if durations:
            stats["average_duration_ms"] = sum(durations) / len(durations)
        return stats

    def get_recent_executions(self, limit: int = 10) -> list[SecureExecutionResult]:
        return self._secure_execution_history[-limit:]

    def force_expand_to_tier(self, tier: ToolTier, reason: str = "manual") -> set[str]:
        return self._tool_expander.force_expand_to_tier(tier, reason) if self._tool_expander else set()

    def reset_tool_tier(self) -> None:
        if self._tool_expander:
            self._tool_expander.reset_to_initial()

    def set_user_permission_level(self, level: str) -> None:
        self._user_permission_level = level
        self._risk_classifier.update_user_level(level)
        logger.info(f"User permission level set to: {level}")

    def set_user_confirmation_callback(self, callback: Callable[[str, str, dict[str, Any]], bool]) -> None:
        self._user_confirmation_callback = callback

    def set_allow_risky_tools(self, allow: bool) -> None:
        self._allow_risky_tools = allow
        if self._tool_factory:
            self._tool_factory.set_allow_risky_tools(allow)

    def set_allow_dangerous_tools(self, allow: bool) -> None:
        self._allow_dangerous_tools = allow
        if self._tool_factory:
            self._tool_factory.set_allow_dangerous_tools(allow)

    def classify_tool_risk(self, tool_name: str, args: dict[str, Any]) -> ClassificationResult:
        return self._risk_classifier.classify(tool_name, args)

    def get_single_purpose_tool_schema(self, tool_name: str) -> dict[str, Any] | None:
        if self._tool_factory:
            try:
                return self._tool_factory.get_tool_schema(tool_name)
            except ValueError:
                return None
        return None

    def get_all_single_purpose_tool_schemas(self) -> list[dict[str, Any]]:
        return self._tool_factory.get_all_tool_schemas() if self._tool_factory else []

    def get_status_secure(self) -> dict[str, Any]:
        base_status = self.get_status()
        secure_status = {**base_status, "user_permission_level": self._user_permission_level,
                         "allow_risky_tools": self._allow_risky_tools, "allow_dangerous_tools": self._allow_dangerous_tools,
                         "progressive_expansion_enabled": self._tool_expander is not None,
                         "single_purpose_tools_enabled": self._tool_factory is not None}
        if self._tool_expander:
            secure_status["tool_tier"] = self._tool_expander.get_current_tier().value
            secure_status["available_tools_count"] = len(TOOL_TIER_CONFIGS[self._tool_expander.get_current_tier()].tools)
        return secure_status

    def clear_history(self) -> None:
        self._secure_execution_history.clear()
        self._risk_classifier.clear_history()