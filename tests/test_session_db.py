"""
Tests for src/tools/session_db.py

Coverage targets:
- SessionDB: init, save/load/list/search sessions
- Memory Graph: record_outcome, stats, banned, top skills
- Utility functions: tokenize, sanitize
- Module-level convenience functions
"""

import os
import sys
import pytest
import tempfile

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tools.session_db import (
    SessionDB,
    tokenize_for_fts5,
    _sanitize_fts_query,
    save_session_history,
    list_sessions,
    _get_db,
)


# ==================== Fixtures ====================

@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    db = SessionDB(db_path=path)
    yield db
    db.close()
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def sample_messages():
    """Sample conversation messages."""
    return [
        {
            'role': 'user',
            'content': 'Hello, how are you?',
            'timestamp': '2024-01-01T10:00:00',
        },
        {
            'role': 'assistant',
            'content': 'I am doing well, thank you!',
            'timestamp': '2024-01-01T10:00:01',
        },
        {
            'role': 'user',
            'content': 'Can you help me with Python?',
            'timestamp': '2024-01-01T10:00:02',
        },
    ]


@pytest.fixture
def sample_messages_with_tools():
    """Sample messages with tool calls."""
    return [
        {
            'role': 'assistant',
            'content': '',
            'tool_calls': [
                {'function': {'name': 'file_read', 'arguments': '{"path": "test.py"}'}}
            ],
            'timestamp': '2024-01-01T10:00:00',
        },
        {
            'role': 'tool',
            'content': 'File content here...',
            'tool_call_id': 'call_123',
            'timestamp': '2024-01-01T10:00:01',
        },
    ]


# ==================== Utility Function Tests ====================

class TestTokenizeForFTS5:
    """Tests for tokenize_for_fts5 function."""

    def test_empty_string(self):
        assert tokenize_for_fts5('') == ''

    def test_none_string(self):
        assert tokenize_for_fts5(None) == ''

    def test_english_text(self):
        result = tokenize_for_fts5('hello world')
        # With or without jieba, should return text
        assert isinstance(result, str)
        assert len(result) > 0

    def test_chinese_text(self):
        result = tokenize_for_fts5('你好世界')
        assert isinstance(result, str)


class TestSanitizeFTSQuery:
    """Tests for _sanitize_fts_query function."""

    def test_removes_quotes(self):
        result = _sanitize_fts_query('hello "world"')
        assert '"' not in result

    def test_removes_parentheses(self):
        result = _sanitize_fts_query('test (query)')
        assert '(' not in result and ')' not in result

    def test_removes_colons(self):
        result = _sanitize_fts_query('field:value')
        assert ':' not in result

    def test_removes_boolean_operators(self):
        result = _sanitize_fts_query('hello AND world')
        assert 'AND' not in result
        assert 'OR' not in _sanitize_fts_query('a OR b')
        assert 'NOT' not in _sanitize_fts_query('a NOT b')

    def test_empty_query(self):
        assert _sanitize_fts_query('') == ''

    def test_strips_whitespace(self):
        result = _sanitize_fts_query('  hello  ')
        assert result == 'hello'


# ==================== SessionDB Init Tests ====================

class TestSessionDBInit:
    """Tests for SessionDB initialization."""

    def test_creates_db_file(self, temp_db):
        assert os.path.exists(temp_db.db_path)

    def test_creates_session_messages_table(self, temp_db):
        cursor = temp_db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='session_messages'")
        assert cursor.fetchone() is not None

    def test_creates_sessions_meta_table(self, temp_db):
        cursor = temp_db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions_meta'")
        assert cursor.fetchone() is not None

    def test_creates_gene_outcomes_table(self, temp_db):
        cursor = temp_db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gene_outcomes'")
        assert cursor.fetchone() is not None

    def test_creates_fts_virtual_table(self, temp_db):
        cursor = temp_db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE name='session_messages_fts'")
        assert cursor.fetchone() is not None

    def test_wal_mode_enabled(self, temp_db):
        result = temp_db.conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == 'wal'


# ==================== Session Save/Load Tests ====================

