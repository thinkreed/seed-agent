# Seed Agent

A modular, asynchronous autonomous AI agent system supporting multi-provider LLM configuration, tool execution, streaming output, and self-evolving capabilities. The system is designed as a physics-level autonomous executor capable of independent reasoning, memory persistence, and self-improvement through exploration.

## Project Structure

```
seed-agent/
├── main.py                  # Interactive CLI entry point
├── requirements.txt         # Python dependencies
│
├── src/                     # Core engine (modular architecture)
│   ├── __init__.py
│   ├── agent_loop/          # Main agent loop (拆分为 6 个子模块)
│   │   ├── _init.py         # 初始化逻辑
│   │   ├── _observability.py # 可观测性集成
│   │   ├── _summarizer.py   # 消息摘要
│   │   ├── _skill_tracker.py # 技能追踪
│   │   ├── _execution.py    # 工具执行
│   │   └── _user_interaction.py # 用户交互
│   ├── autonomous/          # 自主探索 (拆分为 7 个子模块)
│   │   ├── _idle_monitor.py # 空闲监控
│   │   ├── _explorer.py     # 探索执行器
│   │   ├── _state_manager.py # 状态管理
│   │   ├── _task_executor.py # 任务执行
│   │   ├── _prompt_builder.py # Prompt 构建
│   │   ├── _sop_loader.py   # SOP 加载
│   │   └── _defense.py      # 防御机制
│   ├── client/              # LLM Gateway (拆分为多个子模块)
│   │   ├── _streaming.py    # 流式响应
│   │   ├── _execution.py    # 非流式执行
│   │   ├── _prompt_caching.py # 提示缓存保护
│   │   └── streaming_core/  # 流式核心模块
│   │   └ execution_core/    # 执行核心模块
│   ├── harness/             # 控制器 (拆分为 12 个子模块)
│   │   ├── _streaming.py    # 流式处理
│   │   ├── _streaming_loop.py # 流式循环
│   │   ├── _tool_router.py  # 工具路由
│   │   ├── _cycle.py        # 执行周期
│   │   └── lifecycle_ctx/   # 钩子上下文
│   ├── sandbox/             # 工作台 (拆分为 3 个子模块)
│   │   ├── sandbox.py       # 主入口
│   │   └ sandbox_core/      # 核心实现
│   ├── lifecycle_hooks/     # 生命周期钩子 (拆分为多个子模块)
│   │   ├── _message_bus.py  # 消息总线
│   │   ├── _command_runner.py # 命令钩子
│   │   ├── _http_runner.py  # HTTP 钩子
│   │   └── _aggregator.py   # 钩子聚合器
│   ├── tools/               # 工具注册系统 (拆分为多个子模块)
│   │   ├── __init__.py      # ToolRegistry + ToolKind + PermissionDecision
│   │   ├── _registry.py     # 延迟加载机制 (ToolFactory)
│   │   ├── builtin_tools.py # 5 个核心工具
│   │   ├── memory/          # 记忆工具 (拆分为 9 个子模块)
│   │   │   ├── _memory_write.py # 行动验证 + 去重
│   │   │   ├── _memory_search.py # Context Fencing
│   │   │   ├── _ttrl.py     # TTRL 持续学习
│   │   │   └── _extract_cursor.py # 提取光标
│   │   ├── skill_loader/    # 技能加载器 (拆分为 9 个子模块)
│   │   │   ├── _skillloader.py # 渐进式披露
│   │   │   ├── _hub.py      # Skills Hub 集成
│   │   │   └── _index.py    # 技能索引
│   │   ├── session_db.py    # SQLite+FTS5 会话存储
│   │   └── subagent_tools/  # Subagent 工具
│   ├── security/            # 安全模块
│   │   ├── credential_isolated/ # 凭证隔离沙盒
│   │   ├── risk_classifier/ # 命令风险分类
│   │   ├── secure_harness/  # 安全 Harness
│   │   └ vault/             # 凭证 Vault
│   ├── collaboration/       # 多智能体协作
│   ├── ralph_loop.py        # 长周期任务执行器
│   ├── scheduler/           # 任务调度 (拆分为 3 个子模块)
│   ├── subagent/            # Subagent 管理 (拆分为多个子模块)
│   └ context/               # 上下文裁剪
│   └ abort_signal/          # 取消信号
│   └ request_queue/         # 请求队列
│   └ rate_limiter.py        # Token Bucket 限流
│   └ rate_limit_db.py       # SQLite 限流状态
│   └ models.py              # Pydantic 配置验证
│
├── core_principles/         # 系统提示和核心原则 (禁止修改)
│   ├── system_prompts_en.md # 英文系统提示
│   └── system_prompts_zh.md # 中文系统提示
│
├── memory/                  # 记忆系统 (L1-L4 层级)
│   ├── memory.md            # 记忆层级详情
│   └── auto_dream.md        # 记忆整合 SOP
│
├── auto/                    # 自主探索模块
│   └── 自主探索 SOP.md       # 自主探索 SOP
│
├── docs/                    # 设计文档
│   ├── wiki_knowledge_integration_analysis.md # Wiki 知识落地分析
│   ├── harness/             # Harness 系列设计文档
│   ├── L4_SQLite_FTS5_Design.md # L4 存储迁移设计
│   └── ralph_loop.md        # Ralph Loop 概念
│
├── examples/                # 使用示例
├── scripts/                 # 工具脚本
├── tests/                   # 测试文件
└── tasks/                   # 任务存储目录
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

### Tool Classification (Wiki Knowledge)

Based on Qwen-Code's design, tools are classified by operation type:

**ToolKind Enum:**
| Kind | Description | Permission |
|------|-------------|------------|
| `Read` | File reading, listing | `allow` (safe) |
| `Search` | grep, glob, search | `allow` (safe) |
| `Edit` | File modification | `ask` (needs confirmation) |
| `Delete` | File deletion | `ask` (needs confirmation) |
| `Execute` | Code execution, shell | `ask` (needs confirmation) |
| `Memory` | Memory operations | `ask` (needs confirmation) |
| `Agent` | Subagent spawning | `ask` (needs confirmation) |

**Permission Decision Enum:**
| Decision | Behavior |
|----------|----------|
| `allow` | Direct execution, no confirmation needed |
| `ask` | Requires user confirmation before execution |
| `deny` | Blocked due to security policy |

**Concurrency Safety:**
- `CONCURRENCY_SAFE_KINDS`: `{Read, Search}` - Can be executed in parallel
- `MUTATOR_KINDS`: `[Edit, Delete, Execute, Memory]` - Need sequential execution

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

## Wiki Knowledge Integration

基于 E:\projects\wiki 目录下十个开源项目的架构分析，提取并落地的优化点：

### 已实现（P0+P1+P2+P3+P4+P5 全部完成）

| 优化点 | 来源 | 实现位置 | 状态 |
|------|------|----------|------|
| ToolKind 枚举分类 | qwen-code | `src/tools/__init__.py` | ✅ |
| PermissionDecision 三级权限 | qwen-code | `src/tools/__init__.py` | ✅ |
| LoopDetectionService | qwen-code | `src/harness/_loop_detection.py` | ✅ |
| 整合锁机制 | qwen-code | `src/tools/memory/_consolidation_lock.py` | ✅ |
| MessageBus.request() | qwen-code | `src/lifecycle_hooks/_message_bus.py` | ✅ |
| 延迟加载机制 (ToolFactory) | qwen-code (P2) | `src/tools/_registry.py` | ✅ |
| 命令钩子执行器 | qwen-code (P2) | `src/lifecycle_hooks/_command_runner.py` | ✅ |
| HTTP 钩子执行器 | qwen-code (P2) | `src/lifecycle_hooks/_http_runner.py` | ✅ |
| 渐进式披露 Skills | hermes | `src/tools/skill_loader/_skillloader.py` | ✅ |
| Context Fencing | hermes (P2) | `src/tools/memory/_memory_search.py` | ✅ |
| Skills Hub 集成 | hermes (P2) | `src/tools/skill_loader/_hub.py` | ✅ |
| 提示缓存保护机制 | hermes (P2) | `src/client/_prompt_caching.py` | ✅ |
| 行动验证原则 (VerifiedSource) | genericagent (P2) | `src/tools/memory/_memory_write.py` | ✅ |
| win_rate 字段 | mia | `src/tools/session/_rate_calculation.py` | ✅ |
| 记忆去重阈值 | mia (P2) | `src/tools/memory/_memory_write.py` | ✅ |
| TTRL 持续学习 | mia (P2) | `src/tools/memory/_ttrl.py` | ✅ |
| Subagent 上下文隔离 | open-agents | `src/subagent.py` | ✅ |
| **ToolCapability 能力声明** | deepseek-tui (P3) | `src/tools/_types.py` | ✅ |
| **ApprovalRequirement 三级审批** | deepseek-tui (P3) | `src/tools/_types.py` | ✅ |
| **AgentConfig 注册机制** | ai-hedge-fund (P3) | `src/subagent_manager_core/_agent_registry.py` | ✅ |
| **AgentSignal 统一输出** | ai-hedge-fund (P3) | `src/subagent_manager_core/_agent_registry.py` | ✅ |
| **Agent 依赖图拓扑排序** | shannon-architecture (P3) | `src/subagent_manager_core/_agent_registry.py` | ✅ |
| **Circuit Breaker 自动切换** | claude-mem + worldmonitor (P4) | `src/client/_circuit_breaker.py` | ✅ |
| **Orphan Reaper 孤儿回收** | claude-mem (P4) | `src/subagent_manager_core/_orphan_reaper.py` | ✅ |
| **Stampede Protection** | worldmonitor (P4) | `src/request_queue_core/_stampede.py` | ✅ |
| **复杂度评分路由** | manifest-architecture (P4) | `src/client/_complexity_scorer.py` | ✅ |
| **Specificity 检测** | manifest-architecture (P4) | `src/client/_specificity_detector.py` | ✅ |
| **Merkle DAG 增量索引** | claude-context-docs (P5) | `src/core/_merkle_dag.py` | ✅ |
| **FileSynchronizer** | claude-context-docs (P5) | `src/core/_file_synchronizer.py` | ✅ |
| **SemanticIndex 增量更新** | claude-context-docs (P5) | `src/core/semantic_index.py` | ✅ |
| **DataHub Pub/Sub** | FinceptTerminal (P5) | `src/core/_datahub.py` | ✅ |
| **TopicPolicy 策略管理** | FinceptTerminal (P5) | `src/core/_datahub_types.py` | ✅ |
| **QueryInvalidator** | multica (P5) | `src/core/_query_invalidator.py` | ✅ |

详见 [docs/wiki_knowledge_integration_analysis.md](docs/wiki_knowledge_integration_analysis.md)

---

## Acknowledgments

Special thanks to the following projects for architectural inspiration:

- [GenericAgent](https://github.com/lsdefine/GenericAgent) - Agent Loop、行动验证原则
- [Hermes-Agent](https://github.com/ThakraX/Hermes-Agent) - Skills 系统、Context Fencing
- [MIA](https://github.com/agiresearch/MIA) - 记忆系统、TTRL 持续学习
- [Open-Agents](https://github.com/xlang-ai/OpenAgents) - Subagent 系统
- [Qwen-Code](https://github.com/QwenLM/Qwen-Code) - 工具系统、Hooks、三级权限
- [DeepSeek-TUI](https://github.com/Scerlee/TUI) - ToolCapability 能力声明
- [AI-Hedge-Fund](https://github.com/virattt/ai-hedge-fund) - AgentConfig 注册机制
- [Shannon-Architecture](https://github.com/shannon-architecture) - Agent 依赖图拓扑排序