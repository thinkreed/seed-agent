# DSH 变种 vs 《Super-agent 设计探索》——差距审计

审计日期：2026-11-01
审计对象：`seed-agent` 的 DSH fork 变种（`dsh/` + `contrib/dsh/`，桌面版）
依据：
- 文章原文：`_scratch/super-agent-article.txt`（271 行；标题《Super-agent 设计探索：迈向更自主的 Agent 系统》，DeepSeek Harness 团队，2026-10-31）。微信原文链接抓取被验证码拦截，正文以本地副本为准。
- 官方原型文档：`../dsh-superagent-prototype/docs/000–008`（语义/术语/执行/部署的对照物，**不做修改**）。
- 代码与真机证据：`contrib/dsh/packages/**`、`scripts/*-smoke.mjs`、`scripts/verify-super-agent.ps1`、`docs/dsh-desktop-*.png`。

状态记号：✅ 已实现且真机验证 ｜ ⚠️ 部分实现/仅内核未接 fork/未验证 ｜ ❌ 缺失 ｜ ➖ 非实现要求

## 1. 结论摘要

**不能声称"文章描述的 agent 已经完全做出来"。** 当前交付的是一个可运行、可验收的 **DSH 变种原型**：双层架构的骨架、两级过滤的 Slow Path、订阅直通、事件溯源、真实执行、渠道回帖、桌面工作台是真实的；但文章的四项基础特征只对上了一部分：

| 文章基础特征 | 我们的状态 | 说明 |
|---|---|---|
| 连续（跨信道一个 Agent） | ⚠️ | 单一事件库 + 工单是连续的；但没有 Router 会话、没有入站信道、跨 IM/GitHub 的 thread 映射不存在 |
| 高效（并发、不阻塞） | ⚠️ | 多工单可并发、launch 非阻塞；但 worker 回合内没有 start/stop 异步工具语义，turn 中投递未定义 |
| 主动（观察环境、自主推进） | ⚠️/❌ | 有事件驱动与直通，但 fork 里没有 Source（入站监听），也无投机执行 |
| 持久（在线、自愈） | ❌ | 只有本地 SQLite + 本地执行；无云端/端侧 daemon、无重启恢复、Watchdog 仅确定性检查 |

**覆盖度估计（工程判断，非精确度量）**：§2 双层架构 ≈50%、§3 事件驱动 ≈45%、§4 面向人的交互 ≈25%、§5 存算分离 ≈20%、§6 Watchdog ≈35%、原型语义层（001–006）≈30%。**整体 ≈30–35%**。

> **审计后进展（滚动更新）**
> - 2026-11-01：**P0-1 Router Session 完成**——常驻 Router（记忆 + 对话历史 + 跨 Thread 批处理 + recall 动作入口）落地并真机验证；§2.1-a/b/c/d 由 ❌/⚠️ 转为 ✅；覆盖度 ≈35–40%。证据：`host/src/router_session.ts`、`tests/router-smoke.mjs`（`threads:2` 一次调用）、桌面面板 Router 对话截图 `docs/dsh-desktop-router.png`。

