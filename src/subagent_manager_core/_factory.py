"""
SubagentManager - 工厂模块

负责:
- 任务创建
- SubagentInstance 实例化
- 便捷方法封装
"""

import logging

from src.client import LLMGateway
from src.subagent import SubagentInstance, SubagentType
from src.subagent_manager_core._task import (
    SubagentTask,
    create_task,
    get_default_timeout,
)

logger = logging.getLogger(__name__)


class SubagentFactory:
    """Subagent 工厂"""

    DEFAULT_MAX_ITERATIONS = 15

    def __init__(
        self,
        gateway: LLMGateway,
        model_id: str,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
    ):
        self.gateway = gateway
        self.model_id = model_id
        self.max_iterations = max_iterations

    def _get_primary_model(self) -> str:
        """从配置获取主模型"""
        from src.shared_config import get_primary_model
        return get_primary_model(self.gateway)

    def create_task(
        self,
        subagent_type: SubagentType,
        prompt: str,
        custom_tools: set[str] | None = None,
        custom_system_prompt: str | None = None,
        max_iterations: int | None = None,
        timeout: int | None = None,
        priority: int = 0,
    ) -> SubagentTask:
        """创建 Subagent 任务"""
        return create_task(
            subagent_type=subagent_type,
            prompt=prompt,
            custom_tools=custom_tools,
            custom_system_prompt=custom_system_prompt,
            max_iterations=max_iterations,
            timeout=timeout,
            priority=priority,
        )

    def spawn_instance(
        self,
        task: SubagentTask,
    ) -> SubagentInstance:
        """创建 SubagentInstance"""
        return SubagentInstance(
            gateway=self.gateway,
            subagent_type=task.subagent_type,
            model_id=self.model_id,
            max_iterations=task.max_iterations or self.max_iterations,
            timeout=task.timeout or get_default_timeout(task.subagent_type),
            custom_system_prompt=task.custom_system_prompt,
            custom_tools=task.custom_tools,
        )

    # === 便捷方法 ===

    def create_explore_task(self, prompt: str, **kwargs) -> SubagentTask:
        """创建探索型任务"""
        return self.create_task(SubagentType.EXPLORE, prompt, **kwargs)

    def create_review_task(self, prompt: str, **kwargs) -> SubagentTask:
        """创建审查型任务"""
        return self.create_task(SubagentType.REVIEW, prompt, **kwargs)

    def create_implement_task(self, prompt: str, **kwargs) -> SubagentTask:
        """创建实现型任务"""
        return self.create_task(SubagentType.IMPLEMENT, prompt, **kwargs)

    def create_plan_task(self, prompt: str, **kwargs) -> SubagentTask:
        """创建规划型任务"""
        return self.create_task(SubagentType.PLAN, prompt, **kwargs)