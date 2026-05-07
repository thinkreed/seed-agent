# Wiki 知识落地分析报告

## 日期: 2026-05-07 (更新: P4 实现完成)

## 概述

基于 E:\projects\wiki 目录下十个开源项目的架构分析，提取可落地的优化点并评估适用性。

**验证结果**: 所有 P0 + P1 + P2 + P3 + P4 优化点已实现，测试通过 1147 passed。

**P4 实现 (2026-05-07)** - 基于 Wiki 新项目分析：
- **Circuit Breaker 自动切换**: `src/client/_circuit_breaker.py` - 连续失败触发熔断 + 自动恢复探测 (claude-mem + worldmonitor 设计)
- **Orphan Reaper**: `src/subagent_manager_core/_orphan_reaper.py` - 定期回收孤儿 Subagent 进程 (claude-mem 设计)
- **Stampede Protection**: `src/request_queue_core/_stampede.py` - 并发缓存击穿保护 (worldmonitor 设计)
- **复杂度评分路由**: `src/client/_complexity_scorer.py` - 23 维度评分 → 四级 Tier (manifest-architecture 设计)
- **Specificity 检测**: `src/client/_specificity_detector.py` - 任务类型检测路由特定模型 (manifest-architecture 设计)

**P3 实现 (2026-05-07)**:
- **ToolCapability 枚举**: `src/tools/_types.py` - 6 种能力声明 (DeepSeek-TUI 设计)
- **ApprovalRequirement 枚举**: `src/tools/_types.py` - Auto/Suggest/Required 三级审批 (DeepSeek-TUI 设计)
- **AgentConfig 注册机制**: `src/subagent_manager_core/_agent_registry.py` - Agent 元数据 + 依赖图 (ai-hedge-fund 设计)
- **AgentSignal 统一输出**: `src/subagent_manager_core/_agent_registry.py` - signal/confidence/reasoning 格式 (ai-hedge-fund 设计)

**新增内容 (2026-05-06 P2)**:
- 延迟加载机制: `ToolFactory`, `register_factory`, `ensure_tool`, `warm_all` (Qwen-Code 设计)
- Context Fencing: `_build_memory_context_block` (Hermes-Agent 设计)
- **行动验证原则**: `VerifiedSource`, `_validate_source` (GenericAgent 设计)
- **记忆去重阈值**: `DEDUPLICATION_THRESHOLD`, `_compute_similarity` (MIA 设计)
- **Skills Hub 集成**: `SkillsHub`, `GitHubSource`, `TrustLevel` (Hermes-Agent 设计)
- **TTRL 持续学习**: `TTRLProcessor`, `ttrl_consolidate` (MIA 设计)

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
| qwen-code | Hook 专用输出类 | `src/lifecycle_hooks/_types.py` | ✅ 已实现 |
| **qwen-code** | **延迟加载机制** | **`src/tools/_registry.py` ToolFactory** | **✅ 新增 (P2)** |
| hermes | check_fn 可用性检查 | `src/tools/_registry.py` ToolRegistry.check_fn | ✅ 已实现 |
| **hermes** | **Context Fencing** | **`src/tools/memory/_memory_search.py`** | **✅ 新增 (P2)** |
| hermes | 提取光标机制 | `src/tools/memory/_extract_cursor.py` | ✅ 已实现 |
| **genericagent** | **行动验证原则** | **`src/tools/memory/_memory_write.py` VerifiedSource** | **✅ 新增 (P2)** |
| **mia** | **记忆去重阈值** | **`src/tools/memory/_memory_write.py` DEDUPLICATION_THRESHOLD** | **✅ 新增 (P2)** |
| **mia** | **TTRL 持续学习** | **`src/tools/memory/_ttrl.py` TTRLProcessor** | **✅ 新增 (P2)** |
| **hermes** | **Skills Hub 集成** | **`src/tools/skill_loader/_hub.py` SkillsHub** | **✅ 新增 (P2)** |
| open-agents | Subagent 上下文隔离 | `src/subagent.py` | ✅ 已实现 |
| open-agents | Subagent 类型分级 | EXPLORE/REVIEW/IMPLEMENT/PLAN | ✅ 已实现 |
| hermes | SQLite+FTS5 会话存储 | `src/tools/session_db.py` | ✅ 已实现 |
| hermes | 工具注册表模式 | `src/tools/__init__.py` ToolRegistry | ✅ 已实现 |
| hermes | 渐进式披露 Skills | `src/tools/skill_loader/_skillloader.py` | ✅ 已实现 |
| hermes | 三级披露架构 | Tier 1/2/3 (索引/内容/参考) | ✅ 已实现 |
| genericagent | 自主探索空闲检测 | `src/autonomous/_idle_monitor.py` | ✅ 已实现 |
| genericagent | StepOutcome 统一返回 | `src/agent_loop/_execution.py` | ✅ 已实现 |
| mia | MPE 三代理架构 | SubagentManager + Planner/Executor 分工 | ✅ 已实现 |
| mia | win_rate 字段 | `src/tools/session/_rate_calculation.py` | ✅ 已实现 |
| mia | 混合评分检索 | SessionDB FTS5 + 相关性计算 | ✅ 已实现 |
| **deepseek-tui** | **ToolCapability 枚举** | **`src/tools/_types.py` ToolCapability** | **✅ 新增 (P3)** |
| **deepseek-tui** | **ApprovalRequirement 三级审批** | **`src/tools/_types.py` ApprovalRequirement** | **✅ 新增 (P3)** |
| **ai-hedge-fund** | **AgentConfig 注册机制** | **`src/subagent_manager_core/_agent_registry.py` AGENT_CONFIG** | **✅ 新增 (P3)** |
| **ai-hedge-fund** | **AgentSignal 统一输出** | **`src/subagent_manager_core/_agent_registry.py` AgentSignal** | **✅ 新增 (P3)** |
| **ai-hedge-fund** | **get_agents_list API** | **`src/subagent_manager_core/_agent_registry.py` get_agents_list** | **✅ 新增 (P3)** |
| **shannon-architecture** | **Agent 依赖图拓扑排序** | **`src/subagent_manager_core/_agent_registry.py` resolve_agent_execution_order** | **✅ 新增 (P3)** |

