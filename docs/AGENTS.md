# Module Overview - Design Documentation

This directory contains design documents that capture architectural decisions, implementation plans, and technical specifications for the Seed Agent system. These documents serve as the authoritative reference for understanding why specific design choices were made.

---

## Available Documents

| Document | Description |
|----------|-------------|
| `L4_SQLite_FTS5_Design.md` | L4 session storage migration from JSONL to SQLite+FTS5 |
| `long_cycle_loop_enhancement_design.md` | Ralph Loop architecture and implementation design |
| `ralph_loop.md` | Ralph Loop concept and motivation |

---

## L4 SQLite+FTS5 Design

**File:** `L4_SQLite_FTS5_Design.md`

**Purpose:** Documents the migration from JSONL file-based session storage to SQLite+FTS5 database.

**Key Sections:**
- Current JSONL implementation limitations
- SQLite+FTS5 architecture with jieba Chinese tokenization
- Database schema design (session_messages, sessions_meta, FTS5 virtual table)
- Migration strategy and compatibility
- Performance benchmarks and PRAGMA optimizations
- API compatibility with existing memory tools

**Why SQLite+FTS5:**
- Efficient full-text search for Chinese content (jieba tokenization)
- Better query performance for history searches
- Atomic transactions for data integrity
- WAL mode for concurrent access

---

## Ralph Loop Enhancement Design

**File:** `long_cycle_loop_enhancement_design.md`

**Purpose:** Documents the Ralph Loop architecture for long-cycle deterministic task execution.

**Key Sections:**
- Problem analysis: context drift in long-running tasks
- 3-layer architecture: Verification Layer, Execution Layer, Safety Layer
- Completion promise mechanism
- Context reset strategy
- State persistence for crash recovery
- Safety limits (iterations and duration)
- Implementation details and code examples

**Core Mechanisms:**
1. **External Verification**: Completion driven by objective criteria (tests, markers, git)
2. **Fresh Context**: Periodic history reset prevents drift
3. **State Persistence**: Crash recovery via filesystem state
4. **Safety Limits**: Max iterations and duration protection

---

## Ralph Loop Concept

**File:** `ralph_loop.md`

**Purpose:** Explains the conceptual motivation and design philosophy behind Ralph Loop.

**Key Concepts:**
- The "Ralph" metaphor: rolling the boulder with persistence
- Deterministic vs self-judged completion
- External verification as objective truth
- Context freshness as drift prevention
- Long-cycle task patterns and use cases

---

## Document Usage Guidelines

### When to Read These Documents

- **L4 SQLite Design**: Before modifying session storage or adding search features
- **Ralph Loop Design**: Before implementing long-cycle tasks or modifying autonomous.py
- **Ralph Loop Concept**: To understand the design philosophy and motivation

### How These Documents Relate to Code

| Document | Related Code |
|----------|--------------|
| L4 SQLite Design | `src/tools/session_db.py`, `src/tools/memory_tools.py` |
| Ralph Loop Design | `src/ralph_loop.py`, `src/autonomous.py`, `src/tools/ralph_tools.py` |
| Ralph Loop Concept | Architecture decision rationale |

---

## Future Design Documents

Planned design documents to add:

| Planned Document | Purpose |
|------------------|---------|
| Scheduler Design | Task scheduling architecture and built-in tasks |
| FallbackChain Design | Multi-provider failover mechanism |
| Memory Consolidation Design | Auto-dream process and ROI assessment |