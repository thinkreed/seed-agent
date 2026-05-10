# Seed Agent 项目指南

物理级全能进化型执行者：具备自主进化能力，不推诿"无法操作"，优先探测解决问题，核心是任务中自主沉淀、迭代。

---

## 目录索引

| 目录 | 文档 | 描述 |
|------|------|------|
| 核心引擎 | [src/AGENTS.md](src/AGENTS.md) | AgentLoop、RalphLoop、LLMGateway、Harness 等核心组件 |
| 工具系统 | [src/tools/AGENTS.md](src/tools/AGENTS.md) | ToolRegistry、核心工具、记忆工具、Skill Loader |
| 记忆系统 | [memory/AGENTS.md](memory/AGENTS.md) | L1-L5 五层记忆架构、Auto-Dream 整理 |
| 自主探索 | [auto/AGENTS.md](auto/AGENTS.md) | 空闲自主任务执行、Ralph Loop 集成、长期战略任务 |
| 设计文档 | [docs/AGENTS.md](docs/AGENTS.md) | Wiki 知识落地、Memory Graph、Ralph Loop、限流系统等设计 |
| 使用示例 | [examples/AGENTS.md](examples/AGENTS.md) | LLMGateway 初始化、AgentLoop 创建、工具注册示例 |
| 工具脚本 | [scripts/AGENTS.md](scripts/AGENTS.md) | JSONL 迁移、系统维护脚本 |
| 测试套件 | [tests/AGENTS.md](tests/AGENTS.md) | Ralph Loop 测试、验证机制测试 |
| 核心原则 | [core_principles/AGENTS.md](core_principles/AGENTS.md) | 系统提示、Agent 身份与约束（⚠️禁止修改） |

---

## 操作原则

- 每次从 `origin/main` 拉出新分支工作，结束后合回 `origin/main`
- 发现问题优先改动代码
- **禁止修改 `core_principles` 目录下的文件**
- **禁止修改 `golden_rules` 目录下的文件**
- **必须使用 pathlib 处理文件路径**

---

## 核心架构

### 三件套解耦架构

| 组件 | 文件 | 功能 |
|------|------|------|
| **LLMClient** | `src/llm_client/` | 大脑：负责推理，无状态，首 Token 延迟优化 |
| **Harness** | `src/harness/` | 控制器：驱动循环，路由工具，可随时创建/销毁 |
| **Sandbox** | `src/sandbox_core/` | 工作台：隔离执行环境（文件/进程/网络） |

### 核心权限

- **物理操作**：文件读写、脚本执行调试
- **浏览器干预**：JS 注入、页面操控
- **系统干预**：环境探测、工具调用
- **进化权限**：自主记录、沉淀经验、优化策略

### 行动原则

- 操作前 `<thinking>` 推演阶段、结果、问题及下一步
- 未知/失败先探测关键信息，记录至工作记忆
- **失败升级**：1 次重试，2 次探测更新策略，3 次换方案或询用户

---

## Wiki 知识落地状态

P0-P5 全部完成，详见 [docs/wiki_knowledge_integration_analysis.md](docs/wiki_knowledge_integration_analysis.md)

| 优化点 | 来源 | 实现位置 |
|------|------|----------|
| ToolKind 分类 | qwen-code | `src/tools/_types.py` |
| Circuit Breaker 熔断器 | claude-mem | `src/client/_circuit_breaker.py` |
| Orphan Reaper 孤儿回收 | claude-mem | `src/subagent_manager_core/_orphan_reaper.py` |
| Stampede Protection | worldmonitor | `src/request_queue_core/_stampede.py` |
| 复杂度评分路由 | manifest-architecture | `src/client/_complexity_scorer.py` |
| Merkle DAG 增量索引 | claude-context-docs | `src/core/_merkle_dag.py` |
| DataHub Pub/Sub | FinceptTerminal | `src/core/_datahub.py` |

---

## 核心禁忌

- 不推诿，无方案时提建议
- 不盲目操作，每步有逻辑并记录
- 不忽视进化，任务结束必总结
- 不可逆操作先和用户确认