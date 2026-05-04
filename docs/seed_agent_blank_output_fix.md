# Seed Agent 流式输出修复实施记录

> **状态**: ✅ 已实施 (2026-05-04)
> **方案**: 方案 A + 方案 B 组合实施

---

## 实施摘要

修复 `AgentLoop.stream_run()` 空白输出问题，实现真正的流式输出。

### 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `src/harness.py` | 重写 `stream_conversation()` 添加取消信号、Ask User、钩子支持；新增 `stream_resume_with_user_response()` |
| `src/agent_loop.py` | 重写 `stream_run()` 调用 `stream_conversation()` 实现真正流式输出 |
| `tests/test_harness.py` | 新增流式测试：取消信号、事件记录、用户响应恢复 |
| `tests/test_agent_loop.py` | 新增流式测试：chunk 转发、Ask User 处理、取消处理、错误处理 |

---

## 原问题分析

### 🔴 核心问题：`stream_run()` 未实现真正的流式输出

用户输入 "你好" 后，Agent 输出空白：
```
You: 你好
Agent:
--------------------------------------------------
You:
```

**根因**: `AgentLoop.stream_run()` 调用 `harness.run_conversation()` (非流式)，等待完整响应后才返回。

**执行链路对比**:

| 修复前（错误） | 修复后（正确） |
|---------------|---------------|
| `stream_run()` → `run_conversation()` (阻塞) | `stream_run()` → `stream_conversation()` (流式) |
| 只返回 `{"type": "final"}` | 返回 `{"type": "chunk"}` + `{"type": "final"}` |
| 用户等待完整响应后才看到输出 | 用户实时看到流式响应 |

---

## 实施细节

### 1. `Harness.stream_conversation()` 重写

**新增功能**:
- ✅ 取消信号支持 (`signal: AbortSignal | None = None`)
- ✅ Ask User 等待检测 (检查 `get_pending_ask_user_request()`)
- ✅ 生命周期钩子触发 (`SESSION_START`, `LLM_CALL_BEFORE/AFTER`, `RESPONSE_BEFORE/AFTER`, `SESSION_END`)
- ✅ 使用 `_route_tool_calls_with_hooks()` 替代 `_route_tool_calls()`

**新增方法**: `stream_resume_with_user_response()` 用于 Ask User 后恢复流式执行。

**Chunk 类型**:
- `{"type": "chunk", "content": "..."}` - 文本片段（实时）
- `{"type": "tool_start", "tool_name": "..."}` - 工具开始
- `{"type": "tool_end", "result": "..."}` - 工具结束
- `{"type": "awaiting_user_input", "request": {...}}` - 等待用户输入
- `{"type": "cancelled", "reason": "..."}` - 执行取消
- `{"type": "final", "content": "..."}` - 最终响应
- `{"type": "error", "content": "..."}` - 错误

### 2. `AgentLoop.stream_run()` 重写

**核心改进**:
- ✅ 直接调用 `harness.stream_conversation()` 获取真正流式 chunks
- ✅ 转发所有中间 chunks (`chunk`, `tool_start`, `tool_end`)
- ✅ Ask User 等待时阻塞，收到响应后调用 `stream_resume_with_user_response()` 恢复
- ✅ 取消信号检查每轮执行
- ✅ 摘要和 Skill Outcome 记录在 `final` 时触发

---

## 测试覆盖

### `test_harness.py` 新增测试

| 测试 | 覆盖内容 |
|------|---------|
| `test_stream_conversation_basic` | 基本流式输出验证 |
| `test_stream_conversation_chunk_types` | Chunk 类型验证 |
| `test_stream_conversation_with_signal` | 取消信号处理 |
| `test_stream_conversation_events_recorded` | 事件记录验证 |
| `test_stream_resume_with_user_response` | Ask User 恢复验证 |

### `test_agent_loop.py` 新增测试

| 测试 | 覆盖内容 |
|------|---------|
| `test_stream_run_basic` | 真正流式 chunks 转发 |
| `test_stream_run_with_ask_user` | Ask User 等待处理 |
| `test_stream_run_with_cancelled` | 取消处理 |
| `test_stream_run_with_error` | 错误处理 |

---

## 验证方法

### 步骤 1：运行单元测试

```bash
pytest tests/test_harness.py::TestHarnessStreamConversation -v
pytest tests/test_agent_loop.py::TestRunMethods::test_stream_run_basic -v
```

### 步骤 2：交互模式验证

```bash
python main.py
You: 你好
Agent: 你好！有什么我可以帮助你的吗？  # ← 应看到实时输出
```