---

## 二、新增优化点详情 (P2 2026-05-06)

### 2.1 延迟加载机制 (Qwen-Code ToolRegistry 设计)

**实现位置**: `src/tools/_registry.py`

**功能**: 按需加载工具，减少启动时开销，使用 `inflight` Map 防重复请求。

**新增类型**:
- `ToolFactory` - 工厂函数类型（异步函数，返回工具函数）

**新增方法**:
- `register_factory(name, factory, ...)` - 注册延迟加载工厂
- `async ensure_tool(name)` - 确保工具已加载（防重复请求）
- `async warm_all(strict)` - 预热所有延迟工具
- `has_factory(name)` - 检查是否有延迟工厂
- `get_pending_factories()` - 获取未加载的工厂列表

```python
# 使用示例
from src.tools import ToolRegistry, ToolFactory

registry = ToolRegistry()

# 注册延迟加载工厂
registry.register_factory(
    "vision_analyze",
    lambda: import_and_get("vision_tools", "analyze"),
    kind=ToolKind.Other,
)

# 按需加载
tool = await registry.ensure_tool("vision_analyze")

# 预热所有
await registry.warm_all()
```

### 2.2 Context Fencing (Hermes-Agent 设计)

**实现位置**: `src/tools/memory/_memory_search.py`

**功能**: 使用标签包裹记忆内容，防止模型误认为是用户输入。

```python
# 输出格式示例
<memory-context>
[System note: The following is recalled memory context,
NOT new user input. Do not respond to it as if the user asked these questions.]

[L1] notes.md
[L2] github_sop.md
[L3] refactoring_knowledge.md
</memory-context>
```

**新增函数**:
- `_build_memory_context_block(raw_context)` - 构建记忆上下文块

**修改函数**:
- `search_memory()` - 返回结果包裹在 `<memory-context>` 标签中

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
| check_fn 可用性检查 | `src/tools/_registry.py` | ✅ 已实现 |
| Hook 专用输出类 | `src/lifecycle_hooks/_types.py` | ✅ 已实现 |
| 提取光标机制 | `src/tools/memory/_extract_cursor.py` | ✅ 已实现 |

### P2 - 中期规划（中价值 + 高复杂度）✅ 全部完成

