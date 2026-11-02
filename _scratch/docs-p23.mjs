import { readFileSync, writeFileSync } from 'node:fs'

const auditPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-audit.md'
let audit = readFileSync(auditPath, 'utf8')
const marker = '\n\n## 2. 逐条差距（文章 §2–§6）'
const bullet = '> - 2026-11-01：**P2-3 打包（部分）**——安装包 `productName`/协议名已改为 `seed-agent`（apply 脚本注入），无签名打包环境模板与 `scripts/package-seed-agent.ps1` 已就绪；**本机因缺少 Visual Studio C++ Build Tools（`vswhere.exe ENOENT`）无法产出安装包**，见 `docs/packaging.md`。桌面仍可用 `scripts/desktop-super-agent.ps1 -Restart` 源码一键启动。最终总验收表见 `docs/acceptance.md`。'
if (!audit.includes('P2-3 打包（部分）')) {
  audit = audit.replace(marker, `${bullet}\n${marker}`)
  writeFileSync(auditPath, audit, 'utf8')
}

const variantPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-variant.md'
let variant = readFileSync(variantPath, 'utf8')
const anchor = '- [x] **P2-2 §7 实验复现（机制级）**'
const line = '- [ ] **P2-3 打包**：productName/协议已改、脚本就绪；本机缺 VS Build Tools，见 `docs/packaging.md`。\n'
if (variant.includes(anchor) && !variant.includes('P2-3 打包')) {
  variant = variant.replace(anchor, line + anchor)
  writeFileSync(variantPath, variant, 'utf8')
}
console.log('docs updated')