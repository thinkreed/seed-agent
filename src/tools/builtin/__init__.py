"""
Builtin 工具注册

基于 qwen-code ToolRegistry 设计：
- 延迟加载
- 工具 schema 生成
- 注册 5 个核心工具

核心工具：
- file_read: 文件读取
- file_write: 文件写入
- file_edit: 文件编辑
- code_as_policy: 代码执行
- ask_user: 用户交互
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.tools import ToolRegistry

logger = logging.getLogger(__name__)

from ._ask_user import ask_user
from ._code_execution import code_as_policy, code_as_policy_async
from ._file_operations import file_edit, file_read, file_write


def register_builtin_tools(registry: "ToolRegistry") -> None:
    """Register builtin tools to the Agent system.

    注册以下工具:
    - file_read: 文件读取（带行号、编码检测）
    - file_write: 文件写入（覆盖/追加）
    - file_edit: 文件编辑（字符串替换）
    - code_as_policy: 代码执行（Python/JS/Shell/PowerShell）
    - ask_user: 用户交互问答
    """
    registry.register("file_read", file_read)
    registry.register("file_write", file_write)
    registry.register("file_edit", file_edit)
    registry.register("code_as_policy", code_as_policy)
    registry.register("ask_user", ask_user)

    logger.info("Builtin tools registered: 5 tools")


# 导出公共 API
__all__ = [
    # 路径验证
    "_resolve_path",
    "_validate_path_safety",
    # 用户交互
    "ask_user",
    # 代码执行
    "code_as_policy",
    "code_as_policy_async",
    "file_edit",
    # 文件操作
    "file_read",
    "file_write",
    # 注册
    "register_builtin_tools",
]