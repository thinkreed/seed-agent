"""多智能体协作模块 - 多脑一手核心

包含 MultiBrainOneHandOrchestrator 的核心定义和基础方法。

版本: v2.0 (重构实现)
创建日期: 2026-05-05
"""

import logging
import uuid

from src.collaboration._types import AgentInstance
from src.llm_client import LLMClient
from src.sandbox import Sandbox

logger = logging.getLogger(__name__)


class MultiBrainOneHandOrchestrator:
    """多脑一手编排器：多个 Claude 共享一个 Sandbox

    适用场景：多角度分析同一份代码（安全审查 + 性能优化）

    核心特性：
    - 共享 Sandbox：所有大脑在同一工作台操作
    - 多视角分析：每个大脑从不同角度分析
    - 协作改进：融合建议后执行改进
    """

    def __init__(
        self,
        sandbox: Sandbox,
        llm_clients: list[LLMClient],
        perspectives: list[str] | None = None,
    ):
        """初始化多脑一手编排器

        Args:
            sandbox: 共享工作台
            llm_clients: 多个 LLMClient（大脑）
            perspectives: 分析视角列表（如 ["security", "performance", "readability"]）
        """
        self.sandbox = sandbox
        self.llm_clients = llm_clients

        # 创建智能体实例
        self._agents: list[AgentInstance] = []
        for i, client in enumerate(llm_clients):
            perspective = (
                perspectives[i]
                if perspectives and i < len(perspectives)
                else f"perspective_{i}"
            )
            self._agents.append(
                AgentInstance(
                    id=str(uuid.uuid4())[:8],
                    llm_client=client,
                    sandbox=sandbox,
                    perspective=perspective,
                )
            )

        self._perspectives: list[str] = perspectives or [
            a.perspective for a in self._agents if a.perspective is not None
        ]
        logger.info(
            f"MultiBrainOneHandOrchestrator initialized: "
            f"brains={len(llm_clients)}, perspectives={self._perspectives}"
        )

    def register_perspective(self, agent_index: int, perspective: str) -> None:
        """为智能体注册分析视角

        Args:
            agent_index: 智能体索引
            perspective: 分析视角
        """
        if agent_index < len(self._agents):
            self._agents[agent_index].perspective = perspective
            self._perspectives[agent_index] = perspective
            logger.debug(
                f"Perspective registered: agent={agent_index}, perspective={perspective}"
            )

    def get_agents_status(self) -> list[dict]:
        """获取所有智能体状态"""
        return [
            {
                "id": agent.id,
                "perspective": agent.perspective,
                "status": agent.status,
            }
            for agent in self._agents
        ]