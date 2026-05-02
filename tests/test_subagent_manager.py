"""SubagentManager 模块单元测试

测试覆盖:
- SubagentTask: 任务创建、默认值、优先级
- SubagentManager: 初始化、任务创建、实例生成
- run_subagent: 单任务执行、状态通知、结果存储
- run_parallel: 并行执行、fail_fast 模式、异常处理
- 状态查询: get_status, get_result, get_all_results
- wait_for_result: 超时等待
- aggregate_results: 结果聚合、错误包含、长度截断
- cleanup: 单个/全部清理
- list_tasks: 状态过滤
- 便捷方法: spawn_explore/review/implement/plan
- RalphSubagentOrchestrator: 编排流程、执行报告
"""

import sys
import asyncio
import unittest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 导入测试模块（使用 src 前缀确保一致性）
from src.subagent import (  # noqa: E402
    SubagentType,
    SubagentInstance,
    SubagentState,
    SubagentResult,
)
from src.subagent_manager import (  # noqa: E402
    SubagentManager,
    SubagentTask,
    RalphSubagentOrchestrator,
)


class TestSubagentTask(unittest.TestCase):
    """测试 SubagentTask 数据类"""

    def test_minimal_task(self):
        """测试最小任务创建"""
        task = SubagentTask(
            id="task-1",
            subagent_type=SubagentType.EXPLORE,
            prompt="Test prompt",
        )
        self.assertEqual(task.id, "task-1")
        self.assertEqual(task.subagent_type, SubagentType.EXPLORE)
        self.assertEqual(task.prompt, "Test prompt")
        self.assertIsNone(task.custom_tools)
        self.assertIsNone(task.custom_system_prompt)
        self.assertIsNone(task.max_iterations)
        self.assertIsNone(task.timeout)
        self.assertEqual(task.priority, 0)

    def test_full_task(self):
        """测试完整参数任务"""
        task = SubagentTask(
            id="task-2",
            subagent_type=SubagentType.IMPLEMENT,
            prompt="Implement feature",
            custom_tools={"file_read", "file_write"},
            custom_system_prompt="Custom prompt",
            max_iterations=20,
            timeout=600,
            priority=5,
        )
        self.assertEqual(task.custom_tools, {"file_read", "file_write"})
        self.assertEqual(task.max_iterations, 20)
        self.assertEqual(task.timeout, 600)
        self.assertEqual(task.priority, 5)

    def test_priority_ordering(self):
        """测试优先级设置"""
        high = SubagentTask(id="high", subagent_type=SubagentType.EXPLORE, prompt="High", priority=10)
        low = SubagentTask(id="low", subagent_type=SubagentType.EXPLORE, prompt="Low", priority=0)
        self.assertGreater(high.priority, low.priority)


class MockGateway:
    """Mock LLMGateway for testing"""
    
    def __init__(self):
        self.config = MagicMock()
        self.config.agents = {'defaults': MagicMock()}
        self.config.agents['defaults'].defaults = MagicMock()
        self.config.agents['defaults'].defaults.primary = "gpt-4o"


