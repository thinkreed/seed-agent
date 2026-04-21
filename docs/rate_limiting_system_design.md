# LLM 请求限流系统设计文档

> **决策摘要**：在 LLMGateway 中集成多层次限流机制（Token Bucket + 滚动窗口追踪 + 请求队列 + 状态持久化），解决 Subagent 并发执行导致的 LLM Provider 限流问题，配置通过 `config.json` 可自定义。

---

## 一、背景与动机

### 1.1 问题现象

引入 ULW Subagent 机制后，系统频繁触发 LLM 服务端限流错误：

```
Provider 返回 429 Rate Limit Error
→ Retry 3 次 (exponential backoff)
→ Fallback 到备用 Provider
→ 最终全部失败
```

### 1.2 根因分析

| 层级 | 文件位置 | 问题 |
|------|----------|------|
| **SubagentManager** | `src/subagent_manager.py` L56, L88 | `max_concurrent=3` 允许 3 个 subagent 并行 |
| **SubagentInstance** | `src/subagent.py` L156 | `MAX_SUBAGENT_ITERATIONS=15` 每个 subagent 最多 15 轮 LLM 调用 |
| **LLMGateway** | `src/client.py` 全文件 | **无任何请求限流机制** - 直接发到 Provider |
| **并行执行** | `src/subagent_manager.py` L233 | `asyncio.gather(*tasks)` 真正并发执行 |

### 1.3 并发请求峰值计算

```
峰值请求 = max_concurrent × MAX_SUBAGENT_ITERATIONS
         = 3 × 15 = 45 个并发 LLM 调用

加上重试 (每个请求最多 3 次):
         = 45 × 3 = 135 次实际 API 调用尝试
```

### 1.4 Provider 限流规格

**阿里云百炼（默认 Provider）**：

| 时间窗口 | 请求上限 | 平均速率 |
|----------|----------|----------|
| **5小时** | 6,000 次 | **0.33 req/sec** (核心瓶颈) |
| 每周 | 45,000 次 | 更宽松 |
| 每月 | 90,000 次 | 更宽松 |

**关键洞察**：
- 5小时窗口是核心瓶颈（滚动窗口，非固定窗口）
- 突发可快速耗尽配额（如 10 分钟用完 6000 次 → 等待 5 小时）
- 需要精确的速率控制，而非简单并发限制

---

## 二、架构设计

### 2.1 系统架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Rate Limiting System Architecture                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐│
│  │ AgentLoop     │  │ RalphLoop     │  │ SubagentMgr   │  │ Scheduler     ││
│  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘│
│          │                  │                  │                  │         │
│          ▼                  ▼                  ▼                  ▼         │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                     LLMGateway (统一入口)                                ││
│  │                                                                          ││
│  │  ┌───────────────────────────────────────────────────────────────────┐ ││
│  │  │                    RequestQueue (异步调度)                          │ ││
│  │  │  • FIFO / Priority Queue                                           │ ││
│  │  │  • Async dispatch                                                  │ ││
│  │  │  • Backpressure mechanism                                          │ ││
│  │  └───────────────────────────────────────────────────────────────────┘ ││
│  │                                    │                                    ││
│  │                                    ▼                                    ││
│  │  ┌───────────────────────────────────────────────────────────────────┐ ││
│  │  │                   RollingWindowTracker                             │ ││
│  │  │  • 5小时滚动窗口追踪                                                │ ││
│  │  │  • 窗口内请求计数                                                   │ ││
│  │  │  • 下次可用时间预测                                                 │ ││
│  │  └───────────────────────────────────────────────────────────────────┘ ││
│  │                                    │                                    ││
│  │                                    ▼                                    ││
│  │  ┌───────────────────────────────────────────────────────────────────┐ ││
│  │  │                   TokenBucketRateLimiter                           │ ││
│  │  │  • Rate: 0.33 tokens/sec (可配置)                                   │ ││
│  │  │  • Capacity: 100 (burst)                                            │ ││
│  │  │  • 平滑突发请求                                                     │ ││
│  │  └───────────────────────────────────────────────────────────────────┘ ││
│  │                                    │                                    ││
│  │                                    ▼                                    ││
│  │  ┌───────────────────────────────────────────────────────────────────┐ ││
│  │  │                   Semaphore (并发控制)                              │ ││
│  │  │  • max_concurrent: 3-5 (可配置)                                     │ ││
│  │  └───────────────────────────────────────────────────────────────────┘ ││
│  │                                    │                                    ││
│  │                                    ▼                                    ││
│  │  ┌───────────────────────────────────────────────────────────────────┐ ││
│  │  │                   RateLimitState (状态持久化)                       │ ││
│  │  │  • SQLite storage                                                  │ ││
│  │  │  • Cross-process shared                                            │ ││
│  │  │  • Crash recovery                                                  │ ││
│  │  └───────────────────────────────────────────────────────────────────┘ ││
│  │                                    │                                    ││
│  └────────────────────────────────────┼────────────────────────────────────┘│
│                                       │                                     │
│                                       ▼                                     │
│                              ┌───────────────────┐                           │
│                              │ LLM Provider API  │                           │
│                              │ (阿里云百炼等)    │                           │
│                              └───────────────────┘                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件职责

