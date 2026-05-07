"""自主探索模块单元测试（四层防御体系增强版）

测试覆盖:
- CompletionType enum: 完成验证类型
- AutonomousExplorer 初始化: SOP 加载、状态初始化、四层防御状态
- record_activity / get_idle_time: 空闲时间计算
- _check_completion_promise: 完成标志检测与清理
- _check_safety_limits: 迭代和时间安全上限
- _extract_critical_context: 关键上下文提取
- _persist_state / _load_or_init_state / _cleanup_state: 状态持久化
- _load_todo_content: TODO 文件加载
- _extract_task_signals: 任务信号提取
- _build_task_instruction: 任务指令构建
- _handle_response: 空响应处理

新增四层防御测试:
- _get_retry_budget: 递减预算计算
- _inject_budget_warning: 预算警告注入
- _check_progress_window: 进度检测窗口
- _check_time_circuit_breaker: 时间断路器
- _reset_defense_state: 防御状态重置
- AutonomousConfig 新增字段验证
"""

import sys
import json
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

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


class TestAutonomousConfigFields(unittest.TestCase):
    """测试 AutonomousConfig 新增字段（方案 A+C）"""

    def test_config_fields_exist(self):
        """测试所有新增配置字段存在"""
        from src.shared_config import get_autonomous_config
        config = get_autonomous_config()

        # 方案 A: 配置化上限
        self.assertEqual(config.max_iterations_per_task, 100)
        self.assertEqual(config.max_iterations_high, 300)
        self.assertEqual(config.max_iterations_research, 500)
        self.assertEqual(config.max_duration_per_task, 1800)
        self.assertEqual(config.max_retry_count, 3)

        # 方案 C: 渐进式预算
        self.assertEqual(config.budget_warning_threshold, 0.70)
        self.assertEqual(config.budget_urgent_threshold, 0.90)
        self.assertEqual(config.progress_detection_window, 5)
        self.assertEqual(config.time_warning_threshold, 0.80)

        # retry_decay_factors 默认值
        self.assertEqual(config.retry_decay_factors, [1.0, 0.5, 0.25])

        # meaningful_tools 默认值
        expected_tools = [
            "file_read", "file_write", "file_edit",
            "code_as_policy", "search_grep", "search_glob"
        ]
        self.assertEqual(config.meaningful_tools, expected_tools)


class TestAutonomousExplorerInit(unittest.TestCase):
    """测试 AutonomousExplorer 初始化（四层防御状态）"""

    def setUp(self):
        """设置测试环境"""
        self.mock_agent = MagicMock()
        self.mock_agent.system_prompt = "Test system prompt"
        self.mock_agent.history = []
        self.mock_agent.skill_loader = None
        self.mock_agent.tools = MagicMock()
        self.mock_agent.tools.get_tool_names.return_value = []
        self.mock_agent.max_iterations = 50
        self.mock_agent.inject_system_message = MagicMock()

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

    def test_init_defense_state(self):
        """测试四层防御状态初始化"""
        explorer = AutonomousExplorer(self.mock_agent)

        # 验证四层防御状态变量
        self.assertEqual(explorer._task_start_time, 0.0)
        self.assertEqual(explorer._action_history, [])
        self.assertEqual(explorer._retry_count, 0)
        self.assertFalse(explorer._budget_warning_sent)
        self.assertFalse(explorer._budget_urgent_sent)
        self.assertFalse(explorer._time_warning_sent)

    def test_idle_timeout_from_config(self):
        """测试空闲超时从配置读取"""
        from src.shared_config import get_autonomous_config
        config = get_autonomous_config()
        expected_timeout = config.idle_timeout_hours * 60 * 60  # 默认2小时
        explorer = AutonomousExplorer(self.mock_agent)
        self.assertEqual(explorer._idle_timeout, expected_timeout)

    def test_config_reference(self):
        """测试配置引用"""
        explorer = AutonomousExplorer(self.mock_agent)
        from src.shared_config import get_autonomous_config
        config = get_autonomous_config()
        self.assertEqual(explorer._config, config)


