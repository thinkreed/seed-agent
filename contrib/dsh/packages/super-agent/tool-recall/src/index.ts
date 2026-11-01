/**
 * Model-facing `super_agent_recall`: 在 Super-agent 的召回索引上按 id 逐跳展开上下文。
 *
 * 索引由 host 的 writeRecallIndex() 生成（triggers / threads / tickets 引用图），
 * 路径通过环境变量 SUPER_AGENT_RECALL_INDEX 传给 SDK worker。
 * 每次召回都返回下一跳 handles，模型可以 trigger → thread → ticket 逐跳追。
 */
import { readFileSync } from 'node:fs'

import type { Context } from '@deepseek-ai/cordis'
import type { ContentBlock } from '@deepseek-ai/dsh-llm'
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'tool-super-agent-recall'

export const inject: string[] = ['tools']

export type RecallKind = 'trigger' | 'thread' | 'ticket'

export interface RecallHandle {
  readonly kind: RecallKind
  readonly id: string
}

export interface RecallTrigger {
  readonly source?: string
  readonly actor?: string
  readonly text?: string
  readonly threadIds?: readonly string[]
  readonly channelIds?: readonly string[]
  readonly at?: number
}

export interface RecallThread {
  readonly triggerIds?: readonly string[]
  readonly ticketIds?: readonly string[]
}

export interface RecallTicket {
  readonly shortName?: string
  readonly state?: string
  readonly threadIds?: readonly string[]
  readonly channelIds?: readonly string[]
  readonly triggerId?: string
  readonly reports?: readonly { readonly status?: string; readonly summary?: string; readonly at?: number }[]
}

export interface RecallIndexFile {
  readonly writeAt?: number
  readonly triggers?: Record<string, RecallTrigger>
  readonly threads?: Record<string, RecallThread>
  readonly tickets?: Record<string, RecallTicket>
}

export interface RecallResult {
  readonly kind: RecallKind
  readonly id: string
  readonly found: boolean
  readonly summary: string
  readonly text: string
  readonly handles: readonly RecallHandle[]
}

export function recallFromIndex(index: RecallIndexFile, kind: RecallKind, id: string): RecallResult {
  if (kind === 'trigger') {
    const trigger = index.triggers?.[id]
    if (!trigger) return missing(kind, id)
    const threads = (trigger.threadIds ?? []).map((threadId) => ({ kind: 'thread' as const, id: threadId }))
    return {
      kind, id, found: true,
      summary: `${trigger.source ?? 'unknown'} · ${trigger.actor ?? 'unknown'} · ${(trigger.at ?? 0)}`,
      text: trigger.text ?? '',
      handles: threads,
    }
  }
  if (kind === 'thread') {
    const thread = index.threads?.[id]
    if (!thread) return missing(kind, id)
    const handles: RecallHandle[] = [
      ...(thread.triggerIds ?? []).map((triggerId) => ({ kind: 'trigger' as const, id: triggerId })),
      ...(thread.ticketIds ?? []).map((ticketId) => ({ kind: 'ticket' as const, id: ticketId })),
    ]
    return {
      kind, id, found: true,
      summary: `${handles.filter((handle) => handle.kind === 'trigger').length} triggers · ${handles.filter((handle) => handle.kind === 'ticket').length} tickets`,
      text: '',
      handles,
    }
  }
  const ticket = index.tickets?.[id]
  if (!ticket) return missing(kind, id)
  const handles: RecallHandle[] = [
    ...(ticket.triggerId ? [{ kind: 'trigger' as const, id: ticket.triggerId }] : []),
    ...(ticket.threadIds ?? []).map((threadId) => ({ kind: 'thread' as const, id: threadId })),
  ]
  const reports = ticket.reports ?? []
  return {
    kind, id, found: true,
    summary: `${ticket.shortName ?? id} · ${ticket.state ?? 'unknown'}`,
    text: reports.map((report) => `[${report.status ?? '?'}] ${report.summary ?? ''}`).join('\n'),
    handles,
  }
}

export function readRecallIndex(path = process.env.SUPER_AGENT_RECALL_INDEX ?? ''): RecallIndexFile | undefined {
  if (!path) return undefined
  try {
    return JSON.parse(readFileSync(path, 'utf8')) as RecallIndexFile
  } catch {
    return undefined
  }
}

function missing(kind: RecallKind, id: string): RecallResult {
  return { kind, id, found: false, summary: `${kind} not found`, text: '', handles: [] }
}

const RECALL_DESCRIPTION = [
  'Recall Super-agent context by id, following the reference graph hop by hop.',
  'kind=trigger returns the message text and its thread handles;',
  'kind=thread returns trigger and ticket handles;',
  'kind=ticket returns reports and thread/trigger handles.',
  'Call again with any returned handle to walk further (trigger → thread → ticket).',
].join(' ')

export function apply(ctx: Context): void {
  ctx.tools.register(defineTool({
    name: 'super_agent_recall',
    description: RECALL_DESCRIPTION,
    parameters: {
      kind: { type: 'string', required: true, enum: ['trigger', 'thread', 'ticket'], description: 'Object kind to recall.' },
      id: { type: 'string', required: true, description: 'Object id from a previous result or the injected context.' },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          kind: { type: 'string' },
          id: { type: 'string' },
          found: { type: 'boolean' },
          summary: { type: 'string' },
          text: { type: 'string' },
          handles: {
            type: 'array',
            items: {
              type: 'object',
              additionalProperties: false,
              properties: { kind: { type: 'string' }, id: { type: 'string' } },
            },
          },
        },
      } as const,
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 1) }] as ContentBlock[],
    },
    execute: async (args) => {
      const index = readRecallIndex()
      if (!index) {
        return { kind: args.kind, id: args.id, found: false, summary: 'recall index not available', text: '', handles: [] }
      }
      const result = recallFromIndex(index, args.kind, args.id)
      return {
        kind: result.kind,
        id: result.id,
        found: result.found,
        summary: result.summary,
        text: result.text,
        handles: result.handles.map((handle) => ({ kind: handle.kind, id: handle.id })),
      }
    },
  }))
}