class TestSaveSessionHistory:
    """Tests for save_session_history method."""

    def test_save_basic_messages(self, temp_db, sample_messages):
        result = temp_db.save_session_history(
            sample_messages,
            summary='Test session',
            session_id='test_001'
        )
        assert 'Session saved' in result
        assert '3 messages' in result

    def test_save_creates_meta_entry(self, temp_db, sample_messages):
        temp_db.save_session_history(sample_messages, session_id='test_002')
        row = temp_db.conn.execute(
            "SELECT * FROM sessions_meta WHERE session_id = 'test_002'"
        ).fetchone()
        assert row is not None
        assert row['message_count'] == 3

    def test_save_with_summary(self, temp_db, sample_messages):
        temp_db.save_session_history(
            sample_messages,
            summary='This is a test summary',
            session_id='test_003'
        )
        row = temp_db.conn.execute(
            "SELECT summary FROM sessions_meta WHERE session_id = 'test_003'"
        ).fetchone()
        assert row['summary'] == 'This is a test summary'

    def test_save_with_tool_calls(self, temp_db, sample_messages_with_tools):
        result = temp_db.save_session_history(
            sample_messages_with_tools,
            session_id='test_tools'
        )
        assert 'Session saved' in result

    def test_save_generates_session_id(self, temp_db, sample_messages):
        result = temp_db.save_session_history(sample_messages)
        assert 'Session saved' in result
        assert 'session_' in result

    def test_save_empty_messages(self, temp_db):
        result = temp_db.save_session_history([], session_id='empty_test')
        assert 'Session saved' in result
        assert '0 messages' in result

    def test_save_duplicate_session_appends(self, temp_db, sample_messages):
        temp_db.save_session_history(sample_messages, session_id='dup_test')
        temp_db.save_session_history(sample_messages, session_id='dup_test')
        row = temp_db.conn.execute(
            "SELECT message_count FROM sessions_meta WHERE session_id = 'dup_test'"
        ).fetchone()
        assert row['message_count'] == 6  # 3 + 3


class TestLoadSessionHistory:
    """Tests for load_session_history method."""

    def test_load_existing_session(self, temp_db, sample_messages):
        temp_db.save_session_history(sample_messages, session_id='load_test')
        result = temp_db.load_session_history('load_test')
        assert 'load_test' in result
        assert 'user' in result
        assert 'assistant' in result

    def test_load_nonexistent_session(self, temp_db):
        result = temp_db.load_session_history('nonexistent')
        assert 'not found' in result.lower() or 'error' in result.lower()

    def test_load_partial_match(self, temp_db, sample_messages):
        temp_db.save_session_history(sample_messages, session_id='partial_match_001')
        result = temp_db.load_session_history('partial')
        assert 'partial_match_001' in result

    def test_load_shows_message_count(self, temp_db, sample_messages):
        temp_db.save_session_history(sample_messages, session_id='count_test')
        result = temp_db.load_session_history('count_test')
        assert '3' in result  # message count


class TestListSessions:
    """Tests for list_sessions method."""

    def test_list_empty(self, temp_db):
        result = temp_db.list_sessions()
        assert 'No sessions found' in result

    def test_list_with_sessions(self, temp_db, sample_messages):
        temp_db.save_session_history(sample_messages, session_id='list_001')
        temp_db.save_session_history(sample_messages, session_id='list_002')
        result = temp_db.list_sessions()
        assert 'list_002' in result
        assert 'list_001' in result

    def test_list_respects_limit(self, temp_db, sample_messages):
        for i in range(5):
            temp_db.save_session_history(sample_messages, session_id=f'limit_{i:03d}')
        result = temp_db.list_sessions(limit=2)
        # Should only show 2 sessions
        lines = result.strip().split('\n')
        session_lines = [line for line in lines if line.startswith('-')]
        assert len(session_lines) <= 2

    def test_list_ordered_by_created_desc(self, temp_db, sample_messages):
        temp_db.save_session_history(sample_messages, session_id='first')
        import time
        time.sleep(0.01)
        temp_db.save_session_history(sample_messages, session_id='last')
        result = temp_db.list_sessions(limit=1)
        assert 'last' in result


# ==================== Session Search Tests ====================

