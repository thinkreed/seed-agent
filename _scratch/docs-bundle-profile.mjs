import { readFileSync, writeFileSync } from 'node:fs'

const packagingPath = 'E:/projects/reed-dev/seed-agent/docs/packaging.md'
let packaging = readFileSync(packagingPath, 'utf8')
const addition = `
## 首启挂载 Super-agent（本轮进展）

- 新增 bundle 包 \`@deepseek-ai/dsh-super-agent-bundle\`（\`contrib/dsh/packages/super-agent/bundle\`）：\`cordis.patch.yml\` 插入 \`super-agent-host\`（\`bundleDefaults: true\`、bailian、v4.1-flash）与 \`super-agent-ui\` 两行
- bundle 进入 \`@deepseek-ai/dsh\` 依赖闭包；\`createPluginProfile\` 首次创建 profile 时把 bundle 追加进 \`dsh.profile.bundles\`
- host 新增 \`bundleDefaults\`：未配置时从包位置推断 \`dshBin\` / \`dshHome\` / \`dshPatch\` / \`workspace\`，并优先用 \`resources/dsh\` 物理 runtime
- worker patch \`config/sdk-super-agent.patch.yml\`（provider + 四个工具，按包名挂载）随 host 包发布

已验证（dev 等价路径，绕过 Electron 首启）：

1. \`createPluginProfile\` 生成的 profile bundles = \`[...web-app, '@deepseek-ai/dsh-super-agent-bundle']\`
2. \`dsh --profile sa-test --dump-config\` 中出现 \`super-agent-host\` / \`super-agent-ui\` 两行及配置
3. 用该 profile 启动 \`dsh web\`：\`/super-agent/state\` 返回 **200**（无 token 也可读）

未完成：打包产物里 \`resources/dsh\` 只复制到根文件，\`node_modules\` 未被 electron-builder extraResources 带入（worker 子进程需要物理 runtime）。下一步改用「先 --dir 打包 → 脚本复制 runtime → \`electron-builder --prepackaged\`」或 override 复制。
`
if (!packaging.includes('首启挂载 Super-agent')) {
  packaging = packaging.trimEnd() + '\n' + addition
  writeFileSync(packagingPath, packaging, 'utf8')
}

const acceptancePath = 'E:/projects/reed-dev/seed-agent/docs/acceptance.md'
let acceptance = readFileSync(acceptancePath, 'utf8')
acceptance = acceptance.replace(
  '| 安装包 | ✅（首启为基础形态） | `dist/seed-agent-0.2.2-alpha.2-win-x64-unsigned.exe`（301.7 MB，SHA256 `27F2D1…7E11B9`）：静默安装退出码 0、`seed-agent.exe` 可启动并拉起 dsh web；Super-agent 面板需准备 profile（尚未烘进安装包，见 `docs/packaging.md`） |',
  '| 安装包 | ✅（首启挂载 Super-agent，待重打） | bundle 已进 runtime 闭包；首次创建 profile 自动挂载 host+UI（dev 等价验证：dump-config 出现两行、`/super-agent/state`=200）。打包产物的物理 runtime 复制与安装包重打待完成（`docs/packaging.md`）；本机 Smart App Control 拦截未签名新 exe |',
)
writeFileSync(acceptancePath, acceptance, 'utf8')
console.log('docs updated')