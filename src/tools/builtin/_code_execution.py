"""
代码执行工具

基于 qwen-code Execute kind 设计：
- 多语言支持: Python, JavaScript, Shell, PowerShell
- 安全黑名单检查
- 同步/异步执行

安全特性：
- 命令黑名单检测
- base64 编码绕过检测
- 环境变量注入防护
"""

import asyncio
import logging
import re
import subprocess
from pathlib import Path

from ._path_validation import DEFAULT_WORK_DIR, PROJECT_ROOT

logger = logging.getLogger("seed_agent.code_exec")

# 安全配置
try:
    from src.shared_config import get_code_execution_security_config

    _security_config = get_code_execution_security_config()
    SHELL_BLACKLIST = _security_config.shell_blacklist
    POWERSHELL_BLACKLIST = _security_config.powershell_blacklist
    MAX_CODE_LENGTH = _security_config.max_code_length
    DEFAULT_EXECUTION_TIMEOUT = _security_config.default_timeout
except ImportError:
    SHELL_BLACKLIST = [
        "rm -rf", "rm -r", "rmdir", "del ", "format", "sudo", "su",
        "chmod 777", "chown", "wget", "curl -o", "nc ", "netcat",
        "kill -9", "pkill", "killall", "; rm", "| rm", "& rm",
        "`rm", "$(rm", "cat /etc/passwd", "cat /etc/shadow",
    ]
    POWERSHELL_BLACKLIST = [
        "Remove-Item", "Delete-Item", "Format-Volume",
        "Set-ExecutionPolicy", "Start-Process -Verb RunAs",
        "Download-File", "Invoke-WebRequest -OutFile",
        "Stop-Process -Force", "Kill-Process",
    ]
    MAX_CODE_LENGTH = 10000
    DEFAULT_EXECUTION_TIMEOUT = 60

# 语言映射
LANGUAGE_MAP = {
    "python": (["python", "-c"], "py"),
    "javascript": (["node", "-e"], "js"),
    "shell": (["bash", "-c"], "sh"),
    "powershell": (["powershell", "-Command"], "ps"),
}

