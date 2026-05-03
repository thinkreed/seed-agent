"""
background_task_registry.py 单元测试

测试：
- BackgroundTaskEntry: 任务条目
- BackgroundTaskRegistry: 任务注册表
- 任务生命周期管理
- 取消机制
"""

import asyncio
import sys
import unittest
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from background_task_registry import (
    BackgroundTaskEntry,
    BackgroundTaskRegistry,
    TaskStatus,
    get_background_task_registry,
    init_background_task_registry,
    reset_background_task_registry,
)


class TestBackgroundTaskEntry(unittest.TestCase):
    """测试 BackgroundTaskEntry"""

    def test_basic_entry(self):
        """基本条目"""
        from abort_signal import AbortController

        entry = BackgroundTaskEntry(
            task_id="test_1",
            prompt="Test task",
            status=TaskStatus.PENDING,
            abort_controller=AbortController()
        )

        self.assertEqual(entry.task_id, "test_1")
        self.assertEqual(entry.prompt, "Test task")
        self.assertEqual(entry.status, TaskStatus.PENDING)
        self.assertFalse(entry.abort_controller.signal.aborted)

    def test_to_dict(self):
        """转换为字典"""
        from abort_signal import AbortController

        entry = BackgroundTaskEntry(
            task_id="test_1",
            prompt="Test task",
            status=TaskStatus.RUNNING,
            abort_controller=AbortController()
        )
        d = entry.to_dict()

        self.assertEqual(d["task_id"], "test_1")
        self.assertEqual(d["status"], "running")

    def test_long_prompt_truncated(self):
        """长提示截断"""
        from abort_signal import AbortController

        long_prompt = "x" * 150  # 150 个字符
        entry = BackgroundTaskEntry(
            task_id="test_1",
            prompt=long_prompt,
            status=TaskStatus.PENDING,
            abort_controller=AbortController()
        )
        d = entry.to_dict()

        # to_dict 截断到 100 字符 + "..."
        self.assertTrue(len(d["prompt"]) <= 103)  # 100 + "..."
        self.assertTrue(d["prompt"].endswith("..."))


