"""多智能体协作模块 - 一脑多手编排器

OneBrainMultiHandOrchestrator: 一脑多手编排器

适用场景：在不同环境执行任务（Python + Node.js）

核心特性：
- 多工作台：每个 Sandbox 代表不同环境
- 任务分配：大脑规划各环境任务
- 跨环境测试：同时在不同环境验证

重构说明：
- 规划逻辑移至 _one_brain_multi_hand_planning.py
- 执行逻辑移至 _one_brain_multi_hand_execution.py
- 聚合逻辑移至 _one_brain_multi_hand_aggregation.py
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from src.collaboration._one_brain_multi_hand_aggregation import MultiHandAggregator
from src.collaboration._one_brain_multi_hand_execution import MultiHandExecutor
from src.collaboration._one_brain_multi_hand_planning import MultiHandPlanner
from src.collaboration._types import AgentInstance
from src.llm_client import LLMClient
from src.sandbox import IsolationLevel, Sandbox

logger = logging.getLogger(__name__)


class OneBrainMultiHandOrchestrator:
    """一脑多手编排器：一个 Claude 控制多个 Sandbox"""

    def __init__(
        self,
        llm_client: LLMClient,
        sandbox_configs: list[dict[str, Any]],
        labels: list[str] | None = None,
    ):
        self.llm_client = llm_client

        # 创建多个工作台
        self.sandboxes: list[Sandbox] = []
        self._agents: list[AgentInstance] = []

        for i, config in enumerate(sandbox_configs):
            isolation_level_raw = config.get("isolation_level", IsolationLevel.PROCESS)
            isolation_level = (
                IsolationLevel(isolation_level_raw)
                if isinstance(isolation_level_raw, str)
                else isolation_level_raw
            )

            sandbox = Sandbox(
                isolation_level=isolation_level,
                file_system_root=config.get("file_system_root"),
                workspace_path=config.get("workspace_path"),
            )
            self.sandboxes.append(sandbox)

            label = labels[i] if labels and i < len(labels) else f"sandbox_{i}"
            self._agents.append(
                AgentInstance(
                    id=str(uuid.uuid4())[:8],
                    llm_client=llm_client,
                    sandbox=sandbox,
                    label=label,
                )
            )

        self._sandbox_labels: dict[int, str] = {
            i: agent.label or f"sandbox_{i}" for i, agent in enumerate(self._agents)
        }

        # 拆分模块组件
        self._planner = MultiHandPlanner(llm_client, len(self.sandboxes), self._sandbox_labels)
        self._executor = MultiHandExecutor()
        self._aggregator = MultiHandAggregator(llm_client)

        logger.info(
            f"OneBrainMultiHandOrchestrator initialized: "
            f"sandboxes={len(self.sandboxes)}, labels={list(self._sandbox_labels.values())}"
        )

    def label_sandbox(self, index: int, label: str) -> None:
        """为 Sandbox 设置标签"""
        if index < len(self.sandboxes):
            self._sandbox_labels[index] = label
            self._agents[index].label = label
            self._planner._sandbox_labels[index] = label

    async def execute_in_multiple_environments(self, task: str) -> dict[str, Any]:
        """在不同环境执行任务"""
        # 1. 规划任务分配
        plan = await self._planner.plan_for_multi_hand(task)

        # 2. 分发到各 Sandbox
        results: dict[str, list[str]] = {}

        for sandbox_idx, sandbox_tasks in plan.items():
            idx = int(sandbox_idx)
            if idx >= len(self.sandboxes):
                continue
            sandbox = self.sandboxes[idx]
            label = self._sandbox_labels.get(idx, f"sandbox_{idx}")
            results[label] = await self._executor.execute_sandbox_tasks(sandbox, sandbox_tasks)
            self._agents[idx].status = "completed"

        # 3. 聚合结果
        aggregated = await self._aggregator.aggregate_results(results)

        return {
            "task": task,
            "plan": plan,
            "execution_results": results,
            "aggregated_result": aggregated,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def cross_environment_test(self, test_code: str) -> dict[str, Any]:
        """跨环境测试"""
        test_plan = {
            "0": [{"tool": "code_as_policy", "args": {"code": test_code, "language": "python"}}],
            "1": [{"tool": "code_as_policy", "args": {"code": test_code, "language": "javascript"}}],
        }

        results = {}
        for sandbox_idx, tasks in test_plan.items():
            idx = int(sandbox_idx)
            if idx < len(self.sandboxes):
                label = self._sandbox_labels.get(idx, f"sandbox_{idx}")
                results[label] = await self._executor.execute_sandbox_tasks(self.sandboxes[idx], tasks)

        python_result = results.get("python_env", [""])
        node_result = results.get("node_env", [""])
        cross_env_valid = "PASS" in str(python_result) and "PASS" in str(node_result)

        return {
            "test_code": test_code[:200],
            "python_test": python_result,
            "node_test": node_result,
            "cross_env_valid": cross_env_valid,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def get_sandboxes_status(self) -> list[dict[str, Any]]:
        """获取所有 Sandbox 状态"""
        return [
            {
                "index": i,
                "label": self._sandbox_labels.get(i, f"sandbox_{i}"),
                "status": self._agents[i].status,
                "sandbox_state": sandbox.get_status(),
            }
            for i, sandbox in enumerate(self.sandboxes)
        ]