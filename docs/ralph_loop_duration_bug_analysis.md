# Ralph Loop 超时与空响应问题分析

## 问题现象

系统日志中出现重复的警告信息：

```
2026-04-22 10:56:24,140 | WARNING | Ralph Loop exceeded max duration (28800s)
2026-04-22 10:56:24,140 | WARNING | Autonomous exploration returned empty response
2026-04-22 11:26:24,608 | WARNING | Ralph Loop exceeded max duration (28800s)
2026-04-22 11:26:24,608 | WARNING | Autonomous exploration returned empty response
...
```

**关键观察**：
- 每 30 分钟重复出现（10:56 → 11:26 → 11:56 → 12:26 → 12:56）
- 两条警告同时出现
- 时间间隔精确匹配 `IDLE_TIMEOUT = 30 * 60` 秒

---

## 根本原因

### 状态恢复 Bug

**核心问题**：`AutonomousExplorer` 在恢复状态时，保留了**原始的开始时间戳**，而非正确计算已消耗时间。

**执行流程分析**：

```
每 30 分钟空闲触发时：
1. _idle_monitor_loop() 触发 _execute_autonomous_task()
2. _load_or_init_state() 加载 ~/.seed/ralph_state.json
3. 【BUG】恢复 _ralph_start_time 为原始时间戳（可能是 8+ 小时前）
4. _check_safety_limits() 计算 elapsed = time.time() - start_time
5. elapsed >= 28800s → 循环立即退出（iteration_count = 0）
6. response 保持为 None（未执行任何工作）
7. 记录警告："Autonomous exploration returned empty response"
```

**Bug 代码位置**（`src/autonomous.py` 第 195-208 行）：

```python
def _load_or_init_state(self):
    """加载或初始化状态（支持进程恢复）"""
    if self._state_file.exists():
        try:
            state = json.loads(self._state_file.read_text())
            self._iteration_count = state.get("iteration", 0)
            # BUG: 使用原始 start_time，未调整！
            self._ralph_start_time = state.get("start_time", time.time())
            logger.info(f"Resumed Ralph Loop from iteration {self._iteration_count}")
        except (json.JSONDecodeError, KeyError):
            self._iteration_count = 0
            self._ralph_start_time = time.time()
    else:
        self._iteration_count = 0
        self._ralph_start_time = time.time()
```

**同样的问题存在于** `src/ralph_loop.py` 第 345-359 行。

### 为什么会保留原始时间戳？

状态持久化时保存了 `start_time`（第 189 行）：

```python
state = {
    "iteration": self._iteration_count,
    "start_time": self._ralph_start_time,  # 保存的是原始时间戳
    ...
}
```

恢复时直接读取此时间戳，导致：

- 如果首次运行在 10 小时前，状态文件记录 `start_time = 10小时前的时间戳`
- 恢复后 `elapsed = time.time() - start_time` 可能达到 10+ 小时
- 立即超过 `max_duration = 28800s`（8 小时），循环退出

---

## 问题时间线示例

```
时间点           事件
────────────────────────────────────────────────────────
T+0h            Ralph Loop 开始，start_time = T+0h
T+7h            进程崩溃/重启，状态保存：start_time = T+0h
T+8h (恢复)     加载状态：start_time = T+0h
                elapsed = (T+8h) - (T+0h) = 8h >= max_duration
                → 立即退出，response = None
T+8h+30min      下次空闲触发，重复同样问题...
```

---

## 解决方案

### 方案一：跟踪累计执行时间（推荐）

**原理**：正确跟踪实际执行时间，而非墙钟时间。

**修改 `src/autonomous.py`**：

```python
# 1. 添加累计时间属性
class AutonomousExplorer:
    def __init__(self, ...):
        ...
        self._accumulated_duration: float = 0  # 新增

# 2. 状态持久化时保存累计时间
def _persist_state(self, response: str = ""):
    """持久化当前状态"""
    current_elapsed = time.time() - self._ralph_start_time
    state = {
        "iteration": self._iteration_count,
        "accumulated_duration": self._accumulated_duration + current_elapsed,  # 新增
        "last_response": response[:500] if response else "",
        "timestamp": time.time()
    }
    self._state_file.write_text(json.dumps(state, indent=2))

# 3. 状态恢复时正确处理
def _load_or_init_state(self):
    """加载或初始化状态"""
    if self._state_file.exists():
        try:
            state = json.loads(self._state_file.read_text())
            self._iteration_count = state.get("iteration", 0)
            self._accumulated_duration = state.get("accumulated_duration", 0)  # 新增
            # FIX: 重置 start_time 为当前时间
            self._ralph_start_time = time.time()
            logger.info(f"Resumed Ralph Loop from iteration {self._iteration_count}, "
                       f"accumulated: {self._accumulated_duration}s")
        except (json.JSONDecodeError, KeyError):
            self._iteration_count = 0
            self._ralph_start_time = time.time()
            self._accumulated_duration = 0
    else:
        self._iteration_count = 0
        self._ralph_start_time = time.time()
        self._accumulated_duration = 0

# 4. 安全检查使用累计 + 当前时间
def _check_safety_limits(self) -> bool:
    """检查安全上限"""
    if self._iteration_count >= RALPH_MAX_ITERATIONS:
        logger.warning(f"Ralph Loop exceeded max iterations ({RALPH_MAX_ITERATIONS})")
        return True
    
    current_elapsed = time.time() - self._ralph_start_time
    total_elapsed = self._accumulated_duration + current_elapsed
    
    if total_elapsed >= RALPH_MAX_DURATION:
        logger.warning(f"Ralph Loop exceeded max duration ({RALPH_MAX_DURATION}s, "
                      f"total: {total_elapsed}s)")
        return True
    return False
```

