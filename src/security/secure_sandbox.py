"""
安全沙盒 - SecureSandbox

集成风险分类、渐进式扩展、单用途工具的完整安全沙盒

核心特性:
- 基于风险分类的工具执行控制
- 渐进式工具扩展
- 单用途工具替代通用 Shell
- 用户确认机制
- 执行历史追溯

参考来源: Harness Engineering "工具与权限"
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.sandbox import IsolationLevel, Sandbox
from src.security.risk_classifier import (
    ClassificationResult,
    CommandRiskClassifier,
    RiskAction,
    RiskLevel,
)
from src.security.single_purpose_tools import (
    SinglePurposeToolFactory,
)
from src.security.tool_expander import (
    TOOL_TIER_CONFIGS,
    ProgressiveToolExpander,
    ToolTier,
)
from src.tools.utils import is_parse_failed, parse_tool_arguments

logger = logging.getLogger(__name__)


@dataclass
class SecureExecutionResult:
    """安全执行结果"""
    tool_call_id: str
    content: str
    success: bool
    risk_level: RiskLevel | None = None
    action_taken: RiskAction | None = None
    duration_ms: float = 0.0
    blocked: bool = False
    user_confirmed: bool | None = None


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
            result = await self._execute_single_tool_secure(tc, context)
            results.append(result)

        return results

    async def _execute_single_tool_secure(
        self,
        tool_call: dict,
        context: dict[str, Any] | None = None,
    ) -> SecureExecutionResult:
        """执行单个工具（带安全检查）

        流程:
        1. 工具可用性检查（渐进式扩展）
        2. 风险分类
        3. 根据风险等级处理（block/request_confirm/log_and_execute/auto_execute）
        4. 执行工具
        5. 记录结果
        """
        tool_call_id = tool_call.get("id", "unknown")
        func_data = tool_call.get("function", {})
        tool_name = func_data.get("name", "unknown")
        raw_args = func_data.get("arguments", "{}")

        start_time = time.time()

        # 使用统一函数解析参数
        tool_args = parse_tool_arguments(raw_args)
        if is_parse_failed(tool_args):
            return SecureExecutionResult(
                tool_call_id=tool_call_id,
                content="Error: Failed to parse arguments: invalid JSON",
                success=False,
                duration_ms=0.0,
            )

        # 1. 工具可用性检查（渐进式扩展）
        if self._tool_expander and context:
            available_tools = self._tool_expander.get_available_tools(context)
            if tool_name not in available_tools:
                current_tier = self._tool_expander.get_current_tier()
                return SecureExecutionResult(
                    tool_call_id=tool_call_id,
                    content=f"[BLOCKED] Tool '{tool_name}' not available in current tier ({current_tier.value})",
                    success=False,
                    blocked=True,
                    duration_ms=(time.time() - start_time) * 1000,
                )

        # 2. 风险分类
        classification = self._risk_classifier.classify(tool_name, tool_args)

        # 3. 根据风险等级处理
        if classification.action == RiskAction.BLOCK:
            # 直接拦截
            return SecureExecutionResult(
                tool_call_id=tool_call_id,
                content=f"[BLOCKED] Tool '{tool_name}' blocked by security policy (risk: {classification.risk_level.value}, score: {classification.score:.2f})",
                success=False,
                risk_level=classification.risk_level,
                action_taken=classification.action,
                blocked=True,
                duration_ms=(time.time() - start_time) * 1000,
            )

        if classification.action == RiskAction.REQUEST_CONFIRM:
            # 请求用户确认
            confirmed = await self._request_user_approval(
                tool_name, classification.risk_level, tool_args
            )

            if not confirmed:
                return SecureExecutionResult(
                    tool_call_id=tool_call_id,
                    content=f"[CANCELLED] User cancelled '{tool_name}' (risk: {classification.risk_level.value})",
                    success=False,
                    risk_level=classification.risk_level,
                    action_taken=classification.action,
                    user_confirmed=False,
                    duration_ms=(time.time() - start_time) * 1000,
                )

        # 4. 日志记录（caution 级别）
        if classification.action == RiskAction.LOG_AND_EXECUTE:
            logger.warning(
                f"Executing cautious tool: {tool_name} "
                f"(risk: {classification.risk_level.value}, "
                f"score: {classification.score:.2f}, "
                f"factors: {classification.factors})"
            )

        # 5. 执行工具
        try:
            # 优先使用单用途工具
            if self._tool_factory and self._is_single_purpose_tool(tool_name):
                result_content = self._execute_single_purpose_tool(tool_name, tool_args)
            else:
                # 使用标准工具执行
                result_content = await self._execute_standard_tool(tool_name, tool_args)

            duration_ms = (time.time() - start_time) * 1000

            # 记录成功结果
            execution_result = SecureExecutionResult(
                tool_call_id=tool_call_id,
                content=result_content,
                success=True,
                risk_level=classification.risk_level,
                action_taken=classification.action,
                duration_ms=duration_ms,
                user_confirmed=True if classification.action == RiskAction.REQUEST_CONFIRM else None,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = f"Error: {type(e).__name__}: {str(e)[:200]}"

            execution_result = SecureExecutionResult(
                tool_call_id=tool_call_id,
                content=error_msg,
                success=False,
                risk_level=classification.risk_level,
                action_taken=classification.action,
                duration_ms=duration_ms,
            )

        # 6. 记录执行历史
        self._record_execution(execution_result)

        return execution_result

    async def _request_user_approval(
        self,
        tool_name: str,
        risk_level: RiskLevel,
        args: dict[str, Any],
    ) -> bool:
        """请求用户批准

        Args:
            tool_name: 工具名称
            risk_level: 风险等级
            args: 工具参数

        Returns:
            是否批准
        """
        if self._user_confirmation_callback:
            return self._user_confirmation_callback(
                tool_name, risk_level.value, args
            )

        # 默认行为：记录并返回 False（需要外部确认机制）
        logger.warning(
            f"Tool '{tool_name}' requires user confirmation (risk: {risk_level.value}) "
            f"but no callback configured - defaulting to deny"
        )
        return False

    def _is_single_purpose_tool(self, tool_name: str) -> bool:
        """检查是否为单用途工具"""
        if self._tool_factory is None:
            return False

        return self._tool_factory.get_tool_config(tool_name) is not None

    def _execute_single_purpose_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> str:
        """执行单用途工具"""
        if self._tool_factory is None:
            return "[ERROR] Single-purpose tool factory not enabled"

        try:
            tool_func = self._tool_factory.create_tool(tool_name)
            return tool_func(**args)
        except ValueError as e:
            return f"[ERROR] {e}"
        except Exception as e:
            return f"[ERROR] Tool execution failed: {type(e).__name__}: {str(e)[:200]}"

    async def _execute_standard_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> str:
        """执行标准工具（通过 ToolRegistry）"""
        if not self._tools:
            raise RuntimeError("Sandbox has no tools registered")

        result = await self._tools.execute(tool_name, **args)
        return str(result)

    def _record_execution(self, result: SecureExecutionResult) -> None:
        """记录执行历史"""
        self._secure_execution_history.append(result)

        # 限制历史大小
        if len(self._secure_execution_history) > self._max_history_size:
            self._secure_execution_history = self._secure_execution_history[-self._max_history_size:]

    # === 公共 API ===

    def get_available_tools_secure(self, context: dict[str, Any] | None = None) -> set[str]:
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
            "cancelled": sum(1 for r in self._secure_execution_history if r.user_confirmed is False),
            "by_risk_level": {},
            "average_duration_ms": 0.0,
        }

        # 按风险等级统计
        for level in RiskLevel:
            stats["by_risk_level"][level.value] = sum(
                1 for r in self._secure_execution_history
                if r.risk_level == level
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
