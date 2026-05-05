"""
单用途工具核心模块

整合所有实现模块，提供统一的接口和映射表
"""

import logging
from collections.abc import Callable

from src.security.single_purpose._code_exec import CodeExecution
from src.security.single_purpose._file_ops import FileOperations
from src.security.single_purpose._git_ops import GitOperations
from src.security.single_purpose._sys_info import SystemInfo

logger = logging.getLogger(__name__)


class ToolImplementations:
    """工具实现类

    包含所有单用途工具的具体实现方法
    """

    # === 文件操作实现 ===

    read_file = FileOperations.read_file
    list_directory = FileOperations.list_directory
    find_file = FileOperations.find_file
    grep_search = FileOperations.grep_search
    create_directory = FileOperations.create_directory
    delete_file = FileOperations.delete_file
    delete_directory = FileOperations.delete_directory
    copy_file = FileOperations.copy_file
    move_file = FileOperations.move_file

    # === 代码执行实现 ===

    run_python = CodeExecution.run_python
    run_test = CodeExecution.run_test
    install_package = CodeExecution.install_package

    # === Git 操作实现 ===

    git_status = GitOperations.git_status
    git_diff = GitOperations.git_diff
    git_log = GitOperations.git_log
    git_commit = GitOperations.git_commit
    git_push = GitOperations.git_push
    git_pull = GitOperations.git_pull
    git_branch = GitOperations.git_branch

    # === 系统信息实现 ===

    get_env_info = SystemInfo.get_env_info
    get_disk_usage = SystemInfo.get_disk_usage


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