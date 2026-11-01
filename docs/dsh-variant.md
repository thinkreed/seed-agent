# DSH 变种：把 Super-agent 做成下一代 agent 的宿主

目标：不是给 seed-agent 套一个 DSH 皮肤，而是**以 DSH 为宿主 fork 出一个变种**，把《Super-agent 设计探索》里的下一代 agent 能力做成 DSH 的插件层，复用 DSH 的 LLM 网关、工具、沙箱、Web/桌面 UI 与插件生态。

## 1. 为什么不继续"自绘一个面板"

自绘面板只能模仿外观；文章里的能力（多源触发、工单化、两级过滤、订阅扇出、存算分离、看门狗）需要的是**运行时骨架**：事件、会话、工具、渠道、调度。DSH 已经把这些做成了插件系统和可复用包，所以正确路径是 fork DSH，把 Super-agent 层做成它的一等公民。

## 2. 分层

```
┌──────────────────────────── DSH 宿主（fork）────────────────────────────┐
│ cordis 插件运行时 · LLM 网关 · 工具/沙箱 · 会话持久化 · Web/桌面壳        │
│                                                                          │
│  packages/super-agent/                                                   │
│   ├─ core        领域模型 + 事件表 + reducer + SQLite store（移植 seed-agent）│
│   ├─ sources     Trigger 源：IM / GitHub / 邮件 / 定时 / 人                  │
│   ├─ router      Gate（确定性）+ 模型评估 → Ticket；对外只由 Router 说话     │
│   ├─ executor    把 Assignment 映射成 DSH session（工具、沙箱、权限）→ 报告  │
│   ├─ watchdog    外部看门狗：停滞/未投递 → 模型裁定 → 重试                  │
│   └─ client-ui   工单工作台（侧栏 + 时间线 + 事件流 + 回复），用 DSH UI kit   │
└──────────────────────────────────────────────────────────────────────────┘
```

- **状态单向**：一切变化 = 事件；`store.append()` 唯一写入口；重放确定。
- **Router/Worker 分离**：Router 只做准入、派工、对外回复；Worker = DSH session（带工具/沙箱），互不越权。
- **两级过滤**：先 Gate（策略/发送者/强度），再 LLM 评估（accept/stop/ignore/unavailable）；显式指令可绕过评估。
- **Thread/Ticket**：一个 Thread 一个 Ticket；订阅扇出把新事件并入已有工单上下文。
- **Inline & Spill + 链式召回**：上下文按预算内联/落盘，Worker 需要时按 `recall(state, kind, id)` 取回。
- **存算分离**：状态在 store（事件库），执行在 DSH session/沙箱；daemon 可重启恢复。
- **Watchdog**：外部循环巡检，不依赖被测系统自证。

## 3. 里程碑

| 阶段 | 交付 | 验收 |
|---|---|---|
| M0 | fork 可构建：`pnpm install` + `build:lib:client` + `build:web` | 产出 web 构建、能起本地宿主 |
| M1 | `packages/super-agent/core`：领域模型/事件/reducer/store 移植 + 单测 | 事件重放哈希稳定 |
| M2 | `sources` + `router`：Gate + 模型评估 + Ticket 创建 | 本地 JSONL/IM 触发 → 工单 |
| M3 | `executor`：Ticket → DSH session（真实模型 + 工具）→ 报告 | 写文件/跑命令真机通过 |
| M4 | `client-ui`：DSH 侧栏工作台（工单/时间线/事件/回复） | 真机截图 + 操作回写 |
| M5 | `watchdog` + 重启恢复 + 渠道（飞书/GitHub） | 真机事件→执行→回帖 |
| M6 | 品牌变种：logo/名称/默认布局改为 seed-agent；保留 DSH MIT 版权 | 桌面窗口截图 |
| M7 | 可复现：`contrib/dsh` 补丁层 + `scripts/*` + 文档 | 新机器一条命令重建 |

## 4. 工程约定

