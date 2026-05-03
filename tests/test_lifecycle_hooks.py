"""
Tests for src/lifecycle_hooks.py - 确定性生命周期钩子体系

Coverage targets:
- LifecycleHookRegistry initialization
- register() and unregister() methods
- trigger() and trigger_sync() methods
- Hook execution with priorities
- Hook statistics
- Built-in hooks registration
"""

import asyncio
import pytest
import time
from unittest.mock import MagicMock, AsyncMock
from pathlib import Path

from src.lifecycle_hooks import (
    LifecycleHookRegistry,
    HookPoint,
    HookStats,
    HookTriggerReport,
    HookExecutionResult,
    get_global_registry,
    reset_global_registry,
)
from src.builtin_hooks import register_builtin_hooks


class TestLifecycleHookRegistryInit:
    """Test LifecycleHookRegistry initialization"""

    def test_init_basic(self):
        """Test basic initialization"""
        registry = LifecycleHookRegistry()

        assert registry._hooks is not None
        assert len(registry._hooks) == len(HookPoint)
        assert registry._hook_stats == {}
        assert registry._global_stats["total_triggers"] == 0

    def test_init_all_hook_points(self):
        """Test all hook points are initialized"""
        registry = LifecycleHookRegistry()

        for point in HookPoint:
            assert point.value in registry._hooks
            assert registry._hooks[point.value] == []

    def test_hook_point_descriptions(self):
        """Test hook point descriptions exist"""
        registry = LifecycleHookRegistry()

        for point in HookPoint:
            description = registry.get_hook_point_description(point.value)
            assert description is not None


class TestHookRegistration:
    """Test hook registration"""

    def test_register_basic(self):
        """Test basic hook registration"""
        registry = LifecycleHookRegistry()

        hook_id = registry.register(
            HookPoint.TOOL_CALL_BEFORE,
            lambda ctx: True,
            priority=0,
            name="test_hook"
        )

        assert hook_id == "test_hook"
        assert len(registry._hooks[HookPoint.TOOL_CALL_BEFORE.value]) == 1
        assert registry.has_hook("test_hook")

    def test_register_auto_name(self):
        """Test auto-generated hook name"""
        registry = LifecycleHookRegistry()

        hook_id = registry.register(
            HookPoint.TOOL_CALL_BEFORE,
            lambda ctx: True,
            priority=0
        )

        assert hook_id.startswith("tool_call_before_")
        assert registry.has_hook(hook_id)

    def test_register_priority_sorting(self):
        """Test hooks are sorted by priority"""
        registry = LifecycleHookRegistry()

        # Register hooks in different priorities
        id1 = registry.register(HookPoint.TOOL_CALL_BEFORE, lambda ctx: "first", priority=10, name="hook_10")
        id2 = registry.register(HookPoint.TOOL_CALL_BEFORE, lambda ctx: "second", priority=0, name="hook_0")
        id3 = registry.register(HookPoint.TOOL_CALL_BEFORE, lambda ctx: "third", priority=5, name="hook_5")

        hooks = registry._hooks[HookPoint.TOOL_CALL_BEFORE.value]

        # Should be sorted by priority
        assert hooks[0][2] == "hook_0"  # priority 0
        assert hooks[1][2] == "hook_5"  # priority 5
        assert hooks[2][2] == "hook_10"  # priority 10

    def test_register_duplicate_replace(self):
        """Test replacing existing hook with same name"""
        registry = LifecycleHookRegistry()

        hook_id1 = registry.register(
            HookPoint.TOOL_CALL_BEFORE,
            lambda ctx: "first",
            priority=0,
            name="test_hook"
        )

        hook_id2 = registry.register(
            HookPoint.TOOL_CALL_BEFORE,
            lambda ctx: "second",
            priority=0,
            name="test_hook"
        )

        assert hook_id1 == hook_id2
        assert len(registry._hooks[HookPoint.TOOL_CALL_BEFORE.value]) == 1

    def test_register_invalid_hook_point(self):
        """Test registering with invalid hook point"""
        registry = LifecycleHookRegistry()

        with pytest.raises(ValueError, match="Unknown hook point"):
            registry.register("invalid_point", lambda ctx: True)

    def test_unregister_existing(self):
        """Test unregistering existing hook"""
        registry = LifecycleHookRegistry()

        hook_id = registry.register(HookPoint.TOOL_CALL_BEFORE, lambda ctx: True, name="test_hook")

        result = registry.unregister(hook_id)

        assert result is True
        assert not registry.has_hook(hook_id)

    def test_unregister_non_existing(self):
        """Test unregistering non-existing hook"""
        registry = LifecycleHookRegistry()

        result = registry.unregister("non_existing_hook")

        assert result is False

    def test_clear_hooks_all(self):
        """Test clearing all hooks"""
        registry = LifecycleHookRegistry()

        registry.register(HookPoint.TOOL_CALL_BEFORE, lambda ctx: True)
        registry.register(HookPoint.TOOL_CALL_AFTER, lambda ctx: True)

        count = registry.clear_hooks()

        assert count == 2
        assert registry.get_hook_count() == 0

    def test_clear_hooks_specific_point(self):
        """Test clearing hooks for specific point"""
        registry = LifecycleHookRegistry()

        registry.register(HookPoint.TOOL_CALL_BEFORE, lambda ctx: True)
        registry.register(HookPoint.TOOL_CALL_AFTER, lambda ctx: True)

        count = registry.clear_hooks(HookPoint.TOOL_CALL_BEFORE)

        assert count == 1
        assert registry.get_hook_count(HookPoint.TOOL_CALL_BEFORE) == 0
        assert registry.get_hook_count(HookPoint.TOOL_CALL_AFTER) == 1


