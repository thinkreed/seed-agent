/** DshRouterClient 离线契约：首轮发完整协议上下文，后续只发增量并复用 session。 */
import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { DshRouterClient } from '../dsh/packages/super-agent/host/lib/index.js'

const dir = mkdtempSync(join(tmpdir(), 'seed-router-dsh-'))
const sessionStorePath = join(dir, 'router-session.json')
const calls = []
let closes = 0
const fake = {
  session() {
    return {
      async run(prompt) {
        calls.push(prompt)
        return {
          sessionId: 'router-session-1',
          finalResponse: '{"reply":"ok"}',
          finishReason: 'stop',
          events: [],
          notifications: [],
        }
      },
    }
  },
  async resumeSession() {
    return this.session()
  },
  async close() {
    closes += 1
  },
}

try {
  const client = new DshRouterClient({
    harness: {},
    harnessFactory: () => fake,
    sessionStorePath,
  })
  const system = { role: 'system', content: 'ROUTER SYSTEM' }
  assert.equal(await client.complete([system, { role: 'user', content: 'first input' }]), '{"reply":"ok"}')
  assert.match(calls[0], /\[ROUTER PROTOCOL\]/)
  assert.match(calls[0], /first input/)

  assert.equal(await client.complete([system, { role: 'user', content: 'second input' }]), '{"reply":"ok"}')
  assert.equal(calls[1], 'second input\n\n只输出请求的 JSON，不要使用工具，不要解释。')
  assert.ok(!calls[1].includes('ROUTER SYSTEM'))
  await client.close()
  assert.equal(closes, 1)
  console.log('ROUTER DSH CONTRACT OK')
} finally {
  rmSync(dir, { recursive: true, force: true })
}