"""多智能体协作模块测试

测试覆盖:
- MultiBrainOneHandOrchestrator: 多脑一手模式
- OneBrainMultiHandOrchestrator: 一脑多手模式
- MultiBrainMultiHandOrchestrator: 多脑多手模式
- InterAgentMessageBus: 智能体间消息总线
- 协作工具函数

版本: v2.0 (重写测试)
"""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.collaboration import (  # noqa: E402
    CollaborationMode,
    AgentInstance,
    AnalysisResult,
    ExecutionResult,
    CoordinationResult,
    MultiBrainOneHandOrchestrator,
    OneBrainMultiHandOrchestrator,
    MultiBrainMultiHandOrchestrator,
    InterAgentMessageBus,
)
from src.session_event_stream import SessionEventStream  # noqa: E402
from src.sandbox import Sandbox, IsolationLevel  # noqa: E402
from src.llm_client import LLMClient  # noqa: E402


# === Mock 类 ===

class MockGateway:
    """Mock LLMGateway"""

    def __init__(self):
        self.config = MagicMock()
        self.config.agents = {'defaults': MagicMock()}
        self.config.agents['defaults'].defaults = MagicMock()
        self.config.agents['defaults'].defaults.primary = "mock/model"


class MockLLMClient:
    """Mock LLMClient"""

    def __init__(self, model_id: str = "mock/model"):
        self.model_id = model_id
        self.reason = AsyncMock(return_value={
            "choices": [{
                "message": {
                    "content": "Mock response content",
                    "tool_calls": None
                }
            }]
        })


# === 测试类 ===

class TestCollaborationMode(unittest.TestCase):
    """测试协作模式枚举"""

    def test_modes_exist(self):
        """验证所有模式存在"""
        self.assertEqual(CollaborationMode.MULTI_BRAIN_ONE_HAND.value, "multi_brain_one_hand")
        self.assertEqual(CollaborationMode.ONE_BRAIN_MULTI_HAND.value, "one_brain_multi_hand")
        self.assertEqual(CollaborationMode.MULTI_BRAIN_MULTI_HAND.value, "multi_brain_multi_hand")


class TestAgentInstance(unittest.TestCase):
    """测试智能体实例"""

    def test_agent_creation(self):
        """测试创建智能体"""
        mock_client = MockLLMClient()
        agent = AgentInstance(
            id="agent-1",
            llm_client=mock_client,
            perspective="security",
        )

        self.assertEqual(agent.id, "agent-1")
        self.assertEqual(agent.perspective, "security")
        self.assertEqual(agent.status, "idle")

    def test_agent_with_sandbox(self):
        """测试带 Sandbox 的智能体"""
        mock_client = MockLLMClient()
        mock_sandbox = MagicMock(spec=Sandbox)
        agent = AgentInstance(
            id="agent-2",
            llm_client=mock_client,
            sandbox=mock_sandbox,
            label="python_env",
        )

        self.assertIsNotNone(agent.sandbox)
        self.assertEqual(agent.label, "python_env")


class TestAnalysisResult(unittest.TestCase):
    """测试分析结果"""

    def test_analysis_result(self):
        """测试分析结果"""
        result = AnalysisResult(
            perspective="security",
            result="No critical security issues found.",
            issues=["Potential XSS in line 42"],
            suggestions=["Add input validation"],
        )

        self.assertEqual(result.perspective, "security")
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(len(result.suggestions), 1)


