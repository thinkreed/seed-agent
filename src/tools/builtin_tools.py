"""5个核心内置工具：file_read, file_write, file_edit, code_as_policy, ask_user

性能优化:
- 缓存 ALLOWED_DIRS 解析结果
- 使用 lru_cache 缓存路径验证结果
- 预编译正则表达式

Ask User 机制:
- 真正的等待机制（而非字符串标记）
- 结构化问题定义
- 支持单选、多选、自定义输入
"""

import functools
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

from . import ToolRegistry
from .ask_user_types import (
    AskUserRequest,
    AskUserResult,
    get_ask_user_state,
)

logger = logging.getLogger("seed_agent.path")

# 使用共享配置模块
try:
    from src.shared_config import (
        get_code_execution_security_config,
        get_path_validation_config,
    )

    _path_config = get_path_validation_config()
    _security_config = get_code_execution_security_config()
    PROJECT_ROOT = _path_config.project_root
    DEFAULT_WORK_DIR = _path_config.default_work_dir
    ALLOWED_DIRS_RAW = _path_config.allowed_dirs
    SHELL_BLACKLIST = _security_config.shell_blacklist
    POWERSHELL_BLACKLIST = _security_config.powershell_blacklist
    MAX_CODE_LENGTH = _security_config.max_code_length
    DEFAULT_EXECUTION_TIMEOUT = _security_config.default_timeout
except ImportError:
    # Fallback: 使用默认值
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    DEFAULT_WORK_DIR = Path.home() / ".seed"
    ALLOWED_DIRS_RAW = [
        DEFAULT_WORK_DIR,
        PROJECT_ROOT,
        Path.home() / "Documents",
    ]
    SHELL_BLACKLIST = [
        "rm -rf",
        "rm -r",
        "rmdir",
        "del ",
        "format",
        "sudo",
        "su",
        "chmod 777",
        "chown",
        "wget",
        "curl -o",
        "nc ",
        "netcat",
        "kill -9",
        "pkill",
        "killall",
        "; rm",
        "| rm",
        "& rm",
        "`rm",
        "$(rm",
        "cat /etc/passwd",
        "cat /etc/shadow",
    ]
    POWERSHELL_BLACKLIST = [
        "Remove-Item",
        "Delete-Item",
        "Format-Volume",
        "Set-ExecutionPolicy",
        "Start-Process -Verb RunAs",
        "Download-File",
        "Invoke-WebRequest -OutFile",
        "Stop-Process -Force",
        "Kill-Process",
    ]
    MAX_CODE_LENGTH = 10000
    DEFAULT_EXECUTION_TIMEOUT = 60


# 缓存已解析的 ALLOWED_DIRS（避免每次调用 resolve()）
def _resolve_allowed_dirs() -> list[str]:
    """解析并缓存 ALLOWED_DIRS（模块初始化时调用）"""
    resolved = []
    for allowed in ALLOWED_DIRS_RAW:
        try:
            resolved.append(str(Path(str(allowed)).resolve()))
        except Exception as e:
            logger.debug(f"Failed to resolve allowed dir '{allowed}': {e}")
    return resolved


ALLOWED_DIRS: list[str] = _resolve_allowed_dirs()

# 缓存 DEFAULT_WORK_DIR 和 PROJECT_ROOT 的解析结果
DEFAULT_WORK_DIR_RESOLVED = str(DEFAULT_WORK_DIR.resolve())
PROJECT_ROOT_RESOLVED = str(PROJECT_ROOT.resolve())


# 预编译正则表达式（性能优化）
_RE_WINDOWS_DRIVE = re.compile(r"^[a-zA-Z]:[/\\]")
_RE_DOUBLE_DOT = re.compile(r"\.\.")  # 快速检测 .. 序列

# URL 编码攻击模式（包括双重编码和 UTF-8 过长编码）
_RE_URL_ENCODED = re.compile(r"%[0-9a-fA-F]{2}", re.IGNORECASE)
_RE_DOUBLE_URL_ENCODED = re.compile(r"%25[0-9a-fA-F]{2}", re.IGNORECASE)
# UTF-8 过长编码：\xc0\xae 或 \xe0\x80\xae 等变体表示 '.'
_RE_UTF8_OVERLONG = re.compile(
    r"[\xc0-\xc1][\x80-\xbf]|\xe0\x80[\xae\xaf]|\xed\xa0[\x80-\xbf]"
)

