"""
代码执行安全检查与辅助模块

安全特性：
- 命令黑名单检测
- base64 编码绕过检测
- 环境变量注入防护
"""

import re
import subprocess
from pathlib import Path

from ._path_validation import DEFAULT_WORK_DIR, PROJECT_ROOT

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


def check_code_security(code: str, language: str) -> str | None:
    """检查代码安全性，返回错误消息或 None"""
    code_lower = code.lower()
    normalized = _RE_ESCAPE_BACKSLASH.sub(r"\1", code_lower)
    normalized = _RE_IFS_VAR.sub("", normalized)
    normalized = _RE_QUOTED_VAR.sub("", normalized)
    normalized = _RE_WHITESPACE.sub(" ", normalized)
    normalized = _RE_QUOTES.sub("", normalized)

    # 十六进制转义检测
    if _RE_HEX_ESCAPE.search(code):
        decoded = _RE_HEX_ESCAPE.sub(lambda m: chr(int(m.group(0)[2:], 16)), code)
        dangerous = SHELL_BLACKLIST[:5]
        if ".." in decoded or any(d.lower() in decoded.lower() for d in dangerous):
            return "Error: Blocked hex escape sequence."

    # 八进制转义检测
    if _RE_OCTAL_ESCAPE.search(code):
        decoded = _RE_OCTAL_ESCAPE.sub(lambda m: chr(int(m.group(0)[1:], 8)), code)
        dangerous = SHELL_BLACKLIST[:5]
        if ".." in decoded or any(d.lower() in decoded.lower() for d in dangerous):
            return "Error: Blocked octal escape sequence."

    if language in ("shell", "bash", "sh"):
        for danger in SHELL_BLACKLIST:
            if danger.lower() in code_lower or danger.lower() in normalized:
                return f"Error: Blocked dangerous command: '{danger}'"
        if _RE_BASE64_DECODE.search(normalized):
            return "Error: Blocked base64 decode pattern."
        for env_var in _RE_ENV_VAR.findall(normalized):
            name = env_var.replace("${", "").replace("}", "").replace("$", "")
            if name in ["PATH", "HOME", "USER", "SHELL", "IFS", "LD_PRELOAD", "LD_LIBRARY_PATH"]:
                return f"Error: Blocked dangerous environment variable: '{name}'"

    elif language in ("powershell", "ps", "pwsh"):
        for danger in POWERSHELL_BLACKLIST:
            if danger.lower() in code_lower or danger.lower() in normalized:
                return f"Error: Blocked dangerous command: '{danger}'"
        if _RE_PWSH_ENCODED.search(normalized):
            return "Error: Blocked PowerShell encoded command."

    return None


def resolve_execution_cwd(cwd: str | None) -> str:
    """解析代码执行的工作目录"""
    if cwd is None:
        return str(DEFAULT_WORK_DIR)
    if Path(cwd).is_absolute():
        return cwd
    seed_cwd = DEFAULT_WORK_DIR / cwd
    if seed_cwd.exists():
        return str(seed_cwd)
    return str(PROJECT_ROOT / cwd)


def build_command(code: str, language: str) -> list[str] | None:
    """构建执行命令"""
    for lang_prefix, (cmd_prefix, alias) in LANGUAGE_MAP.items():
        if language in (lang_prefix, alias):
            return [*cmd_prefix, code]
    if language in ("js", "node"):
        return ["node", "-e", code]
    return None


def format_result(result: subprocess.CompletedProcess[str], language: str) -> str:
    """格式化执行结果"""
    output = result.stdout
    if result.stderr:
        output += "\n[Stderr]\n" + result.stderr
    if result.returncode != 0:
        output += f"\n[Exit Code: {result.returncode}]"
    return output if output.strip() else f"Code executed successfully ({language})"


__all__ = [
    "SHELL_BLACKLIST",
    "POWERSHELL_BLACKLIST",
    "MAX_CODE_LENGTH",
    "DEFAULT_EXECUTION_TIMEOUT",
    "LANGUAGE_MAP",
    "check_code_security",
    "resolve_execution_cwd",
    "build_command",
    "format_result",
]