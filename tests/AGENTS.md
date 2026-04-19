# Module Overview - Test Suite

This directory contains test files for validating the Seed Agent system components. Tests cover Ralph Loop functionality, verification mechanisms, and core system behaviors.

---

## Test Files

| Test File | Description |
|-----------|-------------|
| `test_ralph_loop.py` | Ralph Loop execution and verification tests |
| `verify_ralph.py` | Ralph Loop verification mechanism tests |

---

## test_ralph_loop.py

**Purpose:** Tests Ralph Loop execution scenarios, completion verification, and safety mechanisms.

**Test Categories:**

### Completion Verification Tests
- Test `TEST_PASS` completion with pytest output parsing
- Test `FILE_EXISTS` completion with file creation
- Test `MARKER_FILE` completion with marker detection
- Test `GIT_CLEAN` completion with git status
- Test `CUSTOM_CHECK` completion with custom function

### Safety Limit Tests
- Test iteration limit enforcement (max 1000)
- Test duration limit enforcement (max 8 hours)
- Test safety limit exit with status report

### Context Management Tests
- Test context reset at specified intervals
- Test critical context extraction
- Test history clearing and re-injection

### State Persistence Tests
- Test state file creation
- Test crash recovery from persisted state
- Test state cleanup on completion

---

## verify_ralph.py

**Purpose:** Validates Ralph Loop verification mechanisms and edge cases.

**Test Categories:**

### Marker File Tests
- Test marker file creation and detection
- Test marker content validation
- Test marker cleanup on completion
- Test custom marker paths

### Test Pass Rate Tests
- Test pytest output parsing
- Test pass rate calculation
- Test timeout handling
- Test test command execution

### Git Clean Tests
- Test git status parsing
- Test clean vs dirty detection
- Test repository path handling

---

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_ralph_loop.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

---

## Test Dependencies

Tests require the following packages:
- `pytest`: Test framework
- `pytest-asyncio`: Async test support
- `pytest-cov`: Coverage reporting

---

## Future Tests

Planned test files to add:

| Planned Test | Purpose |
|--------------|---------|
| `test_session_db.py` | SQLite+FTS5 session storage tests |
| `test_scheduler.py` | Task scheduling tests |
| `test_autonomous.py` | Autonomous exploration tests |
| `test_llm_gateway.py` | Multi-provider gateway tests |
| `test_memory_tools.py` | Memory system tests |