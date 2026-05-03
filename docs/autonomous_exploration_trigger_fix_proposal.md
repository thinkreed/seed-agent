# 自主探索触发问题修复方案

> **文档类型**: 技术修复方案
> **创建日期**: 2026-05-03
> **作者**: Sisyphus (AI Agent)
> **状态**: 待评审实施

---

## 一、问题概述

用户报告在触发 seed-agent 的自主探索功能时遇到问题。经过代码分析，发现以下潜在问题点：

| 问题类别 | 具体表现 | 影响程度 |
|----------|----------|----------|
| **配置不一致** | 空闲超时值在代码与文档间不一致 | 中 |
| **状态管理冲突** | 自主探索直接修改 history，与 Session 事件流不兼容 | 高 |
| **上下文重置问题** | 重置后 prompt 可能丢失，导致 LLM 收到空消息 | 高 |
| **状态持久化碎片** | 每次实例化生成新状态文件，无法恢复 | 中 |
| **完成检测边界** | 完成标记检测可能存在竞态条件 | 低 |

---

## 二、问题详细分析

### 2.1 配置不一致问题

**现象**：空闲超时触发时机与用户预期不符。

**代码位置**：
- `src/autonomous.py` 第 60 行: `IDLE_TIMEOUT = 2 * 60 * 60` (2小时)
- `src/shared_config.py` 第 63 行: `idle_timeout_hours: int = 2`
- `src/AGENTS.md` 文档描述: 1小时或30分钟

**问题分析**：
代码与文档描述不一致，可能导致用户误判触发时机。实际上：
- `AutonomousExplorer.IDLE_TIMEOUT = 7200` 秒 = 2小时
- 监控间隔: 30秒检查一次
- 只有空闲达到2小时才会触发自主探索

**影响**：
- 用户可能在预期1小时后等待自主探索，但实际上需要2小时
- 或者反过来，用户预期2小时，但文档说1小时

---

### 2.2 状态管理冲突问题（核心问题）

**现象**：自主探索执行后，Session 事件流与 history 状态不一致。

**代码位置**：
- `src/autonomous.py` 第 287-316 行: `_execute_autonomous_task`
- `src/agent_loop.py` 第 644-646 行: `history` 属性定义

**问题代码片段**：

```python
# autonomous.py 第 287-316 行
async def _execute_autonomous_task(self):
    ...
    original_system_prompt = self.agent.system_prompt
    original_history = list(self.agent.history)  # 问题点1: 拷贝了兼容性接口
    ...
    try:
        self.agent.system_prompt = prompt
        self.agent.max_iterations = 100
        response = await self._run_ralph_loop()
        ...
    finally:
        self.agent.system_prompt = original_system_prompt
        self.agent.history = original_history  # 问题点2: 直接赋值
        self.agent.max_iterations = original_max_iterations
```

**问题分析**：

1. **AgentLoop.history 是兼容性接口**：
   ```python
   # agent_loop.py 第 644-646 行
   @property
   def history(self) -> list[dict[str, Any]]:
       """兼容性属性：从事件流构建消息列表"""
       return self.session.build_context_for_llm(system_prompt=None)
   ```
   
   - `history` 属性每次访问都会从 SessionEventStream 构建
   - 它不是可修改的属性，赋值操作无效
   - `self.agent.history = original_history` 实际上不会修改任何状态

2. **自主探索事件已记录到 Session**：
   - `_run_ralph_loop` 通过 `self.agent.run(next_prompt)` 执行
   - `AgentLoop.run` 会记录 USER_INPUT 和 LLM_RESPONSE 事件到 Session
   - 这些事件不会因为 finally 块的赋值而清除

3. **状态不一致后果**：
   - Session 包含自主探索的完整事件历史
   - 但代码试图恢复 `original_history`（实际无效）
   - 可能导致下次用户交互时上下文包含自主探索的内容

---

### 2.3 上下文重置问题

