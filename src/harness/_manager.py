"""
Harness 管理器模块

提取 HarnessManager 类，支持多实例管理。

内容:
- HarnessManager - Harness 生命周期管理器
"""

import logging
from typing import TYPE_CHECKING, Any

from src.llm_client import LLMClient
from src.sandbox import Sandbox
from src.session_event_stream import SessionEventStream

if TYPE_CHECKING:
    from src.client import LLMGateway

logger = logging.getLogger(__name__)

# 最大迭代次数（安全上限）
MAX_ITERATIONS = 100


class HarnessManager:
    """Harness 管理器 - 支持多实例

    用于管理多个 Harness 实例，支持：
    - 创建新 Harness（牲畜可替换）
    - 销毁 Harness
    - 多实例协作
    - 状态持久化

    使用场景：
    - 多用户并发对话
    - 多任务并行执行
    - 容错恢复
    """

    def __init__(self, gateway_config_path: str):
        """初始化 HarnessManager

        Args:
            gateway_config_path: Gateway 配置文件路径
        """
        self._gateway_config_path = gateway_config_path
        self._harnesses: dict[str, Any] = {}  # harness_id -> Harness
        self._sandboxes: dict[str, Sandbox] = {}  # harness_id -> Sandbox
        self._gateway: LLMGateway | None = None

        logger.info("HarnessManager initialized")

    def _ensure_gateway(self) -> "LLMGateway":
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
        """创建新的 Harness 实例

        Args:
            harness_id: Harness 实例 ID
            model_id: 模型 ID
            system_prompt: 系统提示
            sandbox_config: Sandbox 配置
            max_iterations: 最大迭代次数

        Returns:
            Harness 实例
        """
        gateway = self._ensure_gateway()

        # 创建 LLMClient
        llm_client = LLMClient(gateway, model_id)

        # 创建 Sandbox
        sandbox_config = sandbox_config or {}
        sandbox = Sandbox(**sandbox_config)

        # 创建 Session
        session = SessionEventStream(harness_id)

        # 创建 Harness（延迟导入避免循环依赖）
        from src.harness import Harness

        harness = Harness(
            llm_client,
            session,
            sandbox,
            max_iterations=max_iterations,
            system_prompt=system_prompt,
        )

        # 注册
        self._harnesses[harness_id] = harness
        self._sandboxes[harness_id] = sandbox

        logger.info(f"Harness created: id={harness_id}, model={model_id}")
        return harness

    def get_harness(self, harness_id: str) -> Any | None:
        """获取 Harness 实例

        Args:
            harness_id: Harness 实例 ID

        Returns:
            Harness 实例或 None
        """
        return self._harnesses.get(harness_id)

    def destroy_harness(self, harness_id: str) -> bool:
        """销毁 Harness（牲畜可替换）

        Args:
            harness_id: Harness 实例 ID

        Returns:
            是否成功销毁
        """
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
        """列出所有 Harness ID

        Returns:
            Harness ID 列表
        """
        return list(self._harnesses.keys())

    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """获取所有 Harness 状态

        Returns:
            harness_id -> status 字典
        """
        return {h_id: harness.get_status() for h_id, harness in self._harnesses.items()}

    def destroy_all(self) -> None:
        """销毁所有 Harness"""
        for harness_id in list(self._harnesses.keys()):
            self.destroy_harness(harness_id)
        logger.info("All harnesses destroyed")

    def get_total_metrics(self) -> dict[str, Any]:
        """获取所有 Harness 的总指标

        Returns:
            总指标统计
        """
        total_tools = 0
        total_success = 0
        total_failed = 0
        total_duration_ms = 0.0

        for harness in self._harnesses.values():
            metrics = harness.get_metrics()
            total_tools += len(metrics)
            for m in metrics:
                if m["success"]:
                    total_success += 1
                else:
                    total_failed += 1
                total_duration_ms += m["duration_ms"]

        return {
            "total_tool_calls": total_tools,
            "successful_calls": total_success,
            "failed_calls": total_failed,
            "total_duration_ms": total_duration_ms,
            "average_duration_ms": total_duration_ms / total_tools if total_tools > 0 else 0,
        }