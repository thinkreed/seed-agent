/**
 * 异步 ReAct 工具：start() 立即返回 Started，命令在后台跑；status()/stop() 取结果或终止。
 * 对应文章 §4.1 的 start/stop 语义——worker 不必等待长命令，回合可以继续。
 */
import { spawn, spawnSync } from 'node:child_process'
import { appendFileSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'

import type { Context } from '@deepseek-ai/cordis'
import type { ContentBlock } from '@deepseek-ai/dsh-llm'
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'tool-super-agent-background'

export const inject: string[] = ['tools']

interface JobRecord {
  readonly child: ReturnType<typeof spawn>
  readonly logPath: string
  readonly startedAt: number
}

const jobs = new Map<string, JobRecord>()

function jobsDir(): string {
  const dir = process.env.SUPER_AGENT_JOB_DIR?.trim() || join(process.cwd(), '.seed', 'jobs')
  mkdirSync(dir, { recursive: true })
  return dir
}

/** Windows 优先用系统自带的 Windows PowerShell，PATH 里没有 pwsh 时也能起后台命令。 */
function powershellPath(): string {
  const root = process.env.SystemRoot?.trim()
  return root ? join(root, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe') : 'powershell.exe'
}

function logTail(path: string, limit = 1200): string {
  try {
    return readFileSync(path, 'utf8').slice(-limit)
  } catch {
    return ''
  }
}

function statusOf(job: JobRecord): string {
  return job.child.exitCode !== null
    ? job.child.exitCode === 0 ? 'done' : 'failed'
    : job.child.signalCode !== null ? 'stopped' : 'running'
}

function killTree(pid: number | undefined): void {
  if (pid === undefined) return
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], { windowsHide: true })
  } else {
    try { process.kill(-pid, 'SIGTERM') } catch { try { process.kill(pid) } catch { /* already gone */ } }
  }
}

const START_DESCRIPTION = [
  'Start a long-running command in the background and return immediately (Started).',
  'The command keeps running while you continue the conversation; do not wait for it.',
  'Pass ticketId (the Super-agent ticket id in your task) so the completion is delivered back to this session as a new message.',
  'Poll with super_agent_status(jobId), terminate with super_agent_stop(jobId).',
  'Backend is pwsh on Windows, sh elsewhere.',
].join(' ')

const STATUS_DESCRIPTION = 'Check a background job: status (running|done|failed|stopped), exit code, and the tail of its log.'

const STOP_DESCRIPTION = 'Stop a background job and its child process tree.'

export function apply(ctx: Context): void {
  ctx.tools.register(defineTool({
    name: 'super_agent_start',
    description: START_DESCRIPTION,
    parameters: {
      command: { type: 'string', required: true, description: 'Shell command to run in the background.' },
      cwd: { type: 'string', description: 'Working directory (defaults to the current session workspace).' },
      ticketId: { type: 'string', description: 'Super-agent ticket id; completion is delivered back to this session when set.' },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          jobId: { type: 'string' },
          started: { type: 'boolean' },
          pid: { type: 'integer' },
          logPath: { type: 'string' },
        },
      } as const,
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 1) }] as ContentBlock[],
    },
    execute: async (args) => {
      const id = `job-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
      const dir = jobsDir()
      const logPath = join(dir, `${id}.log`)
      const cwd = resolve(args.cwd ?? process.env.SUPER_AGENT_WORKSPACE ?? process.cwd())
      writeFileSync(logPath, `command: ${args.command}\ncwd: ${cwd}\n`, 'utf8')
      const shell = process.platform === 'win32'
        ? powershellPath()
        : 'sh'
      const shellArgs = process.platform === 'win32'
        ? ['-NoProfile', '-Command', args.command]
        : ['-c', args.command]
      const child = spawn(shell, shellArgs, {
        cwd,
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
      })
      const record: JobRecord = { child, logPath, startedAt: Date.now() }
      const sink = (chunk: Buffer): void => {
        try { appendFileSync(logPath, chunk) } catch { /* best effort */ }
      }
      child.stdout?.on('data', sink)
      child.stderr?.on('data', sink)
      child.on('error', (error) => {
        try { appendFileSync(logPath, `spawn error: ${String(error)}\n`) } catch { /* best effort */ }
      })
      // 完成即回灌：写成 host 可消费的 reply 请求（文章 §4.1：结果作为新事件回到会话）。
      child.on('close', (code) => {
        const ticketId = typeof args.ticketId === 'string' ? args.ticketId : ''
        const controlDir = process.env.SUPER_AGENT_CONTROL_DIR?.trim()
        if (!ticketId || !controlDir) return
        try {
          mkdirSync(controlDir, { recursive: true })
          const status = code === 0 ? 'done' : 'failed'
          writeFileSync(
            join(controlDir, `job-${id}.json`),
            JSON.stringify({
              action: 'reply',
              ticketId,
              text: `[后台任务 ${id} ${status}]\n${logTail(logPath, 800)}`,
            }),
            'utf8',
          )
        } catch { /* best effort */ }
      })
      jobs.set(id, record)
      return { jobId: id, started: true, pid: child.pid ?? 0, logPath }
    },
  }))

  ctx.tools.register(defineTool({
    name: 'super_agent_status',
    description: STATUS_DESCRIPTION,
    parameters: {
      jobId: { type: 'string', required: true, description: 'Id returned by super_agent_start.' },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          jobId: { type: 'string' },
          status: { type: 'string' },
          exitCode: { type: 'integer' },
          tail: { type: 'string' },
        },
      } as const,
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 1) }] as ContentBlock[],
    },
    execute: async (args) => {
      const job = jobs.get(args.jobId)
      if (!job) return { jobId: args.jobId, status: 'unknown', exitCode: -1, tail: '' }
      return {
        jobId: args.jobId,
        status: statusOf(job),
        exitCode: job.child.exitCode ?? -1,
        tail: logTail(job.logPath),
      }
    },
  }))

  ctx.tools.register(defineTool({
    name: 'super_agent_stop',
    description: STOP_DESCRIPTION,
    parameters: {
      jobId: { type: 'string', required: true, description: 'Id returned by super_agent_start.' },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: { jobId: { type: 'string' }, stopped: { type: 'boolean' }, status: { type: 'string' } },
      } as const,
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 1) }] as ContentBlock[],
    },
    execute: async (args) => {
      const job = jobs.get(args.jobId)
      if (!job) return { jobId: args.jobId, stopped: false, status: 'unknown' }
      killTree(job.child.pid)
      return { jobId: args.jobId, stopped: true, status: 'stopped' }
    },
  }))
}