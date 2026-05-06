"""
SubagentManager - 管理器核心

负责:
- 创建独立 SubagentInstance
- 并行执行调度
- 结果收集与过滤
- 超时管理
- 资源限制

重构说明：
- 结果管理移至 _results.py
- 状态管理移至 _status.py
- 任务定义移至 _task.py
"""

import asyncio
import logging
import threading

from src.client import LLMGateway
from src.subagent import SubagentInstance, SubagentResult, SubagentState, SubagentType
from src.subagent_manager_core._task import SubagentTask, create_task, get_default_timeout
from src.subagent_manager_core._results import ResultsManager
from src.subagent_manager_core._status import StatusManager

logger = logging.getLogger(__name__)


class SubagentManager:
    """Subagent 管理器"""

    DEFAULT_MAX_CONCURRENT = 3
    DEFAULT_TIMEOUT = 300
    DEFAULT_MAX_ITERATIONS = 15

    def __init__(
        self,
        gateway: LLMGateway,
        model_id: str | None = None,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    ):
        self.gateway = gateway
        self.model_id = model_id or self._get_primary_model()
        self.max_concurrent = max_concurrent

        # 活跃的 subagent 实例
        self._instances: dict[str, SubagentInstance] = {}

        # 任务状态跟踪
        self._tasks: dict[str, SubagentTask] = {}

        # 并发控制
        self._semaphore = asyncio.Semaphore(max_concurrent)

        # 字典操作锁
        self._dict_sync_lock = threading.Lock()

        # 拆分模块组件
        self._results_manager = ResultsManager()
        self._status_manager = StatusManager()

    # === 向后兼容属性 ===

    @property
    def _results(self) -> dict[str, SubagentResult]:
        return self._results_manager._results

    @_results.setter
    def _results(self, value: dict[str, SubagentResult]) -> None:
        self._results_manager._results = value

    @property
    def _status_callbacks(self) -> list:
        return self._status_manager._status_callbacks

    def _get_primary_model(self) -> str:
        """从配置获取主模型"""
        from src.shared_config import get_primary_model
        return get_primary_model(self.gateway)

    def register_status_callback(self, callback) -> None:
        """注册状态变更回调"""
        self._status_manager.register_callback(callback)

    def _notify_status(self, task_id: str, status: str) -> None:
        """向后兼容：通知状态变更"""
        self._status_manager.notify_status(task_id, status)

    def create_task(
        self,
        subagent_type: SubagentType,
        prompt: str,
        custom_tools: set[str] | None = None,
        custom_system_prompt: str | None = None,
        max_iterations: int | None = None,
        timeout: int | None = None,
        priority: int = 0,
    ) -> str:
        """创建 Subagent 任务"""
        task = create_task(
            subagent_type=subagent_type,
            prompt=prompt,
            custom_tools=custom_tools,
            custom_system_prompt=custom_system_prompt,
            max_iterations=max_iterations,
            timeout=timeout,
            priority=priority,
        )
        with self._dict_sync_lock:
            self._tasks[task.id] = task
        return task.id

    def spawn_subagent(self, task_id: str) -> SubagentInstance:
        """创建 SubagentInstance"""
        with self._dict_sync_lock:
            if task_id not in self._tasks:
                raise ValueError(f"Task not found: {task_id}")
            task = self._tasks[task_id]

            instance = SubagentInstance(
                gateway=self.gateway,
                subagent_type=task.subagent_type,
                model_id=self.model_id,
                max_iterations=task.max_iterations or self.DEFAULT_MAX_ITERATIONS,
                timeout=task.timeout or get_default_timeout(task.subagent_type),
                custom_system_prompt=task.custom_system_prompt,
                custom_tools=task.custom_tools,
            )

            self._instances[task_id] = instance
            return instance

    async def run_subagent(self, task_id: str) -> SubagentResult:
        """执行单个 Subagent 任务"""
        with self._dict_sync_lock:
            if task_id not in self._tasks:
                raise ValueError(f"Task not found: {task_id}")
            task = self._tasks[task_id]
            need_spawn = task_id not in self._instances

        if need_spawn:
            self.spawn_subagent(task_id)

        with self._dict_sync_lock:
            instance = self._instances[task_id]

        async with self._semaphore:
            self._status_manager.notify_status(task_id, "running")
            state = await instance.run(task.prompt, task_id)
            result = SubagentResult(state)

            self._results_manager.store_result(task_id, result)
            await self._results_manager.notify_result_stored()

            self._status_manager.notify_status(task_id, state.status)
            return result

    async def run_parallel(
        self, task_ids: list[str], fail_fast: bool = False
    ) -> dict[str, SubagentResult]:
        """并行执行多个任务"""
        if fail_fast:
            results: dict[str, SubagentResult] = {}
            for task_id in task_ids:
                result = await self.run_subagent(task_id)
                results[task_id] = result
                if not result.success:
                    break
            return results

        tasks = [self.run_subagent(task_id) for task_id in task_ids]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        parallel_results: dict[str, SubagentResult] = {}
        for task_id, raw_result in zip(task_ids, results_list, strict=True):
            if isinstance(raw_result, BaseException):
                with self._dict_sync_lock:
                    task = self._tasks.get(task_id)
                if task:
                    state = SubagentState(
                        id=task_id,
                        subagent_type=task.subagent_type,
                        status="failed",
                        prompt=task.prompt,
                        error=str(raw_result),
                    )
                else:
                    state = SubagentState(
                        id=task_id,
                        subagent_type=SubagentType.EXPLORE,
                        status="failed",
                        prompt="",
                        error=str(raw_result),
                    )
                parallel_results[task_id] = SubagentResult(state)
            else:
                parallel_results[task_id] = raw_result

        return parallel_results

    def get_status(self, task_id: str) -> str | None:
        """获取任务状态"""
        return self._status_manager.get_status(
            task_id, self._results_manager._results, self._instances, self._tasks
        )

    def get_result(self, task_id: str) -> SubagentResult | None:
        """获取任务结果"""
        return self._results_manager.get_result(task_id)

    def get_all_results(self) -> dict[str, SubagentResult]:
        """获取所有结果"""
        return self._results_manager.get_all_results()

    async def wait_for_result_async(
        self, task_id: str, timeout: float | None = None
    ) -> SubagentResult | None:
        """等待任务完成"""
        return await self._results_manager.wait_for_result_async(task_id, timeout)

    def aggregate_results(
        self, task_ids: list[str], include_errors: bool = True, max_length: int = 2000
    ) -> str:
        """聚合多个任务的结果"""
        return self._results_manager.aggregate_results(
            task_ids,
            self._results_manager._results,
            self._tasks,
            include_errors,
            max_length,
        )

    def cleanup(self, task_id: str | None = None) -> None:
        """清理任务资源"""
        with self._dict_sync_lock:
            if task_id:
                self._tasks.pop(task_id, None)
                self._instances.pop(task_id, None)
            else:
                self._tasks.clear()
                self._instances.clear()
        self._results_manager.cleanup(task_id)

    def list_tasks(self, status: str | None = None) -> list[dict]:
        """列出所有任务"""
        return self._status_manager.list_tasks(
            self._tasks, self._results_manager._results, self._instances, status
        )

    # === 便捷方法 ===

    def spawn_explore(self, prompt: str, **kwargs) -> str:
        """创建探索型任务"""
        return self.create_task(SubagentType.EXPLORE, prompt, **kwargs)

    def spawn_review(self, prompt: str, **kwargs) -> str:
        """创建审查型任务"""
        return self.create_task(SubagentType.REVIEW, prompt, **kwargs)

    def spawn_implement(self, prompt: str, **kwargs) -> str:
        """创建实现型任务"""
        return self.create_task(SubagentType.IMPLEMENT, prompt, **kwargs)

    def spawn_plan(self, prompt: str, **kwargs) -> str:
        """创建规划型任务"""
        return self.create_task(SubagentType.PLAN, prompt, **kwargs)