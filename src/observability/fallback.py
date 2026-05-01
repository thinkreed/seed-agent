"""
OpenTelemetry Fallback 实现

当 OpenTelemetry 未安装时，提供 NoOp 实现以确保代码正常运行。
所有核心模块只需从 observability 导入，无需单独处理 ImportError。

使用方式:
    from src.observability import get_tracer, SPAN_SESSION, StatusCode
    # 自动处理 ImportError，返回 NoOp 实现
"""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

# 类型别名，用于 Span 属性值
SpanAttributeValue = str | int | float | bool

T = TypeVar("T")


# NoOp Span 实现
class NoOpSpan:
    """NoOp Span - 不记录任何数据"""

    def set_attribute(self, key: str, value: SpanAttributeValue) -> None:
        pass

    def add_event(self, name: str, attributes: dict[str, SpanAttributeValue] | None = None) -> None:
        pass

    def record_exception(self, exception: BaseException) -> None:
        pass

    def set_status(self, status: str, description: str | None = None) -> None:
        pass
    
    def end(self) -> None:
        pass
    
    def is_recording(self) -> bool:
        return False


# NoOp Tracer 实现
class NoOpTracer:
    """NoOp Tracer - 不创建真实的 Span"""

    def start_span(self, name: str, context: object = None) -> NoOpSpan:  # type: ignore[override]
        return NoOpSpan()

    def start_as_current_span(
        self,
        name: str,
        attributes: dict[str, SpanAttributeValue] | None = None,
        context: object = None,
    ):
        """返回一个 context manager"""
        class NoOpContextManager:
            def __enter__(self) -> NoOpSpan:
                return NoOpSpan()
            def __exit__(self, *args) -> None:
                pass
        return NoOpContextManager()


# NoOp StatusCode
class NoOpStatusCode:
    """NoOp StatusCode 枚举"""
    UNSET = "UNSET"
    OK = "OK"
    ERROR = "ERROR"


# Span 名称常量（与 tracing.py 保持一致）
SPAN_SESSION = "seed.session"
SPAN_LLM_REQUEST = "seed.llm.request"
SPAN_LLM_FALLBACK = "seed.llm.fallback"
SPAN_TOOL_PREFIX = "seed.tool."
SPAN_SUBAGENT_EXECUTE = "seed.subagent.execute"


# Fallback 函数实现
def get_tracer() -> NoOpTracer:
    """获取 NoOp Tracer"""
    return NoOpTracer()


def get_meter():
    """获取 NoOp Meter"""
    return None


def is_initialized() -> bool:
    """检查是否已初始化（fallback 总是返回 False）"""
    return False


def setup_observability(**kwargs) -> tuple[NoOpTracer, None]:
    """NoOp 初始化"""
    return NoOpTracer(), None


def shutdown_observability() -> None:
    """NoOp 关闭"""
    pass


def classify_error(error: Exception) -> str:
    """错误分类（简化版本）"""
    error_str = str(error).lower()
    if "rate limit" in error_str or "429" in error_str:
        return "ratelimit"
    if "timeout" in error_str:
        return "timeout"
    if "connection" in error_str or "network" in error_str:
        return "connection"
    return "api_error"


def record_llm_span_error(span: NoOpSpan, error: Exception) -> str:
    """在 Span 上记录错误（NoOp）"""
    return classify_error(error)


def record_llm_success(provider: str, model: str, input_tokens: int, output_tokens: int, duration_ms: float) -> None:
    """记录成功（NoOp）"""
    pass


def record_llm_error(provider: str, model: str, duration_ms: float, error_type: str) -> None:
    """记录错误（NoOp）"""
    pass


def add_fallback_event(span: NoOpSpan, from_provider: str, to_provider: str, reason: str, attempt: int) -> None:
    """添加 Fallback 事件（NoOp）"""
    pass


def set_llm_span_attributes(
    span: NoOpSpan, 
    model: str, 
    provider: str, 
    streaming: bool = False,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> None:
    """设置 LLM Span 属性（NoOp）"""
    pass


def set_tool_span_attributes(
    span: NoOpSpan, 
    tool_name: str, 
    file_path: str | None = None,
    duration_ms: float | None = None,
) -> None:
    """设置工具 Span 属性（NoOp）"""
    pass


def set_subagent_span_attributes(
    span: NoOpSpan, 
    subagent_type: str, 
    task_id: str,
    status: str | None = None,
) -> None:
    """设置 Subagent Span 属性（NoOp）"""
    pass


def start_span(name: str, attributes: dict[str, SpanAttributeValue] | None = None) -> NoOpSpan:
    """启动新 Span（NoOp）"""
    return NoOpSpan()


def start_as_current_span(name: str, attributes: dict[str, SpanAttributeValue] | None = None):
    """启动作为当前 Span（NoOp context manager）"""
    class NoOpContextManager:
        def __enter__(self) -> NoOpSpan:
            return NoOpSpan()
        def __exit__(self, *args) -> None:
            pass
    return NoOpContextManager()


def create_task_with_context(coro: Coroutine[Any, Any, T], ctx: object = None) -> asyncio.Task[T]:
    """创建带 context 的 task（fallback 直接创建）"""
    return asyncio.create_task(coro)


def traced(
    name: str | None = None,
    attributes: dict[str, SpanAttributeValue] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """装饰器：创建 Span 包装函数（NoOp 版本直接返回原函数）"""
    return lambda f: f


__all__ = [
    # Types
    "NoOpSpan",
    "NoOpTracer",
    "NoOpStatusCode",
    # Constants
    "SPAN_SESSION",
    "SPAN_LLM_REQUEST",
    "SPAN_LLM_FALLBACK",
    "SPAN_TOOL_PREFIX",
    "SPAN_SUBAGENT_EXECUTE",
    # Functions
    "get_tracer",
    "get_meter",
    "is_initialized",
    "setup_observability",
    "shutdown_observability",
    "classify_error",
    "record_llm_span_error",
    "record_llm_success",
    "record_llm_error",
    "add_fallback_event",
    "set_llm_span_attributes",
    "set_tool_span_attributes",
    "set_subagent_span_attributes",
    "start_span",
    "start_as_current_span",
    "create_task_with_context",
    "traced",
]