---

## 设计决策

### 为什么选择方案 A + B 组合？

1. **方案 A** (修改 `stream_run()` 调用流式方法) 是必须的修复
2. **方案 B** (增强 `stream_conversation()`) 是必要的补充：
   - Ask User 机制是核心功能，流式执行必须支持
   - 取消信号是用户体验关键，需要中断能力
   - 生命周期钩子是确定性执行保障，不可缺失

### 为什么不选择方案 C (完整重构)？

方案 C 改动较大，风险高。方案 A + B 组合：
- 最小改动原则
- 利用现有架构
- 保持 API 兼容性

---

## 后续建议

1. **监控指标**: 添加流式输出的 OpenTelemetry metrics
2. **性能优化**: 考虑 chunk 缓冲优化大文本输出
3. **错误恢复**: 增强 Ask User 多次等待的处理逻辑

---

## 参考实现

其他框架流式模式（对比验证）:

| 框架 | 流式模式 |
|------|---------|
| LangChain | `agent.stream({"messages": [...]}, stream_mode="values")` |
| AutoGen | `async for message in agent.run_stream(task="...")` |
| Semantic Kernel | `async for response in agent.invoke_stream("...")` |

**关键模式**: 所有框架都使用 `async for` + 直接 yield chunks。

---

## 附录：原设计文档内容

> 以下内容为原设计分析，已实施完成，保留作为参考。

### 问题定位（文件级别）

### 问题 1：`AgentLoop.stream_run()` 调用错误方法

**文件**: `src/agent_loop.py`
**位置**: Line 593
**问题代码**:
```python
async def stream_run(self, user_input: str, ...) -> AsyncGenerator[dict, None]:
    # ...
    # ❌ 错误：调用非流式方法
    result = await self.harness.run_conversation(user_input, priority, signal)
    
    # ❌ 只 yield 单个 final chunk，无中间流式输出
    if result["status"] == "completed":
        yield {"type": "final", "content": result["content"]}
```

**影响**: 用户等待完整响应后才看到输出，无实时交互感。

### 问题 2：流式能力存在但未被使用

**文件**: `src/llm_client.py`
**位置**: Line 221-286
**存在代码**:
```python
async def stream_reason(self, context, tools=None, priority=None, **kwargs) -> AsyncGenerator:
    """流式推理 - 已实现但未被调用！"""
    async for chunk in self.gateway.stream_chat_completion(...):
        yield chunk  # ✅ 正确的流式实现
```

**文件**: `src/harness.py`
**位置**: Line 745-834
**存在代码**:
```python
async def stream_conversation(self, initial_prompt, priority) -> AsyncGenerator:
    """流式执行对话 - 已实现但未被调用！"""
    async for chunk in self.llm_client.stream_reason(context, tools):
        delta = chunk["choices"][0].get("delta", {})
        content = delta.get("content")
        if content:
            yield {"type": "chunk", "content": content}  # ✅ 正确的流式输出
```

**问题**: 这些流式方法已实现，但 `AgentLoop.stream_run()` 未调用它们。

### 问题 3：`main.py` chunk 处理分支永不执行

**文件**: `main.py`
**位置**: Line 376-377
**问题代码**:
```python
async for chunk in agent.stream_run(user_input):
    chunk_type = chunk.get("type")
    
    if chunk_type == "chunk":
        print(chunk["content"], end="", flush=True)  # ← 永远不执行！
    elif chunk_type == "final":
        print()  # ← 只有这个执行
```

**原因**: `stream_run()` 只返回 `"final"` 类型，从不返回 `"chunk"` 类型。

---

## 修复方案

### 方案 A：直接修改 `AgentLoop.stream_run()` 调用流式方法（推荐）

**修改文件**: `src/agent_loop.py`
**修改位置**: Line 566-664

