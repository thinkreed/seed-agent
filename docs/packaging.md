# 桌面打包（P2-3）

> 状态：**已产出安装包（unsigned）**。`seed-agent-0.2.2-alpha.2-win-x64-unsigned.exe`（301.7 MB，SHA256 `165D075BE5F21046530A3B2062E1DFF58E576DCE8578271F2770239018BCB1F9`），位于 `dist/`（构建产物不入库）。
>
> 构建前提：Visual Studio C++ Build Tools（本机已装）。经 `scripts/package-seed-agent.ps1` 一键复现。
>
> 已知边界：安装后的**首启是 DSH 基础形态**（欢迎页 / 登录 / 添加 API Key）。Super-agent 面板需要带 `sa-home` 那套 profile 启动；把 Super-agent profile 默认烘进安装包仍待做（见文末）。

## 已验证

| 项 | 结果 |
|---|---|
| 打包 | `package:win:x64:unsigned` 成功；产物 301.7 MB |
| 品牌 | 安装包 `productName=seed-agent`、可执行名 `seed-agent.exe`、协议名 `seed-agent`、卸载器 `Uninstall seed-agent.exe` |
| 静默安装 | `installer.exe /S /D=<dir>` 退出码 0；安装目录含 `seed-agent.exe`、`resources/`、卸载器 |
| 启动 | 安装后的 `seed-agent.exe` 能起 Electron 进程并拉起 `dsh web`（日志 `dsh web: http://127.0.0.1:…`） |
| 打包运行时自检 | 官方 smoke：native 模块（koffi/sharp/pty）、Office 转换（DOCX/XLSX/PPTX→PDF）、CLI 离线插件安装均通过 |
| Super-agent 面板 | 用准备好的 `sa-home` profile 启动时 `/super-agent/state` 返回 200；默认安装首启没有该 profile |

## 复现

```powershell
# 需要：Visual Studio C++ Build Tools + Node 24 + pnpm 11
# 可选：代理/镜像加速下载
$env:SEED_AGENT_PROXY='http://127.0.0.1:10809'
pwsh -File scripts/package-seed-agent.ps1            # NSIS 安装包（unsigned）
pwsh -File scripts/package-seed-agent.ps1 -Dir       # 只产出解包目录
```

产物：`dsh/apps/desktop/.desktop-build/targets/win-x64/unsigned-artifacts/…-unsigned.exe`。

## 品牌补丁（可重放，apply-dsh-patches.ps1）

- `productName: 'seed-agent'`、协议名 `seed-agent`
- unsigned 构建跳过 mandatory-update policy（否则假更新源会让应用启动即阻塞/退出）
- 打包冒烟脚本里的可执行名改为 `seed-agent.exe`
- 无签名打包环境模板 `contrib/dsh/config/desktop.env.windows` → `dsh/apps/desktop/.env.windows`

## 待办：把 Super-agent profile 烘进安装包

当前安装包首启走 DSH 默认欢迎页；Super-agent 面板只在带准备 profile（`dsh/apps/desktop/.desktop-build/sa-home`）时出现。要默认带上，需要在桌面 app-boot 初始化 profile 时注入：

1. `super-agent-host` 插件行（host 配置：dbPath、workspace、sources、router…）
2. `ui-super-agent` 客户端插件行
3. SDK worker 用的工具插件行（recall/background/control/remote，file URL 指向打包后的 dsh）
4. `sdk-bailian` provider 配置与 `BAILIAN_API_KEY` 来源

这需要改 `apps/desktop` 的 profile 初始化路径（或把上述插件做成随包安装的 bundle），并重新打包验证。

## 环境限制：Smart App Control（2026-11-01 21:00 起）

本机 Windows Smart App Control 已从评估切到**强制**（`VerifiedAndReputablePolicyState=1`），会拦截新构建的未签名 `seed-agent.exe`：

```
An Application Control policy has blocked this file
```

- 安装包本身仍可运行（`/S` 静默安装退出码 0，文件完整写入）
- 安装后的 `seed-agent.exe` 在本机**无法启动**（被代码完整性策略拦截）
- 早期（20:20 前后）同一形态的未签名 exe 能启动并截到欢迎页，说明是系统策略在此后切换，不是构建问题
- 解除：关闭 Smart App Control（系统设置，需重置系统才能再开启），或使用受信任代码签名证书签名

因此本机后续只能验证到“安装成功”，启动验证需在关闭 SAC 的机器或签名后做。

## 首启挂载 Super-agent（本轮进展）

- 新增 bundle 包 `@deepseek-ai/dsh-super-agent-bundle`（`contrib/dsh/packages/super-agent/bundle`）：`cordis.patch.yml` 插入 `super-agent-host`（`bundleDefaults: true`、bailian、v4.1-flash）与 `super-agent-ui` 两行
- bundle 进入 `@deepseek-ai/dsh` 依赖闭包；`createPluginProfile` 首次创建 profile 时把 bundle 追加进 `dsh.profile.bundles`
- host 新增 `bundleDefaults`：未配置时从包位置推断 `dshBin` / `dshHome` / `dshPatch` / `workspace`，并优先用 `resources/dsh` 物理 runtime
- worker patch `config/sdk-super-agent.patch.yml`（provider + 四个工具，按包名挂载）随 host 包发布

已验证（dev 等价路径，绕过 Electron 首启）：

1. `createPluginProfile` 生成的 profile bundles = `[...web-app, '@deepseek-ai/dsh-super-agent-bundle']`
2. `dsh --profile sa-test --dump-config` 中出现 `super-agent-host` / `super-agent-ui` 两行及配置
3. 用该 profile 启动 `dsh web`：`/super-agent/state` 返回 **200**（无 token 也可读）

未完成：打包产物里 `resources/dsh` 只复制到根文件，`node_modules` 未被 electron-builder extraResources 带入（worker 子进程需要物理 runtime）。下一步改用「先 --dir 打包 → 脚本复制 runtime → `electron-builder --prepackaged`」或 override 复制。