**现象**：上下文重置后，自主探索 prompt 可能丢失，导致 LLM 收到空消息或错误判断。

**代码位置**：`src/autonomous.py` 第 167-202 行

**问题代码片段**：

```python
# autonomous.py 第 167-202 行
async def _reset_context_if_needed(self) -> str | None:
    ...
    # 关键修复：保留自主探索的核心指令
    autonomous_prompt = self.agent.system_prompt or ""
    preserved_autonomous = self._extract_autonomous_prompt_core(autonomous_prompt)
    
    # 合并：自主探索指令 + 上次执行摘要
    preserved = f"{preserved_autonomous}\n\n---\n\n{history_context}"
    
    # 通过 Session 创建上下文重置标记
    self.agent.session.create_context_reset_marker(
        iteration=self._iteration_count,
        preserved_context=preserved
    )
```

**问题分析**：

1. **`create_context_reset_marker` 只创建事件**：
   - 该方法调用 `session.emit_event(EventType.CONTEXT_RESET, ...)`
   - 它不会实际清除任何状态
   - `build_context_for_llm` 需要正确处理此标记

2. **`build_context_for_llm` 处理逻辑**：
   ```python
   # session_event_stream.py 第 458-466 行
   elif event_type == EventType.CONTEXT_RESET.value:
       preserved = data.get("preserved_context")
       iteration = data.get("iteration", 0)
       if preserved:
           messages.append({
               "role": "system",
               "content": f"[迭代 {iteration} 状态摘要]\n{preserved}"
           })
   ```
   
   - 正确处理了 preserved_context
   - 但如果 `preserved_autonomous` 提取失败，可能导致空内容

3. **`_extract_autonomous_prompt_core` 的 fallback**：
   ```python
   # autonomous.py 第 238-239 行
   if core_parts:
       return "\n\n".join(core_parts)
   
   # 如果无法提取，返回 prompt 的前 2000 字符作为 fallback
   return full_prompt[:2000] if full_prompt else ""
   ```
   
   - 如果 `full_prompt` 为空，返回空字符串
   - 可能导致上下文重置后 LLM 收到空消息

---

### 2.4 状态持久化碎片问题

**现象**：每次 AutonomousExplorer 实例化生成新的状态文件，无法恢复之前的状态。

**代码位置**：`src/autonomous.py` 第 78-79 行

**问题代码**：

```python
self._instance_id: str = uuid.uuid4().hex[:8]
self._state_file: Path = SEED_DIR / "ralph" / f"autonomous_{self._instance_id}_state.json"
```

**问题分析**：

- `_instance_id` 使用随机 UUID
- 每次 `AutonomousExplorer.__init__` 都会生成新 ID
- 如果进程重启，无法找到之前的状态文件
- 导致无法恢复自主探索的迭代状态

---

### 2.5 完成检测边界问题

**现象**：`completion_promise` 文件检测可能存在竞态条件。

**代码位置**：`src/autonomous.py` 第 142-151 行

**问题代码**：

```python
def _check_completion_promise(self) -> bool:
    if COMPLETION_PROMISE_FILE.exists():
        content = COMPLETION_PROMISE_FILE.read_text().strip()
        if content in COMPLETION_PROMISE_TOKENS:
            COMPLETION_PROMISE_FILE.unlink()  # 清除标志
            return True
    return False
```

**问题分析**：

- 文件检查与删除是非原子操作
- 如果多个进程同时检查，可能产生竞态
- 但考虑到当前架构是单进程，风险较低

---

## 三、修复方案

### 3.1 方案概览

| 问题 | 修复方案 | 优先级 | 复杂度 |
|------|----------|--------|--------|
| 配置不一致 | 统一配置源，文档同步更新 | P1 | 低 |
| 状态管理冲突 | 重构自主探索使用 Session API | P0 | 高 |
| 上下文重置 | 增强 prompt 保留逻辑 | P1 | 中 |
| 状态持久化碎片 | 使用固定文件名 | P2 | 低 |
| 完成检测边界 | 添加原子操作保护 | P3 | 低 |