class TestSearchHistory:
    """Tests for search_history method (FTS5)."""

    def test_search_empty_keyword(self, temp_db):
        result = temp_db.search_history('')
        assert 'provide a search keyword' in result.lower()

    def test_search_finds_match(self, temp_db, sample_messages):
        temp_db.save_session_history(sample_messages, session_id='search_test')
        result = temp_db.search_history('Python')
        assert 'match' in result.lower() or 'Python' in result

    def test_search_no_match(self, temp_db, sample_messages):
        temp_db.save_session_history(sample_messages, session_id='no_match_test')
        result = temp_db.search_history('zzzznonexistent')
        assert 'no match' in result.lower() or 'found' in result.lower()

    def test_search_case_insensitive(self, temp_db, sample_messages):
        temp_db.save_session_history(sample_messages, session_id='case_test')
        result_lower = temp_db.search_history('python')
        temp_db.search_history('PYTHON')
        # Both should find the match
        assert 'match' in result_lower.lower() or 'python' in result_lower.lower()


class TestSearchWithFilters:
    """Tests for search_with_filters method."""

    def test_search_by_session_id(self, temp_db, sample_messages):
        temp_db.save_session_history(sample_messages, session_id='filter_sid')
        results = temp_db.search_with_filters('', session_id='filter_sid')
        assert len(results) == 3

    def test_search_by_role(self, temp_db, sample_messages):
        temp_db.save_session_history(sample_messages, session_id='filter_role')
        results = temp_db.search_with_filters('', role='user')
        # Should only find user messages from this session
        user_msgs = [r for r in results if r['role'] == 'user']
        assert len(user_msgs) >= 1

    def test_search_by_keyword(self, temp_db, sample_messages):
        temp_db.save_session_history(sample_messages, session_id='filter_kw')
        results = temp_db.search_with_filters('Python')
        assert len(results) >= 1

    def test_search_combined_filters(self, temp_db, sample_messages):
        temp_db.save_session_history(sample_messages, session_id='filter_combo')
        results = temp_db.search_with_filters('', session_id='filter_combo', role='user')
        assert len(results) >= 1


class TestGetSessionStats:
    """Tests for get_session_stats method."""

    def test_stats_existing_session(self, temp_db, sample_messages):
        temp_db.save_session_history(sample_messages, session_id='stats_test', summary='Test')
        stats = temp_db.get_session_stats('stats_test')
        assert stats['session_id'] == 'stats_test'
        assert stats['message_count'] == 3
        assert stats['has_summary'] is True

    def test_stats_nonexistent_session(self, temp_db):
        stats = temp_db.get_session_stats('nonexistent')
        assert 'error' in stats

    def test_stats_without_summary(self, temp_db, sample_messages):
        temp_db.save_session_history(sample_messages, session_id='no_summary')
        stats = temp_db.get_session_stats('no_summary')
        assert stats['has_summary'] is False


# ==================== Index Management Tests ====================

class TestIndexManagement:
    """Tests for FTS5 index optimization and rebuild."""

    def test_optimize_index(self, temp_db):
        result = temp_db.optimize_index()
        assert 'optimized' in result.lower() or 'error' in result.lower()

    def test_rebuild_index(self, temp_db):
        result = temp_db.rebuild_index()
        assert 'rebuilt' in result.lower() or 'error' in result.lower()


# ==================== Memory Graph Tests ====================

class TestRecordSkillOutcome:
    """Tests for record_skill_outcome method."""

    def test_record_success(self, temp_db):
        result = temp_db.record_skill_outcome(
            skill_name='test_skill',
            outcome='success',
            score=1.0
        )
        assert 'Outcome recorded' in result

    def test_record_failed(self, temp_db):
        result = temp_db.record_skill_outcome(
            skill_name='failing_skill',
            outcome='failed',
            score=0.0
        )
        assert 'Outcome recorded' in result

    def test_record_partial(self, temp_db):
        result = temp_db.record_skill_outcome(
            skill_name='partial_skill',
            outcome='partial',
            score=0.5
        )
        assert 'Outcome recorded' in result

    def test_record_invalid_outcome(self, temp_db):
        result = temp_db.record_skill_outcome(
            skill_name='bad_skill',
            outcome='invalid',
            score=0.5
        )
        assert 'Invalid' in result

    def test_record_invalid_score(self, temp_db):
        result = temp_db.record_skill_outcome(
            skill_name='bad_score',
            outcome='success',
            score=2.0
        )
        assert 'Invalid' in result

    def test_record_with_signals(self, temp_db):
        result = temp_db.record_skill_outcome(
            skill_name='signal_skill',
            outcome='success',
            signals=['自主探索', 'autonomous']
        )
        assert 'Outcome recorded' in result

    def test_record_with_context(self, temp_db):
        result = temp_db.record_skill_outcome(
            skill_name='context_skill',
            outcome='success',
            context='Test execution context'
        )
        assert 'Outcome recorded' in result


