"""LLM 请求限流系统单元测试"""

import sys
import asyncio
import time
import tempfile
import unittest
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

# 导入测试模块
from rate_limiter import (  # noqa: E402
    TokenBucket,
    RollingWindowTracker,
    RateLimiter,
    RateLimitStatus,
)
from request_queue import (  # noqa: E402
    RequestQueue,
    RequestPriority,
    QueueFullError,
    QueueConfig,
)
from rate_limit_db import (  # noqa: E402
    RateLimitSQLite,
    RateLimitState,
)
from models import RateLimitConfig  # noqa: E402


class TestTokenBucket(unittest.TestCase):
    """测试 Token Bucket 限流器"""

    def test_initial_state(self):
        """测试初始状态：满载"""
        bucket = TokenBucket(rate=1.0, capacity=10.0)
        self.assertEqual(bucket.tokens, 10.0)
        self.assertEqual(bucket.rate, 1.0)
        self.assertEqual(bucket.capacity, 10.0)

    def test_acquire_success(self):
        """测试获取 token 成功"""
        bucket = TokenBucket(rate=1.0, capacity=10.0)

        async def run():
            allowed, wait_time = await bucket.acquire()
            return allowed, wait_time

        allowed, wait_time = asyncio.run(run())
        self.assertTrue(allowed)
        self.assertEqual(wait_time, 0.0)
        self.assertEqual(bucket.tokens, 9.0)

    def test_acquire_multiple_tokens(self):
        """测试连续获取多个 token"""
        bucket = TokenBucket(rate=1.0, capacity=5.0)

        async def run():
            results = []
            for _ in range(5):
                allowed, wait_time = await bucket.acquire()
                results.append((allowed, wait_time))
            return results

        results = asyncio.run(run())
        # 前 5 次应该成功
        for allowed, wait_time in results:
            self.assertTrue(allowed)
            self.assertEqual(wait_time, 0.0)

        # 现在 token 应该接近 0（浮点精度问题）
        self.assertAlmostEqual(bucket.tokens, 0.0, places=2)

    def test_acquire_when_empty(self):
        """测试 token 耗尽时获取"""
        bucket = TokenBucket(rate=1.0, capacity=1.0)

        async def run():
            # 先用掉唯一的 token
            await bucket.acquire()
            # 再次尝试获取
            allowed, wait_time = await bucket.acquire()
            return allowed, wait_time

        allowed, wait_time = asyncio.run(run())
        self.assertFalse(allowed)
        self.assertAlmostEqual(wait_time, 1.0, places=1)

    def test_token_refill(self):
        """测试 token 自动补充"""
        bucket = TokenBucket(rate=10.0, capacity=10.0, initial_tokens=0.0)

        async def run():
            # 等待 0.5 秒，应该补充约 5 个 token
            await asyncio.sleep(0.5)
            allowed, wait_time = await bucket.acquire()
            return allowed, bucket.tokens

        allowed, tokens = asyncio.run(run())
        self.assertTrue(allowed)
        # 补充了约 5 个，用了 1 个，剩余约 4 个（允许一定误差）
        self.assertGreater(tokens, 3.5)
        self.assertLess(tokens, 5.5)

    def test_state_persistence(self):
        """测试状态持久化"""
        bucket = TokenBucket(rate=1.0, capacity=10.0, initial_tokens=5.0)

        # 获取状态
        state = bucket.get_state()
        self.assertEqual(state.tokens, 5.0)

        # 创建新 bucket 并恢复状态
        new_bucket = TokenBucket(rate=1.0, capacity=10.0)
        new_bucket.restore_state(state)
        self.assertEqual(new_bucket.tokens, 5.0)