---

### 3.2 修复方案详细设计

#### 修复方案 1: 配置统一化

**修改文件**: `src/autonomous.py`, `src/AGENTS.md`, `auto/AGENTS.md`

**修改内容**：

1. **统一使用 shared_config.py 的配置**：

```python
# src/autonomous.py 修改建议
from src.shared_config import get_autonomous_config

class AutonomousExplorer:
    def __init__(self, agent_loop, ...):
        config = get_autonomous_config()
        self.IDLE_TIMEOUT = config.idle_timeout_hours * 60 * 60  # 从配置读取
        ...
```

2. **文档同步更新**：

```markdown
# src/AGENTS.md 更新内容
- **Idle Monitoring**: Tracks user activity and triggers exploration after 
  **2 hours** of inactivity (configurable via `AutonomousConfig.idle_timeout_hours`)
```

**验收标准**：
- 代码与文档描述一致
- 配置可通过 `shared_config.py` 覆盖

---

#### 修复方案 2: 状态管理重构（核心修复）

**修改文件**: `src/autonomous.py`

**设计原则**：
- 不直接修改 `AgentLoop.history`（这是兼容性接口）
- 使用 Session API 记录所有状态变更
- 通过 Session 标记机制管理上下文

**修改内容**：

```python
# src/autonomous.py 重构建议

async def _execute_autonomous_task(self):
    """执行自主探索任务（重构版）
    
    关键修改：
    1. 不保存/恢复 history（无效操作）
    2. 使用 Session 标记自主探索开始/结束
    3. 通过 Session 创建上下文边界
    """
    if not self._sop_content:
        logger.warning("No SOP loaded, skipping autonomous exploration")
        return None

    self._load_or_init_state()
    todo_content = self._load_todo_content()
    prompt = self._build_autonomous_prompt(todo_content, bool(todo_content))
    
    # === 新增：创建自主探索开始标记 ===
    self.agent.session.emit_event(EventType.SESSION_START, {
        "type": "autonomous_exploration",
        "iteration": self._iteration_count,
        "todo_status": bool(todo_content)
    })
    
    logger.info("Starting autonomous exploration via Agent Loop (Ralph enhanced)")

    # === 修改：只保存/恢复 system_prompt 和 max_iterations ===
    # 不再操作 history（无效操作）
    original_system_prompt = self.agent.system_prompt
    original_max_iterations = self.agent.max_iterations

    try:
        self.agent.system_prompt = prompt
        self.agent.max_iterations = 100
        response = await self._run_ralph_loop()

        if response:
            logger.info(f"Autonomous exploration completed, response length: {len(response)}")
            
            # === 新增：创建自主探索结束标记 ===
            self.agent.session.emit_event(EventType.SESSION_END, {
                "type": "autonomous_exploration",
                "reason": "completed",
                "response_length": len(response)
            })
            
            if self.on_explore_complete:
                if asyncio.iscoroutinefunction(self.on_explore_complete):
                    await self.on_explore_complete(response)
                else:
                    self.on_explore_complete(response)
            return response
        else:
            logger.warning("Autonomous exploration returned empty response")
            
            # 创建失败标记
            self.agent.session.emit_event(EventType.SESSION_END, {
                "type": "autonomous_exploration",
                "reason": "empty_response"
            })
            return None

    except Exception as e:
        logger.exception(f"Autonomous exploration failed: {e}")
        self._persist_state(str(e))
        
        # 创建错误标记
        self.agent.session.emit_event(EventType.ERROR_OCCURRED, {
            "error_type": "autonomous_exploration_failed",
            "error_message": str(e)[:500]
        })
        return None
        
    finally:
        self.agent.system_prompt = original_system_prompt
        self.agent.max_iterations = original_max_iterations
        # === 移除：不再恢复 history（无效操作） ===
```