| 优化点 | 文件 | 状态 |
|------|------|------|
| **延迟加载机制** | `src/tools/_registry.py` | **✅ 已实现** |
| **Context Fencing** | `src/tools/memory/_memory_search.py` | **✅ 已实现** |
| **行动验证原则** | `src/tools/memory/_memory_write.py` | **✅ 已实现** |
| **记忆去重阈值** | `src/tools/memory/_memory_write.py` | **✅ 已实现** |
| **Skills Hub 集成** | `src/tools/skill_loader/_hub.py` | **✅ 已实现** |
| **TTRL 持续学习** | `src/tools/memory/_ttrl.py` | **✅ 已实现** |

---

## 四、落地进度追踪

| 日期 | 已落地 | 测试状态 |
|------|--------|----------|
| 2026-05-05 | P0 全部 | 1130 passed |
| 2026-05-06 早期 | P0 + P1 大部分 | 1132 passed |
| 2026-05-06 中期 | P0 + P1 全部 | 1147 passed |
| 2026-05-06 P2 | P0 + P1 + P2 全部 | 1147 passed |
| **2026-05-07 P3** | **P0 + P1 + P2 + P3 全部** | **1147 passed** |

---

## 五、新增优化点详情 (P2 完整版)

### 5.3 行动验证原则 (GenericAgent 设计)

**实现位置**: `src/tools/memory/_memory_write.py`

**功能**: 只有成功的工具调用结果才能写入 L1/L2/L3，禁止模型猜测写入。

**新增类型**:
- `VerifiedSource` - 验证来源枚举
- `ValidationResult` - 验证结果数据类

**新增方法**:
- `_validate_source(source, level)` - 验证信息来源
- `write_memory(..., source=...)` - 带 source 参数的记忆写入

**核心理念**: No Execution, No Memory

### 5.4 记忆去重阈值 (MIA 设计)

**实现位置**: `src/tools/memory/_memory_write.py`

**功能**: 相似度 ≥ 0.9999 时执行去重逻辑。

**新增常量**:
- `DEDUPLICATION_THRESHOLD = 0.9999`

**新增方法**:
- `_compute_similarity(text1, text2)` - 计算文本相似度
- `_check_existing_memory(path, content, metadata)` - 去重检查

**去重策略**:
- 现有记忆错误 + 新记忆正确 → 替换
- 都正确 → 保留更短版本

### 5.5 Skills Hub 集成 (Hermes-Agent 设计)

**实现位置**: `src/tools/skill_loader/_hub.py`

**功能**: 从 GitHub/skills.sh 发现和安装社区技能。

**新增类型**:
- `TrustLevel` - 信任级别枚举 (builtin/trusted/community)
- `SkillSource` - 技能来源抽象接口
- `GitHubSource` - GitHub 仓库技能来源
- `WellKnownSkillSource` - /.well-known/skills 来源
- `SkillsHub` - Hub 协调器

**新增 API**:
- `skills_hub_list()` - 列出可用技能
- `skills_hub_search(query)` - 搜索技能
- `skills_hub_install(skill_name)` - 安装技能
- `skills_hub_uninstall(skill_name)` - 卸载技能
- `skills_hub_installed()` - 列出已安装技能

### 5.6 TTRL 持续学习 (MIA 设计)

**实现位置**: `src/tools/memory/_ttrl.py`

**功能**: 推理时持续学习，记忆整合流程。

**新增类型**:
- `JudgementType` - 执行结果判断类型
- `MemorySource` - 记忆来源类型
- `ExecutionTrace` - 执行轨迹数据类
- `MemoryEntry` - 记忆条目数据类
- `TTRLProcessor` - TTRL 处理器

**新增 API**:
- `ttrl_add_trace(...)` - 添加执行轨迹
- `ttrl_batch_evaluate()` - 批量评估
- `ttrl_add_memory(...)` - 添加记忆条目
- `ttrl_consolidate()` - 整合记忆
- `ttrl_get_stats()` - 获取 Win Rate 统计

---

## 六、P3 评估详情 (2026-05-07)

### 6.1 Snapshot-based Sandbox 持久化 (Open-Agents 设计)

**来源**: `E:\projects\wiki\open-agents\03-sandbox-package.md`