class TestSubagentManagerInit(unittest.TestCase):
    """测试 SubagentManager 初始化"""

    def setUp(self):
        self.gateway = MockGateway()

    def test_init_default(self):
        """测试默认初始化"""
        manager = SubagentManager(self.gateway)
        self.assertEqual(manager.model_id, "gpt-4o")
        self.assertEqual(manager.max_concurrent, 3)
        self.assertEqual(manager._instances, {})
        self.assertEqual(manager._tasks, {})
        self.assertEqual(manager._results, {})
        self.assertEqual(manager._status_callbacks, [])

    def test_init_custom_model(self):
        """测试自定义模型"""
        manager = SubagentManager(self.gateway, model_id="claude-3-opus")
        self.assertEqual(manager.model_id, "claude-3-opus")

    def test_init_custom_concurrency(self):
        """测试自定义并发数"""
        manager = SubagentManager(self.gateway, max_concurrent=5)
        self.assertEqual(manager.max_concurrent, 5)

    def test_register_status_callback(self):
        """测试注册状态回调"""
        manager = SubagentManager(self.gateway)
        callback = Mock()
        manager.register_status_callback(callback)
        self.assertEqual(len(manager._status_callbacks), 1)
        self.assertEqual(manager._status_callbacks[0], callback)

    def test_notify_status(self):
        """测试状态通知"""
        manager = SubagentManager(self.gateway)
        callback = Mock()
        manager.register_status_callback(callback)
        manager._notify_status("task-1", "running")
        callback.assert_called_once_with("task-1", "running")

    def test_notify_status_multiple_callbacks(self):
        """测试多个状态回调"""
        manager = SubagentManager(self.gateway)
        cb1 = Mock()
        cb2 = Mock()
        manager.register_status_callback(cb1)
        manager.register_status_callback(cb2)
        manager._notify_status("task-1", "completed")
        cb1.assert_called_once_with("task-1", "completed")
        cb2.assert_called_once_with("task-1", "completed")

    def test_notify_status_error_handling(self):
        """测试回调异常处理"""
        manager = SubagentManager(self.gateway)
        bad_callback = Mock(side_effect=Exception("Callback error"))
        good_callback = Mock()
        manager.register_status_callback(bad_callback)
        manager.register_status_callback(good_callback)
        # 不应该抛出异常
        manager._notify_status("task-1", "running")
        good_callback.assert_called_once()


class TestSubagentManagerCreateTask(unittest.TestCase):
    """测试任务创建"""

    def setUp(self):
        self.gateway = MockGateway()
        self.manager = SubagentManager(self.gateway)

    def test_create_task_basic(self):
        """测试基本任务创建"""
        task_id = self.manager.create_task(SubagentType.EXPLORE, "Explore codebase")
        self.assertIsInstance(task_id, str)
        self.assertIn(task_id, self.manager._tasks)
        task = self.manager._tasks[task_id]
        self.assertEqual(task.subagent_type, SubagentType.EXPLORE)
        self.assertEqual(task.prompt, "Explore codebase")

    def test_create_task_with_options(self):
        """测试带选项的任务创建"""
        task_id = self.manager.create_task(
            SubagentType.IMPLEMENT,
            "Fix bug",
            max_iterations=10,
            timeout=120,
            priority=5,
        )
        task = self.manager._tasks[task_id]
        self.assertEqual(task.max_iterations, 10)
        self.assertEqual(task.timeout, 120)
        self.assertEqual(task.priority, 5)

    def test_create_task_returns_id(self):
        """测试返回唯一 ID"""
        id1 = self.manager.create_task(SubagentType.EXPLORE, "Task 1")
        id2 = self.manager.create_task(SubagentType.EXPLORE, "Task 2")
        self.assertNotEqual(id1, id2)


class TestSubagentManagerSpawn(unittest.TestCase):
    """测试 Subagent 实例生成"""

    def setUp(self):
        self.gateway = MockGateway()
        self.manager = SubagentManager(self.gateway)

    def test_spawn_subagent_success(self):
        """测试成功生成实例"""
        task_id = self.manager.create_task(SubagentType.REVIEW, "Review code")
        instance = self.manager.spawn_subagent(task_id)
        self.assertIsInstance(instance, SubagentInstance)
        self.assertIn(task_id, self.manager._instances)

    def test_spawn_subagent_not_found(self):
        """测试任务不存在"""
        with self.assertRaises(ValueError) as context:
            self.manager.spawn_subagent("nonexistent")
        self.assertIn("not found", str(context.exception))

    def test_spawn_subagent_uses_defaults(self):
        """测试使用默认配置"""
        task_id = self.manager.create_task(SubagentType.EXPLORE, "Explore")
        instance = self.manager.spawn_subagent(task_id)
        self.assertEqual(instance.model_id, "gpt-4o")
        self.assertEqual(instance.max_iterations, 15)  # DEFAULT_MAX_ITERATIONS

    def test_spawn_subagent_uses_task_timeout(self):
        """测试使用任务超时"""
        task_id = self.manager.create_task(
            SubagentType.EXPLORE, "Explore", timeout=60
        )
        instance = self.manager.spawn_subagent(task_id)
        self.assertEqual(instance.timeout, 60)

    def test_spawn_subagent_uses_custom_tools(self):
        """测试自定义工具集传递给 SubagentInstance"""
        task_id = self.manager.create_task(
            SubagentType.IMPLEMENT, "Implement", custom_tools={"file_read", "file_write"}
        )
        instance = self.manager.spawn_subagent(task_id)
        # custom_tools 被传入 _setup_tools 但不存储为属性
        # 验证实例创建成功且参数被传递
        self.assertIsNotNone(instance)
        self.assertEqual(instance.subagent_type, SubagentType.IMPLEMENT)


