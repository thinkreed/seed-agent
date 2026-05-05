"""自主探索常量模块

包含自主探索任务执行的配置常量。
"""

# Ralph Loop 增强配置
CONTEXT_RESET_ENABLED = True  # 默认开启
CONTEXT_RESET_INTERVAL = 5  # 每5轮迭代重置
RALPH_MAX_ITERATIONS = 1000  # 理论上限（安全兜底）
RALPH_MAX_DURATION = 8 * 60 * 60  # 8小时最大执行时间（安全兜底）

# 任务完成检测标记（支持多语言）
COMPLETION_MARKERS = [
    "任务完成",
    "已完成",
    "DONE",
    "COMPLETE",
    "FINISHED",
    "done",
    "complete",
    "finished",
]


__all__ = [
    "CONTEXT_RESET_ENABLED",
    "CONTEXT_RESET_INTERVAL",
    "RALPH_MAX_ITERATIONS",
    "RALPH_MAX_DURATION",
    "COMPLETION_MARKERS",
]