# DSH fork 补丁

`dsh/` 是上游源码的 vendor checkout（不入库）。本目录存放我们相对上游的改动，可复现地应用到 checkout 上。

## 补丁清单

| 文件/目录 | 改动 | 原因 |
|---|---|---|
| `packages/client/ui-sidebar-documentpreview/package.json` | `xlsx` 依赖：`https://cdn.sheetjs.com/xlsx-0.20.3/...` → `npm:@e965/xlsx@0.20.3` | 该 CDN 在本机网络不可达；`@e965/xlsx` 是同一版本的 npm 可用分支（含 `dist/cpexcel.full.mjs`） |
| `overlay/ui-sidebar-documentpreview/cpexcel.full.d.ts` → `packages/client/ui-sidebar-documentpreview/src/client/excel/` | 新增模块声明 | `@e965/xlsx` 没带 `xlsx/dist/cpexcel.full.mjs` 子路径的 `.d.ts`，`tsc -b` 报 TS7016 |
| `packages/super-agent/core/**` | 新增包 `@deepseek-ai/dsh-super-agent-core` | Super-agent 内核（seed-agent 移植）：领域/事件/reducer/store/engine/Router/Worker/Watchdog |

## 用法

```powershell
.\scripts\sync-dsh.ps1 -Force        # 拉取 pinned commit + pnpm install
.\scripts\apply-dsh-patches.ps1      # 应用补丁 + overlay + 新增包
```

> pin: `ce7073d5`（DSH 0.2.2-alpha.2）。
> 注意：DSH 的 `postinstall`（lefthook）会在 seed-agent 根目录生成 `lefthook.yml` 与 git hook，应用后需清理；`scripts/apply-dsh-patches.ps1` 不负责，建议在 `sync-dsh.ps1 -Force` 后手动删除，已记录在 docs/dsh-fork.md。