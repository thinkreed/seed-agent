# Seed Agent 显示问题修复方案

**问题分析日期**: 2026-05-06

**实施状态**: ✅ 已完成 (2026-05-06)

**问题描述**: 用户报告 seed agent 运行时存在两个显示问题：
1. 运行过程中不展示思考过程（thinking/thought blocks）
2. 日志显示 `Unknown hook point: RESPONSE_AFTER` 警告

---

## 问题一：思考过程不展示

### 问题分析

#### 当前实现分析

通过代码审查，发现思考过程不展示的根本原因：

**流式响应处理链路**：

```
LLMClient.stream_reason() → LLMGateway._stream_internal() → Harness._streaming_executor.execute_iteration() → main.py interactive_loop()
```

**关键文件分析**：

| 文件 | 问题 |
|------|------|
| `src/llm_client/_client.py` | 只处理标准 `content` 字段，无 thinking 处理 |
| `src/harness/_streaming_executor.py` | `delta.get("content")` 仅提取文本内容 |
| `src/harness/_streaming_types.py` | `StreamChunkType` 无 thinking 类型定义 |
| `main.py` (line 393-395) | 只处理 `chunk["content"]`，无 thinking 输出逻辑 |

**代码片段** (`src/harness/_streaming_executor.py` lines 98-102):
```python
# 处理文本内容
content = delta.get("content")
if content:
    full_content += content
    yield {"type": StreamChunkType.CHUNK, "content": content}
```

**问题根因**：
- 当前代码只处理 OpenAI 标准 API 的 `content` 字段
- 未处理扩展思考（Extended Thinking）模型的特殊响应格式
- 缺少对 `thinking` / `reasoning_content` 字段的识别和流式输出

#### 模型思考格式分析

不同 LLM Provider 返回思考内容的方式不同：

| Provider | 思考字段 | 格式 |
|----------|----------|------|
| Anthropic Claude | `thinking` | `{ "thinking": "...", "content": "..." }` |
| OpenAI o-series | `reasoning_content` | `{ "reasoning_content": "...", "content": "..." }` |
| Qwen (百炼) | 可能在 `content` 中嵌入 `\u003cthinking\u003e` 标签 | 混合格式 |
| DeepSeek R1 | `content` 前段为思考，后段为回答 | 需解析分隔 |

**当前百炼配置** (`config.json`):
```json
{
  "bailian": {
    "baseUrl": "https://coding.dashscope.aliyuncs.com/v1",
    "apiKey": "${BAILIAN_API_KEY}",
    "models": [{"id": "qwen-coder-plus", ...}]
  }
}
```

百炼 Qwen 模型的思考内容可能以以下形式返回：
1. **单独字段**: `delta.thinking` 或 `delta.reasoning_content`
2. **嵌入标签**: `content` 中包含 `<thinking>` 或 `【思考】` 标签
3. **前缀区分**: 思考内容在正式回答之前，无明确分隔

### 修复方案

#### 方案概述

采用三层处理策略：

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: LLMClient - 原始响应识别                           │
│   - 识别 thinking/reasoning_content 字段                    │
│   - 解析嵌入标签格式                                         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: StreamingExecutor - 流式输出类型分类               │
│   - 新增 StreamChunkType.THINKING                           │
│   - 区分思考块与内容块                                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: main.py - 前端显示控制                             │
│   - 思考内容显示样式（可配置：隐藏/简化/完整）               │
│   - 颜色/格式区分                                           │
└─────────────────────────────────────────────────────────────┘
```

#### Layer 1: LLMClient 响应识别

**文件**: `src/llm_client/_streaming.py` 或 `src/client/_streaming.py`

**新增逻辑**:
```python
# 伪代码示例 - 实际修改需要测试验证
async def stream_chat_completion_single(...):
    async for chunk in client.chat.completions.create(..., stream=True):
        delta = chunk.choices[0].delta
        
        # 1. 识别思考字段
        thinking_content = None
        if hasattr(delta, 'thinking') and delta.thinking:
            thinking_content = delta.thinking
        elif hasattr(delta, 'reasoning_content') and delta.reasoning_content:
            thinking_content = delta.reasoning_content
        
        # 2. 解析嵌入标签（可选，根据模型特性）
        content = delta.content or ""
        if "<thinking>" in content or "【思考】" in content:
            # 解析并分离思考与回答
            thinking_content, content = parse_embedded_thinking(content)
        
        # 返回结构化 chunk
        if thinking_content:
            yield {"type": "thinking", "content": thinking_content}
        if content:
            yield {"type": "content", "content": content}