**优点**：
- 正确跟踪跨会话的累计执行时间
- 支持进程崩溃恢复后继续执行
- 保持设计意图（8 小时执行上限）

**缺点**：
- 需要新增属性和修改多处逻辑

---

### 方案二：恢复时重置开始时间（简单）

**原理**：每次探索会话视为全新开始。

**修改 `src/autonomous.py`**：

```python
def _load_or_init_state(self):
    """加载或初始化状态"""
    if self._state_file.exists():
        try:
            state = json.loads(self._state_file.read_text())
            self._iteration_count = state.get("iteration", 0)
            # FIX: 恢复时总是重置 start_time
            self._ralph_start_time = time.time()
            logger.info(f"Resumed Ralph Loop from iteration {self._iteration_count}")
        except (json.JSONDecodeError, KeyError):
            self._iteration_count = 0
            self._ralph_start_time = time.time()
    else:
        self._iteration_count = 0
        self._ralph_start_time = time.time()
```

**优点**：
- 改动最小，一处修改即可
- 不引入新的状态跟踪

**缺点**：
- 失去跨会话的时间跟踪
- 可能允许无限执行（每次都重置为 0）

---

### 方案三：清理过期状态文件

**原理**：在开始新探索前清理过期状态，防止旧状态影响新会话。

**修改 `src/autonomous.py`**：

```python
async def _execute_autonomous_task(self):
    """执行自主探索任务"""
    # 在加载状态前，清理过期状态文件
    if self._state_file.exists():
        try:
            state = json.loads(self._state_file.read_text())
            state_age = time.time() - state.get("timestamp", time.time())
            # 状态文件超过 max_duration 就清理
            if state_age > RALPH_MAX_DURATION:
                logger.info(f"Clearing stale state file (age: {state_age}s)")
                self._cleanup_state()
        except (json.JSONDecodeError, KeyError):
            self._cleanup_state()
    
    self._load_or_init_state()
    ...
```

**优点**：
- 改动小
- 防止过期状态污染新会话

**缺点**：
- 不解决根本问题（只是规避）
- 可能丢失有效状态（进程刚崩溃时）

---

## 需修改的文件

| 文件 | 行号 | 修改内容 |
|------|------|----------|
| `src/autonomous.py` | 57-67, 184-193, 195-208, 132-146 | 添加累计时间跟踪，修复状态恢复 |
| `src/ralph_loop.py` | 361-371, 345-359, 375-388 | 同样修复（独立 RalphLoop 使用场景） |

---

## 其他发现的问题

### 1. 任务完成检测依赖中文短语

**位置**：`src/autonomous.py` 第 281 行

```python
if response and ("任务完成" in response or "已完成" in response):
```

**问题**：如果模型使用英文或其他表述（如 "done"、"complete"、"finished"），无法识别为完成。

**建议**：扩展检测模式：

```python
COMPLETION_MARKERS = ["任务完成", "已完成", "DONE", "COMPLETE", "FINISHED", "done", "complete"]

if response and any(marker in response for marker in COMPLETION_MARKERS):
```

### 2. 空响应处理不完整

**位置**：`src/autonomous.py` 第 286-290 行

```python
if not response:
    logger.warning(f"Empty response at iteration {self._iteration_count}, re-injecting prompt")
    self.agent.history.append({"role": "user", "content": prompt})
```

**问题**：重新注入 prompt 后没有改变策略，可能导致无限重复空响应。

**建议**：添加失败计数和策略切换：

```python
if not response:
    self._empty_response_count += 1
    if self._empty_response_count >= 3:
        logger.warning("Too many empty responses, trying simplified prompt")
        self.agent.history.append({"role": "user", "content": "请报告当前状态"})
    else:
        self.agent.history.append({"role": "user", "content": prompt})
```

### 3. SOP 文件依赖无提示

**位置**：`src/autonomous.py` 第 217-219 行

```python
if not self._sop_content:
    logger.warning("No SOP loaded, skipping autonomous exploration")
    return
```

**问题**：如果 `auto/自主探索 SOP.md` 不存在，探索会静默跳过，用户看不到提示。

**建议**：在启动时检查并发出明确警告：

```python
async def start(self):
    if not self._sop_content:
        logger.error("SOP file not found: auto/自主探索 SOP.md - autonomous exploration disabled")
        return
    ...
```

---

## 修复优先级

| 优先级 | 解决方案 | 工作量 | 影响 |
|--------|----------|--------|------|
| **P0（关键）** | 方案一或方案三 | 中等 | 修复核心 Bug |
| **P1** | 扩展任务完成检测模式 | 低 | 提升任务完成可靠性 |
| **P2** | 添加空响应策略切换 | 低 | 更好的错误恢复 |
| **P3** | SOP 文件检查提示 | 低 | 用户体验改进 |

---

## 测试建议

修复后需验证：

1. **状态恢复测试**：
   - 启动 Ralph Loop，运行 1 小时后模拟崩溃
   - 恢复后检查是否正确计算累计时间
   - 验证不会因过期时间立即退出

2. **长时间运行测试**：
   - 连续运行超过 8 小时（模拟跨会话）
   - 验证累计时间正确累加
   - 验证达到上限时正确退出

3. **空响应恢复测试**：
   - 模拟空响应场景
   - 验证重新注入 prompt 后能恢复执行

---

## 相关文档

- [Ralph Loop 增强设计](long_cycle_loop_enhancement_design.md)
- [Ralph Loop 概念文档](ralph_loop.md)
- [核心引擎文档](../src/AGENTS.md)