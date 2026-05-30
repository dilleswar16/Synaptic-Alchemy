import { useEffect, useState, useRef } from 'react'
import { createPortal } from 'react-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { API_BASE } from '../../api/baseUrl'

interface WarRoomProps {
  requestId: string
  onClose: () => void
}

// ── Shared Markdown component config ────────────────────────────────────────
const mdComponents = {
  strong: ({ children }: any) => (
    <strong style={{ color: 'var(--c-text)', fontWeight: 700 }}>{children}</strong>
  ),
  em: ({ children }: any) => (
    <em style={{ color: 'var(--c-text-dim)' }}>{children}</em>
  ),
  code: ({ children }: any) => (
    <code style={{
      fontFamily: 'var(--font-mono)', fontSize: '0.85em',
      background: 'rgba(168,85,247,0.1)', padding: '1px 5px',
      borderRadius: 4, color: 'var(--c-purple)'
    }}>{children}</code>
  ),
  p: ({ children }: any) => (
    <p style={{ margin: '0 0 10px', lineHeight: 1.65 }}>{children}</p>
  ),
  ul: ({ children }: any) => (
    <ul style={{ margin: '0 0 10px', paddingLeft: 18 }}>{children}</ul>
  ),
  li: ({ children }: any) => (
    <li style={{ marginBottom: 4, lineHeight: 1.6 }}>{children}</li>
  ),
}

// ── Modal Portal ─────────────────────────────────────────────────────────────
function Modal({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  // Close on Escape key
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
        backgroundColor: 'rgba(5, 8, 18, 0.75)',
        backdropFilter: 'blur(6px)',
        padding: 24,
      }}
    >
      <div style={{
        position: 'relative',
        width: '100%', maxWidth: 1100,
        maxHeight: 'calc(100vh - 48px)',
        background: 'var(--c-surface)',
        border: '1px solid var(--c-purple)',
        borderRadius: 16,
        boxShadow: '0 24px 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(168,85,247,0.2)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {children}
      </div>
    </div>,
    document.body
  )
}

