"""
SubagentManager - 管理器核心

负责:
- 创建独立 SubagentInstance
- 并行执行调度
- 结果收集与过滤
- 超时管理
- 资源限制（同时运行的 subagent 数量）
"""

import asyncio
import logging
import threading
from collections.abc import Callable

from src.client import LLMGateway
from src.subagent import (
    SubagentInstance,
    SubagentResult,
    SubagentState,
    SubagentType,
)
from src.subagent_manager_core._task import (
    SubagentTask,
    create_task,
    get_default_timeout,
)

logger = logging.getLogger(__name__)


class SubagentManager:
    """
    Subagent 管理器

    负责管理子代理的完整生命周期:
    - 创建: spawn_subagent()
    - 执行: run_subagent() / run_parallel()
    - 状态: get_status()
    - 结果: get_result()
    - 清理: cleanup()
    """

    DEFAULT_MAX_CONCURRENT = 3  # 默认最大并行数
    DEFAULT_TIMEOUT = 300  # 默认超时 5 分钟
    DEFAULT_MAX_ITERATIONS = 15  # 默认最大迭代次数

    def __init__(
        self,
        gateway: LLMGateway,
        model_id: str | None = None,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    ):
        """初始化 SubagentManager

        Args:
            gateway: LLM 网关实例
            model_id: 默认使用的模型 ID
            max_concurrent: 最大并行执行的 subagent 数量
        """
        self.gateway = gateway
        self.model_id = model_id or self._get_primary_model()
        self.max_concurrent = max_concurrent

        # 活跃的 subagent 实例
        self._instances: dict[str, SubagentInstance] = {}

        # 任务状态跟踪
        self._tasks: dict[str, SubagentTask] = {}

        # 执行结果
        self._results: dict[str, SubagentResult] = {}

        # 并发控制信号量
        self._semaphore = asyncio.Semaphore(max_concurrent)

        # 状态变更回调
        self._status_callbacks: list[Callable[[str, str], None]] = []

        # 事件驱动等待：Condition 变量
        self._result_condition = asyncio.Condition()

        # 字典操作同步锁
        self._dict_sync_lock = threading.Lock()

    def _get_primary_model(self) -> str:
        """从配置获取主模型"""
        from src.shared_config import get_primary_model
        return get_primary_model(self.gateway)

    def register_status_callback(self, callback: Callable[[str, str], None]):
        """注册状态变更回调"""
        self._status_callbacks.append(callback)

    def _notify_status(self, task_id: str, status: str):
        """通知状态变更"""
        for callback in self._status_callbacks:
            try:
                callback(task_id, status)
            except Exception as e:
                logger.warning(f"Status callback error: {type(e).__name__}: {e}")

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
        """创建 Subagent 任务（返回 task_id）"""
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
            self._notify_status(task_id, "running")
            state = await instance.run(task.prompt, task_id)
            result = SubagentResult(state)

            async with self._result_condition:
                self._results[task_id] = result
                self._result_condition.notify_all()

            self._notify_status(task_id, state.status)
            return result

    async def run_parallel(
        self,
        task_ids: list[str],
        fail_fast: bool = False,
    ) -> dict[str, SubagentResult]:
        """并行执行多个 Subagent 任务"""
        if fail_fast:
            sequential_results: dict[str, SubagentResult] = {}
            for task_id in task_ids:
                result = await self.run_subagent(task_id)
                sequential_results[task_id] = result
                if not result.success:
                    break
            return sequential_results

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
        with self._dict_sync_lock:
            if task_id in self._results:
                return self._results[task_id].state.status
            if task_id in self._instances:
                instance = self._instances[task_id]
                if instance.state:
                    return instance.state.status
                return "pending"
            if task_id in self._tasks:
                return "pending"
            return None

    def get_result(self, task_id: str) -> SubagentResult | None:
        """获取任务结果"""
        with self._dict_sync_lock:
            return self._results.get(task_id)

    def get_all_results(self) -> dict[str, SubagentResult]:
        """获取所有结果"""
        with self._dict_sync_lock:
            return self._results.copy()

    async def wait_for_result_async(
        self,
        task_id: str,
        timeout: float | None = None,
    ) -> SubagentResult | None:
        """等待任务完成（事件驱动）"""
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
        include_errors: bool = True,
        max_length: int = 2000,
    ) -> str:
        """聚合多个任务的结果"""
        if max_length <= 0:
            raise ValueError("max_length must be positive")
        summaries: list[str] = []
        with self._dict_sync_lock:
            results_copy = {tid: self._results.get(tid) for tid in task_ids}
        for task_id in task_ids:
            result = results_copy.get(task_id)
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
        """清理任务资源"""
        with self._dict_sync_lock:
            if task_id:
                self._tasks.pop(task_id, None)
                self._instances.pop(task_id, None)
                self._results.pop(task_id, None)
            else:
                self._tasks.clear()
                self._instances.clear()
                self._results.clear()

    def list_tasks(self, status: str | None = None) -> list[dict]:
        """列出所有任务"""
        tasks = []
        with self._dict_sync_lock:
            task_items = list(self._tasks.items())
        for task_id, task in task_items:
            task_status = self.get_status(task_id)
            if status and task_status != status:
                continue
            tasks.append({
                "id": task_id,
                "type": task.subagent_type.value,
                "status": task_status,
                "prompt_preview": task.prompt[:100] + "..." if len(task.prompt) > 100 else task.prompt,
                "priority": task.priority,
            })
        return tasks

    # === 便捷方法 ===

    def spawn_explore(self, prompt: str, **kwargs) -> str:
        """创建探索型 Subagent 任务"""
        return self.create_task(SubagentType.EXPLORE, prompt, **kwargs)

    def spawn_review(self, prompt: str, **kwargs) -> str:
        """创建审查型 Subagent 任务"""
        return self.create_task(SubagentType.REVIEW, prompt, **kwargs)

    def spawn_implement(self, prompt: str, **kwargs) -> str:
        """创建实现型 Subagent 任务"""
        return self.create_task(SubagentType.IMPLEMENT, prompt, **kwargs)

    def spawn_plan(self, prompt: str, **kwargs) -> str:
        """创建规划型 Subagent 任务"""
        return self.create_task(SubagentType.PLAN, prompt, **kwargs)