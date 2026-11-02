/**
 * 端侧轻量 daemon（文章 §5.2）：只执行命令/读取文件，不保存任何会话状态。
 * 计算与状态在 host（SQLite + Router/Worker），真实工作环境留在这里。
 */
import { existsSync, readFileSync } from 'node:fs'
import { createServer } from 'node:http'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { dirname, isAbsolute, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

export interface DaemonOptions {
  readonly root: string
  readonly token?: string
  readonly port?: number
  readonly host?: string
}

export interface DaemonExecResult {
  readonly exitCode: number
  readonly stdout: string
  readonly stderr: string
}

export function startDaemon(options: DaemonOptions): ReturnType<typeof createServer> {
  const root = resolve(options.root)
  const token = options.token?.trim()
  const server = createServer((request, response) => {
    void handle(request, response, root, token)
  })
  server.listen(options.port ?? 0, options.host ?? '127.0.0.1')
  return server
}

async function handle(request: IncomingMessage, response: ServerResponse, root: string, token: string | undefined): Promise<void> {
  const url = new URL(request.url ?? '/', 'http://daemon')
  if (url.pathname === '/health') return sendJson(response, 200, { ok: true, root })
  if (token && request.headers.authorization !== `Bearer ${token}`) {
    return sendJson(response, 401, { ok: false, error: 'unauthorized' })
  }
  try {
    if (url.pathname === '/exec' && request.method === 'POST') {
      const body = await readJson<{ command?: string; cwd?: string; timeoutMs?: number }>(request)
      if (!body.command) return sendJson(response, 400, { ok: false, error: 'command required' })
      const result = await execCommand(body.command, resolveCwd(root, body.cwd), body.timeoutMs ?? 120_000)
      return sendJson(response, 200, { ok: true, ...result })
    }
    if (url.pathname === '/read') {
      const path = resolveCwd(root, url.searchParams.get('path') ?? '')
      if (!existsSync(path)) return sendJson(response, 404, { ok: false, error: 'not found' })
      return sendJson(response, 200, { ok: true, path, text: readFileSync(path, 'utf8').slice(0, 200_000) })
    }
    if (url.pathname === '/write' && request.method === 'POST') {
      const body = await readJson<{ path?: string; text?: string }>(request)
      if (!body.path || typeof body.text !== 'string') return sendJson(response, 400, { ok: false, error: 'path and text required' })
      const path = resolveCwd(root, body.path)
      const { mkdirSync, writeFileSync } = await import('node:fs')
      mkdirSync(dirname(path), { recursive: true })
      writeFileSync(path, body.text, 'utf8')
      return sendJson(response, 200, { ok: true, path })
    }
    return sendJson(response, 404, { ok: false, error: 'unknown endpoint' })
  } catch (error) {
    return sendJson(response, 500, { ok: false, error: String(error).slice(0, 400) })
  }
}

/** 路径限制在 daemon root 内（拒绝逃逸），相对路径按 root 解析。 */
function resolveCwd(root: string, path: string | undefined): string {
  const candidate = path && path.trim() ? resolve(root, path) : root
  const normalized = candidate.replaceAll('\\', '/')
  if (!normalized.startsWith(root.replaceAll('\\', '/'))) throw new Error(`path escapes daemon root: ${path}`)
  return candidate
}

function execCommand(command: string, cwd: string, timeoutMs: number): Promise<DaemonExecResult> {
  return new Promise((resolvePromise) => {
    const shell = process.platform === 'win32'
      ? join(process.env.SystemRoot ?? 'C:\\Windows', 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
      : 'sh'
    const args = process.platform === 'win32' ? ['-NoProfile', '-Command', command] : ['-c', command]
    const child = spawn(shell, args, { cwd, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] })
    let stdout = ''
    let stderr = ''
    child.stdout?.on('data', (chunk: Buffer) => { stdout += chunk.toString('utf8') })
    child.stderr?.on('data', (chunk: Buffer) => { stderr += chunk.toString('utf8') })
    const timer = setTimeout(() => { child.kill() }, timeoutMs)
    child.on('error', (error) => {
      clearTimeout(timer)
      resolvePromise({ exitCode: -1, stdout, stderr: `${stderr}\n${String(error)}` })
    })
    child.on('close', (code) => {
      clearTimeout(timer)
      resolvePromise({ exitCode: code ?? -1, stdout: stdout.slice(-200_000), stderr: stderr.slice(-20_000) })
    })
  })
}

function readJson<T>(request: IncomingMessage): Promise<T> {
  return new Promise((resolvePromise, reject) => {
    let body = ''
    request.on('data', (chunk: Buffer) => {
      body += chunk.toString('utf8')
      if (body.length > 1_000_000) {
        reject(new Error('body too large'))
        request.destroy()
      }
    })
    request.on('end', () => {
      try { resolvePromise(JSON.parse(body || '{}') as T) } catch (error) { reject(error) }
    })
    request.on('error', reject)
  })
}

function sendJson(response: ServerResponse, status: number, payload: unknown): void {
  const body = JSON.stringify(payload)
  response.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'content-length': Buffer.byteLength(body) })
  response.end(body)
}

// 直接运行时：SA_DAEMON_ROOT / SA_DAEMON_TOKEN / SA_DAEMON_PORT
if (process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))) {
  const port = Number(process.env.SA_DAEMON_PORT ?? 0)
  const server = startDaemon({
    root: process.env.SA_DAEMON_ROOT ?? process.cwd(),
    ...(process.env.SA_DAEMON_TOKEN ? { token: process.env.SA_DAEMON_TOKEN } : {}),
    port,
  })
  server.on('listening', () => {
    const address = server.address()
    const actual = typeof address === 'object' && address ? address.port : port
    console.log(JSON.stringify({ ok: true, port: actual, root: process.env.SA_DAEMON_ROOT ?? process.cwd() }))
  })
}

export { isAbsolute }