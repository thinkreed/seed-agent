# Harness Engineering Architecture Optimization Design

> **文档版本**: v1.0  
> **创建日期**: 2026-05-03  
> **参考来源**: 深入浅出Harness Engineering之核心模式与理念  
> **目标**: 对比 Harness Engineering 核心模式与 seed-agent 当前架构，提出整改优化设计方案

---

## 目录

1. [概述与核心理念对比](#概述与核心理念对比)
2. [架构解耦分析](#架构解耦分析)
3. [记忆系统升级设计](#记忆系统升级设计)
4. [上下文工程优化](#上下文工程优化)
5. [生命周期钩子体系](#生命周期钩子体系)
6. [多智能体协作模式](#多智能体协作模式)
7. [工具与权限体系](#工具与权限体系)
7. [凭证安全架构](#凭证安全架构)
8. [实施路线图](#实施路线图)

---

## 概述与核心理念对比

### Harness Engineering 核心哲学

**宠物与牲畜基础设施哲学**:

| 概念 | Harness 定义 | 核心价值 |
|------|-------------|----------|
| **Session（会话）** | 宠物 | 精心培育、持久保存、不可丢失、不可变事件流 |
| **Harness（控制器）** |牲畜 | 可随时创建、销毁、替换、无状态 |
| **Sandbox（沙盒）** |牲畜 | 可随时创建、销毁、替换、完全隔离 |

**三件套解耦架构**:

```
┌─────────────────────────────────────────────────────────────┐
│                    Claude (大脑)                             │
│                 负责推理和决策                                 │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Harness (双手)                            │
│       驱动运行循环 → 调用 Claude API → 路由工具调用            │
│                    本身无状态                                 │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Sandbox (工作台)                          │
│         隔离的文件系统、进程、网络执行环境                       │
│                    可重建、可扩展                              │
└─────────────────────────────────────────────────────────────┘
```

### seed-agent 当前架构

```
┌─────────────────────────────────────────────────────────────┐
│                    AgentLoop                                 │
│           主执行引擎 (对话生命周期 + 工具执行)                   │
│                 历史可变，支持摘要压缩                          │
└───────────────────────────┬─────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│ LLMGateway    │  │ Subagent      │  │ RalphLoop     │
│ 多Provider网关 │  │ 管理器        │  │ 长周期执行器   │
└───────────────┘  └───────────────┘  └───────────────┘
```

### 核心差距分析

| Harness 特性 | seed-agent 状态 | 差距等级 |
|--------------|-----------------|----------|
| Session 不可变事件流 | ❌ 历史可变，可摘要截断 | **高** |
| Harness/Sandbox 解耦 | ❌ AgentLoop 直接执行工具 | **高** |
| 凭证保险库 + 代理 | ❌ API Key 直接存储于配置 | **高** |
| 五层记忆架构 (L1-L5) | ⚠️ 四层架构 (L1-L4) | **中** |
| 五段式执行循环 | ⚠️ 三段式 (Plan→Exec→Review) | **中** |
| 确定性生命周期钩子 | ⚠️ 部分 (autodream, autonomous) | **中** |
| 渐进式上下文压缩 | ⚠️ 有压缩，缺渐进分层 | **中** |
| 上下文裁剪机制 | ❌ 无智能裁剪 | **中** |
| 多脑一手/一脑多手协作 | ⚠️ 有 Subagent，缺协作模式 | **低** |

---

## 架构解耦分析

### 当前问题

**seed-agent 架构耦合点**:

1. **AgentLoop 与工具执行耦合**: `_execute_tool_calls()` 直接执行，无隔离层
2. **历史与推理耦合**: 上下文管理嵌入 AgentLoop，无法独立重置
3. **凭证与执行耦合**: API Key 存储于配置文件，执行环境可直接访问

### 设计方案: 三件套解耦架构

#### 1. Session 层重构 (不可变事件流)

**目标**: 将历史记录从可变列表改为只追加事件流

**设计要点**:

```python
# 当前: 可变历史列表
class AgentLoop:
    self.history: list[dict] = []  # 可变，可截断

# 目标: 不可变事件流
class SessionEventStream:
    """只追加的事件日志，支持重放与恢复"""
    
    def emit_event(self, event: dict) -> None:
        """记录事件 - 只追加，不可修改"""
        self._events.append({
            "id": self._next_event_id(),
            "timestamp": time.time(),
            "type": event["type"],
            "data": event["data"]
        })
    
    def get_events(self, start_id: int = 0) -> list[dict]:
        """读取事件 - 支持重放"""
        return self._events[start_id:]
    
    def replay_to_state(self, target_event_id: int) -> dict:
        """重放事件到指定状态 - 容错恢复"""
        ...
```

**收益**:

- 容错能力: 进程崩溃后可从任意事件点恢复
- 可追溯性: 完整操作历史，支持审计
- 重放能力: 可重现任意执行状态

#### 2. Harness 层分离 (无状态控制器)

**目标**: 从 AgentLoop 提取纯控制逻辑

**设计要点**:

```python
# 新架构: Harness 作为纯控制器
class Harness:
    """无状态执行控制器"""
    
    def __init__(self, session: SessionEventStream, sandbox: Sandbox):
        self.session = session  # 只读
        self.sandbox = sandbox  # 执行环境
    
    async def run_cycle(self, prompt: str) -> str:
        """执行一轮对话循环"""
        # 1. 从 Session 拉取上下文
        context = self._build_context_from_session()
        
        # 2. 调用 LLM (大脑)
        response = await self.llm_client.chat_completion(context)
        
        # 3. 记录响应到 Session
        self.session.emit_event({"type": "llm_response", "data": response})
        
        # 4. 路由工具调用到 Sandbox
        if response.get("tool_calls"):
            results = await self.sandbox.execute_tools(response["tool_calls"])
            self.session.emit_event({"type": "tool_results", "data": results})
        
        return response
```

**收益**:

- 可替换性: Harness 可随时替换，不影响 Session
- 状态分离: 所有状态在 Session，Harness 可重启
- 首Token延迟优化: 大脑与容器解耦后，推理可立即开始

#### 3. Sandbox 层引入 (隔离执行环境)

**目标**: 创建隔离的工具执行环境

**设计要点**:

```python
class Sandbox:
    """隔离的执行沙盒"""
    
    def __init__(self, isolation_level: str = "process"):
        """
        Args:
            isolation_level: 进程级/容器级隔离
        """
        self._file_system_root: Path = Path("~/.seed/sandbox/")
        self._network_policy: dict = {"allow": [], "deny": ["*"]}
        self._credential_proxy: CredentialProxy = None
    
    async def execute_tool(self, tool_call: dict) -> dict:
        """在隔离环境中执行工具"""
        tool_name = tool_call["function"]["name"]
        tool_args = json.loads(tool_call["function"]["arguments"])
        
        # 路径映射: 沙盒内路径 → 主机路径
        mapped_args = self._map_paths(tool_args)
        
        # 权限检查
        if not self._check_permission(tool_name, mapped_args):
            return {"error": "Permission denied in sandbox"}
        
        # 执行工具
        result = await self._execute_in_isolation(tool_name, mapped_args)
        return result
```

**收益**:

- 安全隔离: 代码执行在沙盒内，不影响主机
- 可重建性: 沙盒可随时销毁重建
- 可扩展性: 支持不同隔离级别 (进程/Docker/VM)

---

## 记忆系统升级设计

### Harness 五层记忆架构

| 层级 | 名称 | 用途 | Harness 特性 |
|------|------|------|-------------|
| L1 | 短期记忆 (便利贴) | 当前对话临时信息 | 快速参考 |
| L2 | 技能手册 (肌肉记忆) | 复杂任务后自动生成 SKILL.md | 可复用流程 |
| L3 | 知识库 (语义记忆) | 向量存储，模糊检索 | 语义相似度匹配 |
| L4 | 对用户的了解 (用户建模) | 黑格尔辩证式用户理解 | 不断进化调整 |
| L5 | 工作日志 (长期档案) | FTS5 + LLM 摘要 | 永久存储，智能索引 |

### seed-agent 当前四层架构

| 层级 | 名称 | 用途 | 存储 |
|------|------|------|------|
| L1 | 索引 | 快速参考可用 SOP | `notes.md` |
| L2 | 技能 | 可复用操作流程 | `skills/*.md` |
| L3 | 知识 | 跨任务模式和原则 | `knowledge/*.md` |
| L4 | 原始 | 会话历史和日志 | SQLite+FTS5 |

### 升级设计方案

#### 1. L4 重构: 用户建模层 (辩证式进化)

**核心概念**: 不是一次判断就定终身，允许用户改变，通过不断观察、思考、调整，越来越懂真实的用户

**设计要点**:

```python
class UserModelingLayer:
    """L4 用户建模 - 黑格尔辩证式进化"""
    
    def __init__(self):
        self._user_profile: dict = {}  # 用户偏好模型
        self._observations: list[dict] = []  # 观察记录
    
    def observe(self, evidence: dict) -> None:
        """观察新证据"""
        self._observations.append({
            "timestamp": time.time(),
            "type": evidence["type"],  # preference, behavior, feedback
            "data": evidence["data"],
            "context": evidence["context"]
        })
    
    def dialectical_update(self) -> None:
        """辩证式更新: 发现矛盾 → 内部讨论 → 升级模型"""
        # 1. 检测新证据与旧模型矛盾
        conflicts = self._detect_conflicts()
        
        # 2. 内部推理讨论
        resolution = self._reason_about_conflicts(conflicts)
        
        # 3. 升级用户模型 (不直接覆盖)
        self._upgrade_model(resolution)
    
    def _upgrade_model(self, resolution: dict) -> None:
        """升级模型而非简单覆盖"""
        # 示例: "林总平时喝美式，但周三下午会换拿铁"
        # 不是: preference = "拿铁"
        # 而是: preference = {"usual": "美式", "exceptions": {"周三下午": "拿铁"}}
        ...
```

**数据结构示例**:

```json
{
  "user_preferences": {
    "coffee": {
      "usual": "美式",
      "exceptions": {
        "周三下午": "拿铁",
        "会议前": "浓缩"
      },
      "confidence": 0.85
    },
    "work_style": {
      "primary": "深度工作",
      "exceptions": {
        "紧急项目": "快速迭代"
      }
    }
  },
  "observation_history": [...],
  "last_update": "2026-05-03T10:30:00"
}
```

#### 2. L5 新增: 工作日志层 (FTS5 + LLM 摘要)

**核心概念**: 每次长谈后自动用一两句话总结核心结论，FTS5 提供智能目录

**设计要点**:

```python
class LongTermArchiveLayer:
    """L5 工作日志 - FTS5 + LLM 摘要"""
    
    def __init__(self, db_path: Path):
        self._db = SQLiteFTS5Database(db_path)
        self._llm_summarizer: LLMGateway = None
    
    async def archive_session(self, session_id: str, messages: list) -> None:
        """归档会话"""
        # 1. LLM 生成摘要 (写读书笔记)
        summary = await self._generate_summary(messages)
        
        # 2. 存储到数据库
        self._db.insert_session(
            session_id=session_id,
            messages=messages,
            summary=summary
        )
        
        # 3. FTS5 自动索引 (智能目录)
        self._db.update_fts_index(session_id)
    
    async def _generate_summary(self, messages: list) -> str:
        """LLM 生成核心结论摘要"""
        prompt = f"请用1-2句话总结以下对话的核心结论:\n{self._format_messages(messages)}"
        response = await self._llm_summarizer.chat_completion(prompt)
        return response["choices"][0]["message"]["content"]
    
    def search_with_context(self, keyword: str) -> list[dict]:
        """语义搜索 + 摘要提取"""
        # FTS5 搜索关键词
        matches = self._db.search_fts(keyword)
        
        # 返回: 摘要 + 关键上下文片段
        return [
            {
                "session_id": m["session_id"],
                "summary": m["summary"],
                "matched_snippet": m["snippet"],
                "timestamp": m["timestamp"]
            }
            for m in matches
        ]
```

**升级后五层架构**:

```
┌─────────────────────────────────────────────────────────────┐
│ L5 工作日志 (长期档案)                                        │
│     FTS5 全文检索 + LLM 自动摘要                               │
│     永久存储，支持语义搜索                                     │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ 归档
┌─────────────────────────────────────────────────────────────┐
│ L4 用户建模 (辩证式理解)                                      │
│     黑格尔辩证式: 观察 → 矛盾检测 → 内部推理 → 升级模型          │
│     越来越懂用户，允许例外和复杂情况                            │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ 用户反馈提取
┌─────────────────────────────────────────────────────────────┐
│ L3 知识库 (语义记忆)                                          │
│     向量存储，模糊检索                                        │
│     "进度报告" vs "项目周报" → 相似度 0.92                     │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ 模式蒸馏
┌─────────────────────────────────────────────────────────────┐
│ L2 技能手册 (肌肉记忆)                                        │
│     完成复杂任务后自动生成 SKILL.md                            │
│     可复用操作流程                                            │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ 技能注册
┌─────────────────────────────────────────────────────────────┐
│ L1 短期记忆 (便利贴)                                          │
│     当前对话的临时信息                                        │
│     快速参考索引                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 上下文工程优化

### Harness 上下文工程模式

| 模式 | 描述 | Harness 实现 |
|------|------|-------------|
| **上下文压缩** | 上下文窗口将满时压缩早期对话 | LLM 生成摘要，原始数据保留在 Session |
| **记忆工具** | Claude 主动将重要信息写入持久存储 | 类似人类记笔记 |
| **上下文裁剪** | 发送前智能裁剪不相关上下文 | 只保留当前任务需要的部分 |
| **渐进式压缩** | 新对话保留细节 → 轻量总结 → 简短摘要 | 三层压缩，渐进信息损失 |

### seed-agent 当前实现

**已有能力**:

- `_maybe_summarize()`: 上下文阈值或对话轮数触发摘要
- `_estimate_context_size()`: Token 计数估算
- `RalphLoop._reset_context()`: 长周期任务的新鲜上下文

**缺失能力**:

- 无渐进式压缩分层
- 无智能裁剪机制
- 无上下文相关性评估

### 升级设计方案

#### 1. 渐进式上下文压缩

**设计要点**: 三层压缩策略

```python
class ProgressiveContextCompressor:
    """渐进式上下文压缩"""
    
    COMPRESSION_TIERS = {
        "recent": {"keep_lines": 5, "method": "full"},      # 最新 5 轮: 完整保留
        "medium": {"keep_lines": 10, "method": "light"},    # 稍旧 10 轮: 轻量总结
        "old": {"keep_lines": None, "method": "abstract"},  # 更早: 简短摘要
    }
    
    def compress(self, history: list[dict]) -> list[dict]:
        """应用三层压缩"""
        compressed = []
        
        # 1. 最近对话: 完整保留
        recent = history[-5:]
        compressed.extend(recent)
        
        # 2. 稍旧对话: 轻量总结
        medium = history[-15:-5]
        if medium:
            summary = self._light_summarize(medium)
            compressed.append({"role": "system", "content": f"[轻量摘要]\n{summary}"})
        
        # 3. 更早对话: 简短摘要
        old = history[:-15]
        if old:
            abstract = self._abstract_summarize(old)
            compressed.append({"role": "system", "content": f"[历史摘要]\n{abstract}"})
        
        return compressed
```

#### 2. 智能上下文裁剪

**设计要点**: 基于任务相关性裁剪

```python
class IntelligentContextPruner:
    """智能上下文裁剪"""
    
    def prune_for_task(self, history: list[dict], current_task: str) -> list[dict]:
        """根据当前任务裁剪不相关上下文"""
        # 1. 识别当前任务的关键实体
        entities = self._extract_entities(current_task)
        
        # 2. 计算每条历史消息的相关性分数
        relevance_scores = self._compute_relevance(history, entities)
        
        # 3. 保留高相关性消息
        pruned = [
            msg for msg, score in zip(history, relevance_scores)
            if score > RELEVANCE_THRESHOLD
        ]
        
        # 4. 添加裁剪说明
        if len(pruned) < len(history):
            pruned.append({
                "role": "system",
                "content": f"[裁剪说明: 已过滤 {len(history) - len(pruned)} 条低相关性历史]"
            })
        
        return pruned
```

---

## 生命周期钩子体系

### Harness 确定性生命周期钩子

**核心理念**: 在智能体生命周期的关键节点自动触发预设动作，由系统确保关键流程被执行，不依赖可能被模型遗忘的指令

| 钩子节点 | 触发时机 | 预设动作 |
|----------|----------|----------|
| `on_session_start` | 会话开始 | 加载 L1 索引、初始化上下文 |
| `on_tool_call_before` | 工具调用前 | 代码格式化、权限检查 |
| `on_tool_call_after` | 工具调用后 | 结果验证、日志记录 |
| `on_response_before` | 响应前 | 上下文裁剪、格式检查 |
| `on_response_after` | 响应后 | 记忆整理、摘要生成 |
| `on_session_end` | 会话结束 | 状态持久化、归档 L5 |

### seed-agent 当前钩子

| 钩子 | 实现 | 状态 |
|------|------|------|
| `autodream` | Scheduler 12小时任务 | ✅ 已有 |
| `autonomous_explore` | AutonomousExplorer 1小时空闲监控 | ✅ 已有 |
| `_maybe_summarize` | 对话轮数/阈值触发 | ⚠️ 部分 |
| 工具调用前后钩子 | OpenTelemetry Span | ⚠️ 部分 |

### 升级设计方案

#### 生命周期钩子注册体系

```python
class LifecycleHookRegistry:
    """确定性生命周期钩子注册中心"""
    
    HOOK_POINTS = {
        "session_start": "会话开始",
        "tool_call_before": "工具调用前",
        "tool_call_after": "工具调用后",
        "response_before": "响应生成前",
        "response_after": "响应生成后",
        "context_reset": "上下文重置时",
        "session_end": "会话结束",
    }
    
    def __init__(self):
        self._hooks: dict[str, list[Callable]] = {
            point: [] for point in self.HOOK_POINTS
        }
    
    def register(self, hook_point: str, callback: Callable, priority: int = 0) -> None:
        """注册钩子"""
        self._hooks[hook_point].append((priority, callback))
        self._hooks[hook_point].sort(key=lambda x: x[0])
    
    async def trigger(self, hook_point: str, context: dict) -> None:
        """触发钩子"""
        for priority, callback in self._hooks[hook_point]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(context)
                else:
                    callback(context)
            except Exception as e:
                logger.warning(f"Hook {hook_point} failed: {e}")
```

**内置钩子示例**:

```python
# 注册内置钩子
registry.register("tool_call_before", lambda ctx: format_code(ctx["code"]))
registry.register("tool_call_after", lambda ctx: log_tool_result(ctx["result"]))
registry.register("response_after", lambda ctx: archive_to_l5(ctx["session"]))
registry.register("session_end", lambda ctx: persist_state(ctx["state"]))
```

---

## 多智能体协作模式

### Harness 多智能体协作

| 模式 | 描述 | 适用场景 |
|------|------|----------|
| **多脑一手** | 多个 Claude 实例共享一个 Sandbox | 多角度分析同一份代码 (安全审查 + 性能优化) |
| **一脑多手** | 一个 Claude 控制多个 Sandbox | 在不同环境执行 (Python + Node.js) |
| **多脑多手** | 多个 Claude 各有 Sandbox，共享 Session 协调 | 最复杂的多步骤任务 |

### seed-agent Subagent 机制

**当前能力**:

- SubagentInstance: 独立上下文的子代理
- SubagentManager: 并行执行调度 (最大 3 个)
- RalphSubagentOrchestrator: Plan→Implement→Review 流程

**差距分析**:

- 缺少共享 Session 协调机制
- 缺少多脑一手 (共享 Sandbox) 模式
- 缺少一脑多手 (多 Sandbox) 模式

### 升级设计方案

#### 1. 多脑一手模式

```python
class MultiBrainOneHandOrchestrator:
    """多脑一手: 多个 Claude 共享一个 Sandbox"""
    
    def __init__(self, sandbox: Sandbox, num_brains: int = 2):
        self.sandbox = sandbox
        self.brains: list[LLMClient] = [LLMClient() for _ in range(num_brains)]
    
    async def analyze_from_multiple_angles(self, code_path: str) -> dict:
        """多角度分析同一份代码"""
        results = await asyncio.gather(
            self.brains[0].analyze(code_path, perspective="security"),
            self.brains[1].analyze(code_path, perspective="performance"),
        )
        
        return {
            "security_analysis": results[0],
            "performance_analysis": results[1],
            "sandbox_state": self.sandbox.get_state()
        }
```

#### 2. 一脑多手模式

```python
class OneBrainMultiHandOrchestrator:
    """一脑多手: 一个 Claude 控制多个 Sandbox"""
    
    def __init__(self, brain: LLMClient, sandbox_configs: list[dict]):
        self.brain = brain
        self.sandboxes: list[Sandbox] = [
            Sandbox(config) for config in sandbox_configs
        ]
    
    async def execute_in_multiple_environments(self, task: str) -> dict:
        """在不同环境执行任务"""
        # 1. 大脑规划
        plan = await self.brain.plan(task)
        
        # 2. 分发到多个 Sandbox
        results = await asyncio.gather(
            self.sandboxes[0].execute(plan["python_tasks"]),
            self.sandboxes[1].execute(plan["node_tasks"]),
        )
        
        return {
            "plan": plan,
            "python_results": results[0],
            "node_results": results[1]
        }
```

#### 3. Session 共享协调机制

```python
class SharedSessionCoordinator:
    """多脑多手模式的 Session 共享协调"""
    
    def __init__(self, session: SessionEventStream):
        self.session = session
        self._brain_sandbox_pairs: list[tuple[LLMClient, Sandbox]] = []
    
    def register_pair(self, brain: LLMClient, sandbox: Sandbox) -> str:
        """注册 Claude + Sandbox 组合"""
        pair_id = str(uuid.uuid4())[:8]
        self._brain_sandbox_pairs.append((brain, sandbox, pair_id))
        return pair_id
    
    async def coordinated_execution(self, task: str) -> dict:
        """协调执行"""
        # 1. 每个组合独立执行
        results = await asyncio.gather(
            *[self._execute_pair(brain, sandbox, task) 
              for brain, sandbox, _ in self._brain_sandbox_pairs]
        )
        
        # 2. 所有结果记录到共享 Session
        for result in results:
            self.session.emit_event({
                "type": "coordinated_result",
                "data": result
            })
        
        # 3. Session 协调合并
        merged = self._merge_results_from_session()
        return merged
```

---

## 工具与权限体系

### Harness 工具与权限模式

| 模式 | 描述 |
|------|------|
| **渐进式工具扩展** | 开始时只提供最必要工具，复杂工具按需动态加载 |
| **命令风险分类** | 根据命令类型、参数、影响自动评估风险等级 |
| **单用途工具设计** | 常用操作封装为专用工具，而非通用 Shell |

### seed-agent 当前实现

**已有能力**:

- SubagentPermissionSets: read_only, review, implement, plan
- SkillLoader: 渐进式披露技能索引
- ToolRegistry: 工具注册与执行

**差距分析**:

- 无命令风险分类机制
- 无动态工具扩展触发
- 部分 Shell 命令依赖 (code_as_policy)

### 升级设计方案

#### 1. 命令风险分类体系

```python
class CommandRiskClassifier:
    """命令风险分类"""
    
    RISK_LEVELS = {
        "safe": {"action": "auto_execute", "description": "无风险，自动执行"},
        "caution": {"action": "log_and_execute", "description": "轻微风险，记录后执行"},
        "risky": {"action": "request_confirm", "description": "有风险，请求确认"},
        "dangerous": {"action": "block", "description": "危险操作，直接拦截"},
    }
    
    def classify(self, tool_name: str, args: dict) -> str:
        """分类命令风险"""
        # 1. 工具类型基础风险
        tool_risk = self._get_tool_base_risk(tool_name)
        
        # 2. 参数影响分析
        impact = self._analyze_impact(tool_name, args)
        
        # 3. 综合评估
        if tool_risk == "high" or impact == "irreversible":
            return "dangerous"
        elif tool_risk == "medium" or impact == "significant":
            return "risky"
        elif impact == "minor":
            return "caution"
        return "safe"
```

**风险分类示例**:

| 工具 | 基础风险 | 参数条件 | 最终风险 |
|------|----------|----------|----------|
| file_read | low | - | safe |
| file_write | medium | mode=append | caution |
| file_write | medium | mode=overwrite, path=~/.seed/ | risky |
| file_edit | medium | - | caution |
| code_as_policy | high | language=shell, rm -rf | dangerous |
| code_as_policy | high | language=python, print() | safe |

#### 2. 渐进式工具扩展

```python
class ProgressiveToolExpander:
    """渐进式工具扩展"""
    
    BASE_TOOL_SET = {
        "file_read", "ask_user", "search_history", "read_memory_index"
    }
    
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self._expanded_tools: set[str] = set()
    
    def get_available_tools(self, context: dict) -> set[str]:
        """根据上下文动态扩展工具集"""
        available = self.BASE_TOOL_SET.copy()
        
        # 1. 根据任务类型扩展
        task_type = context.get("task_type")
        if task_type == "implementation":
            available.update({"file_write", "file_edit", "code_as_policy"})
        elif task_type == "exploration":
            available.update({"file_read", "search_memory"})
        
        # 2. 根据用户权限扩展
        if context.get("user_permission") == "full":
            available.update({"file_write", "file_edit", "code_as_policy"})
        
        return available
    
    def expand_for_complex_task(self, complexity_score: float) -> None:
        """复杂任务动态扩展"""
        if complexity_score > 0.7:
            self._expanded_tools.update({"run_diagnosis", "spawn_subagent"})
```

---

## 凭证安全架构

### Harness 凭证安全设计

**核心理念**: 凭证永不进沙盒

**架构**: 保险库 (Vault) + 代理 (Proxy)

```
┌─────────────────────────────────────────────────────────────┐
│                    Vault (保险库)                            │
│         所有第三方凭证存储在独立的保险库                        │
│         Harness 和 Sandbox 都无法直接访问                      │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ 按需获取
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Proxy (代理)                              │
│         需调用外部工具时，通过代理从保险库获取凭证               │
│         执行请求后，凭证立即销毁                               │
│         凭证始终不暴露给 Sandbox                              │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ 路由请求
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Sandbox (沙盒)                            │
│         执行环境，凭证永不进入                                 │
└─────────────────────────────────────────────────────────────┘
```

### seed-agent 当前实现

**当前状态**:

- API Key 存储于 `~/.seed/config.json`
- LLMGateway 直接解析 `${ENV_VAR}` 格式
- 执行环境 (code_as_policy) 可访问环境变量

**风险分析**:

- 凭证暴露给执行环境
- 无法审计外部调用
- 凭证无法统一轮换

### 升级设计方案

#### 凭证保险库 + 代理架构

```python
class CredentialVault:
    """凭证保险库"""
    
    def __init__(self, vault_path: Path):
        self._vault_path = vault_path
        self._credentials: dict[str, str] = {}
        self._load_credentials()
    
    def get_credential(self, provider: str, scope: str = "api_call") -> str:
        """获取凭证 (带作用域限制)"""
        # 1. 检查作用域权限
        if not self._check_scope_permission(provider, scope):
            raise PermissionError(f"Scope {scope} not allowed for {provider}")
        
        # 2. 返回临时凭证
        return self._credentials.get(provider)
    
    def rotate_credential(self, provider: str, new_credential: str) -> None:
        """轮换凭证"""
        self._credentials[provider] = new_credential
        self._persist_credentials()


class CredentialProxy:
    """凭证代理"""
    
    def __init__(self, vault: CredentialVault):
        self.vault = vault
    
    async def execute_external_request(
        self,
        provider: str,
        request_func: Callable,
        **kwargs
    ) -> dict:
        """代理执行外部请求"""
        # 1. 从保险库获取临时凭证
        credential = self.vault.get_credential(provider, scope="api_call")
        
        # 2. 执行请求
        try:
            result = await request_func(credential, **kwargs)
        finally:
            # 3. 请求完成后，凭证上下文自动清理
            # (凭证不在 Sandbox 内存中保留)
            pass
        
        # 4. 记录审计日志
        self._log_external_call(provider, kwargs, result)
        
        return result
```

**集成到 Harness**:

```python
class SecureHarness(Harness):
    """带凭证安全的 Harness"""
    
    def __init__(self, session: SessionEventStream, sandbox: Sandbox, vault: CredentialVault):
        super().__init__(session, sandbox)
        self.credential_proxy = CredentialProxy(vault)
    
    async def call_external_api(self, provider: str, **kwargs) -> dict:
        """调用外部 API"""
        return await self.credential_proxy.execute_external_request(
            provider,
            self._api_call_func,
            **kwargs
        )
```

---

## 实施路线图

### Phase 1: 核心架构解耦 (高优先级)

| 任务 | 工作量 | 依赖 |
|------|--------|------|
| SessionEventStream 实现 | 3天 | 无 |
| Harness 层分离 | 5天 | SessionEventStream |
| Sandbox 隔离层引入 | 7天 | Harness |
| CredentialVault + Proxy | 3天 | Sandbox |

**预期收益**:

- 容错能力大幅提升
- 安全隔离增强
- 首Token延迟优化

### Phase 2: 记忆系统升级 (中优先级)

| 任务 | 工作量 | 依赖 |
|------|--------|------|
| L4 用户建模层实现 | 5天 | SessionEventStream |
| L5 工作日志层实现 | 3天 | L4 |
| 五层架构集成 | 2天 | L4, L5 |

**预期收益**:

- 用户理解持续进化
- 长期知识沉淀能力

### Phase 3: 上下文工程优化 (中优先级)

| 任务 | 工作量 | 依赖 |
|------|--------|------|
| 渐进式压缩实现 | 3天 | SessionEventStream |
| 智能裁剪实现 | 5天 | 渐进式压缩 |

**预期收益**:

- 上下文利用率提升
- 长对话任务稳定性

### Phase 4: 生命周期钩子体系 (中优先级)

| 任务 | 工作量 | 依赖 |
|------|--------|------|
| LifecycleHookRegistry | 2天 | Harness |
| 内置钩子注册 | 3天 | LifecycleHookRegistry |

**预期收益**:

- 流程自动化增强
- 关键节点确定性保证

### Phase 5: 多智能体协作模式 (低优先级)

| 任务 | 工作量 | 依赖 |
|------|--------|------|
| 多脑一手模式 | 3天 | Sandbox |
| 一脑多手模式 | 3天 | Sandbox |
| Session 共享协调 | 5天 | 多脑一手, 一脑多手 |

**预期收益**:

- 复杂任务协作能力
- 多角度分析能力

---

## 附录

### A. Harness Engineering 核心模式汇总

| 模式分类 | 具体模式 |
|----------|----------|
| 持久化指令 | AGENTS.md, 作用域上下文组装 |
| 分层记忆 | L1-L5 五层架构 |
| 做梦整理 | 定期后台去重、清理、重组 |
| 渐进式上下文压缩 | 三层压缩策略 |
| 工作流编排 | 探索-规划-行动循环, 上下文隔离子智能体, 分支-合并并行 |
| 工具权限 | 渐进式工具扩展, 命令风险分类, 单用途工具设计 |
| 自动化 | 确定性生命周期钩子 |
| 架构解耦 | 三件套解耦 (Claude + Harness + Sandbox), 宠物与牲畜哲学 |
| 安全 | 凭证保险库 + 代理, 凭证永不进沙盒 |
| 多智能体 | 多脑一手, 一脑多手, 多脑多手 |
| 五段式循环 | 规划 → 执行 → 观察 → 学习 → 适应 |

### B. seed-agent 当前架构优势

| 优势 | 描述 |
|------|------|
| RalphLoop 外部验证 | 测试/DONE标志驱动完成，确定性执行 |
| Subagent 并行执行 | 独立上下文，权限隔离 |
| SQLite+FTS5 存储 | 中文全文搜索，WAL模式并发 |
| autodream 机制 | 12小时记忆整理，ROI评估 |
| AutonomousExplorer | 1小时空闲自主探索 |

---

## 讨论

本文档基于 Harness Engineering 核心模式与理念，对比分析了 seed-agent 当前架构的实现程度，提出了多个升级设计方案。

**待讨论要点**:

1. **Session 不可变事件流**: 是否需要完整实现重放能力？对现有历史管理的影响？
2. **Sandbox 隔离**: 进程级隔离 vs Docker 容器级隔离的选择？
3. **L4 用户建模**: 辩证式进化机制的复杂度是否值得投入？
4. **凭证安全**: 对现有 API Key 管理流程的改动范围？
5. **实施优先级**: 各阶段任务的依赖关系和资源分配？

请针对以上要点进行讨论，以便细化设计方案。