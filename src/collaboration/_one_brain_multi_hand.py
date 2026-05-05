"""多智能体协作模块 - 一脑多手编排器

OneBrainMultiHandOrchestrator: 一脑多手编排器

适用场景：在不同环境执行任务（Python + Node.js）

核心特性：
- 多工作台：每个 Sandbox 代表不同环境
- 任务分配：大脑规划各环境任务
- 跨环境测试：同时在不同环境验证

版本: v2.0 (重构实现)
创建日期: 2026-05-05
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from src.collaboration._types import AgentInstance
from src.llm_client import LLMClient
from src.sandbox import IsolationLevel, Sandbox

logger = logging.getLogger(__name__)


class OneBrainMultiHandOrchestrator:
    """一脑多手编排器：一个 Claude 控制多个 Sandbox

    适用场景：在不同环境执行任务（Python + Node.js）

    核心特性：
    - 多工作台：每个 Sandbox 代表不同环境
    - 任务分配：大脑规划各环境任务
    - 跨环境测试：同时在不同环境验证
    """

    def __init__(
        self,
        llm_client: LLMClient,
        sandbox_configs: list[dict[str, Any]],
        labels: list[str] | None = None,
    ):
        """初始化一脑多手编排器

        Args:
            llm_client: 单个大脑
            sandbox_configs: Sandbox 配置列表
            labels: 工作台标签（如 ["python_env", "node_env", "browser"]）
        """
        self.llm_client = llm_client

        # 创建多个工作台
        self.sandboxes: list[Sandbox] = []
        self._agents: list[AgentInstance] = []

        for i, config in enumerate(sandbox_configs):
            # 支持字符串和枚举两种输入
            isolation_level_raw = config.get("isolation_level", IsolationLevel.PROCESS)
            if isinstance(isolation_level_raw, str):
                isolation_level = IsolationLevel(isolation_level_raw)
            else:
                isolation_level = isolation_level_raw

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

        logger.info(
            f"OneBrainMultiHandOrchestrator initialized: "
            f"sandboxes={len(self.sandboxes)}, labels={list(self._sandbox_labels.values())}"
        )

    def label_sandbox(self, index: int, label: str) -> None:
        """为 Sandbox 设置标签

        Args:
            index: Sandbox 索引
            label: 标签
        """
        if index < len(self.sandboxes):
            self._sandbox_labels[index] = label
            self._agents[index].label = label
            logger.debug(f"Sandbox labeled: index={index}, label={label}")

    async def execute_in_multiple_environments(self, task: str) -> dict[str, Any]:
        """在不同环境执行任务

        Args:
            task: 任务描述

        Returns:
            各环境执行结果
        """
        # 1. 大脑规划任务分配
        plan = await self._plan_for_multi_hand(task)

        # 2. 分发到各 Sandbox
        results: dict[str, list[str]] = {}

        for sandbox_idx, sandbox_tasks in plan.items():
            sandbox = self.sandboxes[int(sandbox_idx)]
            label = self._sandbox_labels.get(int(sandbox_idx), f"sandbox_{sandbox_idx}")

            # 执行该 Sandbox 的任务
            sandbox_results = await self._execute_sandbox_tasks(sandbox, sandbox_tasks)
            results[label] = sandbox_results

            # 更新智能体状态
            self._agents[int(sandbox_idx)].status = "completed"

        # 3. 大脑聚合结果
        aggregated = await self._aggregate_results(results)

        return {
            "task": task,
            "plan": plan,
            "execution_results": results,
            "aggregated_result": aggregated,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def _plan_for_multi_hand(self, task: str) -> dict[str, list[dict[str, Any]]]:
        """大脑规划多环境任务分配

        Args:
            task: 任务描述

        Returns:
            各环境的任务列表
        """
        sandbox_descriptions = [
            self._sandbox_labels.get(i, f"Sandbox {i}")
            for i in range(len(self.sandboxes))
        ]

        # 构建环境描述列表
        env_list = "\n".join(f"- {desc}" for desc in sandbox_descriptions)

        prompt = f"""请为以下任务规划多环境执行方案:

任务: {task}

可用环境:
{env_list}

