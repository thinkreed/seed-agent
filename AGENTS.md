项目目标是打造物理级全能进化型执行者:
具备自主进化能力，不推诿"无法操作"，优先探测解决问题，核心是任务中自主沉淀、迭代。

---

## 架构概览

### 核心组件

| 组件 | 文件 | 功能 |
|------|------|------|
| **AgentLoop** | `src/agent_loop.py` | 主执行引擎：对话生命周期管理、工具调用循环、历史压缩 |
| **LLMGateway** | `src/client.py` | 多Provider网关：FallbackChain自动降级、重试逻辑 |
| **RalphLoop** | `src/ralph_loop.py` | 长周期任务执行器：外部验证驱动完成、上下文重置防漂移 |
| **Scheduler** | `src/scheduler.py` | 定时任务调度：内置任务 + 自定义任务管理 |
| **AutonomousExplorer** | `src/autonomous.py` | 空闲自主探索：2小时触发、SOP驱动执行 |
| **SubagentManager** | `src/subagent_manager.py` | 子代理管理器：创建、调度、并行执行、结果聚合 |
| **SubagentInstance** | `src/subagent.py` | 独立上下文的子代理：权限隔离、执行循环 |
| **RateLimiter** | `src/rate_limiter.py` | 双重限流：TokenBucket + RollingWindow |
| **RateLimitSQLite** | `src/rate_limit_db.py` | 限流状态持久化（SQLite+WAL） |
| **RequestQueue** | `src/request_queue.py` | 请求队列：TurnTicket模式、优先级调度 |

### 工具系统

| 模块 | 文件 | 功能 |
|------|------|------|
| **builtin_tools** | `src/tools/builtin_tools.py` | 5个核心工具：文件读写/编辑、代码执行、用户交互 |
| **memory_tools** | `src/tools/memory_tools.py` | L1-L4记忆管理、经验沉淀 |
| **skill_loader** | `src/tools/skill_loader.py` | 动态技能加载（渐进式披露） |
| **ralph_tools** | `src/tools/ralph_tools.py` | Ralph Loop管理：启动/状态检查/完成标记 |
| **subagent_tools** | `src/tools/subagent_tools.py` | Subagent管理：创建/等待/聚合/终止 |
| **session_db** | `src/tools/session_db.py` | SQLite+FTS5会话存储（jieba中文分词） |

### Ralph Loop 机制

长周期确定性任务执行，核心特性：
- **外部验证驱动**：测试通过/标志文件/Git干净等客观标准决定完成
- **新鲜上下文**：每N轮迭代重置上下文，防止漂移
- **状态持久化**：任务状态保存至文件，支持崩溃恢复
- **安全上限**：最大1000次迭代或8小时执行时间

完成类型：
- `TEST_PASS` - 测试通过率验证
- `FILE_EXISTS` - 目标文件存在
- `MARKER_FILE` - 完成标志文件
- `GIT_CLEAN` - Git工作区干净
- `CUSTOM_CHECK` - 自定义验证函数

### Subagent 机制

独立上下文的子代理执行，核心特性：
- **独立上下文**：每个 subagent 有独立的 context window，不共享主对话历史
- **并行执行**：多个 subagent 可同时运行（默认最大 3 个）
- **权限隔离**：可配置不同权限集（read-only, review, implement, plan）
- **结果聚合**：只返回关键结果给主对话，不污染主上下文
- **超时管理**：每个 subagent 默认 5 分钟超时

Subagent 类型：
| 类型 | 权限集 | 用途 |
|------|------|------|
| `EXPLORE` | read_only | 只读探索：搜索文件、阅读代码 |
| `REVIEW` | review | 审查验证：只读 + 代码执行 |
| `IMPLEMENT` | implement | 实现执行：全权限 |
| `PLAN` | plan | 规划分析：只读 + 记忆写入 |

权限集定义：
| 权限集 | 允许工具 |
|------|------|
| `read_only` | file_read, search_history, ask_user |
| `review` | file_read, code_as_policy, search_history, ask_user |
| `implement` | file_read/write/edit, code_as_policy, memory tools, search_history |
| `plan` | file_read, write_memory, search_history, ask_user |

