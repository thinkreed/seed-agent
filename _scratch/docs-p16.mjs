import { readFileSync, writeFileSync } from 'node:fs'

const auditPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-audit.md'
let audit = readFileSync(auditPath, 'utf8')
const marker = '\n\n## 2. 逐条差距（文章 §2–§6）'
const bullet = '> - 2026-11-01：**P1-6 多信道交付规范完成**——新增 `format.ts`（IM 去 Markdown 压缩 ≤100 字、GitHub/异步信道结构化标题+结论+落款），出站统一经 `ChannelFormattingWriter`。证据：`CHANNEL FORMAT SMOKE OK`（IM 94 字、GitHub 结构化、写手按地址分派）；`CHANNEL FORMAT LIVE OK`（飞书 `om_x100b6144d87a…` + GitHub 评论 `gh-thinkreed/seed-agent-e2e-3`）；`CHANNELS SMOKE OK`（飞书真实回帖）。'
if (!audit.includes('P1-6 多信道交付规范完成')) {
  audit = audit.replace(marker, `${bullet}\n${marker}`)
  writeFileSync(auditPath, audit, 'utf8')
}

const variantPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-variant.md'
let variant = readFileSync(variantPath, 'utf8')
const anchor = '- [x] **P1-5 面板补全（第一批）**'
const line = '- [x] **P1-6 多信道交付规范**：IM ≤100 字压缩、GitHub 结构化；`ChannelFormattingWriter` 统一出口；`CHANNEL FORMAT SMOKE OK`、live 飞书+GitHub 消息 ID。\n'
if (variant.includes(anchor) && !variant.includes('P1-6 多信道交付规范')) {
  variant = variant.replace(anchor, line + anchor)
  writeFileSync(variantPath, variant, 'utf8')
}
console.log('docs updated')