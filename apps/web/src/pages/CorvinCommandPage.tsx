import { useState, useRef, useEffect, useCallback } from 'react'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import NavBar from '../components/NavBar'

import { ToolResultCard, ToolCallingSkeleton } from '../components/corvin/ToolResultCard'
import {
  createSession, listSessions, getSession, deleteSession, streamChat,
  type CorvinSession, type AgentEvent,
} from '../api/corvinApi'


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
  get_site_knowledge: 'CHAD Architecture', get_runbook: 'Runbook',
  run_kql: 'Log Analytics Query', get_aks_health: 'AKS Health',
  run_elastic_query: 'Elastic Logs',
}

const TOOL_ICONS: Record<string, string> = {
  get_platform_stats: '📊', list_recent_incidents: '📋', get_investigation_detail: '🔍',
  get_predictive_alerts: '⚠️', get_service_score: '🎯', get_roi: '💰',
  get_service_topology: '🗺️', get_blast_radius: '💥', get_postmortem: '📄',
  get_similar_incidents: '🔁', get_site_knowledge: '🏗️', get_runbook: '📖',
  run_kql: '🔬', get_aks_health: '☸️', run_elastic_query: '📡',
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
    case 'run_kql': return Array.isArray(d) ? `${d.length} rows` : 'Query complete'
    case 'get_site_knowledge': return `${Math.round((typeof d === 'string' ? d.length : 0) / 100) / 10}k chars`
    case 'get_runbook': return 'Runbook loaded'
    default: return 'Done'
  }
}

// ── Markdown components (reuse widget pattern) ─────────────────────────────────

