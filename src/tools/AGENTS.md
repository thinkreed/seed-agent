# Tool Registry System

This module provides a comprehensive tool registration and execution framework for the Seed Agent system. It enables dynamic tool registration, automatic schema inference, and supports both synchronous and asynchronous tool execution.

## Module Overview

The tool registry system is located in `src/tools/` and consists of seven main components:

| File | Purpose |
|------|---------|
| `__init__.py` | ToolRegistry class for registering and executing tools |
| `builtin_tools.py` | Five core built-in tools for file operations and code execution |
| `memory_tools.py` | L1-L4 memory management system and session history tools |
| `skill_loader.py` | Dynamic skill loading with progressive disclosure pattern |
| `ralph_tools.py` | Ralph Loop management tools for long-cycle task execution |
| `session_db.py` | SQLite+FTS5 session storage with Chinese full-text search |
| `subagent_tools.py` | Subagent management tools for spawning, waiting, aggregating |

---

## ToolRegistry Class

The `ToolRegistry` class manages tool registration, schema generation, and execution. It provides a unified interface for registering tools and invoking them through the agent loop.

### Key Methods

#### register(name, func, schema=None)

Registers a tool function with the registry.

```python
registry.register("tool_name", tool_function, tool_schema)
```

**Parameters:**
- `name` (str): Unique identifier for the tool
- `func` (Callable): The tool function (can be sync or async)
- `schema` (dict, optional): JSON Schema description for function calling

#### execute(tool_name, **kwargs)

Executes a registered tool by name. Supports both synchronous and asynchronous functions.

```python
result = await registry.execute("tool_name", param1="value1", param2="value2")
```

**Parameters:**
- `tool_name` (str): Name of the tool to execute
- `**kwargs`: Arguments to pass to the tool function

**Returns:**
- Any: The result returned by the tool function

#### get_tool(name)

Retrieves a tool function by name.

**Parameters:**
- `name` (str): Tool name

**Returns:**
- Callable: The registered tool function

**Raises:**
- KeyError: If the tool is not found

#### get_schemas()

Returns all tool schemas in JSON Schema format, suitable for LLM function calling.

**Returns:**
- List[dict]: List of JSON Schema definitions for all registered tools

### Schema Inference

The registry automatically infers JSON Schema from function signatures. It supports:

- **Basic types**: `str`, `int`, `float`, `bool`
- **Container types**: `List[T]`, `Dict`
- **Union types**: `Optional[T]`, `Union[T1, T2]`
- **Parameter descriptions**: Extracted from docstrings

Example inferred schema:

```json
{
  "type": "function",
  "function": {
    "name": "file_read",
    "description": "Read file content with line numbers.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "File path to read (absolute or relative to .seed directory)."
        },
        "start": {
          "type": "integer",
          "description": "Start line number (1-based)."
        },
        "count": {
          "type": "integer",
          "description": "Number of lines to read."
        }
      },
      "required": ["path"]
    }
  }
}
```

---

## Core Tools

The core tools (`builtin_tools.py`) provide essential file operations and code execution capabilities. These five tools form the foundation of agent interactions with the filesystem.

### file_read

Reads file content with line numbers for easy reference.

**Function Signature:**
```python
def file_read(path: str, start: int = 1, count: int = 100) -> str
```

**Parameters:**
- `path` (str): File path to read. Can be absolute or relative to the `.seed` directory.
- `start` (int, optional): Start line number (1-based). Defaults to 1.
- `count` (int, optional): Number of lines to read. Defaults to 100.

**Returns:**
- str: File content with line numbers in format `line_number|content`, or error message if file not found.

**Path Resolution:**
- Absolute paths are used as-is
- Relative paths first check `.seed` directory, then project root
- Default working directory: `~/.seed/`

---

### file_write

Writes content to a file with support for overwrite or append modes.

**Function Signature:**
```python
def file_write(path: str, content: str, mode: str = "overwrite") -> str
```

**Parameters:**
- `path` (str): File path to write. Supports absolute and relative paths.
- `content` (str): Content to write to the file.
- `mode` (str, optional): Write mode - `"overwrite"` (default) or `"append"`.

**Returns:**
- str: Success message with file path and character count, or error message.

**Behavior:**
- Creates parent directories if they do not exist
- Overwrite mode replaces existing content
- Append mode adds content to the end of the file