**验收标准**：
- 自主探索状态通过 Session 正确记录
- 用户交互时上下文可正确区分自主探索事件
- Session 事件流完整包含自主探索历史

---

#### 修复方案 3: 上下文重置增强

**修改文件**: `src/autonomous.py`, `src/session_event_stream.py`

**修改内容**：

1. **增强 prompt 提取逻辑**：

```python
# src/autonomous.py 修改建议

def _extract_autonomous_prompt_core(self, full_prompt: str) -> str:
    """从完整自主探索 prompt 中提取核心指令部分（增强版）
    
    新增：
    1. 保提取到有效内容
    2. 如果提取失败，使用完整的 SOP 作为 fallback
    3. 始终包含任务指令
    """
    import re
    
    # 匹配 SOP 部分
    sop_match = re.search(
        r'(##?\s*自主探索\s*SOP.*?)(?=##?\s*|$)',
        full_prompt,
        re.DOTALL | re.IGNORECASE
    )
    sop_content = sop_match.group(1) if sop_match else ""
    
    # === 新增：如果提取失败，使用加载的 SOP ===
    if not sop_content and self._sop_content:
        sop_content = f"## 自主探索 SOP\n\n{self._sop_content}"
    
    # 匹配任务指令部分
    task_match = re.search(
        r'(#\s*自主探索任务触发.*?)(?=请开始执行|$)',
        full_prompt,
        re.DOTALL | re.IGNORECASE
    )
    task_content = task_match.group(1) if task_match else ""
    
    # === 新增：如果任务指令缺失，使用当前任务 ===
    if not task_content:
        todo_content = self._load_todo_content()
        has_todo = bool(todo_content)
        task_content = self._build_task_instruction(todo_content, has_todo)
    
    # 合并核心部分
    core_parts = []
    if sop_content:
        core_parts.append(sop_content.strip())
    if task_content:
        core_parts.append(task_content.strip())
    
    # === 修改：确保返回有效内容 ===
    if core_parts:
        return "\n\n".join(core_parts)
    
    # === 新增 fallback：使用已加载的 SOP 内容 ===
    if self._sop_content:
        return f"## 自主探索 SOP\n\n{self._sop_content}"
    
    # 最终 fallback：返回 prompt 的前 3000 字符（增加长度）
    return full_prompt[:3000] if full_prompt else "继续执行自主探索任务"
```

2. **Session 上下文构建增强**：

```python
# src/session_event_stream.py 修改建议

def build_context_for_llm(
    self,
    system_prompt: str | None = None,
    max_recent_events: int | None = None,
    exclude_event_types: list[EventType] | None = None  # 新增参数
) -> list[dict[str, Any]]:
    """从事件流构建 LLM 上下文（增强版）
    
    新增：
    - exclude_event_types: 可排除的事件类型（用于用户交互排除自主探索事件）
    """
    messages: list[dict[str, Any]] = []
    
    # ... 原有逻辑
    
    # === 新增：类型排除逻辑 ===
    if exclude_event_types:
        exclude_values = [t.value for t in exclude_event_types]
        recent_events = [e for e in recent_events if e["type"] not in exclude_values]
    
    # ... 后续逻辑
```

**验收标准**：
- 上下文重置后 prompt 始终有效
- 用户交互时可排除自主探索事件（可选）
- 无空消息传递给 LLM

---

#### 修复方案 4: 状态文件名固定化

**修改文件**: `src/autonomous.py`

**修改内容**：

