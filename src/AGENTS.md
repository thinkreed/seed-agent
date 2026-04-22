# Module Overview

The `src/` directory contains the core engine of the Seed Agent system. This module provides a modular, asynchronous agent loop architecture supporting multi-provider LLM configuration, tool execution, streaming output, autonomous exploration, and scheduled task management.

The core engine consists of five main components that work together to create an autonomous, self-evolving agent capable of handling complex tasks with graceful degradation and minimal user intervention.

## Architecture Overview

```
src/
├── agent_loop.py         # Main agent loop with message handling and tool execution
├── autonomous.py         # Idle-time autonomous exploration (Ralph Loop enhanced)
├── client.py             # LLM Gateway with multi-provider fallback
├── models.py             # Pydantic configuration validation
├── ralph_loop.py         # Long-cycle deterministic task executor
├── rate_limiter.py       # Token Bucket + Rolling Window dual rate limiting
├── rate_limit_db.py      # SQLite persistence for rate limit state
├── request_queue.py      # TurnTicket request queue with priority and backpressure
├── scheduler.py          # Task scheduling and management
├── subagent_manager.py   # Subagent orchestration and lifecycle management
└── subagent.py           # Independent context subagent execution
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

## RalphLoop

The `RalphLoop` class provides a long-cycle deterministic task execution framework with external verification-driven completion. It is designed for complex, multi-step operations that require objective completion criteria rather than self-judgment.

### Purpose

RalphLoop addresses the challenge of long-running tasks where traditional agent loops suffer from context drift and unreliable completion detection. It uses external verification (tests passing, marker files, git clean) to determine task completion, ensuring deterministic and verifiable outcomes.

### Core Mechanisms

1. **External Verification**: Completion is driven by objective criteria, not model self-judgment
2. **Fresh Context**: Periodic context reset prevents drift in long-running iterations
3. **State Persistence**: Task state saved to filesystem for crash recovery
4. **Safety Limits**: Max iterations (1000) and duration (8 hours) protection

### Completion Types

| Type | Description | Use Case |
|------|-------------|----------|
| `TEST_PASS` | Test suite passes at specified rate | Code refactoring, bug fixes |
| `FILE_EXISTS` | Target files created | File generation tasks |
| `MARKER_FILE` | Completion marker written | Multi-step workflows |
| `GIT_CLEAN` | Working directory clean | Full project changes |
| `CUSTOM_CHECK` | Custom validation function | Domain-specific validation |

### Key Methods

#### `__init__(agent_loop, completion_type, completion_criteria, task_prompt_path, ...)`

Initializes Ralph Loop with configuration.

```python
class RalphLoop:
    """Ralph Loop 执行器"""

    MAX_ITERATIONS = 1000
    MAX_DURATION = 8 * 60 * 60  # 8 hours
    ITERATION_INTERVAL = 5  # Context reset every 5 iterations

    def __init__(
        self,
        agent_loop,
        completion_type: CompletionType,
        completion_criteria: dict,
        task_prompt_path: Path,
        on_iteration_complete: Callable = None,
        max_iterations: int = None,
        max_duration: int = None,
        context_reset_interval: int = None
    ):
        self.agent = agent_loop
        self.completion_type = completion_type
        self.completion_criteria = completion_criteria
        self.task_prompt_path = task_prompt_path
        # ... initialization
```

#### `run() -> str`

Executes the Ralph Loop with verification.

```python
async def run(self) -> str:
    """执行 Ralph Loop"""
    while self._is_running:
        self._iteration_count += 1
        
        # 1. Safety check
        if self._check_safety_limits():
            break
        
        # 2. Context reset
        self._reset_context()
        
        # 3. Load task prompt
        prompt = self._load_task_prompt()
        
        # 4. Execute agent loop
        response = await self.agent.run(prompt)
        
        # 5. Persist state
        self._persist_state(response)
        
        # 6. External completion verification
        if self._check_completion():
            self._cleanup()
            return "DONE"
        
        await asyncio.sleep(1)
```

#### `_check_completion() -> bool`

External completion verification (core mechanism).

```python
def _check_completion(self) -> bool:
    """外部完成验证"""
    validators = {
        CompletionType.TEST_PASS: self._check_test_pass,
        CompletionType.FILE_EXISTS: self._check_file_exists,
        CompletionType.MARKER_FILE: self._check_marker_file,
        CompletionType.GIT_CLEAN: self._check_git_clean,
        CompletionType.CUSTOM_CHECK: self._check_custom,
    }
    
    validator = validators.get(self.completion_type)
    return validator() if validator else False
```

#### `_reset_context()`

Periodic context reset to prevent drift.

```python
def _reset_context(self):
    """重置上下文（新鲜上下文）"""
    if self._iteration_count % self.context_reset_interval != 0:
        return
    
    # Extract critical context
    preserved = self._extract_critical_context()
    
    # Clear history
    self.agent.history.clear()
    
    # Re-inject preserved info
    if preserved:
        self.agent.history.append({
            "role": "system",
            "content": f"[迭代 {self._iteration_count} 状态摘要]\n{preserved}"
        })
```

### Factory Methods

```python
# Test-driven execution
ralph = RalphLoop.create_test_driven(
    agent_loop=agent,
    task_prompt_path=Path(".seed/tasks/refactor.md"),
    test_command="pytest tests/ -v",
    pass_rate=100
)

# Marker-driven execution
ralph = RalphLoop.create_marker_driven(
    agent_loop=agent,
    task_prompt_path=Path(".seed/tasks/task.md"),
    marker_path=Path(".seed/done")
)
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

#### `chat_completion(model_id, messages, priority, **kwargs) -> Dict`

Non-streaming chat completion with TurnTicket mode (three-phase waiting).

