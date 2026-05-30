import { useEffect, useState, useRef } from 'react'
import { createPortal } from 'react-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { API_BASE } from '../../api/baseUrl'

interface WarRoomProps {
  requestId: string
  onClose: () => void
}

// ── Shared markdown renderer config ─────────────────────────────────────────
const mdComponents: Record<string, React.ComponentType<any>> = {
  strong: ({ children }) => <strong style={{ color: 'var(--c-text)', fontWeight: 700 }}>{children}</strong>,
  em: ({ children }) => <em style={{ color: 'var(--c-text-dim)' }}>{children}</em>,
  code: ({ children }) => (
    <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85em', background: 'rgba(168,85,247,0.12)', padding: '1px 5px', borderRadius: 4, color: 'var(--c-purple)' }}>
      {children}
    </code>
  ),
  p: ({ children }) => <p style={{ margin: '0 0 8px', lineHeight: 1.65 }}>{children}</p>,
  ul: ({ children }) => <ul style={{ margin: '0 0 8px', paddingLeft: 18 }}>{children}</ul>,
  ol: ({ children }) => <ol style={{ margin: '0 0 8px', paddingLeft: 18 }}>{children}</ol>,
  li: ({ children }) => <li style={{ marginBottom: 3, lineHeight: 1.6 }}>{children}</li>,
}

