"""5个核心内置工具：file_read, file_write, file_edit, code_as_policy, ask_user"""

import subprocess
import os
from pathlib import Path
import logging

logger = logging.getLogger("seed_agent.path")

# 默认工作目录为 ~/.seed 目录
PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_WORK_DIR = Path(os.path.expanduser("~")) / ".seed"

# 允许的目录列表（用于路径验证）
ALLOWED_DIRS = [
    DEFAULT_WORK_DIR,
    PROJECT_ROOT,
    Path(os.path.expanduser("~")) / "Documents",
]


def _validate_path_safety(path: str) -> tuple[bool, str]:
    """
    验证路径安全性，防止路径遍历攻击。

    Args:
        path: 原始路径字符串

    Returns:
        (is_safe, error_message): 安全返回 (True, ""), 不安全返回 (False, 错误信息)
    """
    # 检查危险路径模式

    # 检查 .. 序列
    normalized = path.replace("\\", "/")
    if ".." in normalized:
        # 计算遍历深度
        parts = normalized.split("/")
        depth = 0
        for part in parts:
            if part == "..":
                depth -= 1
            elif part and part != ".":
                depth += 1
        if depth < 0:
            logger.warning(f"Path traversal attempt blocked: {path}")
            return False, f"Path traversal blocked: '{path}' contains '..' sequences that escape allowed directories"

    # 检查绝对路径是否在允许范围内
    if os.path.isabs(path):
        resolved = str(Path(path).resolve())
        for allowed in ALLOWED_DIRS:
            try:
                # 检查是否是允许目录的子路径
                resolved_path = Path(resolved)
                allowed_path = Path(str(allowed.resolve()))
                if str(resolved_path).startswith(str(allowed_path)):
                    return True, ""
            except Exception:
                continue
        logger.warning(f"Absolute path outside allowed dirs: {path}")
        return False, f"Absolute path '{path}' is outside allowed directories"

    return True, ""


