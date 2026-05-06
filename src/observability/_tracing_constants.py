"""
Tracing 常量定义

Span 名称和错误类型分类常量。
"""

# Span 名称常量
SPAN_SESSION = "seed.session"
SPAN_LLM_REQUEST = "seed.llm.request"
SPAN_LLM_FALLBACK = "seed.llm.fallback"
SPAN_TOOL_PREFIX = "seed.tool."
SPAN_SUBAGENT_EXECUTE = "seed.subagent.execute"

# 错误类型分类关键词
ERROR_TYPES = {
    "ratelimit": ["rate limit", "429"],
    "timeout": ["timeout", "timed out"],
    "connection": ["connection", "connect", "network"],
    "context_overflow": ["context", "overflow", "too long"],
}

# Span 属性值类型
SpanAttributeValue = str | int | float | bool