```python
# src/autonomous.py 修改建议

class AutonomousExplorer:
    """自主探索执行器 (Ralph Loop 增强)"""
    
    # === 新增：使用固定文件名 ===
    STATE_FILE_NAME = "autonomous_state.json"  # 固定名称，不含实例ID
    
    def __init__(
        self,
        agent_loop: "AgentLoop",
        on_explore_complete: Callable | None = None
    ):
        self.agent = agent_loop
        self.on_explore_complete = on_explore_complete
        self._last_activity: float = time.time()
        self._running: bool = False
        self._task: asyncio.Task | None = None
        self._sop_content: str | None = None
        self._iteration_count: int = 0
        self._ralph_start_time: float = 0.0
        self._accumulated_duration: float = 0.0
        self._empty_response_count: int = 0
        
        # === 修改：使用固定文件名 ===
        self._state_file: Path = SEED_DIR / "ralph" / self.STATE_FILE_NAME
        self._load_sop()
```

**验收标准**：
- 进程重启后可恢复状态
- 状态文件唯一，无碎片化

---

#### 修复方案 5: 完成检测原子化

**修改文件**: `src/autonomous.py`

**修改内容**：

```python
# src/autonomous.py 修改建议

import threading

class AutonomousExplorer:
    """自主探索执行器 (Ralph Loop 增强)"""
    
    # === 新增：原子操作锁 ===
    _completion_check_lock = threading.Lock()
    
    def _check_completion_promise(self) -> bool:
        """检查外部完成标志（原子化版本）"""
        with self._completion_check_lock:  # 加锁
            if COMPLETION_PROMISE_FILE.exists():
                try:
                    content = COMPLETION_PROMISE_FILE.read_text().strip()
                    if content in COMPLETION_PROMISE_TOKENS:
                        logger.info(f"Completion promise detected: {content}")
                        COMPLETION_PROMISE_FILE.unlink()
                        return True
                except IOError as e:
                    logger.warning(f"Failed to read/delete completion promise: {e}")
        return False
```

**验收标准**：
- 多进程/多线程场景下无竞态
- 文件操作错误有容错处理

---

## 四、实施优先级与测试

### 4.1 实施顺序

```
Phase 1 (优先级 P0): 核心状态管理重构
├── 修复方案 2: 状态管理重构
├── 单元测试：Session 事件记录验证
└── 集成测试：自主探索 + 用户交互流程

Phase 2 (优先级 P1): 配置与上下文修复
├── 修复方案 1: 配置统一化
├── 修复方案 3: 上下文重置增强
└── 文档同步更新

Phase 3 (优先级 P2-P3): 边界问题修复
├── 修复方案 4: 状态文件名固定化
├── 修复方案 5: 完成检测原子化
└── 压力测试验证
```

### 4.2 测试用例设计

| 测试类别 | 用例 | 验证点 |
|----------|------|--------|
| **状态管理** | 自主探索后用户交互 | Session 正确记录两种事件 |
| **上下文边界** | 自主探索后重置上下文 | 用户消息不包含自主探索内容 |
| **配置一致性** | 检查 IDLE_TIMEOUT | 代码与文档一致 |
| **状态恢复** | 模拟进程崩溃重启 | 从固定文件恢复状态 |
| **原子操作** | 多线程完成检测 | 无竞态条件 |

### 4.3 测试代码示例