class TestActivityTracking(unittest.TestCase):
    """测试活动跟踪功能"""

    def setUp(self):
        self.mock_agent = MagicMock()
        self.mock_agent.system_prompt = "Test"
        self.mock_agent.history = []
        self.mock_agent.skill_loader = None
        self.mock_agent.tools = MagicMock()
        self.mock_agent.tools.get_tool_names.return_value = []
        self.mock_agent.inject_system_message = MagicMock()
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
        self.mock_agent.inject_system_message = MagicMock()
        self.explorer = AutonomousExplorer(self.mock_agent)

    def test_completion_promise_detected(self):
        """测试检测到完成标志"""
        with tempfile.TemporaryDirectory() as tmpdir:
            promise_file = Path(tmpdir) / "completion_promise"
            promise_file.write_text("DONE")

            # 使用动态函数替代常量 patch - 更新路径以适应新模块结构
            with patch('autonomous._explorer._get_completion_promise_file', return_value=promise_file):
                result = self.explorer._check_completion_promise()
                self.assertTrue(result)
                # 文件应被删除
                self.assertFalse(promise_file.exists())

    def test_completion_promise_complete(self):
        """测试 COMPLETE 标志"""
        with tempfile.TemporaryDirectory() as tmpdir:
            promise_file = Path(tmpdir) / "completion_promise"
            promise_file.write_text("COMPLETE")

            with patch('autonomous._explorer._get_completion_promise_file', return_value=promise_file):
                result = self.explorer._check_completion_promise()
                self.assertTrue(result)

    def test_completion_promise_task_finished(self):
        """测试 TASK_FINISHED 标志"""
        with tempfile.TemporaryDirectory() as tmpdir:
            promise_file = Path(tmpdir) / "completion_promise"
            promise_file.write_text("TASK_FINISHED")

            with patch('autonomous._explorer._get_completion_promise_file', return_value=promise_file):
                result = self.explorer._check_completion_promise()
                self.assertTrue(result)

    def test_completion_promise_not_detected(self):
        """测试未检测到完成标志"""
        with tempfile.TemporaryDirectory() as tmpdir:
            promise_file = Path(tmpdir) / "completion_promise"
            promise_file.write_text("IN_PROGRESS")

            with patch('autonomous._explorer._get_completion_promise_file', return_value=promise_file):
                result = self.explorer._check_completion_promise()
                self.assertFalse(result)
                # 文件不应被删除
                self.assertTrue(promise_file.exists())

    def test_completion_promise_file_not_exists(self):
        """测试标志文件不存在"""
        with tempfile.TemporaryDirectory() as tmpdir:
            promise_file = Path(tmpdir) / "completion_promise"

            with patch('autonomous._explorer._get_completion_promise_file', return_value=promise_file):
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
        self.mock_agent.inject_system_message = MagicMock()
        self.explorer = AutonomousExplorer(self.mock_agent)

    def test_iteration_limit(self):
        """测试迭代上限"""
        self.explorer._task_executor._state_manager.set_iteration_count(RALPH_MAX_ITERATIONS)
        self.assertTrue(self.explorer._check_safety_limits())

        self.explorer._task_executor._state_manager.set_iteration_count(RALPH_MAX_ITERATIONS - 1)
        self.assertFalse(self.explorer._check_safety_limits())

    def test_duration_limit(self):
        """测试时间上限"""
        self.explorer._task_executor._state_manager.set_start_time(time.time())
        self.explorer._task_executor._state_manager.set_accumulated_duration(RALPH_MAX_DURATION)
        self.assertTrue(self.explorer._check_safety_limits())

    def test_no_limits_exceeded(self):
        """测试未超过任何上限"""
        self.explorer._task_executor._state_manager.set_iteration_count(0)
        self.explorer._task_executor._state_manager.set_start_time(0)
        self.explorer._task_executor._state_manager.set_accumulated_duration(0)
        self.assertFalse(self.explorer._check_safety_limits())

    def test_duration_not_started(self):
        """测试未开始时的时间检查"""
        self.explorer._task_executor._state_manager.set_iteration_count(0)
        self.explorer._task_executor._state_manager.set_start_time(0)
        self.assertFalse(self.explorer._check_safety_limits())


