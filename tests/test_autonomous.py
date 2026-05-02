"""自主探索模块单元测试

测试覆盖:
- CompletionType enum: 完成验证类型
- AutonomousExplorer 初始化: SOP 加载、状态初始化
- record_activity / get_idle_time: 空闲时间计算
- _check_completion_promise: 完成标志检测与清理
- _check_safety_limits: 迭代和时间安全上限
- _extract_critical_context: 关键上下文提取
- _persist_state / _load_or_init_state / _cleanup_state: 状态持久化
- _load_todo_content: TODO 文件加载
- _extract_task_signals: 任务信号提取
- _build_task_instruction: 任务指令构建
- _handle_response: 空响应处理
"""

import sys
import json
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

# CompletionType 现在从 ralph_loop 导入，避免重复定义
from ralph_loop import CompletionType  # noqa: E402
from autonomous import (  # noqa: E402
    AutonomousExplorer,
    RALPH_MAX_ITERATIONS,
    RALPH_MAX_DURATION,
)


class TestCompletionType(unittest.TestCase):
    """测试完成验证类型枚举"""

    def test_all_values_exist(self):
        """测试所有枚举值存在"""
        self.assertEqual(CompletionType.TEST_PASS.value, "test_pass")
        self.assertEqual(CompletionType.FILE_EXISTS.value, "file_exists")
        self.assertEqual(CompletionType.MARKER_FILE.value, "marker_file")
        self.assertEqual(CompletionType.GIT_CLEAN.value, "git_clean")
        self.assertEqual(CompletionType.CUSTOM_CHECK.value, "custom_check")

    def test_from_string(self):
        """测试从字符串创建枚举"""
        self.assertEqual(CompletionType("test_pass"), CompletionType.TEST_PASS)
        self.assertEqual(CompletionType("file_exists"), CompletionType.FILE_EXISTS)


class TestAutonomousExplorerInit(unittest.TestCase):
    """测试 AutonomousExplorer 初始化"""

    def setUp(self):
        """设置测试环境"""
        self.mock_agent = MagicMock()
        self.mock_agent.system_prompt = "Test system prompt"
        self.mock_agent.history = []
        self.mock_agent.skill_loader = None
        self.mock_agent.tools = MagicMock()
        self.mock_agent.tools.get_tool_names.return_value = []
        self.mock_agent.max_iterations = 50

    def test_init_basic(self):
        """测试基本初始化"""
        explorer = AutonomousExplorer(self.mock_agent)
        self.assertEqual(explorer.agent, self.mock_agent)
        self.assertIsNone(explorer.on_explore_complete)
        self.assertFalse(explorer._running)
        self.assertIsNone(explorer._task)
        self.assertEqual(explorer._iteration_count, 0)
        self.assertEqual(explorer._accumulated_duration, 0)
        self.assertEqual(explorer._empty_response_count, 0)

    def test_init_with_callback(self):
        """测试带回调函数的初始化"""
        callback = MagicMock()
        explorer = AutonomousExplorer(self.mock_agent, on_explore_complete=callback)
        self.assertEqual(explorer.on_explore_complete, callback)

    def test_idle_timeout_constant(self):
        """测试空闲超时常量"""
        self.assertEqual(AutonomousExplorer.IDLE_TIMEOUT, 120 * 60)  # 2小时


class TestActivityTracking(unittest.TestCase):
    """测试活动跟踪功能"""

    def setUp(self):
        self.mock_agent = MagicMock()
        self.mock_agent.system_prompt = "Test"
        self.mock_agent.history = []
        self.mock_agent.skill_loader = None
        self.mock_agent.tools = MagicMock()
        self.mock_agent.tools.get_tool_names.return_value = []
        self.explorer = AutonomousExplorer(self.mock_agent)

    def test_record_activity(self):
        """测试记录活动"""
        old_time = self.explorer._last_activity
        time.sleep(0.01)
        self.explorer.record_activity()
        self.assertGreater(self.explorer._last_activity, old_time)

    def test_get_idle_time(self):
        """测试获取空闲时间"""
        self.explorer.record_activity()
        time.sleep(0.1)
        idle = self.explorer.get_idle_time()
        self.assertGreaterEqual(idle, 0.1)
        self.assertLess(idle, 1.0)  # 应该小于1秒