**Open-Agents 实现**:
- `snapshot()` 方法 - 创建云端 Sandbox 快照，返回 `snapshotId`
- `restoreSnapshotId` - 从快照恢复 Sandbox 状态
- `SandboxState` 持久化 - 包含 `sandboxName`, `snapshotId`, `files` 等

**适用性评估**: **不适用**

**原因**:
1. seed-agent 使用本地执行环境 (`~/.seed/sandbox/`)
2. 本地文件系统本身持久化，无需云端快照
3. 进程状态无法通过快照保存（云端 Sandbox 通过虚拟机快照实现）
4. 会话恢复已有独立机制 (`SessionEventStream`, `RalphState`)

**替代方案**:
- 如需增强 Sandbox 持久化，可考虑：
  - 文件变更追踪（类似 `files` 字段）
  - Sandbox 状态序列化 (`getState()`)
- 但这些功能优先级较低，暂不实施

---

## 七、新增优化点详情 (P3 2026-05-07)

基于 Wiki 新项目分析（ai-hedge-fund, codex-architecture, deepseek-tui, shannon-architecture, opensre-docs），提取并实施以下优化点：

### 7.1 ToolCapability 能力声明枚举 (DeepSeek-TUI 设计)

**实现位置**: `src/tools/_types.py`

**功能**: 更细粒度的工具能力声明，与 ToolKind 互补。

**新增类型**:
- `ToolCapability` 枚举 - ReadOnly/WritesFiles/ExecutesCode/Network/Sandboxable/RequiresApproval
- `ApprovalRequirement` 枚举 - Auto/Suggest/Required 三级审批需求

**新增常量**:
- `CAPABILITY_APPROVAL_MAP` - 能力到审批需求的映射
- `SANDBOX_REQUIRED_CAPABILITIES` - 需要沙箱隔离的能力
- `READ_ONLY_CAPABILITIES` - 只读能力集合

```python
# 使用示例
from src.tools import ToolCapability, ApprovalRequirement, CAPABILITY_APPROVAL_MAP

# 声明工具能力
capabilities = [ToolCapability.ReadOnly, ToolCapability.Sandboxable]

# 获取默认审批需求
approval = CAPABILITY_APPROVAL_MAP[ToolCapability.ExecutesCode]  # Required
```

### 7.2 AgentConfig 注册机制 (ai-hedge-fund ANALYST_CONFIG 设计)

**实现位置**: `src/subagent_manager_core/_agent_registry.py`

**功能**: Agent 元数据注册和发现，支持依赖图拓扑排序。

**新增类型**:
- `AgentSignalType` 枚举 - Bullish/Bearish/Neutral 信号类型
- `AgentSignal` dataclass - 统一信号输出格式（signal, confidence, reasoning）
- `AgentConfig` dataclass - Agent 元数据配置

**新增注册表**:
- `AGENT_CONFIG` - Agent 配置字典（display_name, description, style, capabilities, order, prerequisites）

**新增函数**:
- `get_agent_nodes()` - 获取 Agent 名称到配置的映射
- `get_agents_list()` - 获取 Agent 列表用于 API 响应
- `get_agent_by_type()` - 根据 SubagentType 获取配置
- `get_agent_dependencies()` - 获取前置依赖列表
- `resolve_agent_execution_order()` - 依赖图拓扑排序

```python
# 使用示例
from src.subagent_manager_core import AGENT_CONFIG, resolve_agent_execution_order

# 查看 Agent 配置
print(AGENT_CONFIG["explore"].display_name)  # "Explorer"

# 解析执行顺序（基于依赖图）
order = resolve_agent_execution_order(["implement", "review"])
# ["review", "implement"] - review 是 implement 的前置依赖
```

### 7.3 其他评估但未实施的优化点

| 来源 | 优化点 | 评估结果 |
|------|--------|----------|
| **codex-architecture** | ThreadManager + RolloutRecorder | seed-agent 已有 SubagentManager + SessionEventStream |
| **codex-architecture** | SandboxPolicy 枚举 | seed-agent 已有 SandboxPolicy 实现 |
| **shannon-architecture** | VulnType 枚举 + 依赖图 | 已整合到 AgentConfig.prerequisites |
| **shannon-architecture** | "No Exploit No Report" 验证策略 | RalphLoop 已有类似外部验证机制 |
| **opensre-docs** | ThreadPoolExecutor 并行执行 | SubagentManager 已有并发控制 |
| **opensre-docs** | CostTier 成本等级 | 可作为后续优化 |
| **opensre-docs** | investigation_loop 循环控制 | RalphLoop 已有迭代控制 |
| **deepseek-tui** | RLM Context Busting | 需额外架构设计 |