| 组件 | 文件 | 职责 |
|------|------|------|
| **RequestQueue** | `request_queue.py` | 异步请求调度、优先级队列、反压机制 |
| **TokenBucket** | `rate_limiter.py` | 突发流量平滑、token 速率控制 |
| **RollingWindowTracker** | `rate_limiter.py` | 5小时滚动窗口追踪、配额监控 |
| **RateLimitState** | `rate_limit_db.py` | 状态持久化、跨进程共享、崩溃恢复 |
| **LLMGateway** | `client.py` | 统一入口、限流集成、配置读取 |

### 2.3 请求处理流程

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          请求处理完整流程                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  chat_completion(model_id, messages, priority)                             │
│  │                                                                          │
│  │ 1. 判断优先级                                                            │
│  │    ├── CRITICAL → direct_execution (跳过队列)                           │
│  │    ├── HIGH/NORMAL → direct_execution (队列空闲时)                       │
│  │    └── LOW → request_queue.submit()                                     │
│  │                                                                          │
│  │ 2. direct_execution 流程:                                               │
│  │    │                                                                     │
│  │    ├── RollingWindowTracker.check_available()                           │
│  │    │   ├── 检查窗口内请求数 (< 6000)                                     │
│  │    │   ├── 如果超限 → 返回 wait_time                                     │
│  │    │   └── asyncio.sleep(wait_time)                                     │
│  │    │                                                                     │
│  │    ├── TokenBucket.acquire()                                            │
│  │    │   ├── 检查 token 可用性                                             │
│  │    │   ├── 如果不足 → 返回 wait_time                                     │
│  │    │   └── asyncio.sleep(wait_time)                                     │
│  │    │                                                                     │
│  │    ├── Semaphore.acquire() (并发控制)                                   │
│  │    │                                                                     │
│  │    ├── chat_completion_with_fallback()                                  │
│  │    │   ├── retry × 3                                                    │
│  │    │   └── provider fallback                                            │
│  │    │                                                                     │
│  │    ├── RollingWindowTracker.record_request()                            │
│  │    │                                                                     │
│  │    ├── RateLimitDB.record_request()                                     │
│  │    │                                                                     │
│  │    └── Semaphore.release()                                              │
│  │                                                                          │
│  │ 3. queue 流程:                                                          │
│  │    │                                                                     │
│  │    ├── submit() → 加入优先级队列                                         │
│  │    │                                                                     │
│  │    ├── QueueDispatcher 取出请求                                         │
│  │    │                                                                     │
│  │    ├── 调用 _execute_with_rate_limit()                                  │
│  │    │                                                                     │
│  │    └── wait_for_result() → 返回结果                                     │
│  │                                                                          │
│  │ 4. 状态持久化 (后台):                                                    │
│  │    │                                                                     │
│  │    ├── 每分钟: save_state() → SQLite                                    │
│  │    │   ├── window_requests                                              │
│  │    │   ├── tokens_available                                             │
│  │    │   └── last_refill_time                                             │
│  │    │                                                                     │
│  │    └── 启动时: restore_state() ← SQLite                                 │
│  │                                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、配置系统设计

