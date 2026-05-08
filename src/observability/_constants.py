"""
Span 名称常量

与 tracing.py 保持一致的 Span 命名常量。
"""

# Span 名称常量
SPAN_SESSION = "seed.session"
SPAN_LLM_REQUEST = "seed.llm.request"
SPAN_LLM_FALLBACK = "seed.llm.fallback"
SPAN_TOOL_PREFIX = "seed.tool."
SPAN_SUBAGENT_EXECUTE = "seed.subagent.execute"

__all__ = [
    "SPAN_LLM_FALLBACK",
    "SPAN_LLM_REQUEST",
    "SPAN_SESSION",
    "SPAN_SUBAGENT_EXECUTE",
    "SPAN_TOOL_PREFIX",
]