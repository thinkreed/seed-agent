import subprocess
import os
from pathlib import Path

def run_code(code: str, type: str = "python", cwd: str = "."):
    """Execute code safely via subprocess.
    Args:
        code: The code string to execute.
        type: Type of code ('python' or 'powershell').
        cwd: Working directory for execution.
    """
    try:
        if type == "python":
            result = subprocess.run(
                ["python", "-c", code],
                capture_output=True, text=True, timeout=60, cwd=cwd
            )
        elif type == "powershell":
            result = subprocess.run(
                ["powershell", "-Command", code],
                capture_output=True, text=True, timeout=60, cwd=cwd
            )
        else:
            return f"Error: Unsupported code type '{type}'"
        
        output = result.stdout
        if result.stderr:
            output += "\nStderr:\n" + result.stderr
        return output if output else "Execution finished successfully."
    except subprocess.TimeoutExpired:
        return "Error: Execution timed out."
    except Exception as e:
        return f"Error: {str(e)}"

def read_file(path: str, start: int = 1, count: int = 100):
    """Read file content with line numbers.
    Args:
        path: File path to read.
        start: Start line number (1-based).
        count: Number of lines to read.
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        start_idx = max(0, start - 1)
        end_idx = start_idx + count
        selected = lines[start_idx:end_idx]
        return "".join(f"{i+start_idx+1}|{line}" for i, line in enumerate(selected))
    except Exception as e:
        return f"Error reading file: {str(e)}"

def write_file(path: str, content: str, mode: str = "overwrite"):
    """Write content to a file.
    Args:
        path: File path to write.
        content: Content to write.
        mode: Write mode ('overwrite' or 'append').
    """
    try:
        write_mode = 'w' if mode == 'overwrite' else 'a'
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, write_mode, encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"

def list_files(path: str = "."):
    """List files in a directory.
    Args:
        path: Directory path.
    """
    try:
        items = sorted(os.listdir(path))
        return "\n".join(items)
    except Exception as e:
        return f"Error listing files: {str(e)}"

def register_builtin_tools(registry):
    """Register builtin tools to the registry."""
    registry.register("run_code", run_code)
    registry.register("read_file", read_file)
    registry.register("write_file", write_file)
    registry.register("list_files", list_files)