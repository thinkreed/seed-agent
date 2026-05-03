"""Subagent 机制单元测试"""

import sys
import asyncio
import unittest
from pathlib import Path
from unittest.mock import Mock, AsyncMock

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 导入测试模块（使用 src 前缀确保一致性）
from src.subagent import (  # noqa: E402
    SubagentType,
    SubagentInstance,
    SubagentState,
    SubagentResult,
    PERMISSION_SETS,
    SUBAGENT_TYPE_PERMISSIONS,
    SUBAGENT_SYSTEM_PROMPTS,
)
from src.subagent_manager import (  # noqa: E402
    SubagentManager,
    RalphSubagentOrchestrator,
)


class TestSubagentType(unittest.TestCase):
    """测试 Subagent 类型枚举"""

    def test_subagent_types_exist(self):
        """验证所有 Subagent 类型存在"""
        self.assertEqual(SubagentType.EXPLORE.value, "explore")
        self.assertEqual(SubagentType.REVIEW.value, "review")
        self.assertEqual(SubagentType.IMPLEMENT.value, "implement")
        self.assertEqual(SubagentType.PLAN.value, "plan")

    def test_permission_sets_defined(self):
        """验证权限集定义完整"""
        self.assertIn("read_only", PERMISSION_SETS)
        self.assertIn("review", PERMISSION_SETS)
        self.assertIn("implement", PERMISSION_SETS)
        self.assertIn("plan", PERMISSION_SETS)

        # 验证 read_only 权限集
        self.assertIn("file_read", PERMISSION_SETS["read_only"])
        self.assertNotIn("file_write", PERMISSION_SETS["read_only"])

        # 验证 implement 权限集包含全部权限
        self.assertIn("file_read", PERMISSION_SETS["implement"])
        self.assertIn("file_write", PERMISSION_SETS["implement"])
        self.assertIn("file_edit", PERMISSION_SETS["implement"])

    def test_type_permission_mapping(self):
        """验证类型与权限集映射"""
        self.assertEqual(SUBAGENT_TYPE_PERMISSIONS["explore"], "read_only")
        self.assertEqual(SUBAGENT_TYPE_PERMISSIONS["review"], "review")
        self.assertEqual(SUBAGENT_TYPE_PERMISSIONS["implement"], "implement")
        self.assertEqual(SUBAGENT_TYPE_PERMISSIONS["plan"], "plan")

    def test_system_prompts_defined(self):
        """验证 System Prompt 定义"""
        for subagent_type in SubagentType:
            self.assertIn(subagent_type.value, SUBAGENT_SYSTEM_PROMPTS)
            prompt = SUBAGENT_SYSTEM_PROMPTS[subagent_type.value]
            self.assertGreater(len(prompt), 50)


class TestSubagentState(unittest.TestCase):
    """测试 Subagent 状态"""

    def test_state_creation(self):
        """测试状态创建"""
        state = SubagentState(
            id="test-123",
            subagent_type=SubagentType.EXPLORE,
            status="pending",
            prompt="Test prompt"
        )

        self.assertEqual(state.id, "test-123")
        self.assertEqual(state.status, "pending")
        self.assertIsNone(state.result)
        self.assertIsNone(state.error)

    def test_state_timing(self):
        """测试时间记录"""
        from datetime import datetime

        state = SubagentState(
            id="test-123",
            subagent_type=SubagentType.EXPLORE,
            status="running",
            prompt="Test prompt",
            started_at=datetime.now()
        )

        self.assertIsNotNone(state.started_at)
        self.assertIsNone(state.completed_at)