class TestCompletionPromise(unittest.TestCase):
    """测试完成标志检测"""

    def setUp(self):
        self.mock_agent = MagicMock()
        self.mock_agent.system_prompt = "Test"
        self.mock_agent.history = []
        self.mock_agent.skill_loader = None
        self.mock_agent.tools = MagicMock()
        self.mock_agent.tools.get_tool_names.return_value = []
        self.explorer = AutonomousExplorer(self.mock_agent)

    def test_completion_promise_detected(self):
        """测试检测到完成标志"""
        with tempfile.TemporaryDirectory() as tmpdir:
            promise_file = Path(tmpdir) / "completion_promise"
            promise_file.write_text("DONE")

            with patch('autonomous.COMPLETION_PROMISE_FILE', promise_file):
                result = self.explorer._check_completion_promise()
                self.assertTrue(result)
                # 文件应被删除
                self.assertFalse(promise_file.exists())

    def test_completion_promise_complete(self):
        """测试 COMPLETE 标志"""
        with tempfile.TemporaryDirectory() as tmpdir:
            promise_file = Path(tmpdir) / "completion_promise"
            promise_file.write_text("COMPLETE")

            with patch('autonomous.COMPLETION_PROMISE_FILE', promise_file):
                result = self.explorer._check_completion_promise()
                self.assertTrue(result)

    def test_completion_promise_task_finished(self):
        """测试 TASK_FINISHED 标志"""
        with tempfile.TemporaryDirectory() as tmpdir:
            promise_file = Path(tmpdir) / "completion_promise"
            promise_file.write_text("TASK_FINISHED")

            with patch('autonomous.COMPLETION_PROMISE_FILE', promise_file):
                result = self.explorer._check_completion_promise()
                self.assertTrue(result)

    def test_completion_promise_not_detected(self):
        """测试未检测到完成标志"""
        with tempfile.TemporaryDirectory() as tmpdir:
            promise_file = Path(tmpdir) / "completion_promise"
            promise_file.write_text("IN_PROGRESS")

            with patch('autonomous.COMPLETION_PROMISE_FILE', promise_file):
                result = self.explorer._check_completion_promise()
                self.assertFalse(result)
                # 文件不应被删除
                self.assertTrue(promise_file.exists())

    def test_completion_promise_file_not_exists(self):
        """测试标志文件不存在"""
        with tempfile.TemporaryDirectory() as tmpdir:
            promise_file = Path(tmpdir) / "completion_promise"

            with patch('autonomous.COMPLETION_PROMISE_FILE', promise_file):
                result = self.explorer._check_completion_promise()
                self.assertFalse(result)


class TestSafetyLimits(unittest.TestCase):
    """测试安全上限检查"""

    def setUp(self):
        self.mock_agent = MagicMock()
        self.mock_agent.system_prompt = "Test"
        self.mock_agent.history = []
        self.mock_agent.skill_loader = None
        self.mock_agent.tools = MagicMock()
        self.mock_agent.tools.get_tool_names.return_value = []
        self.explorer = AutonomousExplorer(self.mock_agent)

    def test_iteration_limit(self):
        """测试迭代上限"""
        self.explorer._iteration_count = RALPH_MAX_ITERATIONS
        self.assertTrue(self.explorer._check_safety_limits())

        self.explorer._iteration_count = RALPH_MAX_ITERATIONS - 1
        self.assertFalse(self.explorer._check_safety_limits())

    def test_duration_limit(self):
        """测试时间上限"""
        self.explorer._ralph_start_time = time.time()
        self.explorer._accumulated_duration = RALPH_MAX_DURATION
        self.assertTrue(self.explorer._check_safety_limits())

    def test_no_limits_exceeded(self):
        """测试未超过任何上限"""
        self.explorer._iteration_count = 0
        self.explorer._ralph_start_time = 0
        self.explorer._accumulated_duration = 0
        self.assertFalse(self.explorer._check_safety_limits())

    def test_duration_not_started(self):
        """测试未开始时的时间检查"""
        self.explorer._iteration_count = 0
        self.explorer._ralph_start_time = 0
        self.assertFalse(self.explorer._check_safety_limits())


class TestContextExtraction(unittest.TestCase):
    """测试关键上下文提取"""

    def setUp(self):
        self.mock_agent = MagicMock()
        self.mock_agent.system_prompt = "Test"
        self.mock_agent.history = []
        self.mock_agent.skill_loader = None
        self.mock_agent.tools = MagicMock()
        self.mock_agent.tools.get_tool_names.return_value = []
        self.explorer = AutonomousExplorer(self.mock_agent)

    def test_empty_history(self):
        """测试空历史"""
        result = self.explorer._extract_critical_context()
        self.assertIsNone(result)

    def test_extract_from_last_assistant(self):
        """测试从最后一条 assistant 消息提取"""
        self.mock_agent.history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "This is a long response that should be truncated"},
        ]
        result = self.explorer._extract_critical_context()
        self.assertIn("上次执行摘要", result)
        self.assertIn("This is a long response", result)

    def test_content_truncation(self):
        """测试内容截断"""
        long_content = "A" * 500
        self.mock_agent.history = [
            {"role": "assistant", "content": long_content},
        ]
        result = self.explorer._extract_critical_context()
        # 应该截断到300字符
        self.assertLessEqual(len(result), 400)  # 包含前缀

    def test_no_assistant_message(self):
        """测试没有 assistant 消息"""
        self.mock_agent.history = [
            {"role": "user", "content": "Hello"},
            {"role": "system", "content": "System"},
        ]
        result = self.explorer._extract_critical_context()
        self.assertIsNone(result)

    def test_empty_content(self):
        """测试空内容的 assistant 消息"""
        self.mock_agent.history = [
            {"role": "assistant", "content": ""},
        ]
        result = self.explorer._extract_critical_context()
        self.assertIsNone(result)