**修复代码**:
```python
async def stream_run(
    self, user_input: str, priority: int = RequestPriority.CRITICAL
) -> AsyncGenerator[dict, None]:
    """流式执行对话（支持 Ask User 等待和取消）
    
    ✅ 使用 harness.stream_conversation() 实现真正的流式输出
    """
    self._conversation_rounds += 1
    
    # 重置取消信号
    self._abort_controller = AbortController()
    signal = self._abort_controller.signal
    
    # 设置当前任务（用于智能裁剪）
    self.harness.set_current_task(user_input)
    
    try:
        # ✅ 修复：调用流式方法而非非流式方法
        async for chunk in self.harness.stream_conversation(user_input, priority):
            # 检查取消信号
            if signal.aborted:
                yield {"type": "cancelled", "reason": signal.reason}
                return
            
            chunk_type = chunk.get("type")
            
            # 直接转发 harness 的流式 chunks
            if chunk_type == "chunk":
                yield chunk
            elif chunk_type == "tool_start":
                yield chunk
            elif chunk_type == "tool_end":
                yield chunk
            elif chunk_type == "final":
                await self._maybe_summarize()
                self._evaluate_and_record_skill_outcomes(final_success=True)
                yield chunk
            elif chunk_type == "error":
                yield chunk
        
    except MaxIterationsExceeded as e:
        logger.exception("Max iterations exceeded")
        self.session.record_session_end("max_iterations_exceeded")
        yield {"type": "error", "content": str(e)}
    except (RuntimeError, OSError, ValueError, asyncio.CancelledError) as e:
        logger.exception("Agent execution failed")
        self.session.record_session_end("error")
        yield {"type": "error", "content": str(e)}
```

**优点**:
- 最小改动，只需修改一个方法
- 利用已存在的 `harness.stream_conversation()`
- 保持 API 兼容性

**风险**:
- `harness.stream_conversation()` 未处理 Ask User 机制
- 需要额外添加 Ask User 支持

---

### 方案 B：增强 `harness.stream_conversation()` 支持 Ask User

**修改文件**: `src/harness.py`
**修改位置**: Line 745-834

**修复代码**:
```python
async def stream_conversation(
    self, 
    initial_prompt: str, 
    priority: int = RequestPriority.CRITICAL,
    signal: AbortSignal | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """流式执行对话（增强版：支持 Ask User 和取消）
    
    新增：
    - 取消信号检查
    - Ask User 等待机制
    - 钩子触发
    """
    # 1. 触发 session_start 钩子
    await self._trigger_hook(HookPoint.SESSION_START, {...})
    
    # 2. 记录初始输入
    self.session.emit_event(EventType.USER_INPUT, {"content": initial_prompt})
    
    iteration = 0
    while iteration < self.max_iterations:
        # 每轮检查取消信号
        if signal and signal.aborted:
            yield {"type": "cancelled", "reason": signal.reason}
            return
        
        iteration += 1
        
        # 构建上下文
        context = self._build_context_from_session()
        tools = self.sandbox.get_tool_schemas()
        
        # 流式推理
        full_content = ""
        tool_calls_accumulator: dict[int, dict] = {}
        
        async for chunk in self.llm_client.stream_reason(context, tools=tools, priority=priority):
            delta = chunk["choices"][0].get("delta", {})
            content = delta.get("content")
            if content:
                full_content += content
                yield {"type": "chunk", "content": content}
            
            tc_list = delta.get("tool_calls")
            if tc_list:
                self._process_tool_delta(tc_list, tool_calls_accumulator)
                for tc in tc_list:
                    if tc.get("function", {}).get("name"):
                        yield {"type": "tool_start", "tool_name": tc["function"]["name"]}
        
        # 累积工具调用
        tool_calls = [...]
        
        # 记录响应
        self.session.emit_event(EventType.LLM_RESPONSE, {...})
        
        # 执行工具或完成
        if tool_calls:
            # ✅ 检查 Ask User 等待
            pending_request = get_pending_ask_user_request()
            if pending_request:
                yield {"type": "awaiting_user_input", "request": pending_request.to_dict()}
                return  # 等待用户响应
            
            tool_results = await self._route_tool_calls_with_hooks(tool_calls)
            for result in tool_results:
                yield {"type": "tool_end", "result": result["content"]}
        else:
            await self._trigger_hook(HookPoint.SESSION_END, {...})
            self.session.record_session_end("completed")
            yield {"type": "final", "content": full_content}
            return
    
    raise MaxIterationsExceeded(iteration)
```

---

### 方案 C：完整重构（长期方案）

**涉及文件**:
- `src/agent_loop.py` - 重构 stream_run
- `src/harness.py` - 统一 run_conversation 和 stream_conversation
- `src/llm_client.py` - 保持不变（已正确实现）

**架构改进**:
```
AgentLoop
├── run()           → 调用 harness.run() (非流式)
└── stream_run()    → 调用 harness.stream() (流式)

Harness
├── run()           → 内部调用 _execute_cycle (非流式迭代)
├── stream()        → 内部调用 _stream_cycle (流式迭代)
└── _execute_cycle()
└── _stream_cycle() → 统一的流式/非流式核心逻辑
```

**优点**: 清晰的流式/非流式分离，易于维护。

