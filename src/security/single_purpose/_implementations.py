"""
单用途工具实现方法

包含所有 _impl_* 方法的具体实现
"""

import fnmatch
import logging
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.security.constants import SENSITIVE_ENV_VARS as _SENSITIVE_ENV_VARS_TYPE
    from src.security.utils import get_safe_environment as _get_safe_environment_type

logger = logging.getLogger(__name__)


def _get_sensitive_env_vars() -> list[str]:
    """延迟获取敏感环境变量列表"""
    from src.security.constants import SENSITIVE_ENV_VARS
    return SENSITIVE_ENV_VARS


def _get_safe_env() -> dict[str, str]:
    """延迟获取安全环境"""
    from src.security.utils import get_safe_environment
    return get_safe_environment()


class ToolImplementations:
    """工具实现类

    包含所有单用途工具的具体实现方法
    """

    # === 文件操作实现 ===

    @staticmethod
    def read_file(args: dict) -> str:
        """读取文件"""
        path = args["path"]
        encoding = args.get("encoding", "utf-8")
        max_lines = args.get("max_lines", 1000)

        try:
            with open(path, encoding=encoding) as f:
                lines = f.readlines()

            total_lines = len(lines)
            if total_lines > max_lines:
                lines = lines[:max_lines]

            result = "".join(f"{i + 1}|{line}" for i, line in enumerate(lines))
            result += f"\n--- File: {path}, Lines: 1-{len(lines)}/{total_lines} ---"
            return result

        except FileNotFoundError:
            return f"[ERROR] File not found: {path}"
        except UnicodeDecodeError:
            return f"[ERROR] Cannot decode file with {encoding}"
        except PermissionError:
            return f"[ERROR] Permission denied: {path}"

    @staticmethod
    def list_directory(args: dict) -> str:
        """列出目录"""
        path = args["path"]
        recursive = args.get("recursive", False)
        show_hidden = args.get("show_hidden", False)

        try:
            if recursive:
                lines = []
                for root, dirs, files in os.walk(path):
                    if not show_hidden:
                        dirs[:] = [d for d in dirs if not d.startswith(".")]
                        files = [f for f in files if not f.startswith(".")]

                    rel_root = os.path.relpath(root, path)
                    lines.append(f"{rel_root}/")
                    lines.extend(f"  {d}/" for d in dirs)
                    lines.extend(f"  {f}" for f in files)
                return "\n".join(lines)

            items = os.listdir(path)
            if not show_hidden:
                items = [i for i in items if not i.startswith(".")]

            lines = [
                f"{item}/" if os.path.isdir(os.path.join(path, item)) else item
                for item in sorted(items)
            ]
            return "\n".join(lines)

        except FileNotFoundError:
            return f"[ERROR] Directory not found: {path}"
        except PermissionError:
            return f"[ERROR] Permission denied: {path}"

    @staticmethod
    def find_file(args: dict) -> str:
        """查找文件"""
        path = args["path"]
        pattern = args["pattern"]
        max_depth = args.get("max_depth", 10)

        try:
            matches: list[str] = []
            for root, dirs, files in os.walk(path):
                depth = root[len(path) :].count(os.sep)
                if depth > max_depth:
                    dirs[:] = []  # 不再深入
                    continue

                matches.extend(
                    os.path.join(root, f)
                    for f in files
                    if pattern in f or f.endswith(pattern)
                )

            if not matches:
                return f"No files matching '{pattern}' found in {path}"

            return "\n".join(matches)

        except FileNotFoundError:
            return f"[ERROR] Directory not found: {path}"
        except PermissionError:
            return f"[ERROR] Permission denied: {path}"

    @staticmethod
    def grep_search(args: dict) -> str:
        """搜索文件内容"""
        pattern = args["pattern"]
        path = args["path"]
        file_pattern = args.get("file_pattern", "*")

        try:
            results = []
            regex = re.compile(pattern, re.IGNORECASE)

            for root, _, files in os.walk(path):
                for f in files:
                    if not fnmatch.fnmatch(f, file_pattern):
                        continue

                    file_path = os.path.join(root, f)
                    try:
                        with open(file_path, encoding="utf-8") as fp:
                            for i, line in enumerate(fp, 1):
                                if regex.search(line):
                                    results.append(f"{file_path}:{i}:{line.strip()}")
                    except (UnicodeDecodeError, PermissionError):
                        continue

            if not results:
                return f"No matches for '{pattern}' in {path}"

            return "\n".join(results[:100])  # 限制输出

        except FileNotFoundError:
            return f"[ERROR] Path not found: {path}"

    @staticmethod
    def create_directory(args: dict) -> str:
        """创建目录"""
        path = args["path"]
        parents = args.get("parents", True)

        try:
            if parents:
                os.makedirs(path, exist_ok=True)
            else:
                os.mkdir(path)

            return f"[OK] Created directory: {path}"

        except FileExistsError:
            return f"[ERROR] Directory already exists: {path}"
        except PermissionError:
            return f"[ERROR] Permission denied: {path}"

    @staticmethod
    def delete_file(args: dict) -> str:
        """删除文件"""
        path = args["path"]

        try:
            os.remove(path)
            return f"[OK] Deleted file: {path}"

        except FileNotFoundError:
            return f"[ERROR] File not found: {path}"
        except PermissionError:
            return f"[ERROR] Permission denied: {path}"

    @staticmethod
    def delete_directory(args: dict) -> str:
        """删除目录"""
        path = args["path"]
        recursive = args.get("recursive", False)

        try:
            if recursive:
                shutil.rmtree(path)
            else:
                os.rmdir(path)

            return f"[OK] Deleted directory: {path}"

        except FileNotFoundError:
            return f"[ERROR] Directory not found: {path}"
        except OSError as e:
            if "not empty" in str(e).lower():
                return f"[ERROR] Directory not empty: {path}"
            return f"[ERROR] {e}"
        except PermissionError:
            return f"[ERROR] Permission denied: {path}"

    @staticmethod
    def copy_file(args: dict) -> str:
        """复制文件"""
        src = args["src"]
        dst = args["dst"]
        overwrite = args.get("overwrite", False)

        try:
            if not overwrite and os.path.exists(dst):
                return f"[ERROR] Destination exists: {dst}"

            shutil.copy2(src, dst)
            return f"[OK] Copied {src} → {dst}"

        except FileNotFoundError:
            return f"[ERROR] Source not found: {src}"
        except PermissionError:
            return "[ERROR] Permission denied"

    @staticmethod
    def move_file(args: dict) -> str:
        """移动文件"""
        src = args["src"]
        dst = args["dst"]
        overwrite = args.get("overwrite", False)

        try:
            if not overwrite and os.path.exists(dst):
                return f"[ERROR] Destination exists: {dst}"

            shutil.move(src, dst)
            return f"[OK] Moved {src} → {dst}"

        except FileNotFoundError:
            return f"[ERROR] Source not found: {src}"
        except PermissionError:
            return "[ERROR] Permission denied"

    # === 代码执行实现 ===

    @staticmethod
    def run_python(args: dict) -> str:
        """执行 Python 脚本（安全：清理环境变量）"""
        script_path = args["script_path"]
        script_args = args.get("args", [])
        timeout = args.get("timeout", 60)

        try:
            cmd = ["python", script_path, *script_args]
            # 安全：清理环境变量，移除敏感凭证
            safe_env = _get_safe_env()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=safe_env,  # 使用清理后的环境
            )

            output = result.stdout
            if result.stderr:
                output += "\n[Stderr]\n" + result.stderr
            if result.returncode != 0:
                output += f"\n[Exit Code: {result.returncode}]"

            return output if output.strip() else "[OK] Script executed successfully"

        except subprocess.TimeoutExpired:
            return f"[ERROR] Timeout ({timeout}s)"
        except FileNotFoundError:
            return f"[ERROR] Script not found: {script_path}"

    @staticmethod
    def run_test(args: dict) -> str:
        """执行测试（安全：清理环境变量）"""
        test_path = args["test_path"]
        options = args.get("options", [])
        timeout = args.get("timeout", 120)

        try:
            cmd = ["pytest", test_path, *options]
            # 安全：清理环境变量，移除敏感凭证
            safe_env = _get_safe_env()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=safe_env,  # 使用清理后的环境
            )

            return result.stdout if result.stdout.strip() else "[OK] Tests passed"

        except subprocess.TimeoutExpired:
            return f"[ERROR] Timeout ({timeout}s)"
        except FileNotFoundError:
            return "[ERROR] pytest not installed"

    @staticmethod
    def install_package(args: dict) -> str:
        """安装包"""
        package = args["package"]
        version = args.get("version")
        index = args.get("index", "https://pypi.org/simple")

        try:
            if version:
                package = f"{package}=={version}"

            cmd = ["pip", "install", package, "--index-url", index]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                return f"[OK] Installed: {package}"
            return f"[ERROR] Install failed: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "[ERROR] Timeout (60s)"

    # === Git 操作实现 ===

    @staticmethod
    def git_status(args: dict) -> str:
        """Git status"""
        try:
            result = subprocess.run(
                ["git", "status"],
                capture_output=True,
                text=True,
            )
            return (
                result.stdout
                if result.stdout.strip()
                else "[OK] Clean working tree"
            )
        except FileNotFoundError:
            return "[ERROR] git not installed"

    @staticmethod
    def git_diff(args: dict) -> str:
        """Git diff"""
        file = args.get("file")
        staged = args.get("staged", False)

        try:
            cmd = ["git", "diff"]
            if staged:
                cmd.append("--staged")
            if file:
                cmd.append(file)

            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.stdout if result.stdout.strip() else "[OK] No changes"
        except FileNotFoundError:
            return "[ERROR] git not installed"

    @staticmethod
    def git_log(args: dict) -> str:
        """Git log"""
        count = args.get("count", 10)
        oneline = args.get("oneline", True)

        try:
            cmd = ["git", "log", f"-{count}"]
            if oneline:
                cmd.append("--oneline")

            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.stdout
        except FileNotFoundError:
            return "[ERROR] git not installed"

    @staticmethod
    def git_commit(args: dict) -> str:
        """Git commit"""
        message = args["message"]
        amend = args.get("amend", False)

        try:
            cmd = ["git", "commit", "-m", message]
            if amend:
                cmd.append("--amend")

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                return f"[OK] Committed: {message}"
            return f"[ERROR] Commit failed: {result.stderr}"

        except FileNotFoundError:
            return "[ERROR] git not installed"

    @staticmethod
    def git_push(args: dict) -> str:
        """Git push"""
        branch = args.get("branch")
        remote = args.get("remote", "origin")
        force = args.get("force", False)

        try:
            cmd = ["git", "push", remote]
            if branch:
                cmd.append(branch)
            if force:
                cmd.append("--force")

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                return f"[OK] Pushed to {remote}"
            return f"[ERROR] Push failed: {result.stderr}"

        except FileNotFoundError:
            return "[ERROR] git not installed"

    @staticmethod
    def git_pull(args: dict) -> str:
        """Git pull"""
        branch = args.get("branch")
        remote = args.get("remote", "origin")

        try:
            cmd = ["git", "pull", remote]
            if branch:
                cmd.append(branch)

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                return f"[OK] Pulled from {remote}"
            return f"[ERROR] Pull failed: {result.stderr}"

        except FileNotFoundError:
            return "[ERROR] git not installed"

    @staticmethod
    def git_branch(args: dict) -> str:
        """Git branch"""
        action = args["action"]
        name = args.get("name")

        try:
            cmd = ["git", "branch"]
            if action == "create" and name:
                cmd.append(name)
            elif action == "delete" and name:
                cmd.extend(["-d", name])

            result = subprocess.run(cmd, capture_output=True, text=True)

            if action == "list":
                return result.stdout
            if result.returncode == 0:
                return f"[OK] Branch {action}: {name}"
            return f"[ERROR] Branch {action} failed: {result.stderr}"

        except FileNotFoundError:
            return "[ERROR] git not installed"

    # === 系统信息实现 ===

    @staticmethod
    def get_env_info(args: dict) -> str:
        """获取环境信息（安全：过滤敏感变量）

        安全：不暴露敏感环境变量（API Key、Token、密码等）
        """
        filter_pattern = args.get("filter")
        sensitive_vars = _get_sensitive_env_vars()

        # 获取环境变量并过滤敏感项（使用公共常量）
        env_vars = {}
        for k, v in os.environ.items():
            # 检查是否为敏感变量
            is_sensitive = False
            for sensitive in sensitive_vars:
                if (
                    sensitive.lower() in k.lower()
                    or k.lower().endswith("_key")
                    or k.lower().endswith("_token")
                ):
                    is_sensitive = True
                    break
            if not is_sensitive:
                env_vars[k] = v

        if filter_pattern:
            env_vars = {
                k: v
                for k, v in env_vars.items()
                if filter_pattern.lower() in k.lower()
            }

        lines = [f"{k}={v}" for k, v in sorted(env_vars.items())]
        return "\n".join(lines[:50])  # 限制输出

    @staticmethod
    def get_disk_usage(args: dict) -> str:
        """获取磁盘使用情况"""
        path = args.get("path", "/")
        try:
            total, used, free = shutil.disk_usage(path)
            return (
                f"Total: {total // (1024**3)} GB\n"
                f"Used: {used // (1024**3)} GB\n"
                f"Free: {free // (1024**3)} GB\n"
                f"Usage: {used * 100 // total}%"
            )
        except FileNotFoundError:
            return f"[ERROR] Path not found: {path}"


# 实现函数映射表
TOOL_IMPLEMENTATIONS: dict[str, Callable] = {
    "read_file_content": ToolImplementations.read_file,
    "list_directory": ToolImplementations.list_directory,
    "find_file": ToolImplementations.find_file,
    "grep_search": ToolImplementations.grep_search,
    "create_directory": ToolImplementations.create_directory,
    "delete_file": ToolImplementations.delete_file,
    "delete_directory": ToolImplementations.delete_directory,
    "copy_file": ToolImplementations.copy_file,
    "move_file": ToolImplementations.move_file,
    "run_python_script": ToolImplementations.run_python,
    "run_test": ToolImplementations.run_test,
    "install_package": ToolImplementations.install_package,
    "git_status": ToolImplementations.git_status,
    "git_diff": ToolImplementations.git_diff,
    "git_log": ToolImplementations.git_log,
    "git_commit": ToolImplementations.git_commit,
    "git_push": ToolImplementations.git_push,
    "git_pull": ToolImplementations.git_pull,
    "git_branch": ToolImplementations.git_branch,
    "get_env_info": ToolImplementations.get_env_info,
    "get_disk_usage": ToolImplementations.get_disk_usage,
}