- `dsh/` 为上游 vendor checkout（不入库，pinned commit）；我们的改动放 `contrib/dsh/`，由 `scripts/apply-dsh-patches.ps1` 应用。
- 新包统一 `packages/super-agent/*`，依赖只指向 DSH 公开包；不改上游核心文件，除非补丁层显式记录。
- 品牌改动集中在 `packages/client/ui-brand-official` 与 web 入口；保留 MIT 声明与 `LICENSE`。
- 构建顺序：`build:lib:client`（client 包产物）→ `build:web`；插件包单独 `tsdown` 构建。

## 5. 当前进度

- [x] DSH 源码复制到 `seed-agent/dsh`（20,233 文件 / 135MB，pinned `ce7073d5`）
- [x] `pnpm install` 通过（396 workspace projects；补丁：xlsx → `@e965/xlsx@0.20.3` + cpexcel 类型声明）
- [x] **M0 构建通过**：`pnpm build` 10/10 gates（native addon / host typert / host compiler / host bundle / desktop bundle / client compiler / client bundle / web build / aggregate checks），366 个 client artifact，`apps/web/dist` 产出
- [x] **M1 内核包**：`packages/super-agent/core` 在 fork 内编译（tsc -b + tsdown）通过，产物 `lib/index.js` 74.9kB；冒烟 `scripts/smoke-super-agent.mjs`：12 events、ticket 创建、assignment 启动、回放哈希稳定 → `CORE SMOKE OK`
- [x] **M2 host 插件**：packages/super-agent/host（cordis Service，服务名 superAgent）：ingest/tick/state/tickets/retry/reply/pause/resume，ctx.effect 关库；冒烟 HOST SMOKE OK（ticket t-000001 + launched 1 + replay hash 与 core 一致）
- [x] **M3 真机**：SdkDshExecutor（官方 SDK）→ 隔离 DSH_HOME + sdk profile + bailian provider patch → 工单 t-000001 → DSH runtime 回合（真实模型+工具）→ 写 sdk-hello.txt（内容 hello from dsh runtime）→ report ready → ticket ended（`tests/sdk-smoke.mjs`，DSH EXECUTOR SMOKE OK）

> 注意：`scripts/apply-dsh-patches.ps1` 会重写 `dsh/packages/super-agent/*` 源码目录（清掉 lib），应用补丁后需要重新 `pnpm --filter ... run build`。

- [x] **M4 桌面版**：fork 的 Electron 窗口（`apps/desktop`）里加载 `dsh-super-agent-host` + `dsh-client-ui-super-agent`：
  - 侧栏出现 **Super-agent** 入口（截图：`docs/dsh-desktop-super-agent.png`）
  - 面板左列工单（t-000001 ended）、右侧时间线（local·human 指令、ready 报告原文）
  - 真机链路：面板/HTTP ingest → Ticket → `SdkDshExecutor` 嵌套启动 `dsh --profile sdk` → 真实模型写 `desktop-hello.txt` → 报告 ready → ticket ended
  - 窗口底部显示事件库路径与 replay hash
