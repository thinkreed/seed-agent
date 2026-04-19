"""Ralph Loop 单元测试"""

import os
import json
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
import pytest

# 导入测试模块
from src.ralph_loop import RalphLoop, CompletionType, SEED_DIR, create_ralph_loop
from src.tools.ralph_tools import (
    start_ralph_loop,
    write_completion_marker,
    check_ralph_status,
    stop_ralph_loop,
    create_ralph_task_file
)


class TestCompletionType:
    """测试完成验证类型"""

    def test_completion_types_exist(self):
        """验证所有完成类型存在"""
        assert CompletionType.TEST_PASS.value == "test_pass"
        assert CompletionType.FILE_EXISTS.value == "file_exists"
        assert CompletionType.MARKER_FILE.value == "marker_file"
        assert CompletionType.GIT_CLEAN.value == "git_clean"
        assert CompletionType.CUSTOM_CHECK.value == "custom_check"


class TestRalphLoopCompletionChecks:
    """测试 Ralph Loop 完成验证"""

    def setup_method(self):
        """测试前设置"""
        self.temp_dir = tempfile.mkdtemp()
        self.agent_mock = Mock()
        self.agent_mock.history = []

    def teardown_method(self):
        """测试后清理"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_check_marker_file(self):
        """测试标志文件验证"""
        task_file = Path(self.temp_dir) / "task.md"
        task_file.write_text("Test task")

        ralph = RalphLoop(
            agent_loop=self.agent_mock,
            completion_type=CompletionType.MARKER_FILE,
            completion_criteria={
                "marker_path": str(Path(self.temp_dir) / "done"),
                "marker_content": "DONE"
            },
            task_prompt_path=task_file
        )

        # 标志文件不存在时
        assert not ralph._check_marker_file()

        # 创建标志文件
        marker = Path(self.temp_dir) / "done"
        marker.write_text("DONE")

        # 标志文件存在时
        assert ralph._check_marker_file()

        # 标志文件被清除
        assert not marker.exists()

    def test_check_file_exists(self):
        """测试文件存在验证"""
        task_file = Path(self.temp_dir) / "task.md"
        task_file.write_text("Test task")

        ralph = RalphLoop(
            agent_loop=self.agent_mock,
            completion_type=CompletionType.FILE_EXISTS,
            completion_criteria={
                "files": [
                    str(Path(self.temp_dir) / "output1.txt"),
                    str(Path(self.temp_dir) / "output2.txt")
                ]
            },
            task_prompt_path=task_file
        )

        # 文件不存在时
        assert not ralph._check_file_exists()

        # 创建部分文件
        Path(self.temp_dir).joinpath("output1.txt").write_text("result")
        assert not ralph._check_file_exists()

        # 创建所有文件
        Path(self.temp_dir).joinpath("output2.txt").write_text("result")
        assert ralph._check_file_exists()

    def test_check_custom(self):
        """测试自定义验证"""
        task_file = Path(self.temp_dir) / "task.md"
        task_file.write_text("Test task")

        # 自定义验证函数
        custom_checker = Mock(return_value=True)

        ralph = RalphLoop(
            agent_loop=self.agent_mock,
            completion_type=CompletionType.CUSTOM_CHECK,
            completion_criteria={
                "checker": custom_checker
            },
            task_prompt_path=task_file
        )

        assert ralph._check_custom()
        custom_checker.assert_called_once()

    def test_check_safety_limits(self):
        """测试安全上限检查"""
        task_file = Path(self.temp_dir) / "task.md"
        task_file.write_text("Test task")

        ralph = RalphLoop(
            agent_loop=self.agent_mock,
            completion_type=CompletionType.MARKER_FILE,
            completion_criteria={},
            task_prompt_path=task_file,
            max_iterations=10
        )

        ralph._iteration_count = 5
        assert not ralph._check_safety_limits()

        ralph._iteration_count = 10
        assert ralph._check_safety_limits()


class TestRalphLoopContext:
    """测试上下文管理"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.agent_mock = Mock()
        self.agent_mock.history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Continue"},
            {"role": "assistant", "content": "Response 2 with important info"},
        ]

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_extract_critical_context(self):
        """测试关键上下文提取"""
        task_file = Path(self.temp_dir) / "task.md"
        task_file.write_text("Test task")

        ralph = RalphLoop(
            agent_loop=self.agent_mock,
            completion_type=CompletionType.MARKER_FILE,
            completion_criteria={},
            task_prompt_path=task_file
        )

        result = ralph._extract_critical_context()
        assert result is not None
        assert "Response 2" in result

    def test_reset_context(self):
        """测试上下文重置"""
        task_file = Path(self.temp_dir) / "task.md"
        task_file.write_text("Test task")

        ralph = RalphLoop(
            agent_loop=self.agent_mock,
            completion_type=CompletionType.MARKER_FILE,
            completion_criteria={},
            task_prompt_path=task_file,
            context_reset_interval=3
        )

        # 不在重置间隔时
        ralph._iteration_count = 2
        ralph._reset_context()
        assert len(self.agent_mock.history) == 4

        # 在重置间隔时
        ralph._iteration_count = 3
        ralph._reset_context()
        assert len(self.agent_mock.history) <= 2


