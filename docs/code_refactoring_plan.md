# Comprehensive Code Refactoring Plan

## Executive Summary

### Project Overview

**Seed-Agent Codebase Analysis Results**

| Metric | Value |
|--------|-------|
| Total files exceeding 300 lines | **63 files** |
| Source files exceeding 300 lines | **37 files** |
| Test files exceeding 300 lines | **26 files** |
| Total lines requiring refactoring | **~35,000 lines** |
| Largest single file | `src/harness.py` (1722 lines) |

### Refactoring Goal

Bring all source files below **300 lines** while:
- Maintaining backward compatibility
- Preserving all functionality
- Following single responsibility principle
- Eliminating code duplication
- Ensuring all tests pass

### Top 10 Files by Line Count

| Rank | File | Current Lines | Proposed Extracts | Target Lines |
|------|------|---------------|-------------------|--------------|
| 1 | `src/harness.py` | 1722 | 9 modules | ~250 |
| 2 | `src/tools/session_db.py` | 1292 | 8 modules | ~250 |
| 3 | `src/client.py` | 1195 | 7 modules | ~250 |
| 4 | `src/collaboration.py` | 1194 | 6 modules | ~250 |
| 5 | `src/context_engineering.py` | 1015 | 3 modules | ~280 |
| 6 | `src/security/single_purpose_tools.py` | 933 | 5 modules | ~100 |
| 7 | `src/autonomous.py` | 926 | 6 modules | ~200 |
| 8 | `src/tools/user_modeling.py` | 886 | 4 modules | ~200 |
| 9 | `src/tools/skill_loader.py` | 858 | 3 modules | ~250 |
| 10 | `src/tools/memory_tools.py` | 827 | cleanup + 3 modules | ~200 |

---

## Refactoring Principles

### Why 300 Lines?

| Reason | Explanation |
|--------|-------------|
| **Readability** | Files under 300 lines can be read in one session |
| **Maintainability** | Smaller files reduce cognitive load |
| **Single Responsibility** | Each file should have one clear purpose |
| **Testability** | Smaller units are easier to test comprehensively |
| **Reviewability** | Code reviews are more effective on focused files |

### Core Principles

1. **Single Responsibility**: Each extracted module handles one cohesive responsibility
2. **Backward Compatibility**: Public APIs unchanged; internal restructuring only
3. **Zero Circular Dependencies**: Verify import graph after each extraction
4. **Atomic Commits**: One extraction = one commit with tests passing
5. **Progressive Disclosure**: Use underscore prefix (`_module`) for internal submodules

### Naming Convention

```
Parent file: src/harness.py (public)
Extracted:   src/harness/_context_builder.py (internal/private)

Import pattern:
  from src.harness._context_builder import ContextBuilder  (internal use)
  from src.harness import Harness  (public API unchanged)
```

---

## File Inventory

### Source Files (37 files exceeding 300 lines)

#### Core Engine Files (8 files)

| File | Lines | Module |
|------|-------|--------|
| `src/harness.py` | 1722 | Controller |
| `src/client.py` | 1195 | LLM Gateway |
| `src/context_engineering.py` | 1015 | Context optimization |
| `src/autonomous.py` | 926 | Autonomous explorer |
| `src/agent_loop.py` | 807 | Agent loop |
| `src/session_event_stream.py` | 556 | Event stream |
| `src/lifecycle_hooks.py` | 623 | Hook registry |
| `src/builtin_hooks.py` | 453 | Built-in hooks |

#### Collaboration Files (2 files)

| File | Lines | Module |
|------|-------|--------|
| `src/collaboration.py` | 1194 | Multi-agent orchestration |
| `src/tools/collaboration_tools.py` | 605 | Collaboration tools |

#### Security Module Files (8 files)

| File | Lines | Purpose |
|------|-------|--------|
| `src/security/single_purpose_tools.py` | 933 | Single-purpose tool factory |
| `src/security/credential_vault.py` | 760 | Credential encryption/storage |
| `src/security/credential_proxy.py` | 607 | External request proxy |
| `src/security/credential_isolated_sandbox.py` | 598 | Credential isolation |
| `src/security/risk_classifier.py` | 490 | Risk classification |
| `src/security/tool_expander.py` | 429 | Progressive tool expansion |
| `src/security/secure_sandbox.py` | 418 | Secure execution sandbox |
| `src/security/secure_harness.py` | 335 | Secure harness wrapper |

#### Tools Module Files (8 files)

| File | Lines | Purpose |
|------|-------|--------|
| `src/tools/session_db.py` | 1292 | SQLite+FTS5 session storage |
| `src/tools/user_modeling.py` | 886 | User profiling |
| `src/tools/skill_loader.py` | 858 | Skill loading/selection |
| `src/tools/memory_tools.py` | 827 | Memory integration layer |
| `src/tools/long_term_archive.py` | 729 | L5 archive layer |
| `src/tools/builtin_tools.py` | 707 | 5 core tools |
| `src/tools/collaboration_tools.py` | 605 | Collaboration tools |
| `src/tools/subagent_tools.py` | 318 | Subagent management |

#### Supporting Files (13 files)

| File | Lines | Purpose |
|------|-------|--------|
| `src/sandbox.py` | 547 | Execution sandbox |
| `src/ralph_loop.py` | 538 | Long-cycle executor |
| `src/request_queue.py` | 526 | Request queue |
| `src/subagent_manager.py` | 499 | Subagent lifecycle |
| `src/subagent.py` | 420 | Subagent instance |
| `src/scheduler.py` | 389 | Task scheduling |
| `src/background_task_registry.py` | 385 | Background tasks |
| `src/llm_client.py` | 379 | LLM client wrapper |
| `src/memory_manager.py` | 371 | Memory hierarchy |
| `src/rate_limit_db.py` | 365 | Rate limit persistence |
| `src/shared_config.py` | 357 | Shared configuration |
| `src/rate_limiter.py` | 350 | Rate limiting |
| `src/models.py` | 343 | Pydantic models |

### Test Files (26 files exceeding 300 lines)

