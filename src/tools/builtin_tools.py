"""
Builtin 工具模块 - 兼容层

此文件已重构为 src/tools/builtin/ 子包。
所有功能从子模块导入，保持向后兼容性。

迁移指南:
- 原 builtin_tools.py -> src/tools/builtin/__init__.py
- 新导入: from src.tools.builtin import file_read, register_builtin_tools
- 或: from src.tools.builtin import * (获取所有公共 API)

子模块结构:
- _path_validation.py: 路径安全验证
- _file_operations.py: 文件操作工具
- _code_execution.py: 代码执行工具
- _ask_user.py: 用户交互机制
- utils.py: 通用工具函数

版本: v2.0 (拆分重构版 - 向后兼容)
"""

# 从新的子包导入所有功能
# 从 ask_user_types 导入状态管理函数
from src.tools.ask_user_types import (
    clear_ask_user_state,
    get_ask_user_state,
    get_pending_ask_user_request,
    reset_ask_user_state,
)
from src.tools.builtin import (
    # 用户交互
    ask_user,
    # 代码执行
    code_as_policy,
    code_as_policy_async,
    file_edit,
    # 文件操作
    file_read,
    file_write,
    # 注册
    register_builtin_tools,
)
from src.tools.builtin._code_execution import (
    DEFAULT_EXECUTION_TIMEOUT,
    MAX_CODE_LENGTH,
    POWERSHELL_BLACKLIST,
    SHELL_BLACKLIST,
    _build_command,
    _check_code_security,
    _format_execution_result,
    _resolve_execution_cwd,
)

# 从子模块导入私有函数（供测试使用）
from src.tools.builtin._path_validation import (
    ALLOWED_DIRS,
    DEFAULT_WORK_DIR,
    DEFAULT_WORK_DIR_RESOLVED,
    PROJECT_ROOT,
    PROJECT_ROOT_RESOLVED,
    _is_path_in_allowed_dirs,
    _resolve_path,
    _validate_path_safety,
)


# 诊断运行函数（供测试使用）
def run_diagnosis() -> str:
    """诊断运行 - 检查模块状态"""
    import logging
    logger = logging.getLogger("seed_agent.diagnosis")
    logger.info("Running diagnosis...")
    return "Diagnosis complete: all modules imported successfully"


# 导出所有公共 API（保持向后兼容）
__all__ = [
    "ALLOWED_DIRS",
    "DEFAULT_EXECUTION_TIMEOUT",
    "DEFAULT_WORK_DIR",
    "DEFAULT_WORK_DIR_RESOLVED",
    "MAX_CODE_LENGTH",
    "POWERSHELL_BLACKLIST",
    "PROJECT_ROOT",
    "PROJECT_ROOT_RESOLVED",
    "SHELL_BLACKLIST",
    "_build_command",
    # 代码执行（私有函数，供测试）
    "_check_code_security",
    "_format_execution_result",
    "_is_path_in_allowed_dirs",
    "_resolve_execution_cwd",
    # 路径验证（私有函数，供测试）
    "_resolve_path",
    "_validate_path_safety",
    # 用户交互
    "ask_user",
    # 状态管理
    "clear_ask_user_state",
    # 代码执行
    "code_as_policy",
    "code_as_policy_async",
    "file_edit",
    # 文件操作
    "file_read",
    "file_write",
    "get_ask_user_state",
    "get_pending_ask_user_request",
    # 注册
    "register_builtin_tools",
    "reset_ask_user_state",
    # 诊断
    "run_diagnosis",
]