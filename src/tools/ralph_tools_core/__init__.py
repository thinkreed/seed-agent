"""Ralph Loop 工具注册模块

提供工具注册函数：
- register_ralph_tools: 注册所有 Ralph Loop 工具到 Registry

核心特性：
- 统一注册入口
- 路径动态获取
- 类型安全转换
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.tools import ToolRegistry

logger = logging.getLogger(__name__)

from ._completion import (
    _get_completion_promise_file,
    _get_ralph_state_dir,
    write_completion_marker,
)
from ._start import create_ralph_task_file, start_ralph_loop
from ._status import check_ralph_status, stop_ralph_loop


def register_ralph_tools(registry: "ToolRegistry") -> None:
    """注册 Ralph Loop 工具到 Registry"""
    registry.register("start_ralph_loop", start_ralph_loop)
    registry.register("write_completion_marker", write_completion_marker)
    registry.register("check_ralph_status", check_ralph_status)
    registry.register("stop_ralph_loop", stop_ralph_loop)
    registry.register("create_ralph_task_file", create_ralph_task_file)

    logger.info("Ralph tools registered: 5 tools")


__all__ = [
    # 路径获取函数（内部使用，但导出以保持兼容）
    "_get_completion_promise_file",
    "_get_ralph_state_dir",
    "check_ralph_status",
    "create_ralph_task_file",
    # 注册函数
    "register_ralph_tools",
    # 公共工具函数
    "start_ralph_loop",
    "stop_ralph_loop",
    "write_completion_marker",
]