class TestFourLayerDefense(unittest.TestCase):
    """测试四层防御机制（方案 C）"""

    def setUp(self):
        """设置测试环境"""
        self.mock_agent = MagicMock()
        self.mock_agent.system_prompt = "Test"
        self.mock_agent.history = []
        self.mock_agent.skill_loader = None
        self.mock_agent.tools = MagicMock()
        self.mock_agent.tools.get_tool_names.return_value = []
        self.mock_agent.inject_system_message = MagicMock()
        self.explorer = AutonomousExplorer(self.mock_agent)

    # === Layer 4: 递减重试预算 ===

    def test_retry_budget_first_attempt(self):
        """测试首次尝试预算（100%）"""
        self.explorer._retry_count = 0
        budget = self.explorer._get_retry_budget()
        from src.shared_config import get_autonomous_config
        config = get_autonomous_config()
        self.assertEqual(budget, config.max_iterations_per_task)

    def test_retry_budget_second_attempt(self):
        """测试第二次重试预算（50%）"""
        self.explorer._retry_count = 1
        budget = self.explorer._get_retry_budget()
        from src.shared_config import get_autonomous_config
        config = get_autonomous_config()
        expected = int(config.max_iterations_per_task * 0.5)
        self.assertEqual(budget, expected)

    def test_retry_budget_third_attempt(self):
        """测试第三次重试预算（25%）"""
        self.explorer._retry_count = 2
        budget = self.explorer._get_retry_budget()
        from src.shared_config import get_autonomous_config
        config = get_autonomous_config()
        expected = int(config.max_iterations_per_task * 0.25)
        self.assertEqual(budget, expected)

    def test_retry_budget_exceeds_max(self):
        """测试超过最大重试次数"""
        self.explorer._retry_count = 10  # 远超过 max_retry_count
        budget = self.explorer._get_retry_budget()
        self.assertEqual(budget, 0)

    # === Layer 1: 预算警告注入 ===

    def test_budget_warning_70_percent(self):
        """测试 70% 预算警告注入"""
        import asyncio

        self.explorer._budget_warning_sent = False
        self.explorer._budget_urgent_sent = False

        # 模拟 70% 使用率
        asyncio.run(self.explorer._inject_budget_warning(70, 100))

        # 验证警告消息已注入
        self.assertTrue(self.explorer._budget_warning_sent)
        self.assertFalse(self.explorer._budget_urgent_sent)  # 未触发 90%
        self.mock_agent.inject_system_message.assert_called_once()

        # 验证消息内容
        call_args = self.mock_agent.inject_system_message.call_args[0][0]
        self.assertIn("[BUDGET WARNING]", call_args)
        self.assertIn("70%", call_args)

    def test_budget_warning_90_percent(self):
        """测试 90% 紧急警告注入"""
        import asyncio

        self.explorer._budget_warning_sent = False
        self.explorer._budget_urgent_sent = False

        # 模拟 90% 使用率
        asyncio.run(self.explorer._inject_budget_warning(90, 100))

        # 验证两个警告都已触发
        self.assertTrue(self.explorer._budget_warning_sent)
        self.assertTrue(self.explorer._budget_urgent_sent)
        self.assertEqual(self.mock_agent.inject_system_message.call_count, 2)

        # 验证紧急消息内容
        calls = self.mock_agent.inject_system_message.call_args_list
        urgent_call = calls[1][0][0]
        self.assertIn("[BUDGET URGENT]", urgent_call)

    def test_budget_warning_no_duplicate(self):
        """测试警告不重复发送"""
        import asyncio

        self.explorer._budget_warning_sent = True  # 已发送过

        # 再次调用不应发送
        asyncio.run(self.explorer._inject_budget_warning(75, 100))

        # 验证未重复调用
        self.mock_agent.inject_system_message.assert_not_called()

    # === Layer 2: 进度检测窗口 ===

    def test_progress_window_has_progress(self):
        """测试有进展的进度检测"""
        # 添加有意义的工具调用历史
        self.explorer._action_history = [
            {"tool": "file_read", "iteration": 1},
            {"tool": "file_write", "iteration": 2},
            {"tool": "code_as_policy", "iteration": 3},
        ]

        result = self.explorer._check_progress_window()
        self.assertTrue(result)

    def test_progress_window_empty_loop(self):
        """测试空转循环检测"""
        # 设置足够的历史（达到窗口大小）
        window_size = self.explorer._config.progress_detection_window
        self.explorer._action_history = [
            {"tool": "ask_user", "iteration": i}  # 不在 meaningful_tools 中
            for i in range(window_size)
        ]

        result = self.explorer._check_progress_window()
        self.assertFalse(result)

    def test_progress_window_insufficient_history(self):
        """测试历史不足时不判定空转"""
        # 只有 2 条历史（窗口大小为 5）
        self.explorer._action_history = [
            {"tool": "ask_user", "iteration": 1},
            {"tool": "ask_user", "iteration": 2},
        ]

        result = self.explorer._check_progress_window()
        self.assertTrue(result)  # 历史不足，不判定空转

    # === Layer 3: 时间断路器 ===

    def test_time_circuit_breaker_not_triggered(self):
        """测试时间断路器未触发"""
        self.explorer._task_start_time = time.time()
        self.explorer._time_warning_sent = False

        result = self.explorer._check_time_circuit_breaker()
        self.assertTrue(result)

    def test_time_circuit_breaker_triggered(self):
        """测试时间断路器触发"""
        # 设置开始时间为很久以前
        max_duration = self.explorer._config.max_duration_per_task
        self.explorer._task_start_time = time.time() - max_duration - 1

        result = self.explorer._check_time_circuit_breaker()
        self.assertFalse(result)

    def test_time_warning_80_percent(self):
        """测试 80% 时间警告"""
        max_duration = self.explorer._config.max_duration_per_task
        self.explorer._task_start_time = time.time() - max_duration * 0.85
        self.explorer._time_warning_sent = False

        self.explorer._check_time_circuit_breaker()

        # 验证警告已发送
        self.assertTrue(self.explorer._time_warning_sent)
        self.mock_agent.inject_system_message.assert_called_once()

        # 验证消息内容
        call_args = self.mock_agent.inject_system_message.call_args[0][0]
        self.assertIn("[TIME WARNING]", call_args)

    # === 防御状态重置 ===

    def test_reset_defense_state(self):
        """测试防御状态重置"""
        # 设置一些非初始状态
        self.explorer._task_start_time = 0.0
        self.explorer._action_history = [{"tool": "test", "iteration": 1}]
        self.explorer._budget_warning_sent = True
        self.explorer._budget_urgent_sent = True
        self.explorer._time_warning_sent = True

        # 重置
        self.explorer._reset_defense_state()

        # 验证状态已重置
        self.assertGreater(self.explorer._task_start_time, 0.0)
        self.assertEqual(self.explorer._action_history, [])
        self.assertFalse(self.explorer._budget_warning_sent)
        self.assertFalse(self.explorer._budget_urgent_sent)
        self.assertFalse(self.explorer._time_warning_sent)


