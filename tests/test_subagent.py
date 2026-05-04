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
        from src.subagent import DEFAULT_TIMEOUTS

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
        from src.tools.subagent_tools import init_subagent_manager

        self.gateway_mock = Mock()
        self.gateway_mock.config = Mock()
        self.gateway_mock.config.agents = {'defaults': Mock()}
        self.gateway_mock.config.agents['defaults'].defaults = Mock()
        self.gateway_mock.config.agents['defaults'].defaults.primary = "test/test-model"

        self.manager = SubagentManager(gateway=self.gateway_mock)
        init_subagent_manager(self.manager)

    def test_spawn_subagent(self):
        """测试 spawn_subagent 工具"""
        from src.tools.subagent_tools import spawn_subagent

        result = spawn_subagent(
            type="explore",
            prompt="Find all Python files",
        )

        self.assertIn("Subagent task created", result)
        self.assertIn("explore", result)

    def test_spawn_subagent_invalid_type(self):
        """测试无效类型"""
        from src.tools.subagent_tools import spawn_subagent

        result = spawn_subagent(
            type="invalid_type",
            prompt="Test",
        )

        self.assertIn("Error", result)
        self.assertIn("Unknown subagent type", result)

    def test_list_subagents(self):
        """测试列出子代理"""
        from src.tools.subagent_tools import list_subagents, spawn_subagent

        spawn_subagent("explore", "Test 1")
        spawn_subagent("review", "Test 2")

        result = list_subagents()

        self.assertIn("Subagent Tasks", result)
        self.assertIn("explore", result)
        self.assertIn("review", result)

    def test_list_subagents_empty(self):
        """测试空列表"""
        from src.tools.subagent_tools import list_subagents

        self.manager.cleanup()
        result = list_subagents()

        self.assertIn("No subagent tasks found", result)

    def test_get_subagent_status(self):
        """测试获取状态"""
        from src.tools.subagent_tools import get_subagent_status, spawn_subagent

        task_id_result = spawn_subagent("explore", "Test")
        # 提取 task_id
        task_id = task_id_result.split("\n")[0].split(": ")[1]

        result = get_subagent_status(task_id)

        self.assertIn(task_id, result)
        self.assertIn("pending", result)

    def test_kill_subagent(self):
        """测试终止子代理"""
        from src.tools.subagent_tools import kill_subagent, spawn_subagent

        task_id_result = spawn_subagent("explore", "Test")
        task_id = task_id_result.split("\n")[0].split(": ")[1]

        result = kill_subagent(task_id)

        self.assertIn("terminated", result)
        self.assertNotIn(task_id, self.manager._tasks)

    def test_spawn_parallel_subagents(self):
        """测试并行启动"""
        from src.tools.subagent_tools import spawn_parallel_subagents

        tasks = [
            {"type": "explore", "prompt": "Task 1"},
            {"type": "review", "prompt": "Task 2"},
        ]

        result = spawn_parallel_subagents(tasks)

        self.assertIn("Created 2 subagent tasks", result)


