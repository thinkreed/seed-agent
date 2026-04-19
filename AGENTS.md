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
| **AutonomousExplorer** | `src/autonomous.py` | 空闲自主探索：30分钟触发、SOP驱动执行 |

### 工具系统

| 模块 | 文件 | 功能 |
|------|------|------|
| **builtin_tools** | `src/tools/builtin_tools.py` | 5个核心工具：文件读写/编辑、代码执行、用户交互 |
| **memory_tools** | `src/tools/memory_tools.py` | L1-L4记忆管理、经验沉淀 |
| **skill_loader** | `src/tools/skill_loader.py` | 动态技能加载（渐进式披露） |
| **ralph_tools** | `src/tools/ralph_tools.py` | Ralph Loop管理：启动/状态检查/完成标记 |
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

### 定时任务

内置任务：
| 任务 | 间隔 | 功能 |
|------|------|------|
| `autodream` | 12小时 | 记忆整理与清理 |
| `autonomous_explore` | 30分钟 | 空闲自主探索触发 |
| `health_check` | 1小时 | 系统健康检查 |

支持CRUD操作：`create_scheduled_task`, `remove_scheduled_task`, `list_scheduled_tasks`

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
- **禁止改动 `config\config.json`**，它已经完全配置好了。
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