const mdComponents: Record<string, React.ComponentType<any>> = {
  pre: ({ children }) => (
    <div style={{ overflowX: 'auto', margin: '8px 0' }}>
      <pre style={{ margin: 0, background: 'rgba(0,0,0,0.3)', padding: '10px 14px', borderRadius: 8, fontSize: '0.75rem', fontFamily: 'var(--font-mono)' }}>
        {children}
      </pre>
    </div>
  ),
  code: ({ className, children }) => {
    if (className?.startsWith('language-')) {
      return <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem' }}>{children}</code>
    }
    return <code style={{ background: 'rgba(249,115,22,0.15)', color: '#f97316', borderRadius: 4, padding: '1px 5px', fontFamily: 'var(--font-mono)', fontSize: '0.8em' }}>{children}</code>
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
          <stop stopColor="#f97316"/><stop offset="1" stopColor="#ea580c"/>
        </linearGradient>
      </defs>
      <path d="M16 2 L28 9 L28 23 L16 30 L4 23 L4 9 Z" fill="url(#ci)" opacity="0.15" stroke="url(#ci)" strokeWidth="1.5"/>
      <rect x="9" y="13" width="5" height="2.5" rx="1.25" fill="#f97316"/>
      <rect x="18" y="13" width="5" height="2.5" rx="1.25" fill="#f97316"/>
      <rect x="11" y="18.5" width="10" height="1.5" rx="0.75" fill="#f97316" opacity="0.7"/>
      <line x1="16" y1="2" x2="16" y2="6" stroke="#f97316" strokeWidth="1.5" strokeLinecap="round"/>
      <circle cx="16" cy="5" r="1.5" fill="#f97316"/>
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
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const prevMessagesLengthRef = useRef(0)
  const prevLastMessageContentRef = useRef('')

  // Auto-scroll chat
  useEffect(() => {
    const lastMsg = messages[messages.length - 1]
    const contentChanged = lastMsg?.role === 'assistant' && lastMsg.content.length > prevLastMessageContentRef.current
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
      setMessages(detail.messages.map(m => ({
        id: String(m.id),
        role: m.role,
        content: m.content,
        thinking: m.thinking || undefined,
        thinkingCollapsed: true, // historical messages start collapsed
        toolSteps: m.tool_calls?.calls.map((c, i) => ({
          id: `hist-${m.id}-${i}`,
          toolName: c.tool_name,
          status: 'done' as const,
          resultPreview: 'Done',
        })) || [],
      })))
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
    } catch (e) { console.error(e) }
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
  const handleSend = useCallback(async () => {
    if (!input.trim() || loading || !activeSessionId) return
    const userText = input.trim()
    setInput('')
    setLoading(true)

    const userMsg: UiMessage = { id: Date.now().toString(), role: 'user', content: userText }
    setMessages(prev => [...prev, userMsg])

    const assistantId = (Date.now() + 1).toString()
    setMessages(prev => [...prev, { id: assistantId, role: 'assistant', content: '', toolSteps: [], thinking: '' }])

    try {
      for await (const event of streamChat(activeSessionId, userText)) {
        const ev = event as AgentEvent
        if (ev.type === 'thinking' && ev.text) {
          setMessages(prev => { const next=[...prev]; const last=next[next.length-1]; next[next.length-1]={...last,thinking:(last.thinking??'')+ev.text}; return next })
        } else if (ev.type === 'tool_call') {
          const stepId = `step-${ev.tool_name}-${Date.now()}`
          setMessages(prev => { const next=[...prev]; const last=next[next.length-1]; next[next.length-1]={...last,toolSteps:[...(last.toolSteps??[]),{id:stepId,toolName:ev.tool_name!,status:'calling'}]}; return next })
          setToolEvents(prev => [...prev, {id:stepId,type:'calling',toolName:ev.tool_name!,timestamp:new Date().toISOString()}])
        } else if (ev.type === 'tool_result') {
          const preview = extractPreview(ev.tool_name!, ev.data)
          setMessages(prev => { const next=[...prev]; const last=next[next.length-1]; const steps=(last.toolSteps??[]).map(s=>s.toolName===ev.tool_name&&s.status==='calling'?{...s,status:'done' as const,resultPreview:preview}:s); next[next.length-1]={...last,toolSteps:steps}; return next })
          setToolEvents(prev => { const u=[...prev]; const idx=[...u].reverse().findIndex(t=>t.type==='calling'&&t.toolName===ev.tool_name); if(idx!==-1)u[u.length-1-idx]={...u[u.length-1-idx],type:'result',data:ev.data}; return u })
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
        @keyframes thinkPulse { 0%,100%{opacity:0.5} 50%{opacity:1} }
        .corvin-md p { margin: 6px 0; }
        .corvin-md ul, .corvin-md ol { margin: 6px 0; padding-left: 20px; }
        .corvin-md li { margin: 3px 0; }
        .corvin-md h2 { font-size:0.85rem; font-weight:700; margin:12px 0 4px; color:var(--c-text); }
        .corvin-md h3 { font-size:0.78rem; font-weight:700; margin:10px 0 3px; color:var(--c-text); }
        .corvin-cmd-session:hover .corvin-del { opacity:1 !important; }
        .corvin-tool-row:hover { background: rgba(249,115,22,0.06) !important; }
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
              <div style={{ width: 28, height: 28, borderRadius: 8, background: 'rgba(249,115,22,0.15)', border: '1px solid rgba(249,115,22,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <CorvinIcon size={16} />
              </div>
              <div>
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.78rem', color: 'var(--c-text)' }}>CORVIN</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.58rem', color: 'var(--c-signal)', letterSpacing: '0.08em' }}>COMMAND CENTER</div>
              </div>
            </div>
            <button
              onClick={handleNewChat}
              style={{
                width: '100%', padding: '8px 0', borderRadius: 8,
                background: 'linear-gradient(135deg, #ea580c, #f97316)',
                border: 'none', color: '#fff', cursor: 'pointer',
                fontFamily: 'var(--font-mono)', fontSize: '0.72rem', fontWeight: 700,
                letterSpacing: '0.05em', transition: 'opacity 0.15s',
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
                  background: activeSessionId === s.id ? 'rgba(249,115,22,0.12)' : 'transparent',
                  border: activeSessionId === s.id ? '1px solid rgba(249,115,22,0.3)' : '1px solid transparent',
                  transition: 'background 0.15s',
                  position: 'relative',
                }}
              >
                <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.72rem', color: activeSessionId === s.id ? 'var(--c-signal)' : 'var(--c-text-dim)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', paddingRight: 22 }}>
                  {s.title}
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--c-text-faint)', marginTop: 2 }}>
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
            <div style={{ width: 64, height: 64, borderRadius: 18, background: 'rgba(249,115,22,0.12)', border: '2px solid rgba(249,115,22,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <CorvinIcon size={36} />
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '1.4rem', color: 'var(--c-text)' }}>Corvin Command Center</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--c-text-muted)', marginTop: 6 }}>
                Your AI SRE copilot with live access to the entire platform.
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', justifyContent: 'center', maxWidth: 520 }}>
              {[
                'What\'s the MTTR this week?',
                'Show me recent incidents',
                'Is fundsso healthy?',
                'Tell me about CHAD architecture',
                'Any predictive alerts?',
                'What\'s the ROI this month?',
              ].map(q => (
                <button
                  key={q}
                  onClick={async () => { const s = await createSession(); setSessions(p => [s, ...p]); setActiveSessionId(s.id); setMessages([]); setToolEvents([]); setInput(q) }}
                  style={{ padding: '8px 14px', borderRadius: 8, background: 'var(--c-surface-2)', border: '1px solid var(--c-border-hi)', color: 'var(--c-text-dim)', cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: '0.72rem', transition: 'border-color 0.15s' }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(249,115,22,0.5)'; e.currentTarget.style.color = 'var(--c-signal)' }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--c-border-hi)'; e.currentTarget.style.color = 'var(--c-text-dim)' }}
                >
                  {q}
                </button>
              ))}
            </div>
            <button onClick={handleNewChat} style={{ marginTop: 8, padding: '10px 28px', borderRadius: 10, background: 'linear-gradient(135deg, #ea580c, #f97316)', border: 'none', color: '#fff', cursor: 'pointer', fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.8rem', letterSpacing: '0.05em' }}>
              Start a new conversation
            </button>
          </div>
        ) : (
          <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

            {/* ── CHAT PANEL (left 58%) ─────────────────────────────────── */}
            <div style={{ flex: '0 0 58%', display: 'flex', flexDirection: 'column', borderRight: '1px solid var(--c-border)', overflow: 'hidden' }}>
              {/* Chat messages */}
              <div style={{ flex: 1, overflowY: 'auto', padding: '20px 20px 8px', display: 'flex', flexDirection: 'column', gap: 14 }}>
                {messages.length === 0 && (
                  <div style={{ textAlign: 'center', color: 'var(--c-text-muted)', fontFamily: 'var(--font-mono)', fontSize: '0.75rem', marginTop: 60, lineHeight: 2 }}>
                    I have live access to your entire platform.<br />
                    <span style={{ color: 'var(--c-text-faint)', fontSize: '0.68rem' }}>
                      Incidents · AKS · Log Analytics · Elastic · CHAD Knowledge
                    </span><br />
                    Ask me anything.
                  </div>
                )}
                {messages.map((m, i) => {
                  const isStreaming = loading && i === messages.length - 1 && m.role === 'assistant'
                  return (
                    <div key={m.id} style={{ display: 'flex', flexDirection: 'column', alignItems: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, maxWidth: '90%' }}>
                        {m.role === 'assistant' && (
                          <div style={{ marginTop: 2, flexShrink: 0, width: 26, height: 26, borderRadius: 8, background: 'rgba(249,115,22,0.12)', border: '1px solid rgba(249,115,22,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <CorvinIcon size={15} />
                          </div>
                        )}
                        <div style={{
                          padding: '10px 14px',
                          borderRadius: m.role === 'user' ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
                          background: m.role === 'user'
                            ? 'linear-gradient(135deg, rgba(249,115,22,0.18), rgba(249,115,22,0.08))'
                            : 'var(--c-surface-2)',
                          border: `1px solid ${m.role === 'user' ? 'rgba(249,115,22,0.3)' : 'var(--c-border-hi)'}`,
                          color: m.role === 'user' ? 'var(--c-signal)' : 'var(--c-text-dim)',
                          fontFamily: m.role === 'user' ? 'var(--font-mono)' : 'var(--font-body)',
                          fontSize: '0.78rem', lineHeight: 1.6, minWidth: 0, overflow: 'hidden',
                          animation: 'fadeSlideIn 0.2s ease',
                        }}>
                          {m.role === 'user' ? m.content : (
                            <div>
                              {/* ── Section 1: Reasoning block ── */}
                              {m.thinking && (
                                <div style={{ marginBottom: 8 }}>
                                  <button
                                    onClick={() => setMessages(prev => prev.map(msg => msg.id === m.id ? { ...msg, thinkingCollapsed: !msg.thinkingCollapsed } : msg))}
                                    style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: 'pointer', padding: '3px 0', width: '100%' }}
                                  >
                                    <span style={{ fontSize: '0.65rem', color: 'var(--c-signal)', animation: isStreaming && !m.thinkingCollapsed ? 'thinkPulse 1.5s ease infinite' : 'none' }}>
                                      {m.thinkingCollapsed ? '▶' : '▼'}
                                    </span>
                                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--c-signal)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                                      💭 Reasoning {(m.toolSteps ?? []).length > 0 && `· ${(m.toolSteps ?? []).length} tools`} {isStreaming && !m.thinkingCollapsed && !m.content ? '·' : ''}
                                    </span>
                                    {isStreaming && !m.thinkingCollapsed && !m.content && (
                                      <span style={{ width: 10, height: 10, borderRadius: '50%', border: '1.5px solid #f97316', borderTopColor: 'transparent', display: 'inline-block', animation: 'spin 0.7s linear infinite', marginLeft: 2 }} />
                                    )}
                                  </button>
                                  {!m.thinkingCollapsed && (
                                    <div style={{ marginTop: 4, padding: '8px 10px', background: 'rgba(249,115,22,0.05)', borderLeft: '2px solid rgba(249,115,22,0.35)', borderRadius: '0 6px 6px 0', fontFamily: 'var(--font-mono)', fontSize: '0.67rem', color: 'var(--c-text-faint)', lineHeight: 1.6, maxHeight: 160, overflowY: 'auto', whiteSpace: 'pre-wrap' }}>
                                      {m.thinking}
                                    </div>
                                  )}
                                </div>
                              )}

                              {/* ── Section 2: Tool call timeline ── */}
                              {(m.toolSteps ?? []).length > 0 && (
                                <div style={{ marginBottom: m.content ? 10 : 0, display: 'flex', flexDirection: 'column', gap: 3 }}>
                                  {(m.toolSteps ?? []).map(step => (
                                    <div key={step.id} className="corvin-tool-row" style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '4px 6px', borderRadius: 6, background: 'rgba(0,0,0,0.15)', cursor: 'default', transition: 'background 0.15s' }}>
                                      {step.status === 'calling' ? (
                                        <span style={{ width: 12, height: 12, flexShrink: 0, borderRadius: '50%', border: '1.5px solid #f97316', borderTopColor: 'transparent', display: 'inline-block', animation: 'spin 0.7s linear infinite' }} />
                                      ) : (
                                        <span style={{ fontSize: '0.7rem', flexShrink: 0, color: '#22c55e' }}>✓</span>
                                      )}
                                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: step.status === 'calling' ? 'var(--c-signal)' : 'var(--c-text-dim)' }}>
                                        {TOOL_ICONS[step.toolName] ?? '🛠'} {step.status === 'calling' ? 'Calling' : ''} <strong>{TOOL_LABELS[step.toolName] ?? step.toolName}</strong>
                                      </span>
                                      {step.resultPreview && (
                                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--c-text-faint)', marginLeft: 'auto' }}>
                                          {step.resultPreview}
                                        </span>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              )}

                              {/* ── Section 3: Final answer ── */}
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
                                  <span style={{ width: 12, height: 12, borderRadius: '50%', border: '1.5px solid #f97316', borderTopColor: 'transparent', display: 'inline-block', animation: 'spin 0.7s linear infinite' }} />
                                  Corvin is thinking…
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                })}
                <div ref={endRef} />
              </div>


              {/* Input bar */}
              <div style={{ padding: '12px 16px', borderTop: '1px solid var(--c-border)', background: 'var(--c-surface)', flexShrink: 0 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', background: 'var(--c-surface-2)', border: '1px solid var(--c-border-hi)', borderRadius: 12, padding: '8px 12px', transition: 'border-color 0.15s' }}
                  onFocus={e => (e.currentTarget.style.borderColor = 'rgba(249,115,22,0.5)')}
                  onBlur={e => (e.currentTarget.style.borderColor = 'var(--c-border-hi)')}>
                  <textarea
                    ref={inputRef}
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask Corvin anything about your platform…"
                    rows={1}
                    disabled={loading}
                    style={{
                      flex: 1, background: 'none', border: 'none', outline: 'none', resize: 'none',
                      color: 'var(--c-text)', fontFamily: 'var(--font-body)', fontSize: '0.82rem',
                      lineHeight: 1.5, maxHeight: 120, overflowY: 'auto',
                    }}
                  />
                  <button
                    onClick={handleSend}
                    disabled={loading || !input.trim()}
                    style={{
                      width: 34, height: 34, borderRadius: 8, flexShrink: 0,
                      background: loading || !input.trim() ? 'rgba(249,115,22,0.2)' : 'linear-gradient(135deg, #ea580c, #f97316)',
                      border: 'none', cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
                      color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: '1rem', transition: 'background 0.15s',
                    }}
                  >
                    {loading ? '⟳' : '↑'}
                  </button>
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--c-text-faint)', marginTop: 5, textAlign: 'center' }}>
                  Shift+Enter for new line · Enter to send
                </div>
              </div>
            </div>

            {/* ── CONTEXT PANEL (right 42%) ──────────────────────────────── */}
            <div style={{ flex: '0 0 42%', display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--c-bg)' }}>
              <div style={{ padding: '12px 16px 8px', borderBottom: '1px solid var(--c-border)', background: 'var(--c-surface)', flexShrink: 0 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-signal)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
                  ⚡ Live Tool Results
                </div>
                <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.62rem', color: 'var(--c-text-faint)', marginTop: 2 }}>
                  Tool calls and live data appear here as Corvin works
                </div>
              </div>
              <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px' }}>
                {toolEvents.length === 0 && (
                  <div style={{ textAlign: 'center', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)', fontSize: '0.68rem', marginTop: 40, lineHeight: 2 }}>
                    Tool results will appear here<br />as Corvin queries live data.
                  </div>
                )}
                {toolEvents.map(ev =>
                  ev.type === 'calling'
                    ? <ToolCallingSkeleton key={ev.id} toolName={ev.toolName} />
                    : <ToolResultCard key={ev.id} toolName={ev.toolName} data={ev.data} timestamp={ev.timestamp} />
                )}
              </div>
            </div>

          </div>
        )}
      </div>
    </>
  )
}