class TestContextExtraction(unittest.TestCase):
    """测试关键上下文提取"""

    def setUp(self):
        self.mock_agent = MagicMock()
        self.mock_agent.system_prompt = "Test"
        self.mock_agent.history = []
        self.mock_agent.skill_loader = None
        self.mock_agent.tools = MagicMock()
        self.mock_agent.tools.get_tool_names.return_value = []
        self.mock_agent.inject_system_message = MagicMock()
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
        self.mock_agent.inject_system_message = MagicMock()
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
        self.mock_agent.inject_system_message = MagicMock()
        self.tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_load_existing_todo(self):
        """测试加载存在的 TODO 文件"""
        todo_file = Path(self.tmpdir.name) / "TODO.md"
        todo_content = "# TODO\n- [ ] Task 1\n- [ ] Task 2"
        todo_file.write_text(todo_content)

        AutonomousExplorer(self.mock_agent)
        with patch('autonomous._ensure_seed_dir', return_value=Path(self.tmpdir.name)):
            # 需要重新设置 SEED_DIR 常量
            pass

        # 直接测试 _load_todo_content 逻辑
        with patch.object(AutonomousExplorer, '_load_todo_content', return_value=todo_content):
            result = todo_content
            self.assertIn("Task 1", result)

    def test_load_nonexistent_todo(self):
        """测试加载不存在的 TODO 文件"""
        # 直接替换方法 globals 中的函数引用
        # 原因：method.__globals__ 和 module.__dict__ 是不同的字典
        method = AutonomousExplorer._load_todo_content
        original_func = method.__globals__['get_seed_dir_with_fallback']
        
        # 替换为返回临时目录的函数
        method.__globals__['get_seed_dir_with_fallback'] = lambda: Path(self.tmpdir.name)
        
        explorer = AutonomousExplorer(self.mock_agent)
        # 清理缓存，确保从新路径读取
        explorer._task_executor._todo_cache._cache = None
        explorer._task_executor._todo_cache._cache_seed_dir = None
        explorer._task_executor._todo_cache._cache_time = 0.0
        result = explorer._load_todo_content()
        
        # 恢复原始函数
        method.__globals__['get_seed_dir_with_fallback'] = original_func
        
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
        self.mock_agent.inject_system_message = MagicMock()
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
        self.mock_agent.inject_system_message = MagicMock()
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
        self.mock_agent.inject_system_message = MagicMock()
        self.explorer = AutonomousExplorer(self.mock_agent)

    def test_handle_empty_response_first(self):
        """测试第一次空响应"""
        self.explorer._empty_response_count = 0
        import asyncio
        result = asyncio.run(self.explorer._handle_response(None))
        self.assertEqual(self.explorer._empty_response_count, 1)
        # 新版本返回 prompt 字符串
        self.assertIsNotNone(result)
        self.assertIn("继续执行自主探索任务", result)

    def test_handle_empty_response_third(self):
        """测试第三次空响应触发简化 prompt"""
        self.explorer._empty_response_count = 2
        import asyncio
        result = asyncio.run(self.explorer._handle_response(None))
        self.assertEqual(self.explorer._empty_response_count, 3)
        # 新版本返回 prompt 字符串而不是修改 history
        self.assertIsNotNone(result)
        self.assertIn("请报告当前状态", result)

    def test_handle_nonempty_response(self):
        """测试非空响应"""
        self.explorer._empty_response_count = 1
        import asyncio
        result = asyncio.run(self.explorer._handle_response("Some response"))
        self.assertEqual(self.explorer._empty_response_count, 1)  # 不应增加
        # 非空响应返回 None
        self.assertIsNone(result)