| File | Lines | Source Coverage |
|------|-------|-----------------|
| `tests/test_security.py` | 855 | security module |
| `tests/test_autonomous.py` | 740 | autonomous.py |
| `tests/test_subagent_manager.py` | 704 | subagent_manager.py |
| `tests/test_subagent.py` | 677 | subagent.py |
| `tests/test_harness.py` | 599 | harness.py |
| `tests/test_agent_loop.py` | 587 | agent_loop.py |
| `tests/test_skill_loader.py` | 549 | skill_loader.py |
| `tests/test_session_db.py` | 524 | session_db.py |
| `tests/test_models.py` | 514 | models.py |
| `tests/test_builtin_tools.py` | 470 | builtin_tools.py |
| `tests/test_lifecycle_hooks.py` | 461 | lifecycle_hooks.py |
| `tests/test_session_event_stream.py` | 449 | session_event_stream.py |
| `tests/test_rate_limiter.py` | 433 | rate_limiter.py |
| `tests/test_sandbox.py` | 426 | sandbox.py |
| `tests/test_credential_vault.py` | 421 | credential_vault.py |
| `tests/test_context_engineering.py` | 405 | context_engineering.py |
| `tests/test_credential_proxy.py` | 400 | credential_proxy.py |
| `tests/test_request_queue_turn_ticket.py` | 396 | request_queue.py |
| `tests/test_long_term_archive.py` | 394 | long_term_archive.py |
| `tests/test_collaboration.py` | 386 | collaboration.py |
| `tests/test_llm_client.py` | 370 | llm_client.py |
| `tests/test_client.py` | 339 | client.py |
| `tests/test_user_modeling.py` | 304 | user_modeling.py |
| `tests/test_models.py` | 514 | models.py |

---

## Phase 1: Foundation (Shared Utilities)

### Goal

Eliminate code duplication and create foundation modules for subsequent phases.

### Identified Duplications

| Duplication | Location 1 | Location 2 | Lines | Solution |
|-------------|------------|------------|-------|----------|
| `SENSITIVE_ENV_VARS` | `credential_isolated_sandbox.py:43-82` | `single_purpose_tools.py:1016-1044` | 40 | Extract to `security/constants.py` |
| `tokenize_for_fts5` | `session_db.py:91-113` | Used by `long_term_archive.py` | 180 | Extract to `tools/fts_utils.py` |
| `sanitize_fts_query` | `session_db.py:135-177` | Used by `long_term_archive.py` | 42 | Extract to `tools/fts_utils.py` |
| DB singleton pattern | `session_db.py`, `user_modeling.py`, `long_term_archive.py` | 3 files | ~200 each | Extract to `tools/db_base.py` |
| `_get_safe_environment` | `single_purpose_tools.py:837` | Similar logic in `credential_isolated_sandbox.py:464` | ~50 | Extract to `security/utils.py` |

### Extraction Plan

#### 1.1: Create `src/security/constants.py`

**Extract from**: 
- `credential_isolated_sandbox.py` → `BLOCKED_ENV_VARS`
- `single_purpose_tools.py` → `_SENSITIVE_ENV_VARS`

**Target**: ~60 lines

```python
# src/security/constants.py

SENSITIVE_ENV_VARS = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "BAILIAN_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    # ... (unified list of ~40 variables)
]
```

**Atomic Commit**: `refactor(security): extract SENSITIVE_ENV_VARS to constants.py`

---

#### 1.2: Create `src/tools/fts_utils.py`

**Extract from**: `session_db.py:91-177`

**Target**: ~180 lines

```python
# src/tools/fts_utils.py

_HAS_JIEBA: bool
_MAX_CACHE_TEXT_LENGTH: int
_CACHE_MAXSIZE: int

def tokenize_for_fts5(text: str) -> str:
    """Tokenize text for FTS5 indexing with jieba support"""

@lru_cache(maxsize=_CACHE_MAXSIZE)
def _tokenize_cached(text: str) -> str:
    """Cached tokenization"""

_FTS_SPECIAL_CHARS: str
_UNICODE_SPECIAL_CHARS: str
_FTS_SANITIZE_TABLE: dict
_FTS_KEYWORDS_PATTERN: Pattern

def sanitize_fts_query(query: str) -> str:
    """Sanitize FTS5 query to prevent syntax errors"""
```

**Atomic Commit**: `refactor(tools): extract FTS5 tokenizer to fts_utils.py`

---

#### 1.3: Create `src/tools/db_base.py`

**Extract from**: 3 files sharing singleton pattern

**Target**: ~200 lines

```python
# src/tools/db_base.py

class SingletonDB:
    """Base class for singleton database managers"""
    
    _instance: ClassVar[Optional[Self]]
    _initialized: ClassVar[bool]
    _lock: ClassVar[threading.Lock]
    
    def __new__(cls, db_path: str) -> Self:
        """Singleton pattern implementation"""
    
    def _ensure_conn(self) -> sqlite3.Connection:
        """Ensure connection exists"""
    
    def close(self) -> None:
        """Close database connection"""
    
    def _create_schema(self) -> None:
        """Override in subclass"""
```

**Atomic Commit**: `refactor(tools): extract DB singleton base to db_base.py`

---

#### 1.4: Create `src/tools/path_validation.py`

**Extract from**: `builtin_tools.py:validate_path_*`

**Target**: ~150 lines

```python
# src/tools/path_validation.py

def validate_path_safety(path: str, allowed_dirs: List[str]) -> bool:
    """Validate path is within allowed directories"""

def resolve_path(path: str, base_dir: str) -> Path:
    """Resolve relative path to absolute"""

def is_path_in_allowed_dirs(path: Path, allowed_dirs: List[str]) -> bool:
    """Check if resolved path is in allowed dirs"""
```

**Atomic Commit**: `refactor(tools): extract path validation to path_validation.py`

---

#### 1.5: Create `src/security/utils.py`

**Extract from**: `single_purpose_tools.py`, `credential_isolated_sandbox.py`

**Target**: ~50 lines

```python
# src/security/utils.py

from src.security.constants import SENSITIVE_ENV_VARS

def get_safe_environment() -> Dict[str, str]:
    """Return environment dict excluding sensitive variables"""
```

**Atomic Commit**: `refactor(security): extract get_safe_environment to utils.py`

---

### Phase 1 Summary

| Task | Lines Extracted | Risk Level | Test Coverage |
|------|-----------------|------------|---------------|
| 1.1 constants.py | 60 | LOW | Unit tests for list completeness |
| 1.2 fts_utils.py | 180 | LOW | FTS5 search tests |
| 1.3 db_base.py | 200 | MEDIUM | Connection lifecycle tests |
| 1.4 path_validation.py | 150 | LOW | Path traversal tests |
| 1.5 utils.py | 50 | LOW | Environment filtering tests |

---

## Phase 2: Core Files

### Goal

Reduce 6 largest core files to below 300 lines.

### Dependency-Based Execution Order

