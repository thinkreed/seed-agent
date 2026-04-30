"""
Tests for src/ralph_loop.py

Coverage targets:
- CompletionType enum
- RalphLoop initialization and configuration
- Completion checks (marker file, file exists, parse pass rate)
- State persistence logic
"""

import os
import sys
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import ralph_loop
from ralph_loop import RalphLoop, CompletionType

# ==================== Fixtures ====================

@pytest.fixture
def temp_seed_dir():
    """Create a temporary seed directory for state files."""
    temp_dir = tempfile.mkdtemp()
    # Patch SEED_DIR
    original_seed = ralph_loop.SEED_DIR
    ralph_loop.SEED_DIR = Path(temp_dir)
    yield temp_dir
    ralph_loop.SEED_DIR = original_seed

@pytest.fixture
def mock_agent():
    """Mock AgentLoop instance."""
    agent = MagicMock()
    agent.run = AsyncMock(return_value="Iteration response")
    return agent

@pytest.fixture
def temp_task_prompt():
    """Create a temporary task prompt file."""
    temp_dir = tempfile.mkdtemp()
    prompt_file = Path(temp_dir) / "task.md"
    prompt_file.write_text("# Test Task\n\nDo something cool.")
    yield prompt_file
    # Cleanup handled by pytest-tmpdir or just ignore for tempdir

# ==================== Tests for Initialization ====================

class TestRalphLoopInit:
    def test_init_defaults(self, mock_agent, temp_task_prompt):
        """Test initialization with defaults."""
        ralph = RalphLoop(
            agent_loop=mock_agent,
            completion_type=CompletionType.MARKER_FILE,
            completion_criteria={"marker_path": ".seed/done"},
            task_prompt_path=temp_task_prompt
        )
        
        assert ralph.completion_type == CompletionType.MARKER_FILE
        assert ralph.max_iterations == 1000
        assert ralph.max_duration == 8 * 60 * 60
        assert ralph.context_reset_interval == 5

    def test_init_custom_limits(self, mock_agent, temp_task_prompt):
        """Test initialization with custom limits."""
        ralph = RalphLoop(
            agent_loop=mock_agent,
            completion_type=CompletionType.FILE_EXISTS,
            completion_criteria={"files": ["output.txt"]},
            task_prompt_path=temp_task_prompt,
            max_iterations=10,
            max_duration=3600
        )
        
        assert ralph.max_iterations == 10
        assert ralph.max_duration == 3600

# ==================== Tests for Completion Checks ====================