class TestTypeSafetyConversion(unittest.TestCase):
    """测试类型安全转换功能

    测试 LLM 返回字符串类型数值参数时的处理：
    - 字符串 timeout -> 整数 timeout
    - 无效字符串 -> 默认值
    - 负数 -> 默认值
    """

    def setUp(self):
        """测试前设置"""
        from src.tools.subagent_tools import init_subagent_manager, _safe_int_convert

        self.gateway_mock = Mock()
        self.gateway_mock.config = Mock()
        self.gateway_mock.config.agents = {'defaults': Mock()}
        self.gateway_mock.config.agents['defaults'].defaults = Mock()
        self.gateway_mock.config.agents['defaults'].defaults.primary = "test/test-model"

        self.manager = SubagentManager(gateway=self.gateway_mock)
        init_subagent_manager(self.manager)
        self._safe_int_convert = _safe_int_convert

    def test_safe_int_convert_valid_string(self):
        """测试有效字符串转换为整数"""
        result = self._safe_int_convert("300", default=100)
        self.assertEqual(result, 300)

        result = self._safe_int_convert("60", default=30)
        self.assertEqual(result, 60)

    def test_safe_int_convert_valid_int(self):
        """测试整数直接返回"""
        result = self._safe_int_convert(300, default=100)
        self.assertEqual(result, 300)

        result = self._safe_int_convert(60, default=30)
        self.assertEqual(result, 60)

    def test_safe_int_convert_invalid_string(self):
        """测试无效字符串返回默认值"""
        result = self._safe_int_convert("abc", default=100)
        self.assertEqual(result, 100)

        result = self._safe_int_convert("not_a_number", default=300)
        self.assertEqual(result, 300)

    def test_safe_int_convert_none(self):
        """测试 None 返回默认值"""
        result = self._safe_int_convert(None, default=100)
        self.assertEqual(result, 100)

    def test_safe_int_convert_negative(self):
        """测试负数返回默认值（min_val=1）"""
        result = self._safe_int_convert("-5", default=100)
        self.assertEqual(result, 100)

        result = self._safe_int_convert(-10, default=300)
        self.assertEqual(result, 300)

    def test_safe_int_convert_zero(self):
        """测试零返回默认值（min_val=1）"""
        result = self._safe_int_convert("0", default=100, min_val=1)
        self.assertEqual(result, 100)

        result = self._safe_int_convert(0, default=300, min_val=1)
        self.assertEqual(result, 300)

    def test_safe_int_convert_zero_allowed(self):
        """测试零允许（min_val=0）"""
        result = self._safe_int_convert("0", default=100, min_val=0)
        self.assertEqual(result, 0)

        result = self._safe_int_convert(0, default=300, min_val=0)
        self.assertEqual(result, 0)

    def test_spawn_subagent_with_string_timeout(self):
        """测试 spawn_subagent 接收字符串 timeout"""
        from src.tools.subagent_tools import spawn_subagent

        result = spawn_subagent(
            type="explore",
            prompt="Test prompt",
            timeout="60",  # 字符串 timeout
        )

        self.assertIn("task created", result.lower())
        self.assertNotIn("Error", result)

        # 验证任务被正确创建且 timeout 为整数
        # 提取 task_id
        task_id = result.split("\n")[0].split(": ")[1]
        task = self.manager._tasks.get(task_id)
        if task:
            self.assertIsInstance(task.timeout, int)
            self.assertEqual(task.timeout, 60)

    def test_spawn_subagent_with_invalid_timeout(self):
        """测试 spawn_subagent 接收无效 timeout"""
        from src.tools.subagent_tools import spawn_subagent

        result = spawn_subagent(
            type="explore",
            prompt="Test prompt",
            timeout="invalid",  # 无效字符串
        )

        # 应使用默认值，不报错
        self.assertIn("task created", result.lower())
        self.assertNotIn("'<=', not supported", result)

    def test_spawn_subagent_with_negative_timeout(self):
        """测试 spawn_subagent 接收负数 timeout"""
        from src.tools.subagent_tools import spawn_subagent

        result = spawn_subagent(
            type="explore",
            prompt="Test prompt",
            timeout="-100",  # 负数
        )

        # 应使用默认值
        self.assertIn("task created", result.lower())

    def test_spawn_parallel_subagents_with_string_timeout(self):
        """测试 spawn_parallel_subagents 接收字符串 timeout"""
        from src.tools.subagent_tools import spawn_parallel_subagents

        tasks = [
            {"type": "explore", "prompt": "Task 1", "timeout": "120"},
            {"type": "review", "prompt": "Task 2", "timeout": "300"},
        ]

        result = spawn_parallel_subagents(tasks)

        self.assertIn("Created 2 subagent tasks", result)
        self.assertNotIn("Error", result)

    def test_spawn_parallel_subagents_with_invalid_timeout(self):
        """测试 spawn_parallel_subagents 接收无效 timeout"""
        from src.tools.subagent_tools import spawn_parallel_subagents

        tasks = [
            {"type": "explore", "prompt": "Task 1", "timeout": "invalid"},
            {"type": "review", "prompt": "Task 2", "timeout": "-50"},
        ]

        result = spawn_parallel_subagents(tasks)

        # 应使用默认值
        self.assertIn("Created 2 subagent tasks", result)

    def test_aggregate_subagent_results_with_string_max_length(self):
        """测试 aggregate_subagent_results 接收字符串 max_length"""
        from src.tools.subagent_tools import aggregate_subagent_results

        # 创建一些任务和结果
        task_id = self.manager.create_task(SubagentType.EXPLORE, "Test")
        state = SubagentState(
            id=task_id,
            subagent_type=SubagentType.EXPLORE,
            status="completed",
            prompt="Test",
            result="Result content",
        )
        self.manager._results[task_id] = SubagentResult(state)

        result = aggregate_subagent_results(
            task_ids=[task_id],
            max_length="100",  # 字符串 max_length
        )

        self.assertIn("SUCCESS", result)
        self.assertNotIn("Error", result)

    def test_aggregate_subagent_results_with_invalid_max_length(self):
        """测试 aggregate_subagent_results 接收无效 max_length"""
        from src.tools.subagent_tools import aggregate_subagent_results

        task_id = self.manager.create_task(SubagentType.EXPLORE, "Test")
        state = SubagentState(
            id=task_id,
            subagent_type=SubagentType.EXPLORE,
            status="completed",
            prompt="Test",
            result="Result",
        )
        self.manager._results[task_id] = SubagentResult(state)

        result = aggregate_subagent_results(
            task_ids=[task_id],
            max_length="invalid",  # 无效字符串
        )

        # 应使用默认值
        self.assertIn("SUCCESS", result)


