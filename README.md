# Seed Agent

A modular, asynchronous autonomous AI agent system supporting multi-provider LLM configuration, tool execution, streaming output, and self-evolving capabilities. The system is designed as a physics-level autonomous executor capable of independent reasoning, memory persistence, and self-improvement through exploration.

## Project Structure

```
seed-agent/
├── main.py                  # Interactive CLI entry point
├── requirements.txt         # Python dependencies
│
├── src/                     # Core engine
│   ├── __init__.py
│   ├── agent_loop.py        # Main agent loop (conversation lifecycle, tool execution)
│   ├── autonomous.py        # Idle-time autonomous exploration (Ralph enhanced)
│   ├── client.py            # LLM Gateway (OpenAI compatible, multi-provider fallback)
│   ├── models.py            # Pydantic configuration validation
│   ├── ralph_loop.py        # Long-cycle deterministic task executor
│   ├── scheduler.py         # Task scheduling and management
│   ├── rate_limiter.py      # Token bucket rate limiter for API call throttling
│   ├── rate_limit_db.py     # SQLite storage for rate limit tracking
│   ├── request_queue.py    # Async request queue with priority support
│   ├── subagent.py          # Subagent instance with isolated context
│   ├── subagent_manager.py  # Subagent lifecycle and parallel execution manager
│   └── tools/               # Tool registry system
│       ├── __init__.py      # ToolRegistry class with schema inference
│       ├── builtin_tools.py # 5 core tools (file ops, code exec)
│       ├── memory_tools.py  # L1-L4 memory management
│       ├── skill_loader.py  # Dynamic skill loading (progressive disclosure)
│       ├── ralph_tools.py   # Ralph Loop management tools
│       ├── session_db.py    # SQLite+FTS5 session storage (Chinese FTS)
│       └── subagent_tools.py # Subagent spawning and management tools
│
├── core_principles/         # System prompts and core principles
│   ├── system_prompts_en.md # English system prompts
│   └── system_prompts_zh.md # Chinese system prompts
│
├── memory/                  # Memory system (L1-L4 hierarchy)
│   ├── memory.md            # Memory hierarchy details
│   └── auto_dream.md        # Memory consolidation SOP
│
├── auto/                    # Autonomous exploration module
│   └── 自主探索 SOP.md       # Autonomous exploration SOP (Chinese)
│
├── docs/                    # Design documentation
│   ├── L4_SQLite_FTS5_Design.md        # L4 storage migration design
│   ├── long_cycle_loop_enhancement_design.md  # Ralph Loop design
│   └── ralph_loop.md        # Ralph Loop concept documentation
│
├── examples/                # Usage examples
│   └── simple_agent.py      # Basic agent usage demo
│
├── scripts/                 # Utility scripts
├── tests/                   # Test files
└── tasks/                   # Task storage directory
```

---

## Architecture Overview

Seed Agent implements a hierarchical agent architecture with the following core components:

### AgentLoop Engine

The central orchestrator (`src/agent_loop.py`) manages conversation flow, tool execution, history summarization, and maintains session state across interactions. Key features:

- **Message History Management**: Automatic summarization at configured intervals
- **Tool Call Iteration**: Parallel execution with retry logic (max 30 iterations)
- **Streaming Output**: Real-time response chunks via `stream_run()`
- **Context Compression**: Token-aware summarization when context window exceeds 75%
- **Interrupt Handling**: Priority user input injection

### Multi-Provider Gateway

The LLM Gateway (`src/client.py`) provides a unified OpenAI-compatible interface supporting multiple providers with automatic failover:

- **FallbackChain**: Primary → fallback provider switching on failures
- **Retry Logic**: 3 retries with exponential backoff per provider
- **Health Tracking**: Status monitoring (healthy/degraded/unavailable)
- **Environment Variables**: API key resolution via `${VAR_NAME}` format

### Ralph Loop Engine

A long-cycle deterministic task executor (`src/ralph_loop.py`) designed for complex, multi-step operations:

- **External Verification**: Completion driven by objective criteria (tests passing, marker files, git clean)
- **Fresh Context**: Periodic context reset prevents drift in long-running tasks
- **State Persistence**: Task state saved to filesystem for crash recovery
- **Safety Limits**: Max 1000 iterations or 8 hours execution time

**Completion Types:**
| Type | Description | Use Case |
|------|-------------|----------|
| `TEST_PASS` | Test suite passes at specified rate | Code refactoring, bug fixes |
| `FILE_EXISTS` | Target files created | File generation tasks |
| `MARKER_FILE` | Completion marker written | Multi-step workflows |
| `GIT_CLEAN` | Working directory clean | Full project changes |
| `CUSTOM_CHECK` | Custom validation function | Domain-specific validation |

### Task Scheduler

The scheduler (`src/scheduler.py`) enables autonomous task creation and management:

**Built-in Tasks:**
| Task | Interval | Purpose |
|------|----------|---------|
| `autodream` | 12 hours | Memory consolidation and cleanup |

**Note**: `autonomous_explore` is managed by `AutonomousExplorer` class independently (30-minute idle monitoring), not by Scheduler.

**Features:**
- CRUD operations via tool functions
- Task persistence to `~/.seed/tasks/`
- Enable/disable toggle per task
- Execution logging in JSONL format

### Autonomous Explorer

Idle-time autonomous task execution (`src/autonomous.py`) monitors user activity:

- **Trigger**: 30 minutes of user inactivity
- **Workflow**: Check TODO.md → Execute existing tasks OR generate new ones
- **SOP Integration**: Follows defined Standard Operating Procedures
- **Ralph Integration**: Enhanced with completion promise detection

### Rate Limiting System

The rate limiter (`src/rate_limiter.py`) provides token bucket-based API throttling:

- **Token Bucket Algorithm**: Configurable capacity and refill rate per provider
- **Per-Provider Limits**: Independent rate limits for different LLM providers
- **Persistent Tracking**: Rate limit state stored in SQLite (`rate_limit.db`)
- **Auto-Recovery**: Automatic wait and retry when tokens are depleted

**Features:**
- Burst allowance for handling traffic spikes
- Thread-safe async operations
- Provider-specific configuration
- Health status reporting

### Request Queue System

The request queue (`src/request_queue.py`) manages async task execution with priority:

- **Priority Queue**: Higher priority requests processed first
- **Flow Control**: Backpressure handling when system is under load
- **Request Batching**: Aggregate multiple requests for efficiency
- **Timeout Management**: Automatic timeout and cleanup for stalled requests

**Queue Features:**
- FIFO ordering within priority levels
- Concurrent request limiting
- Request cancellation support
- Metrics and monitoring

### Subagent System

The subagent system (`src/subagent.py`, `src/subagent_manager.py`) enables parallel task execution with isolated contexts:

- **Isolated Contexts**: Each subagent has independent conversation history
- **Parallel Execution**: Up to 3 concurrent subagents by default
- **Permission Isolation**: Configurable permission sets per subagent type
- **Result Aggregation**: Unified results returned to main conversation

**Subagent Types:**
| Type | Permission Set | Use Case |
|------|----------------|----------|
| `EXPLORE` | read_only | File exploration, code search |
| `REVIEW` | review | Code review, testing |
| `IMPLEMENT` | implement | Feature implementation |
| `PLAN` | plan | Task planning, analysis |

**Permission Sets:**
| Permission | Allowed Tools |
|------------|---------------|
| `read_only` | file_read, search_history, ask_user |
| `review` | file_read, code_as_policy, search_history, ask_user |
| `implement` | file_read, file_write, file_edit, code_as_policy, memory tools, search_history |
| `plan` | file_read, write_memory, search_history, ask_user |

---

## Memory System

A four-tier hierarchical memory architecture for persistent knowledge management:

| Tier | Name | Purpose | Storage | Persistence |
|------|------|---------|---------|-------------|
| L1 | Index | Quick reference to available SOPs | `notes.md` | Session |
| L2 | Skills | Reusable operation procedures | `skills/*.md` | Persistent |
| L3 | Knowledge | Cross-task patterns and principles | `knowledge/*.md` | Persistent |
| L4 | Raw | Session history and execution logs | SQLite+FTS5 | Persistent |

