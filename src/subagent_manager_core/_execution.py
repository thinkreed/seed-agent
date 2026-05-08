"""
SubagentManager - 执行模块

负责: 单任务执行、并行调度、异常处理
"""

import asyncio
import logging
import threading

from src.subagent import SubagentInstance, SubagentResult, SubagentState, SubagentType
from src.subagent_manager_core._results import ResultsManager
from src.subagent_manager_core._status import StatusManager
from src.subagent_manager_core._task import SubagentTask

logger = logging.getLogger(__name__)


class SubagentExecutor:
    """Subagent 执行器"""

    def __init__(
        self,
        max_concurrent: int,
        dict_sync_lock: threading.Lock,
        status_manager: StatusManager,
        results_manager: ResultsManager,
    ):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._dict_sync_lock = dict_sync_lock
        self._status_manager = status_manager
        self._results_manager = results_manager

    async def run_single(
        self, task_id: str, task: SubagentTask, instance: SubagentInstance
    ) -> SubagentResult:
        """执行单个任务"""
        async with self._semaphore:
            self._status_manager.notify_status(task_id, "running")
            state = await instance.run(task.prompt, task_id)
            result = SubagentResult(state)
            self._results_manager.store_result(task_id, result)
            await self._results_manager.notify_result_stored()
            self._status_manager.notify_status(task_id, state.status)
            return result

    async def run_parallel(
        self,
        task_ids: list[str],
        tasks: dict[str, SubagentTask],
        instances: dict[str, SubagentInstance],
        get_or_spawn_instance,
        fail_fast: bool = False,
    ) -> dict[str, SubagentResult]:
        """并行执行多个任务"""
        if fail_fast:
            return await self._run_sequential(task_ids, tasks, get_or_spawn_instance)
        return await self._run_concurrent(task_ids, tasks, get_or_spawn_instance)

    async def _run_sequential(
        self, task_ids: list[str], tasks: dict[str, SubagentTask], get_or_spawn_instance
    ) -> dict[str, SubagentResult]:
        """顺序执行（快速失败模式）"""
        results: dict[str, SubagentResult] = {}
        for task_id in task_ids:
            task = tasks.get(task_id)
            if not task:
                continue
            instance = get_or_spawn_instance(task_id)
            result = await self.run_single(task_id, task, instance)
            results[task_id] = result
            if not result.success:
                break
        return results

    async def _run_concurrent(
        self, task_ids: list[str], tasks: dict[str, SubagentTask], get_or_spawn_instance
    ) -> dict[str, SubagentResult]:
        """并发执行"""
        coroutines = []
        valid_task_ids = []
        for task_id in task_ids:
            with self._dict_sync_lock:
                task = tasks.get(task_id)
            if not task:
                continue
            valid_task_ids.append(task_id)
            instance = get_or_spawn_instance(task_id)
            coroutines.append(self.run_single(task_id, task, instance))

        results_list = await asyncio.gather(*coroutines, return_exceptions=True)
        return self._collect_results(valid_task_ids, results_list, tasks)

    def _collect_results(
        self, task_ids: list[str], results_list: list, tasks: dict[str, SubagentTask]
    ) -> dict[str, SubagentResult]:
        """收集执行结果"""
        results: dict[str, SubagentResult] = {}
        for task_id, raw_result in zip(task_ids, results_list, strict=True):
            if isinstance(raw_result, BaseException):
                results[task_id] = self._create_error_result(task_id, raw_result, tasks)
            else:
                results[task_id] = raw_result
        return results

    def _create_error_result(
        self, task_id: str, error: BaseException, tasks: dict[str, SubagentTask]
    ) -> SubagentResult:
        """创建错误结果"""
        with self._dict_sync_lock:
            task = tasks.get(task_id)
        if task:
            state = SubagentState(
                id=task_id, subagent_type=task.subagent_type,
                status="failed", prompt=task.prompt, error=str(error)
            )
        else:
            state = SubagentState(
                id=task_id, subagent_type=SubagentType.EXPLORE,
                status="failed", prompt="", error=str(error)
            )
        return SubagentResult(state)