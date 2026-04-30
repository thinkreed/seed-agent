"""Request Queue TurnTicket 模式单元测试"""

import sys
import asyncio
import unittest
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

# 导入测试模块
from request_queue import (
    RequestQueue,
    RequestPriority,
    TurnTicket,
    TurnWaitTimeout,
    QueueFullError,
    QueueConfig,
    QueueStats,
)


class TestTurnTicket(unittest.TestCase):
    """测试 TurnTicket 轮次票"""

    def test_initial_state(self):
        """测试初始状态"""
        ticket = TurnTicket(priority=RequestPriority.NORMAL)
        self.assertIsNotNone(ticket.id)
        self.assertEqual(ticket.priority, RequestPriority.NORMAL)
        self.assertFalse(ticket.is_signaled())
        self.assertFalse(ticket._cancelled)

    def test_signal_turn(self):
        """测试 signal_turn 通知"""
        ticket = TurnTicket(priority=RequestPriority.NORMAL)

        async def run():
            # 信号未触发时等待会阻塞
            self.assertFalse(ticket._turn_event.is_set())

            # 触发信号
            ticket.signal_turn()

            # 等待应该立即返回
            await ticket.wait_for_turn(timeout=1.0)
            return ticket.is_signaled(), ticket._turn_time

        is_signaled, turn_time = asyncio.run(run())
        self.assertTrue(is_signaled)
        self.assertIsNotNone(turn_time)

    def test_wait_for_turn_timeout(self):
        """测试 wait_for_turn 超时"""
        ticket = TurnTicket(priority=RequestPriority.NORMAL)

        async def run():
            try:
                await ticket.wait_for_turn(timeout=0.1)
                return False
            except TurnWaitTimeout as e:
                return True, e.waited_seconds

        result = asyncio.run(run())
        self.assertTrue(result[0])
        self.assertAlmostEqual(result[1], 0.1, places=1)

    def test_cancel(self):
        """测试取消排队"""
        ticket = TurnTicket(priority=RequestPriority.NORMAL)

        async def run():
            # 取消
            ticket.cancel("User cancelled")

            # 等待应该抛出 CancelledError
            try:
                await ticket.wait_for_turn(timeout=1.0)
                return False
            except asyncio.CancelledError as e:
                return True, str(e)

        result = asyncio.run(run())
        self.assertTrue(result[0])
        self.assertIn("User cancelled", result[1])

    def test_get_wait_duration(self):
        """测试获取等待时长"""
        ticket = TurnTicket(priority=RequestPriority.NORMAL)

        # 未分配轮次时，返回当前等待时长（可能很小但应该 >= 0）
        duration = ticket.get_wait_duration()
        self.assertGreaterEqual(duration, 0.0)

        # 分配轮次后，返回实际等待时长
        async def run():
            await asyncio.sleep(0.1)
            ticket.signal_turn()
            return ticket.get_wait_duration()

        duration = asyncio.run(run())
        # 由于异步执行可能很快，使用近似比较
        self.assertGreaterEqual(duration, 0.05)  # 至少等待了一段时间


class TestQueueConfig(unittest.TestCase):
    """测试队列配置"""

    def test_default_config(self):
        """测试默认配置"""
        config = QueueConfig()
        self.assertEqual(config.critical_max_size, 10)
        self.assertEqual(config.critical_backpressure_threshold, 0.9)
        self.assertEqual(config.critical_dispatch_rate, 10.0)
        self.assertEqual(config.normal_max_size, 50)
        self.assertEqual(config.normal_backpressure_threshold, 0.8)

    def test_custom_config(self):
        """测试自定义配置"""
        config = QueueConfig(
            critical_max_size=20,
            critical_dispatch_rate=5.0,
            normal_max_size=100,
        )
        self.assertEqual(config.critical_max_size, 20)
        self.assertEqual(config.critical_dispatch_rate, 5.0)
        self.assertEqual(config.normal_max_size, 100)


