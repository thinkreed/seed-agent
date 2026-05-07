"""多智能体协作模块 - 多脑多手编排器

重构版本：原大文件已拆分为多个小模块
此文件保留为向后兼容的导入入口

模块结构:
- _orchestrator.py: 核心编排器类 (~85 行)
- _pair_executor.py: 组合执行逻辑 (~100 行)
- _result_merger.py: 结果合并逻辑 (~70 行)
- _task_coordinator.py: 任务协调逻辑 (~90 行)

总计: 4 个模块，每个均 < 150 行
"""

# 向后兼容：从新模块导入并导出
from src.collaboration._multi_brain_multi_hand._orchestrator import (
    MultiBrainMultiHandOrchestrator,
)
from src.collaboration._multi_brain_multi_hand._task_coordinator import (
    MAX_DYNAMIC_ITERATIONS,
)

__all__ = ["MAX_DYNAMIC_ITERATIONS", "MultiBrainMultiHandOrchestrator"]