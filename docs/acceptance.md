# 对照文章的总验收（Super-agent 设计探索 → DSH fork 变种）

文章：DeepSeek Harness 团队《Super-agent 设计探索：迈向更自主的 Agent 系统》（2026-10-31）
实现：`seed-agent` 仓库中的 DSH fork 变种（`contrib/dsh/**` + `scripts/**` + `docs/**`）
验收命令：`pwsh -File scripts/verify-super-agent.ps1 -Slow`（可选 `-Network` 追加真实飞书/GitHub）

状态说明：✅ 已实现且可验证 ｜ ⚠️ 有实现但有明确边界 ｜ ❌ 未实现（在已知边界列出）

## 0. 文章 §1 四个基础特征

| 文章要求 | 实现 | 证据 | 状态 |
|---|---|---|---|
| 连续：跨信道、跨会话连续 | Thread + Ticket 多信道 `channelIds`；Trigger 可携带多个 Thread（IM+GitHub 同任务）并订阅全部；Router 常驻记忆/对话；人消息 `resume` | `tests/correlation.test.ts`（多 Thread 订阅与直通）、`tests/router.test.ts`、host Router 对话 | ✅ |
| 高效：快速响应 + 多任务并发 | 同一 tick 多 Thread 批量评估；Worker slot 并发；全双工排队 | `docs/bench-super-agent.md`；`tests/session_inputs.test.ts` | ✅ |
| 主动：观察环境并主动推进 | Source 轮询（飞书/GitHub/JSONL）+ Gate + 模型判定 + 投机执行 | `tests/runner.test.ts`、`SOURCES SMOKE OK`、`SPECULATION SMOKE OK` | ✅ |
| 持久：在线、接真实环境、异常自愈 | SQLite 事件库 + 重启恢复 + 端侧 daemon + Watchdog | `tests/store.test.ts`、`tests/daemon.test.ts`、`tests/remote.test.ts` | ✅ |

## 1. 文章 §2 双层架构

| 文章要求 | 实现 | 证据 | 状态 |
|---|---|---|---|
| 常驻 Router 层承接人类交互 | `RouterSession`（记忆、对话历史、`chat`、`observe` 全事件观测）；内核 `assessor_router` 默认启用，`routerModel` 可配轻量模型，`routerMode=off` 退回单次评估 | `tests/router_session.test.ts`、`tests/app_e2e.test.ts`、`ROUTER SMOKE OK`、面板 Router 对话截图 | ✅ |
| Router 全局序点 / 批处理 | 同一 tick 多 Thread 合并为一次模型调用 | `docs/bench-super-agent.md`：批量 1 call/43ms vs 串行 4 calls/179ms | ✅ |
| Router 不执行具体任务 | Router 只做决策/回复；工具在 Worker | 代码分层 + 面板对话 | ✅ |
| Worker 上下文隔离、完整工具 | 每 Ticket 独立 DSH runtime + 工作目录；内核 Worker 内置 `spawn_subagent` | `DSH EXECUTOR SMOKE OK`、`RESTART SMOKE OK`、`tests/subagent_tool.test.ts` | ✅ |
| Worker 不直接对人说话，Router 统一回复 | Worker 只产 report；出站由 Router/模板 + 信道格式化 | `CHANNELS SMOKE OK` | ✅ |
| Worker 间不直接通信，靠订阅获知 | 订阅扇出、无点对点通道；同一 Thread 可被多个 Worker 订阅 | `FANOUT SMOKE OK`、`tests/correlation.test.ts`（两个 Worker 同时收到同一事件） | ✅ |
| 多对多订阅 / handback | 订阅 + `handback/unsubscribe` | `HANDBACK SMOKE OK`（交回→新工单） | ✅ |

## 2. 文章 §3 事件驱动

