"""多脑多手编排器核心模块

MultiBrainMultiHandOrchestrator: 多脑多手编排器
"""

import logging
import uuid
from typing import Any

from src.collaboration._message_bus import InterAgentMessageBus
from src.collaboration._multi_brain_multi_hand._coordinated_execution import (
    coordinated_execution,
)
from src.collaboration._multi_brain_multi_hand._pair_executor import execute_assignments
from src.collaboration._multi_brain_multi_hand._task_coordinator import (
    dynamic_task_assignment,
)
from src.collaboration._types import AgentInstance
from src.llm_client import LLMClient
from src.sandbox import Sandbox
from src.session_event_stream import SessionEventStream

logger = logging.getLogger(__name__)


class MultiBrainMultiHandOrchestrator:
    """多脑多手编排器：多个 Claude + 多个 Sandbox + Session 协调"""

    def __init__(
        self,
        session: SessionEventStream,
        agent_sandbox_pairs: list[tuple[LLMClient, Sandbox]] | None = None,
        message_bus: InterAgentMessageBus | None = None,
    ):
        self.session = session
        self._pairs: list[tuple[LLMClient, Sandbox]] = agent_sandbox_pairs or []
        self._message_bus = message_bus
        self._agents: list[AgentInstance] = []
        self._pair_ids: list[str] = []

        for _, (llm_client, sandbox) in enumerate(self._pairs):
            pair_id = str(uuid.uuid4())[:8]
            self._pair_ids.append(pair_id)
            self._agents.append(AgentInstance(id=pair_id, llm_client=llm_client, sandbox=sandbox))

        self._task_assignments: dict[str, list[dict]] = {}

        logger.info(
            f"MultiBrainMultiHandOrchestrator initialized: "
            f"pairs={len(self._pairs)}, session={session.session_id}"
        )

    def register_pair(
        self, llm_client: LLMClient, sandbox: Sandbox, pair_id: str | None = None
    ) -> str:
        pair_id = pair_id or str(uuid.uuid4())[:8]
        self._pairs.append((llm_client, sandbox))
        self._pair_ids.append(pair_id)
        self._agents.append(AgentInstance(id=pair_id, llm_client=llm_client, sandbox=sandbox))
        logger.info(f"Pair registered: {pair_id}")
        return pair_id

    async def coordinated_execution(self, task: str) -> Any:
        return await coordinated_execution(self.session, self._agents, self._pair_ids, task)

    async def dynamic_task_assignment(self, task: str) -> dict[str, Any]:
        return await dynamic_task_assignment(
            task, self._pair_ids, self._agents, self.session, execute_assignments
        )

    def get_pairs_status(self) -> list[dict[str, Any]]:
        return [{"pair_id": agent.id, "status": agent.status} for agent in self._agents]