class TestSubagentResult(unittest.TestCase):
    """测试 Subagent 结果"""

    def test_success_result(self):
        """测试成功结果"""
        state = SubagentState(
            id="test-123",
            subagent_type=SubagentType.EXPLORE,
            status="completed",
            prompt="Test prompt",
            result="Found 3 files matching the pattern."
        )

        result = SubagentResult(state)
        self.assertTrue(result.success)
        self.assertEqual(result.result, "Found 3 files matching the pattern.")
        self.assertIsNone(result.error)

    def test_failed_result(self):
        """测试失败结果"""
        state = SubagentState(
            id="test-123",
            subagent_type=SubagentType.EXPLORE,
            status="failed",
            prompt="Test prompt",
            error="Connection timeout"
        )

        result = SubagentResult(state)
        self.assertFalse(result.success)
        self.assertIsNone(result.result)
        self.assertEqual(result.error, "Connection timeout")

    def test_summary_truncation(self):
        """测试摘要截断"""
        long_result = "A" * 600
        state = SubagentState(
            id="test-123",
            subagent_type=SubagentType.EXPLORE,
            status="completed",
            prompt="Test prompt",
            result=long_result
        )

        result = SubagentResult(state)
        summary = result.summary
        # 检查截断逻辑工作（结果被截断）
        self.assertTrue("...(truncated)" in summary or len(summary) < len(long_result))

    def test_to_dict(self):
        """测试字典转换"""
        state = SubagentState(
            id="test-123",
            subagent_type=SubagentType.EXPLORE,
            status="completed",
            prompt="Test prompt",
            result="Test result",
            iterations=5
        )

        result = SubagentResult(state)
        d = result.to_dict()

        self.assertEqual(d["id"], "test-123")
        self.assertEqual(d["type"], "explore")
        self.assertEqual(d["status"], "completed")
        self.assertEqual(d["iterations"], 5)


class TestSubagentInstance(unittest.TestCase):
    """测试 SubagentInstance"""

    def setUp(self):
        """测试前设置"""
        # 创建 Mock Gateway
        self.gateway_mock = Mock()
        self.gateway_mock.config = Mock()
        self.gateway_mock.config.agents = {'defaults': Mock()}
        self.gateway_mock.config.agents['defaults'].defaults = Mock()
        self.gateway_mock.config.agents['defaults'].defaults.primary = "test/test-model"

        # Mock chat_completion
        self.gateway_mock.chat_completion = AsyncMock()

    def test_instance_creation(self):
        """测试实例创建"""
        instance = SubagentInstance(
            gateway=self.gateway_mock,
            subagent_type=SubagentType.EXPLORE,
        )

        self.assertEqual(instance.subagent_type, SubagentType.EXPLORE)
        self.assertEqual(instance.max_iterations, 100)  # 默认值已更新为 100
        self.assertEqual(instance.timeout, 180)  # EXPLORE 默认 180s
        self.assertEqual(len(instance.history), 0)

    def test_instance_type_based_defaults(self):
        """测试基于类型的默认超时配置"""
        from subagent import DEFAULT_TIMEOUTS

        # EXPLORE: 180s, REVIEW: 600s, IMPLEMENT: 900s, PLAN: 300s
        for sub_type, expected_timeout in DEFAULT_TIMEOUTS.items():
            instance = SubagentInstance(
                gateway=self.gateway_mock,
                subagent_type=sub_type,
            )
            self.assertEqual(instance.timeout, expected_timeout, f"Timeout mismatch for {sub_type}")

    def test_tool_filtering(self):
        """测试工具过滤"""
        instance = SubagentInstance(
            gateway=self.gateway_mock,
            subagent_type=SubagentType.EXPLORE,  # read_only 权限集
        )

        # EXPLORE 类型应该只有 read_only 工具
        allowed_tools = PERMISSION_SETS["read_only"]
        for tool_name in instance.tools._tools.keys():
            self.assertIn(tool_name, allowed_tools)

        # 确保危险工具不在列表中
        self.assertNotIn("file_write", instance.tools._tools)
        self.assertNotIn("file_edit", instance.tools._tools)
        self.assertNotIn("code_as_policy", instance.tools._tools)

    def test_custom_tools_override(self):
        """测试自定义工具覆盖"""
        custom_tools = {"file_read", "search_history"}
        instance = SubagentInstance(
            gateway=self.gateway_mock,
            subagent_type=SubagentType.IMPLEMENT,  # 默认全权限
            custom_tools=custom_tools,
        )

        # 应该只有自定义工具
        for tool_name in instance.tools._tools.keys():
            self.assertIn(tool_name, custom_tools)

    def test_custom_system_prompt(self):
        """测试自定义 System Prompt"""
        custom_prompt = "This is a custom prompt for testing."
        instance = SubagentInstance(
            gateway=self.gateway_mock,
            subagent_type=SubagentType.EXPLORE,
            custom_system_prompt=custom_prompt,
        )

        self.assertEqual(instance.system_prompt, custom_prompt)

    async def async_test_run_loop_success(self):
        """测试执行循环成功（异步）"""
        # Mock LLM 返回无工具调用的响应
        self.gateway_mock.chat_completion.return_value = {
            'choices': [{
                'message': {
                    'role': 'assistant',
                    'content': 'Task completed successfully.',
                    'tool_calls': None
                }
            }]
        }

        instance = SubagentInstance(
            gateway=self.gateway_mock,
            subagent_type=SubagentType.EXPLORE,
            max_iterations=3,
        )

        state = await instance.run("Test prompt")

        self.assertEqual(state.status, "completed")
        self.assertEqual(state.result, "Task completed successfully.")
        self.assertEqual(state.iterations, 1)

    def test_run_loop_success(self):
        """测试执行循环成功"""
        asyncio.run(self.async_test_run_loop_success())