### 3.1 配置 Schema

新增 `RateLimitConfig` 类于 `models.py`：

```python
class RateLimitConfig(BaseModel):
    """限流配置
    
    支持两种限流模式:
    - rolling_window: 滚动窗口（如百炼 5小时6000次）
    - rpm: 固定 RPM（如 OpenAI 标准限流）
    """
    model_config = ConfigDict(extra='ignore')
    
    # 滚动窗口模式
    rolling_window_requests: Optional[int] = None  # 窗口内最大请求
    rolling_window_duration: Optional[int] = None  # 窗口时长（秒）
    
    # 固定 RPM 模式
    rpm: Optional[int] = None  # 每分钟请求限制
    
    # 突发容量
    burst_capacity: int = 100
    
    # 并发控制
    max_concurrent: int = 3
    
    # 队列配置
    queue_max_size: int = 50
    queue_backpressure_threshold: float = 0.8
    
    def get_effective_rate(self) -> float:
        """计算有效速率（requests/sec）"""
        if self.rpm is not None:
            return self.rpm / 60.0
        
        if self.rolling_window_requests and self.rolling_window_duration:
            return self.rolling_window_requests / self.rolling_window_duration
        
        # 默认百炼规格
        return 6000 / 18000  # 0.33 req/sec
```

### 3.2 config.json 示例

```json
{
  "models": {
    "bailian": {
      "baseUrl": "https://coding.dashscope.aliyuncs.com/v1",
      "apiKey": "${BAILIAN_API_KEY}",
      "api": "openai-completions",
      "models": [
        {
          "id": "glm-5",
          "name": "GLM-5",
          "contextWindow": 100000,
          "maxTokens": 4096
        }
      ],
      "rateLimit": {
        "rollingWindowRequests": 6000,
        "rollingWindowDuration": 18000,
        "burstCapacity": 100,
        "maxConcurrent": 3,
        "queueMaxSize": 50,
        "queueBackpressureThreshold": 0.8
      }
    },
    
    "openai": {
      "baseUrl": "https://api.openai.com/v1",
      "apiKey": "${OPENAI_API_KEY}",
      "api": "openai-completions",
      "models": [...],
      "rateLimit": {
        "rpm": 500,
        "burstCapacity": 50,
        "maxConcurrent": 5
      }
    }
  },
  
  "agents": {
    "defaults": {
      "defaults": {
        "primary": "bailian/glm-5"
      }
    }
  }
}
```

### 3.3 配置字段对照表

| config.json 字段 | Python 属性 | 默认值 | 说明 |
|------------------|-------------|--------|------|
| `rollingWindowRequests` | `rolling_window_requests` | 6000 | 滚动窗口内最大请求 |
| `rollingWindowDuration` | `rolling_window_duration` | 18000 | 窗口时长（秒）= 5小时 |
| `rpm` | `rpm` | None | RPM模式（优先于滚动窗口） |
| `burstCapacity` | `burst_capacity` | 100 | 突发容量 |
| `maxConcurrent` | `max_concurrent` | 3 | 最大并发 |
| `queueMaxSize` | `queue_max_size` | 50 | 队列容量 |
| `queueBackpressureThreshold` | `queue_backpressure_threshold` | 0.8 | 反压阈值 |

### 3.4 两种限流模式

| 模式 | 配置方式 | 速率计算 | 适用场景 |
|------|----------|----------|----------|
| **滚动窗口** | `rollingWindowRequests` + `rollingWindowDuration` | requests/duration | 百炼等长窗口限流 |
| **固定 RPM** | `rpm` | rpm/60 | OpenAI 等分钟限流 |

---

## 四、核心组件详细设计

