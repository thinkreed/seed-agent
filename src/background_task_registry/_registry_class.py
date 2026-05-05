"""后台任务注册表类模块

包含 BackgroundTaskRegistry 类定义，组合所有 mixins。
"""

import asyncio
import logging
import threading

from src.background_task_registry._cancel import CancelMixin
from src.background_task_registry._lifecycle import LifecycleMixin
from src.background_task_registry._query import QueryMixin
from src.background_task_registry._types import BackgroundTaskEntry

logger = logging.getLogger(__name__)


class BackgroundTaskRegistry(LifecycleMixin, CancelMixin, QueryMixin):
    """后台任务注册表

    参考 qwen-code 的 background-tasks.ts 实现

    核心功能：
    - 任务注册和生命周期管理
    - 取消信号传播
    - 优雅期等待
    - 状态查询

    使用示例：
        registry = BackgroundTaskRegistry()

        # 注册任务
        entry = registry.register("task_123", "Long running task")

        # 开始执行
        registry.start("task_123")

        # 取消任务
        registry.cancel("task_123")

        # 查询状态
        status = registry.get_status("task_123")
    """

    def __init__(self, max_concurrent: int = 3):
        """初始化注册表

        Args:
            max_concurrent: 最大并发任务数
        """
        self._tasks: dict[str, BackgroundTaskEntry] = {}
        self._max_concurrent = max_concurrent
        self._lock = threading.Lock()
        self._async_lock = asyncio.Lock()

        logger.info(
            f"BackgroundTaskRegistry initialized: max_concurrent={max_concurrent}"
        )


__all__ = ["BackgroundTaskRegistry"]