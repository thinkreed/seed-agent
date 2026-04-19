# Module Overview

The `src/` directory contains the core engine of the Seed Agent system. This module provides a modular, asynchronous agent loop architecture supporting multi-provider LLM configuration, tool execution, streaming output, autonomous exploration, and scheduled task management.

The core engine consists of five main components that work together to create an autonomous, self-evolving agent capable of handling complex tasks with graceful degradation and minimal user intervention.

## Architecture Overview

```
src/
├── agent_loop.py    # Main agent loop with message handling and tool execution
├── autonomous.py    # Idle-time autonomous exploration
├── client.py        # LLM Gateway with multi-provider fallback
├── models.py        # Pydantic configuration validation
└── scheduler.py     # Task scheduling and management
```

---

# Key Components

## AgentLoop

The `AgentLoop` class is the central orchestrator of the agent system. It manages conversation flow, tool execution, history summarization, and maintains session state across interactions.

### Purpose

AgentLoop serves as the main execution engine that processes user input through an iterative loop, leveraging LLM responses and tool calls to complete complex tasks. It handles message construction, manages conversation history with automatic summarization, and coordinates tool execution.

### Key Methods

#### `__init__(gateway, model_id, system_prompt, max_iterations, summary_interval, session_id)`

Initializes the agent loop with the LLM gateway and configuration parameters.

```python
def __init__(
    self,
    gateway: LLMGateway,
    model_id: str = None,
    system_prompt: str = None,
    max_iterations: int = 30,
    summary_interval: int = 10,
    session_id: str = None
):
    self.gateway = gateway
    self.model_id = model_id or self._get_primary_model()
    self.max_iterations = max_iterations
    self.summary_interval = summary_interval
    self.history: List[Dict] = []
    self.tools = ToolRegistry()
    self.scheduler = TaskScheduler(self)
    # ... additional initialization
```

**Parameters:**
- `gateway`: LLMGateway instance for API calls
- `model_id`: Specific model to use (defaults to primary from config)
- `system_prompt`: System prompt for the agent
- `max_iterations`: Maximum tool call iterations per turn (default: 30)
- `summary_interval`: Number of conversation rounds before summarization (default: 10)
- `session_id`: Optional session identifier

#### `run(user_input: str) -> str`

Processes user input synchronously and returns the final response.

```python
async def run(self, user_input: str) -> str:
    """处理用户输入,返回最终响应"""
    self.history.append({"role": "user", "content": user_input})
    self._conversation_rounds += 1

    iteration = 0
    while iteration < self.max_iterations:
        iteration += 1
        # ... execution loop
        
        if message.get('tool_calls'):
            tool_results = await self._execute_tool_calls(message['tool_calls'])
            self.history.extend(tool_results)
        else:
            await self._maybe_summarize()
            return message.get('content', '')
    
    raise MaxIterationsExceeded(...)
```

#### `stream_run(user_input: str) -> AsyncGenerator[Dict, None]`

Processes user input with streaming output, yielding chunks in real-time.

```python
async def stream_run(self, user_input: str) -> AsyncGenerator[Dict, None]:
    """流式处理用户输入"""
    # Yields chunks: {"type": "chunk", "content": "..."}
    # Yields tool calls: {"type": "tool_call", "calls": [...]}
    # Yields final: {"type": "final", "content": "..."}
```

#### `_execute_tool_calls(tool_calls: List[Dict]) -> List[Dict]`

Executes tool calls in parallel and returns results.

```python
async def _execute_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
    """批量并行执行工具调用"""
    async def _run_single_call(tool_call: Dict) -> Dict:
        tool_id = tool_call['id']
        tool_name = tool_call['function']['name']
        raw_args = tool_call['function']['arguments']
        
        # Robust JSON parsing for edge cases
        try:
            if isinstance(raw_args, str):
                raw_args = raw_args.strip()
                tool_args = json.loads(raw_args) if raw_args else {}
            else:
                tool_args = raw_args if raw_args else {}
        except (json.JSONDecodeError, TypeError, ValueError):
            tool_args = {}
        
        result = await self.tools.execute(tool_name, **tool_args)
        return {"role": "tool", "tool_call_id": tool_id, "content": str(result)}
    
    return await asyncio.gather(*[_run_single_call(tc) for tc in tool_calls])
```