---

### file_edit

Edits a file by replacing exact text matches.

**Function Signature:**
```python
def file_edit(path: str, old_str: str, new_str: str, replace_all: bool = False) -> str
```

**Parameters:**
- `path` (str): File path to edit. Supports absolute and relative paths.
- `old_str` (str): Text to find and replace. Must be an exact match.
- `new_str` (str): New text to insert in place of the matched text.
- `replace_all` (bool, optional): If `True`, replaces all occurrences. If `False` (default), replaces only the first occurrence.

**Returns:**
- str: Success message with the number of replacements made, or error message.

**Error Handling:**
- Returns error if the search string is not found in the file
- Handles FileNotFoundError and other exceptions gracefully

---

### code_as_policy

Executes code in various programming languages. Supports Python, JavaScript, Shell, and PowerShell.

**Function Signature:**
```python
def code_as_policy(code: str, language: str = "python", cwd: str = None, timeout: int = 60) -> str
```

**Parameters:**
- `code` (str): Code string to execute.
- `language` (str, optional): Language type. Supported values:
  - `python` or `py`
  - `javascript`, `js`, or `node`
  - `shell`, `bash`, or `sh`
  - `powershell`, `ps`, or `pwsh`
  - Defaults to `python`.
- `cwd` (str, optional): Working directory for execution. Defaults to `.seed` directory.
- `timeout` (int, optional): Execution timeout in seconds. Defaults to 60.

**Returns:**
- str: Execution output (stdout + stderr), or error message.

**Error Handling:**
- Returns timeout error if execution exceeds the specified timeout
- Returns interpreter not found error if the runtime is not installed
- Includes exit code in output if non-zero

---

### ask_user

Requests user input or confirmation during task execution. Used to pause agent execution and wait for human response.

**Function Signature:**
```python
def ask_user(question: str, options: list = None) -> str
```

**Parameters:**
- `question` (str): Question or prompt to display to the user.
- `options` (list, optional): Optional list of choices for the user to select from.

**Returns:**
- str: Formatted instruction string indicating the agent is waiting for user response.

**Output Format:**
```
[ASK_USER] {question}
Options: {option1, option2, ...}
[Waiting for user response]
```

---

## Memory Tools

The memory tools (`memory_tools.py`) implement a hierarchical memory system (L1-L4) for persistent knowledge management and session history tracking.

### Memory Hierarchy

| Level | Type | Purpose | Location |
|-------|------|---------|----------|
| L1 | Index | Quick reference index for available SOPs | `~/.seed/memory/notes.md` |
| L2 | Skills | Reusable skills following Open Agent Skills spec | `~/.seed/memory/skills/` |
| L3 | Knowledge | Long-term knowledge and documentation | `~/.seed/memory/knowledge/` |
| L4 | Raw | Raw session data and logs | `~/.seed/memory/raw/` |

---

### write_memory

Writes memory content to the specified level with validation.

**Function Signature:**
```python
def write_memory(level: str, content: str, title: str = "", metadata: str = "") -> str
```

**Parameters:**
- `level` (str): Memory level - `"L1"`, `"L2"`, `"L3"`, or `"L4"`.
- `content` (str): Memory content. For L2, must be in SKILL.md format with YAML frontmatter.
- `title` (str, optional): Memory title or skill name. For L1, used as section header.
- `metadata` (str, optional): Optional metadata such as source or date.

**Returns:**
- str: Success message or error description.

