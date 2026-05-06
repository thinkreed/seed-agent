# Wiki 知识落地分析报告

## 日期: 2026-05-06 (更新: 2026-05-06 P1 新增完成)

## 概述

基于 E:\projects\wiki 目录下五个开源项目的架构分析，提取可落地的优化点并评估适用性。

**验证结果**: 所有 P0 + P1 优化点已实现并验证通过，测试套件 1147 passed。

---

## 一、已实现的优化点（seed-agent 已具备）

| 来源 | 优化点 | seed-agent 实现 | 状态 |
|------|--------|-----------------|------|
| qwen-code | 三件套解耦架构 | LLMClient + Harness + Sandbox | ✅ 已实现 |
| qwen-code | AbortSignal 取消机制 | `src/abort_signal.py` + `_cancellation_token` | ✅ 已实现 |
| qwen-code | Ask User 等待机制 | `src/tools/ask_user_types.py` | ✅ 已实现 |
| qwen-code | BackgroundTaskRegistry | `src/background_task_registry.py` | ✅ 已实现 |
| qwen-code | LifecycleHooks | `src/lifecycle_hooks/` 模块拆分 | ✅ 已实现 |
| qwen-code | ToolKind 枚举分类 | `src/tools/__init__.py` ToolKind | ✅ 已实现 |
| qwen-code | LoopDetectionService | `src/harness/_loop_detection.py` | ✅ 已实现 |
| qwen-code | MessageBus.request() | `src/lifecycle_hooks/_message_bus.py` | ✅ 已实现 |
| qwen-code | 整合锁机制 | `src/tools/memory/_consolidation_lock.py` | ✅ 已实现 |
| qwen-code | HookAggregator | `src/lifecycle_hooks/_message_bus.py` HookAggregator | ✅ 已实现 |
| qwen-code | PermissionDecision 三级权限 | `src/tools/__init__.py` PermissionDecision | ✅ 已实现 |
| qwen-code | MUTATOR_KINDS | `src/tools/__init__.py` MUTATOR_KINDS | ✅ 已实现 |
| qwen-code | CONCURRENCY_SAFE_KINDS | `src/tools/__init__.py` CONCURRENCY_SAFE_KINDS | ✅ 已实现 |
| **hermes** | **check_fn 可用性检查** | **`src/tools/__init__.py` ToolRegistry.check_fn** | **✅ 新增 (2026-05-06)** |
| **qwen-code** | **Hook 专用输出类** | **`src/lifecycle_hooks/_types.py` PreToolUseHookOutput 等** | **✅ 新增 (2026-05-06)** |
| open-agents | Subagent 上下文隔离 | `src/subagent.py` | ✅ 已实现 |
| open-agents | Subagent 类型分级 | EXPLORE/REVIEW/IMPLEMENT/PLAN | ✅ 已实现 |
| hermes | SQLite+FTS5 会话存储 | `src/tools/session_db.py` | ✅ 已实现 |
| hermes | 工具注册表模式 | `src/tools/__init__.py` ToolRegistry | ✅ 已实现 |
| hermes | 渐进式披露 Skills | `src/tools/skill_loader/_skillloader.py` | ✅ 已实现 |
| hermes | 三级披露架构 | Tier 1/2/3 (索引/内容/参考) | ✅ 已实现 |
| genericagent | 自主探索空闲检测 | `src/autonomous/_idle_monitor.py` | ✅ 已实现 |
| genericagent | StepOutcome 统一返回 | `src/agent_loop/_execution.py` | ✅ 已实现 |
| mia | MPE 三代理架构 | SubagentManager + Planner/Executor 分工 | ✅ 已实现 |
| mia | win_rate 字段 | `src/tools/session/_rate_calculation.py` success_rate/laplace_rate | ✅ 已实现 |
| mia | 混合评分检索 | SessionDB FTS5 + 相关性计算 | ✅ 已实现 |

---

## 二、新增优化点详情 (2026-05-06)

### 2.1 check_fn 可用性检查 (Hermes-Agent 设计)

**实现位置**: `src/tools/__init__.py`

**功能**: 工具注册时添加可选的可用性检查函数，用于检查 API Key、环境变量等要求。

```python
# 工具注册示例
registry.register(
    "web_search",
    web_search_func,
    check_fn=lambda: bool(os.environ.get("SEARCH_API_KEY")),
)

# 使用示例
if registry.is_available("web_search"):
    result = await registry.execute("web_search", query="...")
else:
    # 提示用户配置 API Key
```