### L4 SQLite+FTS5 Storage

Session history is now stored in SQLite with FTS5 full-text search:

- **Chinese FTS**: jieba tokenization for Chinese content search
- **Schema**: `session_messages` + `sessions_meta` + FTS5 virtual table
- **Performance**: WAL mode, optimized caching, async writes
- **Search**: `search_history()` with keyword matching and context extraction

---

## Tool System

The tool registry (`src/tools/`) provides extensible agent capabilities through five modules:

### Built-in Tools (`builtin_tools.py`)

| Tool | Signature | Purpose |
|------|-----------|---------|
| `file_read` | `(path, start=1, count=100)` | Read file with line numbers |
| `file_write` | `(path, content, mode="overwrite")` | Write/append to file |
| `file_edit` | `(path, old_str, new_str, replace_all=False)` | Replace exact text |
| `code_as_policy` | `(code, language="python", timeout=60)` | Execute code (py/js/sh/ps) |
| `ask_user` | `(question, options=None)` | Request user confirmation |

### Memory Tools (`memory_tools.py`)

- `write_memory(level, content, title, metadata)` - Write to L1-L4
- `read_memory_index()` - Read L1 index
- `search_memory(keyword, levels)` - Search across levels
- `start_long_term_update()` - Trigger experience extraction

### Session Tools (`session_db.py`)

- `save_session_history(messages, summary, session_id)` - Save to SQLite
- `load_session_history(session_id)` - Load specific session
- `list_sessions(limit)` - List recent sessions
- `search_history(keyword, limit)` - FTS5 search with jieba

### Ralph Tools (`ralph_tools.py`)

- `start_ralph_loop(task_file, completion_type, criteria)` - Configure Ralph Loop
- `write_completion_marker(content, marker_path)` - Signal task completion
- `check_ralph_status(ralph_id)` - Check loop status
- `stop_ralph_loop(ralph_id)` - Stop execution
- `create_ralph_task_file(task_name, description)` - Create task file

### Skill Loader (`skill_loader.py`)

Progressive disclosure pattern for skill management:

- `load_skill(name)` - Load complete skill content
- `list_skills()` - List available skills
- Skills stored in SKILL.md format with YAML frontmatter

### Subagent Tools (`subagent_tools.py`)

Tools for spawning and managing subagent instances:

- `spawn_subagent(type, prompt)` - Create new subagent with specified type
- `wait_for_subagent(task_id)` - Wait for subagent completion
- `aggregate_subagent_results(task_ids)` - Combine results from multiple subagents
- `list_subagents(status)` - List running or completed subagents
- `kill_subagent(task_id)` - Terminate running subagent
- `spawn_parallel_subagents(tasks)` - Launch multiple subagents simultaneously

---

## Configuration

### Configuration File

The system reads configuration from `~/.seed/config.json`:

```json
{
  "models": {
    "bailian": {
      "baseUrl": "https://coding.dashscope.aliyuncs.com/v1",
      "apiKey": "${BAILIAN_API_KEY}",
      "api": "openai-completions",
      "models": [
        {
          "id": "qwen-coder-plus",
          "name": "Qwen Coder Plus",
          "contextWindow": 100000,
          "maxTokens": 4096
        }
      ]
    }
  },
  "agents": {
    "defaults": {
      "defaults": {
        "primary": "bailian/qwen-coder-plus"
      }
    }
  }
}
```

**API Key Resolution:**
- `${VAR_NAME}` → Resolved from environment variables
- Plain strings → Used directly

### Multi-Provider Fallback

Configure multiple providers for automatic failover:

```json
{
  "models": {
    "primary": {
      "baseUrl": "https://api.openai.com/v1",
      "apiKey": "${OPENAI_API_KEY}",
      "models": [{"id": "gpt-4", "name": "GPT-4", "contextWindow": 128000}]
    },
    "fallback": {
      "baseUrl": "https://coding.dashscope.aliyuncs.com/v1",
      "apiKey": "${BAILIAN_API_KEY}",
      "models": [{"id": "qwen-coder-plus", "name": "Qwen", "contextWindow": 100000}]
    }
  }
}
```

