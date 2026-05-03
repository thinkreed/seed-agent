"""
Tests for src/tools/long_term_archive.py (L5 工作日志层)

Coverage targets:
- LongTermArchiveLayer 单例模式
- archive_session() 会话归档
- search_with_context() FTS5 搜索
- get_archive() 归档详情
- 归档统计和清理
"""

import json
import os
import sys
import tempfile
import threading
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tools.long_term_archive import LongTermArchiveLayer


# ==================== Fixtures ====================

@pytest.fixture
def temp_db_path():
    """Create a temporary database path for testing."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_archive.db")
    yield db_path
    # Cleanup
    if os.path.exists(temp_dir):
        import shutil
        shutil.rmtree(temp_dir)


@pytest.fixture
def archive_layer(temp_db_path):
    """Create a LongTermArchiveLayer instance with temp database."""
    # Reset singleton state for testing
    LongTermArchiveLayer._instance = None
    LongTermArchiveLayer._initialized = False
    
    layer = LongTermArchiveLayer(db_path=temp_db_path)
    yield layer
    
    # Cleanup
    layer.close()


@pytest.fixture
def sample_events():
    """Create sample events for testing."""
    return [
        {
            "id": 1,
            "type": "user_input",
            "data": {"content": "帮我重构代码"},
            "timestamp": 1000.0
        },
        {
            "id": 2,
            "type": "llm_response",
            "data": {"content": "好的，我来帮你重构代码"},
            "timestamp": 1001.0
        },
        {
            "id": 3,
            "type": "tool_call",
            "data": {"function": {"name": "file_read"}},
            "timestamp": 1002.0
        },
        {
            "id": 4,
            "type": "tool_result",
            "data": {"content": "文件内容读取成功"},
            "timestamp": 1003.0
        },
        {
            "id": 5,
            "type": "user_input",
            "data": {"content": "完成重构"},
            "timestamp": 1004.0
        }
    ]


# ==================== Tests for Singleton Pattern ====================

class TestSingletonPattern:
    def test_singleton_returns_same_instance(self, temp_db_path):
        """Test that singleton returns the same instance."""
        LongTermArchiveLayer._instance = None
        LongTermArchiveLayer._initialized = False
        
        layer1 = LongTermArchiveLayer(db_path=temp_db_path)
        layer2 = LongTermArchiveLayer(db_path=temp_db_path)
        
        assert layer1 is layer2
        
        layer1.close()

    def test_singleton_thread_safety(self, temp_db_path):
        """Test singleton thread safety."""
        LongTermArchiveLayer._instance = None
        LongTermArchiveLayer._initialized = False
        LongTermArchiveLayer._lock = threading.Lock()
        
        instances = []
        
        def create_instance():
            layer = LongTermArchiveLayer(db_path=temp_db_path)
            instances.append(layer)
        
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


# ==================== Tests for Archive Session ====================

class TestArchiveSession:
    def test_archive_session_basic(self, archive_layer, sample_events):
        """Test basic session archiving."""
        import asyncio
        
        archive_id = asyncio.run(
            archive_layer.archive_session(
                session_id="test_session_001",
                events=sample_events
            )
        )
        
        assert "archive_" in archive_id
        assert "test_session_001" in archive_id

    def test_archive_empty_events(self, archive_layer):
        """Test archiving with empty events."""
        import asyncio
        
        result = asyncio.run(
            archive_layer.archive_session(
                session_id="empty_session",
                events=[]
            )
        )
        
        assert "Error" in result

    def test_archive_with_metadata(self, archive_layer, sample_events):
        """Test archiving with metadata."""
        import asyncio
        
        metadata = {
            "project": "seed-agent",
            "task_type": "refactoring"
        }
        
        archive_id = asyncio.run(
            archive_layer.archive_session(
                session_id="test_with_meta",
                events=sample_events,
                metadata=metadata
            )
        )
        
        assert "archive_" in archive_id
        
        # Verify metadata stored
        archive = archive_layer.get_archive(archive_id)
        assert archive["metadata"]["project"] == "seed-agent"


# ==================== Tests for Search ====================

class TestSearch:
    def test_search_no_results(self, archive_layer):
        """Test search with no matching results."""
        results = archive_layer.search_with_context("nonexistent_keyword")
        assert len(results) == 0

    def test_search_after_archive(self, archive_layer, sample_events):
        """Test search after archiving."""
        import asyncio
        
        # Archive a session
        asyncio.run(
            archive_layer.archive_session(
                session_id="searchable_session",
                events=sample_events
            )
        )
        
        # Search for keyword in events
        results = archive_layer.search_with_context("重构")
        
        assert len(results) > 0
        assert results[0]["summary"] is not None

    def test_search_with_limit(self, archive_layer, sample_events):
        """Test search with limit."""
        import asyncio
        
        # Archive multiple sessions
        for i in range(5):
            asyncio.run(
                archive_layer.archive_session(
                    session_id=f"session_{i}",
                    events=sample_events
                )
            )
        
        results = archive_layer.search_with_context("重构", limit=2)
        assert len(results) <= 2


# ==================== Tests for Get Archive ====================

class TestGetArchive:
    def test_get_archive_existing(self, archive_layer, sample_events):
        """Test getting an existing archive."""
        import asyncio
        
        archive_id = asyncio.run(
            archive_layer.archive_session(
                session_id="get_test_session",
                events=sample_events
            )
        )
        
        archive = archive_layer.get_archive(archive_id)
        
        assert archive is not None
        assert archive["session_id"] == "get_test_session"
        assert archive["events_count"] == len(sample_events)
        assert len(archive["events"]) == len(sample_events)

    def test_get_archive_missing(self, archive_layer):
        """Test getting a missing archive."""
        archive = archive_layer.get_archive("nonexistent_archive")
        assert archive is None

    def test_get_archive_contains_summary(self, archive_layer, sample_events):
        """Test that archive contains summary."""
        import asyncio
        
        archive_id = asyncio.run(
            archive_layer.archive_session(
                session_id="summary_test",
                events=sample_events
            )
        )
        
        archive = archive_layer.get_archive(archive_id)
        
        assert archive["summary"] is not None
        assert len(archive["summary"]) > 0


# ==================== Tests for Statistics ====================

class TestArchiveStats:
    def test_empty_stats(self, archive_layer):
        """Test stats with no archives."""
        stats = archive_layer.get_archive_stats()
        
        assert stats["total_archives"] == 0
        assert stats["total_events"] == 0

    def test_stats_after_archives(self, archive_layer, sample_events):
        """Test stats after creating archives."""
        import asyncio
        
        # Create multiple archives
        for i in range(3):
            asyncio.run(
                archive_layer.archive_session(
                    session_id=f"stats_session_{i}",
                    events=sample_events
                )
            )
        
        stats = archive_layer.get_archive_stats()
        
        assert stats["total_archives"] == 3
        assert stats["total_events"] == len(sample_events) * 3
        assert len(stats["recent_archives"]) > 0


# ==================== Tests for Time Range Search ====================

class TestTimeRangeSearch:
    def test_search_by_time_range(self, archive_layer, sample_events):
        """Test searching by time range."""
        import asyncio
        from datetime import datetime, timedelta
        
        # Archive a session
        asyncio.run(
            archive_layer.archive_session(
                session_id="time_range_test",
                events=sample_events
            )
        )
        
        # Get current time range
        now = datetime.now()
        start = (now - timedelta(days=1)).isoformat()
        end = (now + timedelta(days=1)).isoformat()
        
        results = archive_layer.search_by_time_range(start, end)
        
        assert len(results) > 0

    def test_search_by_time_range_empty(self, archive_layer):
        """Test time range search with no matching archives."""
        from datetime import datetime, timedelta
        
        # Use past time range
        now = datetime.now()
        start = (now - timedelta(days=30)).isoformat()
        end = (now - timedelta(days=29)).isoformat()
        
        results = archive_layer.search_by_time_range(start, end)
        
        assert len(results) == 0


# ==================== Tests for Delete Archive ====================

class TestDeleteArchive:
    def test_delete_archive(self, archive_layer, sample_events):
        """Test deleting an archive."""
        import asyncio
        
        archive_id = asyncio.run(
            archive_layer.archive_session(
                session_id="delete_test",
                events=sample_events
            )
        )
        
        # Delete it
        result = archive_layer.delete_archive(archive_id)
        assert "deleted" in result.lower()
        
        # Verify it's gone
        archive = archive_layer.get_archive(archive_id)
        assert archive is None


# ==================== Tests for Cleanup ====================

class TestCleanup:
    def test_cleanup_keeps_minimum(self, archive_layer, sample_events):
        """Test cleanup keeps minimum count."""
        import asyncio
        
        # Create many archives
        for i in range(10):
            asyncio.run(
                archive_layer.archive_session(
                    session_id=f"cleanup_session_{i}",
                    events=sample_events
                )
            )
        
        # Cleanup with keep_count=5
        deleted = archive_layer.cleanup_old_archives(max_age_days=0, keep_count=5)
        
        stats = archive_layer.get_archive_stats()
        assert stats["total_archives"] == 5


# ==================== Tests for Summary Generation ====================

class TestSummaryGeneration:
    def test_simple_summary_without_llm(self, archive_layer, sample_events):
        """Test simple summary generation without LLM."""
        summary = archive_layer._simple_summary(sample_events)
        
        assert len(summary) > 0
        assert "事件" in summary

    def test_simple_findings_extraction(self, archive_layer, sample_events):
        """Test simple findings extraction."""
        findings = archive_layer._simple_findings(sample_events)
        
        assert isinstance(findings, list)


# ==================== Tests for FTS Query Sanitization ====================

class TestFTSSanitization:
    def test_sanitize_fts_query_removes_special_chars(self, archive_layer):
        """Test FTS query sanitization removes special characters."""
        query = "test:(keyword*^#"
        sanitized = archive_layer._sanitize_fts_query(query)
        
        assert ":" not in sanitized
        assert "*" not in sanitized
        assert "^" not in sanitized
        assert "#" not in sanitized

    def test_sanitize_fts_query_removes_keywords(self, archive_layer):
        """Test FTS query sanitization removes FTS keywords."""
        query = "test AND keyword OR value"
        sanitized = archive_layer._sanitize_fts_query(query)
        
        assert "AND" not in sanitized
        assert "OR" not in sanitized

    def test_sanitize_fts_query_empty(self, archive_layer):
        """Test empty query sanitization."""
        sanitized = archive_layer._sanitize_fts_query("")
        assert sanitized == ""


# ==================== Tests for Session Archives ====================

class TestSessionArchives:
    def test_get_archives_by_session(self, archive_layer, sample_events):
        """Test getting archives by session ID."""
        import asyncio
        
        # Archive same session multiple times
        asyncio.run(
            archive_layer.archive_session(
                session_id="multi_archive_session",
                events=sample_events
            )
        )
        
        archives = archive_layer.get_archives_by_session("multi_archive_session")
        
        assert len(archives) >= 1
        assert archives[0]["session_id"] == "multi_archive_session"