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

官方流程：

```
desktop package: the build host cannot run this packaging sequence:
  vswhere: spawn C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe ENOENT
```

绕过官方预检、直接调用 electron-builder（`--win --dir`）同样失败：

```
⨯ ENOENT: …\.desktop-build\targets\win-x64\dsh\node_modules\@deepseek-ai\libreoffice-kit\package.json
  at officePackageDirectories (scripts/libreoffice-packages.mjs)
  at beforePack (electron-builder-config.mjs)
```

原因：electron-builder 需要官方 prepare 阶段生成的 target 树；该阶段被 VS 工具链预检拦截。结论一致：**本机缺 Visual Studio C++ Build Tools，不能产出安装包或解包目录**。

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