| Wave | Files | Dependencies | Parallel Execution |
|------|-------|--------------|-------------------|
| **Wave 2.1** | `session_db.py`, `client.py`, `collaboration.py` | None | ✓ Parallel |
| **Wave 2.2** | `autonomous.py`, `context_engineering.py` | None | ✓ Parallel |
| **Wave 2.3** | `harness.py` | Depends on `context_engineering.py` | Sequential |

---

### 2.1: Extract from `src/harness.py` (1722 → ~250)

**Current Structure** (from LSP analysis):
- Class `Harness` (line 119-1860): Main controller
- Class `HarnessManager` (line 1873-2002): Harness lifecycle
- Class `CycleResult`, `ToolExecutionMetrics` (dataclasses)
- 40+ methods for execution, routing, streaming, hooks

**Extraction Plan**:

| Module | Lines | Methods Extracted |
|--------|-------|-------------------|
| `harness/_context_builder.py` | ~250 | `_build_context_from_session`, `_build_context_from_session_async`, `_get_events_since_last_summary` |
| `harness/_tool_router.py` | ~280 | `_route_tool_calls`, `_route_tool_calls_with_hooks`, `_execute_tools_parallel`, `_execute_tools_parallel_with_hooks` |
| `harness/_lifecycle_hooks.py` | ~200 | `_trigger_hook`, `_build_session_end_ctx` |
| `harness/_streaming.py` | ~300 | `stream_conversation`, `stream_resume_with_user_response`, `_process_tool_delta` |
| `harness/_metrics.py` | ~180 | `ToolExecutionMetrics`, `get_metrics`, `clear_metrics`, `_start_tool_span`, `_finish_tool_span` |
| `harness/_resume.py` | ~250 | `resume_with_user_response` |
| `harness/_write_conflict.py` | ~180 | `_check_write_conflicts` |
| `harness/_single_tool.py` | ~200 | `_execute_single_tool_with_hooks`, `_execute_single_tool_with_metrics` |
| `harness/_manager.py` | ~250 | `HarnessManager` class |

**Atomic Commits** (sequential due to dependencies):
```
refactor(harness): extract context builder to _context_builder.py
refactor(harness): extract tool router to _tool_router.py
refactor(harness): extract lifecycle hooks to _lifecycle_hooks.py
refactor(harness): extract streaming methods to _streaming.py
refactor(harness): extract metrics to _metrics.py
refactor(harness): extract resume logic to _resume.py
refactor(harness): extract write conflict checker to _write_conflict.py
refactor(harness): extract single tool execution to _single_tool.py
refactor(harness): extract manager to _manager.py
```

---

### 2.2: Extract from `src/tools/session_db.py` (1292 → ~250)

**Current Structure** (from LSP analysis):
- Class `SessionDB` (line 193-1412): SQLite+FTS5 singleton
- FTS5 tokenizer functions
- Memory Graph skill outcome methods
- Session CRUD operations
- Search and filter methods

**Extraction Plan**:

| Module | Lines | Methods Extracted |
|--------|-------|-------------------|
| `tools/session/_schema.py` | ~250 | `_create_schema`, `_create_session_messages_schema`, `_create_sessions_meta_schema`, `_create_gene_outcomes_schema`, `_create_gene_outcomes_triggers` |
| `tools/session/_skill_outcomes.py` | ~280 | `record_skill_outcome`, `_get_skill_basic_stats`, `_get_skill_recent_stats`, `_compute_selection_value`, `get_skill_stats`, `list_banned_skills`, `get_top_skills`, `search_outcomes_by_signal` |
| `tools/session/_search.py` | ~280 | `search_history`, `search_with_filters`, `_fallback_search`, `_highlight_match`, `_get_context`, `_apply_filters` |
| `tools/session/_save.py` | ~200 | `save_session_history`, `_build_message_batches`, `_insert_fts_index`, `_upsert_session_meta` |
| `tools/session/_load.py` | ~150 | `load_session_history`, `_find_session`, `_format_session_message`, `list_sessions` |
| `tools/session/_cleanup.py` | ~150 | `cleanup_old_outcomes`, `optimize_index`, `rebuild_index`, `get_session_stats` |

**Atomic Commits**:
```
refactor(session): extract schema creation to _schema.py
refactor(session): extract skill outcomes to _skill_outcomes.py
refactor(session): extract search methods to _search.py
refactor(session): extract save operations to _save.py
refactor(session): extract load operations to _load.py
refactor(session): extract cleanup methods to _cleanup.py
```

---

### 2.3: Extract from `src/client.py` (1195 → ~250)

**Current Structure** (from LSP analysis):
- Class `LLMGateway` (line 279-1195): Multi-provider gateway
- Class `FallbackChain` (line 201-274): Provider failover
- Class `TimeoutConfig` (line 155-200): Dynamic timeout
- Retry logic, rate limiting, streaming, persistence

**Extraction Plan**:

| Module | Lines | Classes/Methods Extracted |
|--------|-------|---------------------------|
| `client/_fallback_chain.py` | ~150 | `FallbackChain` class |
| `client/_timeout.py` | ~100 | `TimeoutConfig`, `get_timeout`, `get_dynamic_timeout` |
| `client/_rate_limit_integration.py` | ~200 | `_init_rate_limiting`, `_load_queue_config`, `_wait_for_turn_and_acquire`, `_execute_with_concurrency_and_rate_limit` |
| `client/_retry.py` | ~180 | `_should_continue_retry`, `_get_retry_wait_time`, `_try_provider_with_retry` |
| `client/_streaming.py` | ~250 | `_stream_chat_completion_with_fallback_internal`, `_stream_with_retry`, `_stream_fallback_providers`, `_stream_chat_completion_single` |
| `client/_persistence.py` | ~200 | `restore_state`, `save_state`, `start_persistence_loop`, `_persistence_loop`, `get_persistence_stats` |
| `client/_utils.py` | ~150 | `_calc_duration_ms`, `_estimate_stream_tokens`, `_resolve_api_key`, `_iterate_fallback_models` |

**Atomic Commits**:
```
refactor(client): extract FallbackChain to _fallback_chain.py
refactor(client): extract TimeoutConfig to _timeout.py
refactor(client): extract rate limit integration to _rate_limit_integration.py
refactor(client): extract retry logic to _retry.py
refactor(client): extract streaming handlers to _streaming.py
refactor(client): extract state persistence to _persistence.py
refactor(client): extract utility functions to _utils.py
```

---

### 2.4: Extract from `src/collaboration.py` (1194 → ~250)

**Current Structure** (from LSP analysis):
- Class `MultiBrainOneHandOrchestrator` (line 94-492)
- Class `OneBrainMultiHandOrchestrator` (line 495-819)
- Class `MultiBrainMultiHandOrchestrator` (line 822-1270)
- Class `InterAgentMessageBus` (line 1273-1425)
- Data classes: `AgentInstance`, `AnalysisResult`, `ExecutionResult`, `CoordinationResult`