```

#### Layer 2: StreamingExecutor 类型扩展

**文件**: `src/harness/_streaming_types.py`

**新增类型**:
```python
class StreamChunkType:
    """流式 chunk 类型常量"""
    
    THINKING = "thinking"  # 新增：思考过程片段
    CHUNK = "chunk"        # 文本片段（原有）
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    AWAITING_USER_INPUT = "awaiting_user_input"
    CANCELLED = "cancelled"
    FINAL = "final"
    ERROR = "error"
```

**文件**: `src/harness/_streaming_executor.py`

**修改 `execute_iteration()` 函数**:
```python
async def execute_iteration(...):
    # ... existing code ...
    
    async for chunk in llm_client.stream_reason(context, tools=tools, priority=priority):
        choices = chunk.get("choices", [])
        if not choices:
            continue
        delta = choices[0].get("delta", {})
        
        # 新增：处理思考内容
        thinking = delta.get("thinking") or delta.get("reasoning_content")
        if thinking:
            yield {"type": StreamChunkType.THINKING, "content": thinking}
        
        # 处理文本内容（原有）
        content = delta.get("content")
        if content:
            # 如果 content 中嵌入思考标签，先解析
            parsed_thinking, parsed_content = parse_embedded_thinking(content)
            if parsed_thinking:
                yield {"type": StreamChunkType.THINKING, "content": parsed_thinking}
            if parsed_content:
                yield {"type": StreamChunkType.CHUNK, "content": parsed_content}
        
        # ... tool calls handling ...
```

#### Layer 3: main.py 显示控制

**文件**: `main.py` (interactive_loop 函数)

**新增处理逻辑**:
```python
async def interactive_loop(agent: AgentLoop, explorer: AutonomousExplorer) -> None:
    # 新增配置项（可从 config.json 读取）
    SHOW_THINKING = True  # 或 os.getenv("SHOW_THINKING", "true").lower() == "true"
    THINKING_DISPLAY_MODE = "compact"  # modes: "hidden", "compact", "full"
    
    # ... existing code ...
    
    async for chunk in agent.stream_run(user_input):
        chunk_type = chunk.get("type")
        
        # 新增：思考过程显示
        if chunk_type == "thinking":
            if SHOW_THINKING:
                if THINKING_DISPLAY_MODE == "hidden":
                    pass  # 不显示
                elif THINKING_DISPLAY_MODE == "compact":
                    # 简化显示：仅显示进度指示
                    print("💭", end="", flush=True)
                elif THINKING_DISPLAY_MODE == "full":
                    # 完整显示思考内容（灰色文字）
                    # ANSI 灰色: \033[90m
                    print(f"\033[90m{chunk['content']}\033[0m", end="", flush=True)
        
        elif chunk_type == "chunk":
            # 原有处理
            print(chunk["content"], end="", flush=True)
        
        # ... existing handlers for tool_start, tool_end, etc. ...
