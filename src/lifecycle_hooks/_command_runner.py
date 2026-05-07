"""命令钩子执行器 (Wiki 知识落地 - Qwen-Code)

拆分架构:
- _command_types.py: 类型定义
- _command_executor.py: 执行逻辑
"""

import logging
from typing import Any

from ._command_executor import (
    DEFAULT_ALLOWED_COMMANDS,
    check_command_allowed,
    execute_command,
)
from ._command_types import CommandHookConfig, CommandHookResult

logger = logging.getLogger("seed_agent")


class CommandHookRunner:
    """命令钩子执行器"""

    def __init__(
        self,
        allowed_commands: list[str] | None = None,
        default_timeout: float = 30.0,
        enable_whitelist: bool = False,
    ):
        self._allowed_commands = allowed_commands or DEFAULT_ALLOWED_COMMANDS
        self._default_timeout = default_timeout
        self._enable_whitelist = enable_whitelist
        self._total_executions = 0
        self._successful_executions = 0
        self._failed_executions = 0

    async def execute(
        self,
        config: CommandHookConfig | None = None,
        command: str | None = None,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> CommandHookResult:
        """执行命令钩子"""
        if config:
            cmd, t, work_dir, extra_env, use_shell, capture = (
                config.command, config.timeout, config.cwd, config.env, config.shell, config.capture_output
            )
        else:
            cmd = command or ""
            t = timeout or self._default_timeout
            work_dir, extra_env, use_shell, capture = cwd, env or {}, False, True

        if not cmd:
            return CommandHookResult(success=False, error="Empty command")

        if not check_command_allowed(cmd, self._allowed_commands, self._enable_whitelist):
            return CommandHookResult(success=False, error=f"Command not allowed: {cmd}")

        self._total_executions += 1
        result = await execute_command(cmd, t, work_dir, extra_env, use_shell, capture)

        if result.success:
            self._successful_executions += 1
            logger.debug(f"Command hook success: {cmd[:50]}...")
        else:
            self._failed_executions += 1
            logger.warning(f"Command hook failed: {cmd[:50]}...")

        return result

    def get_stats(self) -> dict[str, Any]:
        """获取执行统计"""
        return {
            "total_executions": self._total_executions,
            "successful_executions": self._successful_executions,
            "failed_executions": self._failed_executions,
            "success_rate": self._successful_executions / self._total_executions if self._total_executions > 0 else 0.0,
        }


__all__ = ["CommandHookConfig", "CommandHookResult", "CommandHookRunner"]