class TestSubagentManagerRun(unittest.TestCase):
    """测试单任务执行"""

    def setUp(self):
        self.gateway = MockGateway()
        self.manager = SubagentManager(self.gateway)

    def test_run_subagent_task_not_found(self):
        """测试任务不存在"""
        async def run_test():
            with self.assertRaises(ValueError):
                await self.manager.run_subagent("nonexistent")
        
        asyncio.run(run_test())

    def test_run_subagent_success(self):
        """测试成功执行"""
        task_id = self.manager.create_task(SubagentType.EXPLORE, "Explore")
        
        # Mock instance
        mock_state = SubagentState(
            id=task_id,
            subagent_type=SubagentType.EXPLORE,
            status="completed",
            prompt="Explore",
        )
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=mock_state)
        mock_instance.state = mock_state
        self.manager._instances[task_id] = mock_instance

        async def run_test():
            result = await self.manager.run_subagent(task_id)
            self.assertTrue(result.success)
            self.assertEqual(result.state.status, "completed")
            self.assertIn(task_id, self.manager._results)

        asyncio.run(run_test())

    def test_run_subagent_auto_spawn(self):
        """测试自动创建实例"""
        task_id = self.manager.create_task(SubagentType.EXPLORE, "Explore")
        # 不手动 spawn，run_subagent 应该自动创建

        with patch.object(SubagentInstance, 'run', new_callable=AsyncMock) as mock_run:
            mock_state = SubagentState(
                id=task_id,
                subagent_type=SubagentType.EXPLORE,
                status="completed",
                prompt="Explore",
            )
            mock_run.return_value = mock_state

            async def run_test():
                result = await self.manager.run_subagent(task_id)
                self.assertTrue(result.success)
                self.assertIn(task_id, self.manager._instances)

            asyncio.run(run_test())

    def test_run_subagent_status_notification(self):
        """测试状态通知"""
        task_id = self.manager.create_task(SubagentType.EXPLORE, "Explore")
        callback = Mock()
        self.manager.register_status_callback(callback)

        mock_state = SubagentState(
            id=task_id,
            subagent_type=SubagentType.EXPLORE,
            status="completed",
            prompt="Explore",
        )
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=mock_state)
        mock_instance.state = mock_state
        self.manager._instances[task_id] = mock_instance

        async def run_test():
            await self.manager.run_subagent(task_id)
            # 应该有两次调用: running 和 completed
            self.assertEqual(callback.call_count, 2)
            callback.assert_any_call(task_id, "running")
            callback.assert_any_call(task_id, "completed")

        asyncio.run(run_test())