class TestSubagentManager(unittest.TestCase):
    """测试 SubagentManager"""

    def setUp(self):
        """测试前设置"""
        self.gateway_mock = Mock()
        self.gateway_mock.config = Mock()
        self.gateway_mock.config.agents = {'defaults': Mock()}
        self.gateway_mock.config.agents['defaults'].defaults = Mock()
        self.gateway_mock.config.agents['defaults'].defaults.primary = "test/test-model"

    def test_manager_creation(self):
        """测试管理器创建"""
        manager = SubagentManager(
            gateway=self.gateway_mock,
            max_concurrent=3,
        )

        self.assertEqual(manager.max_concurrent, 3)
        self.assertEqual(len(manager._tasks), 0)
        self.assertEqual(len(manager._instances), 0)

    def test_create_task(self):
        """测试创建任务"""
        manager = SubagentManager(gateway=self.gateway_mock)

        task_id = manager.create_task(
            subagent_type=SubagentType.EXPLORE,
            prompt="Search for config files",
        )

        self.assertIn(task_id, manager._tasks)
        task = manager._tasks[task_id]
        self.assertEqual(task.subagent_type, SubagentType.EXPLORE)
        self.assertEqual(task.prompt, "Search for config files")

    def test_spawn_subagent(self):
        """测试创建 Subagent 实例"""
        manager = SubagentManager(gateway=self.gateway_mock)

        task_id = manager.create_task(
            subagent_type=SubagentType.EXPLORE,
            prompt="Test prompt",
        )

        instance = manager.spawn_subagent(task_id)

        self.assertIn(task_id, manager._instances)
        self.assertIsInstance(instance, SubagentInstance)
        self.assertEqual(instance.subagent_type, SubagentType.EXPLORE)

    def test_spawn_subagent_not_found(self):
        """测试任务不存在"""
        manager = SubagentManager(gateway=self.gateway_mock)

        with self.assertRaises(ValueError):
            manager.spawn_subagent("nonexistent-id")

    def test_convenience_methods(self):
        """测试便捷方法"""
        manager = SubagentManager(gateway=self.gateway_mock)

        explore_id = manager.spawn_explore("Explore task")
        review_id = manager.spawn_review("Review task")
        implement_id = manager.spawn_implement("Implement task")
        plan_id = manager.spawn_plan("Plan task")

        self.assertEqual(manager._tasks[explore_id].subagent_type, SubagentType.EXPLORE)
        self.assertEqual(manager._tasks[review_id].subagent_type, SubagentType.REVIEW)
        self.assertEqual(manager._tasks[implement_id].subagent_type, SubagentType.IMPLEMENT)
        self.assertEqual(manager._tasks[plan_id].subagent_type, SubagentType.PLAN)

    def test_get_status(self):
        """测试获取状态"""
        manager = SubagentManager(gateway=self.gateway_mock)

        task_id = manager.create_task(SubagentType.EXPLORE, "Test")
        status = manager.get_status(task_id)
        self.assertEqual(status, "pending")

        # 不存在的任务
        self.assertIsNone(manager.get_status("nonexistent"))

    def test_cleanup_single(self):
        """测试清理单个任务"""
        manager = SubagentManager(gateway=self.gateway_mock)

        task_id = manager.create_task(SubagentType.EXPLORE, "Test")
        manager.spawn_subagent(task_id)

        manager.cleanup(task_id)

        self.assertNotIn(task_id, manager._tasks)
        self.assertNotIn(task_id, manager._instances)

    def test_cleanup_all(self):
        """测试清理所有任务"""
        manager = SubagentManager(gateway=self.gateway_mock)

        manager.create_task(SubagentType.EXPLORE, "Test 1")
        manager.create_task(SubagentType.REVIEW, "Test 2")

        manager.cleanup()

        self.assertEqual(len(manager._tasks), 0)

    def test_list_tasks(self):
        """测试列出任务"""
        manager = SubagentManager(gateway=self.gateway_mock)

        manager.create_task(SubagentType.EXPLORE, "Short prompt")
        manager.create_task(SubagentType.REVIEW, "A very long prompt that should be truncated")

        tasks = manager.list_tasks()

        self.assertEqual(len(tasks), 2)

    def test_aggregate_results(self):
        """测试聚合结果"""
        manager = SubagentManager(gateway=self.gateway_mock)

        # 创建两个任务并模拟完成
        task_id1 = manager.create_task(SubagentType.EXPLORE, "Test 1")
        task_id2 = manager.create_task(SubagentType.REVIEW, "Test 2")

        # 手动添加结果
        state1 = SubagentState(
            id=task_id1,
            subagent_type=SubagentType.EXPLORE,
            status="completed",
            prompt="Test 1",
            result="Found 5 files"
        )
        state2 = SubagentState(
            id=task_id2,
            subagent_type=SubagentType.REVIEW,
            status="failed",
            prompt="Test 2",
            error="Review failed"
        )

        manager._results[task_id1] = SubagentResult(state1)
        manager._results[task_id2] = SubagentResult(state2)

        # 聚合结果（包含错误）
        aggregated = manager.aggregate_results([task_id1, task_id2])
        self.assertIn("SUCCESS", aggregated)
        self.assertIn("FAILED", aggregated)

        # 聚合结果（不包含错误）
        aggregated_no_errors = manager.aggregate_results([task_id1, task_id2], include_errors=False)
        self.assertIn("SUCCESS", aggregated_no_errors)
        self.assertNotIn("FAILED", aggregated_no_errors)


