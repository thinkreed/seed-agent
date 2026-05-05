"""多脑多手编排器核心模块

MultiBrainMultiHandOrchestrator: 多脑多手编排器

适用场景：最复杂的多步骤任务

核心特性：
- Session 协调：共享 Session 作为协调中心
- 独立组合：每个 Claude 有自己的 Sandbox
- 动态分配：根据进度调整任务分配
- 消息总线：智能体间通信

版本: v2.0 (重构实现)
"""

import asyncio
import logging
import uuid
from typing import Any

from src.collaboration._message_bus import InterAgentMessageBus
from src.collaboration._multi_brain_multi_hand._pair_executor import (
    execute_assignments,
    execute_pair,
)
from src.collaboration._multi_brain_multi_hand._result_merger import merge_from_session
from src.collaboration._multi_brain_multi_hand._task_coordinator import (
    dynamic_task_assignment,
)
from src.collaboration._types import AgentInstance, CoordinationResult
from src.llm_client import LLMClient
from src.sandbox import Sandbox
from src.session_event_stream import EventType, SessionEventStream

logger = logging.getLogger(__name__)


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
            *[
                execute_pair(agent, task, {}, self._agents)
                for agent in self._agents
            ],
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
        merged = await merge_from_session(self.session, self._agents)

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

    async def dynamic_task_assignment(self, task: str) -> dict[str, Any]:
        """动态任务分配

        根据执行进度动态调整任务分配

        Args:
            task: 任务描述

        Returns:
            分配结果
        """
        return await dynamic_task_assignment(
            task,
            self._pair_ids,
            self._agents,
            self.session,
            execute_assignments,
        )

    def get_pairs_status(self) -> list[dict[str, Any]]:
        """获取所有组合状态"""
        return [
            {
                "pair_id": agent.id,
                "status": agent.status,
            }
            for agent in self._agents
        ]