"""取消信号核心模块

导出 AbortSignal, AbortController, CancellationToken 等类型。
"""

from ._abort_signal import AbortController, AbortSignal
from ._cancellation_token import (
    CancellationToken,
    CompositeCancellationToken,
    TimeoutCancellationToken,
    create_linked_token,
)

__all__ = [
    "AbortController",
    "AbortSignal",
    "CancellationToken",
    "CompositeCancellationToken",
    "TimeoutCancellationToken",
    "create_linked_token",
]