```

#### 配置文件扩展

**文件**: `config.json` 或新增 `~/.seed/display_config.json`

```json
{
  "display": {
    "show_thinking": true,
    "thinking_mode": "compact",
    "thinking_color": "gray",
    "thinking_prefix": "💭"
  }
}
```

### 测试验证方案

#### 测试场景

1. **Qwen 模型思考输出测试**
   - 使用 `qwen-coder-plus` 发起需要推理的任务
   - 验证思考内容是否被正确识别和显示

2. **其他模型兼容性测试**
   - 测试 DeepSeek R1（思考内容嵌入 content）
   - 测试 Claude（独立 thinking 字段）

3. **显示模式切换测试**
   - `hidden`: 思考内容完全不显示
   - `compact`: 仅显示进度指示符
   - `full`: 完整显示思考内容（灰色文字）

#### 验证命令

```bash
# 启动 agent 并观察思考显示
python main.py

# You: 分析这段代码的性能问题
# Agent: 💭💭💭 [思考过程指示]
#        根据分析，这段代码存在...
```

---

## 问题二：Unknown hook point: RESPONSE_AFTER

### 问题分析

#### 警告触发位置

**文件**: `src/lifecycle_hooks/_async_trigger.py` (line 52-53)

```python
point_value = (
    hook_point.value if isinstance(hook_point, HookPoint) else hook_point
)

if point_value not in self._hooks:
    logger.warning(f"Unknown hook point: {point_value}")
```

#### Hook 注册机制分析

**文件**: `src/lifecycle_hooks/_registry.py` (line 53-55)

```python
self._hooks: dict[str, list[tuple[int, Any, str]]] = {
    point.value: [] for point in HookPoint
}
```

**HookPoint 枚举值** (`src/lifecycle_hooks/_types.py` line 38):
```python
RESPONSE_AFTER = "response_after"  # 注意：值是小写
```

#### 问题根因

**大小写不一致**：

| 调用方式 | 实际值 | 是否匹配 `_hooks` key |
|----------|--------|----------------------|
| `HookPoint.RESPONSE_AFTER` | `"response_after"` | ✓ 匹配 |
| `"RESPONSE_AFTER"` (字符串) | `"RESPONSE_AFTER"` | ✗ 不匹配（大小写不一致） |
| `"response_after"` (字符串) | `"response_after"` | ✓ 匹配 |

**警告日志显示**: `"Unknown hook point: RESPONSE_AFTER"` 表明调用者传入的是 **大写字符串** `"RESPONSE_AFTER"`，而非正确的枚举值或小写字符串。

#### 确认的 Bug 位置（已定位）

通过代码探索，确认以下位置存在错误的字符串调用：

**Bug 1: `src/harness/_cycle_executor.py` 第 150 行**
```python
# 当前代码（错误）
await trigger_hook(
    hook_registry,
    "RESPONSE_AFTER",  # ← 错误：使用大写字符串
    build_response_after_ctx(session, harness_ref, response, False),
)

# 应修改为
from src.lifecycle_hooks import HookPoint
await trigger_hook(
    hook_registry,
    HookPoint.RESPONSE_AFTER,  # ← 正确：使用枚举值
    build_response_after_ctx(session, harness_ref, response, False),
)
```

**Bug 2: `src/harness/_streaming_loop.py` 第 104 行**
```python
# 当前代码（错误）
await trigger_hook(hook_registry, "SESSION_END",  # ← 错误：使用大写字符串
    build_session_end_ctx(session, harness_ref, "error", error=str(e))
)

# 应修改为
await trigger_hook(hook_registry, HookPoint.SESSION_END,  # ← 正确：使用枚举值
    build_session_end_ctx(session, harness_ref, "error", error=str(e))
)
```

#### 对比：正确用法示例

大多数其他位置正确使用了 `HookPoint` 枚举：
```python
# src/agent_loop/_execution.py - 正确用法
await trigger_hook(hook_registry, HookPoint.SESSION_START, ...)