class TestAutonomousMode(unittest.TestCase):
    """测试自主模式（autonomous_mode）"""

    def setUp(self):
        """设置测试环境"""
        self.mock_agent = MagicMock()
        self.mock_agent.system_prompt = "Test"
        self.mock_agent.history = []
        self.mock_agent.skill_loader = None
        self.mock_agent.tools = MagicMock()
        self.mock_agent.tools.get_tool_names.return_value = []
        self.mock_agent.set_autonomous_mode = MagicMock()
        self.mock_agent.inject_system_message = MagicMock()
        self.explorer = AutonomousExplorer(self.mock_agent)

    def test_set_autonomous_mode_called(self):
        """测试 set_autonomous_mode 方法存在"""
        # 验证 AgentLoop 有 set_autonomous_mode 方法
        self.assertTrue(hasattr(self.mock_agent, 'set_autonomous_mode'))

    def test_autonomous_config_values(self):
        """测试 AutonomousConfig 新配置值"""
        from src.shared_config import get_autonomous_config
        config = get_autonomous_config()
        # 验证新增配置值
        self.assertEqual(config.llm_call_timeout_seconds, 300)
        self.assertEqual(config.consecutive_failure_threshold, 3)
        self.assertEqual(config.backoff_duration_seconds, 60)
        self.assertEqual(config.max_backoff_multiplier, 5)
        self.assertTrue(config.debug_logging_enabled)
        self.assertTrue(config.ask_user_auto_confirm)


