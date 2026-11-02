# DSH 源码并入 seed-agent（fork 方案）

目标：seed-agent 的界面不再"仿"DSH，而是**直接基于 DSH 源码改**，并把 seed-agent 的能力接进去。

## 1. 仓库布局

```
seed-agent/
├── src/                  # seed-agent 零依赖内核（不动）
├── dsh/                  # DSH 源码 fork（vendor checkout，.gitignore，不入库）
│   ├── apps/web          # 上游 Web 前端（Vite/React）
│   ├── packages/client/* # UI 组件包（ui-layout/ui-chat/ui-theme...）
│   ├── packages/host/*   # 宿主/WebServer/RPC
│   └── packages/plugin/seed-agent   # ← 我们新增：seed-agent 插件
├── contrib/dsh/          # 我们相对上游的改动（patch/新增包），入库
└── scripts/sync-dsh.ps1  # 按 pinned commit 拉取/刷新 dsh/
```

上游钉在 `ce7073d5`（对应 npm 包 0.2.2-alpha.2 时代）。`dsh/` 不入库，避免 135MB / 2 万文件污染仓库；我们的改动全部落在 `contrib/dsh/`，用脚本/补丁方式应用。

## 2. 能力接入方式

seed-agent 内核（事件溯源 + 工单 + worker）保持零依赖、独立进程；DSH 前端通过一个**插件**获得能力：

```
DSH Web UI
  └─ client plugin: seed-agent 面板（React + DSH UI kit）
        ↕ host RPC
  └─ host plugin: seed-agent 客户端（fetch 本机 127.0.0.1:4780）
        ↕ HTTP/SSE
  seed-agent 引擎（node src/cli.ts desktop --no-browser）
```

- host plugin：注册 RPC `seedAgent.*`（state / tickets / events / command），内部调用 seed-agent 本地 API；不直接 import 我们的 TS 内核（跨仓库、版本解耦）。
- client plugin：在 DSH 侧栏新增入口，渲染工单列表 / 时间线 / 事件 / 回复框，复用 DSH 的 `ui-*` 组件与主题令牌；品牌改为 seed-agent（logo 换掉）。
- 好处：DSH 的壳、聊天、插件生态全都在；seed-agent 只贡献自己的能力页面与命令。

## 3. 里程碑

1. `scripts/sync-dsh.ps1` + `pnpm install` + `pnpm build:web` 能产出可运行的上游 Web 前端（验证 fork 可用）。
2. 在 `dsh/packages/plugin/seed-agent` 建 host 插件骨架：注册 RPC + 健康检查。
3. client 插件骨架：侧栏入口 + 空面板（类型检查/构建通过）。
4. 面板接 seed-agent HTTP：工单列表、时间线、事件流、暂停/恢复/重试/回复。
5. 品牌替换：logo/名称/标题改为 seed-agent（保留 DSH 版权头与 MIT 声明）。
6. 装进本地 DSH profile，真机截图验收。
7. 文档：README/operations/架构 §20；`contrib/dsh/seed-agent.patch` 固化改动。

## 4. 风险与边界

- 上游处于 `0.2.2-alpha.2`，API 会动：我们只在插件边界使用公开 API，避免改上游核心文件。
- `pnpm install` 依赖量大（数千包）；本机 Node 24 由 DSH runtime 提供，pnpm 11 用 runtime 内置版本。
- 若上游构建过重（全量 build 需要 tsc 大工程），退路是用 `pnpm --filter @deepseek-ai/dsh-web-frontend build` 单包构建 + 只编译插件包。
- 不分发 DSH 二进制；本方案是"源码级 fork + 插件"，许可证 MIT，保留上游 `LICENSE` 与版权声明。