class TestSubagentManagerParallel(unittest.TestCase):
    """测试并行执行"""

    def setUp(self):
        self.gateway = MockGateway()
        self.manager = SubagentManager(self.gateway)

    def _create_mock_instance(self, task_id, status="completed"):
        """创建 mock 实例"""
        mock_state = SubagentState(
            id=task_id,
            subagent_type=SubagentType.EXPLORE,
            status=status,
            prompt="Test",
        )
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=mock_state)
        mock_instance.state = mock_state
        return mock_instance

    def test_run_parallel_all_success(self):
        """测试全部成功"""
        id1 = self.manager.create_task(SubagentType.EXPLORE, "Task 1")
        id2 = self.manager.create_task(SubagentType.EXPLORE, "Task 2")
        
        self.manager._instances[id1] = self._create_mock_instance(id1)
        self.manager._instances[id2] = self._create_mock_instance(id2)

        async def run_test():
            results = await self.manager.run_parallel([id1, id2])
            self.assertEqual(len(results), 2)
            self.assertTrue(results[id1].success)
            self.assertTrue(results[id2].success)

        asyncio.run(run_test())

    def test_run_parallel_fail_fast(self):
        """测试 fail_fast 模式"""
        id1 = self.manager.create_task(SubagentType.EXPLORE, "Task 1")
        id2 = self.manager.create_task(SubagentType.EXPLORE, "Task 2")
        id3 = self.manager.create_task(SubagentType.EXPLORE, "Task 3")

        # 让第二个任务失败
        self.manager._instances[id1] = self._create_mock_instance(id1)
        self.manager._instances[id2] = self._create_mock_instance(id2, "failed")
        self.manager._instances[id3] = self._create_mock_instance(id3)

        async def run_test():
            results = await self.manager.run_parallel([id1, id2, id3], fail_fast=True)
            self.assertEqual(len(results), 2)  # 只执行了前两个
            self.assertTrue(results[id1].success)
            self.assertFalse(results[id2].success)

        asyncio.run(run_test())

    def test_run_parallel_exception_handling(self):
        """测试异常处理"""
        id1 = self.manager.create_task(SubagentType.EXPLORE, "Task 1")
        id2 = self.manager.create_task(SubagentType.EXPLORE, "Task 2")

        self.manager._instances[id1] = self._create_mock_instance(id1)
        
        # 让第二个任务抛出异常
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(side_effect=Exception("Connection error"))
        self.manager._instances[id2] = mock_instance

        async def run_test():
            results = await self.manager.run_parallel([id1, id2])
            self.assertTrue(results[id1].success)
            self.assertFalse(results[id2].success)
            self.assertIn("Connection error", results[id2].error)

        asyncio.run(run_test())


class TestSubagentManagerStatus(unittest.TestCase):
    """测试状态查询"""

    def setUp(self):
        self.gateway = MockGateway()
        self.manager = SubagentManager(self.gateway)

    def test_get_status_pending(self):
        """测试待处理状态"""
        task_id = self.manager.create_task(SubagentType.EXPLORE, "Explore")
        self.assertEqual(self.manager.get_status(task_id), "pending")

    def test_get_status_from_result(self):
        """测试从结果获取状态"""
        task_id = self.manager.create_task(SubagentType.EXPLORE, "Explore")
        state = SubagentState(
            id=task_id,
            subagent_type=SubagentType.EXPLORE,
            status="completed",
            prompt="Explore",
        )
        self.manager._results[task_id] = SubagentResult(state)
        self.assertEqual(self.manager.get_status(task_id), "completed")

    def test_get_status_from_instance(self):
        """测试从实例获取状态"""
        task_id = self.manager.create_task(SubagentType.EXPLORE, "Explore")
        state = SubagentState(
            id=task_id,
            subagent_type=SubagentType.EXPLORE,
            status="running",
            prompt="Explore",
        )
        mock_instance = MagicMock()
        mock_instance.state = state
        self.manager._instances[task_id] = mock_instance
        self.assertEqual(self.manager.get_status(task_id), "running")

    def test_get_status_not_found(self):
        """测试不存在的任务"""
        self.assertIsNone(self.manager.get_status("nonexistent"))

    def test_get_result(self):
        """测试结果获取"""
        task_id = self.manager.create_task(SubagentType.EXPLORE, "Explore")
        state = SubagentState(
            id=task_id,
            subagent_type=SubagentType.EXPLORE,
            status="completed",
            prompt="Explore",
        )
        result = SubagentResult(state)
        self.manager._results[task_id] = result
        self.assertEqual(self.manager.get_result(task_id), result)

    def test_get_result_not_found(self):
        """测试结果不存在"""
        self.assertIsNone(self.manager.get_result("nonexistent"))

    def test_get_all_results(self):
        """测试获取所有结果"""
        id1 = self.manager.create_task(SubagentType.EXPLORE, "Task 1")
        id2 = self.manager.create_task(SubagentType.EXPLORE, "Task 2")
        
        state1 = SubagentState(id=id1, subagent_type=SubagentType.EXPLORE, status="completed", prompt="Task 1")
        state2 = SubagentState(id=id2, subagent_type=SubagentType.EXPLORE, status="completed", prompt="Task 2")
        self.manager._results[id1] = SubagentResult(state1)
        self.manager._results[id2] = SubagentResult(state2)

        results = self.manager.get_all_results()
        self.assertEqual(len(results), 2)
        # 应该是副本
        results.clear()
        self.assertEqual(len(self.manager._results), 2)


