"""SubagentManager - 管理器核心协调器

负责: 组件协调、公共 API、资源管理
"""

import logging
import threading

from src.client import LLMGateway
from src.subagent import SubagentInstance, SubagentResult, SubagentType
from src.subagent_manager_core._execution import SubagentExecutor
from src.subagent_manager_core._factory import SubagentFactory
from src.subagent_manager_core._results import ResultsManager
from src.subagent_manager_core._status import StatusManager
from src.subagent_manager_core._task import SubagentTask

logger = logging.getLogger(__name__)


class SubagentManager:
    """Subagent 管理器"""

    DEFAULT_MAX_CONCURRENT = 3
    DEFAULT_TIMEOUT = 300
    DEFAULT_MAX_ITERATIONS = 100

    def __init__(
        self, gateway: LLMGateway, model_id: str | None = None,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    ):
        self.gateway = gateway
        self.model_id = model_id or self._get_primary_model()
        self.max_concurrent = max_concurrent
        self._instances: dict[str, SubagentInstance] = {}
        self._tasks: dict[str, SubagentTask] = {}
        self._dict_sync_lock = threading.Lock()
        self._factory = SubagentFactory(self.gateway, self.model_id, self.DEFAULT_MAX_ITERATIONS)
        self._results_manager = ResultsManager()
        self._status_manager = StatusManager()
        self._executor = SubagentExecutor(
            max_concurrent, self._dict_sync_lock, self._status_manager, self._results_manager
        )

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
        from src.shared_config import get_primary_model
        return get_primary_model(self.gateway)

    def register_status_callback(self, callback) -> None:
        self._status_manager.register_callback(callback)

    def _notify_status(self, task_id: str, status: str) -> None:
        self._status_manager.notify_status(task_id, status)

    def create_task(
        self, subagent_type: SubagentType, prompt: str,
        custom_tools: set[str] | None = None, custom_system_prompt: str | None = None,
        max_iterations: int | None = None, timeout: int | None = None, priority: int = 0,
    ) -> str:
        task = self._factory.create_task(
            subagent_type, prompt, custom_tools, custom_system_prompt,
            max_iterations, timeout, priority
        )
        with self._dict_sync_lock:
            self._tasks[task.id] = task
        return task.id

    def spawn_subagent(self, task_id: str) -> SubagentInstance:
        with self._dict_sync_lock:
            if task_id not in self._tasks:
                raise ValueError(f"Task not found: {task_id}")
            task = self._tasks[task_id]
            instance = self._factory.spawn_instance(task)
            self._instances[task_id] = instance
            return instance

    def _get_or_spawn_instance(self, task_id: str) -> SubagentInstance:
        with self._dict_sync_lock:
            if task_id in self._instances:
                return self._instances[task_id]
        return self.spawn_subagent(task_id)

    async def run_subagent(self, task_id: str) -> SubagentResult:
        with self._dict_sync_lock:
            if task_id not in self._tasks:
                raise ValueError(f"Task not found: {task_id}")
            task = self._tasks[task_id]
        return await self._executor.run_single(task_id, task, self._get_or_spawn_instance(task_id))

    async def run_parallel(self, task_ids: list[str], fail_fast: bool = False) -> dict[str, SubagentResult]:
        return await self._executor.run_parallel(
            task_ids, self._tasks, self._instances, self._get_or_spawn_instance, fail_fast
        )

    def get_status(self, task_id: str) -> str | None:
        return self._status_manager.get_status(
            task_id, self._results_manager._results, self._instances, self._tasks
        )

    def get_result(self, task_id: str) -> SubagentResult | None:
        return self._results_manager.get_result(task_id)

    def get_all_results(self) -> dict[str, SubagentResult]:
        return self._results_manager.get_all_results()

    async def wait_for_result_async(self, task_id: str, timeout: float | None = None) -> SubagentResult | None:
        return await self._results_manager.wait_for_result_async(task_id, timeout)

    def aggregate_results(self, task_ids: list[str], include_errors: bool = True, max_length: int = 2000) -> str:
        return self._results_manager.aggregate_results(
            task_ids, self._results_manager._results, self._tasks, include_errors, max_length
        )

    def list_tasks(self, status: str | None = None) -> list[dict]:
        return self._status_manager.list_tasks(
            self._tasks, self._results_manager._results, self._instances, status
        )

    def cleanup(self, task_id: str | None = None) -> None:
        with self._dict_sync_lock:
            if task_id:
                self._tasks.pop(task_id, None)
                self._instances.pop(task_id, None)
            else:
                self._tasks.clear()
                self._instances.clear()
        self._results_manager.cleanup(task_id)

    # 便捷方法
    def spawn_explore(self, prompt: str, **kwargs) -> str:
        return self.create_task(SubagentType.EXPLORE, prompt, **kwargs)

    def spawn_review(self, prompt: str, **kwargs) -> str:
        return self.create_task(SubagentType.REVIEW, prompt, **kwargs)

    def spawn_implement(self, prompt: str, **kwargs) -> str:
        return self.create_task(SubagentType.IMPLEMENT, prompt, **kwargs)

    def spawn_plan(self, prompt: str, **kwargs) -> str:
        return self.create_task(SubagentType.PLAN, prompt, **kwargs)