**Extraction Plan**:

| Module | Lines | Classes Extracted |
|--------|-------|-------------------|
| `collaboration/_types.py` | ~100 | `CollaborationMode`, `AgentInstance`, `AnalysisResult`, `ExecutionResult`, `CoordinationResult` |
| `collaboration/_message_bus.py` | ~250 | `InterAgentMessageBus` |
| `collaboration/_multi_brain_one_hand.py` | ~280 | `MultiBrainOneHandOrchestrator` |
| `collaboration/_one_brain_multi_hand.py` | ~280 | `OneBrainMultiHandOrchestrator` |
| `collaboration/_multi_brain_multi_hand.py` | ~280 | `MultiBrainMultiHandOrchestrator` |
| `collaboration/_register.py` | ~50 | `register_collaboration_tools` |

**Atomic Commits**:
```
refactor(collaboration): extract data types to _types.py
refactor(collaboration): extract InterAgentMessageBus to _message_bus.py
refactor(collaboration): extract MultiBrainOneHandOrchestrator to _multi_brain_one_hand.py
refactor(collaboration): extract OneBrainMultiHandOrchestrator to _one_brain_multi_hand.py
refactor(collaboration): extract MultiBrainMultiHandOrchestrator to _multi_brain_multi_hand.py
```

---

### 2.5: Extract from `src/context_engineering.py` (1015 → ~280)

**Current Structure**:
- Class `ProgressiveContextCompressor`
- Class `IntelligentContextPruner`
- Class `ContextEngineering`
- Compression/pruning config dataclasses

**Extraction Plan**:

| Module | Lines | Classes Extracted |
|--------|-------|-------------------|
| `context/_compressor.py` | ~300 | `ProgressiveContextCompressor`, compression logic |
| `context/_pruner.py` | ~300 | `IntelligentContextPruner`, pruning logic |
| `context/_config.py` | ~150 | `CompressionConfig`, `PruningConfig`, `CompressionTier`, `TierConfig` |

**Atomic Commits**:
```
refactor(context): extract ProgressiveContextCompressor to _compressor.py
refactor(context): extract IntelligentContextPruner to _pruner.py
refactor(context): extract configuration classes to _config.py
```

---

### 2.6: Extract from `src/autonomous.py` (926 → ~200)

**Current Structure**:
- Class `AutonomousExplorer`
- Idle monitoring loop
- SOP loading
- Prompt building
- Task execution
- State persistence

**Extraction Plan**:

| Module | Lines | Methods Extracted |
|--------|-------|-------------------|
| `autonomous/_idle_monitor.py` | ~150 | `_idle_monitor_loop`, `record_activity`, `get_idle_time` |
| `autonomous/_sop_loader.py` | ~150 | `_load_sop`, `_build_sop_prompt` |
| `autonomous/_prompt_builder.py` | ~200 | `_build_autonomous_prompt`, `_build_task_instruction` |
| `autonomous/_task_executor.py` | ~250 | `_execute_autonomous_task`, `_run_loop`, `_call_llm_with_retry` |
| `autonomous/_state_manager.py` | ~150 | `_load_state`, `_persist_state`, `_recover_state` |
| `autonomous/_utils.py` | ~100 | Helper functions |

**Atomic Commits**:
```
refactor(autonomous): extract idle monitor to _idle_monitor.py
refactor(autonomous): extract SOP loader to _sop_loader.py
refactor(autonomous): extract prompt builder to _prompt_builder.py
refactor(autonomous): extract task executor to _task_executor.py
refactor(autonomous): extract state manager to _state_manager.py
```

---

### Phase 2 Summary

| File | Current | Target | Extracts | Risk |
|------|---------|--------|----------|------|
| harness.py | 1722 | ~250 | 9 | MEDIUM (central hub) |
| session_db.py | 1292 | ~250 | 6 | LOW |
| client.py | 1195 | ~250 | 7 | LOW |
| collaboration.py | 1194 | ~250 | 5 | LOW |
| context_engineering.py | 1015 | ~280 | 3 | LOW |
| autonomous.py | 926 | ~200 | 6 | LOW |

---

## Phase 3: Security Module

### Goal

Reduce all 8 security module files below 300 lines.

### Dependency-Based Execution Order

| Wave | Files | Dependencies | Parallel |
|------|-------|--------------|----------|
| **Wave 3.1** | `risk_classifier.py`, `tool_expander.py`, `single_purpose_tools.py` | None (Phase 1 complete) | ✓ Parallel |
| **Wave 3.2** | `secure_sandbox.py` | Depends on Wave 3.1 | Sequential |
| **Wave 3.3** | `credential_vault.py`, `credential_proxy.py` | Parallel | ✓ Parallel |
| **Wave 3.4** | `credential_isolated_sandbox.py` | Depends on Waves 3.2, 3.3 | Sequential |

---

### 3.1: Extract from `src/security/single_purpose_tools.py` (933 → ~100)

**Current Structure** (from LSP analysis):
- Class `SinglePurposeToolRisk` (StrEnum)
- Class `SinglePurposeToolConfig` (dataclass)
- Dict `SINGLE_PURPOSE_TOOLS` (30+ tool definitions)
- Class `SinglePurposeToolFactory` (line 301-1100)
- 20+ `_impl_*` implementation methods

**Extraction Plan**:

| Module | Lines | Content |
|--------|-------|---------|
| `security/single_purpose/_config.py` | ~150 | `SinglePurposeToolRisk`, `SinglePurposeToolConfig`, `SINGLE_PURPOSE_TOOLS` |
| `security/single_purpose/_factory.py` | ~200 | `SinglePurposeToolFactory`, `create_tool`, `get_tool_schema`, `_validate_args` |
| `security/single_purpose/_implementations.py` | ~400 | All `_impl_*` methods (read_file, list_directory, find_file, grep_search, etc.) |
| `security/single_purpose/_validation.py` | ~150 | `_validate_args`, `_request_confirmation`, `_get_safe_environment` |

**Atomic Commits**:
```
refactor(security): extract tool configs to single_purpose/_config.py
refactor(security): extract SinglePurposeToolFactory to _factory.py
refactor(security): extract implementations to _implementations.py
refactor(security): extract validation logic to _validation.py
```

---

### 3.2: Extract from `src/security/credential_vault.py` (760 → ~150)

