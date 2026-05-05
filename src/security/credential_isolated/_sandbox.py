"""
凭证隔离沙盒 - 主类

基于 Harness Engineering "凭证永不进沙盒" 设计理念：
- Sandbox 内的代码无法访问凭证
- 禁止访问环境变量中的 API Key
- 进程级隔离执行（无凭证环境）
- 容器级隔离执行（不传递环境变量）

核心特性:
- 环境变量过滤（移除敏感环境变量）
- 进程级隔离（隔离环境执行）
- 容器级隔离（无凭证环境）
- 凭证代理集成（通过代理访问凭证）

参考来源: Harness Engineering "凭证永不进沙盒"
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from src.sandbox import IsolationLevel
from src.security.credential_isolated._environment import (
    create_isolated_environment,
    detect_credential_access_attempt,
)
from src.security.credential_isolated._execution import execute_isolated
from src.security.credential_isolated._proxy import CredentialProxyManager
from src.security.credential_isolated._sanitize import sanitize_output
from src.security.credential_isolated._types import DEFAULT_BLOCKED_ENV_VARS
from src.security.credential_proxy import CredentialProxy
from src.security.secure_sandbox import SecureExecutionResult, SecureSandbox
from src.tools.utils import is_parse_failed, parse_tool_arguments

logger = logging.getLogger(__name__)


class CredentialIsolatedSandbox(SecureSandbox):
    """凭证隔离的 Sandbox

    Sandbox 内的代码无法访问凭证。

    核心特性:
    - 环境变量过滤：移除所有敏感环境变量
    - 进程级隔离：子进程执行使用无凭证环境
    - 容器级隔离：容器执行不传递任何环境变量
    - 凭证代理集成：通过代理安全访问凭证

    继承 SecureSandbox 的安全特性:
    - 风险分类
    - 渐进式工具扩展
    - 单用途工具

    Example:
        sandbox = CredentialIsolatedSandbox(
            isolation_level=IsolationLevel.PROCESS,
            credential_proxy=proxy
        )

        # Sandbox 代码无法访问凭证
        result = await sandbox.execute_tools_isolated(tool_calls)
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
        credential_proxy: CredentialProxy | None = None,
        blocked_env_vars: list[str] | None = None,
        enforce_credential_isolation: bool = True,
    ):
        """初始化凭证隔离沙盒

        Args:
            isolation_level: 隔离级别
            file_system_root: 沙盒文件系统根目录
            workspace_path: 工作目录映射
            user_permission_level: 用户权限等级
            enable_progressive_expansion: 是否启用渐进式扩展
            enable_single_purpose_tools: 是否启用单用途工具
            allow_risky_tools: 是否允许 risky 级别工具
            allow_dangerous_tools: 是否允许 dangerous 级别工具
            credential_proxy: 凭证代理实例（可选）
            blocked_env_vars: 自定义屏蔽环境变量列表
            enforce_credential_isolation: 是否强制凭证隔离
        """
        super().__init__(
            isolation_level=isolation_level,
            file_system_root=file_system_root,
            workspace_path=workspace_path,
            user_permission_level=user_permission_level,
            enable_progressive_expansion=enable_progressive_expansion,
            enable_single_purpose_tools=enable_single_purpose_tools,
            allow_risky_tools=allow_risky_tools,
            allow_dangerous_tools=allow_dangerous_tools,
        )

        # 凭证代理管理器
        self._proxy_manager = CredentialProxyManager(credential_proxy)

        # 屏蔽的环境变量列表
        self._blocked_env_vars = blocked_env_vars or DEFAULT_BLOCKED_ENV_VARS.copy()

        # 强制凭证隔离
        self._enforce_credential_isolation = enforce_credential_isolation

        # 隔离执行统计
        self._isolated_executions_count = 0
        self._credential_access_attempts = 0

        logger.info(
            f"CredentialIsolatedSandbox initialized: "
            f"isolation={isolation_level.value}, "
            f"blocked_env_vars={len(self._blocked_env_vars)}, "
            f"credential_proxy={credential_proxy is not None}, "
            f"enforce={enforce_credential_isolation}"
        )

    # === 隔离执行 ===

    async def execute_tools_isolated(
        self,
        tool_calls: list[dict],
        context: dict[str, Any] | None = None,
    ) -> list[SecureExecutionResult]:
        """凭证隔离的工具执行

        Args:
            tool_calls: 工具调用列表
            context: 执行上下文

        Returns:
            安全执行结果列表
        """
        results: list[SecureExecutionResult] = []

        for tc in tool_calls:
            result = await self._execute_single_tool_isolated(tc, context)
            results.append(result)

        self._isolated_executions_count += len(tool_calls)
        return results

    async def _execute_single_tool_isolated(
        self,
        tool_call: dict,
        context: dict[str, Any] | None = None,
    ) -> SecureExecutionResult:
        """执行单个工具（凭证隔离）"""
        tool_call_id = tool_call.get("id", "unknown")
        func_data = tool_call.get("function", {})
        tool_name = func_data.get("name", "unknown")
        raw_args = func_data.get("arguments", "{}")

        # 使用统一函数解析参数
        tool_args = parse_tool_arguments(raw_args)
        if is_parse_failed(tool_args):
            return SecureExecutionResult(
                tool_call_id=tool_call_id,
                content="Error: Failed to parse arguments: invalid JSON",
                success=False,
                duration_ms=0.0,
            )

        start_time = time.time()

        # 风险分类（继承自 SecureSandbox）
        classification = self._risk_classifier.classify(tool_name, tool_args)

        # 根据风险等级处理
        if classification.action == "block":
            return SecureExecutionResult(
                tool_call_id=tool_call_id,
                content=f"[BLOCKED] Tool '{tool_name}' blocked (risk: {classification.risk_level})",
                success=False,
                risk_level=classification.risk_level,
                action_taken=classification.action,
                blocked=True,
                duration_ms=(time.time() - start_time) * 1000,
            )

        # 凭证隔离执行
        try:
            result_content = await execute_isolated(
                tool_name=tool_name,
                args=tool_args,
                workspace_path=str(self._workspace_path),
                fs_root=str(self._fs_root),
                isolation_level=self.isolation_level,
                blocked_env_vars=self._blocked_env_vars,
                enforce_credential_isolation=self._enforce_credential_isolation,
                timeout=30.0,
            )

            duration_ms = (time.time() - start_time) * 1000

            return SecureExecutionResult(
                tool_call_id=tool_call_id,
                content=result_content,
                success=True,
                risk_level=classification.risk_level,
                action_taken=classification.action,
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = f"Error: {type(e).__name__}: {str(e)[:200]}"

            return SecureExecutionResult(
                tool_call_id=tool_call_id,
                content=error_msg,
                success=False,
                risk_level=classification.risk_level,
                action_taken=classification.action,
                duration_ms=duration_ms,
            )

    # === 凭证代理集成 ===

    async def get_credential_via_proxy(
        self,
        provider: str,
        credential_type: str,
        scope: str = "api_call",
        requester_id: str | None = None,
    ) -> str | None:
        """通过代理获取凭证"""
        return await self._proxy_manager.get_credential(
            provider, credential_type, scope, requester_id
        )

    async def execute_external_request_via_proxy(
        self,
        provider: str,
        credential_type: str,
        request_func: Any,
        request_context: dict[str, Any],
        requester_id: str | None = None,
    ) -> dict[str, Any]:
        """通过代理执行外部请求"""
        return await self._proxy_manager.execute_request(
            provider, credential_type, request_func, request_context, requester_id
        )

    # === 状态管理 ===

    def set_credential_proxy(self, proxy: CredentialProxy) -> None:
        """设置凭证代理"""
        self._proxy_manager.set_proxy(proxy)

    def add_blocked_env_var(self, var_name: str) -> None:
        """添加屏蔽的环境变量"""
        if var_name not in self._blocked_env_vars:
            self._blocked_env_vars.append(var_name)
            logger.info(f"Added blocked environment variable: {var_name}")

    def remove_blocked_env_var(self, var_name: str) -> None:
        """移除屏蔽的环境变量"""
        if var_name in self._blocked_env_vars:
            self._blocked_env_vars.remove(var_name)
            logger.info(f"Removed blocked environment variable: {var_name}")

    def get_blocked_env_vars(self) -> list[str]:
        """获取屏蔽的环境变量列表"""
        return self._blocked_env_vars.copy()

    def get_isolation_stats(self) -> dict[str, Any]:
        """获取隔离统计信息"""
        base_stats = self.get_secure_execution_stats()

        return {
            **base_stats,
            "credential_isolation": {
                "enforced": self._enforce_credential_isolation,
                "blocked_env_vars_count": len(self._blocked_env_vars),
                "isolated_executions_count": self._isolated_executions_count,
                "credential_access_attempts_blocked": self._credential_access_attempts,
                "credential_proxy_enabled": self._proxy_manager.is_enabled(),
            },
        }

    def get_status_isolated(self) -> dict[str, Any]:
        """获取凭证隔离沙盒完整状态"""
        base_status = self.get_status_secure()

        return {
            **base_status,
            "credential_isolation": {
                "enforced": self._enforce_credential_isolation,
                "blocked_env_vars": len(self._blocked_env_vars),
                "isolated_executions": self._isolated_executions_count,
                "credential_attempts_blocked": self._credential_access_attempts,
            },
        }

    # === 验证方法 ===

    async def verify_credential_isolation(self) -> dict[str, Any]:
        """验证凭证隔离是否有效"""
        test_code = "import os; print(os.environ.get('OPENAI_API_KEY', 'NOT_FOUND'))"

        try:
            isolated_env = create_isolated_environment(self._blocked_env_vars)
            proc = await asyncio.create_subprocess_exec(
                "python",
                "-c",
                test_code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=isolated_env,
            )

            stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            result = stdout.decode().strip()

            is_isolated = result in {"NOT_FOUND", "None"} or not result

            return {
                "isolation_verified": is_isolated,
                "test_result": result if is_isolated else "[CONTAINS_CREDENTIAL]",
                "blocked_vars_count": len(self._blocked_env_vars),
            }

        except Exception as e:
            return {
                "isolation_verified": False,
                "error": str(e),
            }

    # === 向后兼容别名（内部方法已移动到独立模块） ===

    def _create_isolated_environment(self) -> dict[str, str]:
        """向后兼容别名：创建隔离环境"""
        return create_isolated_environment(self._blocked_env_vars)

    def _detect_credential_access_attempt(self, content: str) -> bool:
        """向后兼容别名：检测凭证访问尝试"""
        return detect_credential_access_attempt(content, enforce=self._enforce_credential_isolation)

    def _sanitize_output(self, output: str) -> str:
        """向后兼容别名：过滤输出"""
        return sanitize_output(output)