def _resolve_path(path: str) -> str:
    """解析路径，相对路径默认从 .seed 目录解析（含路径遍历防护）"""

    # 安全验证
    is_safe, error = _validate_path_safety(path)
    if not is_safe:
        raise ValueError(error)

    if os.path.isabs(path):
        # 绝对路径已经在验证中检查过是否允许
        return path

    # 相对路径：优先从 .seed 目录解析，如果不存在再从项目根目录解析
    seed_path = DEFAULT_WORK_DIR / path
    try:
        resolved_seed = seed_path.resolve()
        # 再次验证解析后的路径
        if str(resolved_seed).startswith(str(DEFAULT_WORK_DIR.resolve())) or str(resolved_seed).startswith(str(PROJECT_ROOT.resolve())):
            if seed_path.exists():
                return str(resolved_seed)
    except Exception:
        pass

    project_path = PROJECT_ROOT / path
    try:
        resolved_project = project_path.resolve()
        if str(resolved_project).startswith(str(PROJECT_ROOT.resolve())):
            if project_path.exists():
                return str(resolved_project)
    except Exception:
        pass

    # 如果都不存在，使用 .seed 目录作为默认目标（仍然验证）
    final_path = str(DEFAULT_WORK_DIR / path)
    if not str(Path(final_path).resolve()).startswith(str(DEFAULT_WORK_DIR.resolve())):
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
        resolved_path = _resolve_path(path)
        content = None
        detected_encoding = 'utf-8'

        # 尝试多种编码
        for enc in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
            try:
                with open(resolved_path, 'r', encoding=enc) as f:
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
            return f"Empty range: lines {start}-{start+count-1} (file has {total_lines} lines)"

        result = "".join(f"{i+start_idx+1}|{line}" for i, line in enumerate(selected))
        enc_note = f" (decoded as {detected_encoding})" if detected_encoding != 'utf-8' else ""
        result += f"\n--- File: {resolved_path}{enc_note}, Lines: {start}-{end_idx}/{total_lines} ---"
        return result

    except FileNotFoundError:
        return f"Error: File not found - {path}"
    except Exception as e:
        return f"Error reading file: {str(e)}"


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

        write_mode = 'w' if mode == "overwrite" else 'a'
        Path(resolved_path).parent.mkdir(parents=True, exist_ok=True)

        with open(resolved_path, write_mode, encoding='utf-8') as f:
            f.write(content)

        action = "written" if mode == "overwrite" else "appended"
        return f"Successfully {action} to {resolved_path} ({len(content)} chars)"

    except Exception as e:
        return f"Error writing file: {str(e)}"


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

        with open(resolved_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if old_str not in content:
            return f"Error: Text not found in file - '{old_str[:50]}...'"

        if replace_all:
            count = content.count(old_str)
            new_content = content.replace(old_str, new_str)
        else:
            count = 1
            new_content = content.replace(old_str, new_str, 1)

        with open(resolved_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        return f"Successfully edited {resolved_path}: replaced {count} occurrence(s)"

    except FileNotFoundError:
        return f"Error: File not found - {path}"
    except Exception as e:
        return f"Error editing file: {str(e)}"


# 代码执行安全黑名单（模块级常量）
SHELL_BLACKLIST = [
    "rm -rf", "rm -r", "rmdir", "del ", "format",
    "sudo", "su", "chmod 777", "chown",
    "wget", "curl -o", "nc ", "netcat",
    "kill -9", "pkill", "killall",
    "; rm", "| rm", "& rm", "`rm", "$(rm",
    "cat /etc/passwd", "cat /etc/shadow",
]

POWERSHELL_BLACKLIST = [
    "Remove-Item", "Delete-Item", "Format-Volume",
    "Set-ExecutionPolicy", "Start-Process -Verb RunAs",
    "Download-File", "Invoke-WebRequest -OutFile",
    "Stop-Process -Force", "Kill-Process",
]

LANGUAGE_MAP = {
    "python": (["python", "-c"], "py"),
    "javascript": (["node", "-e"], "js"),
    "shell": (["bash", "-c"], "sh"),
    "powershell": (["powershell", "-Command"], "ps"),
}


def _check_code_security(code: str, language: str, logger) -> str | None:
    """Check code against security blacklists. Returns error message if blocked."""
    code_lower = code.lower()
    if language in ("shell", "bash", "sh"):
        for danger in SHELL_BLACKLIST:
            if danger.lower() in code_lower:
                if logger:
                    logger.warning(f"Blocked dangerous shell command: contains '{danger}'")
                return f"Error: Blocked dangerous command pattern: '{danger}'. This tool does not allow system-destructive operations."
    elif language in ("powershell", "ps", "pwsh"):
        for danger in POWERSHELL_BLACKLIST:
            if danger.lower() in code_lower:
                if logger:
                    logger.warning(f"Blocked dangerous PowerShell command: contains '{danger}'")
                return f"Error: Blocked dangerous command pattern: '{danger}'. This tool does not allow system-destructive operations."
    return None


def _resolve_execution_cwd(cwd: str | None) -> str:
    """Resolve working directory for code execution."""
    if cwd is None:
        return str(DEFAULT_WORK_DIR)
    if os.path.isabs(cwd):
        return cwd
    seed_cwd = DEFAULT_WORK_DIR / cwd
    if seed_cwd.exists():
        return str(seed_cwd)
    return str(PROJECT_ROOT / cwd)


def _build_command(code: str, language: str) -> list | None:
    """Build subprocess command for given language. Returns None if unsupported."""
    for lang_prefix, (cmd_prefix, alias) in LANGUAGE_MAP.items():
        if language == lang_prefix or language == alias:
            return cmd_prefix + [code]
    # Check extended aliases
    if language in ("js", "node"):
        return ["node", "-e", code]
    return None


def _format_execution_result(result: subprocess.CompletedProcess, language: str) -> str:
    """Format subprocess output into result string."""
    output = result.stdout
    if result.stderr:
        output += "\n[Stderr]\n" + result.stderr
    if result.returncode != 0:
        output += f"\n[Exit Code: {result.returncode}]"
    return output if output.strip() else f"Code executed successfully ({language})"


def code_as_policy(code: str, language: str = "python", cwd: str = None, timeout: int = 60) -> str:
    """
    Execute code in various languages (python, js, shell, bash, powershell).

    Args:
        code: Code string to execute.
        language: Language type - 'python', 'javascript'/'js', 'shell'/'bash', 'powershell'/'ps'.
        cwd: Working directory for execution (default: .seed directory).
        timeout: Execution timeout in seconds.

    Returns:
        Execution output (stdout + stderr), or error message.
    """
    exec_logger = logging.getLogger("seed_agent.code_exec")
    try:
        if len(code) > 10000:
            return "Error: Code exceeds maximum length (10000 chars) for security"

        cwd = _resolve_execution_cwd(cwd)
        language = language.lower()

        error = _check_code_security(code, language, exec_logger)
        if error:
            return error

        exec_logger.info(f"Code execution requested: language={language}, cwd={cwd}, timeout={timeout}s, code_preview={code[:100]}...")

        cmd = _build_command(code, language)
        if cmd is None:
            return f"Error: Unsupported language '{language}'. Supported: python, javascript, shell, powershell"

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd, encoding='utf-8', errors='replace')
        exec_logger.info(f"Code execution completed: returncode={result.returncode}, output_length={len(result.stdout)}")
        return _format_execution_result(result, language)

    except subprocess.TimeoutExpired:
        exec_logger.warning(f"Code execution timed out: language={language}, timeout={timeout}s")
        return f"Error: Execution timed out ({timeout}s)"
    except FileNotFoundError:
        exec_logger.error(f"Interpreter not found for '{language}'")
        return f"Error: Interpreter not found for '{language}'. Please ensure it's installed."
    except Exception as e:
        exec_logger.exception(f"Code execution error: {str(e)}")
        return f"Error executing code: {str(e)}"


def ask_user(question: str, options: list = None) -> str:
    """
    Ask user for input/confirmation during task execution.

    Args:
        question: Question or prompt to display to user.
        options: Optional list of choices for user to select.

    Returns:
        Instruction for agent to pause and ask user.
    """
    result = f"[ASK_USER] {question}"
    if options:
        result += f"\nOptions: {', '.join(options)}"
    result += "\n[Waiting for user response]"
    return result


def run_diagnosis(fix: bool = False) -> str:
    """
    Run seed-agent diagnostic scan based on known bug patterns.

    Args:
        fix: If True, automatically fix detected issues (default: False).

    Returns:
        Diagnosis results with PASS/FAIL/WARN status for each check.
    """
    try:
        seed_dir = Path(os.path.expanduser("~")) / ".seed"
        script_path = seed_dir / "scripts" / "diagnose_seed_agent.py"

        if not script_path.exists():
            return f"Error: Diagnosis script not found at {script_path}"

        cmd = [
            "python", str(script_path),
        ]
        if fix:
            cmd.append("--fix")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            cwd=str(seed_dir),
            timeout=120
        )

        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR: {result.stderr}"

        return output[:3000]  # Limit output size
    except subprocess.TimeoutExpired:
        return "Error: Diagnosis timed out (>120s)"
    except Exception as e:
        return f"Error running diagnosis: {str(e)}"


def register_builtin_tools(registry):
    """Register the 5 core builtin tools."""
    registry.register("file_read", file_read)
    registry.register("file_write", file_write)
    registry.register("file_edit", file_edit)
    registry.register("code_as_policy", code_as_policy)
    registry.register("ask_user", ask_user)
    registry.register("run_diagnosis", run_diagnosis)