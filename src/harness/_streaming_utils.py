"""
Harness 流式处理工具函数

提取流式处理相关的工具函数。

内容:
- process_tool_delta - 处理流式 Tool Call 增量
- check_cancelled - 检查取消信号
- get_cancel_reason - 获取取消原因
- collect_tool_calls - 从累积器收集工具调用
"""

from typing import Any

from src.abort_signal import AbortSignal


def process_tool_delta(
    tc_list: list[dict[str, Any]],
    accumulator: dict[int, dict[str, Any]],
) -> None:
    """处理流式 Tool Call 增量

    Args:
        tc_list: Tool Call 增量列表
        accumulator: 累积器字典
    """
    for tc in tc_list:
        idx = tc.get("index", 0)
        if idx not in accumulator:
            accumulator[idx] = {
                "id": tc.get("id"),
                "type": tc.get("type", "function"),
                "function": {"name": "", "arguments": ""},
            }
        acc = accumulator[idx]
        if tc.get("id"):
            acc["id"] = tc["id"]
        if tc.get("type"):
            acc["type"] = tc["type"]
        func = tc.get("function", {})
        if func.get("name"):
            acc["function"]["name"] = func["name"]
        if func.get("arguments"):
            acc["function"]["arguments"] += func["arguments"]


def check_cancelled(signal: AbortSignal | None) -> bool:
    """检查取消信号

    Args:
        signal: 取消信号（可为 None）

    Returns:
        是否已取消
    """
    return signal is not None and signal.aborted


def get_cancel_reason(signal: AbortSignal | None) -> str:
    """获取取消原因

    Args:
        signal: 取消信号（可为 None）

    Returns:
        取消原因
    """
    return signal.reason if signal else "unknown"


def collect_tool_calls(
    accumulator: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    """从累积器收集工具调用

    Args:
        accumulator: 工具调用累积器

    Returns:
        工具调用列表（按 index 排序）
    """
    if not accumulator:
        return []
    return [accumulator[i] for i in sorted(accumulator.keys())]