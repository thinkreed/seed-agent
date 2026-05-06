"""SubagentManager - 状态管理模块

负责:
- 状态查询
- 状态回调通知
- 任务列表
"""

import logging
import threading
from collections.abc import Callable

from src.subagent import SubagentResult, SubagentState, SubagentType
from src.subagent_manager_core._task import SubagentTask

logger = logging.getLogger(__name__)


class StatusManager:
    """状态管理器"""

    def __init__(self):
        self._status_callbacks: list[Callable[[str, str], None]] = []
        self._dict_sync_lock = threading.Lock()

    def register_callback(self, callback: Callable[[str, str], None]) -> None:
        """注册状态变更回调"""
        self._status_callbacks.append(callback)

    def notify_status(self, task_id: str, status: str) -> None:
        """通知状态变更"""
        for callback in self._status_callbacks:
            try:
                callback(task_id, status)
            except Exception as e:
                logger.warning(f"Status callback error: {type(e).__name__}: {e}")

    def get_status(
        self,
        task_id: str,
        results: dict[str, SubagentResult],
        instances: dict,
        tasks: dict[str, SubagentTask],
    ) -> str | None:
        """获取任务状态"""
        with self._dict_sync_lock:
            if task_id in results:
                return results[task_id].state.status
            if task_id in instances:
                instance = instances[task_id]
                if instance.state:
                    return instance.state.status
                return "pending"
            if task_id in tasks:
                return "pending"
            return None

    def list_tasks(
        self,
        tasks: dict[str, SubagentTask],
        results: dict[str, SubagentResult],
        instances: dict,
        status_filter: str | None = None,
    ) -> list[dict]:
        """列出所有任务"""
        task_list = []
        with self._dict_sync_lock:
            task_items = list(tasks.items())

        for task_id, task in task_items:
            task_status = self.get_status(task_id, results, instances, tasks)
            if status_filter and task_status != status_filter:
                continue

            task_list.append({
                "id": task_id,
                "type": task.subagent_type.value,
                "status": task_status,
                "prompt_preview": task.prompt[:100] + "..." if len(task.prompt) > 100 else task.prompt,
                "priority": task.priority,
            })

        return task_list