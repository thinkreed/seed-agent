"""Harness 核心循环模块 - 向后兼容入口

提取 run_cycle 和 run_conversation 的核心逻辑。

内容:
- run_cycle_impl - 执行一轮对话循环
- run_conversation_impl - 执行完整对话

所有功能已迁移至子模块：
- _cycle_utils.py: 工具函数
- _cycle_executor.py: 单轮循环执行
- _conversation_executor.py: 对话执行
"""

# 从子模块导入
from src.harness._conversation_executor import run_conversation_impl
from src.harness._cycle_executor import run_cycle_impl
from src.harness._cycle_utils import _check_cancelled, _get_cancel_reason

__all__ = [
    "_check_cancelled",
    "_get_cancel_reason",
    "run_conversation_impl",
    "run_cycle_impl",
]