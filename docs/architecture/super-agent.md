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

运行：`node --test`（不联网、不 sleep、<1s）。

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

## 14. 实现状态（滚动更新）

| 期 | 状态 | 证据 |
|---|---|---|
| **P0 地基** | ✅ 完成 | `src/domain.ts` `events.ts` `reducer.ts` `fsm.ts` `store.ts` `effects.ts` `clock.ts` `ids.ts`；测试：reducer 回放确定性、非法转换、store 持久化/回放哈希、effects 退避与丢弃、FSM 阶段矩阵、架构守护 |
| **P1 受理** | ✅ 完成（LLM 适配器待接） | `src/policy.ts` Gate 矩阵与 Policy 版本；`src/eval_runner.ts` 批处理 + 幂等 + 扇出直通；测试：Gate 7 例、批处理合并、订阅直通、ignore/stop |
| **P2 执行** | ✅ 完成 | `src/executor/local.ts`（工单目录 + prepare + worker 子进程 + stdout JSON 报告回收 + stdin 投递）、`src/model.ts` + `src/assessor_llm.ts`（模型端口 → Inline&Spill 视图 → 决策）、`src/router.ts`（人面向的短回复，同报告只通知一次、失败走 outbox 退避）、Assignment/并发槽/唤醒语义 |
| **P3 路由上下文** | ◐ 核心完成 | `src/context.ts` Inline & Spill 视图、`src/recall.ts` 链式召回（Trigger→Thread→Ticket）、`src/prompts.ts` 评估/执行/路由提示词、`src/assessor.ts` 模型输出解析；测试：截断/Spill/句柄/召回预算/决策解析。Correlation 与 Eval 侧接线待做 |
| **P4 异步交互** | ◐ 核心完成 | 全链路 async；`src/jobs.ts` 后台任务注册表（协作取消、30 分钟判死、完成通知）；`src/react.ts` 异步 ReAct 循环（`tool`/`start`/`stop`/`report` 四种动作）；测试：任务生命周期、stop 取消、deadline、ReAct 全路径。前台中断式全双工与后台唤醒待接 |

| **P5 真渠道** | ◐ GitHub 完成 | `src/sources/github.ts`（通知 → Trigger/Thread，仓库与 reason 过滤）、`GitHubChannel`（评论回写）、`src/sources/local.ts` + `src/runner.ts`（轮询/位点/逐源容错）；飞书 IM 与真实 `gh` 客户端待接 |
| **P6 存算分离** | ◐ 核心完成 | `src/executor/protocol.ts`（daemon 协议）、`RemoteExecutor`（计算侧只发指令收报告）、`DaemonAgent`（执行侧无状态，本地跑命令并回推报告）；测试：端到端报告回流、daemon 离线→outbox 退避→恢复。stdio/网络 transport 与凭据隔离待补 |
| **P7 Watchdog** | ◐ 判据与动作完成 | `src/watchdog.ts` 判据 + 模型裁定；引擎提供 `pause()/resume()/retry()/recoverAfterRestart()`；测试：暂停不派工、重试重新派工、重启收口并留恢复注记。自动接线（verdict → 动作）待做 |
| **P8 面板部署** | ◐ 配置与观测就绪 | `src/config.ts`（JSON 配置 + 校验 + 默认值）、`src/panel.ts` 文本/JSON 两种输出、`src/daemon.ts` 常驻主循环、CLI 演示；一键部署与运维文档待补 |

当前全量测试：**128 例全部通过，约 2s（含子进程/daemon 用例），零网络**。

| 验证命令 | 期望 |
|---|---|
| `node --test` | 128 pass / 0 fail |
| `node src/cli.ts` | 打印 17 条事件、1 张工单 ended、回放哈希、1 条对外回复 |
| `node src/cli.ts panel <db>` | 打印面板（只列待人工项） |