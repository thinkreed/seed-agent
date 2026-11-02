import { readFileSync, writeFileSync } from 'node:fs'

const auditPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-audit.md'
let audit = readFileSync(auditPath, 'utf8')
const marker = '\n\n## 2. 逐条差距（文章 §2–§6）'
const bullet = '> - 2026-11-01：**P2-2 文章 §7 实验复现（机制级）完成**——`scripts/bench-super-agent.mjs` 用确定性假模型测 Router 批处理与消融：N=4 threads 时批量 1 次模型调用 43ms，逐条 4 次 179ms（≈4×）；单 Session 串行 2172ms vs Super-agent（批处理+2 slots）≈1043ms（≈2×）；`--real` 真实模型 3 threads 合并 1 次调用（1995ms）。结果写入 `docs/bench-super-agent.{md,json}`，纳入 verify -Slow（BENCH OK）。'
if (!audit.includes('P2-2 文章 §7 实验复现')) {
  audit = audit.replace(marker, `${bullet}\n${marker}`)
  writeFileSync(auditPath, audit, 'utf8')
}

const variantPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-variant.md'
let variant = readFileSync(variantPath, 'utf8')
const anchor = '- [x] **P2-1 存算分离**'
const line = '- [x] **P2-2 §7 实验复现（机制级）**：`scripts/bench-super-agent.mjs`（Router 批处理 ≈4×、消融 ≈2×，`--real` 3 threads 合并 1 次调用）；结果 `docs/bench-super-agent.md`。\n'
if (variant.includes(anchor) && !variant.includes('P2-2 §7 实验复现')) {
  variant = variant.replace(anchor, line + anchor)
  writeFileSync(variantPath, variant, 'utf8')
}
console.log('docs updated')