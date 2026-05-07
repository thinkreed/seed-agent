"""
生命周期钩子上下文构建器模块

提供各类型生命周期钩子的上下文构建函数。

模块结构:
- _session: 会话钩子上下文 (session_start, session_end)
- _llm: LLM 调用钩子上下文 (llm_call_before, llm_call_after)
- _response: 响应钩子上下文 (response_before, response_after)
- _tool: 工具调用钩子上下文 (tool_call_before, tool_call_after, tool_call_error)
"""

from src.harness.lifecycle_ctx._llm import (
    build_llm_call_after_ctx,
    build_llm_call_before_ctx,
)
from src.harness.lifecycle_ctx._response import (
    build_response_after_ctx,
    build_response_before_ctx,
)
from src.harness.lifecycle_ctx._session import (
    build_session_end_ctx,
    build_session_start_ctx,
)
from src.harness.lifecycle_ctx._tool import (
    build_tool_call_after_ctx,
    build_tool_call_before_ctx,
    build_tool_call_error_ctx,
)

__all__ = [
    "build_llm_call_after_ctx",
    # LLM hooks
    "build_llm_call_before_ctx",
    "build_response_after_ctx",
    # Response hooks
    "build_response_before_ctx",
    "build_session_end_ctx",
    # Session hooks
    "build_session_start_ctx",
    "build_tool_call_after_ctx",
    # Tool hooks
    "build_tool_call_before_ctx",
    "build_tool_call_error_ctx",
]