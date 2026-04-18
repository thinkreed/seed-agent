# Memory Management SOP Module

This module provides the memory management system for the Seed Agent, enabling persistent learning, skill organization, and knowledge evolution across sessions.

---

## Memory Hierarchy (L1-L4)

The memory system is organized into four distinct layers, each with a specific purpose and constraints:

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

### L4 (Raw) - raw directory

Raw archive layer for session history and execution logs.

**Purpose:** Complete original data for traceability and review.

**Format:** JSONL (JSON Lines) format

**Storage:**
- Original execution logs
- Complete session histories
- Raw probe data for review purposes
- Full operation records

**Tools provided:** save_session_history, load_session_history, list_sessions, search_history

**Usage:** Used for review and traceability, not direct execution calls.

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

- Core positioning of each layer
- ROI (Return on Investment) assessment model for memories
- High-ROI retention items per layer
- Low-ROI items to remove
- Four-question verification method for memory entries
- Standard memory consolidation workflow
- Mandatory redline constraints

---

## Memory Tools Integration

The memory system is integrated into the agent via `memory_tools.py`, providing the following functions:

### write_memory

Writes content to a specific memory level.

**Parameters:**
- `level`: L1, L2, L3, or L4
- `content`: Memory content (for L2, must be SKILL.md format with YAML frontmatter)
- `title`: Memory title or skill name
- `metadata`: Optional metadata (source, date, etc.)

**Validation:**
- L1: Max 200 chars, no subsections or code blocks
- L2: Must follow Open Agent Skills format with required YAML frontmatter

---

### read_memory_index

Reads the global memory index (L1 notes.md) to find available SOPs or knowledge.

**Returns:** Complete content of notes.md

---

### search_memory

Searches memory across specified levels by keyword.

**Parameters:**
- `keyword`: Search keyword
- `levels`: Levels to search (default: L1, L2, L3)

**Returns:** List of matching files with their level indicators

---

### Session History Tools (L4)

Additional tools for raw session data management:

- **save_session_history**: Saves conversation history to JSONL format
- **load_session_history**: Loads specific session data
- **list_sessions**: Lists recent sessions with metadata
- **search_history**: Searches past sessions by keyword

---

## Auto-Dream Process

The Auto-Dream is an automated memory consolidation mechanism that runs periodically to maintain memory quality and remove low-value content.

### Trigger Mechanism

Configured in `scheduler.py` as a built-in task:

- **Task ID:** autodream
- **Interval:** 12 hours (43,200 seconds)
- **Prompt:** "执行 autodream 记忆整理 SOP：分层逐查、ROI评估、低ROI清理、补全高价值项"

### Memory Consolidation Workflow

The auto-dream process follows the standard memory consolidation workflow defined in `auto_dream.md`:

1. **Pre-completion check**: Current task must be completed first; no memory writing before task completion

2. **Layer-by-layer inspection**: Check each layer in sequence (L1 -> L2 -> L3 -> L4), marking entry types: redline/trigger_word/routing/detail/redundant

3. **Low-ROI cleanup**: Remove low-value entries, verify L2/L3 coverage before deleting

4. **High-value item supplementation**: Add missing high-ROI trigger words and routing indices based on recent failures and lessons learned

5. **Layer compliance verification:**
   - L1 (notes): Minimal entries, no redundant descriptions
   - L2 (skills): Only verified SOPs, no speculation or common knowledge
   - L3 (knowledge): Only distilled universal knowledge
   - L4 (raw): Only data with traceability value

6. **Final confirmation**: Verify memory completeness, ensure inter-layer associations are intact

### ROI Assessment

Memory retention is evaluated using the formula:

**ROI = (Error Probability × Operation Cost) / Memory Storage Cost**

- L1: Each word incurs call cost; prioritize high-error-tolerance, high-value minimal entries
- L2/L3: Core metric is reuse frequency; higher reuse = more worth retaining
- L4: Only retain raw data with review value; no review value = clean up

---

## Data Flow

The memory system follows a unidirectional flow:

```
L4 (raw/sessions) → L2 (skills) → L3 (knowledge)
       ↓                    ↓             ↓
       └──────────────── L1 (notes) ←─────┘
                    (index synchronization)
```

1. Task execution logs raw data to L4
2. Validated processes are saved as SOPs to L2
3. SOPs reused 3+ times get distilled to L3 knowledge
4. L1 index is synchronized throughout to maintain global accessibility