# 代码安全预处理正则
_RE_ESCAPE_BACKSLASH = re.compile(r"\\([a-zA-Z])")
_RE_IFS_VAR = re.compile(r"\$\{?IFS\}?")
_RE_QUOTED_VAR = re.compile(r"\$'[a-zA-Z]+'")
_RE_WHITESPACE = re.compile(r"\s+")
_RE_QUOTES = re.compile(r'["\']')
_RE_BASE64_DECODE = re.compile(r"base64\s*(-d|--decode)")
_RE_PWSH_ENCODED = re.compile(r"-enc|-encodedcommand")
# 额外的危险模式检测
_RE_HEX_ESCAPE = re.compile(r"\\x[0-9a-fA-F]{2}")
_RE_OCTAL_ESCAPE = re.compile(r"\\[0-7]{3}")
_RE_ENV_VAR = re.compile(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?")


@functools.lru_cache(maxsize=1024)
def _is_path_in_allowed_dirs(resolved_path: str) -> bool:
    """检查路径是否在允许目录内（使用缓存）

    缓存大小 1024 覆盖高频访问路径，减少重复验证开销。
    """
    return any(resolved_path.startswith(allowed) for allowed in ALLOWED_DIRS)


def _validate_path_safety(path: str) -> tuple[bool, str]:
    """
    验证路径安全性，防止路径遍历攻击。

    Args:
        path: 原始路径字符串

    Returns:
        (is_safe, error_message): 安全返回 (True, ""), 不安全返回 (False, 错误信息)
    """
    # 1. URL 编码绕过检测（单层和双重编码）
    path_lower = path.lower()
    if _RE_URL_ENCODED.search(path_lower) or _RE_DOUBLE_URL_ENCODED.search(path_lower):
        # 解码后检查是否包含危险字符
        try:
            from urllib.parse import unquote

            decoded_once = unquote(path)
            decoded_twice = unquote(decoded_once)
            for decoded in [path, decoded_once, decoded_twice]:
                if (
                    ".." in decoded
                    or decoded.startswith("/")
                    or decoded.startswith("\\")
                ):
                    logger.warning(
                        f"URL-encoded path traversal attempt blocked: {path} -> {decoded}"
                    )
                    return (
                        False,
                        f"URL-encoded path blocked: '{path[:50]}...' - decoded path contains traversal patterns",
                    )
        except Exception as e:
            # 解码失败时保守拒绝
            logger.warning(
                f"URL-encoded path blocked (decode failed: {path}, error: {type(e).__name__})"
            )
            return (
                False,
                f"URL-encoded path blocked: '{path[:50]}...' - cannot safely decode",
            )

    # 2. UTF-8 过长编码检测（绕过技术）
    if _RE_UTF8_OVERLONG.search(path):
        logger.warning(f"UTF-8 overlong encoding detected: {path}")
        return (
            False,
            f"UTF-8 overlong encoding blocked: '{path[:50]}...' - potential path traversal attempt",
        )

    # 3. 快速检测 .. 序列（使用预编译正则）
    if _RE_DOUBLE_DOT.search(path):
        # 计算遍历深度
        normalized = path.replace("\\", "/")
        parts = normalized.split("/")
        depth = 0
        for part in parts:
            if part == "..":
                depth -= 1
            elif part and part != ".":
                depth += 1
        if depth < 0:
            logger.warning(f"Path traversal attempt blocked: {path}")
            return (
                False,
                f"Path traversal blocked: '{path}' contains '..' sequences that escape allowed directories",
            )

    # Windows 特殊攻击模式
    if os.name == "nt":
        # 检查驱动器字母模式
        if _RE_WINDOWS_DRIVE.match(path):
            try:
                resolved = str(Path(path).resolve())
                if _is_path_in_allowed_dirs(resolved):
                    return True, ""
            except Exception as e:
                logger.debug(f"Failed to resolve Windows drive path '{path}': {e}")
            logger.warning(f"Windows drive path outside allowed dirs: {path}")
            return False, f"Windows drive path '{path}' is outside allowed directories"

        # 检查 UNC 路径
        if path.startswith("\\\\") or path.startswith("//"):
            logger.warning(f"UNC path blocked: {path}")
            return False, f"UNC path '{path}' is not allowed for security reasons"

    # 检查绝对路径是否在允许范围内（使用缓存）
    if os.path.isabs(path):
        try:
            resolved = str(Path(path).resolve())
            if _is_path_in_allowed_dirs(resolved):
                return True, ""
        except Exception as e:
            logger.debug(f"Failed to resolve absolute path '{path}': {e}")
        logger.warning(f"Absolute path outside allowed dirs: {path}")
        return False, f"Absolute path '{path}' is outside allowed directories"

    return True, ""


def _resolve_path(path: str) -> str:
    """解析路径，相对路径默认从 .seed 目录解析（含路径遍历防护）"""

    # 先展开 ~ 为用户主目录
    if path.startswith("~"):
        path = os.path.expanduser(path)

    # 安全验证
    is_safe, error = _validate_path_safety(path)
    if not is_safe:
        raise ValueError(error)

    if os.path.isabs(path):
        return path

    # 相对路径：优先从 .seed 目录解析
    seed_path = DEFAULT_WORK_DIR / path
    try:
        resolved_seed = str(seed_path.resolve())
        # 使用缓存检查
        if (
            resolved_seed.startswith(DEFAULT_WORK_DIR_RESOLVED)
            or resolved_seed.startswith(PROJECT_ROOT_RESOLVED)
        ) and seed_path.exists():
            return resolved_seed
    except Exception as e:
        logger.debug(f"Failed to resolve seed path '{path}': {e}")

    # 再从项目根目录解析
    project_path = PROJECT_ROOT / path
    try:
        resolved_project = str(project_path.resolve())
        if resolved_project.startswith(PROJECT_ROOT_RESOLVED) and project_path.exists():
            return resolved_project
    except Exception as e:
        logger.debug(f"Failed to resolve project path '{path}': {e}")

    # 如果都不存在，使用 .seed 目录作为默认目标
    final_path = str(DEFAULT_WORK_DIR / path)
    final_resolved = str(Path(final_path).resolve())
    if not final_resolved.startswith(DEFAULT_WORK_DIR_RESOLVED):
        raise ValueError(f"Resolved path escapes allowed directories: {final_path}")

    return final_path


def file_read(path: str, start: int = 1, count: int = 100) -> str:
    """
    Read file content with line numbers.
    支持自动编码检测 (UTF-8, GBK, GB2312, Latin-1)。

    Args:
        path: File path to read (absolute or relative to .seed directory).
        start: Start line number (1-based).
        count: Number of lines to read.

    Returns:
        File content with line numbers, or error message.
    """
    try:
        # 类型安全转换：start 和 count 必须是正整数
        try:
            start = int(start) if isinstance(start, str) else int(start)
            if start < 1:
                start = 1
        except (ValueError, TypeError):
            start = 1

        try:
            count = int(count) if isinstance(count, str) else int(count)
            if count < 1:
                count = 100
        except (ValueError, TypeError):
            count = 100

        resolved_path = _resolve_path(path)
        content = None
        detected_encoding = "utf-8"

        # 尝试多种编码
        for enc in ["utf-8", "gbk", "gb2312", "latin-1"]:
            try:
                with open(resolved_path, encoding=enc) as f:
                    content = f.readlines()
                detected_encoding = enc
                break
            except UnicodeDecodeError:
                continue

        if content is None:
            return f"Error: Unable to decode file {path} with supported encodings"

        total_lines = len(content)
        start_idx = max(0, start - 1)
        end_idx = min(total_lines, start_idx + count)
        selected = content[start_idx:end_idx]

        if not selected:
            return f"Empty range: lines {start}-{start + count - 1} (file has {total_lines} lines)"

        result = "".join(
            f"{i + start_idx + 1}|{line}" for i, line in enumerate(selected)
        )
        enc_note = (
            f" (decoded as {detected_encoding})" if detected_encoding != "utf-8" else ""
        )
        result += f"\n--- File: {resolved_path}{enc_note}, Lines: {start}-{end_idx}/{total_lines} ---"
        return result

    except FileNotFoundError:
        return f"Error: File not found - {path}"
    except Exception as e:
        return f"Error reading file: {e!s}"


def file_write(path: str, content: str, mode: str = "overwrite") -> str:
    """
    Write content to a file.

    Args:
        path: File path to write (absolute or relative to .seed directory).
        content: Content to write.
        mode: Write mode - 'overwrite' (default) or 'append'.

    Returns:
        Success message or error.
    """
    try:
        resolved_path = _resolve_path(path)

        write_mode = "w" if mode == "overwrite" else "a"
        Path(resolved_path).parent.mkdir(parents=True, exist_ok=True)

        with open(resolved_path, write_mode, encoding="utf-8") as f:
            f.write(content)

        action = "written" if mode == "overwrite" else "appended"
        return f"Successfully {action} to {resolved_path} ({len(content)} chars)"

    except Exception as e:
        error_type = type(e).__name__
        # 完整错误记录到日志，截断版本返回给用户
        logger.error(f"Full error writing to '{resolved_path}': {error_type}: {e}")
        error_msg = str(e)[:200]
        return f"Error writing to '{resolved_path}': {error_type} - {error_msg}. Check permissions and disk space."


def file_edit(path: str, old_str: str, new_str: str, replace_all: bool = False) -> str:
    """
    Edit file by replacing text.

    Args:
        path: File path to edit (absolute or relative to .seed directory).
        old_str: Text to find and replace (must be exact match).
        new_str: New text to insert.
        replace_all: If True, replace all occurrences; else replace first.

    Returns:
        Success message with change details, or error.
    """
    try:
        resolved_path = _resolve_path(path)

        with open(resolved_path, encoding="utf-8") as f:
            content = f.read()

        if old_str not in content:
            return f"Error: Text not found in file - '{old_str[:50]}...'"

        if replace_all:
            count = content.count(old_str)
            new_content = content.replace(old_str, new_str)
        else:
            count = 1
            new_content = content.replace(old_str, new_str, 1)

        with open(resolved_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return f"Successfully edited {resolved_path}: replaced {count} occurrence(s)"

    except FileNotFoundError:
        return f"Error: File not found - {path}"
    except Exception as e:
        logger.exception("file_edit failed")
        return f"Error editing file: {e!s}"


# 语言映射表（用于代码执行）
LANGUAGE_MAP = {
    "python": (["python", "-c"], "py"),
    "javascript": (["node", "-e"], "js"),
    "shell": (["bash", "-c"], "sh"),
    "powershell": (["powershell", "-Command"], "ps"),
}


def _check_code_security(
    code: str, language: str, exec_logger: logging.Logger | None
) -> str | None:
    """Check code against security blacklists. Returns error message if blocked."""
    code_lower = code.lower()

    # 预处理：移除常见绕过技巧
    normalized_code = _RE_ESCAPE_BACKSLASH.sub(r"\1", code_lower)
    normalized_code = _RE_IFS_VAR.sub("", normalized_code)
    normalized_code = _RE_QUOTED_VAR.sub("", normalized_code)
    normalized_code = _RE_WHITESPACE.sub(" ", normalized_code)
    normalized_code = _RE_QUOTES.sub("", normalized_code)

    # 通用安全检查（所有语言）
    # 检测十六进制转义序列（如 \x2e = '.'）
    if _RE_HEX_ESCAPE.search(code):
        hex_decoded = _RE_HEX_ESCAPE.sub(lambda m: chr(int(m.group(0)[2:], 16)), code)
        if ".." in hex_decoded or any(
            d.lower() in hex_decoded.lower() for d in SHELL_BLACKLIST[:5]
        ):
            if exec_logger:
                exec_logger.warning("Blocked hex escape sequence in code")
            return (
                "Error: Blocked hex escape sequence that may encode dangerous patterns."
            )

    # 检测八进制转义序列（如 \056 = '.'）
    if _RE_OCTAL_ESCAPE.search(code):
        oct_decoded = _RE_OCTAL_ESCAPE.sub(lambda m: chr(int(m.group(0)[1:], 8)), code)
        if ".." in oct_decoded or any(
            d.lower() in oct_decoded.lower() for d in SHELL_BLACKLIST[:5]
        ):
            if exec_logger:
                exec_logger.warning("Blocked octal escape sequence in code")
            return "Error: Blocked octal escape sequence that may encode dangerous patterns."

    if language in ("shell", "bash", "sh"):
        for danger in SHELL_BLACKLIST:
            danger_lower = danger.lower()
            if danger_lower in code_lower or danger_lower in normalized_code:
                if exec_logger:
                    exec_logger.warning(
                        f"Blocked dangerous shell command: contains '{danger}'"
                    )
                return f"Error: Blocked dangerous command pattern: '{danger}'. This tool does not allow system-destructive operations."
        if _RE_BASE64_DECODE.search(normalized_code):
            if exec_logger:
                exec_logger.warning("Blocked base64 decode attempt")
            return "Error: Blocked base64 decode pattern. Encoded commands are not allowed."
        # 检测环境变量注入攻击
        env_matches = _RE_ENV_VAR.findall(normalized_code)
        dangerous_env_vars = [
            "PATH",
            "HOME",
            "USER",
            "SHELL",
            "IFS",
            "LD_PRELOAD",
            "LD_LIBRARY_PATH",
        ]
        for env_var in env_matches:
            env_name = env_var.replace("${", "").replace("}", "").replace("$", "")
            if env_name in dangerous_env_vars:
                if exec_logger:
                    exec_logger.warning(
                        f"Blocked dangerous env var reference: {env_var}"
                    )
                return f"Error: Blocked dangerous environment variable: '{env_name}'. Environment manipulation is not allowed."

    elif language in ("powershell", "ps", "pwsh"):
        for danger in POWERSHELL_BLACKLIST:
            danger_lower = danger.lower()
            if danger_lower in code_lower or danger_lower in normalized_code:
                if exec_logger:
                    exec_logger.warning(
                        f"Blocked dangerous PowerShell command: contains '{danger}'"
                    )
                return f"Error: Blocked dangerous command pattern: '{danger}'. This tool does not allow system-destructive operations."
        if _RE_PWSH_ENCODED.search(normalized_code):
            if exec_logger:
                exec_logger.warning("Blocked PowerShell encoded command attempt")
            return "Error: Blocked PowerShell encoded command pattern. Encoded commands are not allowed."

    return None


def _resolve_execution_cwd(cwd: str | None) -> str:
    """解析代码执行的工作目录（返回绝对路径）"""
    if cwd is None:
        return str(DEFAULT_WORK_DIR)
    if os.path.isabs(cwd):
        return cwd
    seed_cwd = DEFAULT_WORK_DIR / cwd
    if seed_cwd.exists():
        return str(seed_cwd)
    return str(PROJECT_ROOT / cwd)


def _build_command(code: str, language: str) -> list[str] | None:
    """Build subprocess command for given language."""
    for lang_prefix, (cmd_prefix, alias) in LANGUAGE_MAP.items():
        if language in (lang_prefix, alias):
            return cmd_prefix + [code]
    if language in ("js", "node"):
        return ["node", "-e", code]
    return None


def _format_execution_result(
    result: subprocess.CompletedProcess[str], language: str
) -> str:
    """格式化子进程输出为结果字符串"""
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
    Execute code in various languages (python, js, shell, bash, powershell).

    Args:
        code: Code string to execute.
        language: Language type - 'python', 'javascript'/'js', 'shell'/'bash', 'powershell'/'ps'.
        cwd: Working directory for execution (default: .seed directory).
        timeout: Execution timeout in seconds.

    Returns:
        Execution output (stdout + stderr), or error message.

    Note:
        This is a synchronous version. For async contexts, use code_as_policy_async
        to avoid blocking the event loop.
    """
    exec_logger = logging.getLogger("seed_agent.code_exec")
    try:
        if len(code) > MAX_CODE_LENGTH:
            return f"Error: Code exceeds maximum length ({MAX_CODE_LENGTH} chars) for security"

        # 类型安全转换：timeout 必须是正整数
        try:
            timeout = int(timeout) if isinstance(timeout, str) else int(timeout)
            if timeout <= 0:
                timeout = DEFAULT_EXECUTION_TIMEOUT
        except (ValueError, TypeError):
            timeout = DEFAULT_EXECUTION_TIMEOUT

        cwd = _resolve_execution_cwd(cwd)
        language = language.lower()

        error = _check_code_security(code, language, exec_logger)
        if error:
            return error

        exec_logger.info(
            f"Code execution: language={language}, cwd={cwd}, timeout={timeout}s"
        )

        cmd = _build_command(code, language)
        if cmd is None:
            return f"Error: Unsupported language '{language}'. Supported: python, javascript, shell, powershell"

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            encoding="utf-8",
            errors="replace",
        )
        exec_logger.info(f"Code execution completed: returncode={result.returncode}")
        return _format_execution_result(result, language)

    except subprocess.TimeoutExpired:
        exec_logger.warning(
            f"Code execution timed out: language={language}, timeout={timeout}s"
        )
        return f"Error: Execution timed out ({timeout}s)"
    except FileNotFoundError:
        exec_logger.error(f"Interpreter not found for '{language}'")
        return f"Error: Interpreter not found for '{language}'. Please ensure it's installed."
    except PermissionError as e:
        exec_logger.error(f"Permission denied for '{language}': {e}")
        return f"Error: Permission denied executing '{language}' code."
    except OSError as e:
        exec_logger.error(f"OS error: {type(e).__name__}: {e}")
        return f"Error: OS error - {type(e).__name__}: {str(e)[:100]}"
    except Exception as e:
        exec_logger.exception(f"Code execution error: {e!s}")
        return f"Error executing code: {e!s}"


async def code_as_policy_async(
    code: str, language: str = "python", cwd: str | None = None, timeout: int = 60
) -> str:
    """
    Async version of code_as_policy - non-blocking for event loop.

    Uses asyncio.create_subprocess_exec instead of subprocess.run.

    Args:
        code: Code string to execute.
        language: Language type - 'python', 'javascript'/'js', 'shell'/'bash', 'powershell'/'ps'.
        cwd: Working directory for execution (default: .seed directory).
        timeout: Execution timeout in seconds.

    Returns:
        Execution output (stdout + stderr), or error message.
    """
    import asyncio

    exec_logger = logging.getLogger("seed_agent.code_exec")
    try:
        if len(code) > MAX_CODE_LENGTH:
            return f"Error: Code exceeds maximum length ({MAX_CODE_LENGTH} chars) for security"

        # 类型安全转换：timeout 必须是正整数
        try:
            timeout = int(timeout) if isinstance(timeout, str) else int(timeout)
            if timeout <= 0:
                timeout = DEFAULT_EXECUTION_TIMEOUT
        except (ValueError, TypeError):
            timeout = DEFAULT_EXECUTION_TIMEOUT

        cwd = _resolve_execution_cwd(cwd)
        language = language.lower()

        error = _check_code_security(code, language, exec_logger)
        if error:
            return error

        exec_logger.info(
            f"Async code execution: language={language}, cwd={cwd}, timeout={timeout}s"
        )

        cmd = _build_command(code, language)
        if cmd is None:
            return f"Error: Unsupported language '{language}'. Supported: python, javascript, shell, powershell"

        # Use async subprocess to avoid blocking event loop
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
        except asyncio.TimeoutError:
            # Kill process on timeout
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                # 进程已结束，无需处理
                pass
            exec_logger.warning(
                f"Async code execution timed out: language={language}, timeout={timeout}s"
            )
            return f"Error: Execution timed out ({timeout}s)"

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        exec_logger.info(f"Async code execution completed: returncode={proc.returncode}")

        # Build result
        output = stdout
        if stderr:
            output += "\n[Stderr]\n" + stderr
        if proc.returncode and proc.returncode != 0:
            output += f"\n[Exit Code: {proc.returncode}]"
        return output if output.strip() else f"Code executed successfully ({language})"

    except FileNotFoundError:
        exec_logger.error(f"Interpreter not found for '{language}'")
        return f"Error: Interpreter not found for '{language}'. Please ensure it's installed."
    except PermissionError as e:
        exec_logger.error(f"Permission denied for '{language}': {e}")
        return f"Error: Permission denied executing '{language}' code."
    except OSError as e:
        exec_logger.error(f"OS error: {type(e).__name__}: {e}")
        return f"Error: OS error - {type(e).__name__}: {str(e)[:100]}"
    except Exception as e:
        exec_logger.exception(f"Async code execution error: {e!s}")
        return f"Error executing code: {e!s}"


def ask_user(
    question: str,
    options: Optional[list[str]] = None,
    header: Optional[str] = None,
    multi_select: bool = False,
) -> str:
    """
    Ask user for input/confirmation during task execution.

    这是真正的等待机制：
    - 返回等待标记字符串
    - Harness 检测标记后暂停循环
    - 外部（main.py）注入用户响应
    - Harness 恢复循环继续执行

    Args:
        question: 问题文本
        options: 选项列表（可选，默认 ["Yes", "No"]）
        header: 简短标题（可选，默认从问题截取前30字符）
        multi_select: 是否多选

    Returns:
        等待标记字符串，实际响应由 Harness 处理

    示例：
        ask_user("Continue?", ["Yes", "No", "Cancel"])
        -> "[AWAITING_USER_INPUT] request_id=abc123\\nContinue?\\nOptions: Yes, No, Cancel"
    """
    # 构造请求结构
    request = AskUserRequest.from_simple(
        question=question,
        options=options,
        header=header,
        multi_select=multi_select,
    )

    # 设置全局等待状态
    state = get_ask_user_state()
    state.set_request(request)

    # 构造返回字符串（等待标记）
    options_str = ", ".join(options or ["Yes", "No"])
    result = f"[AWAITING_USER_INPUT] request_id={request.request_id}\n{question}\nOptions: {options_str}"

    if multi_select:
        result += "\n[Multi-select enabled]"

    return result


def inject_user_response(response: AskUserResult) -> None:
    """注入用户响应（由外部调用）

    Args:
        response: 用户响应数据

    用法：
        # 在 main.py 或外部系统调用
        from tools.builtin_tools import inject_user_response
        inject_user_response(AskUserResult(
            request_id="abc123",
            responses=[UserResponse(question_id="0", selected=["Yes"])],
        ))
    """
    state = get_ask_user_state()
    state.inject_response(response)


def get_pending_ask_user_request() -> Optional[AskUserRequest]:
    """获取当前等待中的 ask_user 请求"""
    state = get_ask_user_state()
    return state.pending_request


def clear_ask_user_state() -> None:
    """清理等待状态"""
    state = get_ask_user_state()
    state.clear()


def run_diagnosis(fix: bool = False) -> str:
    """
    Run seed-agent diagnostic scan based on known bug patterns.

    Args:
        fix: If True, automatically fix detected issues (default: False).

    Returns:
        Diagnosis results with PASS/FAIL/WARN status for each check.
    """
    try:
        script_path = DEFAULT_WORK_DIR / "scripts" / "diagnose_seed_agent.py"

        if not script_path.exists():
            return f"Error: Diagnosis script not found at {script_path}"

        cmd = ["python", str(script_path)]
        if fix:
            cmd.append("--fix")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(DEFAULT_WORK_DIR),
            timeout=120,
        )

        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR: {result.stderr}"

        return output[:3000]
    except subprocess.TimeoutExpired:
        return "Error: Diagnosis timed out (>120s)"
    except Exception as e:
        return f"Error running diagnosis: {e!s}"


def register_builtin_tools(registry: ToolRegistry) -> None:
    """Register the 6 core builtin tools."""
    registry.register("file_read", file_read)
    registry.register("file_write", file_write)
    registry.register("file_edit", file_edit)
    registry.register("code_as_policy", code_as_policy)
    registry.register("ask_user", ask_user)
    registry.register("run_diagnosis", run_diagnosis)
