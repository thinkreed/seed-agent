"""SubagentManager - 结果管理模块

负责:
- 结果收集与存储
- 结果聚合与过滤
- 事件驱动等待
"""

import asyncio
import logging
import threading

from src.subagent import SubagentResult, SubagentState
from src.subagent_manager_core._task import SubagentTask

logger = logging.getLogger(__name__)


class ResultsManager:
    """结果管理器"""

    def __init__(self):
        self._results: dict[str, SubagentResult] = {}
        self._result_condition = asyncio.Condition()
        self._dict_sync_lock = threading.Lock()

    def store_result(self, task_id: str, result: SubagentResult) -> None:
        """存储结果"""
        with self._dict_sync_lock:
            self._results[task_id] = result

    async def notify_result_stored(self) -> None:
        """通知结果已存储"""
        async with self._result_condition:
            self._result_condition.notify_all()

    def get_result(self, task_id: str) -> SubagentResult | None:
        """获取结果"""
        with self._dict_sync_lock:
            return self._results.get(task_id)

    def get_all_results(self) -> dict[str, SubagentResult]:
        """获取所有结果"""
        with self._dict_sync_lock:
            return self._results.copy()

    async def wait_for_result_async(
        self, task_id: str, timeout: float | None = None
    ) -> SubagentResult | None:
        """等待任务完成"""
        async with self._result_condition:
            try:
                await asyncio.wait_for(
                    self._result_condition.wait_for(lambda: task_id in self._results),
                    timeout=timeout,
                )
            except TimeoutError:
                return None
            return self._results.get(task_id)

    def aggregate_results(
        self,
        task_ids: list[str],
        results: dict[str, SubagentResult],
        tasks: dict[str, SubagentTask],
        include_errors: bool = True,
        max_length: int = 2000,
    ) -> str:
        """聚合多个任务的结果"""
        if max_length <= 0:
            raise ValueError("max_length must be positive")

        summaries: list[str] = []
        for task_id in task_ids:
            result = results.get(task_id)
            task = tasks.get(task_id)

            if not result:
                summaries.append(f"[{task_id}] Not found")
                continue

            if result.success:
                content = result.result or ""
                if len(content) > max_length:
                    content = content[:max_length] + "...(truncated)"
                summaries.append(f"[{task_id}] SUCCESS:\n{content}")
            elif include_errors:
                error_msg = result.error or "Unknown error"
                summaries.append(f"[{task_id}] {result.state.status.upper()}: {error_msg}")

        return "\n\n---\n\n".join(summaries)

    def cleanup(self, task_id: str | None = None) -> None:
        """清理结果"""
        with self._dict_sync_lock:
            if task_id:
                self._results.pop(task_id, None)
            else:
                self._results.clear()