请输出 JSON 格式的任务分配:
 {{
    "0": [{{"tool": "工具名", "args": {{ "参数": "值"}}}}],
    "1": [{{"tool": "工具名", "args": {{ "参数": "值"}}}}]
}}
"""

        try:
            response = await self.llm_client.reason(
                [{"role": "user", "content": prompt}]
            )
            plan_text = (
                response.get("choices", [{}])[0].get("message", {}).get("content", "")
            )

            # 解析 JSON
            return self._parse_plan(plan_text)

        except Exception as e:
            logger.exception(f"Planning failed: {e}")
            # 默认分配：所有环境执行相同任务
            return {
                str(i): [{"tool": "code_as_policy", "args": {"code": task}}]
                for i in range(len(self.sandboxes))
            }

    def _parse_plan(self, plan_text: str) -> dict[str, list[dict[str, Any]]]:
        """解析规划文本"""
        # 尝试提取 JSON
        try:
            # 查找 JSON 块
            start = plan_text.find("{")
            end = plan_text.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = plan_text[start:end]
                return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.debug(f"Plan JSON parse failed: {e}")

        # 解析失败，使用默认分配
        logger.warning("Failed to parse plan JSON, using default")
        return {
            str(i): [{"tool": "code_as_policy", "args": {"code": "execute task"}}]
            for i in range(len(self.sandboxes))
        }

    async def _execute_sandbox_tasks(
        self, sandbox: Sandbox, tasks: list[dict[str, Any]]
    ) -> list[str]:
        """执行 Sandbox 任务列表

        Args:
            sandbox: 目标 Sandbox
            tasks: 任务列表

        Returns:
            执行结果列表
        """
        results: list[str] = []

        for task in tasks:
            tool_name = task.get("tool", "code_as_policy")
            tool_args = task.get("args", {})

            try:
                result = await sandbox.execute_tools(
                    [
                        {
                            "id": str(uuid.uuid4())[:8],
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(tool_args),
                            },
                        }
                    ]
                )
                if result:
                    results.append(result[0].get("content", "No content"))
                else:
                    results.append("No result returned")

            except Exception as e:
                logger.exception("Task execution failed")
                results.append(f"Error: {e}")

        return results

    async def _aggregate_results(self, results: dict[str, list[str]]) -> dict[str, Any]:
        """大脑聚合结果

        Args:
            results: 各环境执行结果

        Returns:
            聚合分析
        """
        prompt = f"""请分析以下多环境执行结果并给出总结:

执行结果:
{json.dumps(results, ensure_ascii=False, indent=2)}

请输出:
1. 各环境执行情况总结
2. 发现的问题和差异
3. 最终结论和建议
"""

        try:
            response = await self.llm_client.reason(
                [{"role": "user", "content": prompt}]
            )
            summary = (
                response.get("choices", [{}])[0].get("message", {}).get("content", "")
            )

            return {
                "summary": summary,
                "environments_count": len(results),
                "total_tasks": sum(len(r) for r in results.values()),
            }

        except Exception as e:
            logger.exception("Aggregation failed")
            return {
                "summary": f"Aggregation failed: {e}",
                "environments_count": len(results),
            }

    async def cross_environment_test(self, test_code: str) -> dict[str, Any]:
        """跨环境测试

        Args:
            test_code: 测试代码或描述

        Returns:
            跨环境测试结果
        """
        # 规划测试方案
        test_plan = {
            "0": [
                {
                    "tool": "code_as_policy",
                    "args": {"code": test_code, "language": "python"},
                }
            ],
            "1": [
                {
                    "tool": "code_as_policy",
                    "args": {"code": test_code, "language": "javascript"},
                }
            ],
        }

        # 执行测试
        results = {}
        for sandbox_idx, tasks in test_plan.items():
            if int(sandbox_idx) < len(self.sandboxes):
                sandbox = self.sandboxes[int(sandbox_idx)]
                label = self._sandbox_labels.get(
                    int(sandbox_idx), f"sandbox_{sandbox_idx}"
                )
                results[label] = await self._execute_sandbox_tasks(sandbox, tasks)

        # 检查跨环境一致性
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
