# Memory Management SOP Module

This module provides the memory management system for the Seed Agent, enabling persistent learning, skill organization, and knowledge evolution across sessions.

---

## Memory Hierarchy (L1-L5)

The memory system is organized into five distinct layers, each with a specific purpose and constraints:

### L1 (Index) - notes.md

The global index layer providing quick reference to all memory content.

**Purpose:** Minimal keyword-based index pointing to L2 skills, L3 knowledge, and L4 raw data.

**Constraints:**
- Maximum 200 characters per entry
- No subsections (##) or code blocks allowed
- Pure existence index, no operational details
- Uses scenario-based trigger words (e.g., "browser_automation", "file_permission_error")

**Content:** Short trigger phrases that map to corresponding skill/knowledge files.

---

### L2 (Skills) - skills directory

Standard SOP layer containing executable operation procedures.

**Purpose:** Directly executable skill definitions, retry strategies, and failure handling procedures.

**Format:** Open Agent Skills format with YAML frontmatter

**Required frontmatter fields:**
- `name`: Skill identifier (lowercase letters, numbers, hyphens only; 1-64 characters)
- `description`: Skill purpose (maximum 1024 characters)

**File structure:** Each skill stored as `skill_name/SKILL.md`

**Examples:**
- High-frequency reusable SOPs
- Retry and escalation strategies
- Irreversible operation execution flows
- Verified effective operation steps

---

### L3 (Knowledge) - knowledge directory

General-purpose knowledge base extracted from frequently-used SOPs.

**Purpose:** Cross-task patterns, principles, environment configurations, and core experiences.

**Content:**
- Universal patterns extracted from tasks
- Core principles and rules
- Stable environment configurations
- Evolution experiences from repeated SOP usage
- Action redlines applicable to all scenarios

**Constraint:** Only stores distilled knowledge, not specific operational steps.

---

### L4 (User Modeling) - SQLite Database

**NEW:** 黑格尔辩证式用户建模层 (Hegelian Dialectical User Modeling)

**Purpose:** Building progressive understanding of the user through observation, conflict detection, and model evolution.

**Core Philosophy:**
> 不是一次判断就定终身，允许用户改变、允许情况复杂，通过不断观察、思考、调整，越来越懂真实的用户

**Key Features:**
- **辩证式进化**: Upgrade rather than overwrite preferences
- **例外处理**: Allow exceptions for complex situations
- **置信度管理**: Track confidence levels for each preference
- **上下文感知**: Context-based preference retrieval

**Database Location:** `~/.seed/memory/user_modeling.db`

**Schema:**
- `user_profiles`: Preference storage with exceptions
- `user_observations`: Observation records queue
- `dialectical_history`: Evolution history tracking

**Tools provided:**
- `observe_user_preference`: Record preference evidence
- `get_user_preference`: Retrieve preference with context
- `get_user_profile_summary`: Full profile summary
- `update_user_model`: Trigger dialectical update
- `list_user_preferences`: List all preferences

**Example Evolution:**
```
Old: "用户偏好美式咖啡"
New Evidence: "用户点了拿铁" (context: "周三下午")
Conflict Detected: Old vs New
Resolution: Exception case
Upgrade: {
  "usual": "美式",
  "exceptions": {"周三下午": "拿铁"}
}
```

---

### L5 (Work Archive) - SQLite + FTS5

**NEW:** 长期工作日志层 (Long-term Archive Layer)

**Purpose:** Permanent storage of session events with LLM-generated summaries, enabling cross-session knowledge retrieval.

**Key Features:**
- **LLM 自动摘要**: Generate concise summaries after each session
- **FTS5 全文检索**: Chinese full-text search with jieba tokenization
- **关键发现提取**: Extract key findings from conversations
- **跨会话搜索**: Search across all archived sessions

**Database Location:** `~/.seed/memory/archives.db`

**Schema:**
- `archives`: Archive metadata with summaries
- `archive_events`: Detailed event storage
- `archives_fts`: FTS5 virtual table for search

**Tools provided:**
- `archive_session_events`: Archive session to long-term storage
- `search_archives`: FTS5 search across archives
- `get_archive_details`: Retrieve full archive details
- `get_archive_stats`: Archive statistics

**Summary Generation Process:**
1. Extract events from session
2. LLM generates 1-2 sentence core conclusion
3. Extract 3-5 key findings
4. Store with FTS5 indexing

---

## Files in this Module

### memory.md

The core Memory Management SOP document. Defines:

- Core memory axioms (highest priority)
- Layer definitions and responsibilities
- Inter-layer association rules
- Agent memory execution SOP
- Mandatory constraints

This is the primary reference for memory operations and hierarchy management.

### auto_dream.md

The Auto-Dream (Memory Consolidation) SOP document. Defines:

- Core positioning of each layer (L1-L5)
- ROI assessment model for memories
- High-ROI retention items per layer
- Low-ROI items to remove
- Five-question verification method for memory entries
- Standard memory consolidation workflow
- Mandatory redline constraints

---

## Memory Tools Integration

The memory system is integrated into the agent via `memory_tools.py`, providing the following functions:

### L1-L3 Tools

#### write_memory

Writes content to a specific memory level.

**Parameters:**
- `level`: L1, L2, L3, or L4 (legacy file-based)
- `content`: Memory content
- `title`: Memory title or skill name
- `metadata`: Optional metadata

#### read_memory_index

Reads the global memory index (L1 notes.md).

#### search_memory

Searches memory across L1-L3 by keyword.

---

### L4 User Modeling Tools

#### observe_user_preference

Records a preference observation with optional context.

**Parameters:**
- `key`: Preference key (e.g., "coffee", "work_style")
- `value`: Preference value
- `context`: Optional context for exceptions
- `confidence`: Confidence level (0.0-1.0)

**Example:**
```python
observe_user_preference("coffee", "美式", confidence=0.9)
observe_user_preference("coffee", "拿铁", context="周三下午", confidence=0.85)
```

#### get_user_preference

Retrieves preference with context-aware exception handling.

**Parameters:**
- `key`: Preference key
- `context`: Optional current context

**Returns:**
```python
{
    "value": "拿铁",
    "reason": "例外情况: 周三下午",
    "confidence": 0.85
}
```

#### get_user_profile_summary

Returns full user profile with all preferences and exceptions.

#### update_user_model

Triggers dialectical update (async operation hint in sync context).

#### list_user_preferences

Lists all stored preferences with their exceptions.

---

### L5 Archive Tools

#### archive_session_events

Archives session events to long-term storage (async operation hint).

**Parameters:**
- `session_id`: Session identifier
- `events_json`: JSON array of events
- `metadata_json`: Optional metadata

#### search_archives

FTS5 full-text search across all archives.

**Parameters:**
- `keyword`: Search keyword
- `limit`: Maximum results

**Returns:**
```python
[
    {
        "archive_id": "archive_xxx",
        "session_id": "session_xxx",
        "summary": "核心结论摘要...",
        "matched_snippet": "匹配片段...",
        "key_findings": ["发现1", "发现2"],
        "timestamp": "2026-05-03..."
    }
]
```

#### get_archive_details

Retrieves full archive with events.

#### get_archive_stats

Returns archive statistics (counts, averages, recent archives).

#### get_memory_hierarchy

Returns summary of all five layers (L1-L5).

---

### Session History Tools (L4 Legacy)

Additional tools for raw session data management via SQLite+FTS5:

- **save_session_history**: Saves conversation history
- **load_session_history**: Loads specific session
- **list_sessions**: Lists recent sessions
- **search_history**: FTS5 search with Chinese support

---

## Memory Manager

The unified `MemoryManager` class (in `src/memory_manager.py`) manages all five layers:

```python
from src.memory_manager import get_memory_manager

manager = get_memory_manager(llm_gateway)

# Cross-layer search
results = manager.search_all_levels("重构", levels=["L3", "L5"])

# User observation
manager.observe_preference("coffee", "美式", confidence=0.9)

# Get preference with context
pref = manager.get_user_preference("coffee", "周三下午")

# Archive session
archive_id = await manager.archive_session(session_id, events)
```

---

## Auto-Dream Process

The Auto-Dream is an automated memory consolidation mechanism that runs periodically to maintain memory quality and remove low-value content.

### Trigger Mechanism

Configured in `scheduler.py` as a built-in task:

- **Task ID:** autodream
- **Interval:** 12 hours (43,200 seconds)
- **Prompt:** "执行 autodream 记忆整理 SOP"

### Memory Consolidation Workflow

The auto-dream process follows the standard workflow defined in `auto_dream.md`:

1. **Pre-completion check**: Task must be completed first
2. **Layer-by-layer inspection**: Check L1 → L2 → L3 → L4 → L5
3. **Low-ROI cleanup**: Remove low-value entries
4. **High-value supplementation**: Add missing high-ROI items
5. **Layer compliance verification**
6. **Final confirmation**: Verify inter-layer associations

### ROI Assessment

**ROI = (Error Probability × Operation Cost) / Memory Storage Cost**

---

## Data Flow

The memory system follows a unidirectional flow:

```
L5 (archives) → 归档摘要 → L3 (knowledge)
                    ↓
L4 (user_modeling) → 用户偏好洞察
                    ↓
L4 (raw/sessions) → L2 (skills) → L3 (knowledge)
       ↓                    ↓             ↓
       └──────────────── L1 (notes) ←─────┘
                    (index synchronization)
```

1. Session events archived to L5 with LLM summary
2. User observations stored in L4 for dialectical modeling
3. Raw session data logged to L4 (legacy)
4. Validated processes saved as SOPs to L2
5. SOPs reused 3+ times distilled to L3 knowledge
6. L1 index synchronized throughout