一个重要的减负事实：**内核 `seed-agent/src` 里已有** `react.ts`（异步 ReAct）、`jobs.ts`（后台任务）、`sources/*`（飞书/GitHub/JSONL/本地入站）、`watchdog_llm.ts`（模型裁定）、`executor/{stdio,remote}`、`daemon.ts`、`recall.ts`（链式召回）。这些**没有搬进 fork**，所以多数缺口是"移植+接线"，不是"从零实现"。> - 2026-11-01：**P0-2 入站 Source 完成**——移植飞书/GitHub/JSONL 适配器到 host（src/sources/*），宿主按间隔轮询、策略放行新来源、engine 按 trigger id 幂等去重。证据：	ests/sources-smoke.mjs（JSONL 真实文件轮询：2 条事件 → 2 个工单，重复轮询不再触发）；	ests/inbound-live-smoke.mjs（飞书 24h 拉取 3 条消息、产出 1 条 human trigger；GitHub 通知 API 连通）；桌面探活 sources=feishu+github。§3-a 由 ❌ 转 ✅（admission 表/bot 白名单细节仍 P1）。> - 2026-11-01：**P0-3 链式召回（基线）完成**——host 生成 ecall-index.json（triggers/threads/tickets 引用图）并随 tick 更新；ecallContext(kind,id) 返回摘要 + 下一跳 handles（trigger→thread→ticket）；worker prompt 注入索引路径，可用读取工具逐跳展开。证据：	ests/recall-smoke.mjs（trigger→thread→ticket 逐跳）、RECALL SMOKE OK、verify 七项全绿。**仍差**：没有独立 super_agent_recall DSH 工具（模型用 read 读索引，而非 mouth-to-mouth 工具调用）。> - 2026-11-01：**P0-3 链式召回（工具版）完成**——新增 packages/super-agent/tool-recall（DSH defineTool 注册 super_agent_recall，读 SUPER_AGENT_RECALL_INDEX 索引，返回摘要+下一跳 handles）；sdk profile 以 root insert 挂载（file URL 由 apply 脚本生成）。证据：worker 真机两次调用工具 ticket→trigger 取回只存在于索引中的 marker 并落盘（RECALL TOOL SMOKE OK）；worker 工具列表包含 super_agent_recall。> - 2026-11-01：**P0-4 异步 ReAct + 全双工完成**——(1) host 执行器按工单串行回合、回合中到达的新消息排队、回合结束立即作为下一轮输入（`FULL DUPLEX SMOKE OK`：turns=2、最后 prompt 是第二条指令、队列排空）；(2) 新增 `tool-background`（`super_agent_start/status/stop`），start 立即返回 Started、后台命令继续跑、worker 继续前台工作并轮询到 done（`ASYNC REACT SMOKE OK`：jobId、running→done、后台产物存在）。
> - 2026-11-01：**P1-1 handback / unsubscribe 完成**——core 新增 `engine.unsubscribe()/handback()`（移除订阅 + 把 Thread 最新事件重新入评估队列）；host 提供 API 与文件式控制入口（tick 时 drain），worker 用 `super_agent_handback`/`super_agent_unsubscribe` 工具写请求。证据：`HANDBACK SMOKE OK`（API 交回→新工单、控制文件→再新建、Thread 只剩最新工单订阅、worker 工具列表含两个工具）。
> - 2026-11-01：**P1-2 执行语义（每工单目录 + 重启恢复）完成**——executor 改为每工单一个 DSH runtime（cwd=`<workspace>/tickets/<ticketId>`），worker prompt 注入工作目录；host 启动时调用 `recoverAfterRestart()`（收口 running assignment + 投递 resume 输入并重新派发），snapshot 暴露 `recovery`。证据：`RESTART SMOKE OK`（recovery events=2、live assignment=true）、`DSH EXECUTOR SMOKE OK`（产物落在工单目录）、全双工/异步召回 smokes 在工单目录下通过。
> - 2026-11-01：**P1-3 Watchdog 模型裁定完成**——host 构造 `LlmWatchdogJudge`（core 已有实现）交给 `Watchdog`；每次巡检记录 intervention/复查（intervene 后 15s 复查），snapshot 暴露 verdict reason/interventions/rechecks。证据：`WATCHDOG LLM SMOKE OK`——同一停滞状态，确定性模式判 intervene，模型判 "benign slowness, ok"（避免误报）；确定性路径 rechecks=1。


## 2. 逐条差距（文章 §2–§6）

### §2 双层架构

| # | 文章要求 | 我们的实现 | 状态 | 证据/位置 | 差距 |
|---|---|---|---|---|---|
| 2.1-a | 常驻 Router 层承接所有人类交互 | 只有 HTTP/面板入口触发 ingest；无 Router 会话/对话 | ❌ | host `index.ts`（assess + tick + 模板回复） | 无 Router Session，人类无法与 Router 对话 |
| 2.1-b | Router 是全局序点/协调点/记忆 | 事件库是唯一序点；全局状态可查 | ⚠️ | `core/store.ts`、`engine.ts` | 无 Router 上下文/记忆；协调只是评估+派工 |
| 2.1-c | Router 不执行具体任务、轻量模型、可不配 Bash | 确实不执行工具；但也没有 Router 模型（评估用同一配置） | ⚠️ | `assessorMode: llm` | Router 与评估器未分离 |
| 2.1-d | Trigger 积压批处理，合并进下一轮 LLM 调用 | 同 Thread 的 queued eval 会合并 trigger（`evalQueued` 累加） | ⚠️ | `core/engine.ts:126-150` | 跨 Thread 不合并；无"Router 会话排队"语义 |
| 2.1-e | 跨信道连续（IM 提方案 A，GitHub 改方案 B） | 无入站 Source，无跨信道 thread 映射 | ❌ | — | 只有出站渠道 |
| 2.2-a | Worker 上下文隔离 | 每 Ticket 独立 `DeepSeekHarness` session | ✅ | `host/executor.ts`、`sdk-smoke.mjs` | — |
| 2.2-b | Worker 完整工具、强模型 | DSH sdk profile 全工具，模型可配 | ✅ | `config/sdk-bailian.patch.yml`、桌面真机 | — |
| 2.2-c | Worker 不直接对人说话，由 Router 统一回复 | Worker 只产 report；渠道文本由模板拼接后发送 | ⚠️ | `core/router.ts` TemplateComposer | 没有 Router 改写/润色/按信道定制 |
| 2.2-d | Worker 之间不直接通信，靠 Thread 订阅获知 | 架构上无点对点通道，订阅扇出分发 | ✅ | `fanout-smoke.mjs` | — |
| 2.2-e | Worker 内部可再开 Subagent/Team | DSH 默认带 subagent 工具，未配置 worker preset | ⚠️ | 未验证 | 未按 Worker 预设（工具集/等待上限）配置 |

### §3 事件驱动

| # | 文章要求 | 我们的实现 | 状态 | 证据/位置 | 差距 |
|---|---|---|---|---|---|
| 3-a | 接入群聊/邮件/日程/GitHub/CI 的 Trigger 监听 | fork host 无 Source；内核 `src/sources/*` 有实现 | ❌ | `kernel src/sources/{feishu,github,jsonl,local}.ts` | 未移植；入站完全缺失 |
| 3.1-a | Fast Path 程序策略：来源/群组/发送者白名单/机器人列表，分"仅明确请求/候选/忽略" | `gate()` 有 sender 白名单 + 按 source/actor 的 allow/deny 规则 | ⚠️ | `core/policy.ts` | 缺 mention/direct、群组 scope、bot 列表、admission 表 |
| 3.1-b | Slow Path 语义策略，提示词可开关/扩展 | `LlmAssessor` + assessment prompt | ⚠️ | `assessor-smoke.mjs` | 提示词硬编码在 core，不能运行时增删策略 |
| 3.1-c | Eval 输入批 Trigger+Thread 快照+全部 Ticket+Policy；输出 Decision；无状态 | 完全一致 | ✅ | `core/ports.ts`、`eval_runner.ts` | — |
| 3.2-a | Thread = 同 PR / IM 话题 / 邮件串事件流 | threadId 由调用方给；fork 无 source 映射 | ⚠️ | `fanout-smoke.mjs`（人工 threadId） | 真实 thread 生成缺失 |
| 3.2-b | 初始事件经 Router 创建 Ticket 并建立订阅 | `eval` accept → ticket + subscription(own) | ✅ | `core/eval_runner.ts` | — |
| 3.2-c | 后续事件 Fast Path 直通已订阅 Worker | `subscribedTickets` → `fanOut` + deliver 效果 | ✅ | `fanout-smoke.mjs`（`trg-second → fanned_out`） | — |
| 3.2-d | Worker 可取消订阅 / 交回 Router 重新分派 | 无 handback/unsubscribe 动作 | ❌ | `core/actions.ts` 无对应事件 | 完全缺失 |
| 3.2-e | Thread 与 Worker 多对多订阅 | thread→多 ticket ✅；ticket→多 thread 仅 own 一条，context 类型无入口 | ⚠️ | `core/domain.ts` `SubscriptionKind = own/context` | 无 attach/context 订阅工具 |
| 3.2-f | 未订阅事件 Router 仍观测但只判断新事件 | 所有 trigger 落库；gate/eval 只处理未订阅的 | ✅ | `engine.ingest` | — |
| 3.2-g | 输出统一由 Router 回复并同步全局记忆 | report → 模板 compose → 渠道 | ⚠️ | `core/router.ts` | 无记忆同步/摘要 |
| 3.3-a | 从 ID+摘要开始；逐步 inline 关联 ID 与时空相邻内容 | `buildView` 有 handles/summary，仅用于评估 | ⚠️ | `core/context.ts` | Worker 侧无 inline |
| 3.3-b | 超上限 Spill：截断+保留续读入口 | 评估视图有 handle；worker 指令落盘给路径 | ⚠️ | `tests/spill-smoke.mjs` | 只有一跳、只有指令文本 |
| 3.3-c | 对象唯一 ID 构成引用图（Trigger/Thread/Session） | ID 体系有；引用只有 ticket.threadIds/mandate.triggerId/channelIds | ⚠️ | `core/domain.ts` | 无 Worker Session ID、无 Correlation |
| 3.3-d | 链式召回：recall 工具逐跳展开 | 内核 `recall.ts` 已实现 trigger→thread→ticket 逐跳；fork 未暴露工具 | ❌ | `kernel src/recall.ts`；fork 未接 | Worker/Router 都无法调 recall |
| 3.4 | 投机执行：后台提前尝试，有价值才交付（静默复现并修复） | 无 | ❌ | — | 完全缺失 |

### §4 面向人的交互

| # | 文章要求 | 我们的实现 | 状态 | 证据 | 差距 |
|---|---|---|---|---|---|
| 4.1-a | 异步 ReAct：start()/stop()、Started 通知、后台完成投递事件 | 内核 `react.ts` 实现；fork 改用 DSH session，未启用 start/stop 语义 | ⚠️/❌ | `kernel src/react.ts`、`jobs.ts` | worker 回合仍是同步 run |
| 4.1-b | 全双工：后台任务期间可响应新输入 | 新事件可 fan-out 入库；turn 进行中的 deliver 语义未定义 | ⚠️ | `executor.ts` 并发风险 | 无队列/抢占/yield |
| 4.2-a | IM 低打扰：只在决策/验收时说话，≤100 词 | 渠道会发 report 摘要；无长度/时机约束 | ⚠️ | `channels.ts`、`router.ts` | 无按信道提示词/格式 |
| 4.2-b | GitHub/邮件结构化异步交付（PR/评审规范） | 只能 `gh issue comment` | ⚠️ | `channels.ts` | 无 PR 创建、结构化模板 |

### §5 计算、状态与环境分离

| # | 文章要求 | 我们的实现 | 状态 | 差距 |
|---|---|---|---|---|
| 5.1 | 计算与状态分离（无状态计算 + 持久会话库，云端在线） | 有 seam（SQLite 存状态、executor 执行），但全在本机 | ⚠️ | 无云端/水平扩展；重启恢复未接 |
| 5.2 | 计算与执行环境分离（端侧轻量 daemon，BYOM） | fork 无 daemon；内核有 `executor/{stdio,remote}` 与 `daemon.ts` | ❌ | 未移植/未接 |

### §6 Watchdog

| # | 文章要求 | 我们的实现 | 状态 | 证据 | 差距 |
|---|---|---|---|---|---|
| 6-a | 主系统外独立 Watchdog Session，定时消息驱动 | host `setInterval` + 确定性 `Watchdog.check` | ⚠️ | `smoke.mjs`（watchdog ok 0） | 不是 agent session，无独立上下文 |
| 6-b | 模型判断 Worker 进展/偏航 | 内核 `LlmWatchdogJudge` 未接 | ❌ | `kernel src/watchdog_llm.ts` | 只做 stalled/undelivered |
| 6-c | 介入修复、外部故障持续复查 | intervene 只做 retry + tick | ⚠️ | `index.ts: checkWatchdog` | 无复查策略/修复动作 |
| 6-d | Watchdog 可被自然语言询问、在线改主系统行为 | 无 | ❌ | — | 完全缺失 |

### §7/§8

➖ §7 实验（消融、Router 批处理压测）与 §8 开放问题不是实现要求；但 §7 的 benchmark 可用于后续量化验收，暂未复现。

## 3. 原型文档层（001–008）的语义差距

| 文档 | 关键语义 | 状态 | 差距 |
|---|---|---|---|
| 001 domain | Ticket stages（person/delivery…working）、Mandate 不可变、Assignment 独立、Subscription own/context、Correlation、Source 读位置、Policy 版本、Eval 无状态 | ⚠️ | stages 已算（`fsm.ts`）但面板不展示；Correlation、Source 读位置缺失；Subscription 只有 own 主链路 |
| 002 authorization | mention/direct 准入表、bot 列表、routing candidates、handback、resume/stop 规则、Policy 重新校验 | ❌/⚠️ | 准入表与 bot 列表缺失；handback 缺失；resume 有、stop/重新校验不完整 |
| 003 execution | 每 Ticket 独立目录与 `worker-<id>` 会话、worker slot/后台工作 30 分钟上限、并发、merge、重启恢复、stored work、channel failure | ⚠️ | 共享 workspace；无 slot/后台/merge；重启恢复未接；outbox 有 |
| 004 prompts | 提示词分层拼装、优先级、版本 | ❌ | 固定字符串，无分层/版本 |
| 005 panel | 三个问题、tabs、设置组、搜索、管理 API | ❌/⚠️ | 只有工单列表+时间线+四个动作 |
| 006 deployment | 安装、账号、setup 检查、管理 API、升级、小时巡检 | ❌ | 开发模式启动，无安装/巡检 |
| 007 architecture | 模块/依赖规则/测试矩阵/持久化/配置热载 | ⚠️ | 我们是插件式变种，结构不同；host 缺单测 |

## 4. 修复路线（按优先级）

### P0 —— 对齐文章核心语义（决定"是不是同一个东西"）
1. **Router Session**：新增 `packages/super-agent/router`（或 host 内的 Router session）：常驻、承接人交互、批量消费 Trigger、统一对外回复；评估器从"一次性 judge"升级为 Router 决策的一步。
   验收：面板可与 Router 对话；两条不同 Thread 的 Trigger 在同一轮 Router 输入里被批处理（日志/测试可见）。
2. **入站 Source**：移植内核 `sources/*` 到 host（飞书轮询、GitHub 通知），含 bot 自身消息过滤、读位置、thread 映射。
   验收：真实群消息 → Trigger → Thread → 工单；重放不重复。
3. **链式召回工具**：把 `core/recall.ts` 暴露成 DSH tool（Router 与 Worker 都可用），补 session/correlation 引用。
   验收：worker 能从 trigger id 逐跳取到 thread → ticket → 关联 thread。
4. **异步 ReAct / 全双工**：接 DSH 后台任务（start/stop 或 jobs），turn 中到达的输入排队、在下一步处理；禁止并发 race。
   验收：长命令运行期间发第二条消息，不中断且被处理。

### P1 —— 执行语义与自愈
5. **handback/unsubscribe**：Worker 交回超范围事件；取消订阅。
6. **执行语义补全**：每 Ticket 目录、worker slot/后台期限、重启恢复（`recoverAfterRestart`）。
7. **Watchdog 升级**：独立 session + `LlmWatchdogJudge` + 渠道告警 + 复查。
8. **投机执行**："静默复现并修复"策略：后台 ticket，价值判定后交付/丢弃。
9. **面板**：stage、Router 对话、搜索、设置、事件详情。

### P2 —— 交付形态与量化
10. 多信道交付规范（IM ≤100 词、GitHub PR 结构化）。
11. 存算分离部署（daemon/远端 executor；内核已有 `stdio/remote` 可移植）。
12. 复现 §7 实验（消融 + 批处理压测），作为量化验收。
13. 桌面打包安装包；品牌补全（hero/托盘/安装包元信息）。

## 5. 审计方法与复现

```powershell
# 文章与原型
notepad _scratch/super-agent-article.txt
dir ../dsh-superagent-prototype/docs

# 我们的实现
dir contrib/dsh/packages/super-agent/{core,host}
dir contrib/dsh/packages/client/ui-super-agent

# 真机证据（当前全绿）
pwsh -File scripts/verify-super-agent.ps1 -Slow
```

**证据边界**：本审计基于上述本地文件与真机测试输出；微信原文因验证码未能在线抓取，若本地副本与线上版本有差异，需重新比对对应条目。