```python
async def chat_completion(
    self,
    model_id: str,
    messages: List[Dict],
    priority: RequestPriority = RequestPriority.NORMAL,
    **kwargs
) -> Dict:
    """非流式聊天补全（TurnTicket 模式）

    三阶段等待：
    1. 排队入场 (request_turn + wait_for_turn)
    2. 抢执行位置 (semaphore)
    3. 限流检查 (rate_limiter)
    4. 执行 (execute with fallback)
    """
    # 获取动态超时
    turn_timeout = self.get_dynamic_timeout(priority)

    # 阶段1：排队入场
    ticket = await self.request_turn(priority)
    await ticket.wait_for_turn(timeout=turn_timeout)

    # 阶段2-4：执行（带 semaphore 和限流）
    async with self._request_semaphore:
        if self._rate_limiter:
            max_wait = 0.0 if priority == RequestPriority.CRITICAL else 60.0
            await self._rate_limiter.wait_and_acquire(max_wait=max_wait)

        result = await self._chat_completion_with_fallback_internal(model_id, messages, **kwargs)

    return result
```

#### `stream_chat_completion(model_id, messages, priority, **kwargs) -> AsyncGenerator[Dict, None]`

Streaming chat completion with TurnTicket mode.

```python
async def stream_chat_completion(
    self,
    model_id: str,
    messages: List[Dict],
    priority: RequestPriority = RequestPriority.NORMAL,
    **kwargs
) -> AsyncGenerator[Dict, None]:
    """流式聊天补全（TurnTicket 模式）

    返回 generator，由调用者迭代
    """
    # 阶段1：排队入场
    ticket = await self.request_turn(priority)
    await ticket.wait_for_turn(timeout=self.get_dynamic_timeout(priority))

    # 阶段2-4：返回 generator（调度器不介入）
    async def actual_stream():
        async with self._request_semaphore:
            if self._rate_limiter:
                max_wait = 0.0 if priority == RequestPriority.CRITICAL else 60.0
                await self._rate_limiter.wait_and_acquire(max_wait=max_wait)

            async for chunk in self._stream_chat_completion_with_fallback_internal(model_id, messages, **kwargs):
                yield chunk

    return actual_stream()
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

## RateLimiter

The `rate_limiter` module provides dual rate limiting mechanisms combining Token Bucket and Rolling Window algorithms. It ensures smooth handling of burst requests while maintaining strict control over total request volume within configurable time windows.

### Purpose

RateLimiter protects the LLM Gateway from exceeding API rate limits by implementing a two-tier throttling system:
- **Token Bucket**: Smooths burst requests by replenishing tokens at a fixed rate
- **Rolling Window**: Enforces hard limits on total requests within a sliding time window

This combination handles both short-term burst control and long-term quota management (e.g., 6000 requests per 5 hours).

### Key Classes

#### TokenBucket

A classic rate limiting algorithm that controls request flow by replenishing tokens at a fixed rate.

```python
class TokenBucket:
    """Token Bucket 限流器

    核心算法:
    - tokens 以固定速率补充
    - 每次请求消耗 1 token
    - tokens 不能超过 capacity
    - tokens 不足时需要等待

    线程安全：使用 asyncio.Lock 保证并发安全
    """

    def __init__(self, rate: float, capacity: float, initial_tokens: Optional[float] = None):
        """
        Args:
            rate: 每秒补充的 token 数
            capacity: 最大 token 容量
            initial_tokens: 初始 token 数，默认满载
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = initial_tokens if initial_tokens is not None else capacity
        self.last_refill = time.time()
        self._lock = asyncio.Lock()
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `rate` | `float` | Token replenishment rate (tokens/sec) |
| `capacity` | `float` | Maximum token bucket capacity |
| `initial_tokens` | `Optional[float]` | Initial tokens, defaults to capacity |

#### RollingWindowTracker

A sliding window tracker that maintains precise control over request counts within a configurable duration.

```python
class RollingWindowTracker:
    """滚动窗口追踪器

    核心机制:
    - 记录每个请求的时间戳
    - 滚动计算窗口内已用请求数
    - 窗口为滑动窗口（非固定窗口）

    适用场景：
    - 百炼 5 小时 6000 次限流
    - 其他长窗口限流场景
    """

    def __init__(self, window_limit: int, window_duration: float):
        """
        Args:
            window_limit: 窗口内最大请求数
            window_duration: 窗口时长（秒）
        """
        self.window_limit = window_limit
        self.window_duration = window_duration
        self.requests: List[float] = []
        self.total_requests_lifetime = 0
        self._lock = asyncio.Lock()
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `window_limit` | `int` | Maximum requests within the window |
| `window_duration` | `float` | Window duration in seconds |

#### RateLimiter

Combines Token Bucket and Rolling Window for dual-layer rate limiting.

```python
class RateLimiter:
    """组合限流器

    组合 Token Bucket + Rolling Window 的双重限流机制:
    - Token Bucket: 平滑突发请求
    - Rolling Window: 控制长周期窗口内的总请求数
    """

    def __init__(
        self,
        rate: float,
        capacity: float,
        window_limit: int,
        window_duration: float,
    ):
        """
        Args:
            rate: Token 补充速率（requests/sec）
            capacity: Token 桶容量
            window_limit: 滚动窗口请求上限
            window_duration: 滚动窗口时长（秒）
        """
        self.token_bucket = TokenBucket(rate, capacity)
        self.window_tracker = RollingWindowTracker(window_limit, window_duration)
```

### Key Methods

#### `acquire() -> Tuple[bool, float]`

Attempts to acquire a request permit without waiting.

```python
async def acquire(self) -> Tuple[bool, float]:
    """尝试获取请求许可

    Returns:
        (allowed, wait_time): 是否允许, 需等待时间
    """
    # 先检查滚动窗口（硬限制）
    window_allowed, window_wait = await self.window_tracker.check_available()
    if not window_allowed:
        return False, window_wait

    # 再检查 Token Bucket（软限制，平滑突发）
    bucket_allowed, bucket_wait = await self.token_bucket.acquire()
    if not bucket_allowed:
        return False, bucket_wait

    return True, 0.0
```

#### `wait_and_acquire(max_wait: float) -> bool`

Waits up to `max_wait` seconds to acquire a permit.

```python
async def wait_and_acquire(self, max_wait: float = 60.0) -> bool:
    """等待并获取请求许可

    Args:
        max_wait: 最大等待时间（秒）

    Returns:
        是否成功获取
    """
    start = time.time()
    while True:
        allowed, wait_time = await self.acquire()
        if allowed:
            await self.window_tracker.record_request()
            return True

        elapsed = time.time() - start
        if elapsed + wait_time > max_wait:
            return False

        await asyncio.sleep(wait_time)
```

#### `get_status() -> RateLimitStatus`

Returns a snapshot of current rate limiting state.

```python
def get_status(self) -> RateLimitStatus:
    """获取限流状态快照"""
    return RateLimitStatus(
        tokens_available=bucket_state.tokens,
        token_bucket_capacity=self.token_bucket.capacity,
        refill_rate=self.token_bucket.rate,
        window_requests_used=len(active_requests),
        window_requests_remaining=self.window_tracker.get_remaining(),
        window_requests_limit=self.window_tracker.window_limit,
        window_reset_time=self.window_tracker.get_reset_time(),
        window_usage_ratio=self.window_tracker.get_usage_ratio(),
        total_requests_lifetime=window_state.total_requests_lifetime,
    )
```

### State Persistence

RateLimiter supports state persistence via `get_state()` and `restore_state()` methods for crash recovery.

### Usage Example

```python
from rate_limiter import RateLimiter

# Create rate limiter: 2 req/sec burst, 6000 req/5hr window
limiter = RateLimiter(
    rate=2.0,
    capacity=10.0,
    window_limit=6000,
    window_duration=18000  # 5 hours
)

# Acquire with max wait
if await limiter.wait_and_acquire(max_wait=30.0):
    # Make API request
    response = await gateway.chat_completion(...)
else:
    # Handle timeout
    logger.warning("Rate limit wait timeout")
```

### Reference

For detailed design documentation, see [docs/rate_limiting_system_design.md](../docs/rate_limiting_system_design.md).

---

## RateLimitSQLite

The `rate_limit_db` module provides SQLite-based persistence for rate limiting state, enabling cross-process state sharing and crash recovery.

### Purpose

RateLimitSQLite ensures rate limiting state survives process restarts and can be shared across multiple agent instances. It uses WAL mode for high-concurrency access and implements automatic cleanup of expired data.

### Key Features

- **Cross-Process Sharing**: Multiple processes can share rate limit state
- **WAL Mode**: Write-Ahead Logging for high concurrent access
- **Auto Cleanup**: Automatic removal of expired request records
- **Crash Recovery**: State persistence survives process termination

### Key Class

#### RateLimitSQLite

```python
class RateLimitSQLite:
    """SQLite 持久化存储

    特性:
    - 跨进程共享状态
    - WAL 模式高并发
    - 自动清理过期数据
    - 崩溃恢复支持
    """

    DB_PATH = Path.home() / ".seed" / "rate_limit.db"

    def __init__(self, db_path: Optional[Path] = None):
        """
        Args:
            db_path: 数据库路径，默认 ~/.seed/rate_limit.db
        """
        self._db_path = db_path or self.DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._lock = asyncio.Lock()
        self._init_db()
```

### Database Schema

#### `rate_limit_state` Table

Single-row table storing current rate limit state:

| Column | Type | Description |
|--------|------|-------------|
| `id` | `INTEGER` | Primary key (fixed to 1) |
| `window_requests` | `TEXT` | JSON array of request timestamps |
| `tokens_available` | `REAL` | Current token bucket tokens |
| `last_refill_time` | `REAL` | Last token refill timestamp |
| `total_requests` | `INTEGER` | Lifetime request count |
| `updated_at` | `REAL` | Last update timestamp |

#### `request_history` Table

Audit trail for request execution:

| Column | Type | Description |
|--------|------|-------------|
| `id` | `INTEGER` | Auto-increment primary key |
| `request_id` | `TEXT` | Unique request identifier |
| `timestamp` | `REAL` | Request timestamp |
| `priority` | `TEXT` | Request priority level |
| `duration` | `REAL` | Request duration (optional) |
| `success` | `INTEGER` | Success flag (0/1) |
| `error_message` | `TEXT` | Error message (optional) |

### Key Methods

#### `load_state() -> RateLimitState`

Loads current rate limit state with automatic expired request cleanup.

```python
async def load_state(self) -> RateLimitState:
    """加载当前状态"""
    async with self._lock:
        conn = self._get_conn()
        cursor = conn.execute("""
            SELECT window_requests, tokens_available, last_refill_time,
                   total_requests, updated_at
            FROM rate_limit_state WHERE id = 1
        """)
        row = cursor.fetchone()

        if row:
            window_requests = json.loads(row[0])
            # 清理过期请求（超过 5 小时）
            now = time.time()
            window_requests = [
                t for t in window_requests
                if now - t < 18000  # 5 hours
            ]
            return RateLimitState(...)
```

#### `save_state(state: RateLimitState) -> None`

Persists rate limit state to database.

```python
async def save_state(self, state: RateLimitState) -> None:
    """保存状态"""
    async with self._lock:
        conn = self._get_conn()
        conn.execute("""
            UPDATE rate_limit_state SET
                window_requests = ?,
                tokens_available = ?,
                last_refill_time = ?,
                total_requests = ?,
                updated_at = ?
            WHERE id = 1
        """, (...))
        conn.commit()
```

#### `save_bucket_state(bucket_state: TokenBucketState) / save_window_state(window_state: RollingWindowState)`

Saves individual component states for partial updates.

#### `record_request(request_id, priority, duration, success, error_message)`

Records request execution for audit trail.

#### `cleanup_old_history(max_age: float) -> int`

Removes history records older than `max_age` seconds.

```python
async def cleanup_old_history(self, max_age: float = 86400.0) -> int:
    """清理过期历史记录

    Args:
        max_age: 最大保留时间（秒），默认 24 小时

    Returns:
        清理的记录数
    """
```

#### `get_stats() -> dict`

Returns aggregate statistics including success rate, average duration, and recent errors.

### Usage Example

```python
from rate_limit_db import RateLimitSQLite
from rate_limiter import RateLimiter, TokenBucketState, RollingWindowState

# Initialize database
db = RateLimitSQLite()

# Load persisted state on startup
state = await db.load_state()

# Create rate limiter with persisted state
limiter = RateLimiter(rate=2.0, capacity=10.0, window_limit=6000, window_duration=18000)
if state.tokens_available:
    limiter.restore_state(
        bucket_state=TokenBucketState(state.tokens_available, state.last_refill_time),
        window_state=RollingWindowState(state.requests_in_window, state.total_requests_lifetime)
    )

# Save state periodically
bucket_state, window_state = limiter.get_state()
await db.save_bucket_state(bucket_state)
await db.save_window_state(window_state)
```

---

## RequestQueue

The `request_queue` module implements a priority-based request queue with TurnTicket mode, providing fair scheduling, backpressure control, and intelligent auto-adjustment.

### Purpose

RequestQueue orchestrates concurrent LLM requests through a fair scheduling system:
- **TurnTicket Mode**: Queue manages "turn allocation" without intervening in execution
- **Priority Levels**: CRITICAL, HIGH, NORMAL, LOW for differentiated service
- **Backpressure**: Rejects requests when queues approach capacity
- **Auto-Adjustment**: Dynamically adjusts dispatch rates based on wait times

### Key Classes

#### RequestPriority

Priority levels for request differentiation.

```python
class RequestPriority(IntEnum):
    """请求优先级"""
    CRITICAL = 0    # 用户直接交互，最高优先级，独立队列
    HIGH = 1        # RalphLoop 迭代，优先处理
    NORMAL = 2      # Subagent 任务，标准处理
    LOW = 3         # Scheduler 后台，队列处理
```

| Priority | Value | Use Case |
|----------|-------|----------|
| `CRITICAL` | 0 | User direct interaction, independent queue |
| `HIGH` | 1 | RalphLoop iterations, priority processing |
| `NORMAL` | 2 | Subagent tasks, standard processing |
| `LOW` | 3 | Scheduler background tasks |

#### TurnTicket

A "turn signal" representing permission to execute.

```python
@dataclass
class TurnTicket:
    """轮次票 - 代表"轮到你执行了"的信号

    核心理念：队列只管"轮次分配"，不介入执行细节
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    priority: RequestPriority = RequestPriority.NORMAL
    created_at: float = field(default_factory=time.time)

    _turn_event: asyncio.Event = field(default_factory=asyncio.Event)
    _turn_time: Optional[float] = None
    _cancelled: bool = False
    _cancel_reason: Optional[str] = None
