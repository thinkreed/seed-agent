"""
HarnessManager 指标计算

提取 get_total_metrics 方法。
"""

from typing import Any


def calculate_total_metrics(harnesses: dict[str, Any]) -> dict[str, Any]:
    """计算所有 Harness 的总指标

    Args:
        harnesses: harness_id -> Harness 字典

    Returns:
        总指标统计
    """
    total_tools = 0
    total_success = 0
    total_failed = 0
    total_duration_ms = 0.0

    for harness in harnesses.values():
        metrics = harness.get_metrics()
        total_tools += len(metrics)
        for m in metrics:
            if m["success"]:
                total_success += 1
            else:
                total_failed += 1
            total_duration_ms += m["duration_ms"]

    return {
        "total_tool_calls": total_tools,
        "successful_calls": total_success,
        "failed_calls": total_failed,
        "total_duration_ms": total_duration_ms,
        "average_duration_ms": total_duration_ms / total_tools if total_tools > 0 else 0,
    }


__all__ = ["calculate_total_metrics"]