### 4.1 Token Bucket Rate Limiter

```python
# rate_limiter.py

class TokenBucket:
    """Token Bucket 限流器
    
    核心算法:
    - tokens 以固定速率补充
    - 每次请求消耗 1 token
    - tokens 不能超过 capacity
    - tokens 不足时需要等待
    """
    
    def __init__(self, rate: float, capacity: float):
        self.rate = rate              # 每秒补充 token 数
        self.capacity = capacity      # 最大 token 数
        self.tokens = capacity        # 初始满载
        self.last_refill = time.time()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> tuple[bool, float]:
        """尝试获取 token
        
        Returns:
            (allowed, wait_time): 是否允许, 需等待时间
        """
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_refill
            
            # 补充 tokens
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            self.last_refill = now
            
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True, 0.0
            
            # 需要等待
            wait_time = (1.0 - self.tokens) / self.rate
            return False, wait_time
```

### 4.2 Rolling Window Tracker

```python
# rate_limiter.py

class RollingWindowTracker:
    """滚动窗口追踪器
    
    核心机制:
    - 记录每个请求的时间戳
    - 滚动计算窗口内已用请求数
    - 窗口为滑动窗口（非固定窗口）
    """
    
    def __init__(self, window_limit: int, window_duration: float):
        self.window_limit = window_limit       # 6000
        self.window_duration = window_duration # 18000秒 (5小时)
        self.requests: list[float] = []        # 时间戳列表
        self._lock = asyncio.Lock()
    
    async def check_available(self) -> tuple[bool, float]:
        """检查是否可以发起请求
        
        Returns:
            (available, wait_seconds)
        """
        async with self._lock:
            now = time.time()
            
            # 清理过期记录
            self.requests = [
                t for t in self.requests
                if now - t < self.window_duration
            ]
            
            if len(self.requests) < self.window_limit:
                return True, 0.0
            
            # 窗口满了，计算等待时间
            oldest = min(self.requests)
            wait_until = oldest + self.window_duration
            wait_seconds = wait_until - now
            
            return False, wait_seconds
    
    async def record_request(self) -> None:
        """记录一个请求"""
        async with self._lock:
            self.requests.append(time.time())
    
    def get_remaining(self) -> int:
        """获取窗口内剩余请求数"""
        now = time.time()
        active = [t for t in self.requests if now - t < self.window_duration]
        return self.window_limit - len(active)
    
    def get_reset_time(self) -> float:
        """获取窗口重置时间（最早请求过期时间）"""
        if not self.requests:
            return time.time()
        return min(self.requests) + self.window_duration
```

### 4.3 Request Queue System

```python
# request_queue.py

class RequestPriority(Enum):
    """请求优先级"""
    CRITICAL = 0    # 用户直接交互，跳过队列
    HIGH = 1        # RalphLoop 迭代，优先处理
    NORMAL = 2      # Subagent 任务，标准处理
    LOW = 3         # Scheduler 后台，走队列

class RequestQueue:
    """请求队列系统
    
    特性:
    - FIFO + 优先级排序
    - 异步调度分发
    - 反压机制（队列满时拒绝新请求）
    """
    
    def __init__(
        self,
        max_size: int = 100,
        dispatch_rate: float = 0.33,
        backpressure_threshold: float = 0.8,
    ):
        self.max_size = max_size
        self.dispatch_rate = dispatch_rate
        self.backpressure_threshold = backpressure_threshold
        
        # 多优先级队列
        self._queues: Dict[RequestPriority, deque] = {
            p: deque() for p in RequestPriority
        }
        
        # 调度控制
        self._semaphore = asyncio.Semaphore(5)  # 最大同时执行数
        self._dispatcher_task: Optional[asyncio.Task] = None
        self._new_request_event = asyncio.Event()
    
    async def submit(
        self,
        model_id: str,
        messages: list,
        priority: RequestPriority = RequestPriority.NORMAL,
        **kwargs
    ) -> str:
        """提交请求到队列
        
        Returns:
            request_id: 请求ID
        """
        # 反压检查
        if self.get_fill_ratio() >= self.backpressure_threshold:
            raise QueueFullError("Queue at capacity, rejecting requests")
        
        item = RequestItem(
            model_id=model_id,
            messages=messages,
            kwargs=kwargs,
            priority=priority,
        )
        
        self._queues[priority].append(item)
        self._new_request_event.set()
        
        return item.id
    
    async def wait_for_result(
        self,
        request_id: str,
        timeout: float = 300.0
    ) -> dict:
        """等待请求完成"""
        # ... 轮询检查结果 ...
    
    async def start_dispatcher(self, executor: Callable):
        """启动异步调度器"""
        self._executor = executor
        self._dispatcher_task = asyncio.create_task(self._dispatch_loop())
    
    async def _dispatch_loop(self):
        """调度循环核心"""
        while True:
            await self._new_request_event.wait()
            
            item = self._get_next_request()
            if not item:
                self._new_request_event.clear()
                continue
            
            asyncio.create_task(self._execute_request(item))
    
    def _get_next_request(self) -> Optional[RequestItem]:
        """按优先级获取下一个请求"""
        for priority in RequestPriority:
            if self._queues[priority]:
                return self._queues[priority].popleft()
        return None
```

