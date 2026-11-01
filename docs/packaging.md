# 桌面打包（P2-3）

## 现状

| 项 | 状态 |
|---|---|
| 安装包 productName / 协议名改为 seed-agent | ✅ 已由 `scripts/apply-dsh-patches.ps1` 注入（`apps/desktop/scripts/electron-builder-config.mjs`） |
| 打包环境模板（无签名本地构建） | ✅ `contrib/dsh/config/desktop.env.windows` → `dsh/apps/desktop/.env.windows` |
| 一键打包脚本 | ✅ `scripts/package-seed-agent.ps1`（封装官方 `package:win:x64:unsigned`） |
| 实际产出安装包 | ❌ 本机缺少 VS Build Tools（`vswhere.exe ENOENT`），官方打包预检拒绝继续 |
| hero / 托盘图标 / 安装包图标 | ❌ 仍是 DSH 原样 |

## 本机失败证据

```
desktop package: the build host cannot run this packaging sequence:
  vswhere: spawn C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe ENOENT
```

DSH 的打包流程要求本机具备 Visual Studio C++ 工具链（用于原生组件/安装器构建）。当前机器未安装，故无法在此环境产出安装包。这是构建环境限制，不是代码问题。

## 在具备工具链的机器上打包

1. 安装 Visual Studio Build Tools，勾选 “Desktop development with C++”。
2. 在仓库根目录执行：

```powershell
pwsh -File scripts/package-seed-agent.ps1            # 安装包（NSIS，unsigned）
pwsh -File scripts/package-seed-agent.ps1 -Dir       # 仅解包目录（更快检查）
```

产物在 `dsh/apps/desktop/.desktop-build/` 下（electron-builder 输出目录，见打包记录 `packaging-runs/`）。

## 当前可用的桌面形态

没有安装包时仍可用一键源码桌面：

```powershell
pwsh -File scripts/desktop-super-agent.ps1 -Restart
```

它使用隔离的 `DSH_HOME`（`dsh/apps/desktop/.desktop-build/sa-home`），不会动用户真实 DSH 配置。