**缺点**: 改动较大，需要更多测试。

---

## 快速验证修复

### 步骤 1：验证 LLM API 正常工作

在 `src/harness.py` line 335 后添加调试日志：
```python
response = await self.llm_client.reason(context, tools=tools, priority=priority)
print(f"DEBUG LLM response: {response}")  # ← 添加
```

运行：
```bash
python main.py --chat "hello"
```

如果输出正常，说明 LLM API 正常工作。

### 步骤 2：验证流式方法工作

在 `src/harness.py` line 777 后添加调试：
```python
async for chunk in self.llm_client.stream_reason(context, tools=tools, priority=priority):
    delta = chunk["choices"][0].get("delta", {})
    print(f"DEBUG stream chunk: {delta}")  # ← 添加
    content = delta.get("content")
    if content:
        yield {"type": "chunk", "content": content}
```

### 步骤 3：验证修复后效果

应用方案 A 后，运行交互模式：
```bash
python main.py
You: 你好
Agent: 你好！有什么我可以帮助你的吗？  # ← 应看到实时输出
```

---

## 其他可能问题

### 问题 A：LLM API Key 配置错误

**检查文件**: `~/.seed/config.json`
**检查内容**:
```json
{
  "models": {
    "bailian": {
      "baseUrl": "https://coding.dashscope.aliyuncs.com/v1",
      "apiKey": "${BAILIAN_API_KEY}",  // ← 确保环境变量已设置
      "models": [...]
    }
  }
}
```

**验证**:
```bash
echo $BAILIAN_API_KEY  # Linux/Mac
echo %BAILIAN_API_KEY%  # Windows
```

### 问题 B：中文编码问题

**检查文件**: `src/session_event_stream.py`
**关键代码** (line 429-430):
```python
encoding="utf-8"
ensure_ascii=False  # ← 确保中文正确保存
```

**已正确处理**，无需修改。

### 问题 C：Rate Limit 阻塞

**检查文件**: `src/client.py`
**关键代码** (line 794-801):
```python
if self._rate_limiter:
    max_wait = 0.0 if priority == RequestPriority.CRITICAL else 60.0
    acquired = await self._rate_limiter.wait_and_acquire(max_wait=max_wait)
    if not acquired:
        raise RateLimitTimeoutError(...)
```

**诊断**: 检查日志是否有 Rate Limit 错误：
```bash
cat ~/.seed/logs/seed_agent_*.log | grep -i "rate limit"
```

---

## 参考实现（其他框架）

### LangChain 流式模式
```python
for chunk in agent.stream({"messages": [...]}, stream_mode="values"):
    latest_message = chunk["messages"][-1]
    if latest_message.content:
        print(latest_message.content)
```

### AutoGen 流式模式
```python
async for message in agent.run_stream(task="Your task"):
    print(message)
```

### Semantic Kernel 流式模式
```python
async for response in agent.invoke_stream("Your question"):
    print(response.content)
```

**关键模式**: 所有框架都使用 `async for` + 直接 yield chunks，而非等待完整响应。

---

## 总结

| 问题 | 根因 | 修复方案 |
|------|------|---------|
| 空白输出 | `stream_run()` 使用非流式方法 | 调用 `harness.stream_conversation()` |
| 无实时交互 | 只返回 final chunk | 转发中间 chunks |
| 流式能力闲置 | `LLMClient.stream_reason()` 未被使用 | 在 harness.stream 中调用 |

**推荐修复**: 方案 A - 修改 `agent_loop.py` 的 `stream_run()` 调用 `harness.stream_conversation()`。

**预期效果**: 用户输入后立即看到流式输出，而非等待完整响应后空白显示。

---

## 文件修改清单

| 文件 | 修改类型 | 优先级 |
|------|---------|--------|
| `src/agent_loop.py` | 修改 `stream_run()` | P0 必须 |
| `src/harness.py` | 增强 `stream_conversation()` 支持 Ask User | P1 推荐 |
| `main.py` | 无需修改（已正确处理 chunks） | - |
| `src/llm_client.py` | 无需修改（已正确实现） | - |

---

## 附录：关键代码位置索引

| 功能 | 文件 | 行号 |
|------|------|------|
| Interactive loop | main.py | 331-421 |
| stream_run (问题所在) | agent_loop.py | 566-664 |
| stream_conversation (正确实现) | harness.py | 745-834 |
| stream_reason (正确实现) | llm_client.py | 221-286 |
| stream_chat_completion | client.py | 925-955 |
| chunk 处理 | main.py | 376-395 |