class TestMultiBrainOneHandOrchestrator(unittest.TestCase):
    """测试多脑一手编排器"""

    def setUp(self):
        """测试前设置"""
        # 创建 Mock Sandbox
        self.mock_sandbox = MagicMock(spec=Sandbox)
        self.mock_sandbox.execute_tools = AsyncMock(return_value=[
            {"tool_call_id": "1", "content": "file content"}
        ])
        self.mock_sandbox.get_status = MagicMock(return_value={
            "isolation_level": "process",
            "tools_registered": 5,
        })

        # 创建 Mock LLMClient
        self.mock_clients = [MockLLMClient(), MockLLMClient()]
        self.perspectives = ["security", "performance"]

        self.orchestrator = MultiBrainOneHandOrchestrator(
            sandbox=self.mock_sandbox,
            llm_clients=self.mock_clients,
            perspectives=self.perspectives,
        )

    def test_orchestrator_creation(self):
        """测试编排器创建"""
        self.assertEqual(len(self.orchestrator.llm_clients), 2)
        self.assertEqual(len(self.orchestrator._agents), 2)
        self.assertEqual(self.orchestrator._perspectives, self.perspectives)

    def test_register_perspective(self):
        """测试注册视角"""
        self.orchestrator.register_perspective(0, "readability")
        self.assertEqual(self.orchestrator._perspectives[0], "readability")

    def test_get_agents_status(self):
        """测试获取状态"""
        status = self.orchestrator.get_agents_status()
        self.assertEqual(len(status), 2)
        self.assertEqual(status[0]["perspective"], "security")

    async def _test_analyze_from_multiple_angles(self):
        """测试多角度分析（异步）"""
        result = await self.orchestrator.analyze_from_multiple_angles("test.py")
        self.assertIn("analyses", result)
        self.assertEqual(len(result["analyses"]), 2)

    def test_analyze_from_multiple_angles(self):
        """测试多角度分析"""
        asyncio.run(self._test_analyze_from_multiple_angles())


class TestOneBrainMultiHandOrchestrator(unittest.TestCase):
    """测试一脑多手编排器"""

    def setUp(self):
        """测试前设置"""
        self.mock_client = MockLLMClient()

        # Sandbox 配置
        self.sandbox_configs = [
            {"isolation_level": "process"},
            {"isolation_level": "process"},
        ]
        self.labels = ["python_env", "node_env"]

        self.orchestrator = OneBrainMultiHandOrchestrator(
            llm_client=self.mock_client,
            sandbox_configs=self.sandbox_configs,
            labels=self.labels,
        )

    def test_orchestrator_creation(self):
        """测试编排器创建"""
        self.assertEqual(len(self.orchestrator.sandboxes), 2)
        self.assertEqual(len(self.orchestrator._agents), 2)
        self.assertEqual(list(self.orchestrator._sandbox_labels.values()), self.labels)

    def test_label_sandbox(self):
        """测试设置标签"""
        self.orchestrator.label_sandbox(0, "browser_env")
        self.assertEqual(self.orchestrator._sandbox_labels[0], "browser_env")

    def test_get_sandboxes_status(self):
        """测试获取状态"""
        status = self.orchestrator.get_sandboxes_status()
        self.assertEqual(len(status), 2)
        self.assertEqual(status[0]["label"], "python_env")

    async def _test_execute_in_multiple_environments(self):
        """测试跨环境执行（异步）"""
        # Mock Sandbox 执行
        for sandbox in self.orchestrator.sandboxes:
            sandbox.execute_tools = AsyncMock(return_value=[
                {"tool_call_id": "1", "content": "Execution result"}
            ])

        result = await self.orchestrator.execute_in_multiple_environments("Test task")
        self.assertIn("execution_results", result)
        self.assertIn("aggregated_result", result)

    def test_execute_in_multiple_environments(self):
        """测试跨环境执行"""
        asyncio.run(self._test_execute_in_multiple_environments())