class TestSubagentTaskTypeSafety(unittest.TestCase):
    """测试 SubagentTask 的类型安全（__post_init__）"""

    def test_subagent_task_string_timeout_conversion(self):
        """测试 SubagentTask 自动转换字符串 timeout"""
        from src.subagent_manager import SubagentTask

        task = SubagentTask(
            id="test-1",
            subagent_type=SubagentType.EXPLORE,
            prompt="Test",
            timeout="300",  # 字符串 timeout
        )

        # __post_init__ 应自动转换为整数
        self.assertIsInstance(task.timeout, int)
        self.assertEqual(task.timeout, 300)

    def test_subagent_task_invalid_timeout_conversion(self):
        """测试 SubagentTask 处理无效 timeout"""
        from src.subagent_manager import SubagentTask

        task = SubagentTask(
            id="test-2",
            subagent_type=SubagentType.EXPLORE,
            prompt="Test",
            timeout="invalid",  # 无效字符串
        )

        # __post_init__ 应返回 None（default=None）
        self.assertIsNone(task.timeout)

    def test_subagent_task_negative_timeout_conversion(self):
        """测试 SubagentTask 处理负数 timeout"""
        from src.subagent_manager import SubagentTask

        task = SubagentTask(
            id="test-3",
            subagent_type=SubagentType.EXPLORE,
            prompt="Test",
            timeout="-100",  # 负数
        )

        # __post_init__ 应返回 None（min_val=1）
        self.assertIsNone(task.timeout)

    def test_subagent_task_string_max_iterations_conversion(self):
        """测试 SubagentTask 自动转换字符串 max_iterations"""
        from src.subagent_manager import SubagentTask

        task = SubagentTask(
            id="test-4",
            subagent_type=SubagentType.EXPLORE,
            prompt="Test",
            max_iterations="20",  # 字符串
        )

        self.assertIsInstance(task.max_iterations, int)
        self.assertEqual(task.max_iterations, 20)

    def test_subagent_task_string_priority_conversion(self):
        """测试 SubagentTask 自动转换字符串 priority"""
        from src.subagent_manager import SubagentTask

        task = SubagentTask(
            id="test-5",
            subagent_type=SubagentType.EXPLORE,
            prompt="Test",
            priority="10",  # 字符串
        )

        self.assertIsInstance(task.priority, int)
        self.assertEqual(task.priority, 10)

    def test_subagent_task_negative_priority_conversion(self):
        """测试 SubagentTask 处理负数 priority"""
        from src.subagent_manager import SubagentTask

        task = SubagentTask(
            id="test-6",
            subagent_type=SubagentType.EXPLORE,
            prompt="Test",
            priority="-5",  # 负数（min_val=0 允许）
        )

        # min_val=0 允许负数... 不，min_val=0 检查的是 < min_val
        # -5 < 0，所以返回默认值 0
        self.assertEqual(task.priority, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)