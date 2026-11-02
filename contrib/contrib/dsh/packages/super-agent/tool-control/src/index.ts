/**
 * Worker 控制工具：把超出范围的工作交回 Router（handback），或取消订阅（unsubscribe）。
 * 工具只写请求文件到 SUPER_AGENT_CONTROL_DIR，host 在下一次 tick 统一应用并删除。
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

import type { Context } from '@deepseek-ai/cordis'
import type { ContentBlock } from '@deepseek-ai/dsh-llm'
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'tool-super-agent-control'

export const inject: string[] = ['tools']

function controlDir(): string {
  const dir = process.env.SUPER_AGENT_CONTROL_DIR?.trim() || join(process.cwd(), '.seed', 'control')
  mkdirSync(dir, { recursive: true })
  return dir
}

function writeRequest(request: Record<string, unknown>): string {
  const file = join(controlDir(), `${String(request.action)}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}.json`)
  writeFileSync(file, JSON.stringify(request), 'utf8')
  return file
}

const OUTPUT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: { requested: { type: 'boolean' }, file: { type: 'string' } },
} as const

const render = (_args: unknown, value: unknown): ContentBlock[] =>
  [{ type: 'text', text: JSON.stringify(value, null, 1) }]

export function apply(ctx: Context): void {
  ctx.tools.register(defineTool({
    name: 'super_agent_handback',
    description: 'Hand this work back to the Router when it is out of scope: the Thread subscription is removed and the latest event is re-evaluated by the Router (which may open a new ticket or ignore it).',
    parameters: {
      ticketId: { type: 'string', required: true, description: 'Current ticket id from the task prompt.' },
      reason: { type: 'string', description: 'Why this work does not belong to the ticket.' },
    },
    output: { schema: OUTPUT_SCHEMA, render },
    execute: async (args) => ({ requested: true, file: writeRequest({ action: 'handback', ticketId: args.ticketId, reason: args.reason ?? '' }) }),
  }))

  ctx.tools.register(defineTool({
    name: 'super_agent_unsubscribe',
    description: 'Stop receiving events from a Thread without re-evaluating it. Use when the Thread is clearly no longer relevant.',
    parameters: {
      ticketId: { type: 'string', required: true, description: 'Current ticket id from the task prompt.' },
      threadId: { type: 'string', description: 'Thread address to unsubscribe (defaults to all of the ticket threads).' },
    },
    output: { schema: OUTPUT_SCHEMA, render },
    execute: async (args) => ({
      requested: true,
      file: writeRequest({
        action: 'unsubscribe',
        ticketId: args.ticketId,
        ...(args.threadId === undefined ? {} : { threadId: args.threadId }),
      }),
    }),
  }))
}