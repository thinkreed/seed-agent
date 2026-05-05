"""
Tests for src/scheduler.py

Coverage targets:
- ScheduledTask class (should_run, mark_run, serialization)
- TaskScheduler (add_task, get_task, remove_task - mocked)

路径配置已迁移到动态函数，测试使用 mock 路径函数替代。
"""

import os
import sys
import pytest
import tempfile
import json
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import scheduler
from scheduler import ScheduledTask, TaskScheduler

# ==================== Fixtures ====================

@pytest.fixture
def mock_tasks_dir(monkeypatch):
    """Mock tasks directory and file for TaskScheduler tests using override mechanism."""
    temp_dir = tempfile.mkdtemp()
    tasks_file = Path(temp_dir) / 'scheduled_tasks.json'

    # Use the override mechanism instead of monkeypatch for functions
    import scheduler._storage
    scheduler._storage._set_tasks_dir_override(Path(temp_dir))

    yield temp_dir

    # Reset override after test
    scheduler._storage._set_tasks_dir_override(None)

# ==================== Tests for ScheduledTask ====================

class TestScheduledTask:
    def test_init(self):
        """Test task initialization."""
        task = ScheduledTask(
            task_id="test_1",
            task_type="autodream",
            interval_seconds=3600,
            prompt="Test prompt"
        )
        assert task.task_id == "test_1"
        assert task.interval_seconds == 3600
        assert task.enabled is True
        assert task.last_run == 0

    def test_should_run_initial(self):
        """Task should run immediately after creation (last_run=0)."""
        task = ScheduledTask(
            task_id="test",
            task_type="test",
            interval_seconds=3600,
            prompt="Test"
        )
        assert task.should_run() is True

    def test_should_run_after_interval(self):
        """Task should not run before interval."""
        task = ScheduledTask(
            task_id="test",
            task_type="test",
            interval_seconds=3600,
            prompt="Test",
            last_run=time.time() - 100  # 100s ago
        )
        assert task.should_run() is False

    def test_should_run_after_interval_passed(self):
        """Task should run after interval has passed."""
        task = ScheduledTask(
            task_id="test",
            task_type="test",
            interval_seconds=3600,
            prompt="Test",
            last_run=time.time() - 4000  # More than 1 hour ago
        )
        assert task.should_run() is True

    def test_mark_run(self):
        """Test mark_run updates last_run."""
        task = ScheduledTask(
            task_id="test",
            task_type="test",
            interval_seconds=3600,
            prompt="Test"
        )
        before = task.last_run
        task.mark_run()
        assert task.last_run > before

    def test_to_dict(self):
        """Test serialization to dict."""
        task = ScheduledTask(
            task_id="test",
            task_type="custom",
            interval_seconds=123,
            prompt="Test prompt",
            last_run=100,
            enabled=True
        )
        data = task.to_dict()
        assert data["task_id"] == "test"
        assert data["task_type"] == "custom"
        assert data["interval_seconds"] == 123
        assert data["prompt"] == "Test prompt"
        assert data["last_run"] == 100
        assert data["enabled"] is True

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "task_id": "test",
            "task_type": "custom",
            "interval_seconds": 123,
            "prompt": "Test prompt",
            "last_run": 100,
            "enabled": False
        }
        task = ScheduledTask.from_dict(data)
        assert task.task_id == "test"
        assert task.task_type == "custom"
        assert task.interval_seconds == 123
        assert task.prompt == "Test prompt"
        assert task.last_run == 100
        assert task.enabled is False

    def test_serialization_roundtrip(self):
        """Test serialization roundtrip."""
        original = ScheduledTask(
            task_id="test",
            task_type="custom",
            interval_seconds=123,
            prompt="Test prompt",
            last_run=time.time(),
            enabled=True
        )
        data = original.to_dict()
        restored = ScheduledTask.from_dict(data)
        assert restored.task_id == original.task_id
        assert restored.task_type == original.task_type
        assert restored.interval_seconds == original.interval_seconds
        assert restored.prompt == original.prompt
        assert restored.last_run == original.last_run
        assert restored.enabled == original.enabled


# ==================== Tests for TaskScheduler ====================