class TestMultiBrainMultiHandOrchestrator(unittest.TestCase):
    """测试多脑多手编排器"""

    def setUp(self):
        """测试前设置"""
        # 创建 Session
        self.session = SessionEventStream("test-collab-session")

        # 创建 Mock 组合
        self.mock_clients = [MockLLMClient(), MockLLMClient()]
        self.mock_sandboxes = [MagicMock(spec=Sandbox), MagicMock(spec=Sandbox)]

        for sandbox in self.mock_sandboxes:
            sandbox.execute_tools = AsyncMock(return_value=[
                {"tool_call_id": "1", "content": "Result"}
            ])
            sandbox.get_status = MagicMock(return_value={"status": "ready"})

        self.agent_sandbox_pairs = list(zip(self.mock_clients, self.mock_sandboxes))

        self.orchestrator = MultiBrainMultiHandOrchestrator(
            session=self.session,
            agent_sandbox_pairs=self.agent_sandbox_pairs,
        )

    def test_orchestrator_creation(self):
        """测试编排器创建"""
        self.assertEqual(len(self.orchestrator._pairs), 2)
        self.assertEqual(len(self.orchestrator._agents), 2)
        self.assertEqual(len(self.orchestrator._pair_ids), 2)

    def test_register_pair(self):
        """测试注册组合"""
        new_client = MockLLMClient("new/model")
        new_sandbox = MagicMock(spec=Sandbox)

        pair_id = self.orchestrator.register_pair(new_client, new_sandbox)
        self.assertEqual(len(self.orchestrator._pairs), 3)
        self.assertIn(pair_id, self.orchestrator._pair_ids)

    def test_get_pairs_status(self):
        """测试获取状态"""
        status = self.orchestrator.get_pairs_status()
        self.assertEqual(len(status), 2)

    async def _test_coordinated_execution(self):
        """测试协调执行（异步）"""
        result = await self.orchestrator.coordinated_execution("Test task")
        # CoordinationResult 是 dataclass，使用属性访问
        self.assertEqual(len(result.agent_results), 2)
        self.assertIn("total_pairs", result.merged_result)

    def test_coordinated_execution(self):
        """测试协调执行"""
        asyncio.run(self._test_coordinated_execution())


class TestInterAgentMessageBus(unittest.TestCase):
    """测试智能体间消息总线"""

    def setUp(self):
        """测试前设置"""
        self.session = SessionEventStream("test-message-session")
        self.message_bus = InterAgentMessageBus(self.session)
        self.message_bus.set_pair_ids(["agent-1", "agent-2", "agent-3"])

    def test_message_bus_creation(self):
        """测试消息总线创建"""
        self.assertEqual(len(self.message_bus._pair_ids), 3)
        # Session 可能已有事件，只检查消息总线是否正确初始化
        self.assertIsNotNone(self.message_bus.session)

    def test_register_handler(self):
        """测试注册处理器"""
        handler = MagicMock()
        self.message_bus.register_handler("test_type", handler)
        self.assertIn("test_type", self.message_bus._message_handlers)

    async def _test_send_message(self):
        """测试发送消息（异步）"""
        message_id = await self.message_bus.send_message(
            from_agent="agent-1",
            to_agent="agent-2",
            message_type="task_update",
            content={"progress": 50},
        )
        self.assertIsInstance(message_id, int)
        self.assertGreater(self.message_bus.get_message_count(), 0)

    def test_send_message(self):
        """测试发送消息"""
        asyncio.run(self._test_send_message())

    async def _test_broadcast(self):
        """测试广播消息（异步）"""
        message_ids = await self.message_bus.broadcast(
            from_agent="agent-1",
            message_type="broadcast_test",
            content={"status": "completed"},
            exclude_self=True,
        )
        self.assertEqual(len(message_ids), 2)  # 排除自己，发给 2 个

    def test_broadcast(self):
        """测试广播消息"""
        asyncio.run(self._test_broadcast())

    async def _test_receive_messages(self):
        """测试接收消息（异步）"""
        # 先发送一条消息
        await self.message_bus.send_message(
            from_agent="agent-1",
            to_agent="agent-2",
            message_type="test",
            content={"data": "test"},
        )

        # 接收消息
        messages = await self.message_bus.receive_messages("agent-2")
        self.assertGreater(len(messages), 0)

    def test_receive_messages(self):
        """测试接收消息"""
        asyncio.run(self._test_receive_messages())

    def test_clear_handlers(self):
        """测试清除处理器"""
        self.message_bus.register_handler("type1", MagicMock())
        self.message_bus.register_handler("type2", MagicMock())
        self.message_bus.clear_handlers()
        self.assertEqual(len(self.message_bus._message_handlers), 0)


