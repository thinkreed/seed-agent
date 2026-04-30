"""5个核心内置工具：file_read, file_write, file_edit, code_as_policy, ask_user"""

import subprocess
import os
from pathlib import Path
import re

# 默认工作目录为 ~/.seed 目录
PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_WORK_DIR = Path(os.path.expanduser("~")) / ".seed"


def _resolve_path(path: str) -> str:
    """解析路径，相对路径默认从 .seed 目录解析"""
    if os.path.isabs(path):
        return path

    # 相对路径：优先从 .seed 目录解析，如果不存在再从项目根目录解析
    seed_path = DEFAULT_WORK_DIR / path
    if seed_path.exists():
        return str(seed_path.resolve())

    project_path = PROJECT_ROOT / path
    if project_path.exists():
        return str(project_path.resolve())

    # 如果都不存在，使用 .seed 目录作为默认目标
    return str(seed_path.resolve())


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
    try:
        # 默认工作目录为 .seed
        if cwd is None:
            cwd = str(DEFAULT_WORK_DIR)
        elif not os.path.isabs(cwd):
            seed_cwd = DEFAULT_WORK_DIR / cwd
            if seed_cwd.exists():
                cwd = str(seed_cwd)
            else:
                cwd = str(PROJECT_ROOT / cwd)

        language = language.lower()

        # 根据语言选择执行方式
        if language in ("python", "py"):
            cmd = ["python", "-c", code]
        elif language in ("javascript", "js", "node"):
            cmd = ["node", "-e", code]
        elif language in ("shell", "bash", "sh"):
            cmd = ["bash", "-c", code]
        elif language in ("powershell", "ps", "pwsh"):
            cmd = ["powershell", "-Command", code]
        else:
            return f"Error: Unsupported language '{language}'. Supported: python, javascript, shell, powershell"

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            encoding='utf-8',
            errors='replace'
        )

        output = result.stdout
        if result.stderr:
            output += "\n[Stderr]\n" + result.stderr

        if result.returncode != 0:
            output += f"\n[Exit Code: {result.returncode}]"

        return output if output.strip() else f"Code executed successfully ({language})"

    except subprocess.TimeoutExpired:
        return f"Error: Execution timed out ({timeout}s)"
    except FileNotFoundError:
        return f"Error: Interpreter not found for '{language}'. Please ensure it's installed."
    except Exception as e:
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