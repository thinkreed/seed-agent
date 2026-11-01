import { readFileSync, writeFileSync } from 'node:fs'

const auditPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-audit.md'
let audit = readFileSync(auditPath, 'utf8')
const marker = '\n\n## 2. 逐条差距（文章 §2–§6）'
const bullet = '> - 2026-11-01：**P2-3 打包完成（unsigned 安装包已产出）**——安装 VS C++ Build Tools 后，经代理/Electron 镜像加速，`scripts/package-seed-agent.ps1` 产出 `dist/seed-agent-0.2.2-alpha.2-win-x64-unsigned.exe`（301.7 MB，SHA256 `27F2D1…7E11B9`）；静默安装退出码 0，`seed-agent.exe` 可启动并拉起 dsh web，打包运行时冒烟（native/Office/CLI）通过。已知边界：首启是 DSH 基础欢迎页，Super-agent profile 尚未烘进安装包（带 `sa-home` profile 启动时 `/super-agent/state`=200）。'
if (!audit.includes('P2-3 打包完成')) {
  audit = audit.replace(marker, `${bullet}\n${marker}`)
  writeFileSync(auditPath, audit, 'utf8')
}

const variantPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-variant.md'
let variant = readFileSync(variantPath, 'utf8')
variant = variant.replace(/- \[ \] \*\*P2-3 打包\*\*：[^\n]*/, '- [x] **P2-3 打包**：unsigned 安装包 `dist/seed-agent-0.2.2-alpha.2-win-x64-unsigned.exe`（301.7 MB）；静默安装+启动已验证；Super-agent profile 待烘进安装包，见 `docs/packaging.md`。')
writeFileSync(variantPath, variant, 'utf8')
console.log('docs updated')