/** Super-agent 主面板：工单列表 + 时间线 + 人的干预。 */
import { createElement, useCallback, useEffect, useMemo, useState } from 'react'

const STATE_URL = '/super-agent/state'
const COMMAND_URL = '/super-agent/command'

export interface ReportView {
  readonly status: string
  readonly summary: string
  readonly at: number
}

export interface TicketView {
  readonly id: string
  readonly shortName: string
  readonly state: string
  readonly stage?: string
  readonly title: string
  readonly source: string
  readonly actor: string
  readonly assignment: { readonly id: string; readonly state: string } | null
  readonly reports: readonly ReportView[]
  readonly updatedAt: number
  readonly queuedInputs?: number
  readonly turns?: number
}

export interface Snapshot {
  readonly ok: boolean
  readonly paused: boolean
  readonly usesDshRuntime: boolean
  readonly storePath: string
  readonly replayHash: string
  readonly lastSeq: number
  readonly router?: {
    readonly mode: string
    readonly memory?: string
    readonly history?: number
    readonly lastBatch?: { readonly threads: number; readonly triggers: number } | null
  }
  readonly tickets: readonly TicketView[]
  readonly config?: {
    readonly assessorMode?: string
    readonly routerMode?: string
    readonly watchdogMode?: string
    readonly sources?: readonly string[]
    readonly speculationEnabled?: boolean
  }
}

async function fetchState(): Promise<Snapshot | undefined> {
  try {
    const response = await fetch(STATE_URL, { headers: { accept: 'application/json' } })
    if (!response.ok) return undefined
    return (await response.json()) as Snapshot
  } catch {
    return undefined
  }
}

async function sendCommand(action: string, ticketId?: string, text?: string): Promise<void> {
  await fetch(COMMAND_URL, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ action, ticketId, text }),
  })
}

const STATE_COLOR: Record<string, string> = {
  open: '#4176e6',
  running: '#d97706',
  ended: '#16a34a',
  blocked: '#dc2626',
  abandoned: '#6b7280',
}

const BUTTON = {
  padding: '5px 10px', borderRadius: 8, border: '1px solid var(--dsw-alias-border-l2, #d1d5db)',
  background: 'var(--dsw-alias-bg-base, #fff)', color: 'inherit', cursor: 'pointer',
} as const

