/**
 * Super-agent 的 HTTP 面：给 client 插件（DSH 侧栏工作台）读状态、下命令。
 *
 * 为什么不用 typert Remote：这层只需要"读快照 + 五个命令"，用 webServer 上的
 * 两个 exact 路由更小、更容易在 fork 里维护；以后要严格类型 RPC 再升级。
 */

import type { IncomingMessage, ServerResponse } from 'node:http'

/** 一条路由的响应写入器。 */
export type RouteHandler = (req: IncomingMessage, res: ServerResponse) => void | Promise<void>

export interface SuperAgentHttpRoutes {
  readonly statePath: string
  readonly commandPath: string
  readonly snapshot: () => unknown
  readonly command: (input: CommandInput) => unknown
}

export interface CommandInput {
  readonly action: 'pause' | 'resume' | 'retry' | 'reply' | 'ingest'
  readonly ticketId?: string
  readonly text?: string
  /** ingest 的回帖地址：`oc_...`（飞书）、`gh:owner/repo#123`（GitHub）或 local。 */
  readonly channel?: string
}

/** 读 JSON body（上限 1MB；超限拒绝）。 */
async function readJson(req: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = []
  let total = 0
  for await (const chunk of req) {
    const buf = chunk as Buffer
    total += buf.length
    if (total > 1_000_000) throw new Error('body too large')
    chunks.push(buf)
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8')) as unknown
}

function sendJson(res: ServerResponse, status: number, value: unknown): void {
  res.statusCode = status
  res.setHeader('content-type', 'application/json; charset=utf-8')
  res.setHeader('cache-control', 'no-store')
  res.end(JSON.stringify(value))
}

/** 把 Super-agent 的读写挂在 webServer 上；返回两个 disposer。 */
export function mountHttpRoutes(routes: SuperAgentHttpRoutes): {
  state: RouteHandler
  command: RouteHandler
} {
  return {
    state: (_req, res) => {
      sendJson(res, 200, routes.snapshot())
    },
    command: async (req, res) => {
      try {
        const body = await readJson(req)
        const input = body as CommandInput
        if (typeof input?.action !== 'string') throw new Error('action required')
        sendJson(res, 200, { ok: true, snapshot: routes.command(input) })
      } catch (error) {
        sendJson(res, 400, { ok: false, error: String(error) })
      }
    },
  }
}

export { sendJson }