```

### Key Methods

#### `wait_for_turn(timeout: float) -> None`

Waits for turn signal with timeout.

```python
async def wait_for_turn(self, timeout: float) -> None:
    """等待轮次到达

    Args:
        timeout: 最大等待时间（秒）

    Raises:
        TurnWaitTimeout: 等待超时
        asyncio.CancelledError: 被取消
    """
    try:
        await asyncio.wait_for(self._turn_event.wait(), timeout)
    except asyncio.TimeoutError:
        raise TurnWaitTimeout(self.id, timeout, {})

    if self._cancelled:
        raise asyncio.CancelledError(self._cancel_reason)
```

#### `signal_turn()`

Dispatcher signals that turn has arrived.

```python
def signal_turn(self) -> None:
    """调度器通知：轮次到了"""
    self._turn_time = time.time()
    self._turn_event.set()
```

#### `cancel(reason: str)`

Cancels the ticket, waking waiting threads with CancelledError.

#### QueueConfig

Configurable queue parameters with auto-adjustment support.

```python
@dataclass
class QueueConfig:
    """队列配置（可动态调整）"""

    # CRITICAL 队列配置
    critical_max_size: int = 10
    critical_backpressure_threshold: float = 0.9
    critical_dispatch_rate: float = 10.0
    critical_target_wait_time: float = 5.0

    # 普通队列配置（HIGH/NORMAL/LOW 共享）
    normal_max_size: int = 50
    normal_backpressure_threshold: float = 0.8
    normal_dispatch_rate: float = 0.33
    normal_target_wait_time: float = 30.0

    # 自动调整
    auto_adjust_enabled: bool = True
    adjust_interval: float = 60.0