class TestTaskScheduler:
    def test_add_task(self, mock_tasks_dir):
        """Test adding a new task."""
        scheduler_mock = TaskScheduler()

        result = scheduler_mock.add_task("my_task", "custom", 600, "Do something")

        assert "my_task" in scheduler_mock._tasks
        assert scheduler_mock._tasks["my_task"].interval_seconds == 600
        assert scheduler_mock._tasks["my_task"].prompt == "Do something"
        assert "已添加" in result or "added" in result.lower()

    def test_add_task_duplicate(self, mock_tasks_dir):
        """Test adding a duplicate task returns error."""
        scheduler_mock = TaskScheduler()

        scheduler_mock.add_task("my_task", "custom", 600, "Do something")
        result2 = scheduler_mock.add_task("my_task", "custom", 300, "Do something else")

        # Should not update, should return error message
        assert "already exists" in result2
        assert scheduler_mock._tasks["my_task"].interval_seconds == 600
        assert scheduler_mock._tasks["my_task"].prompt == "Do something"

    def test_save_tasks(self, mock_tasks_dir):
        """Test saving tasks to file."""
        scheduler_mock = TaskScheduler()
        # Add a new task
        scheduler_mock.add_task("my_task", "custom", 600, "Do something")

        scheduler_mock._save_tasks()

        tasks_file = scheduler._get_tasks_file()
        assert tasks_file.exists()

        with open(tasks_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Should contain builtin tasks + my_task
        task_ids = [t['task_id'] for t in data['tasks']]
        assert "my_task" in task_ids
        # Builtins should also be present
        assert "autodream" in task_ids

    def test_load_tasks(self, mock_tasks_dir):
        """Test loading tasks from file."""
        tasks_file = scheduler._get_tasks_file()
        # Data must be wrapped in {"tasks": [...]}
        data = {
            "tasks": [{
                "task_id": "saved_task",
                "task_type": "custom",
                "interval_seconds": 123,
                "prompt": "Saved prompt",
                "last_run": 0,
                "enabled": True
            }]
        }

        with open(tasks_file, 'w') as f:
            json.dump(data, f)

        # Re-initialize to load tasks
        scheduler_mock = TaskScheduler()

        assert "saved_task" in scheduler_mock._tasks
        assert scheduler_mock._tasks["saved_task"].prompt == "Saved prompt"

    def test_list_tasks(self, mock_tasks_dir):
        """Test listing tasks."""
        scheduler_mock = TaskScheduler()
        scheduler_mock.add_task("task_1", "type1", 100, "p1")
        scheduler_mock.add_task("task_2", "type2", 200, "p2")

        tasks_list = scheduler_mock.list_tasks()
        # list_tasks returns a formatted string, check if tasks are present
        assert "task_1" in tasks_list
        assert "task_2" in tasks_list

    def test_enable_disable_task(self, mock_tasks_dir):
        """Test enabling/disabling tasks."""
        scheduler_mock = TaskScheduler()
        scheduler_mock.add_task("my_task", "custom", 600, "Do something")

        scheduler_mock.disable_task("my_task")
        assert scheduler_mock._tasks["my_task"].enabled is False

        scheduler_mock.enable_task("my_task")
        assert scheduler_mock._tasks["my_task"].enabled is True

    def test_remove_task(self, mock_tasks_dir):
        """Test removing a task."""
        scheduler_mock = TaskScheduler()
        scheduler_mock.add_task("to_remove", "custom", 600, "Remove me")

        assert "to_remove" in scheduler_mock._tasks
        scheduler_mock.remove_task("to_remove")
        assert "to_remove" not in scheduler_mock._tasks

    def test_remove_nonexistent_task(self, mock_tasks_dir):
        """Test removing a nonexistent task."""
        scheduler_mock = TaskScheduler()
        result = scheduler_mock.remove_task("nonexistent")
        assert "not found" in result or "不存在" in result

    def test_get_task(self, mock_tasks_dir):
        """Test getting a specific task."""
        scheduler_mock = TaskScheduler()
        scheduler_mock.add_task("my_task", "custom", 600, "Do something")

        task = scheduler_mock.get_task("my_task")
        assert task is not None
        assert task.task_id == "my_task"
        assert task.interval_seconds == 600

    def test_get_nonexistent_task(self, mock_tasks_dir):
        """Test getting a nonexistent task."""
        scheduler_mock = TaskScheduler()
        task = scheduler_mock.get_task("nonexistent")
        assert task is None


# ==================== Tests for Edge Cases ====================

class TestTaskSchedulerEdgeCases:
    def test_empty_tasks_file(self, mock_tasks_dir):
        """Test handling empty tasks file."""
        tasks_file = scheduler._get_tasks_file()
        # Create empty file
        tasks_file.parent.mkdir(parents=True, exist_ok=True)
        with open(tasks_file, 'w') as f:
            json.dump({}, f)

        scheduler_mock = TaskScheduler()
        # Should have builtin task only
        assert "autodream" in scheduler_mock._tasks

    def test_corrupted_tasks_file(self, mock_tasks_dir):
        """Test handling corrupted tasks file."""
        tasks_file = scheduler._get_tasks_file()
        tasks_file.parent.mkdir(parents=True, exist_ok=True)
        with open(tasks_file, 'w') as f:
            f.write("not valid json")

        scheduler_mock = TaskScheduler()
        # Should start fresh with builtin task
        assert "autodream" in scheduler_mock._tasks

    def test_multiple_task_types(self, mock_tasks_dir):
        """Test handling multiple task types."""
        scheduler_mock = TaskScheduler()
        scheduler_mock.add_task("autodream_custom", "custom", 600, "Custom autodream")

        assert "autodream_custom" in scheduler_mock._tasks
        assert scheduler_mock._tasks["autodream_custom"].task_type == "custom"