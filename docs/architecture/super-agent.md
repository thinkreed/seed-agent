# Super-agent 设计与实现方案

> 状态：v2（2026-11-01）· 实现基线：`src/`（TypeScript，零第三方依赖，Node ≥ 22.18）
> 语言选型已定：主实现 TypeScript；端侧 daemon（P6）后续用 Rust，仍走 `ports.Executor`。
> 旧 Python 实现已全部删除，历史保留在 `main` 分支；本仓库无兼容义务。
> 依据：DeepSeek Harness 团队《Super-agent 设计探索：迈向更自主的 Agent 系统》（2026-10-31，公众号原文）与官方原型 [dsh-superagent-prototype](https://github.com/deepseek-ai/dsh-superagent-prototype) 的 `docs/000`–`docs/008`。
> 本文是实现的唯一契约：代码、测试、提示词都以此为准。

---

## 0. 目标与非目标

**目标**：在 `seed-agent` 中实现一个可运行的 Super-agent —— 常驻 Router + 并发 Worker，事件驱动、异步全双工、存算/环境分离、带外部 Watchdog。全量覆盖原文五个模块。

**非目标**（本期不做）：多租户 SaaS、跨实例 A2A 协议、端侧 daemon 的强安全边界（原文 8.4 开放问题，方案只做"凭据不进模型上下文"的最小隔离）、Web 富前端（先 CLI 面板）。

**硬约束**（贯穿全部代码，评审时逐条检查）：

| 约束 | 定义 | 违例即打回 |
|---|---|---|
| 状态单向流动 | `state' = reduce(state, event)`；只有 `Store.append()` 能改变状态；工具/执行器/渠道只产事件 | 任何模块直接改聚合对象 |
| 修改收敛单点 | 每类变更只有一个合法落点（见 §5 表） | 同类改动出现在两处 |
| 易于测试 | 端口可替换、时钟注入、回放确定、全套测试不联网不 sleep | 测试依赖真实模型/网络/时间 |

---

## 1. 原文要点（实现必须覆盖）

四特征：**连续 / 高效 / 主动 / 持久**。五模块：

1. **双层架构**：Router 常驻，只接人、持全局上下文、分派；Worker 上下文隔离、挂全套工具、**不直接对人说话**，只向 Router 汇报。Router 可用轻模型；Worker 用最强模型。
2. **事件驱动**：外部事件 = Trigger；两级过滤（程序 Fast Path → 模型 Slow Path）；Thread 聚合事件流，已订阅的后续事件**程序直通** Worker；Inline & Spill + 链式召回组织上下文；投机执行（后台先做，有价值才交付）。
3. **面向人的交互**：异步 ReAct（`start()` 立即返回 Started、`stop()` 终止、结果作为新事件回灌）实现全双工；不同信道不同输出规范（IM ≤100 词、GitHub/邮件结构化）。
4. **计算/状态/环境分离**：计算无状态、状态入库；执行环境留在原地，端侧只跑无状态 daemon（BYOM）。
5. **Watchdog**：主系统之外的独立 Control Loop，定时消息驱动；既看基础设施故障，也用模型判断 Worker 是否真推进、是否跑偏；可用自然语言运维。

原文关键量化（用于回归基线，不追精确复现）：Super-agent p50/p95 12.4/15.7 min；去直通后 Router 决策 +30%；40 msg/min 时 batch 1.0→2.8、单决定推理 6.4s→1.6s。

---

## 2. 领域模型

严格对齐原型 `docs/001-domain.md`，不自创概念。代码名保留英文，文档/面板显示中文。

| 概念 | 代码 | 中文 | 不变量 |
|---|---|---|---|
| Source | `sources/` | 来源 | 各自持有读取位点与 bot 身份；进入域前丢弃自己的消息与范围外触发；Trigger 幂等 |
| Trigger | `domain.Trigger` | 触发 | 不可变；属于一个或多个 Thread；重复受理只产生一个 Ticket |
| Thread | `domain.Thread` | 线程 | 同一时刻最多一个 Eval；可有多个 Ticket；持有订阅与决定历史 |
| Correlation | `domain.Correlation` | 关联 | 只增加上下文，绝不路由 |
| Channel | `domain.Channel` | 渠道 | Thread 的写侧；一个 Thread 可有多个 |
| Policy | `policy.Policy` | 策略 | 版本化；含每 Source 的白名单、准入表、accept 模式；版本随内容哈希变化 |
| Eval | `domain.Eval` | 评估 | 两层：Gate（确定性）+ Assessment（模型）；**无状态**，输入 Trigger 批 + Thread 快照 + Ticket 列表 + 当前 Policy，输出 Decision |
| Mandate | `domain.Mandate` | 授权 | 不可变：Policy 版本、scope、strength、命中规则、来源身份；只有人 stop 撤销，Policy 失效则吊销 |
| Ticket | `domain.Ticket` | 工单 | 仅 Eval 创建；`open → ended → open`（人 stop 的除外）；自己定义状态，不跟随 Executor |
| Assignment | `domain.Assignment` | 派工 | Ticket ↔ Executor 实例；`pending → running → ended` 独立于 Ticket |
| Subscription | `domain.Subscription` | 订阅 | Ticket ↔ Thread 多对多；ended 仍保留；人可移除 |
| Report | `domain.Report` | 报告 | progress/waiting/ready/blocked/failed/dropped，结构化，不靠自由文本推断 |
| Attention | `domain.Attention` | 待人工决定 | 结构化问题，只问一个 |
| Input | `domain.Input` | 输入 | 扇出的 Trigger、Policy 变更、resume、文本 |
| Disposition | `domain.Disposition` | 去向 | 每个 Trigger 的记录：filtered / evaluated / fanned-out |

Ticket 阶段（派生，不落库）：`person/delivery` → `person/answer` → `person/review` → `person/blocked|failed` → `working/queued` → `idle` → `working`（自上而下首个匹配，见 `fsm.py`）。

---

## 3. 单向数据流

```
Source.poll ─► Engine.ingest(trigger)
                   │  Gate(确定性)                 ┌───────────── Store ─────────────┐
                   ├─ filtered ──► Event ───────► │ events 表（append-only）        │
                   └─ candidate ─► Event(eval 批次)│ snapshots 表（缓存，可重算）    │
                                                  │ outbox 表（stored work）        │
                 reduce(state, event) ◄───────────┘ source_cursors 表
                          │
                          ├─► 只读快照 ──► Panel / 测试断言
                          └─► Effect 意图（先落 outbox，再执行）
                                   │
                                   └─ 执行结果 ──► 新事件（回到顶部）
```

规则：
1. `Store.append(event)` 是唯一写入口；Event 带 `seq`（全局单调）与 `at`。
2. `reduce()` 纯函数：无 IO、无时钟、无随机；非法转换抛 `TransitionError`。
3. Effect 只能"提议"，不得直接改状态；执行结果必须以事件形式回来。
4. 模型可见即已记录：任何进入 Worker 上下文的输入都有对应事件（`input.delivered`）。

---

## 4. 状态机

| 实体 | 状态 | 转移由 |
|---|---|---|
| Trigger | `recorded → filtered \| queued → evaluated \| fanned_out` | `trigger.filtered` / `eval.decided` / `input.fanned_out` |
| Eval | `queued → running → decided \| unavailable` | `eval.started` / `eval.decided`；同 Thread 串行 |
| Ticket | `open → ended`（人 stop 除外）；`ended → open`（人消息 resume，Mandate 需按当前 Policy 复验） | `ticket.opened/ended/resumed` |
| Assignment | `pending → running → ended` | `assignment.created/started/ended` |
| Subscription | `added → removed` | `subscription.added/removed` |
| Attention | `opened → answered` | `attention.opened/answered` |

非法转换（如 ended Ticket 在无事件情况下直接变 open）由 reducer 拒绝并抛错——测试必须覆盖。

---

## 5. 单点收敛表

| 变更类型 | 唯一落点 | 禁止出现的位置 |
|---|---|---|
| 新增/修改事件字段 | `src/events.ts` 类型表 + `src/reducer.ts` 分支 + 视图（≤3 文件） | 引擎、端口、面板里拼状态 |
| 新增 Source / Channel | `src/sources/<name>/` 一个包（实现两个端口 + 注册） | 引擎 switch、面板判断 |
| 修改受理规则 | `src/policy.ts` 规则表 或 `prompts/assessment.md` | 代码里的 if 人名单 |
| 改重试/退避/并发 | `src/effects.ts` 单表 | 各处 sleep/retry 循环 |
| 改面板展示 | `src/panel.ts`（只读快照） | reducer 里算展示字段 |
| 改 Watchdog 判据 | `src/watchdog/criteria.ts` + 提示词 | 主引擎 |
| 新增工具 | 工具 seam（端口 registry） | Worker 内部硬编码 |
| 换存储/执行器 | 实现 `ports.Store` / `ports.Executor` | 引擎内部 SQL |

架构守护测试（`tests/architecture.test.ts`）：扫描 `src/`，禁止 `node:sqlite` 出现在 `store.ts` 之外、禁止 `Date.now` 出现在 `clock.ts` 之外、禁止端口实现依赖引擎、单文件 > 210 行即失败。

---

## 6. 存储设计（SQLite）

```sql
CREATE TABLE events   (seq INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL,
                       at REAL NOT NULL, data TEXT NOT NULL);
CREATE TABLE snapshots(seq INTEGER PRIMARY KEY, state TEXT NOT NULL);   -- 可选缓存，崩溃后可从 events 重算
CREATE TABLE outbox   (id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
                       state TEXT NOT NULL,                  -- pending|done|dropped
                       attempts INTEGER NOT NULL DEFAULT 0,
                       next_at REAL NOT NULL, created_at REAL NOT NULL, last_error TEXT);
CREATE TABLE cursors   (source TEXT PRIMARY KEY, position TEXT NOT NULL, updated_at REAL NOT NULL);
```

- 事件只追加，永不更新/删除。
- 快照是缓存：`Store.rebuild()` 从 events 重放到最新 seq，校验 hash 一致。
- outbox 是 stored work：先写后做，失败按退避（2s→翻倍→60s；渠道 5s→300s），有界重试与 `dropped` 终态。

---

## 7. 事件目录（v1）

| 事件 | 携带 | 生产方 |
|---|---|---|
| `trigger.recorded` | trigger | Engine.ingest |
| `trigger.filtered` | trigger_id, reason, layer(fast/slow) | Gate / Assessment |
| `thread.declared` | thread_id, source, trigger_id | Source adapter |
| `eval.queued` / `eval.started` | eval_id, thread_id, trigger_ids | Engine |
| `eval.decided` | eval_id, decision{kind,strength,reason,rules,scope} | Assessment |
| `ticket.opened` / `ticket.ended` / `ticket.resumed` | ticket 字段 / 结果 | Engine |
| `mandate.revoked` | ticket_id, policy_version | Policy 变更 |
| `subscription.added` / `subscription.removed` | ticket_id, thread_id, kind | Engine / 人 |
| `assignment.created` / `assignment.started` / `assignment.ended` | assignment | Engine / Executor |
| `input.fanned_out` / `input.delivered` / `input.undelivered` | input, ticket_id | Engine / Effects |
| `report.recorded` | report{ticket_id,assignment_id,status,summary} | Executor |
| `attention.opened` / `attention.answered` | attention | Executor / 人 |
| `message.queued` / `message.sent` / `message.failed` / `message.dropped` | channel, address, text, reason | Effects |
| `source.failed` / `source.recovered` | source, error, count | Source runner |
| `policy.changed` | policy 版本与内容 | 人/面板 |

---

## 8. 端口与替身

| 端口 | 真实实现 | 测试替身 |
|---|---|---|
| `ports.Source` | `sources/local`（文件/脚本注入）、`sources/github`、`sources/feishu` | `FakeSource`（脚本化 Trigger） |
| `ports.Executor` | `executor.process`（子进程/daemon）、`executor.dsh`（复用旧引擎，后置） | `FakeExecutor`（可编程 Report） |
| `ports.Assessor` | `assessor.llm`（轻模型，批量判定） | `FakeAssessor`（表驱动 Decision） |
| `ports.Clock` | `clock.SystemClock` | `FakeClock` |
| `ports.Store` | `store.SqliteStore` | `store.MemoryStore`（同一契约测试） |
| `ports.Effects` | `effects.Outbox` | 同左，内存库 |

契约测试：同一套 case 跑真实实现与替身。

---

## 9. 测试矩阵

| 层 | 内容 | 目标 |
|---|---|---|
| L1 | reducer 表驱动、事件回放确定性（同事件→同快照 hash） | 毫秒级 |
| L2 | FSM：7 种 Ticket 阶段 × 非法转换 | 全矩阵 |
| L3 | Gate 矩阵：来源/白名单/强度/幂等 | 全组合 |
| L4 | Effects：退避序列、有界重试、dropped 终态、顺序性 | 用 FakeClock，无 sleep |
| L5 | 引擎端到端：Trigger → Eval → Ticket → Assignment → Report → ended | 零网络 |
| L6 | 原文场景复现：300 条消息/20 请求批处理 | 断言 batch 合并与确定性 |
| L7 | 架构守护（§5） | import/AST 扫描 |

运行：`node --test "tests/*.test.ts"`（不联网、不 sleep、<10s）。

---

## 10. 分期与验收

| 期 | 范围 | 验收 |
|---|---|---|
| **P0** 地基 | 领域模型、事件、SQLite store、reducer、FSM、effects、时钟/ID | L1–L4 全绿；`rebuild` 一致 |
| **P1** 受理 | Gate、Policy 版本、Assessment 端口、Eval 批处理、幂等 | L3 + 端到端 accept/ignore/stop |
| **P2** 执行 | Router Session 骨架、Executor 端口、Assignment、worker slot、并发上限 | 单 Ticket 全生命周期 |
| **P3** 路由上下文 | 订阅直通、Correlation、Inline & Spill、链式召回工具 | 直通正确 + 召回预算 |
| **P4** 异步交互 | 异步 ReAct（start/stop）、后台 job、全双工、多信道输出规范 | 后台运行时前台可应答 |
| **P5** 真渠道 | GitHub（gh CLI）、飞书（lark-cli 可选）、消息顺序/重试/丢弃 | 沙盒仓库端到端 |
| **P6** 存算分离 | 状态外置 + 端侧 daemon + BYOM + 执行变量 | 关 daemon→undelivered→恢复 |
| **P7** Watchdog | 定时驱动、基础设施 + 模型判进展、pause/retry/restart | 注入卡死能被纠正 |
| **P8** 面板部署 | CLI 面板（先）、配置、观测、一键启动 | 面板只列待人工项 |

---

## 11. 决策记录（ADR）

| # | 决策 | 理由 |
|---|---|---|
| A1 | 存储用 SQLite（事件表 + outbox + cursors） | 事务/幂等/重试可持久化；单机先跑通，`ports.Store` 保证可换 |
| A2 | TypeScript + Node 24（类型擦除直跑，零第三方依赖） | 与 DSH/原型同栈；`node:test`、`node:sqlite` 内置；无需 npm install 即可运行与测试 |
| A3 | 事件用判别联合 `(type, data)` + 类型表，不做 per-event 类 | 单点扩字段、JSON 即序列化、回放稳定 |
| A4 | 全量重写：旧 Python 代码已从工作区删除（`main` 保留历史） | 推倒重来，无兼容负担；需要对照时 `git show main:src/...` |
| A5 | 渠道顺序：local（脚本）→ GitHub → 飞书 | 先证明语义，再接外部凭证 |
| A6 | 面板先 CLI 只读 | 面板只回答"谁在等我"，不需要前端 |
| A7 | ID 用注入式序号（运行期可用 uuid） | 测试确定性优先 |

---

## 12. 风险与开放问题

- **P6 安全边界**：daemon 接入本地机器后，提示词注入/凭据泄露是原文 8.4 明确未解的问题；本方案只保证凭据不进模型上下文、daemon 只认白名单命令，不做强隔离。
- **Router 扩展**：先单常驻 Session + 批处理；分片/多层过滤留接口（后续 `router.ts` 可替换）。
- **长程记忆**：链式召回覆盖"近期可追溯"；跨月记忆依赖后续 Memory 设计（沿用 seed-agent memory 作为插件）。
- **成本**：多会话 token 上升（原文 +37% 量级），配置暴露并发与预算上限。

---

## 13. 术语对照

| 英文 | 中文 | 代码 |
|---|---|---|
| Super-agent | 超级智能体 | `seed` 整体 |
| Main Session / Router | 主会话 / 路由层 | `engine.router` |
| Executor / Worker | 执行器 / 执行会话 | `executor` / `worker` |
| Source / Trigger / Thread | 来源 / 触发 / 线程 | `sources/` `domain.Trigger` `domain.Thread` |
| Eval / Gate / Assessment / Decision | 评估 / 准入 / 研判 / 决定 | `engine` `policy.gate` `assessor` |
| Mandate / Ticket / Assignment | 授权 / 工单 / 派工 | `domain` |
| Subscription / Fan-out | 订阅 / 扇出 | `domain.Subscription` `engine.fan_out` |
| Report / Attention / Disposition | 报告 / 待人工决定 / 去向 | `domain` |
| Inline & Spill / Chain of Recall | 内联与溢出 / 链式召回 | `context/` |
| Watchdog | 看门狗 | `watchdog/` |
| stored work | 已存工作 | `effects/outbox` |

---

## 14. 实现状态（1.0）

| 期 | 状态 | 证据 |
|---|---|---|
| **P0 地基** | ✅ | `domain/events/reducer/fsm/store/effects/clock/ids`；回放确定性、非法转换、持久化回放哈希、退避与丢弃、阶段矩阵、架构守护测试 |
| **P1 受理** | ✅ | `policy`（Gate 矩阵 + 版本哈希）、`eval_runner`（批处理 + 幂等 + 扇出直通 + 多 Thread Correlation 订阅）、`assessor`（模型输出解析） |
| **P2 执行** | ✅ | `executor/local`（工单目录 + prepare + 子进程 + stdout 报告 + stdin 投递）、`assessor_llm` + `model`、`assessor_router`（默认常驻 Router Session）、`router`（人面向短回复，同报告只通知一次，失败退避）、Worker 内 `spawn_subagent`、Assignment/并发槽/唤醒语义 |
| **P3 路由上下文** | ✅ | `context`（Inline & Spill 视图，预算可配、同 Thread 历史内联）、`recall`（Trigger→Thread→Ticket 链式召回）、`prompts`（assessment/worker/router） |
| **P4 异步交互** | ✅ | 全链路 async；`jobs`（立即返回 jobId、协作取消、30 分钟判死、完成通知自动回灌为会话输入）；`react`（tool/start/stop/report 四动作）；`worker`（turn 进行中投递的消息下一轮消费）；`format`（IM 压缩 / 异步结构化） |
| **P5 真渠道** | ✅ | `sources/github` + `GitHubChannel`（评论回写）、`sources/feishu` + `FeishuChannel`（话题回复）、`sources/local` + `runner`（轮询/位点/逐源容错/异步 poll）；文档/邮件草稿信道 |
| **P6 存算分离** | ✅ | `executor/protocol`（daemon 协议）、`RemoteExecutor`（计算侧，`recover()` 支持设备重连重拉与补投）、`DaemonAgent` + `daemon/main`（stdio）与 `daemon/http`（跨机器 HTTP）、`executor/stdio` + `executor/http` 传输；跨进程报告回流与离线退避有测试 |
| **P7 Watchdog** | ✅ | `watchdog`（停滞/投递失败/Source 故障判据 + 模型裁定 + `ask()` 自然语言问答）、`source_health`（失败/恢复事件）、`control`（verdict → 引擎 retry、`applyPolicy()` 在线换规则）、引擎 `setPolicy/pause/resume/retry/recoverAfterRestart`、daemon 每轮巡检接线 |
| **P8 面板部署** | ✅ | `config`（JSON + 校验 + 默认值、`routerMode`）、`panel`（文本 / `--json`）、`daemon` 常驻主循环、CLI `run` / `desktop` / `daemon` / `panel` |

当前全量测试：**253 例全部通过，约 2.5s（含子进程 / HTTP daemon / 后台任务 / soak / 重试 / 故障注入 / Router 历史/建单/订阅/迟到报告/缓存统计/标题/即时确认/投机/召回/core 同步用例），零网络、零 sleep 依赖**。

## 15. 1.0 验收清单

```bash
cd seed-agent
node --test "tests/*.test.ts"   # 期望：253 pass / 0 fail
node --test tests/app_e2e.test.ts   # 受理→工单→派工→报告→回复
node --test tests/remote.test.ts    # 计算/执行分离、离线→recover
node src/cli.ts panel seed.db --json   # 期望：JSON 面板（无库时输出空表）
```

验收要点：

1. 单向状态流：所有状态仅由 `node --test` 中 reducer/回放用例保证；`store.append` 是唯一写入口。
2. 单点收敛：新增事件只需改 `events.ts` + `reducer.ts` + 视图，架构测试会校验一一对应。
3. 可测试：全部用例零网络；时间走 `clock.ts`，随机走 `ids.ts`，架构测试会扫描越界引用。
4. 端到端：`tests/app_e2e.test.ts` 覆盖"受理→工单→派工→报告→对外回复→面板"，`tests/remote.test.ts` 覆盖"计算与执行分离 + 设备重连"。

## 16. 已知限制（1.0 之后）

- **Correlation 是显式的**：一条 Trigger 可携带多个 Thread，工单订阅全部并接收任一线程的后续事件；尚未做"从内容自动推断两个 Thread 属于同一任务"的语义 Correlation。
- **Shell 工具没有强沙箱**：命令在工单目录作为 cwd 启动，但绝对路径、`gh` 等本机命令仍可调用；生产部署应叠加容器/受限用户。
- **GitHub 通知不标记已读**：靠"最新评论作者是自己则跳过"防回环；更严格的做法是处理完 `PATCH /notifications/threads/:id`。
- **GitHub 真实事件依赖第三方 actor**：自己操作不会给自己发通知；验收时用 Actions bot 评论触发。
- **凭据隔离是弱保证**：daemon 继承执行机环境变量；模型上下文不包含凭据，但没有进程级隔离（对应原文 8.4 开放问题）。
- **设备重连是显式恢复**：`RemoteExecutor.recover()` 负责重拉与补投；尚未做心跳自动探测/自动重连（需宿主定时调用）。
- **HTTP daemon 是明文 HTTP + Bearer token**：默认绑 `127.0.0.1`；跨公网部署应叠加 TLS/隧道与网络访问控制。
- **邮件/文档信道是草稿语义**：落盘 `.eml`/`.md`，不直连 SMTP 或在线文档 API。
- **Router 为单常驻逻辑会话**：评估与回复共享一个逻辑 Router；水平分片/多层过滤留了接口，未实现。
- **桌面控制台是"Edge 应用模式壳"**：独立窗口 + 无地址栏 + 独立 profile，但不是 Electron/Tauri 打包；要分发安装包需另做 installer。
- **界面复用 DSH 设计令牌而非组件**：`src/ui/web/vendor/` 原样复制 DSH 的 design tokens（MIT），布局按其真实比例重排，组件是自绘 HTML/CSS，不是 React 组件级复用。
- **控制台是单用户本机形态**：只绑 `127.0.0.1`，没有多用户/远程访问与细粒度审计（token 保护是可选弱保护）。
## 17. 真实运行（无 fake）依赖

| 能力 | 需要 | 落点 |
|---|---|---|
| 模型 | `DEEPSEEK_API_KEY`（或配置 `model.apiKeyEnv`） | `src/llm/openai.ts`（OpenAI 兼容，含超时/429/5xx 重试） |
| 工单执行 | worker 进程 + 文件/Shell 工具 | `src/worker/main.ts`、`src/tools/files.ts`、`src/tools/shell.ts` |
| GitHub | `gh auth login` | `src/sources/github_cli.ts`、`GitHubChannel` |
| 飞书 | `FEISHU_APP_ID/SECRET` + `chat_id` | `src/sources/feishu_http.ts`、`FeishuChannel` |
| 本地验证 | `inbox.jsonl` | `src/sources/jsonl.ts` |
| 装配 | 配置驱动 | `src/app.ts`、`node src/cli.ts run <config>` |

测试策略：进程内链路用真实 HTTP（本地 mock server 扮演模型端点）与真实子进程；产品代码不含任何 mock 分支。
## 18. 真实运行验收（1.0 已通过）

| 检查项 | 状态 | 证据 |
|---|---|---|
| `node --test "tests/*.test.ts"` | ✅ | 253 例全绿 |
| `pnpm run build`（dsh/） | ✅ | 10/10 gates、368 client artifacts |
| core / host smoke | ✅ | `CORE SMOKE OK`、`HOST SMOKE OK` |
| 骨架无 fake | ✅ | 产品源码不含假实现（替身仅在 `tests/`） |
| 真实模型调用 | ✅ 真机 | 百炼 token-plan 端点 `deepseek-v4.1-flash`；评估→工单→worker→报告→回复多次成功 |
| 真实 worker 进程 + 工具 | ✅ 真机 | worker 子进程用真实模型 + 文件工具写出 `hello.txt` / `feishu.txt` |
| 真实对外回复 | ✅ 真机 | 本地 Console 与飞书群消息双通道均收到"已完成"回复 |
| `gh` 登录与读取 | ✅ 真机 | `doctor` 与 `GhCliClient`（账号 thinkreed） |
| GitHub 写能力 | ✅ 真机 | 私有 gist 创建 → 真实评论（id 6451680）→ 删除（404 校验），无残留 |
| GitHub issue 评论回写 | ✅ 真机 | 产品代码 `GitHubChannel` 写入 scratch 仓库 issue：comment id 6553629857、6553794098 等，`gh` 读回一致 |
| GitHub 通知事件 | ✅ 真机 | `github-actions[bot]` 评论 → 真实通知（id 26822886716）→ `GitHubSource` 入队 → 工单 → agent 回评（issue #2 实测） |
| 飞书 token | ✅ 真机 | tenant_access_token 获取成功（应用「毛毛」） |
| 飞书发送 / 读取 | ✅ 真机 | `say` 真实消息 id `om_x100b6158...`；`read` 可读并过滤机器人/系统消息 |
| 飞书群闭环 | ✅ 真机 | 群内真人消息「帮我在工单目录创建 feishu.txt」→ 工单 t-000002 → 写出 12 字节文件 → 群里回复"已完成…" |
| Watchdog 真机 | ✅ | `scripts/live_watchdog.ts`：卡死 worker → 模型判定 intervene → 旧 assignment 结束、新 assignment 启动 |
| 重启恢复 | ✅ | `scripts/live_recovery.ts`：running assignment → 重启 → `resume` 输入投递 → worker 完成 recovery.txt |
| 崩溃安全 | ✅ | 非法事件在落库前被 reducer 拒绝；ID 工厂按历史事件预热，重启不撞号 |

## 19. 桌面控制台（参考 DSH）

目标：给"看着它跑、顺手干预"提供一个桌面窗口，而不是只能读 CLI 文本。参考 DeepSeek Harness 的三栏布局（侧栏导航 + 主对话区 + 右侧检查器），但不引入它的 React/pnpm 体系。

架构（零 npm 依赖）：

| 层 | 文件 | 职责 |
|---|---|---|
| 视图模型 | `src/ui/view.ts` | `State` → `UiState` / `UiTicketView`（纯函数，可测） |
| 服务 | `src/ui/server.ts` | `node:http` 静态资源 + JSON API + SSE；只绑 `127.0.0.1`，可选 token |
| 界面 | `src/ui/web/` | 手写 HTML/CSS/ESM；设计令牌原样复用 DSH（`web/vendor/`，MIT），三栏/气泡/composer 按其真实样式重排 |
| 桌面壳 | `src/ui/desktop.ts` | 用系统 Edge/Chrome 的 `--app=` 独立窗口（独立 profile），零依赖 |
| 装配 | `src/ui/desktop_main.ts` + `cli.ts desktop` | 引擎常驻 + 服务 + 窗口生命周期绑定 |

API：

| 路径 | 说明 |
|---|---|
| `GET /api/state` | 暂停状态、槽位、计数、工单列表（待人工优先、最近活动排序） |
| `GET /api/tickets/:id` | 工单 + 授权 + 时间线（触发/输入/报告/回复） |
| `GET /api/events?after=&limit=` | 事件流增量（界面默认隐藏 `policy.changed` 噪声） |
| `GET /api/stream` | SSE：状态变化即推送（比较 lastSeq/paused） |
| `POST /api/command` | `pause` / `resume` / `retry` / `reply`（reply 走 `engine.personMessage` 并 tick） |

状态仍是单向的：界面只调用引擎已有方法（`pause/resume/retry/personMessage`），不直接改状态；所有变更仍落为事件。

桌面壳为什么不是 Electron：`--app=` 模式给出独立窗口、无地址栏、独立 profile、任务栏图标，且复用系统 WebView2/Chromium；需要用 Electron 打包安装包时再单列一期（文档 §16 已记）。

验收截图：`docs/desktop-console.png`（真机窗口，1440×920）。