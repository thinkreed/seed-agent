"""5个核心内置工具：file_read, file_write, file_edit, code_as_policy, ask_user"""

import subprocess
import os
from pathlib import Path
import re


def file_read(path: str, start: int = 1, count: int = 100) -> str:
    """
    Read file content with line numbers.

    Args:
        path: File path to read (absolute or relative).
        start: Start line number (1-based).
        count: Number of lines to read.

    Returns:
        File content with line numbers, or error message.
    """
    try:
        # 支持相对路径，自动补全
        if not os.path.isabs(path):
            # 尝试从项目根目录解析
            project_root = Path(__file__).parent.parent.parent
            full_path = project_root / path
            if full_path.exists():
                path = str(full_path)

        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        total_lines = len(lines)
        start_idx = max(0, start - 1)
        end_idx = min(total_lines, start_idx + count)
        selected = lines[start_idx:end_idx]

        if not selected:
            return f"Empty range: lines {start}-{start+count-1} (file has {total_lines} lines)"

        result = "".join(f"{i+start_idx+1}|{line}" for i, line in enumerate(selected))
        result += f"\n--- File: {path}, Lines: {start}-{end_idx}/{total_lines} ---"
        return result

    except FileNotFoundError:
        return f"Error: File not found - {path}"
    except Exception as e:
        return f"Error reading file: {str(e)}"


def file_write(path: str, content: str, mode: str = "overwrite") -> str:
    """
    Write content to a file.

    Args:
        path: File path to write (absolute or relative).
        content: Content to write.
        mode: Write mode - 'overwrite' (default) or 'append'.

    Returns:
        Success message or error.
    """
    try:
        # 支持相对路径
        if not os.path.isabs(path):
            project_root = Path(__file__).parent.parent.parent
            full_path = project_root / path
            if not path.startswith('.'):
                path = str(full_path)

        write_mode = 'w' if mode == "overwrite" else 'a'
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        with open(path, write_mode, encoding='utf-8') as f:
            f.write(content)

        action = "written" if mode == "overwrite" else "appended"
        return f"Successfully {action} to {path} ({len(content)} chars)"

    except Exception as e:
        return f"Error writing file: {str(e)}"


def file_edit(path: str, old_str: str, new_str: str, replace_all: bool = False) -> str:
    """
    Edit file by replacing text.

    Args:
        path: File path to edit.
        old_str: Text to find and replace (must be exact match).
        new_str: New text to insert.
        replace_all: If True, replace all occurrences; else replace first.

    Returns:
        Success message with change details, or error.
    """
    try:
        if not os.path.isabs(path):
            project_root = Path(__file__).parent.parent.parent
            full_path = project_root / path
            if full_path.exists():
                path = str(full_path)

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        if old_str not in content:
            return f"Error: Text not found in file - '{old_str[:50]}...'"

        if replace_all:
            count = content.count(old_str)
            new_content = content.replace(old_str, new_str)
        else:
            count = 1
            new_content = content.replace(old_str, new_str, 1)

        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        return f"Successfully edited {path}: replaced {count} occurrence(s)"

    except FileNotFoundError:
        return f"Error: File not found - {path}"
    except Exception as e:
        return f"Error editing file: {str(e)}"


def code_as_policy(code: str, language: str = "python", cwd: str = ".", timeout: int = 60) -> str:
    """
    Execute code in various languages (python, js, shell, bash, powershell).

    Args:
        code: Code string to execute.
        language: Language type - 'python', 'javascript'/'js', 'shell'/'bash', 'powershell'/'ps'.
        cwd: Working directory for execution.
        timeout: Execution timeout in seconds.

    Returns:
        Execution output (stdout + stderr), or error message.
    """
    try:
        # 支持相对路径
        if not os.path.isabs(cwd):
            project_root = Path(__file__).parent.parent.parent
            full_cwd = project_root / cwd
            if full_cwd.exists():
                cwd = str(full_cwd)

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


def register_builtin_tools(registry):
    """Register the 5 core builtin tools."""
    registry.register("file_read", file_read)
    registry.register("file_write", file_write)
    registry.register("file_edit", file_edit)
    registry.register("code_as_policy", code_as_policy)
    registry.register("ask_user", ask_user)