**Current Structure**:
- Class `CredentialType` (StrEnum)
- Class `CredentialScope` (StrEnum)
- Class `CredentialAccessLog` (dataclass)
- Class `CredentialRotationRecord` (dataclass)
- Class `CredentialRecord` (dataclass)
- Class `CredentialVault` (main class)
- Encryption methods: `_encrypt`, `_decrypt`, `_generate_encryption_key`
- Persistence methods: `_persist_credentials`, `_load_credentials`
- Audit methods: `_persist_audit_log`, `_load_access_logs`

**Extraction Plan**:

| Module | Lines | Content |
|--------|-------|---------|
| `security/vault/_types.py` | ~100 | `CredentialType`, `CredentialScope`, all dataclasses |
| `security/vault/_encryption.py` | ~200 | `_encrypt`, `_decrypt`, `_generate_encryption_key`, `_init_encryption_key` |
| `security/vault/_persistence.py` | ~200 | `_persist_credentials`, `_load_credentials`, credential file I/O |
| `security/vault/_audit.py` | ~150 | `_persist_audit_log`, `_load_access_logs`, `get_access_audit_log` |

**Atomic Commits**:
```
refactor(security): extract vault types to vault/_types.py
refactor(security): extract encryption to vault/_encryption.py
refactor(security): extract persistence to vault/_persistence.py
refactor(security): extract audit logging to vault/_audit.py
```

---

### 3.3: Extract from `src/security/credential_proxy.py` (607 → ~200)

**Extraction Plan**:

| Module | Lines | Content |
|--------|-------|---------|
| `security/proxy/_types.py` | ~50 | `RequestAuditLog` (dataclass) |
| `security/proxy/_temp_client.py` | ~150 | `TemporaryClient` class |
| `security/proxy/_execution.py` | ~200 | `execute_external_request`, `execute_streaming_request` |

**Atomic Commits**:
```
refactor(security): extract proxy types to proxy/_types.py
refactor(security): extract TemporaryClient to proxy/_temp_client.py
refactor(security): extract execution methods to proxy/_execution.py
```

---

### 3.4: Extract from `src/security/credential_isolated_sandbox.py` (598 → ~250)

**Note**: Depends on Phase 1 `constants.py`

**Extraction Plan**:

| Module | Lines | Content |
|--------|-------|---------|
| `security/isolated/_environment.py` | ~150 | `_create_isolated_environment`, `BLOCKED_ENV_VARS` (moved to constants.py) |
| `security/isolated/_detection.py` | ~100 | `_detect_credential_access_attempt`, detection patterns |
| `security/isolated/_sanitize.py` | ~100 | `_sanitize_output`, regex patterns for credential filtering |

**Atomic Commits**:
```
refactor(security): extract environment isolation to isolated/_environment.py
refactor(security): extract credential detection to isolated/_detection.py
refactor(security): extract output sanitization to isolated/_sanitize.py
```

---

### 3.5: Extract from `src/security/risk_classifier.py` (490 → ~250)

**Extraction Plan**:

| Module | Lines | Content |
|--------|-------|---------|
| `security/risk/_types.py` | ~100 | `RiskLevel`, `RiskAction`, `ClassificationResult` |
| `security/risk/_config.py` | ~150 | `RiskLevelConfig`, `TOOL_BASE_RISKS`, `PARAM_RISK_FACTORS`, `USER_LEVEL_MODIFIERS` |

**Atomic Commits**:
```
refactor(security): extract risk types to risk/_types.py
refactor(security): extract risk configs to risk/_config.py
```

---

### 3.6: Extract from `src/security/tool_expander.py` (429 → ~200)

**Extraction Plan**:

| Module | Lines | Content |
|--------|-------|---------|
| `security/expander/_types.py` | ~100 | `ToolTier`, `ToolTierConfig`, `ExpansionEvent` |
| `security/expander/_config.py` | ~100 | `TOOL_TIER_CONFIGS`, `TASK_TYPE_TIER_MAP`, `USER_PERMISSION_TIER_LIMITS` |

**Atomic Commits**:
```
refactor(security): extract expander types to expander/_types.py
refactor(security): extract expander configs to expander/_config.py
```

---

### 3.7: Extract from `src/security/secure_sandbox.py` (418 → ~200)

**Extraction Plan**:

| Module | Lines | Content |
|--------|-------|---------|
| `security/secure/_execution.py` | ~150 | `execute_tools_secure`, `_execute_single_tool_secure` |
| `security/secure/_approval.py` | ~100 | `_request_user_approval`, `_is_single_purpose_tool` |

**Atomic Commits**:
```
refactor(security): extract secure execution to secure/_execution.py
refactor(security): extract approval logic to secure/_approval.py
```

---

### Phase 3 Summary

| File | Current | Target | Extracts | Risk |
|------|---------|--------|----------|------|
| single_purpose_tools.py | 933 | ~100 | 4 | LOW (Phase 1 complete) |
| credential_vault.py | 760 | ~150 | 4 | LOW |
| credential_proxy.py | 607 | ~200 | 3 | LOW |
| credential_isolated_sandbox.py | 598 | ~250 | 3 | MEDIUM (multi-deps) |
| risk_classifier.py | 490 | ~250 | 2 | LOW |
| tool_expander.py | 429 | ~200 | 2 | LOW |
| secure_sandbox.py | 418 | ~200 | 2 | MEDIUM (depends on 3 files) |
| secure_harness.py | 335 | ~335 | 0 | Keep (under 300) |

---

## Phase 4: Tools Module

### Goal

Reduce remaining 6 tools module files below 300 lines.

---

### 4.1: Extract from `src/tools/user_modeling.py` (886 → ~200)

**Extraction Plan**:

| Module | Lines | Content |
|--------|-------|---------|
| `tools/user/_profile.py` | ~250 | `UserModelingLayer`, user profile methods |
| `tools/user/_observation.py` | ~200 | `observe`, `observe_from_interaction` |
| `tools/user/_dialectical.py` | ~250 | `dialectical_update`, `_detect_conflicts`, `_reason_about_conflicts`, `_upgrade_model` |

**Atomic Commits**:
```
refactor(user): extract profile management to _profile.py
refactor(user): extract observation methods to _observation.py
refactor(user): extract dialectical update to _dialectical.py
```

---

### 4.2: Extract from `src/tools/skill_loader.py` (858 → ~250)

**Extraction Plan**:

| Module | Lines | Content |
|--------|-------|---------|
| `tools/skill/_loader.py` | ~250 | `SkillLoader`, `_load_metadata`, `_parse_frontmatter` |
| `tools/skill/_matcher.py` | ~150 | `match_skill`, `_tokenize_query`, `_compute_match_score` |
| `tools/skill/_selection.py` | ~200 | `select_best_skill`, `_rank_candidates`, `_compute_selection_score`, `get_gene_slice` |