```python
# tests/test_autonomous_fix.py

import asyncio
import pytest
from pathlib import Path
from src.autonomous import AutonomousExplorer
from src.session_event_stream import EventType, SessionEventStream


async def test_autonomous_session_events():
    """测试：自主探索正确记录 Session 事件"""
    # 1. 创建测试 Agent
    agent = create_test_agent()
    explorer = AutonomousExplorer(agent)
    
    # 2. 执行自主探索
    await explorer._execute_autonomous_task()
    
    # 3. 验证 Session 事件
    events = agent.session.get_events()
    
    # 应包含自主探索开始标记
    start_events = [e for e in events if 
        e["type"] == EventType.SESSION_START.value and 
        e["data"].get("type") == "autonomous_exploration"]
    assert len(start_events) >= 1
    
    # 应包含自主探索结束标记
    end_events = [e for e in events if 
        e["type"] == EventType.SESSION_END.value and 
        e["data"].get("type") == "autonomous_exploration"]
    assert len(end_events) >= 1


async def test_autonomous_context_preservation():
    """测试：上下文重置后 prompt 保留"""
    agent = create_test_agent()
    explorer = AutonomousExplorer(agent)
    
    # 设置长 prompt
    original_prompt = agent.system_prompt
    assert len(original_prompt) > 1000
    
    # 模拟上下文重置
    preserved = await explorer._reset_context_if_needed()
    
    # 验证保留内容有效
    assert preserved is not None
    assert len(preserved) > 100
    assert "自主探索" in preserved or "SOP" in preserved


async def test_config_consistency():
    """测试：配置一致性"""
    from src.shared_config import get_autonomous_config
    
    config = get_autonomous_config()
    
    # 验证 IDLE_TIMEOUT 计算
    expected_timeout = config.idle_timeout_hours * 60 * 60
    assert AutonomousExplorer.IDLE_TIMEOUT == expected_timeout


async def test_state_file_fixed():
    """测试：状态文件名固定"""
    agent = create_test_agent()
    explorer1 = AutonomousExplorer(agent)
    explorer2 = AutonomousExplorer(agent)
    
    # 验证两个实例使用相同状态文件
    assert explorer1._state_file == explorer2._state_file
    assert explorer1._state_file.name == "autonomous_state.json"
```

---

## 五、风险评估

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| **Session API 不熟悉** | 实现错误 | 中 | 仔细阅读 session_event_stream.py |
| **上下文构建变化** | 用户消息丢失 | 低 | 增加排除参数，而非强制排除 |
| **配置迁移兼容性** | 用户配置失效 | 低 | 保持向后兼容，新增配置优先 |
| **状态文件冲突** | 多实例覆盖 | 低 | 单进程架构，风险可控 |

---

## 六、验收标准汇总

修复完成后，应满足以下所有条件：

1. **配置一致性**
   - [ ] `IDLE_TIMEOUT` 代码值与文档描述一致
   - [ ] 配置可通过 `shared_config.py` 覆盖

2. **状态管理正确性**
   - [ ] 自主探索开始/结束事件正确记录到 Session
   - [ ] 用户交互时 Session 包含完整历史
   - [ ] 不再使用无效的 `history` 赋值操作

3. **上下文完整性**
   - [ ] 上下文重置后 prompt 始终有效（非空）
   - [ ] LLM 不会收到空消息
   - [ ] 用户交互可选择性排除自主探索事件

4. **状态恢复能力**
   - [ ] 进程重启后可从固定文件恢复状态
   - [ ] 状态文件无碎片化

5. **原子操作**
   - [ ] 完成检测无竞态条件
   - [ ] 文件操作有错误容错

---

## 附录

### A. 相关文件清单

| 文件 | 修改内容 | 行数范围 |
|------|----------|----------|
| `src/autonomous.py` | 状态管理重构、配置统一、上下文增强、文件名固定、原子操作 | 全文件 |
| `src/session_event_stream.py` | 上下文构建增强（可选排除） | 第 421-494 行 |
| `src/AGENTS.md` | 文档同步（IDLE_TIMEOUT 描述） | AutonomousExplorer 章节 |
| `auto/AGENTS.md` | 文档同步（触发条件描述） | Trigger Conditions 章节 |
| `src/shared_config.py` | 配置验证（确保 AutonomousConfig 正确） | 第 61-66 行 |

### B. 不修改文件

| 文件 | 理由 |
|------|------|
| `src/agent_loop.py` | 作为底层引擎，history 属性设计已正确 |
| `core_principles/*` | 项目禁止修改原则文件 |
| `auto/自主探索 SOP.md` | SOP 内容无需修改，仅技术实现修复 |

---

> **评审建议**: 请在实施前确认以下问题：
> 1. 用户是否需要自主探索事件在用户交互时可见？
> 2. 状态恢复是否需要跨多日保持（当前设计为进程级）？
> 3. 配置的默认超时值（2小时）是否为最优值？