class TestHookTrigger:
    """Test hook triggering"""

    @pytest.mark.asyncio
    async def test_trigger_single_hook(self):
        """Test triggering single hook"""
        registry = LifecycleHookRegistry()

        call_count = 0
        def my_hook(ctx):
            nonlocal call_count
            call_count += 1
            return "result"

        registry.register(HookPoint.TOOL_CALL_BEFORE, my_hook, name="test_hook")

        report = await registry.trigger(HookPoint.TOOL_CALL_BEFORE, {"test": "data"})

        assert call_count == 1
        assert report.hooks_executed == 1
        assert report.hooks_failed == 0
        assert len(report.results) == 1
        assert report.results[0].hook_id == "test_hook"
        assert report.results[0].status == "success"

    @pytest.mark.asyncio
    async def test_trigger_async_hook(self):
        """Test triggering async hook"""
        registry = LifecycleHookRegistry()

        async def async_hook(ctx):
            await asyncio.sleep(0.01)
            return "async_result"

        registry.register(HookPoint.TOOL_CALL_BEFORE, async_hook, name="async_hook")

        report = await registry.trigger(HookPoint.TOOL_CALL_BEFORE, {})

        assert report.hooks_executed == 1
        assert report.results[0].result == "async_result"

    @pytest.mark.asyncio
    async def test_trigger_multiple_hooks_priority(self):
        """Test triggering multiple hooks with priority ordering"""
        registry = LifecycleHookRegistry()

        execution_order = []

        def hook_1(ctx):
            execution_order.append(1)
            return "first"

        def hook_2(ctx):
            execution_order.append(2)
            return "second"

        def hook_3(ctx):
            execution_order.append(3)
            return "third"

        registry.register(HookPoint.TOOL_CALL_BEFORE, hook_3, priority=10, name="hook_3")
        registry.register(HookPoint.TOOL_CALL_BEFORE, hook_1, priority=0, name="hook_1")
        registry.register(HookPoint.TOOL_CALL_BEFORE, hook_2, priority=5, name="hook_2")

        await registry.trigger(HookPoint.TOOL_CALL_BEFORE, {})

        assert execution_order == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_trigger_hook_failure(self):
        """Test hook failure handling"""
        registry = LifecycleHookRegistry()

        def failing_hook(ctx):
            raise ValueError("Hook failed")

        registry.register(HookPoint.TOOL_CALL_BEFORE, failing_hook, name="failing_hook")

        report = await registry.trigger(HookPoint.TOOL_CALL_BEFORE, {})

        assert report.hooks_executed == 0
        assert report.hooks_failed == 1
        assert report.results[0].status == "failed"
        assert "Hook failed" in report.results[0].error

    @pytest.mark.asyncio
    async def test_trigger_fail_fast(self):
        """Test fail_fast stops execution on first failure"""
        registry = LifecycleHookRegistry()

        execution_count = 0

        def hook_1(ctx):
            raise ValueError("First failed")

        def hook_2(ctx):
            nonlocal execution_count
            execution_count += 1
            return "ok"

        registry.register(HookPoint.TOOL_CALL_BEFORE, hook_1, priority=0, name="hook_1")
        registry.register(HookPoint.TOOL_CALL_BEFORE, hook_2, priority=1, name="hook_2")

        report = await registry.trigger(HookPoint.TOOL_CALL_BEFORE, {}, fail_fast=True)

        assert report.hooks_failed == 1
        assert execution_count == 0  # hook_2 not executed

    @pytest.mark.asyncio
    async def test_trigger_no_hooks(self):
        """Test triggering with no registered hooks"""
        registry = LifecycleHookRegistry()

        report = await registry.trigger(HookPoint.SESSION_START, {})

        assert report.hooks_count == 0
        assert report.hooks_executed == 0

    @pytest.mark.asyncio
    async def test_trigger_unknown_point(self):
        """Test triggering unknown hook point"""
        registry = LifecycleHookRegistry()

        report = await registry.trigger("unknown_point", {})

        assert report.hooks_count == 0

    def test_trigger_sync(self):
        """Test synchronous trigger"""
        registry = LifecycleHookRegistry()

        call_count = 0
        def sync_hook(ctx):
            nonlocal call_count
            call_count += 1
            return "sync_result"

        registry.register(HookPoint.TOOL_CALL_BEFORE, sync_hook, name="sync_hook")

        report = registry.trigger_sync(HookPoint.TOOL_CALL_BEFORE, {})

        assert call_count == 1
        assert report.hooks_executed == 1


