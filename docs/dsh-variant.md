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
- [ ] M5：Watchdog / 渠道（飞书、GitHub）
- [x] **M6 品牌变种**：侧栏 mark/name 换成 seed-agent（SeedBrand.tsx：种子凹形 logo + seed-agent 字标）；rand.localBuild 各语言 locale 改为 seed-agent，窗口标题变成「seed-agent」；截图 docs/dsh-desktop-seed-agent.png
- [ ] M7：可复现（一键脚本 + 文档）

### 桌面版运行步骤（M4 实测）

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