---

## 八、新增优化点详情 (P4 2026-05-07)

基于 Wiki 新项目分析（claude-context-docs, claude-mem-docs, codebrain, FinceptTerminal-Architecture, manifest-architecture, multica, omi, qdrant-docs, worldmonitor-architecture），实施以下 P1 级优化点：

### 8.1 Circuit Breaker 自动切换 (claude-mem + worldmonitor 设计)

**实现位置**: `src/client/_circuit_breaker.py`

**功能**: Provider 熔断器，连续失败自动切换备用，自动恢复探测。

**新增类型**:
- `CircuitState` 枚举 - CLOSED/OPEN/HALF_OPEN 状态
- `CircuitConfig` dataclass - 熔断器配置（failure_threshold, recovery_timeout）
- `CircuitStats` dataclass - 统计信息
- `CircuitBreaker` - 单个 Provider 熔断器
- `CircuitBreakerRegistry` - 多 Provider 熔断注册表

**新增方法**:
- `can_execute()` - 检查是否可执行
- `record_success()` / `record_failure()` - 记录结果
- `reset()` - 强制重置

```python
# 使用示例
from src.client._circuit_breaker import CircuitBreakerRegistry, CircuitConfig

registry = CircuitBreakerRegistry()

# 配置熔断器
registry.configure("openai", CircuitConfig(failure_threshold=3, recovery_timeout=30.0))

# 检查是否可执行
if await registry.can_execute("openai"):
    try:
        result = await call_llm()
        await registry.record_success("openai")
    except Exception:
        await registry.record_failure("openai")
```

### 8.2 Orphan Reaper (claude-mem 设计)

**实现位置**: `src/subagent_manager_core/_orphan_reaper.py`

**功能**: 定期扫描和回收超时的孤儿 Subagent 进程。

**新增类型**:
- `OrphanStatus` 枚举 - ALIVE/TIMEOUT/TERMINATED/KILLED/CLEANED
- `ProcessInfo` dataclass - 进程信息
- `ReaperConfig` dataclass - Reaper 配置
- `OrphanReaper` - 孤儿进程回收器

**新增方法**:
- `register(pid, task_id, timeout)` - 注册新进程
- `unregister(pid)` - 取消注册
- `start()` / `stop()` - 启动/停止 Reaper

```python
# 使用示例
from src.subagent_manager_core._orphan_reaper import get_orphan_reaper

reaper = get_orphan_reaper()
await reaper.start()

# 注册进程
reaper.register(pid=12345, task_id="abc", timeout=300)

# 正常完成后取消注册
reaper.unregister(pid=12345)
```

### 8.3 Stampede Protection (worldmonitor 设计)

**实现位置**: `src/request_queue_core/_stampede.py`

**功能**: 并发缓存击穿保护，单个请求实际调用，其他等待共享结果。

**新增类型**:
- `StampedeConfig` dataclass - 配置
- `StampedeEntry` dataclass - 条目
- `StampedeStats` dataclass - 统计
- `StampedeProtection` - 保护器
- `StampedeRegistry` - 注册表

**新增方法**:
- `get_or_refresh(key, refresh_fn)` - 获取或刷新
- `invalidate(key)` - 失效缓存
- `get_stats()` - 获取统计

```python
# 使用示例
from src.request_queue_core._stampede import StampedeProtection

stampede = StampedeProtection[str]()

async def refresh():
    return await fetch_from_backend()

# 第一个请求执行刷新，其他等待
result = await stampede.get_or_refresh("cache_key", refresh)
```

### 8.4 复杂度评分路由 (manifest-architecture 设计)

**实现位置**: `src/client/_complexity_scorer.py`

**功能**: 23 维度复杂度评分，四级 Tier 路由（simple/standard/complex/reasoning）。

**新增类型**:
- `ComplexityTier` 枚举 - SIMPLE/STANDARD/COMPLEX/REASONING
- `ComplexityDimension` dataclass - 维度定义
- `ComplexityScore` dataclass - 评分结果
- `ComplexityScorer` - 评分器