# src/harness/_streaming_executor.py - 正确用法
await trigger_hook(hook_registry, HookPoint.LLM_CALL_BEFORE, ...)
```

### 修复方案

#### 方案一：直接修复 Bug（推荐）

**修改文件**：
- `src/harness/_cycle_executor.py` 第 150 行
- `src/harness/_streaming_loop.py` 第 104 行

**具体修改**：
```python
# 步骤 1：确保导入 HookPoint
from src.lifecycle_hooks import HookPoint

# 步骤 2：替换字符串为枚举
"RESPONSE_AFTER" → HookPoint.RESPONSE_AFTER
"SESSION_END" → HookPoint.SESSION_END
```

#### 方案二：增强 trigger 方法容错

**文件**: `src/lifecycle_hooks/_async_trigger.py`

**修改 trigger 方法**，添加大小写自动转换：

```python
async def trigger(
    self,
    hook_point: HookPoint | str,
    context: dict[str, Any],
    fail_fast: bool = False,
) -> HookTriggerReport:
    """触发钩子"""
    point_value = (
        hook_point.value if isinstance(hook_point, HookPoint) else hook_point
    )
    
    # 新增：尝试大小写转换容错
    if point_value not in self._hooks:
        # 尝试转换为小写（HookPoint 枚举值均为小写）
        lower_point = point_value.lower()
        if lower_point in self._hooks:
            logger.warning(
                f"Hook point '{point_value}' auto-corrected to '{lower_point}'"
            )
            point_value = lower_point
        else:
            logger.warning(f"Unknown hook point: {point_value}")
            return HookTriggerReport(
                hook_point=point_value,
                hooks_count=0,
                hooks_executed=0,
                hooks_failed=0,
                hooks_skipped=0,
            )
    
    # ... rest of implementation ...
```

#### 方案三：添加类型强制检查（可选）

**文件**: `src/harness/_lifecycle_hooks.py`

```python
async def trigger_hook(
    hook_registry: LifecycleHookRegistry | None,
    hook_point: HookPoint | str,
    context: dict[str, Any],
) -> HookTriggerReport | None:
    """触发生命周期钩子
    
    Args:
        hook_registry: 钩子注册中心
        hook_point: 钩子节点（推荐使用 HookPoint 枚举）
        context: 钩子上下文
    
    Returns:
        钩子执行报告
    
    Note:
        如果传入字符串，必须是小写形式（如 "response_after"）
        大写字符串（如 "RESPONSE_AFTER"）将触发警告并自动转换
    """
    if not hook_registry:
        return None
    
    # 新增：类型检查警告
    if isinstance(hook_point, str):
        if hook_point != hook_point.lower():
            logger.warning(
                f"Hook point string '{hook_point}' should be lowercase. "
                f"Use HookPoint enum or '{hook_point.lower()}' instead."
            )
    
    return await hook_registry.trigger(hook_point, context)
```

### 排查步骤

#### 步骤 1：定位触发位置

使用 grep/搜索工具查找所有 `RESPONSE_AFTER` 字符串引用：

```bash
# Windows PowerShell
Get-ChildItem -Recurse -Include *.py src | Select-String "RESPONSE_AFTER"
```

**预期结果**：
- 找到传入 `"RESPONSE_AFTER"`（大写字符串）的位置
- 确认该位置应改为 `HookPoint.RESPONSE_AFTER`

#### 步骤 2：验证 Hook 注册状态

在运行时添加诊断日志：

**文件**: `src/lifecycle_hooks/_registry.py`

```python
def __init__(self) -> None:
    # ... existing code ...
    
    # 新增：打印注册的 hook points（调试用）
    logger.debug(f"Registered hook points: {list(self._hooks.keys())}")
```

#### 步骤 3：单元测试

新增测试验证 Hook 触发：

```python
# tests/test_lifecycle_hooks.py