class TestHookStats:
    """Test hook statistics"""

    @pytest.mark.asyncio
    async def test_stats_updated_on_success(self):
        """Test stats updated on successful execution"""
        registry = LifecycleHookRegistry()

        registry.register(HookPoint.TOOL_CALL_BEFORE, lambda ctx: True, name="test_hook")

        await registry.trigger(HookPoint.TOOL_CALL_BEFORE, {})
        await registry.trigger(HookPoint.TOOL_CALL_BEFORE, {})

        stats = registry.get_hook_stats("test_hook")

        assert stats is not None
        assert stats["total_calls"] == 2
        assert stats["success_calls"] == 2
        assert stats["failed_calls"] == 0
        assert stats["success_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_stats_updated_on_failure(self):
        """Test stats updated on failed execution"""
        registry = LifecycleHookRegistry()

        def failing_hook(ctx):
            raise ValueError("Failed")

        registry.register(HookPoint.TOOL_CALL_BEFORE, failing_hook, name="failing_hook")

        await registry.trigger(HookPoint.TOOL_CALL_BEFORE, {})

        stats = registry.get_hook_stats("failing_hook")

        assert stats["total_calls"] == 1
        assert stats["success_calls"] == 0
        assert stats["failed_calls"] == 1
        assert stats["success_rate"] == 0.0
        assert "Failed" in stats["last_error"]

    def test_get_all_stats(self):
        """Test getting all statistics"""
        registry = LifecycleHookRegistry()

        registry.register(HookPoint.TOOL_CALL_BEFORE, lambda ctx: True, name="hook_1")
        registry.register(HookPoint.TOOL_CALL_AFTER, lambda ctx: True, name="hook_2")

        stats = registry.get_all_stats()

        assert "global" in stats
        assert "hooks" in stats
        assert len(stats["hooks"]) == 2

    def test_stats_non_existing_hook(self):
        """Test getting stats for non-existing hook"""
        registry = LifecycleHookRegistry()

        stats = registry.get_hook_stats("non_existing")

        assert stats is None


class TestHookQueries:
    """Test hook query methods"""

    def test_list_hooks_all(self):
        """Test listing all hooks"""
        registry = LifecycleHookRegistry()

        registry.register(HookPoint.TOOL_CALL_BEFORE, lambda ctx: True, name="hook_1")
        registry.register(HookPoint.TOOL_CALL_AFTER, lambda ctx: True, name="hook_2")

        hooks = registry.list_hooks()

        assert len(hooks) == 2

    def test_list_hooks_by_point(self):
        """Test listing hooks by point"""
        registry = LifecycleHookRegistry()

        registry.register(HookPoint.TOOL_CALL_BEFORE, lambda ctx: True, name="hook_1")
        registry.register(HookPoint.TOOL_CALL_AFTER, lambda ctx: True, name="hook_2")

        hooks = registry.list_hooks(HookPoint.TOOL_CALL_BEFORE)

        assert len(hooks) == 1
        assert hooks[0]["hook_point"] == "tool_call_before"

    def test_get_hook_count(self):
        """Test getting hook count"""
        registry = LifecycleHookRegistry()

        registry.register(HookPoint.TOOL_CALL_BEFORE, lambda ctx: True)
        registry.register(HookPoint.TOOL_CALL_AFTER, lambda ctx: True)

        count = registry.get_hook_count()

        assert count == 2

    def test_get_hook_count_by_point(self):
        """Test getting hook count by point"""
        registry = LifecycleHookRegistry()

        registry.register(HookPoint.TOOL_CALL_BEFORE, lambda ctx: True)
        registry.register(HookPoint.TOOL_CALL_BEFORE, lambda ctx: True, priority=1)
        registry.register(HookPoint.TOOL_CALL_AFTER, lambda ctx: True)

        count = registry.get_hook_count(HookPoint.TOOL_CALL_BEFORE)

        assert count == 2

    def test_has_hook(self):
        """Test checking if hook exists"""
        registry = LifecycleHookRegistry()

        registry.register(HookPoint.TOOL_CALL_BEFORE, lambda ctx: True, name="test_hook")

        assert registry.has_hook("test_hook") is True
        assert registry.has_hook("non_existing") is False


class TestBuiltinHooks:
    """Test builtin hooks registration"""

    def test_register_builtin_hooks(self):
        """Test registering builtin hooks"""
        registry = LifecycleHookRegistry()

        register_builtin_hooks(registry)

        # Should have multiple hooks registered
        assert registry.get_hook_count() > 0

        # Check specific hooks exist
        assert registry.get_hook_count(HookPoint.SESSION_START) > 0
        assert registry.get_hook_count(HookPoint.SESSION_END) > 0
        assert registry.get_hook_count(HookPoint.TOOL_CALL_BEFORE) > 0
        assert registry.get_hook_count(HookPoint.TOOL_CALL_AFTER) > 0
        assert registry.get_hook_count(HookPoint.LLM_CALL_BEFORE) > 0
        assert registry.get_hook_count(HookPoint.LLM_CALL_AFTER) > 0

    def test_builtin_hook_names(self):
        """Test builtin hook names"""
        registry = LifecycleHookRegistry()

        register_builtin_hooks(registry)

        hooks = registry.list_hooks()

        # Check specific builtin hook names
        hook_ids = [h["hook_id"] for h in hooks]
        assert "session_log_start" in hook_ids
        assert "session_log_end" in hook_ids
        assert "tool_permission_check" in hook_ids
        assert "tool_log_call" in hook_ids

    @pytest.mark.asyncio
    async def test_session_start_hook_execution(self):
        """Test session_start hook execution"""
        registry = LifecycleHookRegistry()
        register_builtin_hooks(registry)

        context = {
            "session_id": "test_session",
            "metadata": {"test": True},
        }

        report = await registry.trigger(HookPoint.SESSION_START, context)

        # Should have executed hooks without error
        assert report.hooks_failed == 0

    @pytest.mark.asyncio
    async def test_tool_permission_check_hook(self):
        """Test tool_permission_check hook"""
        registry = LifecycleHookRegistry()
        register_builtin_hooks(registry)

        # Test allowed tool
        context = {
            "tool_name": "file_read",
            "tool_args": {"path": "/test"},
            "sandbox": None,
        }

        report = await registry.trigger(HookPoint.TOOL_CALL_BEFORE, context)
        assert report.hooks_failed == 0

    @pytest.mark.asyncio
    async def test_tool_permission_check_with_permission_set(self):
        """Test tool_permission_check with permission set"""
        registry = LifecycleHookRegistry()
        register_builtin_hooks(registry)

        # Test denied tool
        context = {
            "tool_name": "file_write",
            "tool_args": {"path": "/test"},
            "sandbox": None,
            "permission_set": ["file_read"],  # Only file_read allowed
        }

        # The hook should raise PermissionError
        report = await registry.trigger(HookPoint.TOOL_CALL_BEFORE, context)

        # Should have at least one failure (permission check)
        assert report.hooks_failed >= 1


class TestGlobalRegistry:
    """Test global registry"""

    def test_get_global_registry(self):
        """Test getting global registry"""
        registry = get_global_registry()

        assert registry is not None
        assert isinstance(registry, LifecycleHookRegistry)

    def test_reset_global_registry(self):
        """Test resetting global registry"""
        registry = get_global_registry()
        registry.register(HookPoint.TOOL_CALL_BEFORE, lambda ctx: True)

        reset_global_registry()

        new_registry = get_global_registry()
        assert new_registry.get_hook_count() == 0


class TestHookPointEnum:
    """Test HookPoint enum"""

    def test_hook_point_values(self):
        """Test HookPoint enum values"""
        assert HookPoint.SESSION_START.value == "session_start"
        assert HookPoint.TOOL_CALL_BEFORE.value == "tool_call_before"
        assert HookPoint.LLM_CALL_AFTER.value == "llm_call_after"

    def test_hook_point_count(self):
        """Test number of hook points"""
        # Should have all defined hook points
        expected_count = 40  # Updated count based on current enum definition
        assert len(HookPoint) == expected_count


class TestDataClasses:
    """Test data classes"""

    def test_hook_execution_result(self):
        """Test HookExecutionResult"""
        result = HookExecutionResult(
            hook_id="test",
            status="success",
            duration_ms=10.5,
            result="output",
        )

        assert result.hook_id == "test"
        assert result.status == "success"
        assert result.duration_ms == 10.5

    def test_hook_trigger_report(self):
        """Test HookTriggerReport"""
        report = HookTriggerReport(
            hook_point="tool_call_before",
            hooks_count=1,
            hooks_executed=1,
            hooks_failed=0,
            hooks_skipped=0,
        )

        assert report.hook_point == "tool_call_before"
        assert report.hooks_executed == 1

    def test_hook_trigger_report_to_dict(self):
        """Test HookTriggerReport.to_dict()"""
        report = HookTriggerReport(
            hook_point="tool_call_before",
            hooks_count=1,
            hooks_executed=1,
            hooks_failed=0,
            hooks_skipped=0,
            results=[HookExecutionResult("test", "success", 10.0)],
            total_duration_ms=10.0,
        )

        d = report.to_dict()

        assert d["hook_point"] == "tool_call_before"
        assert d["hooks_executed"] == 1
        assert len(d["results"]) == 1

    def test_hook_stats(self):
        """Test HookStats"""
        stats = HookStats(
            hook_id="test",
            hook_point="tool_call_before",
            priority=0,
            total_calls=10,
            success_calls=8,
            failed_calls=2,
        )

        d = stats.to_dict()

        assert d["total_calls"] == 10
        assert d["success_rate"] == 0.8