// ── Portal modal ─────────────────────────────────────────────────────────────
function Modal({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
      style={{
        position: 'fixed', inset: 0, zIndex: 10000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        backgroundColor: 'rgba(5, 8, 18, 0.78)',
        backdropFilter: 'blur(7px)',
        padding: 32,
      }}
    >
      <div style={{
        width: '100%', maxWidth: 1160,
        maxHeight: 'calc(100vh - 64px)',
        background: 'var(--c-surface)',
        border: '1px solid var(--c-purple)',
        borderRadius: 16,
        boxShadow: '0 28px 90px rgba(0,0,0,0.65), 0 0 0 1px rgba(168,85,247,0.18)',
        display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {children}
      </div>
    </div>,
    document.body
  )
}

// ── Blinking cursor ──────────────────────────────────────────────────────────
const Cursor = () => (
  <span style={{
    display: 'inline-block', width: 2, height: '1em',
    background: 'currentColor', marginLeft: 2, verticalAlign: 'text-bottom',
    animation: 'corvin-blink 0.7s steps(1) infinite',
  }} />
)

// ── Judge Raw Token View (streamed JSON, shown as monospace raw) ─────────────
// The Judge streams raw JSON tokens. We show them as monospace text while
// streaming, then switch to formatted ReactMarkdown once complete.
function JudgeStreamView({ rawText, isComplete, judgeRca }: {
  rawText: string
  isComplete: boolean
  judgeRca: any
}) {
  if (!rawText && !judgeRca) return null

  if (isComplete && judgeRca) {
    return (
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div>
          <div style={{ fontSize: '0.65rem', fontWeight: 700, color: 'var(--c-text-faint)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Root Cause</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--c-text)', lineHeight: 1.65, fontFamily: 'var(--font-body)' }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>{judgeRca.root_cause}</ReactMarkdown>
          </div>
        </div>
        <div>
          <div style={{ fontSize: '0.65rem', fontWeight: 700, color: 'var(--c-text-faint)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Summary</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--c-text)', lineHeight: 1.65, fontFamily: 'var(--font-body)' }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>{judgeRca.summary}</ReactMarkdown>
          </div>
        </div>
      </div>
    )
  }

  // While judge is streaming JSON in the background — show a clean deliberating state
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 0', color: 'var(--c-text-dim)', fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
      <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: 'var(--c-purple)', animation: 'corvin-blink 0.7s steps(1) infinite' }} />
      Judge is deliberating — synthesising agent hypotheses…
    </div>
  )
}

// ── Agent column content (shared between inline & modal) ─────────────────────
function AgentColumn({ label, color, text, isRunning, maxHeight }: {
  label: string; color: string; text: string; isRunning: boolean; maxHeight?: number | string
}) {
  const ref = useRef<HTMLDivElement>(null)
  // Only auto-scroll if the user hasn't manually scrolled up
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    if (isNearBottom) el.scrollTop = el.scrollHeight
  }, [text])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, height: '100%' }}>
      <div style={{
        padding: '7px 14px', fontSize: '0.68rem', fontWeight: 800, letterSpacing: '0.1em',
        textTransform: 'uppercase', color, flexShrink: 0,
        borderBottom: `1px solid color-mix(in srgb, ${color} 20%, transparent)`,
      }}>
        {label}
      </div>
      <div ref={ref} style={{
        flex: 1, overflowY: 'auto', padding: 14,
        fontSize: '0.78rem', lineHeight: 1.65, color: 'var(--c-text-dim)',
        fontFamily: 'var(--font-body)', minHeight: 0,
      }}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
          {text || (isRunning ? '' : '—')}
        </ReactMarkdown>
        {isRunning && <Cursor />}
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export function WarRoomTerminal({ requestId, onClose }: WarRoomProps) {
  const [alphaText, setAlphaText] = useState('')
  const [betaText, setBetaText] = useState('')
  const [judgeRawText, setJudgeRawText] = useState('')
  const [judgeRca, setJudgeRca] = useState<any>(null)
  const [status, setStatus] = useState<'running' | 'complete' | 'error'>('running')
  const [message, setMessage] = useState('Summoning agents Alpha and Beta...')
  const [isModalOpen, setIsModalOpen] = useState(false)

  useEffect(() => {
    const url = `${API_BASE}/investigations/${requestId}/debate/stream`
    const source = new EventSource(url)

    source.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.stage === 'debate') {
          if (data.status === 'started') {
            setMessage(data.message)
          } else if (data.status === 'token') {
            if (data.agent === 'alpha') setAlphaText(prev => prev + data.message)
            else if (data.agent === 'beta') setBetaText(prev => prev + data.message)
          } else if (data.status === 'judge_token') {
            // Real streaming tokens from the Judge LLM
            setJudgeRawText(prev => prev + data.message)
          } else if (data.status === 'complete') {
            setStatus('complete')
            setMessage(data.message)
            setJudgeRca({ root_cause: data.root_cause, summary: data.summary, confidence: data.confidence })
            source.close()
          }
        } else if (data.stage === 'error') {
          setStatus('error')
          setMessage(data.message)
          source.close()
        }
      } catch (err) {
        console.error('SSE parse error:', err)
      }
    }

    source.onerror = () => {
      setStatus('error')
      setMessage('Lost connection to Debate Orchestrator.')
      source.close()
    }

    return () => source.close()
  }, [requestId])

  const confidenceColor = judgeRca?.confidence === 'high'
    ? 'var(--c-green)' : judgeRca?.confidence === 'medium'
    ? 'var(--c-yellow)' : 'var(--c-red)'

  const isRunning = status === 'running'
  const judgeIsStreaming = !!(judgeRawText && !judgeRca)

  // ── Shared header ─────────────────────────────────────────────────────────
  const headerBar = (isModal: boolean) => (
    <div style={{
      padding: '10px 16px', background: 'var(--c-surface-2)',
      borderBottom: '1px solid var(--c-purple)',
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      flexShrink: 0,
    }}>
      <div style={{
        fontFamily: 'var(--font-display)', fontSize: '0.72rem', fontWeight: 800,
        letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--c-purple)',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        ⚔️ Agent Consensus Engine
        {isRunning && <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--c-purple)', display: 'inline-block', animation: 'corvin-blink 1s steps(1) infinite' }} />}
        {judgeIsStreaming && <span style={{ fontSize: '0.6rem', color: 'var(--c-purple)', opacity: 0.7 }}>JUDGE DELIBERATING…</span>}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {!isModal && (
          <button
            onClick={() => setIsModalOpen(true)}
            title="Open in full-screen modal"
            style={{
              display: 'flex', alignItems: 'center', gap: 5, padding: '4px 10px',
              borderRadius: 6, background: 'rgba(168,85,247,0.1)',
              border: '1px solid rgba(168,85,247,0.3)', color: 'var(--c-purple)',
              cursor: 'pointer', fontSize: '0.68rem', fontWeight: 700,
            }}
          >
            ⤢ Expand
          </button>
        )}
        <button
          onClick={isModal ? () => setIsModalOpen(false) : onClose}
          style={{ background: 'none', border: 'none', color: 'var(--c-text-faint)', cursor: 'pointer', fontSize: '1.3rem', lineHeight: 1 }}
        >×</button>
      </div>
    </div>
  )

  const statusBar = (
    <div style={{ padding: '5px 16px', fontSize: '0.71rem', color: 'var(--c-text-dim)', fontFamily: 'var(--font-mono)', borderBottom: '1px solid var(--c-border)', flexShrink: 0 }}>
      {status === 'complete' ? '✅ ' : status === 'error' ? '❌ ' : '⏳ '}{message}
    </div>
  )

  // ── Judge verdict panel (shared between inline and modal) ─────────────────
  const judgePanel = (judgeRawText || judgeRca) ? (
    <div style={{ padding: '14px 16px', borderTop: '1px solid var(--c-purple)', flexShrink: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: '0.7rem', fontWeight: 800, color: 'var(--c-purple)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
          ⚖️ Judge Verdict
        </span>
        {judgeRca && (
          <span style={{ fontSize: '0.62rem', fontWeight: 700, padding: '2px 8px', borderRadius: 20, border: `1px solid ${confidenceColor}`, color: confidenceColor, textTransform: 'uppercase' }}>
            {judgeRca.confidence} confidence
          </span>
        )}
        {judgeIsStreaming && <Cursor />}
      </div>
      <JudgeStreamView rawText={judgeRawText} isComplete={!!judgeRca} judgeRca={judgeRca} />
      {judgeRca && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 14 }}>
          <button onClick={onClose} style={{ padding: '6px 14px', borderRadius: 7, border: '1px solid var(--c-border-hi)', background: 'transparent', color: 'var(--c-text-dim)', cursor: 'pointer', fontSize: '0.75rem', fontWeight: 600 }}>
            Dismiss
          </button>
          <button onClick={() => window.location.reload()} style={{ padding: '6px 16px', borderRadius: 7, border: 'none', background: 'var(--c-purple)', color: '#fff', cursor: 'pointer', fontSize: '0.75rem', fontWeight: 700, boxShadow: '0 3px 12px rgba(168,85,247,0.3)' }}>
            Apply RCA to Investigation
          </button>
        </div>
      )}
    </div>
  ) : null

  // ── Inline (on-page) view ─────────────────────────────────────────────────
  return (
    <>
      <div style={{ marginBottom: 24, background: 'var(--c-surface)', border: '1px solid var(--c-purple)', borderRadius: 12, overflow: 'hidden', boxShadow: '0 0 20px rgba(168,85,247,0.1)' }}>
        {headerBar(false)}
        {statusBar}
        {/* Agents: fixed height grid — overflow hidden prevents bleed into judge panel */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', height: 260, borderBottom: '1px solid var(--c-border)', overflow: 'hidden' }}>
          <div style={{ borderRight: '1px solid var(--c-border)', height: '100%', overflow: 'hidden' }}>
            <AgentColumn label="Agent Alpha (Infra)" color="var(--c-yellow)" text={alphaText} isRunning={isRunning && !betaText && !alphaText} />
          </div>
          <AgentColumn label="Agent Beta (Network)" color="var(--c-green)" text={betaText} isRunning={isRunning && !betaText && !alphaText} />
        </div>
        {judgePanel}
      </div>

      {/* ── Full-screen Portal Modal ──────────────────────────────────────── */}
      {isModalOpen && (
        <Modal onClose={() => setIsModalOpen(false)}>
          {headerBar(true)}
          {statusBar}
          {/* Modal agents: fill available height */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', flex: 1, minHeight: 0, borderBottom: '1px solid var(--c-border)', overflow: 'hidden' }}>
            <div style={{ borderRight: '1px solid var(--c-border)', height: '100%' }}>
              <AgentColumn label="🟡 Agent Alpha — Infrastructure Specialist" color="var(--c-yellow)" text={alphaText} isRunning={isRunning} />
            </div>
            <AgentColumn label="🟢 Agent Beta — Network & App Specialist" color="var(--c-green)" text={betaText} isRunning={isRunning} />
          </div>
          {judgePanel}
        </Modal>
      )}
    </>
  )
}