**Atomic Commits**:
```
refactor(skill): extract loader core to _loader.py
refactor(skill): extract matching algorithm to _matcher.py
refactor(skill): extract selection logic to _selection.py
```

---

### 4.3: Extract from `src/tools/memory_tools.py` (827 → ~200)

**Analysis**: This is primarily an **integration/wrapper layer** that delegates to other modules.

**Recommendation**: Keep as integration layer (no extraction needed if under 300 after cleanup)

**Cleanup Actions**:
- Remove redundant wrapper functions
- Simplify delegation logic
- Target: ~200 lines after cleanup

**Atomic Commit**: `refactor(memory): simplify integration layer`

---

### 4.4: Extract from `src/tools/long_term_archive.py` (729 → ~250)

**Extraction Plan**:

| Module | Lines | Content |
|--------|-------|---------|
| `tools/archive/_operations.py` | ~200 | `archive_session`, `_store_events`, `_update_fts_index` |
| `tools/archive/_search.py` | ~150 | `search_with_context`, `search_by_time_range` |
| `tools/archive/_stats.py` | ~150 | `get_archive_stats`, `cleanup_old_archives`, `get_archive`, `delete_archive` |

**Atomic Commits**:
```
refactor(archive): extract archive operations to _operations.py
refactor(archive): extract search methods to _search.py
refactor(archive): extract stats methods to _stats.py
```

---

### 4.5: Extract from `src/tools/builtin_tools.py` (707 → ~250)

**Extraction Plan**:

| Module | Lines | Content |
|--------|-------|---------|
| `tools/builtin/_file_ops.py` | ~200 | `file_read`, `file_write`, `file_edit` |
| `tools/builtin/_code_exec.py` | ~200 | `code_as_policy`, `code_as_policy_async`, `_build_command`, `_format_execution_result` |
| `tools/builtin/_ask_user.py` | ~100 | `ask_user`, `inject_user_response`, `get_pending_ask_user_request` |

**Atomic Commits**:
```
refactor(builtin): extract file operations to _file_ops.py
refactor(builtin): extract code execution to _code_exec.py
refactor(builtin): extract ask_user to _ask_user.py
```

---

### Phase 4 Summary

| File | Current | Target | Extracts/Cleanup |
|------|---------|--------|------------------|
| user_modeling.py | 886 | ~200 | 3 extracts |
| skill_loader.py | 858 | ~250 | 3 extracts |
| memory_tools.py | 827 | ~200 | Cleanup only |
| long_term_archive.py | 729 | ~250 | 3 extracts |
| builtin_tools.py | 707 | ~250 | 3 extracts |

---

## Phase 5: Test Files

### Goal

Split test files to match extracted source modules.

### Approach

Test files refactored **after** source refactoring completes. Each test file split to cover corresponding extracted modules.

---

### Test File Splitting Recommendations

#### 5.1: `tests/test_security.py` (855 lines) → 4 files

| New File | Lines | Coverage |
|----------|-------|----------|
| `tests/test_credential_vault.py` | ~300 | `credential_vault.py` + `vault/_*.py` |
| `tests/test_credential_proxy.py` | ~300 | `credential_proxy.py` + `proxy/_*.py` |
| `tests/test_single_purpose.py` | ~200 | `single_purpose_tools.py` + `_*.py` |
| `tests/test_risk_classifier.py` | ~155 | `risk_classifier.py` |

---

#### 5.2: `tests/test_autonomous.py` (740 lines) → 3 files

| New File | Lines | Coverage |
|----------|-------|----------|
| `tests/test_idle_monitor.py` | ~250 | `autonomous/_idle_monitor.py` |
| `tests/test_task_executor.py` | ~300 | `autonomous/_task_executor.py` |
| `tests/test_state_manager.py` | ~190 | `autonomous/_state_manager.py` |

---

#### 5.3: `tests/test_subagent_manager.py` (704 lines) → 2 files

| New File | Lines | Coverage |
|----------|-------|----------|
| `tests/test_subagent_manager.py` | ~400 | `subagent_manager.py` |
| `tests/test_ralph_orchestrator.py` | ~304 | `RalphSubagentOrchestrator` |

---

#### 5.4: `tests/test_harness.py` (599 lines) → 4 files

| New File | Lines | Coverage |
|----------|-------|----------|
| `tests/test_context_builder.py` | ~150 | `harness/_context_builder.py` |
| `tests/test_tool_router.py` | ~200 | `harness/_tool_router.py` |
| `tests/test_streaming.py` | ~150 | `harness/_streaming.py` |
| `tests/test_harness.py` (main) | ~199 | Core `Harness` class |

---

#### 5.5: `tests/test_session_db.py` (524 lines) → 3 files

| New File | Lines | Coverage |
|----------|-------|----------|
| `tests/test_schema.py` | ~150 | `session/_schema.py` |
| `tests/test_skill_outcomes.py` | ~200 | `session/_skill_outcomes.py` |
| `tests/test_session_search.py` | ~174 | `session/_search.py` |

---

### Phase 5 Summary

| Test File | Current | New Files | Total Test Files |
|-----------|---------|-----------|------------------|
| test_security.py | 855 | 4 | 17 → 20 |
| test_autonomous.py | 740 | 3 | 17 → 20 |
| test_subagent_manager.py | 704 | 2 | 17 → 18 |
| test_harness.py | 599 | 4 | 17 → 20 |
| test_session_db.py | 524 | 3 | 17 → 19 |

---

## Dependency Analysis

### Import Graph

**Core Module Dependencies** (verified safe):

```
┌─────────────────────┐
│   harness.py        │ ──imports──→ context_engineering.py
│   (1722 lines)      │              (TYPE_CHECKING client.py)
└─────────────────────┘
         │
         │ imports
         ▼
┌─────────────────────┐
│ context_engineering │ ──imports──→ client.py (TYPE_CHECKING)
│   (1015 lines)      │
└─────────────────────┘
         
┌─────────────────────┐     ┌─────────────────────┐
│   client.py         │     │ collaboration.py    │
│   (1195 lines)      │     │   (1194 lines)      │
│ NO DEPS ON 6 CORE   │     │ NO DEPS ON 6 CORE   │
└─────────────────────┘     └─────────────────────┘

┌─────────────────────┐     ┌─────────────────────┐
│   session_db.py     │     │   autonomous.py     │
│   (1292 lines)      │     │   (926 lines)       │
│ NO DEPS ON 6 CORE   │     │ NO DEPS ON 6 CORE   │
└─────────────────────┘     └─────────────────────┘
```

