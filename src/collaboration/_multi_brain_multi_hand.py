"""多智能体协作模块 - 多脑多手编排器

MultiBrainMultiHandOrchestrator: 多脑多手编排器

适用场景：最复杂的多步骤任务

核心特性：
- Session 协调：共享 Session 作为协调中心
- 独立组合：每个 Claude 有自己的 Sandbox
- 动态分配：根据进度调整任务分配
- 消息总线：智能体间通信

版本: v2.0 (重构实现)
创建日期: 2026-05-05
"""

import asyncio
import json
import logging
import uuid
from typing import Any

from src.collaboration._message_bus import InterAgentMessageBus
from src.collaboration._types import AgentInstance, CoordinationResult
from src.llm_client import LLMClient
from src.sandbox import Sandbox
from src.session_event_stream import EventType, SessionEventStream

logger = logging.getLogger(__name__)

# 默认配置
MAX_DYNAMIC_ITERATIONS = 10  # 动态任务分配最大迭代


class MultiBrainMultiHandOrchestrator:
    """多脑多手编排器：多个 Claude + 多个 Sandbox + Session 协调

    适用场景：最复杂的多步骤任务

    核心特性：
    - Session 协调：共享 Session 作为协调中心
    - 独立组合：每个 Claude 有自己的 Sandbox
    - 动态分配：根据进度调整任务分配
    - 消息总线：智能体间通信
    """

    def __init__(
        self,
        session: SessionEventStream,
        agent_sandbox_pairs: list[tuple[LLMClient, Sandbox]] | None = None,
        message_bus: InterAgentMessageBus | None = None,
    ):
        """初始化多脑多手编排器

        Args:
            session: 共享协调中心
            agent_sandbox_pairs: Claude + Sandbox 组合列表
            message_bus: 消息总线（可选）
        """
        self.session = session
        self._pairs: list[tuple[LLMClient, Sandbox]] = agent_sandbox_pairs or []
        self._message_bus = message_bus

        # 创建智能体实例
        self._agents: list[AgentInstance] = []
        self._pair_ids: list[str] = []

        for _, (llm_client, sandbox) in enumerate(self._pairs):
            pair_id = str(uuid.uuid4())[:8]
            self._pair_ids.append(pair_id)
            self._agents.append(
                AgentInstance(
                    id=pair_id,
                    llm_client=llm_client,
                    sandbox=sandbox,
                )
            )

        self._task_assignments: dict[str, list[dict]] = {}

        logger.info(
            f"MultiBrainMultiHandOrchestrator initialized: "
            f"pairs={len(self._pairs)}, session={session.session_id}"
        )

    def register_pair(
        self, llm_client: LLMClient, sandbox: Sandbox, pair_id: str | None = None
    ) -> str:
        """注册 Claude + Sandbox 组合

        Args:
            llm_client: LLM 客户端
            sandbox: 执行沙盒
            pair_id: 组合 ID（可选）

        Returns:
            组合 ID
        """
        pair_id = pair_id or str(uuid.uuid4())[:8]
        self._pairs.append((llm_client, sandbox))
        self._pair_ids.append(pair_id)
        self._agents.append(
            AgentInstance(
                id=pair_id,
                llm_client=llm_client,
                sandbox=sandbox,
            )
        )

        logger.info(f"Pair registered: {pair_id}")
        return pair_id

    async def coordinated_execution(self, task: str) -> CoordinationResult:
        """协调执行

        流程:
        1. Session 记录任务
        2. 各组合独立执行
        3. 结果记录到 Session
        4. Session 协调合并

        Args:
            task: 任务描述

        Returns:
            协调结果
        """
        # 1. Session 记录任务
        self.session.emit_event(
            EventType.SESSION_START,
            {
                "task": task,
                "pairs": self._pair_ids,
                "mode": "multi_brain_multi_hand",
            },
        )

        # 2. 各组合独立执行（并行）
        pair_results = await asyncio.gather(
            *[self._execute_pair(agent, task) for agent in self._agents],
            return_exceptions=True,
        )

        # 3. 结果记录到 Session
        processed_results: list[dict[str, Any]] = []
        for pair_id, result in zip(self._pair_ids, pair_results, strict=True):
            if isinstance(result, Exception):
                self.session.emit_event(
                    EventType.ERROR_OCCURRED,
                    {
                        "pair_id": pair_id,
                        "error": str(result),
                    },
                )
                processed_results.append(
                    {
                        "pair_id": pair_id,
                        "status": "failed",
                        "error": str(result),
                    }
                )
            else:
                self.session.emit_event(
                    EventType.SUBAGENT_RESULT,
                    {
                        "pair_id": pair_id,
                        "result": result,
                    },
                )
                processed_results.append(
                    {
                        "pair_id": pair_id,
                        "status": "completed",
                        "result": result,
                    }
                )

        # 4. Session 协调合并
        merged = await self._merge_from_session()

        # 5. 记录会话结束
        self.session.emit_event(
            EventType.SESSION_END,
            {
                "reason": "completed",
                "pairs_count": len(self._pair_ids),
            },
        )

        return CoordinationResult(
            task=task,
            agent_results=processed_results,
            merged_result=merged,
            session_events=self.session.get_events(),
        )

    async def _execute_pair(
        self,
        agent: AgentInstance,
        task: str,
    ) -> dict[str, Any]:
        """单个组合执行

        Args:
            agent: 智能体实例
            task: 任务描述

        Returns:
            执行结果
        """
        agent.status = "running"

        # 1. 从 Session 获取当前状态
        session_state = self.session.get_current_state()

        # 2. 构建上下文（包含其他组合的进度）
        context = self._build_pair_context(task, session_state)

        # 3. Claude 推理
        try:
            response = await agent.llm_client.reason(context)

            # 4. Sandbox 执行工具
            tool_results: list[str] = []
            tool_calls = (
                response.get("choices", [{}])[0].get("message", {}).get("tool_calls")
            )

            if tool_calls and agent.sandbox:
                results = await agent.sandbox.execute_tools(tool_calls)
                tool_results = [r.get("content", "") for r in results]

            agent.status = "completed"

            return {
                "pair_id": agent.id,
                "response": response,
                "tool_results": tool_results,
                "status": "completed",
            }

        except Exception as e:
            logger.exception(f"Pair {agent.id} execution failed")
            agent.status = "failed"
            return {
                "pair_id": agent.id,
                "error": str(e),
                "status": "failed",
            }

    def _build_pair_context(
        self, task: str, session_state: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """构建组合上下文

        Args:
            task: 任务描述
            session_state: Session 状态

        Returns:
            上下文消息列表
        """
        # 包含任务和其他组合的进度
        other_pairs_progress = [
            {"pair_id": agent.id, "status": agent.status}
            for agent in self._agents
            if agent.id != session_state.get("current_pair_id")
        ]

        return [
            {
                "role": "system",
                "content": "你是一个协作智能体，正在与其他智能体协同完成任务。",
            },
            {
                "role": "user",
                "content": f"""任务: {task}

其他智能体状态:
{json.dumps(other_pairs_progress, ensure_ascii=False, indent=2)}

请执行你的部分任务，并输出结果或下一步建议。
""",
            },
        ]

    async def _merge_from_session(self) -> dict[str, Any]:
        """从 Session 合并所有结果"""
        # 获取所有 subagent_result 事件
        pair_events = [
            e
            for e in self.session.get_events()
            if e["type"] == EventType.SUBAGENT_RESULT.value
        ]

        # 合并逻辑
        successful_pairs = [e for e in pair_events if "error" not in e["data"]]
        failed_pairs = [e for e in pair_events if "error" in e["data"]]

        # 收集结果
        all_results = []
        for event in successful_pairs:
            result_data = event["data"].get("result", {})
            if isinstance(result_data, dict):
                all_results.append(result_data)

        # 生成合并摘要
        merged_summary = await self._generate_merge_summary(all_results)

        return {
            "total_pairs": len(pair_events),
            "successful_pairs": len(successful_pairs),
            "failed_pairs": len(failed_pairs),
            "results": all_results,
            "merged_summary": merged_summary,
        }

    async def _generate_merge_summary(self, results: list[dict[str, Any]]) -> str:
        """生成合并摘要"""
        if not results:
            return "No results to merge"

        if not self._agents:
            return f"Collected {len(results)} results"

        # 使用第一个大脑生成摘要
        prompt = f"""请总结以下多个智能体的执行结果:

{json.dumps(results[:5], ensure_ascii=False, indent=2)}

请输出:
1. 各智能体贡献总结
2. 整体完成情况
3. 遗留问题或下一步建议
"""

        try:
            response = await self._agents[0].llm_client.reason(
                [{"role": "user", "content": prompt}]
            )
            return (
                response.get("choices", [{}])[0].get("message", {}).get("content", "")
            )

        except Exception:
            logger.exception("Merge summary failed")
            return f"Generated {len(results)} results"

    async def dynamic_task_assignment(self, task: str) -> dict[str, Any]:
        """动态任务分配

        根据执行进度动态调整任务分配

        Args:
            task: 任务描述

        Returns:
            分配结果
        """
        # 1. 初始分配
        initial_assignments = await self._initial_assignment(task)

        # 2. 执行监控
        final_results: list[dict[str, Any]] = []
        iteration = 0

        while iteration < MAX_DYNAMIC_ITERATIONS:
            iteration += 1

            # 执行当前分配
            results = await self._execute_assignments(initial_assignments)
            final_results = results

            # 检查完成状态
            completed_pairs = [
                r["pair_id"] for r in results if r.get("status") == "completed"
            ]

            if len(completed_pairs) == len(self._pair_ids):
                break

            # 3. 动态重分配
            remaining_pairs = [
                pid for pid in self._pair_ids if pid not in completed_pairs
            ]

            if remaining_pairs:
                initial_assignments = await self._reassign_tasks(
                    task, completed_pairs, remaining_pairs
                )

        return {
            "task": task,
            "initial_assignments": initial_assignments,
            "final_results": final_results,
            "iterations": iteration,
            "completed": len(
                [r for r in final_results if r.get("status") == "completed"]
            ),
        }

    async def _initial_assignment(self, task: str) -> dict[str, list[dict]]:
        """初始任务分配"""
        # 简化：将任务平均分配给各组合
        assignments: dict[str, list[dict]] = {}

        for pair_id in self._pair_ids:
            assignments[pair_id] = [{"task": task, "phase": "initial"}]

        return assignments

    async def _execute_assignments(
        self, assignments: dict[str, list[dict]]
    ) -> list[dict[str, Any]]:
        """执行分配的任务"""
        results = []

        for pair_id, tasks in assignments.items():
            # 找到对应的智能体
            agent = next((a for a in self._agents if a.id == pair_id), None)
            if not agent:
                results.append(
                    {
                        "pair_id": pair_id,
                        "status": "failed",
                        "error": "Agent not found",
                    }
                )
                continue

            # 执行任务
            for task_item in tasks:
                result = await self._execute_pair(agent, task_item.get("task", ""))
                results.append(result)

        return results

    async def _reassign_tasks(
        self,
        remaining_task: str,
        completed_pairs: list[str],
        remaining_pairs: list[str],
    ) -> dict[str, list[dict]]:
        """重新分配任务

        Args:
            remaining_task: 剩余任务
            completed_pairs: 已完成的组合
            remaining_pairs: 待完成的组合

        Returns:
            新的分配方案
        """
        # 获取已完成的结果作为上下文
        completed_results = [
            e["data"].get("result")
            for e in self.session.get_events()
            if e["type"] == EventType.SUBAGENT_RESULT.value
            and e["data"].get("pair_id") in completed_pairs
        ]

        # 新分配
        assignments: dict[str, list[dict]] = {}
        for pair_id in remaining_pairs:
            assignments[pair_id] = [
                {
                    "task": remaining_task,
                    "context": completed_results,
                    "phase": "reassigned",
                }
            ]

        return assignments

    def get_pairs_status(self) -> list[dict[str, Any]]:
        """获取所有组合状态"""
        return [
            {
                "pair_id": agent.id,
                "status": agent.status,
            }
            for agent in self._agents
        ]
