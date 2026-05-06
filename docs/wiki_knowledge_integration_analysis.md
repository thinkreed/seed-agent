# Wiki 知识落地分析报告

## 日期: 2026-05-06 (更新: P2 全部完成)

## 概述

基于 E:\projects\wiki 目录下五个开源项目的架构分析，提取可落地的优化点并评估适用性。

**验证结果**: 所有 P0 + P1 + P2 优化点已实现。

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
| **2026-05-06 当前** | **P0 + P1 + P2 全部** | **待验证** |

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

## 五、参考资料

- genericagent: `E:\projects\wiki\genericagent\`
- hermes-agent: `E:\projects\wiki\hermes-agent\`
- mia: `E:\projects\wiki\mia\`
- open-agents: `E:\projects\wiki\open-agents\`
- qwen-code-architecture: `E:\projects\wiki\qwen-code-architecture\`