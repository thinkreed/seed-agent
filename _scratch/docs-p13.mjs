import { readFileSync, writeFileSync } from 'node:fs'

const auditPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-audit.md'
let audit = readFileSync(auditPath, 'utf8')
const marker = '\n\n## 2. 逐条差距（文章 §2–§6）'
const bullet = '> - 2026-11-01：**P1-3 Watchdog 模型裁定完成**——host 构造 `LlmWatchdogJudge`（core 已有实现）交给 `Watchdog`；每次巡检记录 intervention/复查（intervene 后 15s 复查），snapshot 暴露 verdict reason/interventions/rechecks。证据：`WATCHDOG LLM SMOKE OK`——同一停滞状态，确定性模式判 intervene，模型判 "benign slowness, ok"（避免误报）；确定性路径 rechecks=1。'
if (!audit.includes('P1-3 Watchdog 模型裁定完成')) {
  audit = audit.replace(marker, `${bullet}\n${marker}`)
  writeFileSync(auditPath, audit, 'utf8')
}

const variantPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-variant.md'
let variant = readFileSync(variantPath, 'utf8')
const anchor = '- [x] **P1-2 执行语义**'
const line = '- [x] **P1-3 Watchdog 模型裁定**：`LlmWatchdogJudge` 接入 host，intervention/复查记录进 snapshot；确定性 vs 模型对照见 `WATCHDOG LLM SMOKE OK`。\n'
if (variant.includes(anchor) && !variant.includes('P1-3 Watchdog')) {
  variant = variant.replace(anchor, line + anchor)
  writeFileSync(variantPath, variant, 'utf8')
}
console.log('docs updated')