"""Ralph Loop 功能验证（无 pytest）"""

import os
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ralph_loop import RalphLoop, CompletionType, create_ralph_loop
from src.tools.ralph_tools import (
    write_completion_marker,
    check_ralph_status,
    create_ralph_task_file
)


def test_completion_types():
    """验证完成类型"""
    print("Testing CompletionType...")
    assert CompletionType.TEST_PASS.value == "test_pass"
    assert CompletionType.FILE_EXISTS.value == "file_exists"
    assert CompletionType.MARKER_FILE.value == "marker_file"
    assert CompletionType.GIT_CLEAN.value == "git_clean"
    assert CompletionType.CUSTOM_CHECK.value == "custom_check"
    print("✓ CompletionType passed")


def test_marker_file_check():
    """测试标志文件验证"""
    print("\nTesting marker file check...")
    temp_dir = tempfile.mkdtemp()
    agent_mock = Mock()
    agent_mock.history = []

    task_file = Path(temp_dir) / "task.md"
    task_file.write_text("Test task")

    ralph = RalphLoop(
        agent_loop=agent_mock,
        completion_type=CompletionType.MARKER_FILE,
        completion_criteria={
            "marker_path": str(Path(temp_dir) / "done"),
            "marker_content": "DONE"
        },
        task_prompt_path=task_file
    )

    # 标志文件不存在
    assert not ralph._check_marker_file()
    print("✓ Marker not found - check passed")

    # 创建标志文件
    marker = Path(temp_dir) / "done"
    marker.write_text("DONE")
    assert ralph._check_marker_file()
    print("✓ Marker found - check passed")

    # 清理
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_file_exists_check():
    """测试文件存在验证"""
    print("\nTesting file exists check...")
    temp_dir = tempfile.mkdtemp()
    agent_mock = Mock()
    agent_mock.history = []

    task_file = Path(temp_dir) / "task.md"
    task_file.write_text("Test task")

    ralph = RalphLoop(
        agent_loop=agent_mock,
        completion_type=CompletionType.FILE_EXISTS,
        completion_criteria={
            "files": [
                str(Path(temp_dir) / "output1.txt"),
                str(Path(temp_dir) / "output2.txt")
            ]
        },
        task_prompt_path=task_file
    )

    # 文件不存在
    assert not ralph._check_file_exists()
    print("✓ Files not found - check passed")

    # 创建所有文件
    Path(temp_dir).joinpath("output1.txt").write_text("result")
    Path(temp_dir).joinpath("output2.txt").write_text("result")
    assert ralph._check_file_exists()
    print("✓ All files found - check passed")

    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_safety_limits():
    """测试安全上限"""
    print("\nTesting safety limits...")
    temp_dir = tempfile.mkdtemp()
    agent_mock = Mock()
    agent_mock.history = []

    task_file = Path(temp_dir) / "task.md"
    task_file.write_text("Test task")

    ralph = RalphLoop(
        agent_loop=agent_mock,
        completion_type=CompletionType.MARKER_FILE,
        completion_criteria={},
        task_prompt_path=task_file,
        max_iterations=10,
        max_duration=3600  # 1小时
    )

    # 初始化 start_time
    import time
    ralph._start_time = time.time()

    ralph._iteration_count = 5
    assert not ralph._check_safety_limits()
    print("✓ Under limit - check passed")

    ralph._iteration_count = 10
    assert ralph._check_safety_limits()
    print("✓ Over limit - check passed")

    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_context_reset():
    """测试上下文重置"""
    print("\nTesting context reset...")
    temp_dir = tempfile.mkdtemp()
    agent_mock = Mock()
    agent_mock.history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Response"},
    ]

    task_file = Path(temp_dir) / "task.md"
    task_file.write_text("Test task")

    ralph = RalphLoop(
        agent_loop=agent_mock,
        completion_type=CompletionType.MARKER_FILE,
        completion_criteria={},
        task_prompt_path=task_file,
        context_reset_interval=3
    )

    # 不在重置间隔
    ralph._iteration_count = 2
    ralph._reset_context()
    assert len(agent_mock.history) == 2
    print("✓ No reset at iteration 2 - passed")

    # 在重置间隔
    ralph._iteration_count = 3
    ralph._reset_context()
    assert len(agent_mock.history) <= 2
    print("✓ Reset at iteration 3 - passed")

    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_factory_methods():
    """测试工厂方法"""
    print("\nTesting factory methods...")
    agent_mock = Mock()
    temp_dir = tempfile.mkdtemp()
    task_file = Path(temp_dir) / "task.md"
    task_file.write_text("Test task")

    # 测试驱动
    ralph = RalphLoop.create_test_driven(
        agent_loop=agent_mock,
        task_prompt_path=task_file,
        pass_rate=80
    )
    assert ralph.completion_type == CompletionType.TEST_PASS
    assert ralph.completion_criteria["pass_rate"] == 80
    print("✓ create_test_driven passed")

    # 标志文件驱动
    ralph = RalphLoop.create_marker_driven(
        agent_loop=agent_mock,
        task_prompt_path=task_file
    )
    assert ralph.completion_type == CompletionType.MARKER_FILE
    print("✓ create_marker_driven passed")

    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_tools():
    """测试工具函数"""
    print("\nTesting ralph_tools...")
    temp_dir = tempfile.mkdtemp()

    # 写入完成标志
    with patch('src.tools.ralph_tools.COMPLETION_PROMISE_FILE', Path(temp_dir) / 'completion_promise'):
        result = write_completion_marker("DONE")
        assert "Completion marker written" in result
        print("✓ write_completion_marker passed")

    # 创建任务文件
    with patch('src.tools.ralph_tools.SEED_DIR', Path(temp_dir)):
        result = create_ralph_task_file("test_task", "# Test Task")
        assert "Task file created" in result
        print("✓ create_ralph_task_file passed")

    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("Ralph Loop Verification Tests")
    print("=" * 50)

    tests = [
        test_completion_types,
        test_marker_file_check,
        test_file_exists_check,
        test_safety_limits,
        test_context_reset,
        test_factory_methods,
        test_tools,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ ERROR: {e}")
            failed += 1

    print("\n" + "=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)