"""
SubagentManager - RalphLoop 编排器

负责:
- RalphLoop 升级的 Subagent 编排
- Plan/Implement/Review 三阶段执行
- 执行报告生成
"""

import logging
from src.subagent import SubagentResult
from src.subagent_manager_core._manager import SubagentManager

logger = logging.getLogger(__name__)


class RalphSubagentOrchestrator:
    """
    RalphLoop 升级的 Subagent 编排器

    执行模式:
    1. Spawn PlanSubagent -> 获取执行计划
    2. Spawn multiple ImplementSubagent (并行)
    3. Spawn ReviewSubagent -> 验证实现
    4. External verification -> 循环或完成
    """

    def __init__(self, manager: SubagentManager):
        self.manager = manager
        self._plan_task_id: str | None = None
        self._implement_task_ids: list[str] = []
        self._review_task_id: str | None = None

    async def plan_phase(self, task_prompt: str) -> str:
        """规划阶段"""
        self._plan_task_id = self.manager.spawn_plan(
            f"请分析以下任务并制定执行计划:\n\n{task_prompt}"
        )
        result = await self.manager.run_subagent(self._plan_task_id)
        return result.summary

    async def implement_phase(
        self,
        implement_prompts: list[str],
    ) -> dict[str, SubagentResult]:
        """实现阶段（并行执行多个任务）"""
        self._implement_task_ids = []
        for prompt in implement_prompts:
            task_id = self.manager.spawn_implement(prompt)
            self._implement_task_ids.append(task_id)

        return await self.manager.run_parallel(self._implement_task_ids)

    async def review_phase(self, review_prompt: str) -> str:
        """审查阶段"""
        self._review_task_id = self.manager.spawn_review(review_prompt)
        result = await self.manager.run_subagent(self._review_task_id)
        return result.summary

    def get_execution_report(self) -> dict:
        """获取执行报告"""
        plan_result = (
            self.manager.get_result(self._plan_task_id) if self._plan_task_id else None
        )
        return {
            "plan": {
                "task_id": self._plan_task_id,
                "result": plan_result.summary if plan_result else None,
            },
            "implement": [
                {
                    "task_id": task_id,
                    "result": (
                        r.summary if (r := self.manager.get_result(task_id)) else None
                    ),
                }
                for task_id in self._implement_task_ids
            ],
            "review": {
                "task_id": self._review_task_id,
                "result": (
                    r.summary
                    if (
                        r := self.manager.get_result(self._review_task_id)
                        if self._review_task_id
                        else None
                    )
                    else None
                ),
            },
        }

    def cleanup(self):
        """清理所有任务"""
        self.manager.cleanup()
        self._plan_task_id = None
        self._implement_task_ids = []
        self._review_task_id = None