"""命令钩子执行逻辑"""

import asyncio
import logging
import os
import shlex

from ._command_types import CommandHookConfig, CommandHookResult

logger = logging.getLogger("seed_agent")

# 默认命令白名单
DEFAULT_ALLOWED_COMMANDS = [
    "pytest", "ruff", "black", "mypy", "eslint", "npm", "git", "python", "pip",
]


def check_command_allowed(command: str, allowed_commands: list[str], enable_whitelist: bool) -> bool:
    """检查命令是否在白名单中"""
    if not enable_whitelist:
        return True
    cmd_name = shlex.split(command)[0] if command else ""
    return cmd_name in allowed_commands


async def execute_command(
    cmd: str,
    timeout: float,
    work_dir: str | None,
    extra_env: dict[str, str],
    use_shell: bool,
    capture: bool,
) -> CommandHookResult:
    """执行命令"""
    if not cmd:
        return CommandHookResult(success=False, error="Empty command")

    start_time = asyncio.get_event_loop().time()

    try:
        process_env = os.environ.copy()
        process_env.update(extra_env)

        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE if capture else None,
            stderr=asyncio.subprocess.PIPE if capture else None,
            cwd=work_dir,
            env=process_env,
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            return CommandHookResult(success=False, exit_code=-1, duration_ms=duration_ms, error=f"Timeout after {timeout}s")

        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        exit_code = process.returncode or 0
        stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

        return CommandHookResult(
            success=exit_code == 0,
            exit_code=exit_code,
            stdout=stdout_str,
            stderr=stderr_str,
            duration_ms=duration_ms,
        )

    except Exception as e:
        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        return CommandHookResult(success=False, exit_code=-1, duration_ms=duration_ms, error=f"{type(e).__name__}: {str(e)[:200]}")


__all__ = ["DEFAULT_ALLOWED_COMMANDS", "check_command_allowed", "execute_command"]