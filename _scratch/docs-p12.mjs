import { readFileSync, writeFileSync } from 'node:fs'

const auditPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-audit.md'
let audit = readFileSync(auditPath, 'utf8')
const marker = '\n\n## 2. 逐条差距（文章 §2–§6）'
const bullet = '> - 2026-11-01：**P1-2 执行语义（每工单目录 + 重启恢复）完成**——executor 改为每工单一个 DSH runtime（cwd=`<workspace>/tickets/<ticketId>`），worker prompt 注入工作目录；host 启动时调用 `recoverAfterRestart()`（收口 running assignment + 投递 resume 输入并重新派发），snapshot 暴露 `recovery`。证据：`RESTART SMOKE OK`（recovery events=2、live assignment=true）、`DSH EXECUTOR SMOKE OK`（产物落在工单目录）、全双工/异步召回 smokes 在工单目录下通过。'
if (!audit.includes('P1-2 执行语义')) {
  audit = audit.replace(marker, `${bullet}\n${marker}`)
  writeFileSync(auditPath, audit, 'utf8')
}

const variantPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-variant.md'
let variant = readFileSync(variantPath, 'utf8')
const anchor = '- [x] **P1-1 handback / unsubscribe**'
const line = '- [x] **P1-2 执行语义**：每工单独立 runtime + 工作目录 `<workspace>/tickets/<id>`；启动恢复 `recoverAfterRestart`（`RESTART SMOKE OK`）。\n'
if (variant.includes(anchor) && !variant.includes('P1-2 执行语义')) {
  variant = variant.replace(anchor, line + anchor)
  writeFileSync(variantPath, variant, 'utf8')
}
console.log('docs updated')