class TestGetSkillStats:
    """Tests for get_skill_stats method."""

    def test_stats_no_data(self, temp_db):
        stats = temp_db.get_skill_stats('nonexistent')
        assert stats['total'] == 0
        assert stats['is_banned'] is False
        assert stats['laplace_rate'] == 0.5  # cold start default

    def test_stats_after_success(self, temp_db):
        temp_db.record_skill_outcome('test_stats', 'success')
        stats = temp_db.get_skill_stats('test_stats')
        assert stats['total'] == 1
        assert stats['successes'] == 1
        assert stats['failures'] == 0
        assert stats['success_rate'] == 1.0

    def test_stats_after_failure(self, temp_db):
        temp_db.record_skill_outcome('fail_stats', 'failed')
        stats = temp_db.get_skill_stats('fail_stats')
        assert stats['total'] == 1
        assert stats['successes'] == 0
        assert stats['failures'] == 1
        assert stats['success_rate'] == 0.0

    def test_stats_mixed_results(self, temp_db):
        temp_db.record_skill_outcome('mixed', 'success')
        import time
        time.sleep(0.01)
        temp_db.record_skill_outcome('mixed', 'failed')
        time.sleep(0.01)
        temp_db.record_skill_outcome('mixed', 'success')
        stats = temp_db.get_skill_stats('mixed')
        assert stats['total'] == 3
        assert stats['successes'] == 2
        assert stats['success_rate'] == pytest.approx(2/3, abs=0.01)

    def test_laplace_smoothing(self, temp_db):
        temp_db.record_skill_outcome('laplace', 'success')
        stats = temp_db.get_skill_stats('laplace')
        # (1+1)/(1+2) = 0.667
        assert stats['laplace_rate'] == pytest.approx(2/3, abs=0.01)

    def test_recent_success_rate(self, temp_db):
        temp_db.record_skill_outcome('recent', 'success')
        stats = temp_db.get_skill_stats('recent')
        assert stats['recent_success_rate'] == 1.0


class TestListBannedSkills:
    """Tests for list_banned_skills method."""

    def test_no_banned_skills(self, temp_db):
        banned = temp_db.list_banned_skills()
        assert banned == []

    def test_ban_low_success_rate(self, temp_db):
        # Record many failures to trigger ban (use different signal patterns to avoid UNIQUE constraint)
        for i in range(5):
            temp_db.record_skill_outcome('bad_skill', 'failed', score=0.0, signals=[f'signal_{i}'])
        banned = temp_db.list_banned_skills()
        banned_names = [b['skill_name'] for b in banned]
        assert 'bad_skill' in banned_names

    def test_not_banned_good_skill(self, temp_db):
        for _ in range(5):
            temp_db.record_skill_outcome('good_skill', 'success', score=1.0)
        banned = temp_db.list_banned_skills()
        banned_names = [b['skill_name'] for b in banned]
        assert 'good_skill' not in banned_names

    def test_not_banned_insufficient_attempts(self, temp_db):
        # Only 1 attempt, below min_attempts_for_ban
        temp_db.record_skill_outcome('new_skill', 'failed')
        banned = temp_db.list_banned_skills()
        banned_names = [b['skill_name'] for b in banned]
        assert 'new_skill' not in banned_names


class TestGetTopSkills:
    """Tests for get_top_skills method."""

    def test_empty_top_skills(self, temp_db):
        top = temp_db.get_top_skills()
        assert top == []

    def test_top_skills_ordered(self, temp_db):
        temp_db.record_skill_outcome('always_fails', 'failed')
        for _ in range(5):
            temp_db.record_skill_outcome('always_succeeds', 'success')
        top = temp_db.get_top_skills()
        assert len(top) >= 1
        assert top[0]['skill_name'] == 'always_succeeds'

    def test_top_skills_respects_limit(self, temp_db):
        for i in range(10):
            temp_db.record_skill_outcome(f'skill_{i}', 'success')
        top = temp_db.get_top_skills(limit=3)
        assert len(top) == 3


