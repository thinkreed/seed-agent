"""
Tracing 属性设置模块

各种 Span 类型的属性设置函数。
"""

from opentelemetry.trace import Span


def add_fallback_event(
    span: Span,
    from_provider: str,
    to_provider: str,
    reason: str,
    attempt: int,
):
    """在 Span 上添加 Fallback 事件

    Args:
        span: 当前 Span
        from_provider: 原 Provider
        to_provider: 新 Provider
        reason: 切换原因 (error/ratelimit/timeout)
        attempt: 当前尝试次数
    """
    span.add_event(
        "seed.llm.fallback",
        {
            "seed.fallback.from": from_provider,
            "seed.fallback.to": to_provider,
            "seed.fallback.reason": reason,
            "seed.fallback.attempt": attempt,
        },
    )


def set_llm_span_attributes(
    span: Span,
    model: str,
    provider: str,
    streaming: bool = False,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
):
    """设置 LLM Span 的标准属性

    按照 OTel Semantic Conventions 设置属性

    Args:
        span: Span 实例
        model: 模型 ID
        provider: Provider 名称
        streaming: 是否流式响应
        input_tokens: 输入 Token 数
        output_tokens: 输出 Token 数
    """
    span.set_attribute("gen_ai.system", "openai")
    span.set_attribute("gen_ai.request.model", model)
    span.set_attribute("seed.provider", provider)
    span.set_attribute("seed.streaming", streaming)

    if input_tokens is not None:
        span.set_attribute("gen_ai.usage.input_tokens", input_tokens)

    if output_tokens is not None:
        span.set_attribute("gen_ai.usage.output_tokens", output_tokens)


def set_tool_span_attributes(
    span: Span,
    tool_name: str,
    file_path: str | None = None,
    duration_ms: float | None = None,
):
    """设置工具调用 Span 的属性

    Args:
        span: Span 实例
        tool_name: 工具名称
        file_path: 文件路径 (文件操作工具)
        duration_ms: 执行耗时
    """
    span.set_attribute("code.function.name", tool_name)

    if file_path:
        # 脱敏：仅存相对路径
        if len(file_path) > 200:
            file_path = file_path[:200]
        span.set_attribute("seed.tool.file_path", file_path)

    if duration_ms is not None:
        span.set_attribute("seed.tool.duration_ms", duration_ms)


def set_subagent_span_attributes(
    span: Span,
    subagent_type: str,
    task_id: str,
    status: str | None = None,
):
    """设置 Subagent Span 的属性

    Args:
        span: Span 实例
        subagent_type: Subagent 类型 (EXPLORE/REVIEW/IMPLEMENT/PLAN)
        task_id: 任务 ID
        status: 执行状态 (completed/failed/timeout)
    """
    span.set_attribute("seed.subagent.type", subagent_type)
    span.set_attribute("seed.subagent.task_id", task_id)

    if status:
        span.set_attribute("seed.subagent.status", status)