核心工具：
- `spawn_subagent(type, prompt)` - 创建子代理任务
- `wait_for_subagent(task_id)` - 等待任务完成
- `aggregate_subagent_results(task_ids)` - 聚合多个结果
- `list_subagents(status)` - 列出任务状态
- `kill_subagent(task_id)` - 终止任务
- `spawn_parallel_subagents(tasks)` - 并行创建多个任务

RalphLoop 与 Subagent 融合：
```
RalphSubagentOrchestrator 执行模式:
1. PlanSubagent → 分析任务、制定执行计划
2. ImplementSubagent (并行) → 执行多个子任务
3. ReviewSubagent → 验证实现质量
4. External verification → 循环或完成
```

### 定时任务

内置任务：
| 任务 | 间隔 | 功能 |
|------|------|------|
| `autodream` | 12小时 | 记忆整理与清理 |

**注意**：`autonomous_explore` 不是 Scheduler 的内置任务，而是由 `AutonomousExplorer` 类独立管理（1小时空闲监控触发）。

支持CRUD操作：`create_scheduled_task`, `remove_scheduled_task`, `list_scheduled_tasks`

### Rate Limiting System

双重限流机制，保护系统免受过载：

| 组件 | 功能 |
|------|------|
| **TokenBucket** | 令牌桶算法：平滑限流，支持突发流量 |
| **RollingWindow** | 滑动窗口算法：精确控制时间窗口内请求数 |

核心特性：
- **双重限流**：同时启用 TokenBucket 和 RollingWindow，取两者更严格限制
- **状态持久化**：使用 SQLite + WAL 模式保存限流状态
- **Provider级别**：每个 LLM Provider 独立限流配置

详细设计：[docs/rate_limiting_system_design.md](docs/rate_limiting_system_design.md)

### Request Queue System

请求队列系统，实现公平调度：

| 机制 | 描述 |
|------|------|
| **TurnTicket** | 排队票据：按到达顺序分配优先级 |
| **Priority Scheduling** | 优先级调度：VIP用户、系统任务可插队 |

核心特性：
- **公平队列**：FIFO 机制确保请求顺序
- **优先级注入**：支持系统任务和VIP用户优先
- **超时管理**：等待超时自动降级或拒绝

### 记忆层级

| 层级 | 名称 | 用途 | 存储 |
|------|------|------|------|
| L1 | 索引 | 快速参考可用SOP | `notes.md` |
| L2 | 技能 | 可复用操作流程 | `skills/*.md` |
| L3 | 知识 | 跨任务模式和原则 | `knowledge/*.md` |
| L4 | 原始 | 会话历史和日志 | **SQLite+FTS5** |

**L4 SQLite+FTS5**：使用jieba中文分词实现全文搜索，替代原JSONL文件存储。

---

## 核心权限

- **物理操作**：文件读写、脚本执行调试；
- **浏览器干预**：JS注入、页面操控及日志获取；
- **系统干预**：环境探测、工具调用，不可逆操作需确认用户；
- **进化权限**：自主记录、沉淀经验、优化策略。

---

## 行动原则

- 操作前在`<thinking>`内推演阶段、结果、问题及下一步；
- 未知/失败先探测关键信息，记录至工作记忆；
- **失败升级**：1次读错因重试，2次探测更新策略，3次换方案或询用户；
- 自主进化：总结经验、复用优化、拓展能力。

---

## 工作记忆

记录操作日志、经验库、能力清单，确保进化可追溯。

---

## 核心禁忌

- 不推诿，无方案时提建议；
- 不盲目操作，每步有逻辑并记录；
- 不忽视进化，任务结束必总结；
- 不可逆操作先和用户确认。

---

## 操作原则

- 每次从 `origin/main` 拉出一个新分支工作，工作结束合回 `origin/main`
- 发现问题，优先改动代码。
- **禁止修改 `core_principles` 目录下的文件**
- **禁止修改 `golden_rules` 目录下的文件**

---

## 文档索引

| 模块 | 文档 |
|------|------|
| 核心引擎 | [src/AGENTS.md](src/AGENTS.md) |
| 工具系统 | [src/tools/AGENTS.md](src/tools/AGENTS.md) |
| 记忆系统 | [memory/AGENTS.md](memory/AGENTS.md) |
| 自主探索 | [auto/AGENTS.md](auto/AGENTS.md) |
| 设计文档 | [docs/](docs/) |