class TestBackgroundTaskRegistry(unittest.TestCase):
    """测试 BackgroundTaskRegistry"""

    def setUp(self):
        """每个测试前重置"""
        reset_background_task_registry()
        self.registry = BackgroundTaskRegistry()

    def test_register_task(self):
        """注册任务"""
        entry = self.registry.register("task_1", "Test prompt")

        self.assertEqual(entry.task_id, "task_1")
        self.assertEqual(entry.status, TaskStatus.PENDING)

    def test_start_task(self):
        """启动任务"""
        self.registry.register("task_1", "Test")
        success = self.registry.start("task_1")

        self.assertTrue(success)
        self.assertEqual(self.registry.get_status("task_1"), TaskStatus.RUNNING)

    def test_complete_task(self):
        """完成任务"""
        self.registry.register("task_1", "Test")
        self.registry.start("task_1")
        success = self.registry.complete("task_1", "Done")

        self.assertTrue(success)
        self.assertEqual(self.registry.get_status("task_1"), TaskStatus.COMPLETED)

    def test_fail_task(self):
        """失败任务"""
        self.registry.register("task_1", "Test")
        self.registry.start("task_1")
        success = self.registry.fail("task_1", "Error occurred")

        self.assertTrue(success)
        self.assertEqual(self.registry.get_status("task_1"), TaskStatus.FAILED)

    def test_cancel_pending_task(self):
        """取消待执行任务"""
        self.registry.register("task_1", "Test")
        success = self.registry.cancel("task_1")

        # 待执行任务直接取消
        self.assertFalse(success)  # 不是 RUNNING 状态
        self.assertEqual(self.registry.get_status("task_1"), TaskStatus.CANCELLED)

    def test_cancel_running_task(self):
        """取消运行中任务"""
        async def test():
            registry = BackgroundTaskRegistry()
            registry.register("task_1", "Test")
            registry.start("task_1")
            success = registry.cancel("task_1")

            self.assertTrue(success)
            # 发送了取消信号，状态可能在优雅期内
            entry = registry.get_entry("task_1")
            self.assertTrue(entry.abort_controller.signal.aborted)

        asyncio.run(test())

    def test_cancel_all(self):
        """取消所有任务"""
        # cancel_all 返回 RUNNING 任务取消数，PENDING 任务直接标记取消不计入返回值
        self.registry.register("task_1", "Test 1")
        self.registry.register("task_2", "Test 2")

        count = self.registry.cancel_all()

        # PENDING 任务直接标记取消，但不计入返回值（返回值只计 RUNNING 任务）
        self.assertEqual(count, 0)
        # 验证 PENDING 任务确实被标记为 CANCELLED
        self.assertEqual(self.registry.get_status("task_1"), TaskStatus.CANCELLED)
        self.assertEqual(self.registry.get_status("task_2"), TaskStatus.CANCELLED)

    def test_get_stats(self):
        """获取统计"""
        self.registry.register("task_1", "Test 1")
        self.registry.register("task_2", "Test 2")
        self.registry.start("task_1")
        self.registry.complete("task_1", "Done")

        stats = self.registry.get_stats()

        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["pending"], 1)

    def test_list_tasks(self):
        """列出任务"""
        self.registry.register("task_1", "Test 1")
        self.registry.register("task_2", "Test 2")
        self.registry.start("task_1")

        tasks = self.registry.list_tasks()

        self.assertEqual(len(tasks), 2)

    def test_list_tasks_with_filter(self):
        """按状态过滤"""
        self.registry.register("task_1", "Test 1")
        self.registry.register("task_2", "Test 2")
        self.registry.start("task_1")

        tasks = self.registry.list_tasks(status=TaskStatus.RUNNING)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_id"], "task_1")

    def test_cleanup(self):
        """清理任务"""
        self.registry.register("task_1", "Test 1")
        self.registry.register("task_2", "Test 2")
        self.registry.start("task_1")
        self.registry.complete("task_1", "Done")
        self.registry.fail("task_2", "Error")

        count = self.registry.cleanup()

        self.assertEqual(count, 2)
        self.assertEqual(len(self.registry.list_tasks()), 0)

    def test_max_concurrent(self):
        """最大并发数"""
        registry = BackgroundTaskRegistry(max_concurrent=2)

        registry.register("task_1", "Test 1")
        registry.register("task_2", "Test 2")
        registry.start("task_1")
        registry.start("task_2")

        self.assertTrue(registry.can_start_new() == False)

        registry.register("task_3", "Test 3")
        self.assertFalse(registry.can_start_new())


class TestGracePeriod(unittest.TestCase):
    """测试优雅期"""

    def test_grace_period_force_cancel(self):
        """优雅期后强制取消"""
        async def test():
            registry = BackgroundTaskRegistry()
            registry.register("task_1", "Test")
            registry.start("task_1")
            registry.cancel("task_1")

            # 等待优雅期结束
            await asyncio.sleep(6)  # 超过 CANCEL_GRACE_SECONDS

            status = registry.get_status("task_1")
            self.assertEqual(status, TaskStatus.CANCELLED)

        asyncio.run(test())


class TestGlobalRegistry(unittest.TestCase):
    """测试全局注册表"""

    def test_get_global_registry(self):
        """获取全局注册表"""
        reset_background_task_registry()
        registry = get_background_task_registry()

        self.assertIsInstance(registry, BackgroundTaskRegistry)

    def test_init_with_max_concurrent(self):
        """初始化带最大并发数"""
        registry = init_background_task_registry(max_concurrent=5)

        self.assertEqual(registry._max_concurrent, 5)


if __name__ == '__main__':
    unittest.main()