class TestRalphTools:
    """测试 Ralph Loop 工具"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        # 覆盖 SEED_DIR 为临时目录
        self.original_seed_dir = SEED_DIR

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_write_completion_marker_default(self):
        """测试写入默认完成标志"""
        with patch('src.tools.ralph_tools.COMPLETION_PROMISE_FILE', Path(self.temp_dir) / 'completion_promise'):
            result = write_completion_marker("DONE")
            assert "Completion marker written" in result

            marker = Path(self.temp_dir) / 'completion_promise'
            assert marker.exists()
            assert marker.read_text() == "DONE"

    def test_write_completion_marker_custom(self):
        """测试写入自定义完成标志"""
        marker_path = str(Path(self.temp_dir) / "custom_marker")

        with patch('src.tools.ralph_tools.SEED_DIR', Path(self.temp_dir)):
            result = write_completion_marker("COMPLETE", marker_path)
            assert "Completion marker written" in result

            marker = Path(marker_path)
            assert marker.exists()
            assert marker.read_text() == "COMPLETE"

    def test_create_ralph_task_file(self):
        """测试创建任务文件"""
        with patch('src.tools.ralph_tools.SEED_DIR', Path(self.temp_dir)):
            result = create_ralph_task_file("test_task", "# Test Task\n\nDescription here.")
            assert "Task file created" in result

            task_file = Path(self.temp_dir) / "tasks" / "test_task.md"
            assert task_file.exists()
            assert "Test Task" in task_file.read_text()

    def test_check_ralph_status_empty(self):
        """测试空状态检查"""
        with patch('src.tools.ralph_tools.RALPH_STATE_DIR', Path(self.temp_dir) / "ralph"):
            result = check_ralph_status()
            assert "No Ralph Loops found" in result


class TestRalphLoopFactory:
    """测试 Ralph Loop 工厂方法"""

    def test_create_test_driven(self):
        """测试创建测试驱动的 Ralph Loop"""
        agent_mock = Mock()
        task_file = Path(tempfile.mkdtemp()) / "task.md"
        task_file.write_text("Test task")

        ralph = RalphLoop.create_test_driven(
            agent_loop=agent_mock,
            task_prompt_path=task_file,
            test_command="pytest tests/",
            pass_rate=80
        )

        assert ralph.completion_type == CompletionType.TEST_PASS
        assert ralph.completion_criteria["pass_rate"] == 80

    def test_create_marker_driven(self):
        """测试创建标志文件驱动的 Ralph Loop"""
        agent_mock = Mock()
        task_file = Path(tempfile.mkdtemp()) / "task.md"
        task_file.write_text("Test task")

        ralph = RalphLoop.create_marker_driven(
            agent_loop=agent_mock,
            task_prompt_path=task_file,
            marker_content="DONE"
        )

        assert ralph.completion_type == CompletionType.MARKER_FILE


# pytest 运行入口
if __name__ == "__main__":
    pytest.main([__file__, "-v"])