#### `_maybe_summarize()`

Automatically summarizes conversation history at configured intervals to manage context length.

```python
async def _maybe_summarize(self):
    """检查是否需要总结历史，并执行总结"""
    if self._conversation_rounds < self.summary_interval:
        return
    
    # Generate summary using LLM
    summary = await self._summarize_history()
    if not summary:
        return
    
    # Save history to L4 raw/sessions
    save_session_history(self.history, summary=summary, session_id=self.session_id)
    
    # Keep last 2 rounds + summary
    self.history = [
        {"role": "system", "content": f"[对话摘要]\n{summary}"}
    ] + preserved
    
    self._conversation_rounds = 0
```

#### `clear_history(save_current: bool = True)`

Clears conversation history with optional persistence to disk.

#### `interrupt(user_input: str)`

Interrupts current processing to prioritize new user input.

### Exceptions

- `MaxIterationsExceeded`: Raised when maximum iteration limit is reached
- `ProviderNotFoundError`: Raised when specified provider does not exist
- `ToolNotFoundError`: Raised when requested tool is not registered

---

## AutonomousExplorer

The `AutonomousExplorer` class provides idle-time autonomous task execution capabilities. When the user is inactive for a configured period, the agent automatically initiates exploration tasks based on defined SOPs (Standard Operating Procedures).

### Purpose

AutonomousExplorer enables the agent to be productive during idle periods by monitoring user activity and executing autonomous tasks when the system detects inactivity. It reads SOP documents from the project, checks for pending TODO items, and either executes existing tasks or enters planning mode to generate new TODO items.

### Key Features

- **Idle Monitoring**: Tracks user activity and triggers exploration after 30 minutes of inactivity
- **SOP Integration**: Loads and executes tasks based on configurable SOP documents
- **Planning Mode**: When no TODOs exist, generates new task items autonomously
- **Error Resilience**: Implements retry logic with exponential backoff and graceful degradation

### Key Methods

#### `__init__(agent_loop, on_explore_complete)`

Initializes the autonomous explorer with agent loop reference.

```python
class AutonomousExplorer:
    """自主探索执行器"""

    IDLE_TIMEOUT = 30 * 60  # 30 minutes in seconds

    def __init__(self, agent_loop, on_explore_complete: Callable = None):
        self.agent = agent_loop
        self.on_explore_complete = on_explore_complete
        self._last_activity: float = time.time()
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._sop_content: Optional[str] = None
        self._load_sop()
```

#### `start() / stop()`

Manages the lifecycle of the idle monitoring loop.

```python
async def start(self):
    """启动空闲监控"""
    if self._running:
        return
    
    self._running = True
    self._task = asyncio.create_task(self._idle_monitor_loop())
    logger.info("Autonomous explorer started")

async def stop(self):
    """停止空闲监控"""
    self._running = False
    if self._task:
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
```

#### `_idle_monitor_loop()`

Main monitoring loop that checks idle time every 30 seconds.

```python
async def _idle_monitor_loop(self):
    """空闲监控循环"""
    while self._running:
        idle_time = self.get_idle_time()

        if idle_time >= self.IDLE_TIMEOUT:
            logger.info(f"Idle for {idle_time/60:.1f} minutes, starting autonomous exploration")
            await self._execute_autonomous_task()
            self.record_activity()  # Reset timer after execution

        await asyncio.sleep(30)
```

#### `_execute_autonomous_task()`

Executes the autonomous exploration task with full tool iteration loop and retry logic.