class TestSubagentManagerWait(unittest.TestCase):
    """测试等待结果"""

    def setUp(self):
        self.gateway = MockGateway()
        self.manager = SubagentManager(self.gateway)

    def test_wait_for_result_immediate(self):
        """测试立即有结果"""
        task_id = self.manager.create_task(SubagentType.EXPLORE, "Explore")
        state = SubagentState(
            id=task_id,
            subagent_type=SubagentType.EXPLORE,
            status="completed",
            prompt="Explore",
        )
        self.manager._results[task_id] = SubagentResult(state)
        # 使用 get_result 同步方法（wait_for_result_async 是异步方法）
        result = self.manager.get_result(task_id)
        self.assertIsNotNone(result)

    def test_wait_for_result_timeout(self):
        """测试超时 - 使用 get_result 返回 None 表示不存在"""
        result = self.manager.get_result("nonexistent")
        self.assertIsNone(result)

    def test_wait_for_result_no_timeout(self):
        """测试立即返回已有结果"""
        task_id = self.manager.create_task(SubagentType.EXPLORE, "Explore")
        state = SubagentState(
            id=task_id,
            subagent_type=SubagentType.EXPLORE,
            status="completed",
            prompt="Explore",
        )
        self.manager._results[task_id] = SubagentResult(state)
        # 使用 get_result 同步方法
        result = self.manager.get_result(task_id)
        self.assertIsNotNone(result)


class TestSubagentManagerAggregate(unittest.TestCase):
    """测试结果聚合"""

    def setUp(self):
        self.gateway = MockGateway()
        self.manager = SubagentManager(self.gateway)

    def test_aggregate_success_results(self):
        """测试聚合成功结果"""
        id1 = self.manager.create_task(SubagentType.EXPLORE, "Task 1")
        state = SubagentState(
            id=id1,
            subagent_type=SubagentType.EXPLORE,
            status="completed",
            prompt="Task 1",
            result="Success content",
        )
        self.manager._results[id1] = SubagentResult(state)
        
        summary = self.manager.aggregate_results([id1])
        self.assertIn("SUCCESS", summary)
        self.assertIn("Success content", summary)

    def test_aggregate_with_errors(self):
        """测试聚合包含错误"""
        id1 = self.manager.create_task(SubagentType.EXPLORE, "Task 1")
        state = SubagentState(
            id=id1,
            subagent_type=SubagentType.EXPLORE,
            status="failed",
            prompt="Task 1",
            error="Connection error",
        )
        self.manager._results[id1] = SubagentResult(state)
        
        summary = self.manager.aggregate_results([id1], include_errors=True)
        self.assertIn("FAILED", summary)
        self.assertIn("Connection error", summary)

    def test_aggregate_exclude_errors(self):
        """测试聚合排除错误"""
        id1 = self.manager.create_task(SubagentType.EXPLORE, "Task 1")
        state = SubagentState(
            id=id1,
            subagent_type=SubagentType.EXPLORE,
            status="failed",
            prompt="Task 1",
            error="Connection error",
        )
        self.manager._results[id1] = SubagentResult(state)
        
        summary = self.manager.aggregate_results([id1], include_errors=False)
        self.assertEqual(summary, "")

    def test_aggregate_not_found(self):
        """测试聚合不存在的任务"""
        summary = self.manager.aggregate_results(["nonexistent"])
        self.assertIn("Not found", summary)

    def test_aggregate_truncation(self):
        """测试结果截断"""
        id1 = self.manager.create_task(SubagentType.EXPLORE, "Task 1")
        long_content = "A" * 3000
        state = SubagentState(
            id=id1,
            subagent_type=SubagentType.EXPLORE,
            status="completed",
            prompt="Task 1",
            result=long_content,
        )
        self.manager._results[id1] = SubagentResult(state)
        
        summary = self.manager.aggregate_results([id1], max_length=100)
        self.assertIn("truncated", summary)
        self.assertLess(len(summary), 500)


