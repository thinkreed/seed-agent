"""
OpenTelemetry Tracing Helpers

提供:
1. Span 创建和属性设置
2. 错误记录和分类
3. asyncio context 传播
4. 装饰器封装

Span 层级:
- seed.session (Root Span)
- seed.llm.request (LLM 调用)
- seed.llm.fallback (Provider 切换)
- seed.tool.{name} (工具调用)
- seed.subagent.execute (Subagent 执行)

重构说明：
- 常量定义移至 _tracing_constants.py
- 错误处理移至 _tracing_error.py
- Context 传播移至 _tracing_context.py
- Span 创建移至 _tracing_span.py
- 属性设置移至 _tracing_attributes.py
"""

# 从拆分模块导入所有功能
from ._tracing_attributes import (
    add_fallback_event,
    set_llm_span_attributes,
    set_subagent_span_attributes,
    set_tool_span_attributes,
)
from ._tracing_constants import (
    SPAN_LLM_FALLBACK,
    SPAN_LLM_REQUEST,
    SPAN_SESSION,
    SPAN_SUBAGENT_EXECUTE,
    SPAN_TOOL_PREFIX,
    SpanAttributeValue,
)
from ._tracing_context import create_task_with_context
from ._tracing_error import classify_error, record_llm_span_error
from ._tracing_span import start_as_current_span, start_span, traced

__all__ = [
    # 常量
    "SPAN_SESSION",
    "SPAN_LLM_REQUEST",
    "SPAN_LLM_FALLBACK",
    "SPAN_TOOL_PREFIX",
    "SPAN_SUBAGENT_EXECUTE",
    "SpanAttributeValue",
    # 错误处理
    "classify_error",
    "record_llm_span_error",
    # Context 传播
    "create_task_with_context",
    # Span 创建
    "start_span",
    "start_as_current_span",
    "traced",
    # 属性设置
    "add_fallback_event",
    "set_llm_span_attributes",
    "set_tool_span_attributes",
    "set_subagent_span_attributes",
]