---

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure API Keys**:
   Set environment variables for your providers:
   ```bash
   export BAILIAN_API_KEY="your-key-here"
   # or add to .env file
   ```

3. **Run Interactive Mode**:
   ```bash
   python main.py
   ```

4. **One-shot Chat**:
   ```bash
   python main.py --chat "Your message here"
   ```

---

## Usage Examples

### Programmatic Usage

```python
import asyncio
from src.client import LLMGateway
from src.agent_loop import AgentLoop

async def main():
    gateway = LLMGateway("~/.seed/config.json")
    agent = AgentLoop(
        gateway=gateway,
        system_prompt="You are a helpful assistant.",
        max_iterations=30
    )
    
    # Synchronous response
    response = await agent.run("Hello!")
    print(response)
    
    # Streaming response
    async for chunk in agent.stream_run("Tell me a story"):
        if chunk['type'] == 'chunk':
            print(chunk['content'], end='')
        elif chunk['type'] == 'final':
            print()  # Newline at end

asyncio.run(main())
```

### Ralph Loop Usage

```python
from src.ralph_loop import RalphLoop, CompletionType

# Test-driven execution
ralph = RalphLoop.create_test_driven(
    agent_loop=agent,
    task_prompt_path=Path(".seed/tasks/refactor.md"),
    test_command="pytest tests/ -v",
    pass_rate=100
)
result = await ralph.run()

# Marker-driven execution
ralph = RalphLoop.create_marker_driven(
    agent_loop=agent,
    task_prompt_path=Path(".seed/tasks/task.md"),
    marker_path=Path(".seed/done")
)
result = await ralph.run()
```

---

## Module Documentation

| Module | Description | Documentation |
|--------|-------------|---------------|
| Core Engine | AgentLoop, LLMGateway, RalphLoop, Scheduler | [src/AGENTS.md](src/AGENTS.md) |
| Tools | Tool registry and development | [src/tools/AGENTS.md](src/tools/AGENTS.md) |
| Core Principles | System prompts | [core_principles/](core_principles/) |
| Memory | L1-L4 memory system | [memory/AGENTS.md](memory/AGENTS.md) |
| Autonomous | Self-exploration module | [auto/AGENTS.md](auto/AGENTS.md) |
| Examples | Usage examples | [examples/](examples/) |
| Design Docs | Architecture design documents | [docs/](docs/) |

---

## Design Documents

Key architectural design documents in `docs/`:

- **[L4 SQLite+FTS5 Design](docs/L4_SQLite_FTS5_Design.md)**: Session storage migration from JSONL to SQLite with Chinese full-text search
- **[Ralph Loop Enhancement](docs/long_cycle_loop_enhancement_design.md)**: Long-cycle task execution with external verification
- **[Ralph Loop Concept](docs/ralph_loop.md)**: Core concepts and motivation

---

## Data Storage

The system stores data in `~/.seed/`:

| Path | Purpose |
|------|---------|
| `~/.seed/config.json` | Configuration file |
| `~/.seed/memory/` | L1-L4 memory storage |
| `~/.seed/memory/raw/sessions.db` | SQLite session database |
| `~/.seed/rate_limit.db` | SQLite rate limit tracking database |
| `~/.seed/tasks/` | Task storage and logs |
| `~/.seed/logs/` | Daily log files |
| `~/.seed/scripts/` | Utility scripts |

---

## Dependencies

```
openai>=1.0.0        # Async OpenAI client
pydantic>=2.0.0      # Configuration validation
tenacity>=8.0.0      # Retry logic
python-dotenv>=1.0.0 # Environment loading
jieba>=0.42.0        # Chinese text segmentation (FTS5)
```

---

## Acknowledgments

Special thanks to [GenericAgent](https://github.com/lsdefine/GenericAgent) for inspiration to this project.