class TestRollingWindowTracker(unittest.TestCase):
    """测试滚动窗口追踪器"""

    def test_initial_state(self):
        """测试初始状态"""
        tracker = RollingWindowTracker(window_limit=100, window_duration=60.0)
        self.assertEqual(tracker.window_limit, 100)
        self.assertEqual(tracker.window_duration, 60.0)
        self.assertEqual(len(tracker.requests), 0)

    def test_check_available_empty(self):
        """测试空窗口时检查可用"""
        tracker = RollingWindowTracker(window_limit=10, window_duration=60.0)

        async def run():
            available, wait_time = await tracker.check_available()
            return available, wait_time

        available, wait_time = asyncio.run(run())
        self.assertTrue(available)
        self.assertEqual(wait_time, 0.0)

    def test_record_request(self):
        """测试记录请求"""
        tracker = RollingWindowTracker(window_limit=10, window_duration=60.0)

        async def run():
            await tracker.record_request()
            await tracker.record_request()
            return tracker.requests

        requests = asyncio.run(run())
        self.assertEqual(len(requests), 2)
        self.assertEqual(tracker.total_requests_lifetime, 2)

    def test_window_limit_reached(self):
        """测试窗口限额达到"""
        tracker = RollingWindowTracker(window_limit=2, window_duration=60.0)

        async def run():
            await tracker.record_request()
            await tracker.record_request()
            available, wait_time = await tracker.check_available()
            return available, wait_time

        available, wait_time = asyncio.run(run())
        self.assertFalse(available)
        self.assertGreater(wait_time, 0.0)

    def test_window_expiry(self):
        """测试窗口过期清理"""
        tracker = RollingWindowTracker(window_limit=10, window_duration=0.5)

        async def run():
            await tracker.record_request()
            self.assertEqual(len(tracker.requests), 1)

            # 等待窗口过期
            await asyncio.sleep(0.6)

            available, wait_time = await tracker.check_available()
            return available, len(tracker.requests)

        available, remaining_requests = asyncio.run(run())
        self.assertTrue(available)
        self.assertEqual(remaining_requests, 0)  # 过期请求已清理

    def test_get_remaining(self):
        """测试获取剩余请求数"""
        tracker = RollingWindowTracker(window_limit=10, window_duration=60.0)

        async def run():
            await tracker.record_request()
            await tracker.record_request()
            await tracker.record_request()
            return tracker.get_remaining()

        remaining = asyncio.run(run())
        self.assertEqual(remaining, 7)

    def test_state_persistence(self):
        """测试状态持久化"""
        tracker = RollingWindowTracker(window_limit=10, window_duration=60.0)

        async def run():
            await tracker.record_request()
            await tracker.record_request()
            state = tracker.get_state()
            return state

        state = asyncio.run(run())
        self.assertEqual(len(state.requests), 2)
        self.assertEqual(state.total_requests_lifetime, 2)


class TestRateLimiter(unittest.TestCase):
    """测试组合限流器"""

    def test_initial_state(self):
        """测试初始状态"""
        limiter = RateLimiter(
            rate=0.33,
            capacity=100,
            window_limit=6000,
            window_duration=18000.0
        )
        self.assertIsNotNone(limiter.token_bucket)
        self.assertIsNotNone(limiter.window_tracker)

    def test_acquire_success(self):
        """测试获取许可成功"""
        limiter = RateLimiter(
            rate=10.0,
            capacity=100,
            window_limit=100,
            window_duration=60.0
        )

        async def run():
            allowed, wait_time = await limiter.acquire()
            return allowed, wait_time

        allowed, wait_time = asyncio.run(run())
        self.assertTrue(allowed)
        self.assertEqual(wait_time, 0.0)

    def test_window_limit_blocks(self):
        """测试窗口限额阻止请求"""
        limiter = RateLimiter(
            rate=10.0,
            capacity=100,
            window_limit=2,
            window_duration=60.0
        )

        async def run():
            # 先用掉窗口限额
            await limiter.acquire()
            await limiter.window_tracker.record_request()
            await limiter.acquire()
            await limiter.window_tracker.record_request()

            # 再次尝试
            allowed, wait_time = await limiter.acquire()
            return allowed

        allowed = asyncio.run(run())
        self.assertFalse(allowed)

    def test_get_status(self):
        """测试获取状态快照"""
        limiter = RateLimiter(
            rate=1.0,
            capacity=10,
            window_limit=100,
            window_duration=60.0
        )

        async def run():
            await limiter.acquire()
            await limiter.window_tracker.record_request()
            status = limiter.get_status()
            return status

        status = asyncio.run(run())
        self.assertIsInstance(status, RateLimitStatus)
        self.assertEqual(status.tokens_available, 9.0)
        self.assertEqual(status.window_requests_used, 1)
        self.assertEqual(status.window_requests_remaining, 99)


