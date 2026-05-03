# 优化点 01: Session 不可变事件流架构

> **版本**: v1.0  
> **创建日期**: 2026-05-03  
> **优先级**: 高  
> **依赖**: 无  
> **参考来源**: Harness Engineering "宠物与牲畜基础设施哲学"

---

## 问题分析

### Harness Engineering 理念

**Session（会话）是宠物**:
- 精心培育、持久保存、不可丢失
- 核心接口只有两个：`emitEvent()` 记录事件、`getEvents()` 读取事件
- **只追加的日志**，天然支持重放和状态恢复
- 赋予智能体容错能力

### seed-agent 当前状态

**历史记录是可变的**:

```python
# 当前实现 (agent_loop.py)
class AgentLoop:
    self.history: list[dict] = []  # 可变列表
    
    # 摘要时截断历史
    async def _apply_summary(self, summary: str, is_context_full: bool):
        preserved = self.history[-keep_count:]
        self.history = [  # 完全替换，丢失历史
            {"role": "user", "content": f"[摘要]\n{summary}"}
        ] + preserved
        
    # 清空历史
    def clear_history(self, save_current: bool = True):
        self.history.clear()  # 历史丢失
```

**问题**:
- 历史可修改、可截断、可清空
- 无法重放至任意历史节点
- 进程崩溃后无法从精确状态恢复
- 缺乏审计追溯能力

---

## 设计方案

### 1. 核心概念: 只追加事件流

```
┌─────────────────────────────────────────────────────────────┐
│                    SessionEventStream                        │
│                                                              │
│    [Event 1] user_input: "帮我重构代码"                      │
│    [Event 2] llm_response: {"tool_calls": [...]             │
│    [Event 3] tool_result: "读取文件成功"                     │
│    [Event 4] summary_generated: "..."                       │
│    [Event 5] context_reset: preserved="..."                 │
│    ...                                                       │
│                                                              │
│    ↑ 只追加，不可修改                                        │
│    ↑ 支持从任意事件 ID 重放                                  │
│    ↑ 完整审计日志                                            │
└─────────────────────────────────────────────────────────────┘
```

### 2. 类设计

```python
class SessionEventStream:
    """不可变事件流 - 只追加日志"""
    
    def __init__(self, session_id: str, storage_path: Path):
        self.session_id = session_id
        self._storage_path = storage_path
        self._events: list[dict] = []
        self._event_counter: int = 0
        self._load_existing_events()
    
    # === 核心接口 (只两个) ===
    
    def emit_event(self, event_type: str, event_data: dict) -> int:
        """记录事件 - 只追加，不可修改
        
        Returns:
            int: 事件 ID (用于后续引用)
        """
        event_id = self._event_counter + 1
        event = {
            "id": event_id,
            "timestamp": time.time(),
            "type": event_type,
            "data": event_data
        }
        self._events.append(event)
        self._event_counter = event_id
        self._persist_event(event)
        return event_id
    
    def get_events(self, start_id: int = 0, end_id: int = None) -> list[dict]:
        """读取事件 - 支持范围查询
        
        Args:
            start_id: 起始事件 ID (默认 0 = 全部)
            end_id: 结束事件 ID (默认 None = 到最新)
        
        Returns:
            事件列表
        """
        if end_id is None:
            return self._events[start_id:]
        return self._events[start_id:end_id + 1]
    
    # === 恢复能力 ===
    
    def replay_to_state(self, target_event_id: int) -> dict:
        """重放事件到指定状态
        
        Args:
            target_event_id: 目标事件 ID
        
        Returns:
            dict: 重放后的状态摘要
        """
        state = {"messages": [], "context": {}}
        for event in self._events[:target_event_id + 1]:
            state = self._apply_event_to_state(state, event)
        return state
    
    def get_state_at_event(self, event_id: int) -> dict:
        """获取指定事件点的状态快照"""
        return self.replay_to_state(event_id)
    
    # === 摘要支持 (不修改原数据) ===
    
    def create_summary_marker(self, event_id: int, summary: str) -> int:
        """创建摘要标记 (不截断历史)
        
        Args:
            event_id: 摘要覆盖的事件范围终点
            summary: LLM 生成的摘要
        
        Returns:
            摘要事件 ID
        """
        return self.emit_event("summary_marker", {
            "covers_events": list(range(1, event_id + 1)),
            "summary": summary,
            "created_at": time.time()
        })
    
    # === 持久化 ===
    
    def _persist_event(self, event: dict) -> None:
        """持久化单个事件 (JSONL 格式)"""
        with open(self._storage_path / f"{self.session_id}.jsonl", "a") as f:
            f.write(json.dumps(event) + "\n")
    
    def _load_existing_events(self) -> None:
        """加载已存在的事件"""
        event_file = self._storage_path / f"{self.session_id}.jsonl"
        if event_file.exists():
            with open(event_file, "r") as f:
                for line in f:
                    event = json.loads(line)
                    self._events.append(event)
                    self._event_counter = event["id"]
```

### 3. 事件类型定义

