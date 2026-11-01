# DSH fork 补丁

`dsh/` 是上游源码的 vendor checkout（不入库）。本目录存放我们相对上游的改动，可复现地应用到 checkout 上。

## 当前补丁

| 文件 | 改动 | 原因 |
|---|---|---|
| `packages/client/ui-sidebar-documentpreview/package.json` | `xlsx` 依赖从 `https://cdn.sheetjs.com/xlsx-0.20.3/xlsx-0.20.3.tgz` 改为 `0.18.5` | 该 CDN 在本机网络不可达，pnpm install 会超时失败；0.18.5 在 npm registry 可拉取，API 兼容 |

## 用法

```powershell
.\scripts\sync-dsh.ps1 -Force        # 拉取 pinned commit + pnpm install
.\scripts\apply-dsh-patches.ps1      # 应用本目录补丁（sync 之后执行）
```

## 后续补丁

seed-agent 集成代码计划落在 `dsh/packages/plugin/seed-agent`（host RPC + client 面板）。
该目录会以 `contrib/dsh/packages/plugin/seed-agent/` 形式入库，由 `apply-dsh-patches.ps1` 复制进 checkout。