import { useState, useRef, useEffect, useCallback } from 'react'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import NavBar from '../components/NavBar'
import { useSpeechRecognition } from '../hooks/useSpeechRecognition'
import { useSpeechSynthesis } from '../hooks/useSpeechSynthesis'

import { ToolResultCard, ToolCallingSkeleton } from '../components/corvin/ToolResultCard'
import {
  createSession, listSessions, getSession, deleteSession, streamChat,
  type CorvinSession, type AgentEvent,
} from '../api/corvinApi'

import MermaidChart from '../components/common/MermaidChart'
import ApimChart, { type ApimChartData } from '../components/charts/ApimChart'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ToolStep {
  id: string
  toolName: string
  status: 'calling' | 'done' | 'error'
  resultPreview?: string
}

interface UiMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  thinking?: string
  thinkingCollapsed?: boolean
  toolSteps?: ToolStep[]
  chartData: ApimChartData[]
}

interface ToolEvent {
  id: string
  type: 'calling' | 'result'
  toolName: string
  data?: unknown
  timestamp: string
}

// ── Tool label helpers ────────────────────────────────────────────────────────

const TOOL_LABELS: Record<string, string> = {
  get_platform_stats: 'Platform Stats', list_recent_incidents: 'Recent Incidents',
  get_investigation_detail: 'Investigation Detail', get_predictive_alerts: 'Predictive Alerts',
  get_service_score: 'Service Score', get_roi: 'ROI Metrics',
  get_service_topology: 'Service Topology', get_blast_radius: 'Blast Radius',
  get_postmortem: 'Post-Mortem', get_similar_incidents: 'Similar Incidents',
  get_site_knowledge: 'Site Knowledge', get_runbook: 'Runbook',
  run_kql: 'Log Analytics Query', get_aks_health: 'AKS Health',
  get_container_resource_metrics: 'Container Resource Metrics',
  run_elastic_query: 'Container Resource Metrics',
  query_apim_analytics: 'APIM Analytics',
}

const TOOL_ICONS: Record<string, string> = {
  get_platform_stats: '📊', list_recent_incidents: '📋', get_investigation_detail: '🔍',
  get_predictive_alerts: '⚠️', get_service_score: '🎯', get_roi: '💰',
  get_service_topology: '🗺️', get_blast_radius: '💥', get_postmortem: '📄',
  get_similar_incidents: '🔁', get_site_knowledge: '🏗️', get_runbook: '📖',
  run_kql: '🔬', get_aks_health: '☸️',
  get_container_resource_metrics: '📈',
  run_elastic_query: '📈',
  query_apim_analytics: '📈',
}

function extractPreview(toolName: string, data: unknown): string {
  if (!data) return ''
  const d = data as any
  if (d?.error) return `⚠ ${d.error}`.slice(0, 50)
  switch (toolName) {
    case 'list_recent_incidents': return Array.isArray(d) ? `${d.length} incidents` : ''
    case 'get_platform_stats': return `MTTR ${Number(d.avg_mttr_minutes ?? 0).toFixed(1)} min · ${d.total_investigations ?? 0} total`
    case 'get_investigation_detail': return `${d.request?.service_name} · ${d.request?.environment} · ${d.request?.approval_status}`
    case 'get_predictive_alerts': return Array.isArray(d) ? `${d.length} alerts` : ''
    case 'get_service_score': return `Score: ${Number(d.score ?? 0).toFixed(0)}/100`
    case 'get_roi': return `${Number(d.hours_saved ?? 0).toFixed(1)}h saved · $${Number(d.cost_saved ?? 0).toFixed(0)}`
    case 'get_aks_health': return `${(d.pods as any[])?.length ?? 0} pods`
    case 'get_container_resource_metrics': {
      const svc = d?.service ?? {}
      const cpu = typeof svc?.cpu_mcores === 'number' ? svc.cpu_mcores.toFixed(1) : '—'
      const mem = typeof svc?.memory_mib === 'number' ? svc.memory_mib.toFixed(1) : '—'
      return `CPU ${cpu} mC · Memory ${mem} MiB`
    }
    case 'run_kql': return Array.isArray(d) ? `${d.length} rows` : 'Query complete'
    case 'query_apim_analytics': return d.row_count != null ? `${d.row_count} rows · ${d.title ?? ''}`.slice(0, 60) : 'Chart ready'
    case 'get_site_knowledge': return `${Math.round((typeof d === 'string' ? d.length : 0) / 100) / 10}k chars`
    case 'get_runbook': return 'Runbook loaded'
    default: return 'Done'
  }
}

// ── Markdown components (reuse widget pattern) ─────────────────────────────────

