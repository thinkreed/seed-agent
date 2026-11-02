import { readFileSync, writeFileSync } from 'node:fs'

const auditPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-audit.md'
let audit = readFileSync(auditPath, 'utf8')
const marker = '\n\n## 2. 逐条差距（文章 §2–§6）'
const bullet = '> - 2026-11-01：**P2-1 存算分离（端侧 daemon）完成**——新增无状态 daemon 包（`/exec`、`/read`、`/write`，root 内路径约束、token 鉴权）与 `tool-remote`（worker 用 `super_agent_remote_exec/write/read` 在 daemon 所在机器执行）；host 只传 daemon URL/token，状态仍在 SQLite。证据：`DAEMON SMOKE OK`——daemon 独立进程执行命令后，产物 `remote-ok` 落在 daemon root 而**不在**工单目录（证明执行环境在外、计算/状态在 host）。'
if (!audit.includes('P2-1 存算分离')) {
  audit = audit.replace(marker, `${bullet}\n${marker}`)
  writeFileSync(auditPath, audit, 'utf8')
}

const variantPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-variant.md'
let variant = readFileSync(variantPath, 'utf8')
const anchor = '- [x] **P1-6 多信道交付规范**'
const line = '- [x] **P2-1 存算分离**：无状态 daemon（exec/read/write）+ `super_agent_remote_*` 工具；`DAEMON SMOKE OK`（产物在 daemon root、不在工单目录）。\n'
if (variant.includes(anchor) && !variant.includes('P2-1 存算分离')) {
  variant = variant.replace(anchor, line + anchor)
  writeFileSync(variantPath, variant, 'utf8')
}
console.log('docs updated')