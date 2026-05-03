"""
Tests for src/tools/user_modeling.py (L4 用户建模层)

Coverage targets:
- UserModelingLayer 单例模式
- observe() 观察记录
- dialectical_update() 辩证式更新
- get_user_preference() 基于上下文的偏好查询
- 升级而非覆盖逻辑
"""

import json
import os
import sys
import tempfile
import threading
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tools.user_modeling import UserModelingLayer


# ==================== Fixtures ====================

@pytest.fixture
def temp_db_path():
    """Create a temporary database path for testing."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_user_modeling.db")
    yield db_path
    # Cleanup
    if os.path.exists(temp_dir):
        import shutil
        shutil.rmtree(temp_dir)


@pytest.fixture
def user_model(temp_db_path):
    """Create a UserModelingLayer instance with temp database."""
    # Reset singleton state for testing
    UserModelingLayer._instance = None
    UserModelingLayer._initialized = False
    
    model = UserModelingLayer(db_path=temp_db_path)
    yield model
    
    # Cleanup
    model.close()


# ==================== Tests for Singleton Pattern ====================

class TestSingletonPattern:
    def test_singleton_returns_same_instance(self, temp_db_path):
        """Test that singleton returns the same instance."""
        UserModelingLayer._instance = None
        UserModelingLayer._initialized = False
        
        model1 = UserModelingLayer(db_path=temp_db_path)
        model2 = UserModelingLayer(db_path=temp_db_path)
        
        assert model1 is model2
        
        model1.close()

    def test_singleton_thread_safety(self, temp_db_path):
        """Test singleton thread safety."""
        UserModelingLayer._instance = None
        UserModelingLayer._initialized = False
        UserModelingLayer._lock = threading.Lock()
        
        instances = []
        
        def create_instance():
            model = UserModelingLayer(db_path=temp_db_path)
            instances.append(model)
        
        threads = [threading.Thread(target=create_instance) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All instances should be the same
        assert len(set(id(i) for i in instances)) == 1
        
        # Close the singleton properly
        if instances:
            try:
                instances[0].close()
            except Exception:
                # Ignore errors during cleanup
                pass


# ==================== Tests for observe ====================

class TestObserve:
    def test_observe_preference(self, user_model):
        """Test observing a preference."""
        result = user_model.observe(
            evidence_type="preference",
            data={"key": "coffee", "value": "美式"},
            context="早上",
            confidence=0.9
        )
        
        assert "Observation recorded" in result
        assert "coffee" in result

    def test_observe_invalid_type(self, user_model):
        """Test invalid evidence type."""
        result = user_model.observe(
            evidence_type="invalid",
            data={"key": "test", "value": "test"},
            confidence=0.8
        )
        
        assert "Invalid evidence type" in result

    def test_observe_invalid_confidence(self, user_model):
        """Test invalid confidence value."""
        result = user_model.observe(
            evidence_type="preference",
            data={"key": "test", "value": "test"},
            confidence=1.5
        )
        
        assert "Invalid confidence" in result


# ==================== Tests for Preference Query ====================

class TestGetUserPreference:
    def test_get_preference_existing(self, user_model):
        """Test getting an existing preference."""
        # First observe a preference
        user_model.observe(
            evidence_type="preference",
            data={"key": "coffee", "value": "美式"},
            confidence=0.9
        )
        
        # Trigger update to set preference
        import asyncio
        asyncio.run(user_model.dialectical_update())
        
        # Now query it
        result = user_model.get_user_preference("coffee")
        
        assert result["value"] == "美式"
        assert result["confidence"] >= 0.8

    def test_get_preference_missing(self, user_model):
        """Test getting a missing preference."""
        result = user_model.get_user_preference("nonexistent")
        
        assert result["value"] is None
        assert result["confidence"] == 0.0

    def test_get_preference_with_context(self, user_model):
        """Test getting preference with context (exception handling)."""
        # Setup: observe usual preference
        user_model.observe(
            evidence_type="preference",
            data={"key": "coffee", "value": "美式"},
            confidence=0.9
        )
        
        # Setup: observe exception with context
        user_model.observe(
            evidence_type="preference",
            data={"key": "coffee", "value": "拿铁"},
            context="周三下午",
            confidence=0.85
        )
        
        import asyncio
        asyncio.run(user_model.dialectical_update())
        
        # Query without context -> usual
        result_normal = user_model.get_user_preference("coffee")
        assert result_normal["value"] == "美式"
        
        # Query with matching context -> exception
        result_exception = user_model.get_user_preference("coffee", "周三下午开会")
        assert result_exception["reason"] == "例外情况: 周三下午"


# ==================== Tests for Dialectical Update ====================

class TestDialecticalUpdate:
    def test_no_conflicts_reinforce(self, user_model):
        """Test reinforce when no conflicts."""
        import asyncio
        
        # Observe single preference
        user_model.observe(
            evidence_type="preference",
            data={"key": "test", "value": "value1"},
            confidence=0.8
        )
        
        result = asyncio.run(user_model.dialectical_update())
        
        assert result["status"] == "reinforced"
        assert len(result["conflicts"]) == 0

    def test_conflict_detection(self, user_model):
        """Test conflict detection between old and new evidence."""
        import asyncio
        
        # Setup: observe usual preference
        user_model.observe(
            evidence_type="preference",
            data={"key": "coffee", "value": "美式"},
            confidence=0.9
        )
        asyncio.run(user_model.dialectical_update())
        
        # Now observe conflicting evidence with context
        user_model.observe(
            evidence_type="preference",
            data={"key": "coffee", "value": "拿铁"},
            context="周三下午",
            confidence=0.85
        )
        
        result = asyncio.run(user_model.dialectical_update())
        
        # Should detect conflict and upgrade
        assert result["status"] == "upgraded"
        assert len(result["conflicts"]) > 0

    def test_upgrade_not_overwrite(self, user_model):
        """Test that upgrade preserves exceptions, not simple overwrite."""
        import asyncio
        
        # Setup: usual preference
        user_model.observe(
            evidence_type="preference",
            data={"key": "coffee", "value": "美式"},
            confidence=0.9
        )
        asyncio.run(user_model.dialectical_update())
        
        # Setup: exception with context
        user_model.observe(
            evidence_type="preference",
            data={"key": "coffee", "value": "拿铁"},
            context="周三下午",
            confidence=0.85
        )
        asyncio.run(user_model.dialectical_update())
        
        # Verify the preference structure
        pref = user_model._get_preference_from_db("coffee")
        
        assert pref is not None
        assert pref.get("usual") == "美式"
        assert "exceptions" in pref
        # Should have exception for "周三下午"
        assert any("周三" in k or "下午" in k for k in pref["exceptions"])


# ==================== Tests for Profile Summary ====================

class TestUserProfileSummary:
    def test_empty_profile(self, user_model):
        """Test empty profile summary."""
        summary = user_model.get_user_profile_summary()
        assert "无用户画像数据" in summary

    def test_profile_with_preferences(self, user_model):
        """Test profile with preferences."""
        import asyncio
        
        user_model.observe(
            evidence_type="preference",
            data={"key": "coffee", "value": "美式"},
            confidence=0.9
        )
        asyncio.run(user_model.dialectical_update())
        
        summary = user_model.get_user_profile_summary()
        assert "coffee" in summary
        assert "美式" in summary


# ==================== Tests for History ====================

class TestDialecticalHistory:
    def test_get_history_empty(self, user_model):
        """Test empty history."""
        history = user_model.get_dialectical_history()
        assert len(history) == 0

    def test_history_after_conflict(self, user_model):
        """Test history after conflict resolution."""
        import asyncio
        
        # Create conflict
        user_model.observe(
            evidence_type="preference",
            data={"key": "test", "value": "value1"},
            confidence=0.9
        )
        asyncio.run(user_model.dialectical_update())
        
        user_model.observe(
            evidence_type="preference",
            data={"key": "test", "value": "value2"},
            context="特殊情况",
            confidence=0.85
        )
        asyncio.run(user_model.dialectical_update())
        
        history = user_model.get_dialectical_history()
        assert len(history) >= 1
        assert "conflict" in history[0]
        assert "resolution" in history[0]


# ==================== Tests for Clear ====================

class TestClearPreference:
    def test_clear_preference(self, user_model):
        """Test clearing a preference."""
        import asyncio
        
        user_model.observe(
            evidence_type="preference",
            data={"key": "test", "value": "value"},
            confidence=0.8
        )
        asyncio.run(user_model.dialectical_update())
        
        result = user_model.clear_preference("test")
        assert "cleared" in result.lower()
        
        # Verify it's gone
        pref = user_model.get_user_preference("test")
        assert pref["value"] is None