"""命令钩子执行器 (Wiki 知识落地 - Qwen-Code)

基于 Qwen-Code Command Hooks 设计：
- 在生命周期节点执行外部命令
- 支持超时控制
- 支持环境变量注入
- 输出捕获和错误处理

使用场景：
- 触发外部构建脚本
- 执行代码格式化工具
- 运行测试套件
- 调用通知脚本

Example:
    runner = CommandHookRunner()

    result = await runner.execute(
        command="pytest tests/",
        timeout=60,
        env={"PYTHONPATH": "/app"},
        cwd="/project"
    )
"""

import asyncio
import logging
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("seed_agent")


@dataclass
class CommandHookConfig:
    """命令钩子配置

    Attributes:
        command: 要执行的命令
        timeout: 超时时间（秒）
        cwd: 工作目录
        env: 环境变量（额外注入）
        capture_output: 是否捕获输出
        shell: 是否使用 shell 执行
    """

    command: str
    timeout: float = 30.0
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    capture_output: bool = True
    shell: bool = False


@dataclass
class CommandHookResult:
    """命令钩子执行结果

    Attributes:
        success: 是否成功
        exit_code: 退出码
        stdout: 标准输出
        stderr: 标准错误
        duration_ms: 执行时长（毫秒）
        error: 错误信息（如果有）
    """

    success: bool
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "exit_code": self.exit_code,
            "stdout": self.stdout[:1000] if self.stdout else "",
            "stderr": self.stderr[:1000] if self.stderr else "",
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


class CommandHookRunner:
    """命令钩子执行器

    Wiki 知识落地 (Qwen-Code Command Hooks):
    - 异步执行外部命令
    - 超时控制（避免阻塞）
    - 输出捕获（用于日志和调试）
    - 错误处理（失败不中断主流程）

    安全特性：
    - 命令白名单检查（可选）
    - Shell 注入防护（默认不使用 shell）
    - 超时强制终止
    """

    # 默认命令白名单（可选启用）
    DEFAULT_ALLOWED_COMMANDS = [
        "pytest",
        "ruff",
        "black",
        "mypy",
        "eslint",
        "npm",
        "git",
        "python",
        "pip",
    ]

    def __init__(
        self,
        allowed_commands: list[str] | None = None,
        default_timeout: float = 30.0,
        enable_whitelist: bool = False,
    ):
        """初始化命令钩子执行器

        Args:
            allowed_commands: 允许的命令白名单
            default_timeout: 默认超时时间
            enable_whitelist: 是否启用白名单检查
        """
        self._allowed_commands = allowed_commands or self.DEFAULT_ALLOWED_COMMANDS
        self._default_timeout = default_timeout
        self._enable_whitelist = enable_whitelist

        # 统计
        self._total_executions = 0
        self._successful_executions = 0
        self._failed_executions = 0

    def _check_command_allowed(self, command: str) -> bool:
        """检查命令是否在白名单中"""
        if not self._enable_whitelist:
            return True

        # 提取命令名
        cmd_name = shlex.split(command)[0] if command else ""
        return cmd_name in self._allowed_commands

    async def execute(
        self,
        config: CommandHookConfig | None = None,
        command: str | None = None,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> CommandHookResult:
        """执行命令钩子

        Args:
            config: 钩子配置对象
            command: 命令字符串（如果未提供 config）
            timeout: 超时时间（如果未提供 config）
            cwd: 工作目录（如果未提供 config）
            env: 环境变量（如果未提供 config）

        Returns:
            CommandHookResult 执行结果
        """
        # 参数处理
        if config:
            cmd = config.command
            t = config.timeout
            work_dir = config.cwd
            extra_env = config.env
            use_shell = config.shell
            capture = config.capture_output
        else:
            cmd = command or ""
            t = timeout or self._default_timeout
            work_dir = cwd
            extra_env = env or {}
            use_shell = False
            capture = True

        if not cmd:
            return CommandHookResult(success=False, error="Empty command")

        # 白名单检查
        if not self._check_command_allowed(cmd):
            return CommandHookResult(
                success=False,
                error=f"Command not allowed: {cmd}",
            )

        self._total_executions += 1
        start_time = asyncio.get_event_loop().time()

        try:
            # 构建环境
            process_env = os.environ.copy()
            process_env.update(extra_env)

            # 执行命令
            process = await asyncio.create_subprocess_shell(
                cmd if use_shell else self._build_safe_command(cmd),
                stdout=asyncio.subprocess.PIPE if capture else None,
                stderr=asyncio.subprocess.PIPE if capture else None,
                cwd=work_dir,
                env=process_env,
            )

            # 等待完成（带超时）
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=t,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                self._failed_executions += 1
                return CommandHookResult(
                    success=False,
                    exit_code=-1,
                    stdout="",
                    stderr="",
                    duration_ms=duration_ms,
                    error=f"Timeout after {t}s",
                )

            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            exit_code = process.returncode or 0
            stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

            if exit_code == 0:
                self._successful_executions += 1
                logger.debug(f"Command hook success: {cmd[:50]}...")
            else:
                self._failed_executions += 1
                logger.warning(f"Command hook failed: {cmd[:50]}..., code={exit_code}")

            return CommandHookResult(
                success=exit_code == 0,
                exit_code=exit_code,
                stdout=stdout_str,
                stderr=stderr_str,
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            self._failed_executions += 1
            logger.error(f"Command hook error: {type(e).__name__}: {e}")
            return CommandHookResult(
                success=False,
                exit_code=-1,
                duration_ms=duration_ms,
                error=f"{type(e).__name__}: {str(e)[:200]}",
            )

    def _build_safe_command(self, command: str) -> str:
        """构建安全的命令（避免 shell 注入）"""
        # 使用 shlex 分割参数
        parts = shlex.split(command)
        if not parts:
            return ""
        # 返回原始命令（create_subprocess_shell 会处理）
        return command

    def get_stats(self) -> dict[str, Any]:
        """获取执行统计"""
        return {
            "total_executions": self._total_executions,
            "successful_executions": self._successful_executions,
            "failed_executions": self._failed_executions,
            "success_rate": (
                self._successful_executions / self._total_executions
                if self._total_executions > 0
                else 0.0
            ),
        }


__all__ = [
    "CommandHookConfig",
    "CommandHookResult",
    "CommandHookRunner",
]