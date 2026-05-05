"""自主探索模块：空闲时根据 SOP 执行自主任务

增强版 (Ralph Loop + Memory Graph 集成):
- completion_promise 检测：外部完成标志驱动退出
- 可选上下文重置：防止上下文漂移
- 防无限循环上限：迭代和时间双重保护
- Memory Graph 选择：基于历史结果选择最佳 Skill
- 自动结果记录：执行完成后自动记录 outcome
- Session 事件记录：所有状态变更通过 Session 正确记录

子模块架构:
- _explorer: 主类实现（向后兼容）
- _idle_monitor: 空闲监控
- _sop_loader: SOP 加载
- _prompt_builder: Prompt 构建
- _task_executor: 任务执行
- _state_manager: 状态管理
- _defense: 四层防御

公共 API:
- AutonomousExplorer: 主类（向后兼容）
- create_autonomous_explorer: 工厂函数
- RALPH_MAX_ITERATIONS: 安全上限
- RALPH_MAX_DURATION: 最大执行时间
"""

# 导出主类和公共 API
# 导出测试 mock 需要的函数（使用冗余别名避免 ruff F401）
from src.shared_config import (
    get_seed_dir_with_fallback as _ensure_seed_dir,  # noqa: F401
)

from ._defense import (
    DefenseState,
    check_completion_promise,
)
from ._explorer import (
    AutonomousExplorer,
    create_autonomous_explorer,
)

# 内部函数导出（用于测试 mock）
from ._explorer import _get_completion_promise_file as _get_completion_promise_file
from ._idle_monitor import IdleMonitor
from ._prompt_builder import (
    build_autonomous_prompt,
    build_task_instruction,
    extract_task_signals,
)
from ._sop_loader import (
    expand_sop_paths,
    get_project_root,
    get_sop_path,
    load_sop,
)
from ._state_manager import (
    StateManager,
    TodoCache,
)

# 导出常量
from ._task_executor import (
    COMPLETION_MARKERS,
    RALPH_MAX_DURATION,
    RALPH_MAX_ITERATIONS,
    TaskExecutor,
)

__all__ = [
    "COMPLETION_MARKERS",
    "RALPH_MAX_DURATION",
    # 常量
    "RALPH_MAX_ITERATIONS",
    # 主类
    "AutonomousExplorer",
    "DefenseState",
    # 子模块类
    "IdleMonitor",
    "StateManager",
    "TaskExecutor",
    "TodoCache",
    "build_autonomous_prompt",
    "build_task_instruction",
    # 工具函数
    "check_completion_promise",
    "create_autonomous_explorer",
    "expand_sop_paths",
    "extract_task_signals",
    "get_project_root",
    "get_sop_path",
    "load_sop",
]