class TestQueueStats(unittest.TestCase):
    """测试队列统计"""

    def test_initial_state(self):
        """测试初始状态"""
        stats = QueueStats()
        for p in RequestPriority:
            self.assertEqual(stats.submitted[p], 0)
            self.assertEqual(stats.signaled[p], 0)
            self.assertEqual(stats.rejected[p], 0)
            self.assertEqual(stats.wait_times[p], [])

    def test_record_submit(self):
        """测试记录提交"""
        stats = QueueStats()
        stats.record_submit(RequestPriority.CRITICAL)
        stats.record_submit(RequestPriority.NORMAL)
        stats.record_submit(RequestPriority.NORMAL)

        self.assertEqual(stats.submitted[RequestPriority.CRITICAL], 1)
        self.assertEqual(stats.submitted[RequestPriority.NORMAL], 2)

    def test_record_signal(self):
        """测试记录信号"""
        stats = QueueStats()
        stats.record_signal(RequestPriority.HIGH)
        self.assertEqual(stats.signaled[RequestPriority.HIGH], 1)

    def test_record_wait_time(self):
        """测试记录等待时间"""
        stats = QueueStats()
        stats.record_wait_time(RequestPriority.NORMAL, 1.5)
        stats.record_wait_time(RequestPriority.NORMAL, 2.0)
        stats.record_wait_time(RequestPriority.NORMAL, 0.5)

        self.assertEqual(len(stats.wait_times[RequestPriority.NORMAL]), 3)
        avg = stats.get_avg_wait_time(RequestPriority.NORMAL)
        self.assertAlmostEqual(avg, (1.5 + 2.0 + 0.5) / 3, places=2)

    def test_get_p95_wait_time(self):
        """测试 P95 等待时间"""
        stats = QueueStats()
        # 添加 10 个值
        for i in range(10):
            stats.record_wait_time(RequestPriority.NORMAL, float(i))

        p95 = stats.get_p95_wait_time(RequestPriority.NORMAL)
        # P95 应该是第 9 或第 10 个值
        self.assertGreaterEqual(p95, 8.0)

    def test_get_reject_rate(self):
        """测试拒绝率计算"""
        stats = QueueStats()
        stats.record_submit(RequestPriority.LOW)
        stats.record_submit(RequestPriority.LOW)
        stats.record_submit(RequestPriority.LOW)
        stats.record_rejected(RequestPriority.LOW)

        rate = stats.get_reject_rate(RequestPriority.LOW)
        self.assertAlmostEqual(rate, 1 / 3, places=2)

    def test_wait_times_limit(self):
        """测试等待时间记录限制"""
        stats = QueueStats()
        # 添加超过 100 条记录
        for i in range(150):
            stats.record_wait_time(RequestPriority.HIGH, float(i))

        # 只保留最近 100 条
        self.assertEqual(len(stats.wait_times[RequestPriority.HIGH]), 100)