const mdComponents: Record<string, React.ComponentType<any>> = {
  // Suppress the <pre> wrapper for mermaid blocks so the diagram renders clean.
  // For all other code blocks render a styled <pre>.
  pre: ({ children }) => {
    // children is typically a <code> element — check if it's a mermaid block
    const child = Array.isArray(children) ? children[0] : children
    const isMermaid = child?.props?.className === 'language-mermaid'
    if (isMermaid) return <>{children}</>
    return (
      <div style={{ overflowX: 'auto', margin: '8px 0', borderRadius: 8, border: '1px solid var(--c-border)' }}>
        <pre style={{ margin: 0, background: 'var(--c-surface-2)', padding: '10px 14px', borderRadius: 8, fontSize: '0.75rem', fontFamily: 'var(--font-mono)', overflowX: 'auto' }}>
          {children}
        </pre>
      </div>
    )
  },
  code: ({ className, children }) => {
    if (className === 'language-mermaid') {
      return <MermaidChart chart={String(children).trim()} />
    }
    if (className?.startsWith('language-')) {
      return <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>{children}</code>
    }
    return <code style={{ background: 'var(--c-surface-3)', color: 'var(--c-signal)', borderRadius: 4, padding: '1px 5px', fontFamily: 'var(--font-mono)', fontSize: '0.8em' }}>{children}</code>
  },
  table: ({ children }) => <div style={{ overflowX: 'auto', margin: '8px 0' }}><table style={{ borderCollapse: 'collapse', width: '100%', fontSize: '0.75rem' }}>{children}</table></div>,
  th: ({ children }) => <th style={{ border: '1px solid var(--c-border)', padding: '6px 10px', background: 'var(--c-surface)', color: 'var(--c-signal)', textAlign: 'left' }}>{children}</th>,
  td: ({ children }) => <td style={{ border: '1px solid var(--c-border)', padding: '6px 10px' }}>{children}</td>,
}

// ── Bot icon ──────────────────────────────────────────────────────────────────