```

#### RequestQueue

Main queue orchestrator with priority dispatch.

```python
class RequestQueue:
    """请求队列系统 - TurnTicket 模式

    特性:
    - CRITICAL 独立队列，最高优先级
    - 多优先级队列（HIGH/NORMAL/LOW 共享）
    - TurnTicket 模式：只管轮次分配，不介入执行
    - 反压机制（队列满时拒绝新请求）
    - 智能配置调整
    """

    def __init__(self, config: QueueConfig = None):
        self.config = config or QueueConfig()
        self._critical_queue: Deque[TurnTicket] = deque()
        self._normal_queues: Dict[RequestPriority, Deque[TurnTicket]] = {
            RequestPriority.HIGH: deque(),
            RequestPriority.NORMAL: deque(),
            RequestPriority.LOW: deque(),
        }
        self._active_tickets: Dict[str, TurnTicket] = {}
```

### Key Methods

#### `request_turn(priority) -> TurnTicket`

Core entry point for requesting execution turn.

```python
async def request_turn(
    self,
    priority: RequestPriority = RequestPriority.NORMAL
) -> TurnTicket:
    """申请轮次（核心入口）

    Args:
        priority: 请求优先级

    Returns:
        TurnTicket: 轮次票

    Raises:
        QueueFullError: 队列已满
    """
    ticket = TurnTicket(priority=priority)

    async with self._lock:
        # Check backpressure threshold
        if fill_ratio >= threshold:
            self._stats.record_rejected(priority)
            raise QueueFullError(fill_ratio, threshold, queue_type)

        # Enqueue ticket
        ...

    self._new_request_event.set()
    return ticket
