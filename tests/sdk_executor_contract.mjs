/**
 * SdkDshExecutor 离线契约：不启动 DSH runtime、不联网，用 fake harness 验证
 * 报告长度、session 复用、stop 关闭进程。
 */
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { SdkDshExecutor } from '../dsh/packages/super-agent/host/lib/index.js'

const dir = mkdtempSync(join(tmpdir(), 'seed-executor-contract-'))
const sessionStorePath = join(dir, 'sessions.json')
const assignment = { id: 'as-1', ticketId: 'tk-1', state: 'running' }
const ticket = {
  id: 'tk-1',
  shortName: 't-000001',
  mandate: { scope: 'ticket', strength: 'explicit', triggerId: 'trg-1' },
  threadIds: ['thr-1'],
  channelIds: [],
}

function waitFor(check, timeoutMs = 1000) {
  return new Promise((resolve, reject) => {
    const started = Date.now()
    const timer = setInterval(() => {
      if (check()) {
        clearInterval(timer)
        resolve()
      } else if (Date.now() - started > timeoutMs) {
        clearInterval(timer)
        reject(new Error('timeout'))
      }
    }, 5)
  })
}

try {
  const calls = []
  let closed = false
  const fake = {
    session() {
      return {
        async run(prompt) {
          calls.push({ prompt, options: undefined })
          return {
            sessionId: 'sess-1',
            finalResponse: '完整报告'.repeat(300),
            finishReason: 'stop',
            events: [],
            notifications: [],
          }
        },
      }
    },
    async resumeSession() {
      return {
        async run(prompt) {
          calls.push({ prompt, options: { sessionId: 'sess-1' } })
          return {
            sessionId: 'sess-1',
            finalResponse: '完整报告'.repeat(300),
            finishReason: 'stop',
            events: [],
            notifications: [],
          }
        },
      }
    },
    async close() {
      closed = true
    },
  }
  const reports = []
  const executor = new SdkDshExecutor({
    harness: { dshBin: 'unused', dshHome: dir, profile: 'sdk', provider: 'bailian', model: 'm' },
    harnessFactory: () => fake,
    sessionStorePath,
    clock: { now: () => 1 },
    onReport: (report) => reports.push(report),
    ticketDir: () => join(dir, 'tickets', 'tk-1'),
  })
  await executor.launch(assignment, ticket)
  await waitFor(() => reports.length === 1)
  assert.equal(reports[0].status, 'ready')
  assert.equal(reports[0].summary.length, 1200, 'summary must not be truncated to 600')
  assert.equal(calls[0].options?.sessionId, undefined)
  assert.ok(readFileSync(sessionStorePath, 'utf8').includes('sess-1'))

  const secondCalls = []
  const second = new SdkDshExecutor({
    harness: { dshBin: 'unused', dshHome: dir, profile: 'sdk', provider: 'bailian', model: 'm' },
    harnessFactory: () => ({
      session() {
        return {
          async run(prompt) {
            secondCalls.push({ prompt, options: undefined })
            return {
              sessionId: 'sess-1',
              finalResponse: 'ok',
              finishReason: 'stop',
              events: [],
              notifications: [],
            }
          },
        }
      },
      async resumeSession() {
        return {
          async run(prompt) {
            secondCalls.push({ prompt, options: { sessionId: 'sess-1' } })
            return {
              sessionId: 'sess-1',
              finalResponse: 'ok',
              finishReason: 'stop',
              events: [],
              notifications: [],
            }
          },
        }
      },
      async close() {},
    }),
    sessionStorePath,
    clock: { now: () => 2 },
    onReport: () => undefined,
  })
  await second.launch(assignment, ticket)
  await waitFor(() => secondCalls.length === 1)
  assert.equal(secondCalls[0].options?.sessionId, 'sess-1', 'sessionId must survive executor restart')

  let stopClosed = false
  const hanging = new SdkDshExecutor({
    harness: { dshBin: 'unused', dshHome: dir, profile: 'sdk', provider: 'bailian', model: 'm' },
    harnessFactory: () => ({
      session() {
        return { run: async () => new Promise(() => undefined) }
      },
      async resumeSession() {
        return { run: async () => new Promise(() => undefined) }
      },
      async close() {
        stopClosed = true
      },
    }),
    clock: { now: () => 3 },
    onReport: () => undefined,
  })
  await hanging.launch({ ...assignment, id: 'as-2' }, ticket)
  await new Promise((resolve) => setTimeout(resolve, 20))
  await hanging.stop({ ...assignment, id: 'as-2' })
  assert.equal(stopClosed, true, 'stop must close the runtime')
  await executor.close()
  await second.close()
  console.log('EXECUTOR CONTRACT OK')
} finally {
  rmSync(dir, { recursive: true, force: true })
}