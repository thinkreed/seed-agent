"""
NoOp 实现类

当 OpenTelemetry 未安装时，提供 NoOp 类以确保代码正常运行。
"""



# 类型别名，用于 Span 属性值
SpanAttributeValue = str | int | float | bool


class NoOpSpan:
    """NoOp Span - 不记录任何数据"""

    def set_attribute(self, key: str, value: SpanAttributeValue) -> None:
        pass

    def add_event(
        self, name: str, attributes: dict[str, SpanAttributeValue] | None = None
    ) -> None:
        pass

    def record_exception(self, exception: BaseException) -> None:
        pass

    def set_status(self, status: str, description: str | None = None) -> None:
        pass

    def end(self) -> None:
        pass

    def is_recording(self) -> bool:
        return False


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


class NoOpStatusCode:
    """NoOp StatusCode 枚举"""

    UNSET = "UNSET"
    OK = "OK"
    ERROR = "ERROR"


__all__ = [
    "NoOpSpan",
    "NoOpStatusCode",
    "NoOpTracer",
    "SpanAttributeValue",
]