```

#### `start_dispatcher() / stop_dispatcher()`

Lifecycle management for the async dispatcher loop.

#### `get_stats() -> Dict[str, Any]`

Returns comprehensive queue statistics including lengths, fill ratios, wait times, and reject rates.

### Backpressure Mechanism

When queue fill ratio exceeds the configured threshold:
- `QueueFullError` is raised immediately
- Client can choose to retry, downgrade priority, or abort
- Thresholds configurable per queue type (CRITICAL vs normal)

```python
# Backpressure triggers at threshold
if fill_ratio >= threshold:
    raise QueueFullError(fill_ratio, threshold, queue_type)
```

### Dispatch Algorithm

Priority-based dispatch with CRITICAL always first:

```python
async def _dispatch_loop(self):
    """调度循环核心：CRITICAL 优先"""
    while self._running:
        # 1. 先处理 CRITICAL（最高优先级）
        ticket = await self._pop_ticket(RequestPriority.CRITICAL)
        if ticket:
            await self._signal_turn(ticket)
            await asyncio.sleep(1.0 / self.config.critical_dispatch_rate)
            continue

        # 2. CRITICAL 空，处理普通队列（按优先级）
        for priority in [HIGH, NORMAL, LOW]:
            ticket = await self._pop_ticket(priority)
            if ticket:
                await self._signal_turn(ticket)
                await asyncio.sleep(1.0 / self.config.normal_dispatch_rate)
                break
```

### Auto-Adjustment

The queue dynamically adjusts dispatch rates based on observed wait times:

```python
async def _adjust_config(self):
    """根据统计数据智能调整配置"""
    # If CRITICAL avg wait exceeds target, increase dispatch rate
    if critical_avg_wait > self.config.critical_target_wait_time:
        self.config.critical_dispatch_rate *= 1.2

    # If reject rate exceeds 10%, increase backpressure threshold
    if critical_reject_rate > 0.1:
        self.config.critical_backpressure_threshold += 0.05
```

### Usage Example

```python
from request_queue import RequestQueue, RequestPriority, QueueConfig

# Create queue with custom config
config = QueueConfig(
    critical_max_size=10,
    critical_backpressure_threshold=0.9,
    normal_max_size=50
)
queue = RequestQueue(config)

# Start dispatcher
await queue.start_dispatcher()

# Request turn (entry point)
try:
    ticket = await queue.request_turn(RequestPriority.NORMAL)
    await ticket.wait_for_turn(timeout=30.0)
    
    # Execute LLM request (queue doesn't intervene)
    response = await gateway.chat_completion(...)
    
finally:
    # Check stats
    stats = queue.get_stats()
    print(f"Queue fill ratio: {stats['fill_ratios']['total']:.2%}")

# Stop dispatcher
await queue.stop_dispatcher()
```

### Integration with LLMGateway

RequestQueue is integrated into LLMGateway for automatic turn management:

```python
# In LLMGateway.chat_completion():
# Phase 1: Queue turn request
ticket = await self.request_turn(priority)
await ticket.wait_for_turn(timeout=self.get_dynamic_timeout(priority))

# Phase 2-4: Execute with semaphore and rate limiter
async with self._request_semaphore:
    if self._rate_limiter:
        await self._rate_limiter.wait_and_acquire(max_wait=max_wait)
    result = await self._chat_completion_with_fallback_internal(...)
```

---

## SubagentInstance

The `subagent` module provides independent context subagent execution with configurable permission sets. Each subagent operates with its own conversation history, isolated from the main agent context, enabling parallel task execution without context pollution.

### Purpose

SubagentInstance enables the agent to delegate specific tasks to specialized sub-agents with restricted capabilities. This provides:

- **Isolated Context**: Each subagent maintains independent conversation history
- **Permission Isolation**: Configurable tool access per subagent type
- **Parallel Execution**: Multiple subagents can run concurrently
- **Result Aggregation**: Only key results returned to main conversation

### Key Classes

#### SubagentType

Enum defining the four subagent types with specific purposes.

```python
class SubagentType(Enum):
    """Subagent 类型枚举"""
    EXPLORE = "explore"      # 只读探索：搜索文件、阅读代码
    REVIEW = "review"       # 审查验证：只读 + 代码执行
    IMPLEMENT = "implement" # 实现执行：全权限
    PLAN = "plan"           # 规划分析：只读 + 记忆写入