# 预编译正则
_RE_ESCAPE_BACKSLASH = re.compile(r"\\([a-zA-Z])")
_RE_IFS_VAR = re.compile(r"\$\{?IFS\}?")
_RE_QUOTED_VAR = re.compile(r"\$'[a-zA-Z]+'")
_RE_WHITESPACE = re.compile(r"\s+")
_RE_QUOTES = re.compile(r'["\']')
_RE_BASE64_DECODE = re.compile(r"base64\s*(-d|--decode)")
_RE_PWSH_ENCODED = re.compile(r"-enc|-encodedcommand")
_RE_HEX_ESCAPE = re.compile(r"\\x[0-9a-fA-F]{2}")
_RE_OCTAL_ESCAPE = re.compile(r"\\[0-7]{3}")
_RE_ENV_VAR = re.compile(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?")


def _check_code_security(code: str, language: str) -> str | None:
    """Check code against security blacklists. Returns error message if blocked."""
    code_lower = code.lower()

    # 预处理
    normalized_code = _RE_ESCAPE_BACKSLASH.sub(r"\1", code_lower)
    normalized_code = _RE_IFS_VAR.sub("", normalized_code)
    normalized_code = _RE_QUOTED_VAR.sub("", normalized_code)
    normalized_code = _RE_WHITESPACE.sub(" ", normalized_code)
    normalized_code = _RE_QUOTES.sub("", normalized_code)

    # 十六进制转义检测
    if _RE_HEX_ESCAPE.search(code):
        hex_decoded = _RE_HEX_ESCAPE.sub(
            lambda m: chr(int(m.group(0)[2:], 16)), code
        )
        if ".." in hex_decoded or any(d.lower() in hex_decoded.lower() for d in SHELL_BLACKLIST[:5]):
            return "Error: Blocked hex escape sequence."

    # 八进制转义检测
    if _RE_OCTAL_ESCAPE.search(code):
        oct_decoded = _RE_OCTAL_ESCAPE.sub(
            lambda m: chr(int(m.group(0)[1:], 8)), code
        )
        if ".." in oct_decoded or any(d.lower() in oct_decoded.lower() for d in SHELL_BLACKLIST[:5]):
            return "Error: Blocked octal escape sequence."

    if language in ("shell", "bash", "sh"):
        for danger in SHELL_BLACKLIST:
            if danger.lower() in code_lower or danger.lower() in normalized_code:
                return f"Error: Blocked dangerous command: '{danger}'"
        if _RE_BASE64_DECODE.search(normalized_code):
            return "Error: Blocked base64 decode pattern."
        env_matches = _RE_ENV_VAR.findall(normalized_code)
        dangerous_env_vars = ["PATH", "HOME", "USER", "SHELL", "IFS", "LD_PRELOAD", "LD_LIBRARY_PATH"]
        for env_var in env_matches:
            env_name = env_var.replace("${", "").replace("}", "").replace("$", "")
            if env_name in dangerous_env_vars:
                return f"Error: Blocked dangerous environment variable: '{env_name}'"

    elif language in ("powershell", "ps", "pwsh"):
        for danger in POWERSHELL_BLACKLIST:
            if danger.lower() in code_lower or danger.lower() in normalized_code:
                return f"Error: Blocked dangerous command: '{danger}'"
        if _RE_PWSH_ENCODED.search(normalized_code):
            return "Error: Blocked PowerShell encoded command."

    return None


def _resolve_execution_cwd(cwd: str | None) -> str:
    """解析代码执行的工作目录"""
    if cwd is None:
        return str(DEFAULT_WORK_DIR)
    if Path(cwd).is_absolute():
        return cwd
    seed_cwd = DEFAULT_WORK_DIR / cwd
    if seed_cwd.exists():
        return str(seed_cwd)
    return str(PROJECT_ROOT / cwd)


def _build_command(code: str, language: str) -> list[str] | None:
    """Build subprocess command for given language."""
    for lang_prefix, (cmd_prefix, alias) in LANGUAGE_MAP.items():
        if language in (lang_prefix, alias):
            return [*cmd_prefix, code]
    if language in ("js", "node"):
        return ["node", "-e", code]
    return None


def _format_execution_result(result: subprocess.CompletedProcess[str], language: str) -> str:
    """格式化子进程输出"""
    output = result.stdout
    if result.stderr:
        output += "\n[Stderr]\n" + result.stderr
    if result.returncode != 0:
        output += f"\n[Exit Code: {result.returncode}]"
    return output if output.strip() else f"Code executed successfully ({language})"


def code_as_policy(
    code: str, language: str = "python", cwd: str | None = None, timeout: int = 60
) -> str:
    """
    Execute code in various languages (python, js, shell, powershell).

    Args:
        code: Code string to execute.
        language: Language type.
        cwd: Working directory.
        timeout: Execution timeout in seconds.

    Returns:
        Execution output or error message.
    """
    from .utils import safe_int_convert

    try:
        if len(code) > MAX_CODE_LENGTH:
            return f"Error: Code exceeds maximum length ({MAX_CODE_LENGTH} chars)"

        timeout = safe_int_convert(timeout, default=DEFAULT_EXECUTION_TIMEOUT, min_val=1)
        cwd = _resolve_execution_cwd(cwd)
        language = language.lower()

        error = _check_code_security(code, language)
        if error:
            return error

        logger.info(f"Code execution: language={language}, cwd={cwd}, timeout={timeout}s")

        cmd = _build_command(code, language)
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
        return _format_execution_result(result, language)

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
    """
    Async version of code_as_policy - non-blocking for event loop.

    Args:
        code: Code string to execute.
        language: Language type.
        cwd: Working directory.
        timeout: Execution timeout in seconds.

    Returns:
        Execution output or error message.
    """
    from .utils import safe_int_convert

    try:
        if len(code) > MAX_CODE_LENGTH:
            return f"Error: Code exceeds maximum length ({MAX_CODE_LENGTH} chars)"

        timeout = safe_int_convert(timeout, default=DEFAULT_EXECUTION_TIMEOUT, min_val=1)
        cwd = _resolve_execution_cwd(cwd)
        language = language.lower()

        error = _check_code_security(code, language)
        if error:
            return error

        cmd = _build_command(code, language)
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
        return f"Error: Permission denied"
    except Exception as e:
        return f"Error executing code: {type(e).__name__}: {str(e)[:100]}"