```python
async def _execute_autonomous_task(self):
    """执行自主探索任务（带工具调用迭代循环 + 容错重试）"""
    max_iterations = 20
    max_consecutive_failures = 3
    
    # Build prompt with system prompt + skills + SOP
    prompt = self._build_autonomous_prompt(todo_content, has_todo)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "开始执行自主探索任务"}
    ]
    
    for iteration in range(max_iterations):
        response = await self._call_llm_with_retry(messages, max_retries=3)
        
        # Execute tool calls if present
        if tool_calls:
            for tc in tool_calls:
                tool_result = await self.agent.tools.execute(func_name, **func_args)
                messages.append({"role": "tool", "tool_call_id": tc_id, ...})
        else:
            # No more tool calls, task complete
            break
```

#### `_build_autonomous_prompt(todo_content, has_todo)`

Constructs the complete prompt including system prompt, skills, SOP, and task instructions.

```python
def _build_autonomous_prompt(self, todo_content: str, has_todo: bool) -> str:
    """构建自主探索 prompt（包含完整 system prompt + skills + SOP）"""
    base_system_prompt = self.agent.system_prompt or ""
    skills_prompt = self.agent.skill_loader.get_skills_prompt()
    sop_prompt = f"## 自主探索 SOP\n\n{self._sop_content}"
    task_prompt = self._build_task_instruction(todo_content, has_todo)
    
    return "\n\n".join([base_system_prompt, skills_prompt, sop_prompt, task_prompt])
```

#### `record_activity() / get_idle_time()`

Records user activity and calculates current idle duration.

```python
def record_activity(self):
    """记录用户活动时间"""
    self._last_activity = time.time()

def get_idle_time(self) -> float:
    """获取当前空闲时间（秒）"""
    return time.time() - self._last_activity
```

---

## LLMGateway

The `LLMGateway` class provides a unified interface for interacting with multiple LLM providers. It implements a fallback chain mechanism that automatically switches to backup providers when the primary provider fails, ensuring high availability.

### Purpose

LLMGateway abstracts away the complexities of multi-provider LLM access, providing a single interface for chat completions with automatic failover. It supports both streaming and non-streaming modes, handles API key resolution from environment variables, and implements retry logic with exponential backoff.

### Key Classes

#### FallbackChain

Manages provider failover with health status tracking.

```python
class FallbackChain:
    """跨 Provider 降级链：primary 失败时自动切换到 fallback"""

    def __init__(self, providers: List[str], clients: Dict[str, AsyncOpenAI]):
        self._providers = providers  # Priority list
        self._clients = clients
        self._active_provider: Optional[str] = None
        self._status: str = "healthy"  # healthy, degraded, unavailable

    def get_active_client(self) -> tuple[str, AsyncOpenAI]:
        """获取当前活跃的 provider 和 client"""
        if self._active_provider and self._active_provider in self._clients:
            return self._active_provider, self._clients[self._active_provider]
        
        for provider in self._providers:
            if provider in self._clients:
                self._active_provider = provider
                return provider, self._clients[provider]
        
        raise ValueError("No available provider")

    def mark_degraded(self, failed_provider: str):
        """标记 provider 失败，切换到下一个"""
        failed_idx = self._providers.index(failed_provider) if failed_provider in self._providers else -1
        for i, provider in enumerate(self._providers):
            if i > failed_idx and provider in self._clients:
                self._active_provider = provider
                self._status = "degraded"
                return
        
        self._status = "unavailable"
```

### LLMGateway Methods

#### `__init__(config_path: str)`

Initializes the gateway with configuration file.

```python
def __init__(self, config_path: str):
    self.config: FullConfig = load_config(config_path)
    self.clients: Dict[str, AsyncOpenAI] = {}
    self._fallback_chain: Optional[FallbackChain] = None
    self._init_clients()
    self._init_fallback_chain()
```

#### `chat_completion(model_id, messages, **kwargs) -> Dict`