```

| Type | Permission Set | Purpose |
|------|----------------|---------|
| `EXPLORE` | `read_only` | Search files, read code, understand structure |
| `REVIEW` | `review` | Code review, testing, quality verification |
| `IMPLEMENT` | `implement` | Feature implementation, bug fixes, refactoring |
| `PLAN` | `plan` | Task analysis, planning, decision recording |

#### Permission Sets

Each subagent type has a predefined permission set controlling available tools.

```python
PERMISSION_SETS: Dict[str, Set[str]] = {
    "read_only": {
        "file_read",
        "search_history",
        "ask_user",
    },
    "review": {
        "file_read",
        "code_as_policy",
        "search_history",
        "ask_user",
    },
    "implement": {
        "file_read",
        "file_write",
        "file_edit",
        "code_as_policy",
        "write_memory",
        "read_memory_index",
        "search_memory",
        "search_history",
        "ask_user",
        "run_diagnosis",
    },
    "plan": {
        "file_read",
        "write_memory",
        "read_memory_index",
        "search_memory",
        "search_history",
        "ask_user",
    },
}
```

| Permission Set | Allowed Tools |
|----------------|---------------|
| `read_only` | `file_read`, `search_history`, `ask_user` |
| `review` | `file_read`, `code_as_policy`, `search_history`, `ask_user` |
| `implement` | All file tools + `code_as_policy` + memory tools + `search_history` + `ask_user` + `run_diagnosis` |
| `plan` | `file_read`, `write_memory`, `read_memory_index`, `search_memory`, `search_history`, `ask_user` |

#### SubagentState

Dataclass tracking subagent execution state.

```python
@dataclass
class SubagentState:
    """Subagent 状态"""
    id: str
    subagent_type: SubagentType
    status: str  # "pending", "running", "completed", "failed", "timeout"
    prompt: str
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    iterations: int = 0
    parent_session_id: Optional[str] = None
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique task identifier |
| `subagent_type` | `SubagentType` | Subagent type enum |
| `status` | `str` | Execution status (pending/running/completed/failed/timeout) |
| `prompt` | `str` | Original task prompt |
| `result` | `Optional[str]` | Execution result (on success) |
| `error` | `Optional[str]` | Error message (on failure) |
| `iterations` | `int` | Number of tool call iterations executed |

#### SubagentInstance

Main class for independent subagent execution.

```python
class SubagentInstance:
    """独立上下文的 Subagent 执行实例"""

    MAX_SUBAGENT_ITERATIONS = 15  # Default iteration limit

    def __init__(
        self,
        gateway: LLMGateway,
        subagent_type: SubagentType,
        model_id: Optional[str] = None,
        max_iterations: int = MAX_SUBAGENT_ITERATIONS,
        timeout: int = 300,  # 5 minute timeout
        custom_system_prompt: Optional[str] = None,
        custom_tools: Optional[Set[str]] = None,
    ):
        """
        Initialize Subagent instance.

        Args:
            gateway: LLM gateway instance (shared with parent agent)
            subagent_type: Subagent type determining permission set
            model_id: Model ID (defaults to primary model)
            max_iterations: Maximum tool call iterations (default: 15)
            timeout: Execution timeout in seconds (default: 300)
            custom_system_prompt: Override default system prompt
            custom_tools: Override default permission set
        """
```

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `gateway` | `LLMGateway` | required | Shared LLM gateway instance |
| `subagent_type` | `SubagentType` | required | Determines permission set |
| `model_id` | `Optional[str]` | primary model | Specific model to use |
| `max_iterations` | `int` | `15` | Tool call iteration limit |
| `timeout` | `int` | `300` | Execution timeout (seconds) |
| `custom_system_prompt` | `Optional[str]` | type-specific | Override default prompt |
| `custom_tools` | `Optional[Set[str]]` | type-specific | Override permission set |

### Key Methods

#### `run(prompt: str, task_id: Optional[str] = None) -> SubagentState`

Main execution method with timeout protection.

```python
async def run(self, prompt: str, task_id: Optional[str] = None) -> SubagentState:
    """Execute Subagent task with timeout protection.

    Args:
        prompt: Task prompt
        task_id: Optional task ID for tracking

    Returns:
        SubagentState: Final execution state
    """
    task_id = task_id or str(uuid.uuid4())[:8]
    self.state = SubagentState(
        id=task_id,
        subagent_type=self.subagent_type,
        status="pending",
        prompt=prompt,
    )

    try:
        result = await asyncio.wait_for(
            self._run_loop(),
            timeout=self.timeout
        )
        self.state.status = "completed"
        self.state.result = result

    except asyncio.TimeoutError:
        self.state.status = "timeout"
        self.state.error = f"Execution timed out after {self.timeout} seconds"

    except Exception as e:
        self.state.status = "failed"
        self.state.error = str(e)

    return self.state
```

#### `_run_loop() -> str`

Internal execution loop matching AgentLoop pattern.

```python
async def _run_loop(self) -> str:
    """Main execution loop."""
    iteration = 0

    while iteration < self.max_iterations:
        iteration += 1
        self.state.iterations = iteration

        messages = self._build_messages()
        response = await self.gateway.chat_completion(
            self.model_id,
            messages,
            tools=self.tools.get_schemas()
        )

        choice = response['choices'][0]
        message = choice['message']
        self.history.append(message)

        if message.get('tool_calls'):
            tool_results = await self._execute_tool_calls(message['tool_calls'])
            self.history.extend(tool_results)
        else:
            # No tool calls = task complete
            return message.get('content', '')

    raise RuntimeError(f"Exceeded maximum iterations ({self.max_iterations})")
```

#### SubagentResult

Wrapper class providing convenient access to execution results.

```python
class SubagentResult:
    """Subagent 执行结果"""

    def __init__(self, state: SubagentState):
        self.state = state

    @property
    def success(self) -> bool:
        return self.state.status == "completed"

    @property
    def result(self) -> Optional[str]:
        return self.state.result

    @property
    def error(self) -> Optional[str]:
        return self.state.error

    @property
    def summary(self) -> str:
        """Returns truncated result summary."""
        if self.success:
            r = self.result or ""
            if len(r) > 500:
                return r[:500] + "...(truncated)"
            return r
        return f"[{self.state.status.upper()}] {self.error}"
```

### System Prompts

Each subagent type has a predefined system prompt guiding behavior:

| Type | Core Responsibilities |
|------|----------------------|
| `EXPLORE` | Search/analyze files, understand structure, report findings (no modifications) |
| `REVIEW` | Review quality/security, run tests, check best practices (no modifications) |
| `IMPLEMENT` | Implement features, fix bugs, refactor (full file permissions) |
| `PLAN` | Analyze requirements, create execution plan, record decisions (no file modifications) |

### Usage Example