**Validation Rules:**
- **L1**: Content must not exceed 200 characters. Cannot contain subsections (`##`) or code blocks (```).
- **L2**: Must start with YAML frontmatter (---). Must contain `name` and `description` fields.
- **L3/L4**: Free-form content with optional metadata.

---

### read_memory_index

Reads the global memory index (L1) to find available SOPs or knowledge references.

**Function Signature:**
```python
def read_memory_index() -> str
```

**Returns:**
- str: Content of `notes.md` if it exists, or an error message if not found.

---

### search_memory

Searches memory across specified levels by keyword.

**Function Signature:**
```python
def search_memory(keyword: str, levels: list = ["L1", "L2", "L3"]) -> str
```

**Parameters:**
- `keyword` (str): Search keyword (case-insensitive).
- `levels` (list, optional): Levels to search. Defaults to `["L1", "L2", "L3"]`.

**Returns:**
- str: List of matching files with their level indicators, or "No matching memory found."

---

### start_long_term_update

Triggers the experience extraction process when the agent believes a task is complete. Dynamically reads the memory SOP and injects it into the prompt.

**Function Signature:**
```python
def start_long_term_update(args, **kwargs) -> str
```

**Returns:**
- str: Prompt instructing the agent to extract and save effective experiences from the completed task.

---

## Session History Tools

These tools manage conversation history persistence in L4 raw/sessions using JSONL format.

### save_session_history

Saves conversation history to L4 raw/sessions in JSONL format.

**Function Signature:**
```python
def save_session_history(messages: list, summary: str = None, session_id: str = None) -> str
```

**Parameters:**
- `messages` (list): List of message dictionaries with `role`, `content`, `tool_calls`, etc.
- `summary` (str, optional): Optional session summary.
- `session_id` (str, optional): Session identifier (filename). If not provided, a new one is generated.

**Returns:**
- str: Session ID and message count, or error message.

**Storage Format:**
- JSONL (JSON Lines) format with one JSON object per line
- Includes metadata line, message lines, and optional summary line

---

### load_session_history

Loads conversation history from L4 raw/sessions.

**Function Signature:**
```python
def load_session_history(session_id: str) -> str
```

**Parameters:**
- `session_id` (str): Session filename (e.g., `session_20240418_123456.jsonl`)

**Returns:**
- str: Formatted session data including session ID, creation time, message count, summary, and message content.

**Fuzzy Matching:**
- If exact session ID not found, attempts to find matching sessions by prefix or contains

---

### list_sessions

Lists recent conversation sessions from L4 raw/sessions.

**Function Signature:**
```python
def list_sessions(limit: int = 10) -> str
```

**Parameters:**
- `limit` (int, optional): Maximum number of sessions to return. Defaults to 10.

**Returns:**
- str: List of sessions with metadata including session ID, creation time, message count, and summary (if available).

---

### search_history

Searches conversation history by keyword in L4 raw/sessions.

**Function Signature:**
```python
def search_history(keyword: str, limit: int = 20) -> str
```

**Parameters:**
- `keyword` (str): Search keyword (case-insensitive).
- `limit` (int, optional): Maximum number of results to return. Defaults to 20.

**Returns:**
- str: Matching messages with session and context information.

**Output Format:**
- Includes session ID, timestamp, role, matched content, and surrounding context

---

## Skill Loader

The skill loader (`skill_loader.py`) implements a progressive disclosure pattern for loading agent skills. Skills are defined in SKILL.md files with YAML frontmatter.

### Open Agent Skills Specification

Skills follow a specific format stored in `~/.seed/memory/skills/`:

```
~/.seed/memory/skills/
├── skill_name/
│   └── SKILL.md
└── another_skill/
    └── SKILL.md
```

### YAML Frontmatter Format

Each SKILL.md file must start with YAML frontmatter:

```yaml
---
name: skill-name
description: Brief description of the skill
allowed-tools: tool1 tool2 tool3
metadata:
  version: "1.0"
  author: "user"
---
```

**Required Fields:**
- `name`: Skill identifier (lowercase letters, numbers, hyphens only; 1-64 characters)
- `description`: Brief description of what the skill does

**Optional Fields:**
- `allowed-tools`: Space-separated list of permitted tool names
- `metadata`: Additional metadata as key-value pairs

### SkillLoader Class

The `SkillLoader` class provides methods for loading and managing skills.

#### get_skills_list()

Returns all skill metadata as a list.

**Returns:**
- List[dict]: List of skill metadata dictionaries with keys: `name`, `description`, `path`, `allowed_tools`, `metadata`

#### get_skills_prompt()

Generates a formatted skill list for injection into system prompts.

**Returns:**
- str: Formatted string listing available skills with descriptions.

**Output Format:**
```
## 可用技能 (Skills)

- **skill-name**: Brief description...
- **another-skill**: Another description...

When user request matches a skill description, call `load_skill` to load full instructions.
```

#### match_skill(query)

Matches a user query against available skills to find the most relevant one.

**Parameters:**
- `query` (str): User query or request text

**Returns:**
- str or None: Name of the best matching skill, or None if no match found

**Matching Algorithm:**
- Calculates keyword overlap between query and skill name/description
- Returns the skill with the highest match score

#### load_skill_content(name)

Loads the complete skill content for a specific skill.

**Parameters:**
- `name` (str): Skill name (e.g., `'architecture-overview'`)

**Returns:**
- str or None: Complete SKILL.md content, or None if skill not found

#### get_skill_allowed_tools(name)

Returns the list of tools approved for use with a specific skill.

**Parameters:**
- `name` (str): Skill name

**Returns:**
- List[str]: List of allowed tool names, or empty list if skill not found

---

## Tool Functions

### load_skill

Loads complete skill content by name.

**Function Signature:**
```python
def load_skill(name: str) -> str
```

**Parameters:**
- `name` (str): Skill name (e.g., `'architecture-overview'`)

**Returns:**
- str: Complete SKILL.md content, or error message if skill not found

---

### list_skills

Lists all available skills with their descriptions.

**Function Signature:**
```python
def list_skills() -> str
```

**Returns:**
- str: Formatted list of available skills.

**Output Format:**
```
Available Skills:
- skill-name: Description (truncated to 100 chars)...
- another-skill: Description...
```

---

## Ralph Tools

The Ralph tools (`ralph_tools.py`) provide tools for managing Ralph Loop execution. These tools enable the agent to configure, monitor, and control long-cycle deterministic task execution.

### start_ralph_loop

Configures and prepares a Ralph Loop for execution.

**Function Signature:**
```python
def start_ralph_loop(
    task_prompt_file: str,
    completion_type: str = "marker_file",
    max_iterations: int = 1000,
    completion_criteria: Dict = None
) -> str
```

**Parameters:**
- `task_prompt_file` (str): Task description file path (relative path from `~/.seed/tasks/`)
- `completion_type` (str): Completion verification type:
  - `marker_file` (default): Completion marker file
  - `test_pass`: Test pass rate verification
  - `file_exists`: Target file existence verification
  - `git_clean`: Git working directory clean verification
  - `custom_check`: Custom validation function
- `max_iterations` (int): Maximum iterations (default: 1000, max duration: 8 hours)
- `completion_criteria` (Dict): Verification conditions based on type

**Returns:**
- str: Ralph Loop configuration status and ID

---

### write_completion_marker

Writes a completion marker for Ralph Loop's marker_file verification.

**Function Signature:**
```python
def write_completion_marker(content: str = "DONE", marker_path: str = None) -> str
```

**Parameters:**
- `content` (str): Marker content (default: "DONE", supports "COMPLETE", "TASK_FINISHED")
- `marker_path` (str): Marker file path (default: `~/.seed/completion_promise`)

**Returns:**
- str: Success message with marker path

---

### check_ralph_status

Checks the status of a Ralph Loop.

**Function Signature:**
```python
def check_ralph_status(ralph_id: str = None) -> str
```

**Parameters:**
- `ralph_id` (str): Ralph Loop ID (optional, lists all if not provided)

**Returns:**
- str: Ralph Loop status information including iteration count, start time, task file

---

### stop_ralph_loop

Stops a Ralph Loop execution.

**Function Signature:**
```python
def stop_ralph_loop(ralph_id: str) -> str
```

**Parameters:**
- `ralph_id` (str): Ralph Loop ID

**Returns:**
- str: Operation result (state preserved for recovery)

---

### create_ralph_task_file

Creates a Ralph Loop task description file.

**Function Signature:**
```python
def create_ralph_task_file(task_name: str, task_description: str) -> str
```

**Parameters:**
- `task_name` (str): Task name for file naming
- `task_description` (str): Detailed task description

**Returns:**
- str: Task file path

---

## Session Database (SQLite+FTS5)

The session database (`session_db.py`) provides SQLite+FTS5 storage for L4 session history with Chinese full-text search support using jieba tokenization.

### SessionDB Class

The `SessionDB` class manages SQLite database connections and operations.

#### `__init__(db_path: str = None)`

Initializes database connection with schema creation.

```python
class SessionDB:
    """Session 数据库管理类 (SQLite + FTS5)"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)  # ~/.seed/memory/raw/sessions.db
        self._init_db()
```

**Schema:**
- `session_messages`: Main message table with session_id, timestamp, role, content
- `session_messages_fts`: FTS5 virtual table for full-text search
- `sessions_meta`: Metadata table with summary and message count

---

### save_session_history

Saves conversation history to SQLite with FTS5 indexing.

**Function Signature:**
```python
def save_session_history(messages: List[Dict], summary: str = None, session_id: str = None) -> str
```

**Parameters:**
- `messages` (List[Dict]): Message list with role, content, tool_calls
- `summary` (str): Optional session summary
- `session_id` (str): Session identifier (auto-generated if not provided)

**Returns:**
- str: Session ID and message count

**FTS5 Processing:**
- Content tokenized with jieba for Chinese text
- Tokens stored in FTS5 virtual table for search
- WAL mode for concurrent access

---

### load_session_history

Loads conversation history from SQLite.

**Function Signature:**
```python
def load_session_history(session_id: str) -> str
```

**Parameters:**
- `session_id` (str): Session ID (supports fuzzy matching)

**Returns:**
- str: Formatted session data with metadata and messages

---

### list_sessions

Lists recent sessions from database.

**Function Signature:**
```python
def list_sessions(limit: int = 10) -> str
```

**Parameters:**
- `limit` (int): Maximum sessions to return (default: 10)

**Returns:**
- str: Session list with ID, message count, creation time, summary

---

### search_history

Full-text search using FTS5 with jieba tokenization.

**Function Signature:**
```python
def search_history(keyword: str, limit: int = 20) -> str
```

**Parameters:**
- `keyword` (str): Search keyword (Chinese text supported)
- `limit` (int): Maximum results (default: 20)

**Returns:**
- str: Matching messages with session context and highlighted previews

**Chinese Search:**
- Uses jieba for tokenization preprocessing
- OR logic for Chinese tokens to improve recall
- Fallback to LIKE search if FTS5 fails

---

### search_with_filters

Enhanced search with multiple filter conditions.

**Function Signature:**
```python
def search_with_filters(
    keyword: str,
    session_id: Optional[str] = None,
    role: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 20
) -> List[Dict]
```

**Returns:**
- List[Dict]: Matching message dictionaries with full metadata

---

## Subagent Tools

The subagent tools (`subagent_tools.py`) provide tools for managing subagent execution. These tools enable the agent to spawn independent context-isolated subagents, wait for their completion, aggregate results, and manage the subagent lifecycle.

### Overview

Subagents operate with independent context windows, enabling parallel execution without polluting the main conversation history. They support different permission sets for various task types.

**Related Components:** See [src/AGENTS.md](../src/AGENTS.md) for SubagentManager architecture details.

### Subagent Types

| Type | Permission Set | Description |
|------|----------------|-------------|
| `explore` | read_only | Read-only exploration: file search, code reading |
| `review` | review | Review verification: read-only + code execution |
| `implement` | implement | Implementation execution: full permissions |
| `plan` | plan | Planning analysis: read-only + memory write |

### Permission Sets

| Permission Set | Allowed Tools |
|----------------|---------------|
| `read_only` | file_read, search_history, ask_user |
| `review` | file_read, code_as_policy, search_history, ask_user |
| `implement` | file_read, file_write, file_edit, code_as_policy, memory tools, search_history |
| `plan` | file_read, write_memory, search_history, ask_user |

---

### spawn_subagent

Creates and starts a subagent task with specified type and prompt.

**Function Signature:**
```python
def spawn_subagent(
    type: str,
    prompt: str,
    custom_tools: List[str] = None,
    timeout: int = 300,
) -> str
```

**Parameters:**
- `type` (str): Subagent type - `"explore"`, `"review"`, `"implement"`, or `"plan"`
- `prompt` (str): Task prompt describing what the subagent should accomplish
- `custom_tools` (List[str], optional): Custom tool list overriding default permission set
- `timeout` (int, optional): Execution timeout in seconds. Defaults to 300.

**Returns:**
- str: Task ID, type, and status information for tracking

**Error Handling:**
- Returns error if SubagentManager not initialized
- Returns error if unknown subagent type specified

---

### wait_for_subagent

Waits for a subagent to complete and returns results (synchronous wrapper).

**Function Signature:**
```python
def wait_for_subagent(
    task_id: str,
    timeout: float = None,
) -> str
```

**Parameters:**
- `task_id` (str): Task ID to wait for
- `timeout` (float, optional): Wait timeout in seconds. None means no timeout.

**Returns:**
- str: Task execution result or status message if not yet complete

**Note:** In AgentLoop's async context, actual execution is handled by `_execute_tool_calls`.

---

### wait_for_subagent_async

Async version that properly waits for subagent completion.

**Function Signature:**
```python
async def wait_for_subagent_async(
    task_id: str,
    timeout: float = None,
) -> str
```

**Parameters:**
- `task_id` (str): Task ID to wait for
- `timeout` (float, optional): Wait timeout in seconds. None means infinite wait.

**Returns:**
- str: Task execution result summary or timeout error message

**Error Handling:**
- Returns timeout error if wait exceeds specified timeout
- Returns error if SubagentManager not initialized

---

### aggregate_subagent_results

Aggregates results from multiple subagent tasks.

**Function Signature:**
```python
def aggregate_subagent_results(
    task_ids: List[str],
    include_errors: bool = True,
    max_length: int = 2000,
) -> str
```

**Parameters:**
- `task_ids` (List[str]): List of task IDs to aggregate
- `include_errors` (bool, optional): Include failed task error info. Defaults to True.
- `max_length` (int, optional): Maximum display length per result. Defaults to 2000.

**Returns:**
- str: Aggregated result summary from all specified tasks

---

### list_subagents

Lists all subagent tasks with their status.

**Function Signature:**
```python
def list_subagents(status: str = None) -> str
```

**Parameters:**
- `status` (str, optional): Filter by status - `"pending"`, `"running"`, `"completed"`, `"failed"`, `"timeout"`

**Returns:**
- str: Task list with ID, type, status, and prompt preview

**Output Format:**
```
Subagent Tasks:
  [task_id] explore - running
    Prompt: Search for...
```

---

### kill_subagent

Terminates a running subagent task.

**Function Signature:**
```python
def kill_subagent(task_id: str) -> str
```

**Parameters:**
- `task_id` (str): Task ID to terminate

**Returns:**
- str: Operation result or error message

**Behavior:**
- Returns message if task already completed (no need to kill)
- Cleans up task resources on termination

---

### get_subagent_status

Gets detailed status for a single subagent.

**Function Signature:**
```python
def get_subagent_status(task_id: str) -> str
```

**Parameters:**
- `task_id` (str): Task ID to query

**Returns:**
- str: Detailed status including execution count, duration, and result details if completed

---

### spawn_parallel_subagents

Creates and starts multiple subagent tasks in parallel.

**Function Signature:**
```python
def spawn_parallel_subagents(
    tasks: List[Dict],
) -> str
```

**Parameters:**
- `tasks` (List[Dict]): Task specification list, each containing:
  - `type` (str): Subagent type
  - `prompt` (str): Task prompt
  - `timeout` (int, optional): Custom timeout

**Returns:**
- str: List of created task IDs with startup information

**Example:**
```python
spawn_parallel_subagents([
    {"type": "explore", "prompt": "Search for authentication code"},
    {"type": "explore", "prompt": "Find database connection logic"}
])
```

---

### init_subagent_manager

Initializes the global SubagentManager instance.

**Function Signature:**
```python
def init_subagent_manager(manager) -> None
```

**Parameters:**
- `manager`: SubagentManager instance from AgentLoop initialization

**Note:** This is called internally by AgentLoop during initialization.

---

## Registration Functions

These functions register the respective tools with a ToolRegistry instance:

- `register_builtin_tools(registry)`: Registers the 5 core tools
- `register_memory_tools(registry)`: Registers memory and session tools
- `register_skill_tools(registry)`: Registers skill loading tools
- `register_subagent_tools(registry)`: Registers 7 subagent management tools

**Example Usage:**
```python
from src.tools import ToolRegistry
from src.tools.builtin_tools import register_builtin_tools
from src.tools.memory_tools import register_memory_tools
from src.tools.skill_loader import register_skill_tools
from src.tools.subagent_tools import register_subagent_tools

registry = ToolRegistry()
register_builtin_tools(registry)
register_memory_tools(registry)
register_skill_tools(registry)
register_subagent_tools(registry)

# Now tools can be executed
schemas = registry.get_schemas()
result = await registry.execute("file_read", path="example.txt")
```