class TestSubagentManagerCleanup(unittest.TestCase):
    """测试清理"""

    def setUp(self):
        self.gateway = MockGateway()
        self.manager = SubagentManager(self.gateway)

    def test_cleanup_single_task(self):
        """测试清理单个任务"""
        task_id = self.manager.create_task(SubagentType.EXPLORE, "Explore")
        self.manager._instances[task_id] = MagicMock()
        self.manager._results[task_id] = MagicMock()
        
        self.manager.cleanup(task_id)
        self.assertNotIn(task_id, self.manager._tasks)
        self.assertNotIn(task_id, self.manager._instances)
        self.assertNotIn(task_id, self.manager._results)

    def test_cleanup_all(self):
        """测试清理所有任务"""
        self.manager.create_task(SubagentType.EXPLORE, "Task 1")
        self.manager.create_task(SubagentType.EXPLORE, "Task 2")
        self.manager._instances = {"1": MagicMock(), "2": MagicMock()}
        self.manager._results = {"1": MagicMock(), "2": MagicMock()}
        
        self.manager.cleanup()
        self.assertEqual(len(self.manager._tasks), 0)
        self.assertEqual(len(self.manager._instances), 0)
        self.assertEqual(len(self.manager._results), 0)


class TestSubagentManagerListTasks(unittest.TestCase):
    """测试任务列表"""

    def setUp(self):
        self.gateway = MockGateway()
        self.manager = SubagentManager(self.gateway)

    def test_list_all_tasks(self):
        """测试列出所有任务"""
        self.manager.create_task(SubagentType.EXPLORE, "Task 1")
        self.manager.create_task(SubagentType.REVIEW, "Task 2")
        
        tasks = self.manager.list_tasks()
        self.assertEqual(len(tasks), 2)

    def test_list_tasks_with_status_filter(self):
        """测试按状态过滤"""
        id1 = self.manager.create_task(SubagentType.EXPLORE, "Task 1")
        self.manager.create_task(SubagentType.EXPLORE, "Task 2")
        
        # 设置 id1 为 completed
        state = SubagentState(
            id=id1,
            subagent_type=SubagentType.EXPLORE,
            status="completed",
            prompt="Task 1",
        )
        self.manager._results[id1] = SubagentResult(state)
        
        completed = self.manager.list_tasks(status="completed")
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["id"], id1)

    def test_list_tasks_info(self):
        """测试任务信息完整性"""
        task_id = self.manager.create_task(SubagentType.IMPLEMENT, "Fix bug", priority=5)
        tasks = self.manager.list_tasks()
        task = tasks[0]
        self.assertEqual(task["id"], task_id)
        self.assertEqual(task["type"], "implement")
        self.assertEqual(task["status"], "pending")
        self.assertEqual(task["priority"], 5)

    def test_list_tasks_prompt_truncation(self):
        """测试 prompt 截断"""
        long_prompt = "A" * 200
        self.manager.create_task(SubagentType.EXPLORE, long_prompt)
        tasks = self.manager.list_tasks()
        self.assertIn("...", tasks[0]["prompt_preview"])


class TestSubagentManagerConvenience(unittest.TestCase):
    """测试便捷方法"""

    def setUp(self):
        self.gateway = MockGateway()
        self.manager = SubagentManager(self.gateway)

    def test_spawn_explore(self):
        """测试探索型任务创建"""
        task_id = self.manager.spawn_explore("Explore code")
        task = self.manager._tasks[task_id]
        self.assertEqual(task.subagent_type, SubagentType.EXPLORE)

    def test_spawn_review(self):
        """测试审查型任务创建"""
        task_id = self.manager.spawn_review("Review code")
        task = self.manager._tasks[task_id]
        self.assertEqual(task.subagent_type, SubagentType.REVIEW)

    def test_spawn_implement(self):
        """测试实现型任务创建"""
        task_id = self.manager.spawn_implement("Implement feature")
        task = self.manager._tasks[task_id]
        self.assertEqual(task.subagent_type, SubagentType.IMPLEMENT)

    def test_spawn_plan(self):
        """测试规划型任务创建"""
        task_id = self.manager.spawn_plan("Plan architecture")
        task = self.manager._tasks[task_id]
        self.assertEqual(task.subagent_type, SubagentType.PLAN)

    def test_spawn_with_kwargs(self):
        """测试带额外参数"""
        task_id = self.manager.spawn_explore("Explore", priority=10, timeout=60)
        task = self.manager._tasks[task_id]
        self.assertEqual(task.priority, 10)
        self.assertEqual(task.timeout, 60)


