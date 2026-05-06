"""Ralph Loop 工具集 - 为 AgentLoop 提供 Ralph Loop 操作接口

模块拆分:
- ralph_tools_core/_completion.py: 完成标志工具
- ralph_tools_core/_start.py: 启动工具
- ralph_tools_core/_status.py: 状态管理工具
- ralph_tools_core/__init__.py: 工具注册

核心工具:
- start_ralph_loop: 启动 Ralph Loop
- write_completion_marker: 写入完成标志
- check_ralph_status: 检查 Ralph Loop 状态
- stop_ralph_loop: 停止 Ralph Loop
- create_ralph_task_file: 创建任务描述文件

类型安全:
- max_iterations 参数在入口处强制转换为整数

路径从 PathsConfig 动态获取。
"""

# 导入拆分后的模块
from src.tools.ralph_tools_core import (
    _get_completion_promise_file,
    _get_ralph_state_dir,
    check_ralph_status,
    create_ralph_task_file,
    register_ralph_tools,
    start_ralph_loop,
    stop_ralph_loop,
    write_completion_marker,
)

# 向后兼容: 导出 safe_int_convert (实际来自 utils.py)
from src.tools.utils import safe_int_convert as _safe_int_convert

__all__ = [
    # 公共工具函数
    "start_ralph_loop",
    "write_completion_marker",
    "check_ralph_status",
    "stop_ralph_loop",
    "create_ralph_task_file",
    # 路径获取函数（内部使用）
    "_get_completion_promise_file",
    "_get_ralph_state_dir",
    # 注册函数
    "register_ralph_tools",
    # 向后兼容
    "_safe_int_convert",
]