### 4.4 Rate Limit State Persistence

```python
# rate_limit_db.py

class RateLimitSQLite:
    """SQLite 持久化存储
    
    特性:
    - 跨进程共享状态
    - WAL 模式高并发
    - 自动清理过期数据
    - 崩溃恢复支持
    """
    
    DB_PATH = Path.home() / ".seed" / "rate_limit.db"
    
    def __init__(self):
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._lock = asyncio.Lock()
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rate_limit_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                window_requests TEXT NOT NULL DEFAULT '[]',
                tokens_available REAL NOT NULL DEFAULT 100.0,
                last_refill_time REAL NOT NULL,
                total_requests INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS request_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                priority TEXT NOT NULL,
                duration REAL,
                success INTEGER NOT NULL,
                error_message TEXT
            )
        """)
    
    async def load_state(self) -> RateLimitState:
        """加载当前状态"""
        async with self._lock:
            conn = self._get_conn()
            cursor = conn.execute("""
                SELECT window_requests, tokens_available, last_refill_time,
                       total_requests
                FROM rate_limit_state WHERE id = 1
            """)
            row = cursor.fetchone()
            
            if row:
                window_requests = json.loads(row[0])
                # 清理过期请求
                now = time.time()
                window_requests = [
                    t for t in window_requests
                    if now - t < 18000  # 5小时
                ]
                
                return RateLimitState(
                    timestamp=now,
                    requests_in_window=window_requests,
                    tokens_available=row[1],
                    last_refill_time=row[2],
                    total_requests_lifetime=row[3]
                )
            
            return RateLimitState(timestamp=time.time())
    
    async def save_state(self, state: RateLimitState):
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
            """, (
                json.dumps(state.requests_in_window),
                state.tokens_available,
                state.last_refill_time,
                state.total_requests_lifetime,
                time.time()
            ))
```

---

## 五、LLMGateway 集成

### 5.1 初始化流程

```python
# client.py

class LLMGateway:
    def __init__(self, config_path: str):
        # 加载配置
        self.config: FullConfig = load_config(config_path)
        self._init_clients()
        
        # === 从配置初始化限流组件 ===
        self._rate_config = self.config.get_primary_rate_limit()
        self._init_rate_limiting()
        self._init_state_persistence()
    
    def _init_rate_limiting(self):
        """从配置初始化限流组件"""
        config = self._rate_config
        
        # 1. Semaphore
        self._request_semaphore = asyncio.Semaphore(config.max_concurrent)
        
        # 2. Token Bucket
        self._rate_limiter = TokenBucket(
            rate=config.get_effective_rate(),
            capacity=config.burst_capacity,
        )
        
        # 3. Rolling Window Tracker
        self._window_tracker = RollingWindowTracker(
            window_limit=config.get_window_limit(),
            window_duration=config.get_window_duration(),
        )
        
        # 4. Request Queue
        self._request_queue = RequestQueue(
            max_size=config.queue_max_size,
            dispatch_rate=config.get_effective_rate(),
            backpressure_threshold=config.queue_backpressure_threshold,
        )
        
        logger.info(f"Rate limiting initialized: "
                   f"rate={config.get_effective_rate():.3f} req/sec")
```

