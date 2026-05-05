"""
Ask User 数据类型定义

模块拆分:
- ask_user_types_core/_types.py: 问题类型和选项定义
- ask_user_types_core/_request.py: AskUserRequest
- ask_user_types_core/_result.py: AskUserResult
- ask_user_types_core/_state.py: AskUserState

核心特性：
- 结构化问题定义
- 多选支持
- 自定义输入支持
"""

# 导入拆分后的模块
from src.tools.ask_user_types_core import (
    AskUserRequest,
    AskUserResult,
    AskUserState,
    clear_ask_user_state,
    get_ask_user_state,
    get_pending_ask_user_request,
    Question,
    QuestionOption,
    QuestionType,
    reset_ask_user_state,
    UserResponse,
)

__all__ = [
    "QuestionType",
    "QuestionOption",
    "Question",
    "UserResponse",
    "AskUserRequest",
    "AskUserResult",
    "AskUserState",
    "get_ask_user_state",
    "reset_ask_user_state",
    "clear_ask_user_state",
    "get_pending_ask_user_request",
]