class TestCollaborationTools(unittest.TestCase):
    """测试协作工具函数"""

    def setUp(self):
        """测试前设置"""
        # 清理全局状态
        from src.tools.collaboration_tools import (
            _collaboration_sessions,
            _orchestrators,
            _message_buses,
        )
        _collaboration_sessions.clear()
        _orchestrators.clear()
        _message_buses.clear()

    def test_create_collaboration_session(self):
        """测试创建协作会话"""
        from src.tools.collaboration_tools import create_collaboration_session

        result = create_collaboration_session(
            session_id="test-session-1",
            mode="multi_brain_one_hand",
        )
        self.assertIn("created", result)

    def test_create_collaboration_session_invalid_mode(self):
        """测试无效模式"""
        from src.tools.collaboration_tools import create_collaboration_session

        result = create_collaboration_session(
            session_id="test-session-2",
            mode="invalid_mode",
        )
        self.assertIn("Error", result)

    def test_get_collaboration_status(self):
        """测试获取状态"""
        from src.tools.collaboration_tools import (
            create_collaboration_session,
            get_collaboration_status,
        )

        create_collaboration_session("test-session-3", "multi_brain_one_hand")
        result = get_collaboration_status("test-session-3")
        self.assertIn("multi_brain_one_hand", result)

    def test_get_collaboration_status_not_found(self):
        """测试不存在的会话"""
        from src.tools.collaboration_tools import get_collaboration_status

        result = get_collaboration_status("nonexistent-session")
        self.assertIn("Error", result)

    def test_destroy_collaboration_session(self):
        """测试销毁会话"""
        from src.tools.collaboration_tools import (
            create_collaboration_session,
            destroy_collaboration_session,
        )

        create_collaboration_session("test-session-4", "multi_brain_one_hand")
        result = destroy_collaboration_session("test-session-4")
        self.assertIn("destroyed", result)

    def test_destroy_collaboration_session_not_found(self):
        """测试销毁不存在的会话"""
        from src.tools.collaboration_tools import destroy_collaboration_session

        result = destroy_collaboration_session("nonexistent-session")
        self.assertIn("Error", result)


class TestIntegration(unittest.TestCase):
    """集成测试"""

    def setUp(self):
        """测试前设置"""
        self.session = SessionEventStream("integration-test-session")

    async def _test_full_collaboration_flow(self):
        """测试完整协作流程"""
        # 1. 创建 Mock 组合
        mock_clients = [
            MockLLMClient("security/model"),
            MockLLMClient("performance/model"),
        ]
        mock_sandboxes = [
            MagicMock(spec=Sandbox),
            MagicMock(spec=Sandbox),
        ]

        for sandbox in mock_sandboxes:
            sandbox.execute_tools = AsyncMock(return_value=[
                {"tool_call_id": "1", "content": "Result"}
            ])
            sandbox.get_status = MagicMock(return_value={"status": "ready"})

        # 2. 创建消息总线
        message_bus = InterAgentMessageBus(self.session)
        message_bus.set_pair_ids(["pair-1", "pair-2"])

        # 3. 创建编排器
        orchestrator = MultiBrainMultiHandOrchestrator(
            session=self.session,
            agent_sandbox_pairs=list(zip(mock_clients, mock_sandboxes)),
            message_bus=message_bus,
        )

        # 4. 执行协调任务
        result = await orchestrator.coordinated_execution(
            "Analyze code for security and performance issues"
        )

        # 5. 验证结果（CoordinationResult 是 dataclass）
        self.assertEqual(len(result.agent_results), 2)
        self.assertIn("total_pairs", result.merged_result)
        self.assertGreater(len(result.session_events), 0)

        # 6. 发送消息
        await message_bus.send_message(
            "pair-1", "pair-2", "sync", {"status": "completed"}
        )
        self.assertGreater(message_bus.get_message_count(), 0)

    def test_full_collaboration_flow(self):
        """测试完整协作流程"""
        asyncio.run(self._test_full_collaboration_flow())


if __name__ == "__main__":
    unittest.main(verbosity=2)