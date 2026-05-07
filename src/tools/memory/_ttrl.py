"""TTRL 持续学习模块入口 (Wiki 知识落地 P2: MIA)

模块拆分：
- _ttrl_types.py: 枚举和数据类型
- _ttrl_processor.py: TTRLProcessor 核心逻辑
- _ttrl_api.py: 公共 API 函数

基于 MIA Test-Time Reinforcement Learning 设计：
- 推理时学习（无需额外训练数据）
- 记忆整合流程（batch_evaluate → consolidate_memories）
- Executor/Planner 训练机制
- Win Rate 统计和检索优化

流程：
1. 执行任务 → 产生 trace 和 judgement
2. batch_memory_save → 存储到缓冲区
3. batch_evaluate → 评估 reward 信号
4. consolidate_memories → 整合到主记忆库
"""

# 导入所有模块
from ._ttrl_api import (
    get_ttrl_processor,
    ttrl_add_memory,
    ttrl_add_trace,
    ttrl_batch_evaluate,
    ttrl_consolidate,
    ttrl_get_stats,
)
from ._ttrl_processor import TTRLProcessor
from ._ttrl_types import (
    ConsolidationResult,
    ExecutionTrace,
    JudgementType,
    MemoryEntry,
    MemorySource,
)

__all__ = [
    "ConsolidationResult",
    "ExecutionTrace",
    # 枚举和类型
    "JudgementType",
    "MemoryEntry",
    "MemorySource",
    # 处理器
    "TTRLProcessor",
    "get_ttrl_processor",
    "ttrl_add_memory",
    # 公共 API
    "ttrl_add_trace",
    "ttrl_batch_evaluate",
    "ttrl_consolidate",
    "ttrl_get_stats",
]