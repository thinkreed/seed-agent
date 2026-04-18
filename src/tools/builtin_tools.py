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

import urllib.request
import urllib.parse
import platform
import socket

def fetch_url(url: str, headers: dict = None, timeout: int = 10) -> str:
    """Fetch content from a URL.
    Args:
        url: URL to fetch.
        headers: Optional dict of headers.
        timeout: Request timeout in seconds.
    """
    try:
        req = urllib.request.Request(url)
        if headers:
            for key, value in headers.items():
                req.add_header(key, value)
        else:
            req.add_header('User-Agent', 'Mozilla/5.0 (SeedAgent/1.0)')
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read().decode('utf-8', errors='ignore')[:10000]
    except Exception as e:
        return f"Error fetching URL: {str(e)}"

def get_system_info() -> str:
    """Get basic system information.
    Returns:
        String with system details (OS, Node, Release, Machine, IP).
    """
    try:
        info = {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "hostname": platform.node(),
            "local_ip": socket.gethostbyname(socket.gethostname())
        }
        return "\n".join(f"{k}: {v}" for k, v in info.items())
    except Exception as e:
        return f"Error getting system info: {str(e)}"

import datetime

def get_current_time() -> str:
    """Get current date and time.
    Returns:
        Formatted date and time string.
    """
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")

import shutil

def download_file(url: str, save_path: str, headers: dict = None, timeout: int = 30):
    """Download a file from a URL.
    Args:
        url: URL of the file.
        save_path: Local path to save the file.
        headers: Optional dict of headers.
        timeout: Download timeout in seconds.
    """
    try:
        req = urllib.request.Request(url)
        if headers:
            for key, value in headers.items():
                req.add_header(key, value)
        else:
            req.add_header('User-Agent', 'Mozilla/5.0 (SeedAgent/1.0)')
        
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(req, timeout=timeout) as response, open(save_path, 'wb') as out_file:
            out_file.write(response.read())
        return f"Successfully downloaded to {save_path}"
    except Exception as e:
        return f"Error downloading file: {str(e)}"

def compress_files(files: list, output_zip: str):
    """Compress files into a zip archive.
    Args:
        files: List of file paths to compress.
        output_zip: Path to the output zip file.
    """
    try:
        with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file in files:
                zf.write(file)
        return f"Successfully created zip archive: {output_zip}"
    except Exception as e:
        return f"Error creating zip: {str(e)}"

def decompress_files(zip_path: str, extract_dir: str = "."):
    """Decompress a zip archive.
    Args:
        zip_path: Path to the zip file.
        extract_dir: Directory to extract files to.
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)
        return f"Successfully extracted to {extract_dir}"
    except Exception as e:
        return f"Error extracting zip: {str(e)}"

def run_shell(command: str, shell_type: str = "powershell", cwd: str = ".", timeout: int = 60):
    """Execute a shell command.
    Args:
        command: Shell command to execute.
        shell_type: Type of shell ('powershell' or 'bash').
        cwd: Working directory.
        timeout: Execution timeout in seconds.
    """
    try:
        shell = "powershell" if shell_type == "powershell" else "bash"
        result = subprocess.run(
            [shell, "-Command" if shell_type == "powershell" else "-c", command],
            capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
        output = result.stdout
        if result.stderr:
            output += "\nStderr:\n" + result.stderr
        return output if output else "Command executed successfully."
    except subprocess.TimeoutExpired:
        return "Error: Command timed out."
    except Exception as e:
        return f"Error: {str(e)}"

def register_builtin_tools(registry):
    """Register builtin tools to the registry."""
    registry.register("run_code", run_code)
    registry.register("read_file", read_file)
    registry.register("write_file", write_file)
    registry.register("list_files", list_files)
    registry.register("fetch_url", fetch_url)
    registry.register("get_system_info", get_system_info)
    registry.register("get_current_time", get_current_time)
    registry.register("download_file", download_file)
    registry.register("compress_files", compress_files)
    registry.register("decompress_files", decompress_files)
    registry.register("run_shell", run_shell)