class TestRequestQueue(unittest.TestCase):
    """测试请求队列（TurnTicket 模式）"""

    def test_initial_state(self):
        """测试初始状态"""
        config = QueueConfig(normal_max_size=50)
        queue = RequestQueue(config=config)
        self.assertEqual(queue.config.normal_max_size, 50)
        self.assertEqual(queue.get_queue_size()["total"], 0)

    def test_request_turn_success(self):
        """测试申请轮次成功"""
        config = QueueConfig(normal_max_size=10)
        queue = RequestQueue(config=config)

        async def run():
            ticket = await queue.request_turn(RequestPriority.NORMAL)
            return ticket.id, ticket.priority, queue.get_queue_size()["normal"]

        ticket_id, priority, normal_size = asyncio.run(run())
        self.assertIsNotNone(ticket_id)
        self.assertEqual(priority, RequestPriority.NORMAL)
        self.assertEqual(normal_size, 1)

    def test_queue_full_error(self):
        """测试队列满时拒绝"""
        config = QueueConfig(
            normal_max_size=2,
            normal_backpressure_threshold=1.0,
        )
        queue = RequestQueue(config=config)

        async def run():
            await queue.request_turn(RequestPriority.NORMAL)
            await queue.request_turn(RequestPriority.NORMAL)

            # 第三次应该抛出异常
            try:
                await queue.request_turn(RequestPriority.NORMAL)
                return False
            except QueueFullError:
                return True

        raised = asyncio.run(run())
        self.assertTrue(raised)

    def test_backpressure_threshold(self):
        """测试反压阈值"""
        config = QueueConfig(
            normal_max_size=10,
            normal_backpressure_threshold=0.5,
        )
        queue = RequestQueue(config=config)

        async def run():
            # 填充到阈值（5 个）
            for i in range(5):
                await queue.request_turn(RequestPriority.NORMAL)

            # 第六个应该被拒绝
            try:
                await queue.request_turn(RequestPriority.NORMAL)
                return False
            except QueueFullError:
                return True

        raised = asyncio.run(run())
        self.assertTrue(raised)

    def test_priority_ordering(self):
        """测试优先级排序"""
        config = QueueConfig(normal_max_size=10)
        queue = RequestQueue(config=config)

        async def run():
            # 按反序提交
            await queue.request_turn(RequestPriority.LOW)
            await queue.request_turn(RequestPriority.HIGH)
            await queue.request_turn(RequestPriority.NORMAL)
            await queue.request_turn(RequestPriority.CRITICAL)

            # CRITICAL 有独立队列，先处理
            # 普通队列按优先级：HIGH > NORMAL > LOW

            # 获取下一个 CRITICAL 请求
            critical_ticket = await queue._pop_ticket(RequestPriority.CRITICAL)
            if critical_ticket:
                return critical_ticket.priority

            # 获取下一个 HIGH 请求
            high_ticket = await queue._pop_ticket(RequestPriority.HIGH)
            if high_ticket:
                return high_ticket.priority

            return None

        priority = asyncio.run(run())
        self.assertEqual(priority, RequestPriority.CRITICAL)

    def test_get_stats(self):
        """测试获取统计信息"""
        config = QueueConfig(normal_max_size=10)
        queue = RequestQueue(config=config)

        async def run():
            await queue.request_turn(RequestPriority.NORMAL)
            stats = queue.get_stats()
            return stats

        stats = asyncio.run(run())
        self.assertEqual(stats["queue_lengths"]["normal"], 1)
        self.assertIn("stats", stats)
        self.assertEqual(stats["stats"]["submitted"]["NORMAL"], 1)