### 5.2 主入口方法

```python
async def chat_completion(
    self,
    model_id: str,
    messages: List[Dict],
    priority: RequestPriority = RequestPriority.NORMAL,
    **kwargs
) -> Dict:
    """主入口 - 带限流的聊天补全
    
    Args:
        priority: 请求优先级
            - CRITICAL: 用户直接交互，跳过队列
            - HIGH: RalphLoop迭代，优先处理
            - NORMAL: Subagent任务，标准处理
            - LOW: Scheduler后台，走队列
    """
    # CRITICAL 优先级直接执行
    if priority == RequestPriority.CRITICAL:
        return await self._execute_with_rate_limit(model_id, messages, **kwargs)
    
    # 低优先级或队列繁忙 → 走队列
    if priority == RequestPriority.LOW or self._request_queue.get_fill_ratio() > 0.5:
        request_id = await self._request_queue.submit(model_id, messages, priority, **kwargs)
        return await self._request_queue.wait_for_result(request_id)
    
    # 高/正常优先级且队列空闲 → 直接执行
    return await self._execute_with_rate_limit(model_id, messages, **kwargs)
```

### 5.3 状态查询接口

```python
def get_rate_limit_status(self) -> dict:
    """获取限流状态（供外部查询）"""
    return {
        "config": {
            "rate": self._rate_config.get_effective_rate(),
            "window_limit": self._rate_config.get_window_limit(),
            "window_duration": self._rate_config.get_window_duration(),
            "burst_capacity": self._rate_config.burst_capacity,
            "max_concurrent": self._rate_config.max_concurrent,
        },
        "current": {
            "tokens_available": self._rate_limiter.tokens,
            "window_requests_used": len(self._window_tracker.requests),
            "window_requests_remaining": self._window_tracker.get_remaining(),
            "window_reset_time": self._window_tracker.get_reset_time(),
        },
        "queue": self._request_queue.get_stats(),
    }

def is_rate_limited(self) -> bool:
    """检查是否处于限流状态"""
    remaining = self._window_tracker.get_remaining()
    threshold = self._rate_config.get_window_limit() * 0.1
    return remaining < threshold
```

---

## 六、吞吐量预算

### 6.1 预期性能

基于百炼 20 RPM (5小时6000次) 限流：

```
长期平均:
• 0.33 req/sec × 3600 = 1200 req/hour
• 1200 × 5 = 6000 req/5hour (精确匹配限制)

突发能力:
• burst_capacity = 100
• 可在 ~5秒内用完100次突发
• 然后需要等待 token 补充

队列缓存:
• queue_size = 50
• 高峰时可缓存50个待处理请求
• 按优先级依次处理

安全裕度:
• 保留 ~5500 req/5hour 用于正常操作
• 剩余 ~500 用于突发/错误重试
```

### 6.2 参数调优建议

| 参数 | 建议值 | 调优说明 |
|------|--------|----------|
| `rolling_window_requests` | 5500 | 留 500 裕度 |
| `burst_capacity` | 50-100 | 允许短时爆发 |
| `max_concurrent` | 2-3 | 减少并发压力 |
| `queue_max_size` | 30-50 | 平衡容量和响应 |
| `backpressure_threshold` | 0.7-0.8 | 早期预警 |

---

## 七、文件结构

