"""
Tracing 错误处理模块

错误分类和 Span 错误记录。
"""

from opentelemetry.trace import Span, StatusCode

from ._tracing_constants import ERROR_TYPES


def classify_error(error: Exception) -> str:
    """将异常分类为标准错误类型

    Args:
        error: 异常实例

    Returns:
        错误类型字符串:
        - ratelimit: 429 Rate Limit
        - timeout: 请求超时
        - connection: 网络连接错误
        - context_overflow: 上下文窗口溢出
        - api_error: 其他 API 错误
    """
    error_str = str(error).lower()

    for error_type, keywords in ERROR_TYPES.items():
        if any(kw in error_str for kw in keywords):
            return error_type

    return "api_error"


def record_llm_span_error(span: Span, error: Exception) -> str:
    """在 Span 上记录 LLM 错误

    Args:
        span: OpenTelemetry Span
        error: 异常实例

    Returns:
        错误类型字符串
    """
    error_type = classify_error(error)
    error_msg = str(error)

    # 截断错误消息至 500 字符
    truncated_msg = error_msg[:500] if len(error_msg) > 500 else error_msg

    span.record_exception(error)
    span.set_attribute("seed.error.type", error_type)
    span.set_attribute("seed.error.message", truncated_msg)
    span.set_status(StatusCode.ERROR, error_msg[:200])

    return error_type