| 文章要求 | 实现 | 证据 | 状态 |
|---|---|---|---|
| Trigger 源接入（IM/GitHub） | 飞书/GitHub/JSONL Source + 轮询 + bot 自消息过滤 + 幂等 | `SOURCES SMOKE OK`、`INBOUND LIVE OK`（飞书 3 消息/1 trigger）、桌面 `sources=feishu+github` | ✅ |
| Fast Path 程序准入 | Gate（sender 白名单 + source/actor 规则 + 可选 mention 门槛） | `HOST SMOKE OK`、`tests/policy_mention.test.ts`、`tests/watchdog_ops.test.ts`（已订阅 Thread 仍过 Gate） | ✅ |
| Slow Path 语义策略 | LLM Router/assessor 判定 | `ROUTER SMOKE OK`（建单/闲聊） | ✅ |
| Thread 概念与路由（订阅直通） | threadId → 订阅 → 直通 Worker | `FANOUT SMOKE OK` | ✅ |
| 未订阅事件由 Router 观测 | 全部 Trigger 落库；`RouterSession.observe` 把含直通 Worker 的事件写入全局记忆（不触发模型） | `FANOUT SMOKE OK`、`tests/router_session.test.ts`（observe 不发模型调用） | ✅ |
| Inline & Spill | 指令超限落盘 + prompt 给路径；同 Thread 历史事件内联为相邻上下文；召回索引 | `SPILL SMOKE OK`、`tests/context.test.ts`（history 内联） | ✅ |
| 链式召回（trigger→thread→ticket） | `super_agent_recall` DSH 工具 + 索引 | `RECALL SMOKE OK`、`RECALL TOOL SMOKE OK`（worker 逐跳取回索引-only marker） | ✅ |
| 投机执行（有价值才交付） | 内核 `Speculator`（来源/去重/并发/超时/交付闸门）+ `reactSpeculationRunner`；host `speculate()`/`speculationSources` 复用 core Speculator，DSH runtime 执行 | `tests/speculation.test.ts`、demo §3.4、`SPECULATION SMOKE OK` | ✅ |

## 3. 文章 §4 面向人的交互

| 文章要求 | 实现 | 证据 | 状态 |
|---|---|---|---|
| 异步 ReAct start/stop，Started 不阻塞 | `super_agent_start/status/stop` 后台命令工具 | `ASYNC REACT SMOKE OK`（start 立即返回、running→done） | ✅ |
| 后台完成自动作为新事件回到会话 | 内核 `JobRegistry.nextNotice()` + `WorkerSession`；DSH host `super_agent_start` 完成写控制请求 → `drainControl` 以 `reply` 注入会话 | `tests/session_inputs.test.ts`；`tool-background` + `index.ts::drainControl` | ✅ |
| 全双工：后台工作期间可接新指令 | 回合中消息排队；`ReactLoop.nextInputs` 在每个推理步前注入，`WorkerSession` 自动排空 | `FULL DUPLEX SMOKE OK`、`tests/react_inputs.test.ts`（下一推理步即看到新输入） | ✅ |
| IM 低打扰（≤100 字） | `format.ts` IM 压缩、去 Markdown；Router `chat(channel="im")` 注入 IM 交互规范 | `CHANNEL FORMAT SMOKE OK`（94 字）、`tests/channels_outbox.test.ts`、`tests/router_session.test.ts`（async 规范） | ✅ |
| GitHub/异步信道结构化 | 标题/结论/落款结构化交付；`chat(..., "async")` 注入结构化规范；邮件草稿与文档信道 | `CHANNEL FORMAT LIVE OK`；`tests/channels_outbox.test.ts`（`.md`/`.eml`） | ✅ |

## 4. 文章 §5 计算、状态与环境分离

| 文章要求 | 实现 | 证据 | 状态 |
|---|---|---|---|
| 计算与状态分离 | host 无状态逻辑 + SQLite 事件库；重启恢复 | `RESTART SMOKE OK`（recovery events=2、live assignment） | ✅ |
| 计算与执行环境分离（端侧 daemon） | 无状态 daemon（exec/read/write、token、路径约束）+ `super_agent_remote_*`；多设备 `SUPER_AGENT_DAEMONS` + `device` 参数；内核 HTTP 传输与 `cli daemon` | `DAEMON SMOKE OK`；`tests/remote_http.test.ts`（跨网络执行 + token 拒绝） | ✅ |
| 间歇在线设备（重新上线后继续） | `HttpTransport.onReconnect` 自动触发 `RemoteExecutor.recover()` 重拉未结束 Assignment + 补投未确认输入；daemon 幂等收口旧执行器 | `tests/remote.test.ts`（离线→recover）、`tests/remote_http.test.ts`（恢复触发 onReconnect） | ✅ |

## 5. 文章 §6 Watchdog