class TestCompletionChecks:
    def test_check_marker_file_exists(self, mock_agent, temp_task_prompt, temp_seed_dir):
        """Test MARKER_FILE completion check."""
        marker_path = Path(temp_seed_dir) / "done"
        
        ralph = RalphLoop(
            agent_loop=mock_agent,
            completion_type=CompletionType.MARKER_FILE,
            completion_criteria={"marker_path": str(marker_path)},
            task_prompt_path=temp_task_prompt
        )
        
        assert ralph._check_marker_file() is False
        marker_path.write_text("DONE")
        assert ralph._check_marker_file() is True

    def test_check_marker_file_content(self, mock_agent, temp_task_prompt, temp_seed_dir):
        """Test MARKER_FILE completion check with content requirement."""
        marker_path = Path(temp_seed_dir) / "done"
        
        ralph = RalphLoop(
            agent_loop=mock_agent,
            completion_type=CompletionType.MARKER_FILE,
            completion_criteria={
                "marker_path": str(marker_path), 
                "marker_content": "COMPLETE"
            },
            task_prompt_path=temp_task_prompt
        )
        
        marker_path.write_text("DONE") # Wrong content
        assert ralph._check_marker_file() is False
        
        marker_path.write_text("COMPLETE")
        assert ralph._check_marker_file() is True

    def test_check_file_exists(self, mock_agent, temp_task_prompt, temp_seed_dir):
        """Test FILE_EXISTS completion check."""
        target_file = Path(temp_seed_dir) / "output.txt"
        
        ralph = RalphLoop(
            agent_loop=mock_agent,
            completion_type=CompletionType.FILE_EXISTS,
            completion_criteria={"files": [str(target_file)]},
            task_prompt_path=temp_task_prompt
        )
        
        assert ralph._check_file_exists() is False
        target_file.touch()
        assert ralph._check_file_exists() is True

    def test_check_file_exists_multiple(self, mock_agent, temp_task_prompt, temp_seed_dir):
        """Test FILE_EXISTS with multiple files."""
        f1 = Path(temp_seed_dir) / "f1.txt"
        f2 = Path(temp_seed_dir) / "f2.txt"
        
        ralph = RalphLoop(
            agent_loop=mock_agent,
            completion_type=CompletionType.FILE_EXISTS,
            completion_criteria={"files": [str(f1), str(f2)]},
            task_prompt_path=temp_task_prompt
        )
        
        f1.touch()
        assert ralph._check_file_exists() is False
        f2.touch()
        assert ralph._check_file_exists() is True

    def test_parse_test_pass_rate(self, mock_agent, temp_task_prompt):
        """Test test pass rate parsing."""
        ralph = RalphLoop(
            agent_loop=mock_agent,
            completion_type=CompletionType.TEST_PASS,
            completion_criteria={},
            task_prompt_path=temp_task_prompt
        )
        
        # Case 1: X passed, Y failed
        out1 = "================== 10 passed, 2 failed =================="
        assert ralph._parse_test_pass_rate(out1) == (10 / 12.0) * 100
        
        # Case 2: X passed
        out2 = "================== 5 passed =================="
        assert ralph._parse_test_pass_rate(out2) == 100.0
        
        # Case 3: X passed, Y error
        out3 = "3 passed, 1 error"
        assert ralph._parse_test_pass_rate(out3) == (3 / 4.0) * 100
        
        # Case 4: Empty
        assert ralph._parse_test_pass_rate("") == 0.0

# ==================== Tests for State Persistence ====================

class TestStatePersistence:
    def test_load_or_init_state_new(self, mock_agent, temp_task_prompt, temp_seed_dir):
        """Test loading state when no previous state exists."""
        ralph = RalphLoop(
            agent_loop=mock_agent,
            completion_type=CompletionType.MARKER_FILE,
            completion_criteria={"marker_path": ".seed/done"},
            task_prompt_path=temp_task_prompt
        )
        
        # Ensure state file is clean
        ralph._state_file.unlink(missing_ok=True)
        
        ralph._load_or_init_state()
        assert ralph._accumulated_duration == 0.0

    def test_persist_and_load_state(self, mock_agent, temp_task_prompt, temp_seed_dir):
        """Test persisting state and loading it back."""
        ralph = RalphLoop(
            agent_loop=mock_agent,
            completion_type=CompletionType.MARKER_FILE,
            completion_criteria={"marker_path": ".seed/done"},
            task_prompt_path=temp_task_prompt
        )
        
        ralph._accumulated_duration = 100.5
        ralph._iteration_count = 5
        ralph._state_file.parent.mkdir(parents=True, exist_ok=True)
        ralph._persist_state("Work done")
        
        # Create new instance to simulate restart
        ralph2 = RalphLoop(
            agent_loop=mock_agent,
            completion_type=CompletionType.MARKER_FILE,
            completion_criteria={"marker_path": ".seed/done"},
            task_prompt_path=temp_task_prompt
        )
        ralph2._load_or_init_state()
        
        assert ralph2._accumulated_duration == 100.5
        # _iteration_count is reset in __init__/_load_or_init_state logic depending on implementation
        # Check if it loads iteration count correctly
        assert ralph2._iteration_count == 5

    def test_state_file_location(self, mock_agent, temp_task_prompt, temp_seed_dir):
        """Test that state file is created in the correct directory."""
        ralph = RalphLoop(
            agent_loop=mock_agent,
            completion_type=CompletionType.MARKER_FILE,
            completion_criteria={"marker_path": ".seed/done"},
            task_prompt_path=temp_task_prompt
        )
        
        ralph._state_file.parent.mkdir(parents=True, exist_ok=True)
        ralph._persist_state("test")
        
        assert ralph._state_file.exists()
        # Check it is in temp dir
        assert str(temp_seed_dir) in str(ralph._state_file)