export function SuperAgentPage(): React.ReactElement {
  const [snapshot, setSnapshot] = useState<Snapshot>()
  const [selected, setSelected] = useState<string>()
  const [reply, setReply] = useState('')
  const [busy, setBusy] = useState(false)
  const [chatInput, setChatInput] = useState('')
  const [chatLog, setChatLog] = useState<{ role: 'person' | 'router'; text: string }[]>([])
  const [search, setSearch] = useState('')

  const refresh = useCallback(() => {
    void fetchState().then((value) => {
      if (value) setSnapshot(value)
    })
  }, [])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 2000)
    return () => clearInterval(timer)
  }, [refresh])

  const tickets = snapshot?.tickets ?? []
  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return tickets
    return tickets.filter((ticket) =>
      `${ticket.shortName} ${ticket.title} ${ticket.source} ${ticket.stage ?? ''}`.toLowerCase().includes(needle))
  }, [tickets, search])
  const current = useMemo(() => tickets.find((ticket) => ticket.id === selected) ?? tickets[0], [tickets, selected])

  const act = async (action: string): Promise<void> => {
    setBusy(true)
    try {
      await sendCommand(action, current?.id, action === 'reply' ? reply : undefined)
      if (action === 'reply') setReply('')
      refresh()
    } finally {
      setBusy(false)
    }
  }

  const sendChat = async (): Promise<void> => {
    const text = chatInput.trim()
    if (!text) return
    setChatInput('')
    setChatLog((previous) => [...previous, { role: 'person', text }])
    try {
      const response = await fetch(COMMAND_URL, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ action: 'chat', text }),
      })
      const data = (await response.json()) as { snapshot?: { reply?: string } }
      const answer = data.snapshot?.reply ?? '（Router 没有回复）'
      setChatLog((previous) => [...previous, { role: 'router', text: answer }])
    } catch {
      setChatLog((previous) => [...previous, { role: 'router', text: '（Router 不可用）' }])
    }
    refresh()
  }

  return createElement(
    'div',
    { style: { display: 'flex', height: '100%', background: 'var(--dsw-alias-bg-base, #fff)', color: 'var(--dsw-alias-label-primary, #111)', font: '13px/1.5 system-ui' } },
    createElement(
      'div',
      { style: { width: 320, borderRight: '1px solid var(--dsw-alias-border-l1, #e5e7eb)', display: 'flex', flexDirection: 'column' } },
      createElement(
        'div',
        { style: { padding: '12px 14px', borderBottom: '1px solid var(--dsw-alias-border-l1, #e5e7eb)', display: 'flex', alignItems: 'center', gap: 8 } },
        createElement('strong', { style: { fontSize: 14 } }, 'Super-agent'),
        createElement('span', { style: { color: '#6b7280', fontSize: 11 } }, snapshot?.paused ? 'paused' : 'running'),
        createElement('span', { style: { marginLeft: 'auto', color: '#9ca3af', fontSize: 11 } }, `${tickets.length} tickets`),
      ),
      createElement(
        'div',
        { style: { padding: '8px 14px', borderBottom: '1px solid var(--dsw-alias-border-l1, #e5e7eb)' } },
        createElement('input', {
          value: search,
          onChange: (event) => setSearch(event.target.value),
          placeholder: '搜索工单（标题 / stage / 来源）',
          style: { width: '100%', padding: '6px 9px', borderRadius: 8, border: '1px solid var(--dsw-alias-border-l2, #d1d5db)', background: 'transparent', color: 'inherit', boxSizing: 'border-box' },
        }),
      ),
      createElement(
        'div',
        { style: { overflow: 'auto', flex: 1 } },
        tickets.length === 0
          ? createElement('div', { style: { padding: 16, color: '#9ca3af' } }, '还没有工单：等一个 Trigger，或从对话里产生。')
          : filtered.length === 0
            ? createElement('div', { style: { padding: 16, color: '#9ca3af' } }, '没有匹配的工单。')
            : filtered.map((ticket) => createElement(
            'button',
            {
              key: ticket.id,
              onClick: () => setSelected(ticket.id),
              style: {
                display: 'block', width: '100%', textAlign: 'left', padding: '10px 14px', border: 0,
                borderBottom: '1px solid var(--dsw-alias-border-l1, #f1f5f9)',
                background: current?.id === ticket.id ? 'var(--dsw-alias-bg-l2, #f8fafc)' : 'transparent',
                cursor: 'pointer',
              },
            },
            createElement('div', { style: { display: 'flex', gap: 6, alignItems: 'center' } },
              createElement('span', { style: { width: 6, height: 6, borderRadius: 3, background: STATE_COLOR[ticket.state] ?? '#9ca3af' } }),
              createElement('span', { style: { fontWeight: 600 } }, ticket.shortName),
              createElement('span', { style: { color: '#9ca3af', fontSize: 11 } }, ticket.state),
              ticket.stage ? createElement('span', { style: { color: '#6b7280', fontSize: 10, background: '#f1f5f9', borderRadius: 6, padding: '0 4px' } }, ticket.stage) : null,
              createElement('span', { style: { marginLeft: 'auto', color: '#9ca3af', fontSize: 11 } }, ticket.source),
            ),
            createElement('div', { style: { color: '#4b5563', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, ticket.title || '（无标题）'),
          )),
      ),
    ),
    createElement(
      'div',
      { style: { flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 } },
      createElement(
        'div',
        { style: { padding: '10px 16px', borderBottom: '1px solid var(--dsw-alias-border-l1, #e5e7eb)', display: 'flex', gap: 8, alignItems: 'center' } },
        createElement('strong', null, current ? `${current.shortName} · ${current.state}${current.stage ? ` · ${current.stage}` : ''}` : 'Super-agent'),
        createElement('span', { style: { color: '#9ca3af', fontSize: 11 } }, current?.assignment ? `assignment ${current.assignment.state}` : ''),
        createElement('span', { style: { marginLeft: 'auto', color: '#9ca3af', fontSize: 11 } },
          snapshot ? `seq ${snapshot.lastSeq} · ${snapshot.usesDshRuntime ? 'dsh runtime' : 'pending'}` : ''),
        createElement('button', { onClick: () => void act(snapshot?.paused ? 'resume' : 'pause'), disabled: busy, style: BUTTON },
          snapshot?.paused ? 'Resume' : 'Pause'),
        createElement('button', { onClick: () => void act('retry'), disabled: busy || !current, style: BUTTON }, 'Retry'),
      ),
      createElement(
        'div',
        { style: { flex: 1, overflow: 'auto', padding: 16 } },
        current
          ? createElement(
            'div',
            null,
            createElement('div', { style: { color: '#6b7280', marginBottom: 8 } }, `${current.source} · ${current.actor}`),
            createElement('div', { style: { background: 'var(--dsw-alias-bg-l2, #f8fafc)', borderRadius: 10, padding: 12, marginBottom: 12, whiteSpace: 'pre-wrap' } },
              current.title || '（无指令文本）'),
            ...current.reports.map((report, index) => createElement(
              'div',
              { key: `${report.at}-${index}`, style: { borderLeft: `3px solid ${STATE_COLOR[report.status] ?? '#94a3b8'}`, paddingLeft: 10, marginBottom: 12 } },
              createElement('div', { style: { fontSize: 11, color: '#9ca3af' } }, `${report.status} · #${report.at}`),
              createElement('div', { style: { whiteSpace: 'pre-wrap' } }, report.summary),
            )),
            createElement(
              'div',
              { style: { display: 'flex', gap: 8, marginTop: 8 } },
              createElement('input', {
                value: reply,
                onChange: (event) => setReply(event.target.value),
                placeholder: '回复这个工单（会作为人的干预投递）',
                style: { flex: 1, padding: '8px 10px', borderRadius: 8, border: '1px solid var(--dsw-alias-border-l2, #d1d5db)', background: 'transparent', color: 'inherit' },
              }),
              createElement('button', { onClick: () => void act('reply'), disabled: busy || !reply.trim(), style: BUTTON }, 'Send'),
            ),
          )
          : createElement('div', { style: { color: '#9ca3af' } }, '选择一个工单查看时间线。'),
      ),
      createElement(
        'div',
        { style: { borderTop: '1px solid var(--dsw-alias-border-l1, #e5e7eb)', padding: '8px 16px', maxHeight: 220, overflow: 'auto' } },
        createElement(
          'div',
          { style: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 } },
          createElement('strong', { style: { fontSize: 12 } }, 'Router'),
          createElement('span', { style: { color: '#9ca3af', fontSize: 11 } },
            snapshot?.router
              ? `${snapshot.router.mode}${snapshot.router.lastBatch ? ` · 上一批 ${snapshot.router.lastBatch.threads} threads` : ''}`
              : ''),
        ),
        ...chatLog.slice(-6).map((line, index) => createElement(
          'div',
          { key: `${line.role}-${index}`, style: { marginBottom: 4, color: line.role === 'router' ? '#111' : '#6b7280' } },
          `${line.role === 'router' ? 'Router' : '你'}：${line.text}`,
        )),
        createElement(
          'div',
          { style: { display: 'flex', gap: 8, marginTop: 6 } },
          createElement('input', {
            value: chatInput,
            onChange: (event) => setChatInput(event.target.value),
            onKeyDown: (event) => {
              if (event.key === 'Enter') void sendChat()
            },
            placeholder: '和 Router 说话（跨工单的连续上下文）',
            style: { flex: 1, padding: '7px 10px', borderRadius: 8, border: '1px solid var(--dsw-alias-border-l2, #d1d5db)', background: 'transparent', color: 'inherit' },
          }),
          createElement('button', { onClick: () => void sendChat(), disabled: !chatInput.trim(), style: BUTTON }, 'Send'),
        ),
      ),
      createElement('div', { style: { padding: '6px 16px', borderTop: '1px solid var(--dsw-alias-border-l1, #e5e7eb)', color: '#9ca3af', fontSize: 11 } },
        snapshot
          ? [
            `router ${snapshot.config?.routerMode ?? 'off'}`,
            `watchdog ${snapshot.config?.watchdogMode ?? '?'}`,
            `sources ${(snapshot.config?.sources ?? []).join('+') || 'none'}`,
            `speculation ${snapshot.config?.speculationEnabled ? 'on' : 'off'}`,
            `replay ${snapshot.replayHash.slice(0, 12)}`,
          ].join(' · ')
          : ''),
    ),
  )
}