| 文章要求 | 实现 | 证据 | 状态 |
|---|---|---|---|
| 主系统外巡检 | 定时确定性 findings（stalled/undelivered/source 故障） | `HOST SMOKE OK`（watchdog ok 0）；`tests/source_health.test.ts`（失败/恢复事件 + source finding） | ✅ |
| 模型判断是否要介入 | `LlmWatchdogJudge`（内联，带最近报告/原始请求，判断进展与偏离）+ `DshWatchdogJudge`（独立 DSH session） | `WATCHDOG LLM SMOKE OK`、`tests/watchdog_llm.test.ts`（无 finding 但有 open 工单也裁定）；`WATCHDOG SESSION SMOKE OK` | ✅ |
| 介入与复查 | retry + 15s 复查 + intervention 记录 | 同上（rechecks=1） | ✅ |
| 被自然语言询问/在线改行为 | `Watchdog.ask()`（确定性摘要 / LLM 顾问）；`Engine.setPolicy()`；host `watchdog`/`policy` 命令；面板 Watchdog 问答框 + 策略 Apply | `tests/watchdog_ops.test.ts`；面板 `SuperAgentPanel.tsx`（Ask/Apply） | ✅ |

## 6. 文章 §7 实验

| 内容 | 实现 | 证据 | 状态 |
|---|---|---|---|
| Router 批处理定量 | 确定性假模型 + 可选真实模型 | `docs/bench-super-agent.md`（≈4×；真实 3 threads 1 call） | ✅ |
| 消融（4 形态：Super-agent / 去直通 / 单 session 中性 / 优先委派） | 机制级时间线模拟（20 工作、5s/条、5 次运行） | `docs/bench-super-agent.md`（p50/p95、决策数、token 代理）；`node scripts/bench-super-agent.mjs` 零 DSH 依赖可复跑 | ✅（机制级） |

## 7. 原型文档 001–008 的语义

| 文档 | 覆盖 | 状态 |
|---|---|---|
| 001 domain | Ticket stages、Mandate、Assignment、Subscription、Policy 版本、Eval 无状态、多 Thread Correlation | ✅（显式多 Thread 订阅；语义自动关联未做） |
| 002 authorization | Gate/LLM 两级、handback、resume、mention 门槛与 sender 白名单 | ✅（`tests/policy_mention.test.ts`） |
| 003 execution | 工单目录、执行器隔离、重启恢复、outbox | ⚠️（worker slot 用 `slots`；后台期限依赖 watchdog） |
| 004 prompts | 评估/Worker/Router 提示词 | ⚠️（无分层/版本拼装） |
| 005 panel | 工单/时间线/搜索/stage/配置摘要/Router 对话 | ⚠️（设置页与事件跳转未做） |
| 006 deployment | 一键桌面脚本、隔离 DSH_HOME、验收脚本 | ✅ |
| 007 architecture | 插件化模块、host/executor/channels 分层 | ✅ |
| 008 cookbook | 新增 Source 的路径可复制 | ✅ |

## 8. 桌面交付

| 项 | 状态 | 说明 |
|---|---|---|
| 桌面应用（Electron） | ✅ | 窗口标题/侧栏品牌 `seed-agent`，Super-agent 面板 |
| 品牌：productName/协议名 | ✅ | apply 脚本把安装包 `productName`/协议名替换为 `seed-agent` |
| 品牌：hero/托盘/安装包图标 | ⚠️ | hero 文案与托盘图标仍是 DSH 原样 |
| 安装包 | ✅（首启挂载 Super-agent，待重打） | bundle 已进 runtime 闭包；首次创建 profile 自动挂载 host+UI（dev 等价验证：dump-config 出现两行、`/super-agent/state`=200）。打包产物的物理 runtime 复制与安装包重打待完成（`docs/packaging.md`）；本机 Smart App Control 拦截未签名新 exe |

## 9. 已知边界（诚实清单）

