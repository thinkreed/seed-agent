import { readFileSync, writeFileSync } from 'node:fs'

const auditPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-audit.md'
let audit = readFileSync(auditPath, 'utf8')
const auditMarker = '\n\n## 2. 逐条差距（文章 §2–§6）'
const auditBullet = '> - 2026-11-01：**P0-4 异步 ReAct + 全双工完成**——(1) host 执行器按工单串行回合、回合中到达的新消息排队、回合结束立即作为下一轮输入（`FULL DUPLEX SMOKE OK`：turns=2、最后 prompt 是第二条指令、队列排空）；(2) 新增 `tool-background`（`super_agent_start/status/stop`），start 立即返回 Started、后台命令继续跑、worker 继续前台工作并轮询到 done（`ASYNC REACT SMOKE OK`：jobId、running→done、后台产物存在）。'
if (!audit.includes('P0-4 异步 ReAct + 全双工完成')) {
  audit = audit.replace(auditMarker, `${auditBullet}\n${auditMarker}`)
  writeFileSync(auditPath, audit, 'utf8')
}

const variantPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-variant.md'
let variant = readFileSync(variantPath, 'utf8')
const anchor = '- [x] **P0-3 链式召回（工具）**'
const line = '- [x] **P0-4 异步 ReAct + 全双工**：回合中消息排队、回合结束立即处理（`FULL DUPLEX SMOKE OK`，turns=2）；`super_agent_start/status/stop` 后台工具（`ASYNC REACT SMOKE OK`）。\n'
if (variant.includes(anchor) && !variant.includes('P0-4 异步 ReAct')) {
  variant = variant.replace(anchor, line + anchor)
  writeFileSync(variantPath, variant, 'utf8')
}
console.log('docs updated')