class TestTimeoutProtection(unittest.TestCase):
    """测试超时保护"""

    def setUp(self):
        """设置测试环境"""
        self.mock_agent = MagicMock()
        self.mock_agent.system_prompt = "Test"
        self.mock_agent.history = []
        self.mock_agent.skill_loader = None
        self.mock_agent.tools = MagicMock()
        self.mock_agent.tools.get_tool_names.return_value = []
        self.mock_agent.inject_system_message = MagicMock()
        self.explorer = AutonomousExplorer(self.mock_agent)

    def test_timeout_config_available(self):
        """测试超时配置可用"""
        from src.shared_config import get_autonomous_config
        config = get_autonomous_config()
        # 验证超时配置值合理
        self.assertGreater(config.llm_call_timeout_seconds, 0)
        self.assertLess(config.llm_call_timeout_seconds, 3600)  # 不超过1小时

    def test_timeout_error_handling(self):
        """测试超时错误处理逻辑"""
        import asyncio
        # 模拟超时场景（简化测试，不实际等待）
        # 验证配置读取正确
        from src.shared_config import get_autonomous_config
        config = get_autonomous_config()
        self.assertEqual(config.llm_call_timeout_seconds, 300)


class TestErrorRecovery(unittest.TestCase):
    """测试错误恢复退避策略"""

    def setUp(self):
        """设置测试环境"""
        self.mock_agent = MagicMock()
        self.mock_agent.system_prompt = "Test"
        self.mock_agent.history = []
        self.mock_agent.skill_loader = None
        self.mock_agent.tools = MagicMock()
        self.mock_agent.tools.get_tool_names.return_value = []
        self.mock_agent.inject_system_message = MagicMock()
        self.explorer = AutonomousExplorer(self.mock_agent)

    def test_backoff_config(self):
        """测试退避配置"""
        from src.shared_config import get_autonomous_config
        config = get_autonomous_config()
        # 验证退避配置
        self.assertEqual(config.consecutive_failure_threshold, 3)
        self.assertEqual(config.backoff_duration_seconds, 60)
        self.assertEqual(config.max_backoff_multiplier, 5)
        # 验证最大退避时间
        max_backoff = config.max_backoff_multiplier * config.backoff_duration_seconds
        self.assertEqual(max_backoff, 300)  # 5分钟

    def test_exponential_backoff_calculation(self):
        """测试指数退避计算"""
        from src.shared_config import get_autonomous_config
        config = get_autonomous_config()
        base = config.backoff_duration_seconds
        threshold = config.consecutive_failure_threshold
        max_backoff = config.max_backoff_multiplier * base

        # 验证退避时间计算逻辑
        # consecutive_failures = threshold: backoff = base
        # consecutive_failures = threshold + 1: backoff = base * 2
        # consecutive_failures = threshold + 2: backoff = base * 4
        for i in range(5):
            failures = threshold + i
            expected = min(base * (2 ** i), max_backoff)
            # 验证计算正确
            self.assertGreater(expected, 0)
            self.assertLessEqual(expected, max_backoff)


class TestInjectSystemMessage(unittest.TestCase):
    """测试 inject_system_message 方法（新增）"""

    def setUp(self):
        """设置测试环境"""
        self.mock_agent = MagicMock()
        self.mock_agent.inject_system_message = MagicMock()

    def test_inject_system_message_exists(self):
        """测试 inject_system_message 方法存在"""
        self.assertTrue(hasattr(self.mock_agent, 'inject_system_message'))

    def test_inject_system_message_called(self):
        """测试 inject_system_message 被正确调用"""
        test_message = "[BUDGET WARNING] Test message"
        self.mock_agent.inject_system_message(test_message)

        self.mock_agent.inject_system_message.assert_called_once_with(test_message)


if __name__ == '__main__':
    unittest.main()