### Circular Dependency Check

| Relationship | Type | Risk |
|--------------|------|------|
| harness → context_engineering | Runtime import | LOW |
| harness → client | TYPE_CHECKING | NONE |
| context_engineering → client | TYPE_CHECKING | NONE |

**Result**: **NO runtime circular dependencies detected**

### Security Module Dependency Chain

```
Level 0 (Independent):
├── risk_classifier.py
├── tool_expander.py
└── single_purpose_tools.py

Level 1 (Depends on Level 0):
└── secure_sandbox.py → imports all Level 0

Level 2 (Depends on credential_vault):
└── credential_proxy.py → imports CredentialVault

Level 3 (Depends on Level 1 + Level 2):
└── credential_isolated_sandbox.py → extends SecureSandbox, uses CredentialProxy
```

### Tools Module Dependency Graph

```
Level 0 (Utilities):
├── utils.py (safe_int_convert)
├── fts_utils.py (NEW - Phase 1)
└── db_base.py (NEW - Phase 1)

Level 1 (Data layer):
├── session_db.py → uses fts_utils
├── user_modeling.py → uses db_base
├── long_term_archive.py → uses session_db, fts_utils

Level 2 (Business logic):
├── skill_loader.py → uses skill_cache, skill_security
├── builtin_tools.py → uses path_validation (NEW)

Level 3 (Integration):
└── memory_tools.py → wraps session_db, user_modeling, long_term_archive
```

---

## Risk Assessment

### High Risk Extractions

| Extraction | Risk Reason | Mitigation |
|------------|-------------|------------|
| `harness/_tool_router.py` | Central routing logic, affects all tool calls | Extensive unit tests before extraction |
| `client/_streaming.py` | Streaming state management | Verify streaming tests pass |
| `credential_isolated_sandbox.py` | Multi-dependency, extends SecureSandbox | Extract after all dependencies stable |

### Medium Risk Extractions

| Extraction | Risk Reason | Mitigation |
|------------|-------------|------------|
| `session/_skill_outcomes.py` | Memory Graph selection algorithm | Test selection logic thoroughly |
| `secure_sandbox.py` extraction | Depends on 3 security modules | Extract after Level 0 complete |
| `db_base.py` creation | Changes 3 existing files | Update all imports atomically |

### Low Risk Extractions

| Extraction | Risk Reason | Mitigation |
|------------|-------------|------------|
| `security/constants.py` | Simple constant extraction | Verify imports update |
| `fts_utils.py` | Utility functions, no state | Standard unit tests |
| `collaboration/_*.py` | Independent orchestrators | Each class is self-contained |
| `context/_compressor.py` | Single class extraction | Verify compression tests |
| `types.py` extractions | Dataclasses/enums only | Type check verification |

### Risk Matrix

| Phase | Extracts | High Risk | Medium Risk | Low Risk |
|-------|----------|-----------|-------------|----------|
| Phase 1 | 5 | 0 | 1 | 4 |
| Phase 2 | 38 | 2 | 3 | 33 |
| Phase 3 | 20 | 1 | 2 | 17 |
| Phase 4 | 14 | 0 | 1 | 13 |
| Phase 5 | 16 | 0 | 2 | 14 |

---

## Implementation Guidelines

### Atomic Commit Strategy

**One extraction = One commit**

```
Commit message format:
refactor(<module>): extract <component> to <submodule>

Examples:
refactor(harness): extract context builder to _context_builder.py
refactor(session): extract skill outcomes to _skill_outcomes.py
refactor(security): extract SENSITIVE_ENV_VARS to constants.py
```

### TDD-Oriented Execution Pattern

For each extraction:

```
Step 1: READ
  - Analyze source file structure (LSP symbols)
  - Identify extraction boundary (classes/methods)
  - Check import dependencies

Step 2: CREATE TEST
  - Create test file for extracted module
  - Copy relevant tests from parent test file
  - Verify tests pass before extraction

Step 3: IMPLEMENT
  - Create extracted module file
  - Copy code with proper imports
  - Add __init__.py for package if needed

Step 4: UPDATE PARENT
  - Update parent file imports
  - Import from extracted submodule
  - Remove extracted code from parent
  - Verify backward compatibility

Step 5: VERIFY
  - Run: pytest tests/<module> -v
  - Run: pytest tests/test_<parent> -v
  - Run: pylint --disable=all --enable=cyclic-import src/

Step 6: COMMIT
  - git add <new_module> <parent>
  - git commit -m "refactor(<module>): extract <component>..."
```

### Backward Compatibility Rules

| Rule | Implementation |
|------|----------------|
| Public API unchanged | Keep all public functions in parent `__init__.py` |
| Import paths preserved | Use `from <parent> import <class>` still works |
| Type hints maintained | Copy all type annotations to extracted module |
| Docstrings preserved | Move docstrings with extracted code |

### Import Update Pattern

**Before extraction**:
```python
# src/harness.py
class Harness:
    def _build_context_from_session(self, ...):
        ...
```

**After extraction**:
```python
# src/harness/_context_builder.py
def build_context_from_session(harness, session, ...):
    ...

# src/harness.py
from src.harness._context_builder import build_context_from_session

class Harness:
    def _build_context_from_session(self, ...):
        return build_context_from_session(self, self.session, ...)
```

### Verification Commands

After each extraction:

```bash
# Unit tests for extracted module
pytest tests/test_<module> -v

# Integration tests for parent
pytest tests/test_<parent> -v

# Import cycle detection
pylint --disable=all --enable=cyclic-import src/

# Type checking (if using mypy)
mypy src/<module> --no-error-summary

# Line count verification
wc -l src/<parent>.py src/<module>/_*.py
```

---

## Post-Refactoring Verification

### Final Checklist

| Check | Command | Pass Criteria |
|-------|---------|----------------|
| All files < 300 lines | `find src -name "*.py" -exec wc -l {} \; \| awk '$1 > 300'` | Empty output |
| No circular imports | `pylint --disable=all --enable=cyclic-import src/` | No errors |
| All tests pass | `pytest tests/ -v` | 100% pass |
| Backward compatibility | Run integration tests | All API calls work |
| Import paths work | Import from original paths | No ImportError |

### Expected Outcomes

| Metric | Before | After |
|--------|--------|-------|
| Files > 300 lines | 37 | 0 |
| Largest file | 1722 | < 300 |
| Average file size | ~450 | ~200 |
| Duplicate code blocks | 5 | 0 |
| Circular dependencies | 0 | 0 |