// ── Agent Panel ──────────────────────────────────────────────────────────────
function AgentPanel({ label, color, text, isRunning, scrollRef }: {
  label: string
  color: string
  text: string
  isRunning: boolean
  scrollRef: React.RefObject<HTMLDivElement>
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
      <div style={{
        padding: '8px 16px',
        fontSize: '0.68rem', fontWeight: 800, letterSpacing: '0.1em',
        textTransform: 'uppercase', color,
        borderBottom: `1px solid color-mix(in srgb, ${color} 20%, transparent)`,
        flexShrink: 0
      }}>
        {label}
      </div>
      <div ref={scrollRef} style={{
        flex: 1, overflowY: 'auto', padding: 16,
        fontSize: '0.78rem', lineHeight: 1.65,
        color: 'var(--c-text-dim)',
        fontFamily: 'var(--font-body)',
      }}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
          {text || (isRunning ? '▌' : '—')}
        </ReactMarkdown>
        {isRunning && text && <span style={{ opacity: 0.7 }}>▌</span>}
      </div>
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────
export function WarRoomTerminal({ requestId, onClose }: WarRoomProps) {
  const [alphaText, setAlphaText] = useState('')
  const [betaText, setBetaText] = useState('')
  const [status, setStatus] = useState<'idle' | 'running' | 'complete' | 'error'>('idle')
  const [message, setMessage] = useState('Summoning agents Alpha and Beta...')
  const [judgeRca, setJudgeRca] = useState<any>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const alphaRef = useRef<HTMLDivElement>(null)
  const betaRef = useRef<HTMLDivElement>(null)
  const alphaModalRef = useRef<HTMLDivElement>(null)
  const betaModalRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setStatus('running')
    setAlphaText('')
    setBetaText('')

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
          } else if (data.status === 'complete') {
            setStatus('complete')
            setMessage(data.message)
            setJudgeRca({ summary: data.summary, root_cause: data.root_cause, confidence: data.confidence })
            source.close()
          }
        } else if (data.stage === 'error') {
          setStatus('error')
          setMessage(data.message)
          source.close()
        }
      } catch (err) {
        console.error('SSE Parse Error:', err)
      }
    }

    source.onerror = () => {
      setStatus('error')
      setMessage('Lost connection to Debate Orchestrator.')
      source.close()
    }

    return () => source.close()
  }, [requestId])

  // Auto-scroll panels
  useEffect(() => {
    alphaRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' })
    alphaModalRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' })
  }, [alphaText])

  useEffect(() => {
    betaRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' })
    betaModalRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' })
  }, [betaText])

  const confidenceColor = judgeRca?.confidence === 'high'
    ? 'var(--c-green)' : judgeRca?.confidence === 'medium'
    ? 'var(--c-yellow)' : 'var(--c-red)'

  // ── Inline summary panel (shown on the page) ──────────────────────────────
  const inlineSummary = (
    <div style={{
      marginBottom: 24,
      background: 'var(--c-surface)',
      border: '1px solid var(--c-purple)',
      borderRadius: 12,
      overflow: 'hidden',
      boxShadow: '0 0 20px rgba(168, 85, 247, 0.1)'
    }}>
      {/* Header */}
      <div style={{
        padding: '10px 16px',
        background: 'var(--c-surface-2)',
        borderBottom: '1px solid var(--c-purple)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center'
      }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontSize: '0.72rem', fontWeight: 800,
          letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--c-purple)',
          display: 'flex', alignItems: 'center', gap: 8
        }}>
          ⚔️ Agent Consensus Engine
          {status === 'running' && <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--c-purple)', display: 'inline-block', animation: 'corvin-blink 1s steps(1) infinite' }} />}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            onClick={() => setIsModalOpen(true)}
            title="Open in full-screen modal"
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '4px 10px', borderRadius: 6,
              background: 'rgba(168,85,247,0.1)',
              border: '1px solid rgba(168,85,247,0.3)',
              color: 'var(--c-purple)', cursor: 'pointer',
              fontSize: '0.68rem', fontWeight: 700, letterSpacing: '0.05em'
            }}
          >
            <span style={{ fontSize: '0.85rem' }}>⤢</span> Expand
          </button>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--c-text-faint)', cursor: 'pointer', fontSize: '1.2rem', lineHeight: 1 }}>×</button>
        </div>
      </div>

      {/* Status bar */}
      <div style={{ padding: '6px 16px', fontSize: '0.72rem', color: 'var(--c-text-dim)', fontFamily: 'var(--font-mono)', borderBottom: '1px solid var(--c-border)' }}>
        {status === 'complete' ? '✅ ' : status === 'error' ? '❌ ' : '⏳ '}{message}
      </div>

      {/* Agents side-by-side (compact view, 220px height) */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', borderBottom: '1px solid var(--c-border)' }}>
        <div style={{ borderRight: '1px solid var(--c-border)' }}>
          <AgentPanel label="Agent Alpha (Infra)" color="var(--c-yellow)" text={alphaText} isRunning={status === 'running'} scrollRef={alphaRef} />
        </div>
        <AgentPanel label="Agent Beta (Network)" color="var(--c-green)" text={betaText} isRunning={status === 'running'} scrollRef={betaRef} />
      </div>

      {/* Judge verdict – appears after debate */}
      {status === 'complete' && judgeRca && (
        <div style={{ padding: '14px 16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span style={{ fontSize: '0.72rem', fontWeight: 800, color: 'var(--c-purple)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>⚖️ Judge Verdict</span>
            <span style={{
              fontSize: '0.62rem', fontWeight: 700, padding: '2px 8px', borderRadius: 20,
              border: `1px solid ${confidenceColor}`,
              color: confidenceColor,
              textTransform: 'uppercase'
            }}>{judgeRca.confidence} confidence</span>
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--c-text-dim)', lineHeight: 1.6, fontFamily: 'var(--font-body)' }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>{judgeRca.root_cause}</ReactMarkdown>
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 12 }}>
            <button onClick={onClose} style={{ padding: '6px 14px', borderRadius: 7, border: '1px solid var(--c-border-hi)', background: 'transparent', color: 'var(--c-text-dim)', cursor: 'pointer', fontSize: '0.75rem', fontWeight: 600 }}>
              Dismiss
            </button>
            <button onClick={() => window.location.reload()} style={{ padding: '6px 16px', borderRadius: 7, border: 'none', background: 'var(--c-purple)', color: '#fff', cursor: 'pointer', fontSize: '0.75rem', fontWeight: 700 }}>
              Apply RCA to Investigation
            </button>
          </div>
        </div>
      )}
    </div>
  )

  // ── Full-screen modal content ─────────────────────────────────────────────
  const modalContent = isModalOpen && (
    <Modal onClose={() => setIsModalOpen(false)}>
      {/* Modal Header */}
      <div style={{
        padding: '14px 20px', background: 'var(--c-surface-2)',
        borderBottom: '1px solid var(--c-purple)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        flexShrink: 0
      }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontSize: '0.8rem', fontWeight: 800,
          letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--c-purple)',
          display: 'flex', alignItems: 'center', gap: 10
        }}>
          ⚔️ Agent Consensus Engine — Full Debate View
          {status === 'running' && <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--c-purple)', display: 'inline-block', animation: 'corvin-blink 1s steps(1) infinite' }} />}
        </div>
        <button onClick={() => setIsModalOpen(false)} style={{ background: 'none', border: 'none', color: 'var(--c-text-faint)', cursor: 'pointer', fontSize: '1.4rem', lineHeight: 1, padding: '2px 6px' }} title="Close modal">×</button>
      </div>

      {/* Modal Status Bar */}
      <div style={{ padding: '6px 20px', fontSize: '0.72rem', color: 'var(--c-text-dim)', fontFamily: 'var(--font-mono)', borderBottom: '1px solid var(--c-border)', flexShrink: 0 }}>
        {status === 'complete' ? '✅ ' : status === 'error' ? '❌ ' : '⏳ '}{message}
      </div>

      {/* Modal Body — scrollable agents, fixed height */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', flex: 1, minHeight: 0, borderBottom: '1px solid var(--c-border)' }}>
        <div style={{ borderRight: '1px solid var(--c-border)', display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
          <div style={{ padding: '8px 20px', fontSize: '0.68rem', fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--c-yellow)', borderBottom: '1px solid rgba(234,179,8,0.15)', flexShrink: 0 }}>
            🟡 Agent Alpha — Infrastructure Specialist
          </div>
          <div ref={alphaModalRef} style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', fontSize: '0.82rem', color: 'var(--c-text-dim)', lineHeight: 1.7, fontFamily: 'var(--font-body)' }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
              {alphaText || (status === 'running' ? '▌' : '—')}
            </ReactMarkdown>
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
          <div style={{ padding: '8px 20px', fontSize: '0.68rem', fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--c-green)', borderBottom: '1px solid rgba(16,185,129,0.15)', flexShrink: 0 }}>
            🟢 Agent Beta — Network & App Specialist
          </div>
          <div ref={betaModalRef} style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', fontSize: '0.82rem', color: 'var(--c-text-dim)', lineHeight: 1.7, fontFamily: 'var(--font-body)' }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
              {betaText || (status === 'running' ? '▌' : '—')}
            </ReactMarkdown>
          </div>
        </div>
      </div>

      {/* Judge Verdict Footer */}
      {status === 'complete' && judgeRca && (
        <div style={{ padding: '16px 20px', background: 'var(--c-surface-2)', flexShrink: 0, borderTop: '1px solid var(--c-purple)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
            <span style={{ fontFamily: 'var(--font-display)', fontSize: '0.75rem', fontWeight: 800, color: 'var(--c-purple)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>⚖️ Judge Verdict</span>
            <span style={{ fontSize: '0.65rem', fontWeight: 700, padding: '2px 10px', borderRadius: 20, border: `1px solid ${confidenceColor}`, color: confidenceColor, textTransform: 'uppercase' }}>
              {judgeRca.confidence} confidence
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 14 }}>
            <div>
              <div style={{ fontSize: '0.65rem', fontWeight: 700, color: 'var(--c-text-faint)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Root Cause</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--c-text)', lineHeight: 1.6, fontFamily: 'var(--font-body)' }}>
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>{judgeRca.root_cause}</ReactMarkdown>
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.65rem', fontWeight: 700, color: 'var(--c-text-faint)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Summary</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--c-text)', lineHeight: 1.6, fontFamily: 'var(--font-body)' }}>
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>{judgeRca.summary}</ReactMarkdown>
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
            <button onClick={() => { setIsModalOpen(false); onClose() }} style={{ padding: '7px 16px', borderRadius: 8, border: '1px solid var(--c-border-hi)', background: 'transparent', color: 'var(--c-text-dim)', cursor: 'pointer', fontSize: '0.78rem', fontWeight: 600 }}>
              Dismiss
            </button>
            <button onClick={() => window.location.reload()} style={{ padding: '7px 20px', borderRadius: 8, border: 'none', background: 'var(--c-purple)', color: '#fff', cursor: 'pointer', fontSize: '0.78rem', fontWeight: 700, boxShadow: '0 3px 12px rgba(168,85,247,0.35)' }}>
              Apply RCA to Investigation
            </button>
          </div>
        </div>
      )}
    </Modal>
  )

  return (
    <>
      {inlineSummary}
      {modalContent}
    </>
  )
}