```python
from subagent import SubagentInstance, SubagentType
from client import LLMGateway

# Initialize gateway
gateway = LLMGateway("~/.seed/config.json")

# Create explore subagent
explore_agent = SubagentInstance(
    gateway=gateway,
    subagent_type=SubagentType.EXPLORE,
    timeout=60  # Quick exploration
)

# Execute task
state = await explore_agent.run("Find all Python files in the src/tools directory")
if state.status == "completed":
    print(state.result)
else:
    print(f"Error: {state.error}")
```

---

## SubagentManager

The `subagent_manager` module orchestrates subagent lifecycle, parallel execution, and result aggregation. It manages concurrent subagent instances with resource limits and provides convenient factory methods.

### Purpose

SubagentManager provides:

- **Lifecycle Management**: Create, execute, and cleanup subagents
- **Parallel Execution**: Run multiple subagents concurrently with semaphore control
- **Result Collection**: Aggregate results from multiple tasks
- **Resource Limits**: Maximum concurrent subagent count
- **Status Tracking**: Monitor task states with callbacks

### Key Classes

#### SubagentTask

Task definition dataclass for subagent configuration.

```python
@dataclass
class SubagentTask:
    """Subagent 任务定义"""
    id: str
    subagent_type: SubagentType
    prompt: str
    custom_tools: Optional[set] = None
    custom_system_prompt: Optional[str] = None
    max_iterations: Optional[int] = None
    timeout: Optional[int] = None
    priority: int = 0  # Higher priority executes first
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique task identifier |
| `subagent_type` | `SubagentType` | Subagent type |
| `prompt` | `str` | Task prompt |
| `custom_tools` | `Optional[set]` | Override default permission set |
| `custom_system_prompt` | `Optional[str]` | Override default system prompt |
| `max_iterations` | `Optional[int]` | Override default iteration limit |
| `timeout` | `Optional[int]` | Override default timeout |
| `priority` | `int` | Execution priority (higher = first) |

#### SubagentManager

Main orchestration class managing subagent lifecycle.

```python
class SubagentManager:
    """Subagent 管理器"""

    DEFAULT_MAX_CONCURRENT = 3  # Default parallel limit
    DEFAULT_TIMEOUT = 300       # Default timeout 5 minutes
    DEFAULT_MAX_ITERATIONS = 15 # Default iteration limit

    def __init__(
        self,
        gateway: LLMGateway,
        model_id: Optional[str] = None,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    ):
        """
        Initialize SubagentManager.

        Args:
            gateway: LLM gateway instance
            model_id: Default model ID
            max_concurrent: Maximum concurrent subagents
        """
        self.gateway = gateway
        self.model_id = model_id or self._get_primary_model()
        self.max_concurrent = max_concurrent

        # Active subagent instances
        self._instances: Dict[str, SubagentInstance] = {}

        # Task state tracking
        self._tasks: Dict[str, SubagentTask] = {}

        # Execution results
        self._results: Dict[str, SubagentResult] = {}

        # Concurrency control semaphore
        self._semaphore = asyncio.Semaphore(max_concurrent)
```

### Key Methods

#### Lifecycle Methods

```python
def create_task(
    self,
    subagent_type: SubagentType,
    prompt: str,
    custom_tools: Optional[set] = None,
    custom_system_prompt: Optional[str] = None,
    max_iterations: Optional[int] = None,
    timeout: Optional[int] = None,
    priority: int = 0,
) -> str:
    """Create Subagent task, returns task ID."""

def spawn_subagent(self, task_id: str) -> SubagentInstance:
    """Create SubagentInstance for existing task."""

async def run_subagent(self, task_id: str) -> SubagentResult:
    """Execute single subagent task with semaphore control."""

def cleanup(self, task_id: Optional[str] = None):
    """Clean up task resources (all if task_id is None)."""
```

#### Parallel Execution

```python
async def run_parallel(
    self,
    task_ids: List[str],
    fail_fast: bool = False,
) -> Dict[str, SubagentResult]:
    """Execute multiple subagents concurrently.

    Args:
        task_ids: List of task IDs to execute
        fail_fast: Stop on first failure (sequential if True)

    Returns:
        Dict[str, SubagentResult]: Task ID -> result mapping
    """
```

#### Status and Results

```python
def get_status(self, task_id: str) -> Optional[str]:
    """Get task status (pending/running/completed/failed/timeout)."""

def get_result(self, task_id: str) -> Optional[SubagentResult]:
    """Get task result."""

def get_all_results(self) -> Dict[str, SubagentResult]:
    """Get all results."""

def list_tasks(self, status: Optional[str] = None) -> List[Dict]:
    """List all tasks, optionally filtered by status."""
```

#### Result Aggregation

```python
def aggregate_results(
    self,
    task_ids: List[str],
    include_errors: bool = True,
    max_length: int = 2000,
) -> str:
    """Aggregate results from multiple tasks.

    Args:
        task_ids: List of task IDs
        include_errors: Include error messages
        max_length: Max length per result

    Returns:
        str: Aggregated summary
    """
```

### Convenience Methods

Factory methods for creating specific subagent types:

```python
def spawn_explore(self, prompt: str, **kwargs) -> str:
    """Create EXPLORE subagent task."""

def spawn_review(self, prompt: str, **kwargs) -> str:
    """Create REVIEW subagent task."""

def spawn_implement(self, prompt: str, **kwargs) -> str:
    """Create IMPLEMENT subagent task."""

def spawn_plan(self, prompt: str, **kwargs) -> str:
    """Create PLAN subagent task."""
```

### Status Callbacks

```python
def register_status_callback(self, callback: Callable[[str, str], None]):
    """Register callback for status changes (task_id, status)."""

def _notify_status(self, task_id: str, status: str):
    """Notify all registered callbacks."""
```

### Usage Example

```python
from subagent_manager import SubagentManager
from subagent import SubagentType
from client import LLMGateway

# Initialize
gateway = LLMGateway("~/.seed/config.json")
manager = SubagentManager(gateway, max_concurrent=3)