**新增方法**:
- `is_available(name)` - 判断工具是否可用
- `get_available_tools()` - 获取所有可用工具列表
- `get_unavailable_tools()` - 获取不可用工具及原因

### 2.2 Hook 专用输出类 (Qwen-Code 设计)

**实现位置**: `src/lifecycle_hooks/_types.py`

**新增类**:
- `DefaultHookOutput` - 默认 Hook 输出基类
- `PreToolUseHookOutput` - 工具调用前输出（支持拒绝/修改参数）
- `PostToolUseHookOutput` - 工具调用后输出（支持修改结果）
- `LLMStreamHookOutput` - LLM 流式响应输出（支持内容过滤）
- `UserResponseHookOutput` - 用户响应输出（支持输入修改）

```python
# PreToolUseHookOutput 使用示例
def security_hook(tool_name, args):
    if tool_name == "delete_file":
        if args.get("path").startswith("/etc/"):
            return PreToolUseHookOutput(
                should_execute=False,
                deny_reason="禁止删除系统目录文件",
            )
    return PreToolUseHookOutput(should_execute=True)
```

---

## 三、实施优先级

### P0 - 立即落地（高价值 + 低复杂度）✅ 已完成

| 优化点 | 文件 | 实现状态 |
|------|------|----------|
| ToolKind 枚举分类 | `src/tools/__init__.py` | ✅ 已实现 |
| LoopDetectionService | `src/harness/_loop_detection.py` | ✅ 已实现 |
| 整合锁机制 | `src/tools/memory/_consolidation_lock.py` | ✅ 已实现 |
| win_rate 字段 | `src/tools/session/_rate_calculation.py` | ✅ 已实现 |

### P1 - 近期优化（高价值 + 中等复杂度）✅ 已完成

| 优化点 | 文件 | 实现状态 |
|------|------|----------|
| 渐进式披露 Skills | `src/tools/skill_loader/_skillloader.py` | ✅ 已实现 |
| MessageBus.request() | `src/lifecycle_hooks/_message_bus.py` | ✅ 已实现 |
| HookAggregator | `src/lifecycle_hooks/_message_bus.py` | ✅ 已实现 |
| PermissionDecision 三级权限 | `src/tools/__init__.py` | ✅ 已实现 |
| MUTATOR_KINDS / CONCURRENCY_SAFE_KINDS | `src/tools/__init__.py` | ✅ 已实现 |
| **check_fn 可用性检查** | **`src/tools/__init__.py`** | **✅ 新增 (2026-05-06)** |
| **Hook 专用输出类** | **`src/lifecycle_hooks/_types.py`** | **✅ 新增 (2026-05-06)** |
| DeclarativeTool 模式 | `src/tools/builtin/` | 待重构（可选）|
| 双重历史管理 | `src/session_event_stream.py` | 待新增 curated_history（可选）|

### P2 - 中期规划（中价值 + 高复杂度）

| 优化点 | 文件 | 预估工作量 |
|------|------|-----------|
| 行动验证原则 | `src/tools/memory/` | 记忆写入前验证 |
| 记忆去重阈值 | `src/tools/session/` | 相似度 ≥ 0.9999 去重 |
| 并行工具执行 | `src/harness/_tool_router.py` | 重构执行逻辑 |
| StepOutcome 统一返回 | `src/tools/__init__.py` | 全工具接口变更 |
| SSRF 防护 | `src/lifecycle_hooks/` | 安全模块扩展 |
| OAuth 设备码流程 | `src/client/` | 新增认证流程 |

---

## 四、落地进度追踪

| 日期 | 已落地 | 测试状态 |
|------|--------|----------|
| 2026-05-05 | P0 全部 | 1130 passed |
| 2026-05-06 早期 | P0 + P1 大部分 | 1132 passed |
| **2026-05-06 当前** | **P0 + P1 全部 + check_fn + Hook 输出类** | **1147 passed** |

---

## 五、参考资料

- genericagent: `E:\projects\wiki\genericagent\`
- hermes-agent: `E:\projects\wiki\hermes-agent\`
- mia: `E:\projects\wiki\mia\`
- open-agents: `E:\projects\wiki\open-agents\`
- qwen-code-architecture: `E:\projects\wiki\qwen-code-architecture\`