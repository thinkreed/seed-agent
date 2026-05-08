"""
Harness 管理器模块

提取 HarnessManager 类，支持多实例管理。

内容:
- HarnessManager - Harness 生命周期管理器
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from src.llm_client import LLMClient
from src.sandbox import Sandbox
from src.session_event_stream import SessionEventStream
from src.harness._manager_metrics import calculate_total_metrics
from src.harness._manager_types import MAX_ITERATIONS

if TYPE_CHECKING:
    from src.client import LLMGateway

logger = logging.getLogger(__name__)


class HarnessManager:
    """Harness 管理器 - 支持多实例"""

    def __init__(self, gateway_config_path: str) -> None:
        """初始化 HarnessManager"""
        self._gateway_config_path = gateway_config_path
        self._harnesses: dict[str, Any] = {}
        self._sandboxes: dict[str, Sandbox] = {}
        self._gateway: LLMGateway | None = None
        logger.info("HarnessManager initialized")

    def _ensure_gateway(self) -> LLMGateway:
        """确保 Gateway 已创建"""
        if not self._gateway:
            from src.client import LLMGateway
            self._gateway = LLMGateway(self._gateway_config_path)
        return self._gateway

    def create_harness(
        self,
        harness_id: str,
        model_id: str,
        system_prompt: str | None = None,
        sandbox_config: dict[str, Any] | None = None,
        max_iterations: int = MAX_ITERATIONS,
    ) -> Any:
        """创建新的 Harness 实例"""
        gateway = self._ensure_gateway()
        llm_client = LLMClient(gateway, model_id)
        sandbox_config = sandbox_config or {}
        sandbox = Sandbox(**sandbox_config)
        session = SessionEventStream(harness_id)

        from src.harness import Harness as HarnessClass
        harness = cast("Any", HarnessClass)(
            llm_client, session, sandbox,
            max_iterations=max_iterations, system_prompt=system_prompt,
        )

        self._harnesses[harness_id] = harness
        self._sandboxes[harness_id] = sandbox
        logger.info(f"Harness created: id={harness_id}, model={model_id}")
        return harness

    def get_harness(self, harness_id: str) -> Any | None:
        """获取 Harness 实例"""
        return self._harnesses.get(harness_id)

    def destroy_harness(self, harness_id: str) -> bool:
        """销毁 Harness"""
        if harness_id in self._harnesses:
            harness = self._harnesses[harness_id]
            harness.session.record_session_end("destroyed")
            del self._harnesses[harness_id]

        if harness_id in self._sandboxes:
            sandbox = self._sandboxes[harness_id]
            sandbox.cleanup()
            del self._sandboxes[harness_id]

        logger.info(f"Harness destroyed: id={harness_id}")
        return True

    def list_harnesses(self) -> list[str]:
        """列出所有 Harness ID"""
        return list(self._harnesses.keys())

    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """获取所有 Harness 状态"""
        return {h_id: harness.get_status() for h_id, harness in self._harnesses.items()}

    def destroy_all(self) -> None:
        """销毁所有 Harness"""
        for harness_id in list(self._harnesses.keys()):
            self.destroy_harness(harness_id)
        logger.info("All harnesses destroyed")

    def get_total_metrics(self) -> dict[str, Any]:
        """获取所有 Harness 的总指标"""
        return calculate_total_metrics(self._harnesses)


__all__ = ["MAX_ITERATIONS", "HarnessManager"]