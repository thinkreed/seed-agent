import { readFileSync, writeFileSync } from 'node:fs'

const auditPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-audit.md'
let audit = readFileSync(auditPath, 'utf8')
const marker = '\n\n## 2. 逐条差距（文章 §2–§6）'
const bullet = '> - 2026-11-01：**P1-1 handback / unsubscribe 完成**——core 新增 `engine.unsubscribe()/handback()`（移除订阅 + 把 Thread 最新事件重新入评估队列）；host 提供 API 与文件式控制入口（tick 时 drain），worker 用 `super_agent_handback`/`super_agent_unsubscribe` 工具写请求。证据：`HANDBACK SMOKE OK`（API 交回→新工单、控制文件→再新建、Thread 只剩最新工单订阅、worker 工具列表含两个工具）。'
if (!audit.includes('P1-1 handback')) {
  audit = audit.replace(marker, `${bullet}\n${marker}`)
  writeFileSync(auditPath, audit, 'utf8')
}

const variantPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-variant.md'
let variant = readFileSync(variantPath, 'utf8')
const anchor = '- [x] **P0-4 异步 ReAct + 全双工**'
const line = '- [x] **P1-1 handback / unsubscribe**：`engine.handback()` 移除订阅并重新排队评估；worker `super_agent_handback/super_agent_unsubscribe` 工具写控制请求，host tick drain；`HANDBACK SMOKE OK`。\n'
if (variant.includes(anchor) && !variant.includes('P1-1 handback')) {
  variant = variant.replace(anchor, line + anchor)
  writeFileSync(variantPath, variant, 'utf8')
}
console.log('docs updated')