class TestRateLimitSQLite(unittest.TestCase):
    """测试 SQLite 持久化"""

    def setUp(self):
        """使用临时数据库"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_rate_limit.db"

    def tearDown(self):
        """清理临时文件"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_db(self):
        """测试数据库初始化"""
        db = RateLimitSQLite(db_path=self.db_path)
        self.assertTrue(self.db_path.exists())
        db.close()

    def test_save_and_load_state(self):
        """测试保存和加载状态"""
        db = RateLimitSQLite(db_path=self.db_path)

        async def run():
            # 创建并保存状态
            state = RateLimitState(
                timestamp=time.time(),
                tokens_available=50.0,
                last_refill_time=time.time(),
                requests_in_window=[time.time(), time.time()],
                total_requests_lifetime=100
            )
            await db.save_state(state)

            # 加载状态
            loaded = await db.load_state()
            return loaded

        loaded = asyncio.run(run())
        self.assertEqual(loaded.tokens_available, 50.0)
        self.assertEqual(len(loaded.requests_in_window), 2)
        self.assertEqual(loaded.total_requests_lifetime, 100)

        db.close()

    def test_record_request_history(self):
        """测试记录请求历史"""
        db = RateLimitSQLite(db_path=self.db_path)

        async def run():
            await db.record_request(
                request_id="test-123",
                priority="NORMAL",
                duration=1.5,
                success=True
            )

            history = await db.get_recent_requests(limit=10)
            return history

        history = asyncio.run(run())
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["request_id"], "test-123")
        self.assertTrue(history[0]["success"])

        db.close()

    def test_cleanup_old_history(self):
        """测试清理过期历史"""
        db = RateLimitSQLite(db_path=self.db_path)

        async def run():
            # 直接插入一个过期记录（时间戳设为很久以前）
            conn = db._get_conn()
            old_time = time.time() - 86400.0  # 24 小时前
            conn.execute("""
                INSERT INTO request_history (
                    request_id, timestamp, priority, success
                ) VALUES (?, ?, ?, ?)
            """, ("old-request", old_time, "NORMAL", 1))
            conn.commit()

            # 清理超过 1 小时的记录
            deleted = await db.cleanup_old_history(max_age=3600.0)
            return deleted

        deleted = asyncio.run(run())
        self.assertGreater(deleted, 0)

        db.close()


class TestRateLimitConfig(unittest.TestCase):
    """测试限流配置"""

    def test_default_config(self):
        """测试默认配置"""
        config = RateLimitConfig()
        self.assertEqual(config.burstCapacity, 100)
        self.assertEqual(config.maxConcurrent, 3)
        self.assertEqual(config.queueMaxSize, 50)

    def test_effective_rate_rolling_window(self):
        """测试滚动窗口模式速率计算"""
        config = RateLimitConfig(
            rollingWindowRequests=6000,
            rollingWindowDuration=18000
        )
        rate = config.get_effective_rate()
        self.assertAlmostEqual(rate, 0.333, places=2)

    def test_effective_rate_rpm(self):
        """测试 RPM 模式速率计算"""
        config = RateLimitConfig(rpm=60)
        rate = config.get_effective_rate()
        self.assertEqual(rate, 1.0)

    def test_window_limit_rolling_window(self):
        """测试滚动窗口限额"""
        config = RateLimitConfig(
            rollingWindowRequests=5000,
            rollingWindowDuration=18000
        )
        limit = config.get_window_limit()
        self.assertEqual(limit, 5000)

    def test_window_limit_rpm(self):
        """测试 RPM 模式窗口限额推算"""
        config = RateLimitConfig(rpm=20)
        limit = config.get_window_limit()
        # 20 RPM * 300 minutes (5 hours) = 6000
        self.assertEqual(limit, 6000)


if __name__ == "__main__":
    unittest.main()