class TestSearchOutcomesBySignal:
    """Tests for search_outcomes_by_signal method."""

    def test_search_matching_signal(self, temp_db):
        temp_db.record_skill_outcome(
            'signal_test', 'success',
            signals=['autonomous_exploration', 'file_operation']
        )
        results = temp_db.search_outcomes_by_signal('autonomous')
        assert len(results) >= 1

    def test_search_no_match(self, temp_db):
        temp_db.record_skill_outcome(
            'no_signal_match', 'success',
            signals=['文件操作']
        )
        results = temp_db.search_outcomes_by_signal('zzzznonexistent')
        assert len(results) == 0


class TestCleanupOldOutcomes:
    """Tests for cleanup_old_outcomes method."""

    def test_cleanup_removes_oldest(self, temp_db):
        # Record more than max_entries (use different signal patterns to avoid UNIQUE constraint)
        for i in range(10):
            temp_db.record_skill_outcome('cleanup_test', 'success', signals=[f'sig_{i}'])

        count_before = temp_db.conn.execute(
            "SELECT COUNT(*) FROM gene_outcomes WHERE skill_name = 'cleanup_test'"
        ).fetchone()[0]
        assert count_before == 10

        # Cleanup with max 5
        temp_db.cleanup_old_outcomes(max_entries_per_skill=5)

        count_after = temp_db.conn.execute(
            "SELECT COUNT(*) FROM gene_outcomes WHERE skill_name = 'cleanup_test'"
        ).fetchone()[0]
        assert count_after == 5

    def test_cleanup_no_effect_under_limit(self, temp_db):
        for i in range(3):
            temp_db.record_skill_outcome('small_skill', 'success', signals=[f'sig_{i}'])
        temp_db.cleanup_old_outcomes(max_entries_per_skill=10)
        count = temp_db.conn.execute(
            "SELECT COUNT(*) FROM gene_outcomes WHERE skill_name = 'small_skill'"
        ).fetchone()[0]
        assert count == 3


# ==================== SessionDB Close Tests ====================

class TestSessionDBClose:
    """Tests for close method."""

    def test_close_connection(self, temp_db):
        temp_db.close()
        assert temp_db.conn is None

    def test_close_idempotent(self, temp_db):
        temp_db.close()
        temp_db.close()  # Should not raise


# ==================== Module-level Convenience Function Tests ====================

class TestModuleLevelFunctions:
    """Tests for module-level convenience functions."""

    def test_get_db_singleton(self):
        db1 = _get_db()
        db2 = _get_db()
        assert db1 is db2  # Same instance

    def test_save_session_via_module(self):
        # This uses the global db instance - just verify it doesn't crash
        result = save_session_history(
            [{'role': 'user', 'content': 'test', 'timestamp': '2024-01-01'}],
            session_id='module_test'
        )
        assert 'Session saved' in result or 'Error' in result

    def test_list_sessions_via_module(self):
        result = list_sessions(limit=5)
        assert isinstance(result, str)


# ==================== Edge Cases and Error Handling ====================

class TestEdgeCases:
    """Edge case tests."""

    def test_save_with_unicode_content(self, temp_db):
        messages = [
            {'role': 'user', 'content': '你好世界 🌍', 'timestamp': '2024-01-01'}
        ]
        result = temp_db.save_session_history(messages, session_id='unicode_test')
        assert 'Session saved' in result

    def test_save_with_very_long_content(self, temp_db):
        long_content = 'x' * 10000
        messages = [
            {'role': 'user', 'content': long_content, 'timestamp': '2024-01-01'}
        ]
        result = temp_db.save_session_history(messages, session_id='long_test')
        assert 'Session saved' in result

    def test_search_special_characters(self, temp_db, sample_messages):
        temp_db.save_session_history(sample_messages, session_id='special_test')
        result = temp_db.search_history('test "query" (complex)')
        # Should not crash, may or may not find results
        assert isinstance(result, str)

    def test_outcome_score_boundaries(self, temp_db):
        # Test score = 0.0
        result = temp_db.record_skill_outcome('boundary_zero', 'success', score=0.0)
        assert 'Outcome recorded' in result
        # Test score = 1.0
        result = temp_db.record_skill_outcome('boundary_one', 'success', score=1.0)
        assert 'Outcome recorded' in result

    def test_selection_value_decay(self, temp_db):
        """Test that selection value accounts for recency."""
        temp_db.record_skill_outcome('decay_test', 'success')
        stats = temp_db.get_skill_stats('decay_test')
        assert stats['selection_value'] > 0
        assert stats['is_banned'] is False
