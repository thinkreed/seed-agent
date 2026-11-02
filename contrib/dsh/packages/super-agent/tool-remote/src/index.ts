/**
 * 存算分离的端侧入口：worker 通过 super_agent_remote_* 在 daemon 所在机器上执行命令、读写文件。
 * daemon 不保存会话状态，状态仍在 host 的事件库。
 */
import type { Context } from '@deepseek-ai/cordis'
import type { ContentBlock } from '@deepseek-ai/dsh-llm'
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'tool-super-agent-remote'

export const inject: string[] = ['tools']

const outputSchema = {
  type: 'object',
  additionalProperties: false,
  properties: {
    ok: { type: 'boolean' },
    exitCode: { type: 'integer' },
    stdout: { type: 'string' },
    stderr: { type: 'string' },
    path: { type: 'string' },
    text: { type: 'string' },
  },
} as const

const render = (_args: unknown, value: unknown): ContentBlock[] =>
  [{ type: 'text', text: JSON.stringify(value, null, 1) }]

function daemon(device?: string): { url: string; headers: Record<string, string> } {
  const targets = resolveTargets()
  const name = device?.trim() || 'default'
  const target = targets[name] ?? targets.default
  if (!target) throw new Error(`unknown daemon device: ${name}`)
  const token = target.token
  return { url: target.url, headers: { 'content-type': 'application/json', ...(token ? { authorization: `Bearer ${token}` } : {}) } }
}

interface DaemonTarget {
  readonly url: string
  readonly token?: string
}

/** 多设备：SUPER_AGENT_DAEMONS={"laptop":{"url":...,"token":...}}；回退到单 URL。 */
function resolveTargets(): Record<string, DaemonTarget> {
  const raw = process.env.SUPER_AGENT_DAEMONS?.trim()
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as Record<string, { url?: unknown; token?: unknown }>
      const targets: Record<string, DaemonTarget> = {}
      for (const [id, value] of Object.entries(parsed)) {
        if (value && typeof value.url === 'string') {
          targets[id] = { url: value.url, ...(typeof value.token === 'string' ? { token: value.token } : {}) }
        }
      }
      if (Object.keys(targets).length > 0) return targets
    } catch {
      // 配置坏了就退回单设备
    }
  }
  const url = process.env.SUPER_AGENT_DAEMON_URL?.trim()
  if (!url) throw new Error('SUPER_AGENT_DAEMON_URL missing')
  const token = process.env.SUPER_AGENT_DAEMON_TOKEN?.trim()
  return { default: { url, ...(token ? { token } : {}) } }
}

async function call(path: string, init: { method?: string; body?: string } = {}, device?: string): Promise<Record<string, unknown>> {
  const { url, headers } = daemon(device)
  const response = await fetch(`${url}${path}`, { method: init.method ?? 'GET', headers, ...(init.body ? { body: init.body } : {}) })
  const payload = (await response.json()) as Record<string, unknown>
  return payload
}

const DEVICE_PARAM = {
  type: 'string',
  description: 'Daemon device id from SUPER_AGENT_DAEMONS; omit for the default device.',
} as const

export function apply(ctx: Context): void {
  ctx.tools.register(defineTool({
    name: 'super_agent_remote_exec',
    description: 'Run a shell command on the edge daemon (the real working machine). The daemon keeps no session state; use it instead of local shell when the environment lives elsewhere.',
    parameters: {
      command: { type: 'string', required: true, description: 'Shell command to run on the daemon.' },
      cwd: { type: 'string', description: 'Working directory relative to the daemon root.' },
      device: DEVICE_PARAM,
    },
    output: { schema: outputSchema, render },
    execute: async (args) => call('/exec', { method: 'POST', body: JSON.stringify({ command: args.command, ...(args.cwd ? { cwd: args.cwd } : {}) }) }, args.device) as Promise<never>,
  }))

  ctx.tools.register(defineTool({
    name: 'super_agent_remote_write',
    description: 'Write a UTF-8 file on the edge daemon.',
    parameters: {
      path: { type: 'string', required: true, description: 'File path relative to the daemon root.' },
      text: { type: 'string', required: true, description: 'File content.' },
      device: DEVICE_PARAM,
    },
    output: { schema: outputSchema, render },
    execute: async (args) => call('/write', { method: 'POST', body: JSON.stringify({ path: args.path, text: args.text }) }, args.device) as Promise<never>,
  }))

  ctx.tools.register(defineTool({
    name: 'super_agent_remote_read',
    description: 'Read a UTF-8 file from the edge daemon.',
    parameters: {
      path: { type: 'string', required: true, description: 'File path relative to the daemon root.' },
      device: DEVICE_PARAM,
    },
    output: { schema: outputSchema, render },
    execute: async (args) => call(`/read?path=${encodeURIComponent(args.path)}`, {}, args.device) as Promise<never>,
  }))
}