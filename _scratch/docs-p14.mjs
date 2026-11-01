import { readFileSync, writeFileSync } from 'node:fs'

const auditPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-audit.md'
let audit = readFileSync(auditPath, 'utf8')
const marker = '\n\n## 2. 逐条差距（文章 §2–§6）'
const bullet = '> - 2026-11-01：**P1-4 投机执行完成**——`host.speculate()` 走独立 runtime 在后台尝试（不进工单/Router），worker 输出 `{deliver,summary}` 判定；有价值才发 channel，否则静默丢弃；snapshot 记录 speculations。证据：`SPECULATION SMOKE OK`——可交付案例 `delivered=true` 且 channel 收到「[投机执行]」，闲聊案例 `delivered=false` 静默。'
if (!audit.includes('P1-4 投机执行完成')) {
  audit = audit.replace(marker, `${bullet}\n${marker}`)
  writeFileSync(auditPath, audit, 'utf8')
}

const variantPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-variant.md'
let variant = readFileSync(variantPath, 'utf8')
const anchor = '- [x] **P1-3 Watchdog 模型裁定**'
const line = '- [x] **P1-4 投机执行**：`speculate()` 后台尝试，`{deliver}` 判定，值得才发 channel；`SPECULATION SMOKE OK`。\n'
if (variant.includes(anchor) && !variant.includes('P1-4 投机执行')) {
  variant = variant.replace(anchor, line + anchor)
  writeFileSync(variantPath, variant, 'utf8')
}
console.log('docs updated')