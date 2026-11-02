import { readFileSync, writeFileSync } from 'node:fs'

const auditPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-audit.md'
let audit = readFileSync(auditPath, 'utf8')
const marker = '\n\n## 2. 逐条差距（文章 §2–§6）'
const bullet = '> - 2026-11-01：**P1-5 面板补全（第一批）完成**——工单列表加 stage 徽标与搜索，详情头显示 stage，底部显示运行配置（router/watchdog/sources/speculation/replay）；host snapshot 暴露 `stage` 与 `config`。证据：桌面探活断言 `stage=idle router=llm spec=True`（verify 通过），截图 `docs/dsh-desktop-panel.png`。'
if (!audit.includes('P1-5 面板补全')) {
  audit = audit.replace(marker, `${bullet}\n${marker}`)
  writeFileSync(auditPath, audit, 'utf8')
}

const variantPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-variant.md'
let variant = readFileSync(variantPath, 'utf8')
const anchor = '- [x] **P1-4 投机执行**'
const line = '- [x] **P1-5 面板补全（第一批）**：stage 徽标、工单搜索、配置摘要；桌面探活 `stage=idle router=llm spec=True`，截图 `docs/dsh-desktop-panel.png`。\n'
if (variant.includes(anchor) && !variant.includes('P1-5 面板补全')) {
  variant = variant.replace(anchor, line + anchor)
  writeFileSync(variantPath, variant, 'utf8')
}
console.log('docs updated')