Non-streaming chat completion with automatic fallback.

```python
async def chat_completion(
    self,
    model_id: str,
    messages: List[Dict],
    **kwargs
) -> Dict:
    """非流式聊天补全（使用降级机制）"""
    return await self.chat_completion_with_fallback(model_id, messages, **kwargs)

async def chat_completion_with_fallback(
    self,
    model_id: str,
    messages: List[Dict],
    **kwargs
) -> Dict:
    """带跨 Provider 降级的非流式聊天补全"""
    provider_id = model_id.split('/')[0]
    
    # Try current provider with retry
    for attempt in range(3):
        try:
            result = await self._chat_completion_single(model_id, messages, **kwargs)
            if self._fallback_chain:
                self._fallback_chain.mark_healthy(provider_id)
            return result
        except (APIConnectionError, RateLimitError, APIStatusError) as e:
            if attempt < 2:
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
    
    # Trigger fallback
    if self._fallback_chain:
        self._fallback_chain.mark_degraded(provider_id)
        
        for fallback_provider in self._fallback_chain._providers:
            if fallback_provider == provider_id:
                continue
            
            fallback_model_id = self._get_fallback_model_id(model_id, fallback_provider)
            try:
                result = await self._chat_completion_single(fallback_model_id, messages, **kwargs)
                self._fallback_chain.mark_healthy(fallback_provider)
                return result
            except Exception as fallback_e:
                self._fallback_chain.mark_degraded(fallback_provider)
    
    raise APIConnectionError("All providers failed")
```

#### `stream_chat_completion(model_id, messages, **kwargs) -> AsyncGenerator[Dict, None]`

Streaming chat completion with automatic fallback.

```python
async def stream_chat_completion(
    self,
    model_id: str,
    messages: List[Dict],
    **kwargs
) -> AsyncGenerator[Dict, None]:
    """流式聊天补全（使用降级机制）"""
    async for chunk in self.stream_chat_completion_with_fallback(model_id, messages, **kwargs):
        yield chunk
```

#### `_resolve_api_key(api_key: str) -> str`

Resolves API keys with environment variable support.

```python
def _resolve_api_key(self, api_key: str) -> str:
    """解析 API Key,支持环境变量引用"""
    if api_key.startswith("${") and api_key.endswith("}"):
        env_var = api_key[2:-1]
        return os.environ.get(env_var, "").strip()
    return api_key.strip()
```

---

## models

The `models` module provides Pydantic-based configuration validation for the agent system. It defines data structures for provider configuration, model settings, and agent defaults with automatic migration support for legacy config formats.

### Purpose

The models module ensures type-safe configuration loading with validation, providing clear error messages for misconfigured settings. It supports both new and legacy configuration formats through automatic migration logic.

### Data Models

#### `ModelConfig`

Individual model configuration.

```python
class ModelConfig(BaseModel):
    model_config = ConfigDict(extra='ignore')
    id: str
    name: str
    contextWindow: int = 100000
    maxTokens: int = 4096
    compat: Optional[Dict] = None
```

#### `ProviderConfig`

Provider-level configuration including base URL, API key, and model list.

```python
class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra='ignore')
    baseUrl: str
    apiKey: str
    api: str = "openai-completions"
    models: List[ModelConfig]

    @field_validator('apiKey', 'baseUrl')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip() if v else v
```

#### `AgentModelConfig` and `AgentConfig`

Agent-level default configuration.

```python
class AgentModelConfig(BaseModel):
    model_config = ConfigDict(extra='ignore')
    primary: str

class AgentConfig(BaseModel):
    model_config = ConfigDict(extra='ignore')
    defaults: AgentModelConfig
```

#### `FullConfig`

Top-level configuration aggregating all providers and agents.

```python
class FullConfig(BaseModel):
    model_config = ConfigDict(extra='ignore')
    models: Dict[str, ProviderConfig]
    agents: Dict[str, AgentConfig]
```