# Create multiple tasks
task1 = manager.spawn_explore("Analyze the authentication module")
task2 = manager.spawn_explore("Find database connection patterns")
task3 = manager.spawn_review("Check for SQL injection vulnerabilities")

# Execute in parallel
results = await manager.run_parallel([task1, task2, task3])

# Aggregate results
summary = manager.aggregate_results([task1, task2, task3])
print(summary)

# Cleanup
manager.cleanup()
```

---

## RalphSubagentOrchestrator

The `RalphSubagentOrchestrator` provides a Plan→Implement→Review workflow for RalphLoop integration, enabling structured multi-phase task execution with external verification.

### Purpose

RalphSubagentOrchestrator implements a three-phase execution pattern:

1. **Plan Phase**: Analyze task, create execution plan
2. **Implement Phase**: Parallel execution of subtasks
3. **Review Phase**: Verify implementation quality

This pattern integrates with RalphLoop's external verification for deterministic completion.

### Execution Workflow

```
RalphSubagentOrchestrator Flow:

┌─────────────────────────────────────────────────────┐
│ 1. plan_phase(task_prompt)                          │
│    → Spawn PLAN subagent                            │
│    → Returns execution plan                         │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│ 2. implement_phase(implement_prompts)               │
│    → Spawn multiple IMPLEMENT subagents (parallel) │
│    → Returns results for each subtask               │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│ 3. review_phase(review_prompt)                      │
│    → Spawn REVIEW subagent                          │
│    → Returns verification result                    │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│ 4. get_execution_report()                           │
│    → Returns structured report of all phases        │
└─────────────────────────────────────────────────────┘
```

### Key Methods

#### `__init__(manager: SubagentManager)`

```python
class RalphSubagentOrchestrator:
    """RalphLoop 升级的 Subagent 编排器"""

    def __init__(self, manager: SubagentManager):
        self.manager = manager
        self._plan_task_id: Optional[str] = None
        self._implement_task_ids: List[str] = []
        self._review_task_id: Optional[str] = None
```

#### Phase Methods

```python
async def plan_phase(self, task_prompt: str) -> str:
    """规划阶段: Spawn PLAN subagent to create execution plan."""
    self._plan_task_id = self.manager.spawn_plan(
        f"请分析以下任务并制定执行计划:\n\n{task_prompt}"
    )
    result = await self.manager.run_subagent(self._plan_task_id)
    return result.summary

async def implement_phase(
    self,
    implement_prompts: List[str],
) -> Dict[str, SubagentResult]:
    """实现阶段: Parallel execution of multiple IMPLEMENT subagents."""
    self._implement_task_ids = []
    for prompt in implement_prompts:
        task_id = self.manager.spawn_implement(prompt)
        self._implement_task_ids.append(task_id)

    return await self.manager.run_parallel(self._implement_task_ids)

async def review_phase(self, review_prompt: str) -> str:
    """审查阶段: Spawn REVIEW subagent for verification."""
    self._review_task_id = self.manager.spawn_review(review_prompt)
    result = await self.manager.run_subagent(self._review_task_id)
    return result.summary
```

#### Report and Cleanup

```python
def get_execution_report(self) -> Dict:
    """获取执行报告: Returns structured report of all phases."""
    return {
        "plan": {
            "task_id": self._plan_task_id,
            "result": self.manager.get_result(self._plan_task_id).summary,
        },
        "implement": [
            {
                "task_id": task_id,
                "result": self.manager.get_result(task_id).summary,
            }
            for task_id in self._implement_task_ids
        ],
        "review": {
            "task_id": self._review_task_id,
            "result": self.manager.get_result(self._review_task_id).summary,
        },
    }

def cleanup(self):
    """清理所有任务: Clear all task resources."""
```

### Usage Example

```python
from subagent_manager import SubagentManager, RalphSubagentOrchestrator
from client import LLMGateway

# Initialize
gateway = LLMGateway("~/.seed/config.json")
manager = SubagentManager(gateway)
orchestrator = RalphSubagentOrchestrator(manager)

# Phase 1: Plan
plan_result = await orchestrator.plan_phase(
    "Implement user authentication with JWT tokens"
)

# Phase 2: Implement (parallel)
implement_prompts = [
    "Implement JWT token generation in auth.py",
    "Implement token validation middleware",
    "Create user login endpoint",
]
implement_results = await orchestrator.implement_phase(implement_prompts)

# Phase 3: Review
review_result = await orchestrator.review_phase(
    "Review the authentication implementation for security issues"
)

# Get full report
report = orchestrator.get_execution_report()
print(f"Plan: {report['plan']['result']}")
print(f"Implement tasks: {len(report['implement'])}")
print(f"Review: {report['review']['result']}")

# Cleanup
orchestrator.cleanup()
```

### Integration with RalphLoop

```python
from ralph_loop import RalphLoop, CompletionType

# Create orchestrator
orchestrator = RalphSubagentOrchestrator(manager)

# RalphLoop iteration using orchestrator
async def ralph_iteration():
    # Plan
    plan = await orchestrator.plan_phase(task_prompt)
    
    # Parse plan into implement prompts
    implement_prompts = parse_plan_into_subtasks(plan)
    
    # Execute
    results = await orchestrator.implement_phase(implement_prompts)
    
    # Review
    review = await orchestrator.review_phase("Verify all implementations")
    
    # Return for external verification
    return review

# Use with RalphLoop
ralph = RalphLoop.create_test_driven(
    agent_loop=agent,
    task_prompt_path=Path(".seed/tasks/auth.md"),
    test_command="pytest tests/auth/",
    pass_rate=100
)
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
        "health_check": 60 * 60,        # Every hour
    }

    # Note: autonomous_explore is handled by AutonomousExplorer class (30-minute idle monitoring)
    # It is NOT a scheduler built-in task

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