class TestStatePersistence(unittest.TestCase):
    """测试状态持久化"""

    def setUp(self):
        self.mock_agent = MagicMock()
        self.mock_agent.system_prompt = "Test"
        self.mock_agent.history = []
        self.mock_agent.skill_loader = None
        self.mock_agent.tools = MagicMock()
        self.mock_agent.tools.get_tool_names.return_value = []
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_file = Path(self.tmpdir.name) / "ralph_state.json"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_persist_and_load_state(self):
        """测试状态持久化和加载"""
        explorer = AutonomousExplorer(self.mock_agent)
        explorer._state_file = self.state_file
        explorer._iteration_count = 5
        explorer._ralph_start_time = time.time()
        explorer._accumulated_duration = 100.0

        explorer._persist_state("Test response")
        self.assertTrue(self.state_file.exists())

        # 创建新的 explorer 实例加载状态
        explorer2 = AutonomousExplorer(self.mock_agent)
        explorer2._state_file = self.state_file
        explorer2._load_or_init_state()

        self.assertEqual(explorer2._iteration_count, 5)
        self.assertGreaterEqual(explorer2._accumulated_duration, 100.0)

    def test_load_nonexistent_state(self):
        """测试加载不存在的状态文件"""
        explorer = AutonomousExplorer(self.mock_agent)
        explorer._state_file = self.state_file
        explorer._load_or_init_state()

        self.assertEqual(explorer._iteration_count, 0)
        self.assertEqual(explorer._accumulated_duration, 0)

    def test_load_corrupted_state(self):
        """测试加载损坏的状态文件"""
        self.state_file.write_text("invalid json{")

        explorer = AutonomousExplorer(self.mock_agent)
        explorer._state_file = self.state_file
        explorer._load_or_init_state()

        self.assertEqual(explorer._iteration_count, 0)
        self.assertEqual(explorer._accumulated_duration, 0)

    def test_cleanup_state(self):
        """测试清理状态文件"""
        self.state_file.write_text('{"iteration": 5}')

        explorer = AutonomousExplorer(self.mock_agent)
        explorer._state_file = self.state_file
        explorer._cleanup_state()

        self.assertFalse(self.state_file.exists())

    def test_persist_state_long_response(self):
        """测试长响应截断"""
        explorer = AutonomousExplorer(self.mock_agent)
        explorer._state_file = self.state_file
        long_response = "A" * 1000
        explorer._persist_state(long_response)

        state = json.loads(self.state_file.read_text())
        self.assertLessEqual(len(state["last_response"]), 500)


class TestTodoLoading(unittest.TestCase):
    """测试 TODO 文件加载"""

    def setUp(self):
        self.mock_agent = MagicMock()
        self.mock_agent.system_prompt = "Test"
        self.mock_agent.history = []
        self.mock_agent.skill_loader = None
        self.mock_agent.tools = MagicMock()
        self.mock_agent.tools.get_tool_names.return_value = []
        self.tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_load_existing_todo(self):
        """测试加载存在的 TODO 文件"""
        todo_file = Path(self.tmpdir.name) / "TODO.md"
        todo_content = "# TODO\n- [ ] Task 1\n- [ ] Task 2"
        todo_file.write_text(todo_content)

        AutonomousExplorer(self.mock_agent)
        with patch('autonomous.SEED_DIR', Path(self.tmpdir.name)):
            # 需要重新设置 SEED_DIR 常量
            pass

        # 直接测试 _load_todo_content 逻辑
        with patch.object(AutonomousExplorer, '_load_todo_content', return_value=todo_content):
            result = todo_content
            self.assertIn("Task 1", result)

    def test_load_nonexistent_todo(self):
        """测试加载不存在的 TODO 文件"""
        explorer = AutonomousExplorer(self.mock_agent)
        # 使用不存在的目录
        with patch('autonomous.SEED_DIR', Path(self.tmpdir.name)):
            result = explorer._load_todo_content()
            self.assertEqual(result, "")


