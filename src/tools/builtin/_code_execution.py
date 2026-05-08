"""
代码执行工具

支持语言: Python, JavaScript, Shell, PowerShell
执行模式: 同步/异步
"""

import asyncio
import logging
import subprocess

from ._code_execution_security import (
    DEFAULT_EXECUTION_TIMEOUT,
    MAX_CODE_LENGTH,
    POWERSHELL_BLACKLIST,
    SHELL_BLACKLIST,
    build_command,
    check_code_security,
    format_result,
    resolve_execution_cwd,
)

logger = logging.getLogger("seed_agent.code_exec")


def code_as_policy(
    code: str, language: str = "python", cwd: str | None = None, timeout: int = 60
) -> str:
    """Execute code in various languages (python, js, shell, powershell)."""
    from .utils import safe_int_convert

    try:
        if len(code) > MAX_CODE_LENGTH:
            return f"Error: Code exceeds maximum length ({MAX_CODE_LENGTH} chars)"

        timeout = safe_int_convert(timeout, default=DEFAULT_EXECUTION_TIMEOUT, min_val=1)
        cwd = resolve_execution_cwd(cwd)
        language = language.lower()

        error = check_code_security(code, language)
        if error:
            return error

        logger.info(f"Code execution: language={language}, cwd={cwd}, timeout={timeout}s")

        cmd = build_command(code, language)
        if cmd is None:
            return f"Error: Unsupported language '{language}'"

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            encoding="utf-8",
            errors="replace",
        )
        return format_result(result, language)

    except subprocess.TimeoutExpired:
        return f"Error: Execution timed out ({timeout}s)"
    except FileNotFoundError:
        return f"Error: Interpreter not found for '{language}'"
    except PermissionError:
        return f"Error: Permission denied executing '{language}' code"
    except Exception as e:
        return f"Error executing code: {type(e).__name__}: {str(e)[:100]}"


async def code_as_policy_async(
    code: str, language: str = "python", cwd: str | None = None, timeout: int = 60
) -> str:
    """Async version of code_as_policy - non-blocking for event loop."""
    from .utils import safe_int_convert

    try:
        if len(code) > MAX_CODE_LENGTH:
            return f"Error: Code exceeds maximum length ({MAX_CODE_LENGTH} chars)"

        timeout = safe_int_convert(timeout, default=DEFAULT_EXECUTION_TIMEOUT, min_val=1)
        cwd = resolve_execution_cwd(cwd)
        language = language.lower()

        error = check_code_security(code, language)
        if error:
            return error

        cmd = build_command(code, language)
        if cmd is None:
            return f"Error: Unsupported language '{language}'"

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
            return f"Error: Execution timed out ({timeout}s)"

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        output = stdout
        if stderr:
            output += "\n[Stderr]\n" + stderr
        if proc.returncode and proc.returncode != 0:
            output += f"\n[Exit Code: {proc.returncode}]"
        return output if output.strip() else f"Code executed successfully ({language})"

    except FileNotFoundError:
        return f"Error: Interpreter not found for '{language}'"
    except PermissionError:
        return "Error: Permission denied"
    except Exception as e:
        return f"Error executing code: {type(e).__name__}: {str(e)[:100]}"


__all__ = [
    "code_as_policy",
    "code_as_policy_async",
    "SHELL_BLACKLIST",
    "POWERSHELL_BLACKLIST",
    "MAX_CODE_LENGTH",
    "DEFAULT_EXECUTION_TIMEOUT",
]

# 私有别名（供 builtin_tools.py 导入使用）
_check_code_security = check_code_security
_resolve_execution_cwd = resolve_execution_cwd
_build_command = build_command
_format_execution_result = format_result

__all__.extend([
    "_check_code_security",
    "_resolve_execution_cwd",
    "_build_command",
    "_format_execution_result",
])