function CorvinIcon({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
      <defs>
        <linearGradient id="ci" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop stopColor="#0f766e"/><stop offset="1" stopColor="#14b8a6"/>
        </linearGradient>
      </defs>
      <path d="M16 2 L28 9 L28 23 L16 30 L4 23 L4 9 Z" fill="url(#ci)" opacity="0.15" stroke="url(#ci)" strokeWidth="1.5"/>
      <rect x="9" y="13" width="5" height="2.5" rx="1.25" fill="#0d9488"/>
      <rect x="18" y="13" width="5" height="2.5" rx="1.25" fill="#0d9488"/>
      <rect x="11" y="18.5" width="10" height="1.5" rx="0.75" fill="#0d9488" opacity="0.7"/>
      <line x1="16" y1="2" x2="16" y2="6" stroke="#0d9488" strokeWidth="1.5" strokeLinecap="round"/>
      <circle cx="16" cy="5" r="1.5" fill="#0d9488"/>
    </svg>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function CorvinCommandPage() {
  const [sessions, setSessions] = useState<CorvinSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<UiMessage[]>([])
  const [toolEvents, setToolEvents] = useState<ToolEvent[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingSessions, setLoadingSessions] = useState(true)
  const [sessionError, setSessionError] = useState<string | null>(null)
  const [showToolPanel, setShowToolPanel] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const prevMessagesLengthRef = useRef(0)
  const prevLastMessageContentRef = useRef('')
  const [speakingMsgId, setSpeakingMsgId] = useState<string | null>(null)

  // ── Speech hooks ──
  const onSpeechResult = useCallback((transcript: string) => {
    setInput(prev => (prev ? prev + ' ' : '') + transcript)
    inputRef.current?.focus()
  }, [])
  const { listening, interim, supported: sttSupported, start: startMic, stop: stopMic } = useSpeechRecognition(onSpeechResult)
  const { speaking: ttsSpeaking, supported: ttsSupported, speak: ttsSpeak, stop: ttsStop } = useSpeechSynthesis()

  // Sync speakingMsgId when TTS finishes
  useEffect(() => { if (!ttsSpeaking) setSpeakingMsgId(null) }, [ttsSpeaking])

  const handleSpeak = useCallback((msgId: string, content: string) => {
    if (speakingMsgId === msgId) { ttsStop(); setSpeakingMsgId(null); return }
    ttsStop()
    setSpeakingMsgId(msgId)
    ttsSpeak(content)
  }, [speakingMsgId, ttsStop, ttsSpeak])

  // Auto-scroll chat
  useEffect(() => {
    const lastMsg = messages[messages.length - 1]
    const contentChanged = lastMsg?.role === 'assistant' && lastMsg.content.length > prevLastMessageContentRef.current.length
    const newMsgAdded = messages.length > prevMessagesLengthRef.current

    if (newMsgAdded || contentChanged) {
      endRef.current?.scrollIntoView({ behavior: 'smooth' })
    }

    prevMessagesLengthRef.current = messages.length
    prevLastMessageContentRef.current = lastMsg?.content || ''
  }, [messages])



  // Load session list
  const refreshSessions = useCallback(async () => {
    try {
      const list = await listSessions()
      setSessions(list)
    } catch { /* non-fatal */ }
    finally { setLoadingSessions(false) }
  }, [])

  useEffect(() => { refreshSessions() }, [refreshSessions])

  // Switch to a session
  const selectSession = useCallback(async (sessionId: string) => {
    setActiveSessionId(sessionId)
    setToolEvents([])
    try {
      const detail = await getSession(sessionId)
      setMessages(detail.messages.map((m) => {
        // Restore chart data from DB-stored tool_results
        // Restore chart data: new format is array, old format is single object — normalize both
        const rawApim = m.tool_results?.['query_apim_analytics']
        const apimResults: ApimChartData[] = Array.isArray(rawApim)
          ? rawApim as ApimChartData[]
          : rawApim ? [rawApim as ApimChartData] : []
        return {
          id: String(m.id),
          role: m.role,
          content: m.content,
          thinking: m.thinking || undefined,
          thinkingCollapsed: true,
          chartData: apimResults,
          toolSteps: m.tool_calls?.calls.map((c, i) => ({
            id: `hist-${m.id}-${i}`,
            toolName: c.tool_name,
            status: 'done' as const,
            resultPreview: c.tool_name === 'query_apim_analytics' && apimResults.length > 0
              ? `${apimResults[apimResults.length - 1]?.row_count ?? '?'} rows`
              : 'Done',
          })) || [],
        }
      }))
    } catch { setMessages([]) }
  }, [])

  // New chat
  const handleNewChat = useCallback(async () => {
    try {
      const session = await createSession()
      setSessions(prev => [session, ...prev])
      setActiveSessionId(session.id)
      setMessages([])
      setToolEvents([])
    } catch (e) { setSessionError('Failed to create session. Check that the API is running.') }
  }, [])

  // Delete session
  const handleDelete = useCallback(async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation()
    await deleteSession(sessionId)
    setSessions(prev => prev.filter(s => s.id !== sessionId))
    if (activeSessionId === sessionId) {
      setActiveSessionId(null)
      setMessages([])
      setToolEvents([])
    }
  }, [activeSessionId])

  // Send message
  const handleSend = useCallback(async (textOverride?: string, sessionOverride?: string) => {
    const sessionId = sessionOverride ?? activeSessionId
    const userText = (textOverride ?? input).trim()
    if (!userText || loading || !sessionId) return
    if (!textOverride) {
      setInput('')
      // Reset textarea height to 1 row after sending
      if (inputRef.current) {
        inputRef.current.style.height = 'auto'
      }
    }
    setLoading(true)

    // Clear tool panel on each new turn so it only shows current turn's results
    setToolEvents([])
    const userMsg: UiMessage = { id: Date.now().toString(), role: 'user', content: userText, chartData: [] }
    setMessages(prev => [...prev, userMsg])

    const assistantId = (Date.now() + 1).toString()
    setMessages(prev => [...prev, { id: assistantId, role: 'assistant', content: '', toolSteps: [], thinking: '', chartData: [] }])

    try {
      for await (const event of streamChat(sessionId, userText)) {
        const ev = event as AgentEvent
        if (ev.type === 'thinking' && ev.text) {
          setMessages(prev => { const next=[...prev]; const last=next[next.length-1]; next[next.length-1]={...last,thinking:(last.thinking??'')+ev.text}; return next })
        } else if (ev.type === 'tool_call') {
          const stepId = `step-${ev.tool_name}-${Date.now()}`
          setMessages(prev => { const next=[...prev]; const last=next[next.length-1]; next[next.length-1]={...last,toolSteps:[...(last.toolSteps??[]),{id:stepId,toolName:ev.tool_name!,status:'calling'}]}; return next })
          setToolEvents(prev => [...prev, {id:stepId,type:'calling',toolName:ev.tool_name!,timestamp:new Date().toISOString()}])
        } else if (ev.type === 'tool_result') {
          const preview = extractPreview(ev.tool_name!, ev.data)
          setMessages(prev => {
            const next = [...prev]
            const last = next[next.length - 1]
            const steps = (last.toolSteps ?? []).map(s =>
              s.toolName === ev.tool_name && s.status === 'calling'
                ? { ...s, status: 'done' as const, resultPreview: preview }
                : s
            )
            // Accumulate chart data — append each APIM result to the array
            const chartData =
              ev.tool_name === 'query_apim_analytics' && ev.data
                ? [...(last.chartData ?? []), ev.data as ApimChartData]
                : last.chartData ?? []
            next[next.length - 1] = { ...last, toolSteps: steps, chartData }
            return next
          })
          setToolEvents(prev => {
            const u = [...prev]
            const idx = [...u].reverse().findIndex(t => t.type === 'calling' && t.toolName === ev.tool_name)
            if (idx !== -1) u[u.length - 1 - idx] = { ...u[u.length - 1 - idx], type: 'result', data: ev.data }
            return u
          })
        } else if (ev.type === 'text' && ev.text) {
          setMessages(prev => { const next=[...prev]; const last=next[next.length-1]; const collapsed=last.thinking?true:last.thinkingCollapsed; next[next.length-1]={...last,content:last.content+ev.text,thinkingCollapsed:collapsed}; return next })
        }
      }
    } catch (err) {
      setMessages(prev => { const next=[...prev]; next[next.length-1]={...next[next.length-1],content:`> ⚠️ **Error:** ${(err as Error).message}`}; return next })
    } finally {
      setLoading(false)
      await refreshSessions()
    }
  }, [input, loading, activeSessionId, refreshSessions])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <>
      <style>{`
        @keyframes fadeSlideIn { from { opacity:0; transform:translateY(6px) } to { opacity:1; transform:translateY(0) } }
        @keyframes spin { to { transform:rotate(360deg) } }
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
        @keyframes thinkPulse { 0%,100%{opacity:0.4} 50%{opacity:1} }
        @keyframes shimmerSlide { 0%{transform:translateX(-200%)} 100%{transform:translateX(400%)} }
        @keyframes micPulse { 0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,0.4)} 50%{box-shadow:0 0 0 8px rgba(239,68,68,0)} }
        @keyframes thinkScan {
          0%   { transform: translateX(-100%); opacity: 0; }
          20%  { opacity: 0.7; }
          80%  { opacity: 0.7; }
          100% { transform: translateX(300%); opacity: 0; }
        }
        /* ── Markdown body ── */
        /* ── Markdown body — Corvin Command Center ── */
        .corvin-md { line-height: 1.75; font-size: 0.875rem; color: var(--c-text-dim); }
        .corvin-md p { margin: 0 0 10px; }
        .corvin-md p:last-child { margin-bottom: 0; }
        /* Lists */
        .corvin-md ul { margin: 4px 0 10px; padding-left: 0; list-style: none; }
        .corvin-md ol { margin: 4px 0 10px; padding-left: 20px; }
        .corvin-md ul > li { position: relative; padding-left: 14px; margin: 5px 0; }
        .corvin-md ul > li::before { content:''; position:absolute; left:1px; top:0.58em; width:5px; height:5px; border-radius:50%; background: var(--c-signal-dim); }
        .corvin-md ol > li { margin: 5px 0; }
        .corvin-md li > ul { margin: 4px 0 0; }
        .corvin-md li > ul > li::before { background: color-mix(in srgb, var(--c-signal) 30%, transparent); width:4px; height:4px; top:0.62em; }
        /* Inline */
        .corvin-md strong { color: var(--c-text); font-weight: 600; }
        .corvin-md em { color: var(--c-text-muted); font-style: italic; }
        .corvin-md a { color: var(--c-signal); text-decoration: underline; text-underline-offset: 2px; }
        /* Headings — clear visual hierarchy */
        .corvin-md h1 { font-size: 1rem; font-weight: 700; margin: 16px 0 6px; color: var(--c-text); letter-spacing: -0.01em; }
        .corvin-md h2 { font-size: 0.875rem; font-weight: 700; margin: 14px 0 5px; color: var(--c-text); border-bottom: 1px solid var(--c-signal-dim); padding-bottom: 4px; }
        .corvin-md h3 { font-size: 0.8rem; font-weight: 600; margin: 10px 0 4px; color: var(--c-text-muted); text-transform: uppercase; letter-spacing: 0.04em; }
        /* Horizontal rule */
        .corvin-md hr { border: none; border-top: 1px solid var(--c-border); margin: 12px 0; }
        .corvin-cmd-session:hover .corvin-del { opacity:1 !important; }
      `}</style>
      <NavBar />

      <div style={{ display: 'flex', height: 'calc(100vh - 56px)', overflow: 'hidden', background: 'var(--c-bg)' }}>

        {/* ── LEFT SIDEBAR: session list ──────────────────────────────────── */}
        <aside style={{
          width: 260, flexShrink: 0, display: 'flex', flexDirection: 'column',
          background: 'var(--c-surface)', borderRight: '1px solid var(--c-border)',
          overflowY: 'auto',
        }}>
          {/* Header */}
          <div style={{ padding: '16px 14px 10px', borderBottom: '1px solid var(--c-border)', flexShrink: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <div style={{ width: 28, height: 28, borderRadius: 8, background: 'var(--c-signal-glow)', border: '1px solid var(--c-border-glow)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <CorvinIcon size={16} />
              </div>
              <div>
                <div style={{ fontWeight: 600, fontSize: '0.8125rem', color: 'var(--c-text)' }}>Corvin</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', color: 'var(--c-text-muted)' }}>Command Center</div>
              </div>
            </div>
            <button
              onClick={handleNewChat}
              style={{
                width: '100%', padding: '8px 0', borderRadius: 8,
                background: 'var(--c-signal)',
                border: 'none', color: 'white', cursor: 'pointer',
                fontSize: '0.8125rem', fontWeight: 500,
                transition: 'opacity 0.15s',
              }}
              onMouseEnter={e => (e.currentTarget.style.opacity = '0.85')}
              onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
            >
              + New Chat
            </button>
          </div>

          {/* Session list */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '8px 8px' }}>
            {loadingSessions && (
              <div style={{ color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)', fontSize: '0.68rem', padding: '12px 6px' }}>Loading…</div>
            )}
            {!loadingSessions && sessions.length === 0 && (
              <div style={{ color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)', fontSize: '0.68rem', padding: '12px 6px', textAlign: 'center' }}>
                No conversations yet.<br />Click "+ New Chat" to start.
              </div>
            )}
            {sessions.map(s => (
              <div
                key={s.id}
                className="corvin-cmd-session"
                onClick={() => selectSession(s.id)}
                style={{
                  padding: '9px 10px', borderRadius: 8, cursor: 'pointer', marginBottom: 2,
                  background: activeSessionId === s.id ? 'var(--c-signal-glow)' : 'transparent',
                  border: activeSessionId === s.id ? '1px solid var(--c-border-glow)' : '1px solid transparent',
                  transition: 'background 0.15s',
                  position: 'relative',
                }}
              >
                <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.72rem', color: activeSessionId === s.id ? 'var(--c-signal)' : 'var(--c-text-dim)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', paddingRight: 22 }}>
                  {s.title}
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text-faint)', marginTop: 2 }}>
                  {s.message_count} msg · {new Date(s.updated_at).toLocaleDateString()}
                </div>
                <button
                  className="corvin-del"
                  onClick={(e) => handleDelete(e, s.id)}
                  style={{ position: 'absolute', right: 6, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: 'var(--c-text-faint)', cursor: 'pointer', fontSize: '0.8rem', opacity: 0, transition: 'opacity 0.15s', padding: '2px 4px' }}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </aside>

        {/* ── MAIN AREA ────────────────────────────────────────────────────── */}
        {!activeSessionId ? (
          // Empty state
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 16 }}>
            <div style={{ width: 64, height: 64, borderRadius: 18, background: 'var(--c-signal-glow)', border: '1px solid var(--c-border-glow)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <CorvinIcon size={36} />
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontWeight: 700, fontSize: '1.25rem', color: 'var(--c-text)' }}>Corvin Command Center</div>
              <div style={{ fontSize: '0.8125rem', color: 'var(--c-text-muted)', marginTop: 6 }}>
                Your AI SRE copilot with live access to the entire platform.
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', justifyContent: 'center', maxWidth: 520 }}>
              {[
                "What's the MTTR this week?",
                'Show me recent incidents',
                'Which services are healthy?',
                'Tell me about the platform architecture',
                'Any predictive alerts?',
                "What's the ROI this month?",
                'Show me APIM error rate last 24h',
                'Which services have the highest blast radius?',
                'Show me recent post-mortems',
                'What changed in the last hour?',
              ].map(q => (
                <button
                  key={q}
                  onClick={async () => { const s = await createSession(); setSessions(p => [s, ...p]); setActiveSessionId(s.id); setMessages([]); setToolEvents([]); handleSend(q, s.id) }}
                  style={{ padding: '8px 14px', borderRadius: 8, background: 'var(--c-surface-2)', border: '1px solid var(--c-border-hi)', color: 'var(--c-text-dim)', cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: '0.72rem', transition: 'border-color 0.15s' }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--c-border-glow)'; e.currentTarget.style.color = 'var(--c-signal)' }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--c-border-hi)'; e.currentTarget.style.color = 'var(--c-text-dim)' }}
                >
                  {q}
                </button>
              ))}
            </div>
            <button onClick={handleNewChat} style={{ marginTop: 8, padding: '10px 28px', borderRadius: 10, background: 'var(--c-signal)', border: 'none', color: 'white', cursor: 'pointer', fontWeight: 500, fontSize: '0.8125rem' }}>
              Start a new conversation
            </button>
            {sessionError && (
              <div style={{ marginTop: 12, padding: '10px 16px', borderRadius: 8, background: 'var(--c-error-bg)', border: '1px solid var(--c-error-border)', color: 'var(--c-error)', fontSize: '0.8125rem', maxWidth: 480, textAlign: 'center' }}>
                {sessionError}
              </div>
            )}
          </div>
        ) : (
          <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

            {/* ── CHAT PANEL ─────────────────────────────────────────────── */}
            <div style={{ flex: showToolPanel ? '0 0 58%' : '1', display: 'flex', flexDirection: 'column', borderRight: showToolPanel ? '1px solid var(--c-border)' : 'none', overflow: 'hidden', transition: 'flex 0.2s' }}>
              {/* Toolbar */}
              <div style={{ padding: '7px 14px', borderBottom: '1px solid var(--c-border)', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', flexShrink: 0, background: 'var(--c-surface)', gap: 8 }}>
                <button
                  onClick={() => setShowToolPanel(p => !p)}
                  title={showToolPanel ? 'Hide live tool panel' : 'Show live tool panel'}
                  style={{
                    padding: '4px 10px', borderRadius: 6, cursor: 'pointer',
                    border: `1px solid ${showToolPanel ? 'var(--c-signal-dim)' : 'var(--c-border)'}`,
                    background: showToolPanel ? 'var(--c-signal-light)' : 'var(--c-surface-2)',
                    color: showToolPanel ? 'var(--c-signal)' : 'var(--c-text-faint)',
                    fontFamily: 'var(--font-mono)', fontSize: '0.7rem', letterSpacing: '0.04em',
                    transition: 'all 0.15s',
                  }}
                >
                  {showToolPanel ? '⚡ Tools ▸' : '⚡ Tools ◂'}
                </button>
              </div>
              {/* Chat messages */}
              <div style={{ flex: 1, overflowY: 'auto', padding: '20px 20px 8px', display: 'flex', flexDirection: 'column', gap: 14 }}>
                {messages.length === 0 && (
                  <div style={{ textAlign: 'center', color: 'var(--c-text-muted)', fontFamily: 'var(--font-mono)', fontSize: '0.75rem', marginTop: 60, lineHeight: 2 }}>
                    I have live access to your entire platform.<br />
                    <span style={{ color: 'var(--c-text-faint)', fontSize: '0.68rem' }}>
                      Incidents · AKS · Log Analytics · Elastic · Site Knowledge
                    </span><br />
                    Ask me anything.
                  </div>
                )}
                {messages.map((m, i) => {
                  const isStreaming = loading && i === messages.length - 1 && m.role === 'assistant'
                  // Show reasoning on the most-recent completed assistant message too (not just while streaming)
                  // Show reasoning on every assistant message that has thinking — same as VS Code / Claude.
                  // The block is collapsible so it doesn't clutter older turns.
                  const showThinking = m.thinking && m.role === 'assistant'
                  return (
                    <div key={m.id} style={{ display: 'flex', flexDirection: 'column', alignItems: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, maxWidth: m.role === 'user' ? '75%' : '88%' }}>
                        {m.role === 'assistant' && (
                          <div style={{ marginTop: 2, flexShrink: 0, width: 26, height: 26, borderRadius: 8, background: 'var(--c-signal-glow)', border: '1px solid var(--c-border-glow)', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
                            <CorvinIcon size={15} />
                          </div>
                        )}
                        <div style={{
                          padding: '10px 14px',
                          borderRadius: m.role === 'user' ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
                          background: m.role === 'user'
                            ? 'var(--c-signal-glow)'
                            : 'var(--c-surface-2)',
                          border: `1px solid ${m.role === 'user' ? 'var(--c-border-glow)' : 'var(--c-border)'}`,
                          color: m.role === 'user' ? 'var(--c-text)' : 'var(--c-text-dim)',
                          fontSize: '0.875rem', lineHeight: 1.7, minWidth: 0, overflow: 'hidden',
                          animation: 'fadeSlideIn 0.2s ease',
                        }}>
                          {m.role === 'user' ? m.content : (
                            <div>
                              {/* ── Section 1: Reasoning block ── */}
                              {showThinking && (
                                  <div style={{ marginBottom: 10, borderRadius: 8, overflow: 'hidden', border: '1px solid var(--c-purple-border)', background: 'var(--c-purple-bg)' }}>
                                  {/* Header row */}
                                  <button
                                    onClick={() => setMessages(prev => prev.map(msg => msg.id === m.id ? { ...msg, thinkingCollapsed: !msg.thinkingCollapsed } : msg))}
                                    style={{
                                      width: '100%', display: 'flex', alignItems: 'center', gap: 7,
                                      padding: '7px 10px', background: 'none', border: 'none',
                                      borderBottom: m.thinkingCollapsed ? 'none' : '1px solid color-mix(in srgb, var(--c-purple) 15%, transparent)',
                                      cursor: 'pointer',
                                    }}
                                  >
                                    {/* Animated brain icon */}
                                    <span style={{ fontSize: '0.78rem', lineHeight: 1, filter: isStreaming && !m.thinkingCollapsed ? 'drop-shadow(0 0 4px var(--c-purple))' : 'none', transition: 'filter 0.3s' }}>🧠</span>
                                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', fontWeight: 600, letterSpacing: '0.02em', textTransform: 'uppercase', color: 'var(--c-purple)', flex: 1, textAlign: 'left' }}>
                                      Reasoning
                                      {isStreaming && <span style={{ animation: 'thinkPulse 1.2s ease infinite', display: 'inline-block', marginLeft: 6 }}>·</span>}
                                    </span>
                                    {isStreaming && (
                                      <span style={{ width: 9, height: 9, borderRadius: '50%', border: '1.5px solid var(--c-purple)', borderTopColor: 'transparent', display: 'inline-block', animation: 'spin 0.8s linear infinite' }} />
                                    )}
                                    <span style={{ fontSize: '0.68rem', color: 'color-mix(in srgb, var(--c-purple) 50%, transparent)', marginLeft: 2 }}>{m.thinkingCollapsed ? '▶' : '▼'}</span>
                                  </button>
                                  {/* Content */}
                                  {!m.thinkingCollapsed && (
                                    <div style={{ position: 'relative', overflow: 'hidden' }}>
                                      {/* Scan line animation while streaming */}
                                      {isStreaming && (
                                        <div style={{ position: 'absolute', top: 0, left: 0, width: '25%', height: '100%', background: 'linear-gradient(90deg, transparent, color-mix(in srgb, var(--c-purple) 12%, transparent), transparent)', animation: 'thinkScan 2s ease-in-out infinite', pointerEvents: 'none' }} />
                                      )}
                                      <div style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', fontSize: '0.66rem', color: 'color-mix(in srgb, var(--c-purple) 75%, var(--c-text))', lineHeight: 1.7, maxHeight: 180, overflowY: 'auto', whiteSpace: 'pre-wrap' }}>
                                        {m.thinking}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              )}

                              {/* ── Section 2: Tool calls ── */}
                              {(m.toolSteps ?? []).length > 0 && (
                                <div style={{ marginBottom: m.content ? 12 : 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
                                  {(m.toolSteps ?? []).map(step => (
                                    <div key={step.id} style={{
                                      display: 'flex', alignItems: 'center', gap: 8,
                                      padding: '7px 10px', borderRadius: 7,
                                      background: step.status === 'calling'
                                        ? 'color-mix(in srgb, var(--c-signal) 7%, transparent)'
                                        : 'color-mix(in srgb, var(--c-info) 5%, transparent)',
                                      border: `1px solid ${step.status === 'calling' ? 'color-mix(in srgb, var(--c-signal) 22%, transparent)' : 'color-mix(in srgb, var(--c-info) 18%, transparent)'}`,
                                      transition: 'all 0.25s',
                                    }}>
                                      {/* Left: status icon */}
                                      <div style={{ flexShrink: 0, width: 20, height: 20, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        background: step.status === 'calling' ? 'var(--c-signal-light)' : 'var(--c-info-bg)',
                                      border: `1px solid ${step.status === 'calling' ? 'var(--c-signal-dim)' : 'var(--c-info-border)'}`,
                                      }}>
                                        {step.status === 'calling'
                                          ? <span style={{ width: 10, height: 10, borderRadius: '50%', border: '1.5px solid var(--c-signal)', borderTopColor: 'transparent', display: 'inline-block', animation: 'spin 0.7s linear infinite' }} />
                                          : <span style={{ fontSize: '0.72rem', color: 'var(--c-info)' }}>✓</span>
                                        }
                                      </div>
                                      {/* Badge */}
                                      <span style={{
                                        fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', fontWeight: 600,
                                        letterSpacing: '0.02em', textTransform: 'uppercase', flexShrink: 0,
                                        padding: '2px 5px', borderRadius: 4,
                                        background: step.status === 'calling' ? 'var(--c-signal-light)' : 'var(--c-info-bg)',
                                        color: step.status === 'calling' ? 'var(--c-signal)' : 'var(--c-info)',
                                      }}>
                                        {step.status === 'calling' ? 'calling' : 'done'}
                                      </span>
                                      {/* Tool name */}
                                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.69rem', color: step.status === 'calling' ? 'var(--c-text)' : 'var(--c-text-dim)', fontWeight: 600, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                        {TOOL_ICONS[step.toolName] ?? '🛠'} {TOOL_LABELS[step.toolName] ?? step.toolName}
                                      </span>
                                      {/* Result preview — right-aligned */}
                                      {step.resultPreview && (
                                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-text-faint)', flexShrink: 0, opacity: 0.7 }}>
                                          {step.resultPreview}
                                        </span>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              )}

                              {/* ── Section 3: Final answer ── */}
                              {/* ── Inline chart — show immediately when data arrives ── */}
                              {m.chartData.length > 0 && (
                                <div style={{ marginTop: 4, marginBottom: 8, display: 'flex', flexDirection: 'column', gap: 10 }}>
                                  {m.chartData.map((cd, ci) => (
                                    <ApimChart key={`chart-${m.id}-${ci}`} data={cd} compact={false} />
                                  ))}
                                </div>
                              )}
                              {(m.content || (isStreaming && !(m.toolSteps?.some(s => s.status === 'calling')))) && (
                                <>
                                  {(m.toolSteps ?? []).length > 0 && m.content && (
                                    <div style={{ borderTop: '1px solid var(--c-border)', margin: '8px 0' }} />
                                  )}
                                  <div className="corvin-md">
                                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents as any}>
                                      {m.content || (isStreaming ? '▌' : '')}
                                    </ReactMarkdown>
                                    {isStreaming && m.content && (
                                      <span style={{ display: 'inline-block', width: 2, height: '1em', background: 'var(--c-signal)', marginLeft: 1, animation: 'blink 0.7s steps(1) infinite' }} />
                                    )}
                                  </div>
                                </>
                              )}

                              {/* ── Waiting state: no content yet, tool still calling ── */}
                              {isStreaming && !m.content && !(m.toolSteps ?? []).length && !m.thinking && (
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)', fontSize: '0.7rem' }}>
                                  <span style={{ width: 12, height: 12, borderRadius: '50%', border: '1.5px solid var(--c-signal)', borderTopColor: 'transparent', display: 'inline-block', animation: 'spin 0.7s linear infinite' }} />
                                  Corvin is thinking…
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                      {/* ── TTS speaker button on assistant messages ── */}
                      {m.role === 'assistant' && m.content && !isStreaming && ttsSupported && (
                        <button
                          onClick={() => handleSpeak(m.id, m.content)}
                          title={speakingMsgId === m.id ? 'Stop speaking' : 'Read aloud'}
                          style={{
                            alignSelf: 'flex-start', marginTop: 4, marginLeft: 34,
                            background: speakingMsgId === m.id ? 'var(--c-signal-light)' : 'transparent',
                            border: `1px solid ${speakingMsgId === m.id ? 'var(--c-signal-dim)' : 'transparent'}`,
                            borderRadius: 6, padding: '3px 8px', cursor: 'pointer',
                            color: speakingMsgId === m.id ? 'var(--c-signal)' : 'var(--c-text-faint)',
                            fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
                            transition: 'all 0.15s', display: 'flex', alignItems: 'center', gap: 5,
                          }}
                          onMouseEnter={e => { if (speakingMsgId !== m.id) { e.currentTarget.style.color = 'var(--c-text-dim)'; e.currentTarget.style.background = 'var(--c-surface-3)' } }}
                          onMouseLeave={e => { if (speakingMsgId !== m.id) { e.currentTarget.style.color = 'var(--c-text-faint)'; e.currentTarget.style.background = 'transparent' } }}
                        >
                          {speakingMsgId === m.id ? '◼ Stop' : '🔊 Listen'}
                        </button>
                      )}
                    </div>
                  )
                })}
                <div ref={endRef} />
              </div>


              {/* Input bar */}
              <div style={{ padding: '12px 16px', borderTop: '1px solid var(--c-border)', background: 'var(--c-surface)', flexShrink: 0 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', background: 'var(--c-surface-2)', border: '1px solid var(--c-border-hi)', borderRadius: 12, padding: '8px 12px', transition: 'border-color 0.15s' }}
                  onFocus={e => (e.currentTarget.style.borderColor = 'var(--c-border-glow)')}
                  onBlur={e => (e.currentTarget.style.borderColor = 'var(--c-border-hi)')}>
                  <textarea
                    ref={inputRef}
                    value={input}
                    onChange={e => {
                      setInput(e.target.value)
                      // Auto-grow: reset then expand to scrollHeight
                      e.target.style.height = 'auto'
                      e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
                    }}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask Corvin anything about your platform…"
                    rows={1}
                    disabled={loading}
                    className="corvin-interactive"
                    style={{
                      flex: 1, background: 'none', border: 'none', resize: 'none',
                      color: 'var(--c-text)', fontFamily: 'var(--font-body)', fontSize: '0.82rem',
                      lineHeight: 1.5, maxHeight: 120, overflowY: 'hidden', height: 'auto',
                    }}
                  />
                  {/* Mic button */}
                  {sttSupported && (
                    <button
                      onClick={listening ? stopMic : startMic}
                      disabled={loading}
                      title={listening ? 'Stop recording' : 'Voice input'}
                      style={{
                        width: 34, height: 34, borderRadius: 8, flexShrink: 0,
                        background: listening ? 'rgba(239,68,68,0.15)' : 'var(--c-surface-3)',
                        border: listening ? '1px solid rgba(239,68,68,0.4)' : '1px solid transparent',
                        cursor: loading ? 'not-allowed' : 'pointer',
                        color: listening ? '#ef4444' : 'var(--c-text-faint)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: '0.95rem', transition: 'all 0.15s',
                        animation: listening ? 'micPulse 1.5s ease infinite' : 'none',
                      }}
                    >
                      🎤
                    </button>
                  )}
                  {/* Send button */}
                  <button
                    onClick={() => handleSend()}
                    disabled={loading || !input.trim()}
                    style={{
                      width: 34, height: 34, borderRadius: 8, flexShrink: 0,
                      background: loading || !input.trim() ? 'var(--c-surface-3)' : 'var(--c-signal)',
                      border: 'none', cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
                      color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: '1rem', transition: 'background 0.15s',
                    }}
                  >
                    {loading ? '⟳' : '↑'}
                  </button>
                </div>
                {/* Interim transcript preview */}
                {listening && interim && (
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-text-muted)', padding: '4px 12px', fontStyle: 'italic' }}>
                    {interim}…
                  </div>
                )}
                {listening && (
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: '#ef4444', marginTop: 4, textAlign: 'center', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#ef4444', display: 'inline-block', animation: 'blink 0.8s steps(1) infinite' }} />
                    Listening… speak now
                  </div>
                )}
                {!listening && (
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-faint)', marginTop: 5, textAlign: 'center' }}>
                    Shift+Enter for new line · Enter to send{sttSupported ? ' · 🎤 Voice input' : ''}
                  </div>
                )}
              </div>
            </div>

            {/* ── CONTEXT PANEL (right 42%) ──────────────────────────────── */}
            {showToolPanel && <div style={{ flex: '0 0 42%', display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--c-bg)' }}>
              <div style={{ padding: '12px 16px 8px', borderBottom: '1px solid var(--c-border)', background: 'var(--c-surface)', flexShrink: 0 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-signal)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
                  ⚡ Live Tool Results
                </div>
                <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.7rem', color: 'var(--c-text-faint)', marginTop: 2 }}>
                  Tool calls and live data appear here as Corvin works
                </div>
              </div>
              <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px' }}>
                {toolEvents.length === 0 && (
                  <div style={{ textAlign: 'center', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)', fontSize: '0.68rem', lineHeight: 2 }}>
                    Tool results will appear here<br />as Corvin queries live data.
                  </div>
                )}
                {toolEvents.map(ev =>
                  ev.type === 'calling'
                    ? <ToolCallingSkeleton key={`${ev.id}-calling`} toolName={ev.toolName} />
                    : <ToolResultCard key={`${ev.id}-result`} toolName={ev.toolName} data={ev.data} timestamp={ev.timestamp} />
                )}
              </div>
            </div>}

          </div>
        )}
      </div>
    </>
  )
}
