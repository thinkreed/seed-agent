/** Inline & Spill：超预算的指令落盘，prompt 里给摘要 + 可召回路径。 */
import { existsSync, mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { spillInstruction, workerPrompt } from '../lib/index.js'

const dir = mkdtempSync(join(tmpdir(), 'dsh-super-agent-spill-'))
const ticket = { id: 'tk-test', shortName: 't-test', mandate: { scope: 'ticket', strength: 'explicit' } }
const longText = `任务说明：${'这是一段很长的背景上下文，用来触发 Inline & Spill。'.repeat(200)}`
const spilled = spillInstruction(ticket, longText, { threshold: 500, dir })

console.log('spillPath:', spilled.spillPath)
console.log('inline length:', spilled.inline.length)
const prompt = workerPrompt(ticket, spilled.inline)
console.log('prompt has path:', prompt.includes(spilled.spillPath))

const short = spillInstruction(ticket, '短指令', { threshold: 500, dir })
const ok = Boolean(spilled.spillPath) &&
  existsSync(spilled.spillPath) &&
  readFileSync(spilled.spillPath, 'utf8').length === longText.length &&
  spilled.inline.length < longText.length &&
  prompt.includes(spilled.spillPath) &&
  short.spillPath === undefined
console.log(ok ? 'SPILL SMOKE OK' : 'SPILL SMOKE FAIL')
process.exit(ok ? 0 : 1)