**23 维度**:
- 代码复杂度（5维）：file_count, line_count, function_count, nesting_depth, dependency_count
- 任务复杂度（6维）：step_count, decision_points, parallel_tasks, verification_needed, documentation_needed, test_needed
- 上下文复杂度（4维）：message_count, token_count, file_references, history_length
- 工具复杂度（4维）：tool_count, tool_types, cross_domain_calls, permission_level
- 知识复杂度（4维）：domain_count, concept_count, reasoning_depth, uncertainty_level

```python
# 使用示例
from src.client._complexity_scorer import ComplexityScorer, ComplexityTier, select_model_for_tier

scorer = ComplexityScorer()
score = scorer.score_messages(messages, has_tools=True)

# 根据 Tier 选择模型
model = select_model_for_tier(score.tier)
```

### 8.5 Specificity 检测 (manifest-architecture 设计)

**实现位置**: `src/client/_specificity_detector.py`

**功能**: 任务类型自动检测，路由到专用模型。

**新增类型**:
- `SpecificityType` 枚举 - CODING/DATA_ANALYSIS/WEB_BROWSING/PLANNING/REASONING/CONVERSATION/GENERAL
- `SpecificityResult` dataclass - 检测结果
- `SpecificityDetector` - 检测器
- `SpecificityRouter` - 路由器

**三层路由优先级**: Header Tiers → Specificity → Complexity

```python
# 使用示例
from src.client._specificity_detector import SpecificityRouter

router = SpecificityRouter()
model, routing_info = router.route(messages, has_tools=True)

# routing_info["route_source"] 可为 "header", "specificity", "complexity"
```

---

## 九、P4 落地进度追踪

| 日期 | 已落地 | 测试状态 |
|------|--------|----------|
| 2026-05-05 | P0 全部 | 1130 passed |
| 2026-05-06 早期 | P0 + P1 大部分 | 1132 passed |
| 2026-05-06 中期 | P0 + P1 全部 | 1147 passed |
| 2026-05-06 P2 | P0 + P1 + P2 全部 | 1147 passed |
| 2026-05-07 P3 | P0 + P1 + P2 + P3 全部 | 1147 passed |
| **2026-05-07 P4** | **P0-P4 全部** | **1147 passed** |

---

## 十、参考资料

### 原有项目
- genericagent: `E:\projects\wiki\genericagent\`
- hermes-agent: `E:\projects\wiki\hermes-agent\`
- mia: `E:\projects\wiki\mia\`
- open-agents: `E:\projects\wiki\open-agents\`
- qwen-code-architecture: `E:\projects\wiki\qwen-code-architecture\`
- ai-hedge-fund: `E:\projects\wiki\ai-hedge-fund\`
- codex-architecture: `E:\projects\wiki\codex-architecture\`
- deepseek-tui-architecture: `E:\projects\wiki\deepseek-tui-architecture\`
- shannon-architecture: `E:\projects\wiki\shannon-architecture\`
- opensre-docs: `E:\projects\wiki\opensre-docs\`

### 新增项目（P4 参考）
- claude-context-docs: `E:\projects\wiki\claude-context-docs\` - Merkle DAG 增量索引、混合搜索
- claude-mem-docs: `E:\projects\wiki\claude-mem-docs\` - Hooks 系统、CLAIM-CONFIRM 队列、Circuit Breaker
- codebrain: `E:\projects\wiki\codebrain\` - Fallback Chain、意图导向工具合并、增量 SymbolIndex
- FinceptTerminal-Architecture: `E:\projects\wiki\FinceptTerminal-Architecture\` - Result<T> 错误处理、DataHub Pub/Sub
- manifest-architecture: `E:\projects\wiki\manifest-architecture\` - 复杂度评分路由、Specificity 检测
- multica: `E:\projects\wiki\multica\` - 失效策略、乐观更新回滚
- omi: `E:\projects\wiki\omi\` - VAD Gate、Fail-open 策略
- qdrant-docs: `E:\projects\wiki\qdrant-docs\` - Segment 分层、量化压缩
- worldmonitor-architecture: `E:\projects\wiki\worldmonitor-architecture\` - Stampede Protection、五级缓存分层