class TestRalphSubagentOrchestrator(unittest.TestCase):
    """测试 Ralph Subagent 编排器"""

    def setUp(self):
        self.gateway_mock = Mock()
        self.gateway_mock.config = Mock()
        self.gateway_mock.config.agents = {'defaults': Mock()}
        self.gateway_mock.config.agents['defaults'].defaults = Mock()
        self.gateway_mock.config.agents['defaults'].defaults.primary = "test/test-model"
        self.gateway_mock.chat_completion = AsyncMock()

    def test_orchestrator_creation(self):
        """测试编排器创建"""
        manager = SubagentManager(gateway=self.gateway_mock)
        orchestrator = RalphSubagentOrchestrator(manager)

        self.assertEqual(orchestrator.manager, manager)
        self.assertIsNone(orchestrator._plan_task_id)

    def test_get_execution_report(self):
        """测试获取执行报告"""
        manager = SubagentManager(gateway=self.gateway_mock)
        orchestrator = RalphSubagentOrchestrator(manager)

        report = orchestrator.get_execution_report()

        self.assertIn("plan", report)
        self.assertIn("implement", report)
        self.assertIn("review", report)

    def test_cleanup(self):
        """测试编排器清理"""
        manager = SubagentManager(gateway=self.gateway_mock)
        orchestrator = RalphSubagentOrchestrator(manager)

        orchestrator._plan_task_id = "plan-1"
        orchestrator._implement_task_ids = ["impl-1", "impl-2"]
        orchestrator._review_task_id = "review-1"

        orchestrator.cleanup()

        self.assertIsNone(orchestrator._plan_task_id)
        self.assertEqual(len(orchestrator._implement_task_ids), 0)
        self.assertIsNone(orchestrator._review_task_id)