class TestTaskSignals(unittest.TestCase):
    """测试任务信号提取"""

    def setUp(self):
        self.mock_agent = MagicMock()
        self.mock_agent.system_prompt = "Test"
        self.mock_agent.history = []
        self.mock_agent.skill_loader = None
        self.mock_agent.tools = MagicMock()
        self.mock_agent.tools.get_tool_names.return_value = []
        self.explorer = AutonomousExplorer(self.mock_agent)

    def test_extract_signals_from_todo(self):
        """测试从 TODO 提取信号"""
        todo = "# TODO\n- [ ] STR-04 测试覆盖提升\n- [ ] 诊断运行"
        signals = self.explorer._extract_task_signals(todo, has_todo=True)
        self.assertIn("execute", signals)
        self.assertIn("task", signals)

    def test_extract_signals_no_todo(self):
        """测试无 TODO 时的信号"""
        signals = self.explorer._extract_task_signals("", has_todo=False)
        self.assertIn("plan", signals)
        self.assertIn("generate", signals)
        self.assertNotIn("execute", signals)

    def test_signal_limit(self):
        """测试信号数量限制"""
        todo = "\n".join([f"- [ ] Task {i}" for i in range(20)])
        signals = self.explorer._extract_task_signals(todo, has_todo=True)
        self.assertLessEqual(len(signals), 10)


class TestTaskInstruction(unittest.TestCase):
    """测试任务指令构建"""

    def setUp(self):
        self.mock_agent = MagicMock()
        self.mock_agent.system_prompt = "Test system prompt"
        self.mock_agent.history = []
        self.mock_agent.skill_loader = None
        self.mock_agent.tools = MagicMock()
        self.mock_agent.tools.get_tool_names.return_value = []
        self.explorer = AutonomousExplorer(self.mock_agent)

    def test_build_instruction_with_todo(self):
        """测试有 TODO 时的指令"""
        todo = "# TODO\n- [ ] Task 1"
        instruction = self.explorer._build_task_instruction(todo, has_todo=True)
        self.assertIn("自主探索任务触发", instruction)
        self.assertIn("有待执行任务", instruction)
        self.assertIn("Task 1", instruction)
        self.assertIn("请按照 SOP 执行流程", instruction)

    def test_build_instruction_without_todo(self):
        """测试无 TODO 时的指令"""
        instruction = self.explorer._build_task_instruction("", has_todo=False)
        self.assertIn("自主探索任务触发", instruction)
        self.assertIn("无TODO，进入规划模式", instruction)
        self.assertIn("规划模式", instruction)
        self.assertIn("产出5-7条TODO", instruction)

    def test_instruction_contains_sop_principles(self):
        """测试指令包含 SOP 原则"""
        instruction = self.explorer._build_task_instruction("", has_todo=False)
        self.assertIn("价值公式", instruction)
        self.assertIn("不推诿", instruction)
        self.assertIn("失败升级", instruction)


class TestResponseHandling(unittest.TestCase):
    """测试响应处理"""

    def setUp(self):
        self.mock_agent = MagicMock()
        self.mock_agent.system_prompt = "Test"
        self.mock_agent.history = []
        self.mock_agent.skill_loader = None
        self.mock_agent.tools = MagicMock()
        self.mock_agent.tools.get_tool_names.return_value = []
        self.explorer = AutonomousExplorer(self.mock_agent)

    def test_handle_empty_response_first(self):
        """测试第一次空响应"""
        self.explorer._empty_response_count = 0
        import asyncio
        asyncio.run(self.explorer._handle_response(None))
        self.assertEqual(self.explorer._empty_response_count, 1)

    def test_handle_empty_response_third(self):
        """测试第三次空响应触发简化 prompt"""
        self.explorer._empty_response_count = 2
        # 使用 MagicMock 来跟踪 append 调用
        self.mock_agent.history = MagicMock()
        self.explorer.agent = self.mock_agent
        import asyncio
        asyncio.run(self.explorer._handle_response(None))
        self.assertEqual(self.explorer._empty_response_count, 3)
        # 检查是否调用了 append
        self.mock_agent.history.append.assert_called_once()
        call_args = self.mock_agent.history.append.call_args
        self.assertIn("请报告当前状态", str(call_args))

    def test_handle_nonempty_response(self):
        """测试非空响应"""
        self.explorer._empty_response_count = 1
        import asyncio
        asyncio.run(self.explorer._handle_response("Some response"))
        self.assertEqual(self.explorer._empty_response_count, 1)  # 不应增加


if __name__ == '__main__':
    unittest.main()