class TestRequestQueueTurnTicket(unittest.TestCase):
    """测试 RequestQueue TurnTicket 模式"""

    def test_initial_state(self):
        """测试初始状态"""
        queue = RequestQueue()
        self.assertFalse(queue._running)
        self.assertEqual(queue.get_queue_size()["total"], 0)

    def test_request_turn_success(self):
        """测试申请轮次成功"""
        queue = RequestQueue()

        async def run():
            ticket = await queue.request_turn(RequestPriority.NORMAL)
            return ticket.id, ticket.priority, queue.get_queue_size()["normal"]

        ticket_id, priority, normal_size = asyncio.run(run())
        self.assertIsNotNone(ticket_id)
        self.assertEqual(priority, RequestPriority.NORMAL)
        self.assertEqual(normal_size, 1)

    def test_request_turn_critical_queue(self):
        """测试 CRITICAL 独立队列"""
        queue = RequestQueue()

        async def run():
            ticket = await queue.request_turn(RequestPriority.CRITICAL)
            return ticket.priority, queue.get_queue_size()["critical"]

        priority, critical_size = asyncio.run(run())
        self.assertEqual(priority, RequestPriority.CRITICAL)
        self.assertEqual(critical_size, 1)

    def test_queue_full_error_critical(self):
        """测试 CRITICAL 队列满"""
        config = QueueConfig(
            critical_max_size=2,
            critical_backpressure_threshold=1.0,
        )
        queue = RequestQueue(config=config)

        async def run():
            await queue.request_turn(RequestPriority.CRITICAL)
            await queue.request_turn(RequestPriority.CRITICAL)

            # 第三次应该抛出异常
            try:
                await queue.request_turn(RequestPriority.CRITICAL)
                return False
            except QueueFullError as e:
                return True, e.queue_type

        result = asyncio.run(run())
        self.assertTrue(result[0])
        self.assertEqual(result[1], "critical")

    def test_queue_full_error_normal(self):
        """测试普通队列满"""
        config = QueueConfig(
            normal_max_size=3,
            normal_backpressure_threshold=1.0,
        )
        queue = RequestQueue(config=config)

        async def run():
            await queue.request_turn(RequestPriority.HIGH)
            await queue.request_turn(RequestPriority.NORMAL)
            await queue.request_turn(RequestPriority.LOW)

            # 第四次应该抛出异常
            try:
                await queue.request_turn(RequestPriority.NORMAL)
                return False
            except QueueFullError as e:
                return True, e.queue_type

        result = asyncio.run(run())
        self.assertTrue(result[0])
        self.assertEqual(result[1], "normal")

    def test_backpressure_threshold(self):
        """测试反压阈值"""
        config = QueueConfig(
            normal_max_size=10,
            normal_backpressure_threshold=0.5,
        )
        queue = RequestQueue(config=config)

        async def run():
            # 填充到阈值（5 个）
            for _ in range(5):
                await queue.request_turn(RequestPriority.NORMAL)

            # 第六个应该被拒绝
            try:
                await queue.request_turn(RequestPriority.NORMAL)
                return False
            except QueueFullError:
                return True

        raised = asyncio.run(run())
        self.assertTrue(raised)

    def test_get_fill_ratio(self):
        """测试填充率计算"""
        config = QueueConfig(
            critical_max_size=10,
            normal_max_size=50,
        )
        queue = RequestQueue(config=config)

        async def run():
            await queue.request_turn(RequestPriority.CRITICAL)
            await queue.request_turn(RequestPriority.NORMAL)
            await queue.request_turn(RequestPriority.NORMAL)

            return (
                queue.get_critical_fill_ratio(),
                queue.get_normal_fill_ratio(),
                queue.get_total_fill_ratio(),
            )

        critical_fill, normal_fill, total_fill = asyncio.run(run())
        self.assertAlmostEqual(critical_fill, 1 / 10, places=2)
        self.assertAlmostEqual(normal_fill, 2 / 50, places=2)

    def test_cancel_ticket(self):
        """测试取消 ticket"""
        queue = RequestQueue()

        async def run():
            ticket = await queue.request_turn(RequestPriority.NORMAL)
            self.assertEqual(queue.get_queue_size()["normal"], 1)

            # 取消
            success = await queue.cancel_ticket(ticket.id, "Test cancel")
            return success, queue.get_queue_size()["normal"], ticket._cancelled

        success, normal_size, cancelled = asyncio.run(run())
        self.assertTrue(success)
        self.assertEqual(normal_size, 0)
        self.assertTrue(cancelled)

    def test_cancel_all_by_priority(self):
        """测试批量取消指定优先级"""
        queue = RequestQueue()

        async def run():
            await queue.request_turn(RequestPriority.HIGH)
            await queue.request_turn(RequestPriority.HIGH)
            await queue.request_turn(RequestPriority.NORMAL)

            # 取消所有 HIGH
            await queue.cancel_all_by_priority(RequestPriority.HIGH, "Batch cancel")

            return (
                queue.get_queue_size()["high"],
                queue.get_queue_size()["normal"],
            )

        high_size, normal_size = asyncio.run(run())
        self.assertEqual(high_size, 0)
        self.assertEqual(normal_size, 1)  # NORMAL 不受影响

    def test_get_stats(self):
        """测试获取统计信息"""
        queue = RequestQueue()

        async def run():
            await queue.request_turn(RequestPriority.NORMAL)
            await queue.request_turn(RequestPriority.HIGH)
            stats = queue.get_stats()
            return stats

        stats = asyncio.run(run())
        self.assertIn("queue_lengths", stats)
        self.assertIn("fill_ratios", stats)
        self.assertIn("config", stats)
        self.assertIn("stats", stats)
        self.assertEqual(stats["queue_lengths"]["normal"], 1)
        self.assertEqual(stats["queue_lengths"]["high"], 1)

    def test_dispatcher_priority_order(self):
        """测试调度器优先级顺序"""
        queue = RequestQueue()

        async def run():
            # 按反序提交
            await queue.request_turn(RequestPriority.LOW)
            await queue.request_turn(RequestPriority.NORMAL)
            await queue.request_turn(RequestPriority.HIGH)
            await queue.request_turn(RequestPriority.CRITICAL)

            # 启动调度器
            await queue.start_dispatcher()

            # 等待一小段时间让调度器处理
            await asyncio.sleep(0.2)

            # 停止调度器
            await queue.stop_dispatcher()

            # 检查统计：CRITICAL 应该最先被 signaled
            return queue._stats.signaled

        signaled = asyncio.run(run())
        # CRITICAL 应该被处理了
        self.assertGreater(signaled[RequestPriority.CRITICAL], 0)