- [x] **M5a Watchdog**：host 内置 Watchdog（确定性 finding：stalled/undelivered），watchdogSeconds 定时巡检、checkWatchdog() 暴露给快照/测试；intervene 时对 finding 工单 retry + tick。冒烟：watchdog: ok 0（HOST SMOKE OK）
- [x] **M5b 渠道**：MultiChannelWriter（飞书 im/v1、GitHub gh issue comment、本地日志）；Engine 接 Router.queueReplies，报告落地自动排队发帖；飞书实测 message_id om_x100b…549，GitHub 实测评论落在 thinkreed/seed-agent-e2e#3；桌面里 worker 用 DSH_PERMISSION_MODE=danger-full-access 自动放行（截图 docs/dsh-desktop-channels.png）
- [x] **M6 品牌变种**：侧栏 mark/name 换成 seed-agent（SeedBrand.tsx：种子凹形 logo + seed-agent 字标）；brand.localBuild 各语言 locale 改为 seed-agent，窗口标题变成「seed-agent」；截图 docs/dsh-desktop-seed-agent.png
- [x] **M7 可复现**：scripts/desktop-super-agent.ps1（凭据→补丁→构建→隔离 home→link 包→注入 profile 行→启动）与 scripts/verify-super-agent.ps1（core/host 冒烟 + 桌面启动探活，-Slow/-Network 追加真机项）；实测 VERIFY OK
- [x] **订阅扇出**：同线程第二条消息 anned_out 到已有工单（	ests/fanout-smoke.mjs：1 ticket、inp-000001→tk-000001）
- [x] **Inline & Spill + 链式召回**：超预算指令落盘 spills/<ticket>.txt，worker prompt 只留摘要 + 可读取路径（	ests/spill-smoke.mjs，SPILL SMOKE OK）
- [x] **P1-2 执行语义**：每工单独立 runtime + 工作目录 `<workspace>/tickets/<id>`；启动恢复 `recoverAfterRestart`（`RESTART SMOKE OK`）。
- [x] **P1-1 handback / unsubscribe**：`engine.handback()` 移除订阅并重新排队评估；worker `super_agent_handback/super_agent_unsubscribe` 工具写控制请求，host tick drain；`HANDBACK SMOKE OK`。
- [x] **P0-4 异步 ReAct + 全双工**：回合中消息排队、回合结束立即处理（`FULL DUPLEX SMOKE OK`，turns=2）；`super_agent_start/status/stop` 后台工具（`ASYNC REACT SMOKE OK`）。
- [x] **P0-3 链式召回（工具）**：super_agent_recall DSH 工具（trigger/thread/ticket 逐跳），worker 真机两次调用 ticket→trigger 取回索引-only marker；RECALL TOOL SMOKE OK。
- [x] **P0-3 链式召回（基线）**：host 维护 ecall-index.json（triggers/threads/tickets 引用图）并随 tick 更新；ecallContext(kind,id) 返回摘要+下一跳 handles；worker prompt 注入索引路径（trigger→thread→ticket 逐跳）；RECALL SMOKE OK。
- [x] **P0-2 入站 Source**：host 移植飞书/GitHub/JSONL Source 并轮询（src/sources/*），策略按启用来源放行，engine 幂等去重；SOURCES SMOKE OK、INBOUND LIVE OK（飞书 24h 3 条消息/1 trigger，GitHub 通知 API 连通），桌面 sources=feishu+github。
- [x] **P0-1 Router Session**：常驻 Router（host/src/router_session.ts）——跨 Thread 批处理（同一 tick 2 个 Thread 合并为一次 LLM 调用）、记忆与对话历史、recall 动作入口、面板「和 Router 说话」；ROUTER SMOKE OK，截图 docs/dsh-desktop-router.png
- [x] **两级过滤（Gate + LLM）**：host `assessorMode: llm`（默认）→ `LlmAssessor` + `OpenAIClient`（BAILIAN 兼容端点）走 core 的 assessment prompt 与 Inline&Spill 视图；实测闲聊线程不建单、明确指令建单（`tests/assessor-smoke.mjs`，ASSESSOR SMOKE OK）；`verify-super-agent.ps1 -Slow` → core/host/sdk/desktop 全 PASS

### 桌面版运行（M7 一键）

```powershell
pwsh -File scripts/desktop-super-agent.ps1 -Restart     # 准备 + 启动桌面
pwsh -File scripts/verify-super-agent.ps1              # 验收（可加 -Slow -Network）
```

> 脚本是 UTF-8 **BOM**（Windows PowerShell 5.1 读无 BOM 的中文 PS1 会把换行吃掉）；变量名不要用 $home/$Home（只读自动变量）。

### 手工步骤（M4 实测记录）

1. 构建产物：`dsh` 内 `pnpm build`；单独重建三个包（`core` / `host` / `ui-super-agent`）。
2. 复制 profile 到隔离 home：`%DSH_HOME%/profiles/desktop`。
3. profile `package.json` 加两条 link 依赖（pnpm install 建立软链）：
   ```json
   "@deepseek-ai/dsh-super-agent-host": "link:<REPO>/dsh/packages/super-agent/host",
   "@deepseek-ai/dsh-client-ui-super-agent": "link:<REPO>/dsh/packages/client/ui-super-agent"
   ```
4. profile `cordis.patch.yml` 追加 `contrib/dsh/config/desktop-super-agent.patch.yml` 的 insert 块（路径按本机替换）。
5. 以该 `DSH_HOME` 启动 fork 桌面：`pnpm --filter @deepseek-ai/dsh-desktop run start`（需要 `BAILIAN_API_KEY` 供嵌套 runtime 用）。
6. 注意：Electron 启动前必须 `Remove-Item Env:ELECTRON_RUN_AS_NODE`（本会话环境会把它设为 1，导致 electron 以 node 模式启动）。

### 验证

```powershell
cd seed-agent\dsh
node <runtime-node> <runtime-pnpm> pnpm build
cd ..
node scripts/smoke-super-agent.mjs
```

## 6. 能力 → 落点 → 证据（最终验收）

| 文章能力 | 在 fork 里的落点 | 证据 |
|---|---|---|
| Router / Worker 双层 | `SuperAgentHost`（Router 侧：评估/派工/回复）+ `SdkDshExecutor`（Worker：独立 DSH session） | `tests/sdk-smoke.mjs` 真实回合 |
| Trigger / Thread / Ticket | `packages/super-agent/core`（事件表 + reducer + SQLite） | `scripts/smoke-super-agent.mjs`（12 events、ticket、assignment、回放哈希） |
| Gate + LLM 两级过滤 | `defaultPolicy` Gate → `LlmAssessor` + `OpenAIClient`（assessment prompt + Inline&Spill 视图） | `tests/assessor-smoke.mjs`：闲聊不建单、明确指令建单 |
| 订阅扇出 | `Engine.ingest` → `subscribedTickets` → `fanOut`（input + deliver 效果） | `tests/fanout-smoke.mjs`：1 ticket、`trg-second → fanned_out` |
| Inline & Spill + 链式召回 | `buildView`（评估上下文）+ `spillInstruction`（worker 指令落盘，prompt 给路径） | `tests/spill-smoke.mjs`：长指令落盘、prompt 含可读取路径 |
| 异步 ReAct | Worker 在 DSH agent loop 里多轮工具调用；`launch` 受理即返回，回合结束异步 `onReport` | `tests/sdk-smoke.mjs` + 桌面面板 `running → ended` |
| 存算分离 | 状态在 SQLite 事件库；执行在嵌套 DSH runtime（隔离 home/workspace） | 桌面工单底部常驻事件库路径与 replay hash；产物由 worker 写 |
| Watchdog | host 定时 `Watchdog.check`（stalled/undelivered）→ intervene → retry + tick | `tests/smoke.mjs`：`watchdog: ok 0` + snapshot |
| Web / 桌面 UI 复用 | DSH `ui-*` 槽位：`sidebar.panellist` + `main` + 品牌位；Electron 桌面壳 | `docs/dsh-desktop-*.png` 截图 |
| 可复现 | `scripts/desktop-super-agent.ps1` + `verify-super-agent.ps1` + `contrib/dsh` 补丁层 | `VERIFY OK`（core/host/fanout/spill/sdk/desktop 六项） |

> 完整差距审计（对照文章 §2–§6 与原型 001–008）见 docs/dsh-audit.md：整体覆盖约 30–35%，P0 缺口是 Router Session、入站 Source、链式召回工具、异步 ReAct/全双工。

### 已知边界

- **链式召回是一跳**：超预算上下文落盘成单个 digest 文件，prompt 给路径；尚未实现按事件 id 的多级 recall 索引。
- **嵌套 runtime 较重**：每个 worker 回合会拉起一个 DSH runtime 子进程（隔离 home），延迟主要花在启动 + 模型；后续可换成 in-process session 或常驻 worker 池。
- **桌面版是源码运行**：还没有打包安装包（Electron builder 流程未接），`desktop-super-agent.ps1` 以开发模式启动。
- **品牌只覆盖侧栏与标题**：会话 hero（“探索未至之境”）、托盘图标、安装包元信息仍是 DSH 原样。