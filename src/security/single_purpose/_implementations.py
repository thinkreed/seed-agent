"""
单用途工具实现方法

包含所有 _impl_* 方法的具体实现

重构说明:
- 原实现已拆分为独立模块以提高可维护性
- 此文件保持向后兼容，从新模块导入所有内容

模块结构:
- _implementations_types.py: 类型定义和辅助函数
- _file_ops.py: 文件操作实现
- _code_exec.py: 代码执行实现
- _git_ops.py: Git 操作实现
- _sys_info.py: 系统信息实现
- _implementations_core.py: 核心整合模块
"""

# 从核心模块导入所有内容（向后兼容）
from src.security.single_purpose._implementations_core import (
    TOOL_IMPLEMENTATIONS,
    ToolImplementations,
)

# 从类型模块导入辅助函数（向后兼容）
from src.security.single_purpose._implementations_types import (
    _get_sensitive_env_vars,
    _get_safe_env,
)

__all__ = [
    "ToolImplementations",
    "TOOL_IMPLEMENTATIONS",
    "_get_sensitive_env_vars",
    "_get_safe_env",
]