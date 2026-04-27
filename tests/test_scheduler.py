"""
Tests for src/scheduler.py

Coverage targets:
- ScheduledTask class (should_run, mark_run, serialization)
- TaskScheduler (add_task, get_task, remove_task - mocked)
"""

import os
import sys
import pytest
import tempfile
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import scheduler
from scheduler import ScheduledTask, TaskScheduler

# ==================== Fixtures ====================

@pytest.fixture
def mock_tasks_dir():
    """Mock tasks directory and file for TaskScheduler tests."""
    temp_dir = tempfile.mkdtemp()
    tasks_file = os.path.join(temp_dir, 'scheduled_tasks.json')
    
    # Patch global constants
    original_dir = scheduler.TASKS_DIR
    original_file = scheduler.TASKS_FILE
    
    scheduler.TASKS_DIR = Path(temp_dir)
    scheduler.TASKS_FILE = Path(tasks_file)
    
    yield temp_dir
    
    scheduler.TASKS_DIR = original_dir
    scheduler.TASKS_FILE = original_file
    if os.path.exists(temp_dir):
        import shutil
        shutil.rmtree(temp_dir)

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

    def test_should_run_past_interval(self):
        """Task should run if interval passed."""
        task = ScheduledTask(
            task_id="test",
            task_type="test",
            interval_seconds=100,
            prompt="Test",
            last_run=time.time() - 200  # 200s ago
        )
        assert task.should_run() is True

    def test_should_run_disabled(self):
        """Disabled task should not run."""
        task = ScheduledTask(
            task_id="test",
            task_type="test",
            interval_seconds=1,
            prompt="Test",
            last_run=0,
            enabled=False
        )
        assert task.should_run() is False

    def test_mark_run(self):
        """Marking run updates last_run."""
        task = ScheduledTask(
            task_id="test",
            task_type="test",
            interval_seconds=3600,
            prompt="Test",
            last_run=0
        )
        before = time.time()
        task.mark_run()
        after = time.time()
        
        assert task.last_run > 0
        assert task.last_run >= before
        assert task.last_run <= after

    def test_serialization(self):
        """Test to_dict."""
        task = ScheduledTask(
            task_id="test",
            task_type="test",
            interval_seconds=3600,
            prompt="Test",
            last_run=1234567890.0
        )
        data = task.to_dict()
        assert data['task_id'] == "test"
        assert data['last_run'] == 1234567890.0

    def test_deserialization(self):
        """Test from_dict."""
        data = {
            "task_id": "test",
            "task_type": "test",
            "interval_seconds": 3600,
            "prompt": "Test",
            "last_run": 1234567890.0,
            "enabled": False
        }
        task = ScheduledTask.from_dict(data)
        assert task.task_id == "test"
        assert task.enabled is False

    def test_deserialization_defaults(self):
        """Test from_dict with missing optional fields."""
        data = {
            "task_id": "test",
            "task_type": "test",
            "interval_seconds": 3600,
            "prompt": "Test"
        }
        task = ScheduledTask.from_dict(data)
        assert task.last_run == 0
        assert task.enabled is True

# ==================== Tests for TaskScheduler ====================

class TestTaskScheduler:
    def test_add_task(self, mock_tasks_dir):
        """Test adding a task."""
        scheduler_mock = TaskScheduler()
        
        scheduler_mock.add_task("my_task", "custom", 600, "Do something")
        
        assert "my_task" in scheduler_mock._tasks
        assert scheduler_mock._tasks["my_task"].interval_seconds == 600
        assert scheduler_mock._tasks["my_task"].enabled is True

    def test_get_task(self, mock_tasks_dir):
        """Test getting a task."""
        scheduler_mock = TaskScheduler()
        scheduler_mock.add_task("my_task", "custom", 600, "Do something")
        
        task = scheduler_mock.get_task("my_task")
        assert task is not None
        assert task.task_id == "my_task"

    def test_get_task_missing(self, mock_tasks_dir):
        """Test getting a non-existent task."""
        scheduler_mock = TaskScheduler()
        task = scheduler_mock.get_task("missing_task")
        assert task is None

    def test_remove_task(self, mock_tasks_dir):
        """Test removing a task."""
        scheduler_mock = TaskScheduler()
        scheduler_mock.add_task("my_task", "custom", 600, "Do something")
        
        scheduler_mock.remove_task("my_task")
        
        assert "my_task" not in scheduler_mock._tasks

    def test_add_task_duplicate(self, mock_tasks_dir):
        """Test adding a duplicate task updates it."""
        scheduler_mock = TaskScheduler()
        
        scheduler_mock.add_task("my_task", "custom", 600, "Do something")
        scheduler_mock.add_task("my_task", "custom", 300, "Do something else")
        
        assert scheduler_mock._tasks["my_task"].interval_seconds == 300
        assert scheduler_mock._tasks["my_task"].prompt == "Do something else"

    def test_save_tasks(self, mock_tasks_dir):
        """Test saving tasks to file."""
        scheduler_mock = TaskScheduler()
        scheduler_mock.add_task("my_task", "custom", 600, "Do something")
        
        scheduler_mock._save_tasks()
        
        tasks_file = scheduler.TASKS_FILE
        assert tasks_file.exists()
        
        with open(tasks_file, 'r') as f:
            data = json.load(f)
        
        assert len(data) == 1
        assert data[0]['task_id'] == "my_task"

    def test_load_tasks(self, mock_tasks_dir):
        """Test loading tasks from file."""
        tasks_file = scheduler.TASKS_FILE
        data = [{
            "task_id": "saved_task",
            "task_type": "custom",
            "interval_seconds": 123,
            "prompt": "Saved prompt",
            "last_run": 0,
            "enabled": True
        }]
        
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
        
        tasks = scheduler_mock.list_tasks()
        assert len(tasks) == 2
        assert tasks[0]['task_id'] == "task_1"

    def test_enable_disable_task(self, mock_tasks_dir):
        """Test enabling/disabling tasks."""
        scheduler_mock = TaskScheduler()
        scheduler_mock.add_task("my_task", "custom", 600, "Do something")
        
        scheduler_mock.disable_task("my_task")
        assert scheduler_mock._tasks["my_task"].enabled is False
        
        scheduler_mock.enable_task("my_task")
        assert scheduler_mock._tasks["my_task"].enabled is True