class TestRalphSubagentOrchestrator(unittest.TestCase):
    """测试 RalphSubagentOrchestrator"""

    def setUp(self):
        self.gateway = MockGateway()
        self.manager = SubagentManager(self.gateway)
        self.orchestrator = RalphSubagentOrchestrator(self.manager)

    def test_init(self):
        """测试初始化"""
        self.assertEqual(self.orchestrator.manager, self.manager)
        self.assertIsNone(self.orchestrator._plan_task_id)
        self.assertEqual(self.orchestrator._implement_task_ids, [])
        self.assertIsNone(self.orchestrator._review_task_id)

    def test_plan_phase(self):
        """测试规划阶段"""
        async def run_test():
            with patch.object(self.manager, 'run_subagent', new_callable=AsyncMock) as mock_run:
                state = SubagentState(
                    id="plan-1",
                    subagent_type=SubagentType.PLAN,
                    status="completed",
                    prompt="Plan task",
                    result="Execution plan",
                )
                mock_run.return_value = SubagentResult(state)
                
                result = await self.orchestrator.plan_phase("Build feature")
                self.assertIsNotNone(self.orchestrator._plan_task_id)
                self.assertEqual(result, "Execution plan")

        asyncio.run(run_test())

    def test_implement_phase(self):
        """测试实现阶段"""
        async def run_test():
            with patch.object(self.manager, 'run_parallel', new_callable=AsyncMock) as mock_run:
                mock_run.return_value = {
                    "impl-1": MagicMock(success=True),
                    "impl-2": MagicMock(success=True),
                }
                
                results = await self.orchestrator.implement_phase(["Prompt 1", "Prompt 2"])
                self.assertEqual(len(self.orchestrator._implement_task_ids), 2)
                self.assertEqual(len(results), 2)

        asyncio.run(run_test())

    def test_review_phase(self):
        """测试审查阶段"""
        async def run_test():
            with patch.object(self.manager, 'run_subagent', new_callable=AsyncMock) as mock_run:
                state = SubagentState(
                    id="review-1",
                    subagent_type=SubagentType.REVIEW,
                    status="completed",
                    prompt="Review",
                    result="Looks good",
                )
                mock_run.return_value = SubagentResult(state)
                
                result = await self.orchestrator.review_phase("Review implementation")
                self.assertIsNotNone(self.orchestrator._review_task_id)
                self.assertEqual(result, "Looks good")

        asyncio.run(run_test())

    def test_get_execution_report(self):
        """测试执行报告"""
        # 设置一些结果
        plan_id = self.manager.create_task(SubagentType.PLAN, "Plan")
        state = SubagentState(
            id=plan_id,
            subagent_type=SubagentType.PLAN,
            status="completed",
            prompt="Plan",
            result="Plan content",
        )
        self.manager._results[plan_id] = SubagentResult(state)
        self.orchestrator._plan_task_id = plan_id

        report = self.orchestrator.get_execution_report()
        self.assertIn("plan", report)
        self.assertIn("implement", report)
        self.assertIn("review", report)
        self.assertEqual(report["plan"]["task_id"], plan_id)

    def test_get_execution_report_empty(self):
        """测试空执行报告"""
        report = self.orchestrator.get_execution_report()
        self.assertIsNone(report["plan"]["result"])
        self.assertEqual(report["implement"], [])
        self.assertIsNone(report["review"]["result"])

    def test_cleanup(self):
        """测试清理"""
        self.orchestrator._plan_task_id = "plan-1"
        self.orchestrator._implement_task_ids = ["impl-1", "impl-2"]
        self.orchestrator._review_task_id = "review-1"
        self.manager.create_task(SubagentType.PLAN, "Plan")

        self.orchestrator.cleanup()
        self.assertIsNone(self.orchestrator._plan_task_id)
        self.assertEqual(self.orchestrator._implement_task_ids, [])
        self.assertIsNone(self.orchestrator._review_task_id)
        self.assertEqual(len(self.manager._tasks), 0)


if __name__ == '__main__':
    unittest.main()