class TestSubagentTools(unittest.TestCase):
    """测试 Subagent 工具"""

    def setUp(self):
        """测试前设置"""
        from tools.subagent_tools import init_subagent_manager

        self.gateway_mock = Mock()
        self.gateway_mock.config = Mock()
        self.gateway_mock.config.agents = {'defaults': Mock()}
        self.gateway_mock.config.agents['defaults'].defaults = Mock()
        self.gateway_mock.config.agents['defaults'].defaults.primary = "test/test-model"

        self.manager = SubagentManager(gateway=self.gateway_mock)
        init_subagent_manager(self.manager)

    def test_spawn_subagent(self):
        """测试 spawn_subagent 工具"""
        from tools.subagent_tools import spawn_subagent

        result = spawn_subagent(
            type="explore",
            prompt="Find all Python files",
        )

        self.assertIn("Subagent task created", result)
        self.assertIn("explore", result)

    def test_spawn_subagent_invalid_type(self):
        """测试无效类型"""
        from tools.subagent_tools import spawn_subagent

        result = spawn_subagent(
            type="invalid_type",
            prompt="Test",
        )

        self.assertIn("Error", result)
        self.assertIn("Unknown subagent type", result)

    def test_list_subagents(self):
        """测试列出子代理"""
        from tools.subagent_tools import list_subagents, spawn_subagent

        spawn_subagent("explore", "Test 1")
        spawn_subagent("review", "Test 2")

        result = list_subagents()

        self.assertIn("Subagent Tasks", result)
        self.assertIn("explore", result)
        self.assertIn("review", result)

    def test_list_subagents_empty(self):
        """测试空列表"""
        from tools.subagent_tools import list_subagents

        self.manager.cleanup()
        result = list_subagents()

        self.assertIn("No subagent tasks found", result)

    def test_get_subagent_status(self):
        """测试获取状态"""
        from tools.subagent_tools import get_subagent_status, spawn_subagent

        task_id_result = spawn_subagent("explore", "Test")
        # 提取 task_id
        task_id = task_id_result.split("\n")[0].split(": ")[1]

        result = get_subagent_status(task_id)

        self.assertIn(task_id, result)
        self.assertIn("pending", result)

    def test_kill_subagent(self):
        """测试终止子代理"""
        from tools.subagent_tools import kill_subagent, spawn_subagent

        task_id_result = spawn_subagent("explore", "Test")
        task_id = task_id_result.split("\n")[0].split(": ")[1]

        result = kill_subagent(task_id)

        self.assertIn("terminated", result)
        self.assertNotIn(task_id, self.manager._tasks)

    def test_spawn_parallel_subagents(self):
        """测试并行启动"""
        from tools.subagent_tools import spawn_parallel_subagents

        tasks = [
            {"type": "explore", "prompt": "Task 1"},
            {"type": "review", "prompt": "Task 2"},
        ]

        result = spawn_parallel_subagents(tasks)

        self.assertIn("Created 2 subagent tasks", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)