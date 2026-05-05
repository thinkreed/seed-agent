"""Harness 循环工具函数

包含取消信号检查等辅助函数。
"""

from src.abort_signal import AbortSignal


def _check_cancelled(signal: AbortSignal | None) -> bool:
    """检查取消信号"""
    return signal is not None and signal.aborted


def _get_cancel_reason(signal: AbortSignal | None) -> str:
    """获取取消原因"""
    return signal.reason if signal else "unknown"