# Tool Registry System

This module provides a comprehensive tool registration and execution framework for the Seed Agent system. It enables dynamic tool registration, automatic schema inference, and supports both synchronous and asynchronous tool execution.

## Module Overview

The tool registry system is located in `src/tools/` and consists of four main components:

| File | Purpose |
|------|---------|
| `__init__.py` | ToolRegistry class for registering and executing tools |
| `builtin_tools.py` | Five core built-in tools for file operations and code execution |
| `memory_tools.py` | L1-L4 memory management system and session history tools |
| `skill_loader.py` | Dynamic skill loading with progressive disclosure pattern |

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

## Registration Functions

These functions register the respective tools with a ToolRegistry instance:

- `register_builtin_tools(registry)`: Registers the 5 core tools
- `register_memory_tools(registry)`: Registers memory and session tools
- `register_skill_tools(registry)`: Registers skill loading tools

**Example Usage:**
```python
from src.tools import ToolRegistry
from src.tools.builtin_tools import register_builtin_tools
from src.tools.memory_tools import register_memory_tools
from src.tools.skill_loader import register_skill_tools

registry = ToolRegistry()
register_builtin_tools(registry)
register_memory_tools(registry)
register_skill_tools(registry)

# Now tools can be executed
schemas = registry.get_schemas()
result = await registry.execute("file_read", path="example.txt")
```