---

## Appendix: File Structure After Refactoring

### Project Structure Preview

```
src/
├── harness/
│   ├── __init__.py (exports Harness, HarnessManager)
│   ├── _context_builder.py (~250)
│   ├── _tool_router.py (~280)
│   ├── _lifecycle_hooks.py (~200)
│   ├── _streaming.py (~300)
│   ├── _metrics.py (~180)
│   ├── _resume.py (~250)
│   ├── _write_conflict.py (~180)
│   ├── _single_tool.py (~200)
│   └── _manager.py (~250)
│
├── client/
│   ├── __init__.py (exports LLMGateway)
│   ├── _fallback_chain.py (~150)
│   ├── _timeout.py (~100)
│   ├── _rate_limit_integration.py (~200)
│   ├── _retry.py (~180)
│   ├── _streaming.py (~250)
│   ├── _persistence.py (~200)
│   └── _utils.py (~150)
│
├── collaboration/
│   ├── __init__.py (exports orchestrators)
│   ├── _types.py (~100)
│   ├── _message_bus.py (~250)
│   ├── _multi_brain_one_hand.py (~280)
│   ├── _one_brain_multi_hand.py (~280)
│   ├── _multi_brain_multi_hand.py (~280)
│   └── _register.py (~50)
│
├── context/
│   ├── __init__.py (exports ContextEngineering)
│   ├── _compressor.py (~300)
│   ├── _pruner.py (~300)
│   └── _config.py (~150)
│
├── autonomous/
│   ├── __init__.py (exports AutonomousExplorer)
│   ├── _idle_monitor.py (~150)
│   ├── _sop_loader.py (~150)
│   ├── _prompt_builder.py (~200)
│   ├── _task_executor.py (~250)
│   ├── _state_manager.py (~150)
│   └── _utils.py (~100)
│
├── security/
│   ├── __init__.py
│   ├── constants.py (~60) [NEW]
│   ├── utils.py (~50) [NEW]
│   ├── single_purpose/
│   │   ├── __init__.py
│   │   ├── _config.py (~150)
│   │   ├── _factory.py (~200)
│   │   ├── _implementations.py (~400)
│   │   ├── _validation.py (~150)
│   │   └── single_purpose_tools.py (~100)
│   ├── vault/
│   │   ├── __init__.py
│   │   ├── _types.py (~100)
│   │   ├── _encryption.py (~200)
│   │   ├── _persistence.py (~200)
│   │   ├── _audit.py (~150)
│   │   └── credential_vault.py (~150)
│   ├── proxy/
│   │   ├── __init__.py
│   │   ├── _types.py (~50)
│   │   ├── _temp_client.py (~150)
│   │   ├── _execution.py (~200)
│   │   └── credential_proxy.py (~200)
│   ├── isolated/
│   │   ├── __init__.py
│   │   ├── _environment.py (~150)
│   │   ├── _detection.py (~100)
│   │   ├── _sanitize.py (~100)
│   │   └── credential_isolated_sandbox.py (~250)
│   ├── risk/
│   │   ├── __init__.py
│   │   ├── _types.py (~100)
│   │   ├── _config.py (~150)
│   │   └── risk_classifier.py (~250)
│   ├── expander/
│   │   ├── __init__.py
│   │   ├── _types.py (~100)
│   │   ├── _config.py (~100)
│   │   └── tool_expander.py (~200)
│   └── secure/
│   │   ├── __init__.py
│   │   ├── _execution.py (~150)
│   │   ├── _approval.py (~100)
│   │   └── secure_sandbox.py (~200)
│
├── tools/
│   ├── __init__.py (exports ToolRegistry)
│   ├── constants.py [shared]
│   ├── fts_utils.py (~180) [NEW]
│   ├── db_base.py (~200) [NEW]
│   ├── path_validation.py (~150) [NEW]
│   ├── session/
│   │   ├── __init__.py
│   │   ├── _schema.py (~250)
│   │   ├── _skill_outcomes.py (~280)
│   │   ├── _search.py (~280)
│   │   ├── _save.py (~200)
│   │   ├── _load.py (~150)
│   │   ├── _cleanup.py (~150)
│   │   └── session_db.py (~250)
│   ├── user/
│   │   ├── __init__.py
│   │   ├── _profile.py (~250)
│   │   ├── _observation.py (~200)
│   │   ├── _dialectical.py (~250)
│   │   └── user_modeling.py (~200)
│   ├── skill/
│   │   ├── __init__.py
│   │   ├── _loader.py (~250)
│   │   ├── _matcher.py (~150)
│   │   ├── _selection.py (~200)
│   │   └── skill_loader.py (~250)
│   ├── archive/
│   │   ├── __init__.py
│   │   ├── _operations.py (~200)
│   │   ├── _search.py (~150)
│   │   ├── _stats.py (~150)
│   │   └── long_term_archive.py (~250)
│   ├── builtin/
│   │   ├── __init__.py
│   │   ├── _file_ops.py (~200)
│   │   ├── _code_exec.py (~200)
│   │   ├── _ask_user.py (~100)
│   │   └ builtin_tools.py (~250)
│   └── memory_tools.py (~200)
│
├── harness.py (remains as entry point, imports from harness/)
├── client.py (remains as entry point, imports from client/)
├── collaboration.py (remains as entry point)
├── context_engineering.py (remains as entry point)
├── autonomous.py (remains as entry point)
└── ... (other files under 300 lines, unchanged)
```

---

## Summary

This refactoring plan transforms the seed-agent codebase from **37 files exceeding 300 lines** to **0 files exceeding 300 lines** through **~60 extraction operations** across **5 phases**.

### Key Metrics

| Metric | Value |
|--------|-------|
| Total extractions | **~60 modules** |
| Duplicate eliminations | **5 code blocks** |
| Files created | **~65 new files** |
| Commits required | **~60 atomic commits** |
| Test files split | **5 → ~17 files** |
| Estimated risk | **3 HIGH, 8 MEDIUM, ~50 LOW** |

### Execution Priority

1. **Phase 1 (Foundation)**: Eliminate duplications - enables all subsequent phases
2. **Phase 2 (Core Files)**: Largest files with highest impact
3. **Phase 3 (Security)**: Security-sensitive code requires careful handling
4. **Phase 4 (Tools)**: Remaining tools module files
5. **Phase 5 (Tests)**: Split test files after source refactoring

---

**Document Version**: 1.0
**Generated**: 2026-05-05
**Status**: Planning Document (No code modifications)
**Author**: Sisyphus (AI Agent Orchestrator)