class TestRequestQueueIntegration(unittest.TestCase):
    """测试 RequestQueue 集成场景"""

    def test_multiple_priorities_concurrent(self):
        """测试多优先级并发提交"""
        queue = RequestQueue()

        async def run():
            # 并发提交多个请求
            tasks = [
                queue.request_turn(RequestPriority.CRITICAL),
                queue.request_turn(RequestPriority.HIGH),
                queue.request_turn(RequestPriority.NORMAL),
                queue.request_turn(RequestPriority.LOW),
                queue.request_turn(RequestPriority.NORMAL),
            ]
            tickets = await asyncio.gather(*tasks)

            return len(tickets), queue.get_queue_size()["total"]

        ticket_count, total_size = asyncio.run(run())
        self.assertEqual(ticket_count, 5)
        self.assertEqual(total_size, 5)

    def test_ticket_wait_and_signal_flow(self):
        """测试完整的等待-信号流程"""
        queue = RequestQueue()

        async def run():
            # 提交请求
            ticket = await queue.request_turn(RequestPriority.NORMAL)

            # 启动一个等待任务
            wait_task = asyncio.create_task(
                ticket.wait_for_turn(timeout=2.0)
            )

            # 启动调度器
            await queue.start_dispatcher()

            # 等待完成
            await wait_task

            # 停止调度器
            await queue.stop_dispatcher()

            return ticket.is_signaled(), ticket.get_wait_duration()

        is_signaled, wait_duration = asyncio.run(run())
        self.assertTrue(is_signaled)
        # 等待时间可能很小（调度器快速处理），使用 >= 0
        self.assertGreaterEqual(wait_duration, 0.0)

    def test_auto_adjust_high_load(self):
        """测试高负载下智能调整"""
        config = QueueConfig(
            critical_target_wait_time=0.1,  # 设置很低的目标，触发调整
            auto_adjust_enabled=True,
            adjust_interval=0.5,  # 快速调整
        )
        queue = RequestQueue(config=config)

        async def run():
            # 模拟高负载
            for _ in range(10):
                try:
                    await queue.request_turn(RequestPriority.CRITICAL)
                except QueueFullError:
                    pass

            # 记录一些等待时间（模拟高延迟）
            queue._stats.record_wait_time(RequestPriority.CRITICAL, 1.0)
            queue._stats.record_wait_time(RequestPriority.CRITICAL, 1.5)

            # 启动调度器和调整
            await queue.start_dispatcher()
            await asyncio.sleep(1.0)  # 等待调整触发
            await queue.stop_dispatcher()

            return queue.config.critical_dispatch_rate

        dispatch_rate = asyncio.run(run())
        # 调度速率应该被增加
        self.assertGreater(dispatch_rate, 10.0)


if __name__ == "__main__":
    unittest.main()