### Functions

#### `load_config(config_path: str = None) -> FullConfig`

Loads and validates configuration with automatic migration support.

```python
def load_config(config_path: str = None) -> FullConfig:
    """加载并解析配置文件，支持旧版 JSON 结构自动迁移"""
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH  # ~/.seed/config.json
    
    with open(config_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Migration logic for legacy formats
    # 1. models.providers -> models
    # 2. agents.defaults.model -> agents.defaults.defaults
    
    return FullConfig(**data)
```

---

## scheduler

The `scheduler` module provides task scheduling capabilities for the agent. It enables the creation, management, and periodic execution of tasks, with built-in support for common tasks like autonomous exploration and memory consolidation.

### Purpose

The scheduler allows the agent to create and manage time-based tasks that run automatically at configured intervals. It supports CRUD operations for tasks, persists tasks to disk, and logs execution results.

### Key Classes

#### `ScheduledTask`

Represents a single scheduled task with execution logic.

```python
class ScheduledTask:
    """定时任务定义"""

    def __init__(
        self,
        task_id: str,
        task_type: str,
        interval_seconds: int,
        prompt: str,
        last_run: float = 0,
        enabled: bool = True
    ):
        self.task_id = task_id
        self.task_type = task_type
        self.interval_seconds = interval_seconds
        self.prompt = prompt
        self.last_run = last_run
        self.enabled = enabled

    def should_run(self) -> bool:
        """检查是否应该执行"""
        if not self.enabled:
            return False
        return time.time() - self.last_run >= self.interval_seconds
```

#### `TaskScheduler`

Main scheduler class that manages task lifecycle and execution.

```python
class TaskScheduler:
    """定时任务调度器"""

    # Built-in task types with default intervals
    BUILTIN_TASKS = {
        "autodream": 12 * 60 * 60,      # Every 12 hours
        "autonomous_explore": 30 * 60,  # Every 15 minutes
        "health_check": 60 * 60,        # Every hour
    }

    def __init__(self, agent_loop=None):
        self.agent = agent_loop
        self._tasks: Dict[str, ScheduledTask] = {}
        self._running: bool = False
        self._check_interval: int = 60
        self._task: Optional[asyncio.Task] = None
        self._load_tasks()
        self._init_builtin_tasks()
```

### TaskScheduler Methods

#### `start() / stop()`

Manages scheduler lifecycle.

```python
async def start(self):
    """启动调度器"""
    if self._running:
        return
    
    self._running = True
    self._task = asyncio.create_task(self._schedule_loop())
    logger.info("Task scheduler started")

async def stop(self):
    """停止调度器"""
    self._running = False
    self._save_tasks()
    
    if self._task:
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
```

#### `add_task(task_id, task_type, interval_seconds, prompt) -> str`

Creates a new scheduled task.

```python
def add_task(
    self,
    task_id: str,
    task_type: str,
    interval_seconds: int,
    prompt: str
) -> str:
    """添加自定义定时任务"""
    if task_id in self._tasks:
        return f"Task {task_id} already exists"

    self._tasks[task_id] = ScheduledTask(
        task_id=task_id,
        task_type=task_type,
        interval_seconds=interval_seconds,
        prompt=prompt,
        enabled=True
    )

    self._save_tasks()
    return f"Task {task_id} added successfully, will run every {interval_seconds} seconds"
```

#### `remove_task(task_id: str) -> str`

Removes a scheduled task (builtin tasks cannot be removed).

#### `disable_task(task_id: str) / enable_task(task_id: str)`

Toggle task enabled state.

#### `list_tasks() -> str`

Returns formatted list of all scheduled tasks.

#### `get_task_status(task_id: str) -> Dict`

Returns detailed status for a specific task.

### Tool Functions

The scheduler module also exposes tool functions for agent use:

```python
def create_scheduled_task(task_id: str, interval_minutes: int, prompt: str) -> str:
    """Create a scheduled task that runs periodically."""

def remove_scheduled_task(task_id: str) -> str:
    """Remove a scheduled task."""

def list_scheduled_tasks() -> str:
    """List all scheduled tasks."""

def get_task_info(task_id: str) -> str:
    """Get detailed info about a scheduled task."""
```

---

# Usage Guidelines

## Initialization

Create an agent instance with the LLM gateway:

```python
from client import LLMGateway
from agent_loop import AgentLoop
from autonomous import create_autonomous_explorer

# Initialize gateway
gateway = LLMGateway("config/config.json")

# Create agent loop
agent = AgentLoop(
    gateway=gateway,
    system_prompt="You are a helpful assistant.",
    max_iterations=30,
    summary_interval=10
)

# Start autonomous explorer (optional)
explorer = await create_autonomous_explorer(agent)
```

## Running the Agent

### Synchronous Mode

```python
response = await agent.run("Your message here")
print(response)
```

### Streaming Mode

```python
async for chunk in agent.stream_run("Your message here"):
    if chunk["type"] == "chunk":
        print(chunk["content"], end="")
    elif chunk["type"] == "tool_call":
        print(f"\n[Tool calls: {chunk['calls']}]")
    elif chunk["type"] == "final":
        print(f"\n[Final response: {chunk['content']}]")
```

## Task Scheduling

```python
# Create a task that runs every hour
agent.scheduler.add_task(
    task_id="hourly_report",
    task_type="custom",
    interval_seconds=3600,
    prompt="Generate a status report"
)

# List all tasks
print(agent.scheduler.list_tasks())

# Get task status
status = agent.scheduler.get_task_status("hourly_report")
```

## Configuration

Edit `config/config.json` to configure providers and models:

```json
{
  "models": {
    "provider_name": {
      "baseUrl": "https://api.example.com/v1",
      "apiKey": "${ENV_VAR_NAME}",
      "api": "openai-completions",
      "models": [
        {
          "id": "model-name",
          "name": "Model Name",
          "contextWindow": 100000,
          "maxTokens": 4096
        }
      ]
    }
  },
  "agents": {
    "defaults": {
      "defaults": {
        "primary": "provider_name/model-name"
      }
    }
  }
}
```

---

# Dependencies

The core engine requires the following packages:

## Runtime Dependencies

- **pydantic**: Configuration validation and data modeling
- **openai**: OpenAI API client (async version)
- **tenacity**: Retry logic with exponential backoff

## Internal Dependencies

The engine interacts with the following internal modules:

- `tools/`: Tool registry and execution system
- `tools/builtin_tools.py`: Built-in tool implementations
- `tools/memory_tools.py`: Session history persistence
- `tools/skill_loader.py`: Dynamic skill loading

## Configuration

- **config/config.json**: Provider and model configuration file

## Storage

The scheduler stores data in `~/.seed/`:
- `~/.seed/config.json`: Configuration file
- `~/.seed/tasks/`: Task storage directory
- `~/.seed/tasks/scheduled_tasks.json`: Scheduled task definitions
- `~/.seed/tasks/execution_log.jsonl`: Task execution logs

---

# Integration Notes

## Tool Registry Integration

AgentLoop automatically registers built-in tools, memory tools, skill tools, and scheduler tools during initialization. The tool registry is accessible via `agent.tools` and provides methods for tool execution and schema generation.

## Session Management

Each agent maintains its own session with automatic history management. The agent tracks conversation rounds and triggers summarization at configured intervals to manage context length.

## Fallback Behavior

When using multi-provider configurations, the gateway automatically attempts fallback providers in priority order when failures occur. The status is tracked as `healthy`, `degraded`, or `unavailable`.

## Error Handling

The agent loop raises `MaxIterationsExceeded` when the tool execution limit is reached. Tool execution errors are caught and returned as error messages in the tool result, allowing the agent to recover gracefully.