1. 链式召回是一跳/索引式的：工具可逐跳展开，但没有按事件 id 的多级持久索引与自动摘要压缩。
2. Correlation 是显式的：Trigger 可携带多个 Thread，工单订阅全部；尚未从内容自动推断两个 Thread 属于同一任务。
3. 异步 ReAct 的后台完成事件：内核 `WorkerSession` 自动回灌；DSH host 通过 `super_agent_start(..., ticketId)` 写控制请求、`drainControl` 以 `reply` 注入会话（依赖模型传 ticketId，未接 DSH 原生异步工具事件）。
4. Router 是单个常驻会话；未做文章提到的多层过滤/分片。
5. 面板已提供 Watchdog 问答与策略 Apply（纯文本 JSON），尚无图形化规则编辑器和历史回滚。
6. 面板缺设置页、事件详情跳转；工单搜索仅本地过滤。
7. 邮件/文档信道是"草稿"语义（`.eml`/`.md` 落盘），不直连 SMTP 或在线文档 API。
8. daemon 覆盖 stdio 与 HTTP 两种传输和 exec/read/write；`recover()` 支持设备重连后重拉与补投；未做 SSH/远端沙箱与凭证管理。
9. 打包：无签名、无自动更新；hero/托盘品牌未改。
10. benchmark 是机制级（假模型固定延迟），不是真实模型能力对比。

## 9.1 文章 §8 的开放问题（明确非验收项）

文章第 8 节把以下问题列为开放问题，本实现只保留接口/最小隔离，不作为"未实现"：
跨实例 A2A 与上下文边界（8.3）、跨月长程记忆（8.1）、Router 水平分片/多层过滤（8.1）、
端侧强安全隔离与凭据使用（8.4）、脱离 Session 后的产品化交互（8.2）。

## 10. DSH fork 构建验收（2026-11-02）

- `pnpm run build`：**10/10 gates passed**（native addon / Host Typert / host compiler / Host bundle / host aggregate / Desktop bundle / client compiler / Client bundle / client aggregate / Web build），368 个 client artifact。
- `node scripts/smoke-super-agent.mjs` → `CORE SMOKE OK`（12 events、工单/派工、回放哈希）。
- `dsh/packages/super-agent/host/tests/smoke.mjs` → `HOST SMOKE OK`（工单、launch、watchdog）。
- 真实模型 smoke（2026-11-02，`BAILIAN_API_KEY` 经 gitignore 的 `seed.env` 注入）全部通过：
  `SDK EXECUTOR`、`SPECULATION`、`ASYNC REACT`、`FULL DUPLEX`、`DAEMON`、`ROUTER`、`ASSESSOR`、`WATCHDOG LLM`、`WATCHDOG SESSION`、`RECALL TOOL`。
- host 侧投机执行使用 core `Speculator` + DSH `runStandalone`；首次冷启动曾触发 SDK 10s 初始化超时，host 已显式设 `initializeTimeoutMs=30s` 后稳定通过。
- 内核真实模型链路（`node src/cli.ts run <cfg> --once`）：Router 受理 → Worker 子进程 → 真实模型调用 → 工具写文件；产物 `work/t-000001/kernel-real.txt` 内容为 `ok`，工单结束并对外回复。
- 飞书真机（2026-11-02）：`CHANNELS SMOKE OK` 群回复 message id `om_x100b61bcf475f0acdf704d1264b1e7c`；`CHANNEL FORMAT LIVE OK` 同时发出飞书 `om_x100b61bcf72420a0de4f1c6d02c6ba8` 与 GitHub 评论 `gh-thinkreed/seed-agent-e2e-3`；`INBOUND LIVE OK`（飞书 24h 3 条系统消息、0 条人类 trigger；GitHub 通知 0 条）。
- 飞书「提问→Router 直接回复」真机：用户问“现在下一代agent这事情咋样了”，Router 产出 `reply` 决策（不建工单），outbox 发送成功（`sentMessages=msg-000001`，无 message error）。

## 11. 复现命令

```powershell
pnpm --dir dsh install
pwsh -File scripts/apply-dsh-patches.ps1 -Repo .
pwsh -File scripts/desktop-super-agent.ps1 -Restart
pwsh -File scripts/verify-super-agent.ps1 -Slow        # 19 项
pwsh -File scripts/verify-super-agent.ps1 -Network     # 追加飞书/GitHub 真发
node scripts/bench-super-agent.mjs --real              # §7 实验（真实模型可选）
```

证据索引：`docs/dsh-desktop-*.png`、`docs/bench-super-agent.md`、host `tests/*-smoke.mjs`、内核 `node --test "tests/*.test.ts"`（245 例）＋ `scripts/demo-article.mjs`（22 项现场检查）＋ `tests/reply.test.ts`（Router 直接回信道）。