```
src/
├── models.py                    # 配置 schema（更新）
│   ├── RateLimitConfig          # 新增：限流配置类
│   └── ProviderConfig           # 更新：增加 rateLimit 字段
│
├── client.py                    # LLM Gateway（重构）
│   ├── _get_rate_limit_config() # 从配置读取
│   ├── _init_rate_limiting()    # 初始化限流组件
│   ├── chat_completion()        # 新入口（带优先级）
│   ├── _execute_with_rate_limit() # 带限流的执行
│   └── get_rate_limit_status()  # 状态查询
│
├── rate_limiter.py              # 新文件
│   ├── TokenBucket
│   └── RollingWindowTracker
│
├── request_queue.py             # 新文件
│   ├── RequestQueue
│   ├── RequestPriority
│   └── RequestItem
│
├── rate_limit_db.py             # 新文件
│   ├── RateLimitSQLite
│   └── RateLimitState

config/
└── config.json                  # 用户配置
    └── models.provider.rateLimit # 限流配置节点
```

---

## 八、实施路径

### 阶段一：核心限流（预计 1 天）

| 任务 | 文件 | 优先级 |
|------|------|--------|
| 新增 `RateLimitConfig` | `models.py` | P0 |
| 新增 `TokenBucket` | `rate_limiter.py` | P0 |
| 新增 `RollingWindowTracker` | `rate_limiter.py` | P0 |
| LLMGateway 集成限流 | `client.py` | P0 |

### 阶段二：队列系统（预计 1 天）

| 任务 | 文件 | 优先级 |
|------|------|--------|
| 新增 `RequestQueue` | `request_queue.py` | P1 |
| 新增 `RequestPriority` | `request_queue.py` | P1 |
| LLMGateway 集成队列 | `client.py` | P1 |

### 阶段三：状态持久化（预计 0.5 天）

| 任务 | 文件 | 优先级 |
|------|------|--------|
| 新增 `RateLimitSQLite` | `rate_limit_db.py` | P2 |
| 状态恢复逻辑 | `client.py` | P2 |
| 定期持久化 | `client.py` | P2 |

### 阶段四：智能负载均衡（未来扩展）

| 任务 | 文件 | 优先级 |
|------|------|--------|
| 响应时间追踪 | `load_balancer.py` | P3 |
| 错误率感知 | `load_balancer.py` | P3 |
| 动态权重调整 | `load_balancer.py` | P3 |

---

## 九、测试计划

### 9.1 单元测试

| 测试项 | 测试内容 |
|--------|----------|
| `TokenBucket.acquire` | token 补充、等待计算、并发安全 |
| `RollingWindowTracker` | 窗口边界、过期清理、剩余计算 |
| `RequestQueue` | 优先级排序、反压机制、并发执行 |
| `RateLimitSQLite` | 状态保存/恢复、跨进程共享 |

### 9.2 集成测试

| 测试项 | 测试内容 |
|--------|----------|
| 并发压力测试 | 50 并发请求，验证限流生效 |
| 长周期测试 | 5小时窗口边界，验证配额控制 |
| 崩溃恢复测试 | 进程中断后状态恢复 |
| 队列反压测试 | 队列满时拒绝行为 |

### 9.3 性能指标

| 指标 | 目标值 |
|------|--------|
| 请求成功率 | > 99% (限流场景) |
| 平均等待时间 | < 5秒 (正常负载) |
| 队列吞吐量 | 0.33 req/sec (稳定) |
| 状态恢复时间 | < 1秒 |

---

## 十、相关代码

| 文件 | 说明 |
|------|------|
| `src/client.py` | LLMGateway 主入口 |
| `src/subagent_manager.py` | Subagent 并发管理 |
| `src/subagent.py` | SubagentInstance 执行循环 |
| `src/agent_loop.py` | AgentLoop 工具调用 |
| `config/config.json` | Provider 和限流配置 |

---

## 十一、参考文献

- Token Bucket Algorithm: https://en.wikipedia.org/wiki/Token_bucket
- Rolling Window Rate Limiting: https://blog.cloudflare.com/counting-things-a-lot-of-different-things/
- AsyncIO Semaphore: https://docs.python.org/3/library/asyncio-sync.html#semaphore
- SQLite WAL Mode: https://www.sqlite.org/wal.html