```python
class EventType(Enum):
    """事件类型枚举"""
    
    # 对话事件
    USER_INPUT = "user_input"           # 用户输入
    LLM_RESPONSE = "llm_response"       # LLM 响应
    TOOL_CALL = "tool_call"             # 工具调用
    TOOL_RESULT = "tool_result"         # 工具结果
    
    # 上下文事件
    SUMMARY_GENERATED = "summary_generated"  # 摘要生成
    SUMMARY_MARKER = "summary_marker"        # 摘要标记 (不截断)
    CONTEXT_RESET = "context_reset"          # 上下文重置
    
    # 子代理事件
    SUBAGENT_SPAWN = "subagent_spawn"        # 子代理创建
    SUBAGENT_RESULT = "subagent_result"      # 子代理结果
    
    # 系统事件
    SESSION_START = "session_start"          # 会话开始
    SESSION_END = "session_end"              # 会话结束
    ERROR_OCCURRED = "error_occurred"        # 错误发生
    STATE_PERSISTED = "state_persisted"      # 状态持久化
```

### 4. 与 AgentLoop 集成

```python
class AgentLoopWithEventStream:
    """使用事件流的 AgentLoop"""
    
    def __init__(self, gateway: LLMGateway, session: SessionEventStream):
        self.gateway = gateway
        self.session = session  # 只读访问
        self._current_view: list[dict] = []  # 当前上下文视图
    
    async def run(self, user_input: str) -> str:
        """执行对话"""
        # 1. 记录用户输入
        event_id = self.session.emit_event("user_input", {"content": user_input})
        
        # 2. 构建上下文 (从事件流读取)
        context = self._build_context_from_session()
        
        # 3. 调用 LLM
        response = await self.gateway.chat_completion(context)
        
        # 4. 记录响应
        self.session.emit_event("llm_response", response)
        
        # 5. 执行工具调用
        if response.get("tool_calls"):
            for tc in response["tool_calls"]:
                self.session.emit_event("tool_call", tc)
                result = await self._execute_tool(tc)
                self.session.emit_event("tool_result", result)
        
        return response
    
    def _build_context_from_session(self) -> list[dict]:
        """从事件流构建上下文
        
        关键: 使用摘要标记而非截断历史
        """
        messages = []
        
        # 1. 找到最近的摘要标记
        last_summary = self._find_last_summary_marker()
        
        # 2. 添加摘要作为上下文
        if last_summary:
            messages.append({
                "role": "system",
                "content": f"[历史摘要]\n{last_summary['data']['summary']}"
            })
        
        # 3. 从摘要点后开始读取
        start_id = last_summary["id"] + 1 if last_summary else 0
        recent_events = self.session.get_events(start_id)
        
        # 4. 转换事件为消息
        for event in recent_events:
            if event["type"] in ["user_input", "llm_response", "tool_call", "tool_result"]:
                messages.append(self._event_to_message(event))
        
        return messages
    
    def _find_last_summary_marker(self) -> dict | None:
        """找到最近的摘要标记"""
        for event in reversed(self.session._events):
            if event["type"] == "summary_marker":
                return event
        return None
```

---

## 实施步骤

### Phase 1: 基础事件流 (3天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 1.1 | 实现 `SessionEventStream` 类 | 单元测试: emit/get/replay |
| 1.2 | 定义事件类型枚举 | 所有事件类型覆盖 |
| 1.3 | JSONL 持久化 | 文件写入/读取正常 |

### Phase 2: AgentLoop 集成 (2天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 2.1 | 改造 AgentLoop 使用事件流 | 对话流程不变 |
| 2.2 | 实现摘要标记机制 | 不截断历史 |
| 2.3 | 上下文构建适配 | 从事件流读取 |

### Phase 3: 恢复能力 (2天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 3.1 | 实现 `replay_to_state` | 可恢复到任意事件点 |
| 3.2 | 进程崩溃恢复测试 | 模拟崩溃后可恢复 |
| 3.3 | 状态快照机制 | 快照正确 |

---

## 预期收益

| 收益 | 描述 |
|------|------|
| **容错能力** | 进程崩溃后可从任意事件点恢复执行 |
| **可追溯性** | 完整操作历史，支持审计 |
| **重放能力** | 可重现任意执行状态，用于调试 |
| **摘要安全** | 摘要不丢失历史，只创建标记 |
| **Session 不可丢失** | 符合 "宠物" 哲学 |

---

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 存储空间增长 | 事件流无限增长 | 定期归档到 L5 冷存储 |
| 读取性能下降 | 大量事件时慢 | 实现事件索引 + 摘要跳跃 |
| 与现有历史管理冲突 | 接口变化 | 保持 backward compatibility |

---

## 测试计划

```python
# 单元测试
def test_event_stream_basic():
    stream = SessionEventStream("test_session", Path("/tmp/test"))
    
    # 测试追加
    id1 = stream.emit_event("user_input", {"content": "hello"})
    id2 = stream.emit_event("llm_response", {"content": "hi"})
    
    assert id1 == 1
    assert id2 == 2
    
    # 测试读取
    events = stream.get_events()
    assert len(events) == 2
    
    # 测试重放
    state = stream.replay_to_state(2)
    assert "messages" in state

def test_summary_marker():
    stream = SessionEventStream("test_summary", Path("/tmp/test"))
    
    # 创建一些事件
    for i in range(10):
        stream.emit_event("user_input", {"content": f"msg{i}"})
    
    # 创建摘要标记
    summary_id = stream.create_summary_marker(10, "用户说了10条消息")
    
    # 验证历史未被截断
    events = stream.get_events()
    assert len(events) == 11  # 10 input + 1 summary marker
```

---

## 相关文档

- [02_harness_sandbox_decoupling_design.md](02_harness_sandbox_decoupling_design.md) - 三件套解耦架构
- [05_lifecycle_hooks_design.md](05_lifecycle_hooks_design.md) - 生命周期钩子
- [harness_engineering_architecture_optimization_design.md](../harness_engineering_architecture_optimization_design.md) - 总体设计