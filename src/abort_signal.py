"""
AbortSignal 模块 - 取消信号控制

重构说明：
- 类型定义移至 abort_signal_core/_abort_signal.py
- CancellationToken 相关移至 abort_signal_core/_cancellation_token.py
- 主文件只保留向后兼容导入

基于 qwen-code 的 AbortController Pattern 设计：
- 每个任务关联一个 AbortController
- 取消时调用 abort() 发送信号
- 各执行点检查 signal.aborted 状态
"""

# 从子模块导入并导出（向后兼容）
from src.abort_signal_core import (
    AbortController,
    AbortSignal,
    CancellationToken,
    CompositeCancellationToken,
    TimeoutCancellationToken,
    create_linked_token,
)

__all__ = [
    "AbortSignal",
    "AbortController",
    "CancellationToken",
    "TimeoutCancellationToken",
    "CompositeCancellationToken",
    "create_linked_token",
]