def test_response_after_trigger():
    registry = LifecycleHookRegistry()
    register_builtin_hooks(registry)
    
    # 正确用法测试
    report = await registry.trigger(HookPoint.RESPONSE_AFTER, {})
    assert report.hooks_count > 0
    
    # 大写字符串测试（应触发警告但不崩溃）
    report = await registry.trigger("RESPONSE_AFTER", {})
    assert report.hooks_count == 0  # 未找到钩子
    
    # 小写字符串测试（应正常工作）
    report = await registry.trigger("response_after", {})
    assert report.hooks_count > 0
```

---

## 总结

### 问题一修复要点

| 层级 | 文件 | 修改内容 |
|------|------|----------|
| L1 | `src/client/_streaming.py` | 识别 `thinking`/`reasoning_content` 字段 |
| L2 | `src/harness/_streaming_types.py` | 新增 `StreamChunkType.THINKING` |
| L2 | `src/harness/_streaming_executor.py` | 分离思考与内容输出 |
| L3 | `main.py` | 添加思考内容显示逻辑 |
| Config | `config.json` | 新增 display 配置项 |

### 问题二修复要点

| 方案 | 文件 | 修改内容 |
|------|------|----------|
| 方案一 | 触发点代码 | 使用 `HookPoint.RESPONSE_AFTER` 替代字符串 |
| 方案二 | `src/lifecycle_hooks/_async_trigger.py` | 添加大小写自动转换容错 |
| 方案三 | `src/harness/_lifecycle_hooks.py` | 添加类型检查警告 |

### 实施优先级

1. **P0 - 立即修复**: 问题二（方案一或方案二），影响日志和系统稳定性
2. **P1 - 短期修复**: 问题一 Layer 1-2，确保思考内容被正确识别
3. **P2 - 后续优化**: 问题一 Layer 3，添加可配置的显示控制

---

## 附录

### A. 相关文件清单

| 文件路径 | 功能 |
|----------|------|
| `src/lifecycle_hooks/_types.py` | HookPoint 枚举定义 |
| `src/lifecycle_hooks/_async_trigger.py` | Hook 异步触发逻辑 |
| `src/lifecycle_hooks/_registry.py` | Hook 注册中心 |
| `src/harness/_lifecycle_hooks.py` | Hook 触发辅助函数 |
| `src/_response_hooks.py` | RESPONSE_AFTER 钩子定义 |
| `src/harness/_streaming_executor.py` | 流式响应处理 |
| `src/harness/_streaming_types.py` | 流式类型定义 |
| `src/llm_client/_client.py` | LLM 客户端核心 |
| `main.py` | 主入口，显示逻辑 |

### B. HookPoint 枚举完整列表

```python
class HookPoint(StrEnum):
    # 会话生命周期
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SESSION_PAUSE = "session_pause"
    SESSION_RESUME = "session_resume"
    
    # 工具执行生命周期
    TOOL_CALL_BEFORE = "tool_call_before"
    TOOL_CALL_AFTER = "tool_call_after"
    TOOL_CALL_ERROR = "tool_call_error"
    
    # LLM 调用生命周期
    LLM_CALL_BEFORE = "llm_call_before"
    LLM_CALL_AFTER = "llm_call_after"
    LLM_STREAM_START = "llm_stream_start"
    LLM_STREAM_CHUNK = "llm_stream_chunk"
    LLM_STREAM_END = "llm_stream_end"
    
    # 响应生命周期（问题相关）
    RESPONSE_BEFORE = "response_before"
    RESPONSE_AFTER = "response_after"  # ← 值为小写
    
    # ... 其他 hook points ...
```

### C. ANSI 颜色代码参考

| 颜色 | ANSI 代码 | 用途 |
|------|-----------|------|
| 灰色 | `\033[90m` | 思考内容显示 |
| 重置 | `\033[0m` | 恢复默认颜色 |
| 绿色 | `\033[92m` | 成功状态 |
| 黄色 | `\033[93m` | 警告提示 |

---

**文档版本**: v1.0
**创建日期**: 2026-05-06
**适用项目**: seed-agent