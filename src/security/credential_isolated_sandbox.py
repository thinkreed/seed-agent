"""
凭证隔离沙盒 - CredentialIsolatedSandbox

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
import os
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

from src.sandbox import IsolationLevel
from src.security.secure_sandbox import SecureSandbox, SecureExecutionResult
from src.security.credential_proxy import CredentialProxy

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# 需要屏蔽的环境变量列表
BLOCKED_ENV_VARS = [
    # API Keys
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "BAILIAN_API_KEY",
    "DEEPSEEK_API_KEY",
    "GEMINI_API_KEY",
    "COHERE_API_KEY",
    "HUGGINGFACE_TOKEN",

    # Cloud Credentials
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "AZURE_SUBSCRIPTION_ID",
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",

    # Database Credentials
    "DATABASE_URL",
    "DB_PASSWORD",
    "MYSQL_PASSWORD",
    "POSTGRES_PASSWORD",
    "MONGODB_PASSWORD",

    # Service Tokens
    "GITHUB_TOKEN",
    "GITLAB_TOKEN",
    "SLACK_TOKEN",
    "DISCORD_TOKEN",
    "TELEGRAM_TOKEN",

    # SSH Keys
    "SSH_PRIVATE_KEY",
    "SSH_AUTH_SOCK",

    # Generic
    "API_KEY",
    "SECRET_KEY",
    "PRIVATE_KEY",
    "PASSWORD",
    "TOKEN",
]


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

        # 尝试访问环境变量会返回空
        # os.environ.get('OPENAI_API_KEY') -> None (在 Sandbox 内)
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

        # 凭证代理
        self._credential_proxy = credential_proxy

        # 屏蔽的环境变量列表
        self._blocked_env_vars = blocked_env_vars or BLOCKED_ENV_VARS.copy()

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
        """执行单个工具（凭证隔离）

        根据隔离级别选择执行方式：
        - PROCESS: 进程级隔离（无凭证环境）
        - CONTAINER: 容器级隔离（无环境变量）
        """
        tool_call_id = tool_call.get("id", "unknown")
        func_data = tool_call.get("function", {})
        tool_name = func_data.get("name", "unknown")
        raw_args = func_data.get("arguments", "{}")

        # 解析参数
        try:
            if isinstance(raw_args, str):
                tool_args = json.loads(raw_args)
            else:
                tool_args = raw_args
        except json.JSONDecodeError as e:
            return SecureExecutionResult(
                tool_call_id=tool_call_id,
                content=f"Error: Failed to parse arguments: {e}",
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
            if self.isolation_level == IsolationLevel.PROCESS:
                result_content = await self._execute_in_isolated_process(
                    tool_name, tool_args
                )
            elif self.isolation_level == IsolationLevel.CONTAINER:
                result_content = await self._execute_in_isolated_container(
                    tool_name, tool_args
                )
            else:
                # 默认进程级隔离
                result_content = await self._execute_in_isolated_process(
                    tool_name, tool_args
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

    async def _execute_in_isolated_process(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> str:
        """进程级隔离执行（无凭证环境）

        创建隔离的子进程环境，移除所有敏感环境变量。

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            执行结果
        """
        # 创建隔离环境（移除敏感环境变量）
        isolated_env = self._create_isolated_environment()

        # 检查是否尝试访问凭证
        args_str = json.dumps(args)
        if self._detect_credential_access_attempt(args_str):
            self._credential_access_attempts += 1
            logger.warning(
                f"Potential credential access attempt detected in tool: {tool_name}"
            )
            return "[BLOCKED] Credential access attempt detected in sandbox"

        # 构建执行命令
        args_json = json.dumps(args)

        # 创建子进程（无凭证环境）
        try:
            proc = await asyncio.create_subprocess_exec(
                "python", "-c",
                f"import json; from src.tools.builtin_tools import {tool_name}; "
                f"result = {tool_name}(**json.loads('{args_json}')); print(result)",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=isolated_env,  # 无凭证环境
                cwd=str(self._workspace_path),
            )

            stdout, stderr = await proc.communicate(timeout=30.0)

            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                # 过滤错误信息中的凭证
                safe_error = self._sanitize_output(error_msg)
                raise RuntimeError(safe_error)

            result = stdout.decode() if stdout else ""
            # 过滤输出中的凭证
            return self._sanitize_output(result)

        except asyncio.TimeoutError:
            raise RuntimeError("Subprocess execution timeout")
        except Exception as e:
            raise RuntimeError(f"Subprocess execution failed: {type(e).__name__}")

    async def _execute_in_isolated_container(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> str:
        """Docker 容器级隔离执行（无凭证）

        创建临时容器执行，不传递任何环境变量。

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            执行结果
        """
        try:
            import docker
        except ImportError:
            logger.warning("Docker not installed, falling back to process isolation")
            return await self._execute_in_isolated_process(tool_name, args)

        client = docker.from_env()

        # 构建执行命令
        args_json = json.dumps(args)
        cmd = f"python -c 'from src.tools.builtin_tools import {tool_name}; print({tool_name}(**json.loads(\"{args_json}\")))'"

        try:
            # 创建临时容器（不传递环境变量）
            container = client.containers.run(
                "seed-agent-sandbox:latest",
                cmd,
                volumes={
                    str(self._workspace_path): {"bind": "/workspace", "mode": "rw"},
                    str(self._fs_root): {"bind": "/sandbox", "mode": "rw"}
                },
                environment={},  # 不传递任何环境变量（关键）
                remove=True,
                stdout=True,
                stderr=True
            )

            result = container.decode() if isinstance(container, bytes) else str(container)
            return self._sanitize_output(result)

        except Exception as e:
            logger.error(f"Container execution failed: {e}")
            # 降级到进程级隔离
            return await self._execute_in_isolated_process(tool_name, args)

    # === 环境隔离 ===

    def _create_isolated_environment(self) -> dict[str, str]:
        """创建隔离的环境变量字典

        移除所有敏感环境变量，确保凭证不暴露。

        Returns:
            无凭证的环境变量字典
        """
        isolated_env = os.environ.copy()

        # 移除敏感环境变量
        for var in self._blocked_env_vars:
            if var in isolated_env:
                logger.debug(f"Blocked environment variable: {var}")
                del isolated_env[var]

        # 模式匹配移除（如 *_KEY, *_TOKEN, *_SECRET）
        patterns = ["_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_PRIVATE"]
        for key in list(isolated_env.keys()):
            for pattern in patterns:
                if key.endswith(pattern) or pattern in key:
                    logger.debug(f"Blocked environment variable (pattern): {key}")
                    del isolated_env[key]
                    break

        return isolated_env

    def _detect_credential_access_attempt(self, content: str) -> bool:
        """检测凭证访问尝试

        检查代码或参数是否包含访问凭证的意图。

        Args:
            content: 要检查的内容

        Returns:
            是否存在凭证访问尝试
        """
        if not self._enforce_credential_isolation:
            return False

        # 检测模式
        credential_patterns = [
            "os.environ",
            "getenv",
            "environ.get",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "BAILIAN_API_KEY",
            "AWS_ACCESS_KEY",
            "GITHUB_TOKEN",
            "api_key",
            "apiKey",
            "API_KEY",
        ]

        for pattern in credential_patterns:
            if pattern.lower() in content.lower():
                return True

        return False

    def _sanitize_output(self, output: str) -> str:
        """过滤输出中的凭证

        移除或替换输出中可能包含的凭证值。

        Args:
            output: 原始输出

        Returns:
            过滤后的输出
        """
        # 过滤 API Key 模式
        import re

        # sk-* 模式 (OpenAI)
        output = re.sub(r'sk-[a-zA-Z0-9]{20,}', '[REDACTED_API_KEY]', output)

        #Bearer * 模式
        output = re.sub(r'Bearer\s+[a-zA-Z0-9_-]{20,}', 'Bearer [REDACTED]', output)

        #AWS Access Key 模式
        output = re.sub(r'AKIA[A-Z0-9]{16}', '[REDACTED_AWS_KEY]', output)

        # 通用 API Key 模式
        output = re.sub(r'api[_-]?key["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{20,}', 'api_key=[REDACTED]', output)

        return output

    # === 凭证代理集成 ===

    async def get_credential_via_proxy(
        self,
        provider: str,
        credential_type: str,
        scope: str = "api_call",
        requester_id: str | None = None,
    ) -> str | None:
        """通过代理获取凭证

        注意：此方法仅供 Sandbox 内部使用，
        凭证不会暴露给执行代码。

        Args:
            provider: 提供商名称
            credential_type: 凭证类型
            scope: 请求作用域
            requester_id: 请求者 ID

        Returns:
            凭证值（内部使用，不暴露给代码）
        """
        if not self._credential_proxy:
            logger.warning("No credential proxy configured")
            return None

        try:
            # 通过 Vault 获取凭证（代理内部）
            return self._credential_proxy._vault.get_credential(
                provider,
                credential_type,
                scope=scope,
                requester_id=requester_id,
            )
        except Exception as e:
            logger.error(f"Failed to get credential via proxy: {e}")
            return None

    async def execute_external_request_via_proxy(
        self,
        provider: str,
        credential_type: str,
        request_func: Any,
        request_context: dict[str, Any],
        requester_id: str | None = None,
    ) -> dict[str, Any]:
        """通过代理执行外部请求

        Sandbox 内代码无法直接访问凭证，
        必须通过代理执行外部 API 请求。

        Args:
            provider: 提供商名称
            credential_type: 凭证类型
            request_func: 请求函数
            request_context: 请求上下文
            requester_id: 请求者 ID

        Returns:
            请求结果
        """
        if not self._credential_proxy:
            return {
                "status": "failed",
                "error": "No credential proxy configured",
            }

        return await self._credential_proxy.execute_external_request(
            provider=provider,
            credential_type=credential_type,
            request_func=request_func,
            request_context=request_context,
            requester_id=requester_id,
        )

    # === 状态管理 ===

    def set_credential_proxy(self, proxy: CredentialProxy) -> None:
        """设置凭证代理"""
        self._credential_proxy = proxy
        logger.info("Credential proxy set for isolated sandbox")

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
                "credential_proxy_enabled": self._credential_proxy is not None,
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
        """验证凭证隔离是否有效

        通过测试代码执行验证环境变量是否被正确屏蔽。

        Returns:
            验证结果
        """
        test_code = "import os; print(os.environ.get('OPENAI_API_KEY', 'NOT_FOUND'))"

        try:
            proc = await asyncio.create_subprocess_exec(
                "python", "-c", test_code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._create_isolated_environment(),
            )

            stdout, stderr = await proc.communicate(timeout=5.0)
            result = stdout.decode().strip()

            # 验证结果
            is_isolated = result == "NOT_FOUND" or result == "None" or not result

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