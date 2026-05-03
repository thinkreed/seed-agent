"""
abort_signal.py 单元测试

测试：
- AbortSignal: 取消信号
- AbortController: 取消控制器
- CancellationToken: 取消令牌
- TimeoutCancellationToken: 超时取消令牌
- CompositeCancellationToken: 组合取消令牌
"""

import asyncio
import sys
import unittest
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from abort_signal import (
    AbortSignal,
    AbortController,
    CancellationToken,
    TimeoutCancellationToken,
    CompositeCancellationToken,
    create_linked_token,
)


class TestAbortSignal(unittest.TestCase):
    """测试 AbortSignal"""

    def test_initial_state(self):
        """初始状态未取消"""
        signal = AbortSignal()
        self.assertFalse(signal.aborted)
        self.assertEqual(signal.reason, "")

    def test_abort_sets_state(self):
        """abort() 设置取消状态"""
        signal = AbortSignal()
        signal.abort(reason="test_cancel")

        self.assertTrue(signal.aborted)
        self.assertEqual(signal.reason, "test_cancel")

    def test_abort_triggers_listeners(self):
        """abort() 触发监听器"""
        signal = AbortSignal()
        calls = []

        def listener(s):
            calls.append(s.reason)

        signal.add_listener(listener)
        signal.abort(reason="triggered")

        self.assertEqual(calls, ["triggered"])

    def test_double_abort_ignored(self):
        """重复 abort() 被忽略"""
        signal = AbortSignal()
        calls = []

        def listener(s):
            calls.append(s.reason)

        signal.add_listener(listener)
        signal.abort(reason="first")
        signal.abort(reason="second")  # 应被忽略

        self.assertEqual(calls, ["first"])

    def test_add_listener_after_abort(self):
        """取消后添加监听器不执行"""
        signal = AbortSignal()
        signal.abort(reason="done")

        calls = []
        def listener(s):
            calls.append(s.reason)

        signal.add_listener(listener)  # 不应执行

        self.assertEqual(calls, [])

    def test_remove_listener(self):
        """移除监听器"""
        signal = AbortSignal()
        calls = []

        def listener(s):
            calls.append(s.reason)

        signal.add_listener(listener)
        signal.remove_listener(listener)
        signal.abort(reason="triggered")

        self.assertEqual(calls, [])

    def test_check_raises_on_abort(self):
        """check() 在取消时抛出 CancelledError"""
        signal = AbortSignal()
        signal.abort(reason="test")

        with self.assertRaises(asyncio.CancelledError):
            signal.check()


class TestAbortController(unittest.TestCase):
    """测试 AbortController"""

    def test_controller_signal(self):
        """控制器关联信号"""
        controller = AbortController()
        self.assertFalse(controller.signal.aborted)

    def test_controller_abort(self):
        """控制器 abort() 传播到信号"""
        controller = AbortController()
        controller.abort(reason="controller_cancel")

        self.assertTrue(controller.signal.aborted)
        self.assertEqual(controller.signal.reason, "controller_cancel")


class TestCancellationToken(unittest.TestCase):
    """测试 CancellationToken"""

    def test_initial_not_cancelled(self):
        """初始未取消"""
        token = CancellationToken()
        self.assertFalse(token.cancelled)

    def test_cancel_sets_state(self):
        """cancel() 设置取消状态"""
        token = CancellationToken()
        token.cancel(reason="manual")

        self.assertTrue(token.cancelled)
        self.assertEqual(token.reason, "manual")

    def test_parent_cancel_propagates(self):
        """父取消传播到子"""
        parent = CancellationToken()
        child = parent.create_child()

        parent.cancel(reason="parent_cancel")

        self.assertTrue(child.cancelled)
        self.assertIn("parent_cancel", child.reason)

    def test_create_child(self):
        """创建子令牌"""
        parent = CancellationToken()
        child = parent.create_child()

        self.assertEqual(child.parent, parent)
        self.assertIn(child, parent._children)

    def test_check_raises_on_cancel(self):
        """check() 在取消时抛出 CancelledError"""
        token = CancellationToken()
        token.cancel(reason="test")

        with self.assertRaises(asyncio.CancelledError):
            token.check()


class TestTimeoutCancellationToken(unittest.TestCase):
    """测试 TimeoutCancellationToken"""

    def test_timeout_triggers_cancel(self):
        """超时触发取消"""
        async def test_timeout():
            token = TimeoutCancellationToken(timeout_seconds=0.1)
            token.start_timeout()

            await asyncio.sleep(0.2)

            self.assertTrue(token.cancelled)
            self.assertEqual(token.reason, "timeout")

        asyncio.run(test_timeout())

    def test_manual_cancel_stops_timer(self):
        """手动取消停止计时器"""
        async def test_manual():
            token = TimeoutCancellationToken(timeout_seconds=1.0)
            token.start_timeout()

            token.cancel(reason="manual")

            await asyncio.sleep(0.1)

            self.assertTrue(token.cancelled)
            self.assertEqual(token.reason, "manual")

        asyncio.run(test_manual())


class TestCompositeCancellationToken(unittest.TestCase):
    """测试 CompositeCancellationToken"""

    def test_any_source_cancel_propagates(self):
        """任一源取消传播"""
        token1 = CancellationToken()
        token2 = CancellationToken()
        composite = CompositeCancellationToken([token1, token2])

        token1.cancel(reason="source1")

        self.assertTrue(composite.cancelled)

    def test_all_sources_checked(self):
        """检查所有源"""
        token1 = CancellationToken()
        token2 = CancellationToken()
        composite = CompositeCancellationToken([token1, token2])

        # token1 未取消
        self.assertFalse(composite.cancelled)

        token2.cancel(reason="source2")
        self.assertTrue(composite.cancelled)


class TestCreateLinkedToken(unittest.TestCase):
    """测试 create_linked_token"""

    def test_basic_token(self):
        """创建基本令牌"""
        token = create_linked_token()
        self.assertIsNone(token.parent)
        self.assertFalse(token.cancelled)

    def test_token_with_parent(self):
        """创建带父的令牌"""
        parent = CancellationToken()
        token = create_linked_token(parent=parent)

        self.assertEqual(token.parent, parent)

    def test_token_with_timeout(self):
        """创建超时令牌"""
        async def test():
            token = create_linked_token(timeout=0.1)
            await asyncio.sleep(0.2)
            self.assertTrue(token.cancelled)

        asyncio.run(test())


if __name__ == '__main__':
    unittest.main()