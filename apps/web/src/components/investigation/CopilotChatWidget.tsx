import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { API_BASE } from '../../api/baseUrl'

interface Message {
  role: 'user' | 'assistant'
  content: string
  thinking?: string
  thinkingDone?: boolean
}

interface Props {
  requestId: string
}

// ── SVG Icons ──────────────────────────────────────────────────────────────────
function CorvinBotIcon({ size = 22, color = 'var(--c-signal)' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="cg1" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop stopColor={color}/>
          <stop offset="1" stopColor={color}/>
        </linearGradient>
      </defs>
      {/* Hexagonal head */}
      <path d="M16 2 L28 9 L28 23 L16 30 L4 23 L4 9 Z" fill={color} opacity="0.15" stroke={color} strokeWidth="1.5"/>
      {/* Eyes */}
      <rect x="9" y="13" width="5" height="2.5" rx="1.25" fill={color}/>
      <rect x="18" y="13" width="5" height="2.5" rx="1.25" fill={color}/>
      {/* Mouth / signal bar */}
      <rect x="11" y="18.5" width="10" height="1.5" rx="0.75" fill={color} opacity="0.7"/>
      {/* Antenna */}
      <line x1="16" y1="2" x2="16" y2="6" stroke={color} strokeWidth="1.5" strokeLinecap="round"/>
      <circle cx="16" cy="5" r="1.5" fill={color}/>
    </svg>
  )
}

// ── ThinkingBlock ─────────────────────────────────────────────────────────────
// Commented out for now — re-enable when you want reasoning visible in the UI.
// Usage: <ThinkingBlock text={m.thinking} streaming={isStreaming && !m.thinkingDone} />
/*
function ThinkingBlock({ text, streaming }: { text: string; streaming: boolean }) {
  const [open, setOpen] = useState(true)
  useEffect(() => {
    if (!streaming) {
      const t = setTimeout(() => setOpen(false), 1200)
      return () => clearTimeout(t)
    }
  }, [streaming])
  return (
    <div style={{ marginBottom: 8, borderRadius: 8, border: '1px solid var(--c-purple-border)', overflow: 'hidden', background: 'var(--c-purple-bg)' }}>
      <button onClick={() => setOpen(o => !o)} style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
        <span style={{ fontSize: '0.75rem' }}>🧠</span>
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.65rem', letterSpacing: '0.1em', color: 'var(--c-purple)', textTransform: 'uppercase' }}>
          {streaming ? 'Thinking…' : 'Reasoning'}
        </span>
        {streaming && <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: 'var(--c-purple)', marginLeft: 2, animation: 'corvin-blink 0.7s steps(1) infinite' }} />}
        <span style={{ marginLeft: 'auto', color: 'var(--c-purple)', fontSize: '0.7rem' }}>{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div style={{ padding: '6px 12px 10px', fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'color-mix(in srgb, var(--c-purple) 85%, var(--c-text))', lineHeight: 1.55, whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 180, overflowY: 'auto', borderTop: '1px solid var(--c-purple-border)' }}>
          {text}
          {streaming && <span style={{ display: 'inline-block', width: 2, height: '1em', background: 'var(--c-purple)', marginLeft: 1, animation: 'corvin-blink 0.7s steps(1) infinite' }} />}
        </div>
      )}
    </div>
  )
}
*/

// ── Markdown components (react-markdown v10 compatible) ───────────────────────
const mdComponents = {
  // Scrollable table wrapper — prevents horizontal overflow
  table: ({ children }: { children?: React.ReactNode }) => (
    <div style={{ overflowX: 'auto', margin: '8px 0', borderRadius: 6, border: '1px solid var(--c-border)' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 280 }}>
        {children}
      </table>
    </div>
  ),
  th: ({ children }: { children?: React.ReactNode }) => (
    <th style={{ padding: '5px 10px', background: 'var(--c-surface-3)', fontWeight: 700, borderBottom: '1px solid var(--c-border)', whiteSpace: 'nowrap', fontFamily: 'var(--font-display)', fontSize: '0.7rem', textAlign: 'left' }}>
      {children}
    </th>
  ),
  td: ({ children }: { children?: React.ReactNode }) => (
    <td style={{ padding: '5px 10px', borderBottom: '1px solid var(--c-border)', fontSize: '0.72rem', fontFamily: 'var(--font-mono)', verticalAlign: 'top' }}>
      {children}
    </td>
  ),
  // v10 fix: `inline` prop is removed. Detect block vs inline by className.
  // Block code has className="language-xxx"; inline code has none.
  pre: ({ children }: { children?: React.ReactNode }) => (
    <pre style={{ background: 'var(--c-surface-2)', border: '1px solid var(--c-border)', borderRadius: 6, padding: '10px 12px', overflowX: 'auto', margin: '8px 0' }}>
      {children}
    </pre>
  ),
  code: ({ className, children }: { className?: string; children?: React.ReactNode }) => {
    const isBlock = Boolean(className) // block code has e.g. "language-bash"
    if (isBlock) {
      return <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72em', color: 'var(--c-text-dim)' }}>{children}</code>
    }
    // Inline code
    return (
      <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78em', background: 'var(--c-surface-3)', padding: '2px 5px', borderRadius: 4, color: 'var(--c-text)' }}>
        {children}
      </code>
    )
  },
}

// ── Global CSS ─────────────────────────────────────────────────────────────────
const mdStyles = `
  .corvin-md p { margin: 0 0 8px; line-height: 1.6; }
  .corvin-md p:last-child { margin-bottom: 0; }
  .corvin-md ul, .corvin-md ol { padding-left: 20px; margin: 0 0 8px; }
  .corvin-md li { margin-bottom: 4px; line-height: 1.55; }
  .corvin-md li p { margin: 0; }
  .corvin-md strong { color: var(--c-text); }
  .corvin-md em { color: var(--c-text-dim); }
  .corvin-md h1, .corvin-md h2, .corvin-md h3 {
    font-family: var(--font-display); font-weight: 700; margin: 12px 0 5px; color: var(--c-text);
  }
  .corvin-md h1 { font-size: 0.95rem; }
  .corvin-md h2 { font-size: 0.88rem; border-bottom: 1px solid var(--c-border); padding-bottom: 3px; }
  .corvin-md h3 { font-size: 0.8rem; }
  .corvin-md blockquote {
    border-left: 3px solid var(--c-signal); margin: 0 0 8px; padding: 4px 10px;
    color: var(--c-text-dim); background: var(--c-signal-light); border-radius: 0 4px 4px 0;
  }
  .corvin-md hr { border: none; border-top: 1px solid var(--c-border); margin: 10px 0; }
  @keyframes corvin-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
`

// ── Streaming fence patcher ────────────────────────────────────────────────────
// Closes any open ``` or ` so ReactMarkdown always gets a valid parse tree
// while tokens are still arriving. Does NOT reorder content.
function safeMarkdown(content: string, streaming: boolean): string {
  if (!content) return content
  if (!streaming) return content

  let s = content

  // Close unclosed triple-backtick code fences
  const tripleCount = (s.match(/```/g) || []).length
  if (tripleCount % 2 !== 0) s += '\n```'

  // Close unclosed inline backticks (ignore ones inside completed fences)
  const stripped = s.replace(/```[\s\S]*?```/g, '')
  const singleCount = (stripped.match(/(?<!`)`(?!`)/g) || []).length
  if (singleCount % 2 !== 0) s += '`'

  if (!s.endsWith('\n')) s += '\n'

  return s
}

// ── Widget ─────────────────────────────────────────────────────────────────────
export function CopilotChatWidget({ requestId }: Props) {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Load persisted chat history the first time the widget is opened
  const loadHistory = useCallback(async () => {
    if (historyLoaded) return
    try {
      const res = await fetch(`${API_BASE}/investigations/${requestId}/chat/history`)
      if (res.ok) {
        const rows: Array<{ role: string; content: string }> = await res.json()
        if (rows.length > 0) {
          setMessages(rows.map(r => ({ role: r.role as 'user' | 'assistant', content: r.content })))
        }
      }
    } catch { /* history fetch is non-critical */ }
    finally { setHistoryLoaded(true) }
  }, [requestId, historyLoaded])

  useEffect(() => {
    if (open) loadHistory()
  }, [open, loadHistory])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || loading) return

    const userMsg = input.trim()
    setInput('')
    const historyForApi = [...messages, { role: 'user' as const, content: userMsg }]

    setMessages(prev => [
      ...prev,
      { role: 'user', content: userMsg },
      { role: 'assistant', content: '', thinking: undefined, thinkingDone: false },
    ])
    setLoading(true)

    try {
      const res = await fetch(`${API_BASE}/investigations/${requestId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: historyForApi }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`)

      const reader = res.body?.getReader()
      if (!reader) throw new Error('No reader')
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (raw === '[DONE]') break
          try {
            const data = JSON.parse(raw)
            if (data.type === 'thinking' && data.text) {
              setMessages(prev => {
                const next = [...prev]
                const last = next[next.length - 1]
                next[next.length - 1] = { ...last, thinking: (last.thinking ?? '') + data.text }
                return next
              })
            } else if (data.text) {
              setMessages(prev => {
                const next = [...prev]
                const last = next[next.length - 1]
                next[next.length - 1] = { ...last, thinkingDone: true, content: last.content + data.text }
                return next
              })
            }
          } catch { /* incomplete chunk */ }
        }
      }
    } catch (err) {
      setMessages(prev => {
        const next = [...prev]
        const last = next[next.length - 1]
        next[next.length - 1] = { ...last, thinkingDone: true, content: `> ⚠️ **Error:** ${(err as Error).message}` }
        return next
      })
    } finally {
      setLoading(false)
      setMessages(prev => prev.map(m => m.role === 'assistant' ? { ...m, thinkingDone: true } : m))
    }
  }

  if (!open) {
    return (
      <>
        <style>{mdStyles}</style>
        <button
          onClick={() => setOpen(true)}
          title="Ask Corvin"
          style={{
            position: 'fixed', bottom: 32, right: 32,
            width: 56, height: 56, borderRadius: '50%',
            background: 'var(--c-signal)',
            border: 'none', cursor: 'pointer',
            boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 9999, transition: 'transform 0.15s, box-shadow 0.15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.transform = 'scale(1.05)'; e.currentTarget.style.boxShadow = '0 6px 24px rgba(0,0,0,0.35)' }}
          onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)'; e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.25)' }}
        >
          <CorvinBotIcon size={30} color="rgba(255,255,255,0.95)" />
        </button>
      </>
    )
  }

  return (
    <>
      <style>{mdStyles}</style>
      <div style={{
        position: 'fixed', bottom: 32, right: 32,
        width: 'min(430px, calc(100vw - 48px))', height: 'min(590px, calc(100vh - 80px))', borderRadius: 16,
        background: 'color-mix(in srgb, var(--c-surface) 90%, transparent)',
        backdropFilter: 'blur(20px)',
        border: '1px solid var(--c-border-hi)',
        boxShadow: '0 16px 56px rgba(0,0,0,0.55)',
        display: 'flex', flexDirection: 'column', zIndex: 9999,
        overflow: 'hidden',
      }}>

        {/* Header */}
        <div style={{ padding: '12px 16px', background: 'var(--c-surface-2)', borderBottom: '1px solid var(--c-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 34, height: 34, borderRadius: 10, background: 'var(--c-signal-light)', border: '1px solid var(--c-signal-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <CorvinBotIcon size={20} />
            </div>
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.8rem', color: 'var(--c-text)' }}>Ask Corvin</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-signal)' }}>Copilot Active · incident context loaded</div>
            </div>
          </div>
          <button onClick={() => setOpen(false)} style={{ background: 'none', border: 'none', color: 'var(--c-text-faint)', cursor: 'pointer', fontSize: '1rem', lineHeight: 1 }}>✕</button>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 14px', display: 'flex', flexDirection: 'column', gap: 14, minHeight: 0 }}>
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', color: 'var(--c-text-muted)', fontFamily: 'var(--font-mono)', fontSize: '0.78rem', marginTop: 40, lineHeight: 1.8 }}>
              I have the full context of this incident.<br />
              <span style={{ color: 'var(--c-text-faint)', fontSize: '0.72rem' }}>RCA · Evidence · Fix Strategy · CHAD Knowledge</span><br />
              Ask me anything.
            </div>
          )}

          {messages.map((m, i) => {
            const isStreaming = loading && i === messages.length - 1
            return (
              <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start', flexDirection: 'column', alignItems: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                {/* ThinkingBlock disabled — uncomment above to re-enable */}

                {(m.role === 'user' || m.content || isStreaming) && (
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, maxWidth: '92%' }}>
                    {m.role === 'assistant' && (
                      <div style={{ marginTop: 2, flexShrink: 0, width: 26, height: 26, borderRadius: 8, background: 'var(--c-signal-light)', border: '1px solid var(--c-signal-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <CorvinBotIcon size={16} />
                      </div>
                    )}
                    <div style={{
                      padding: '10px 14px',
                      borderRadius: m.role === 'user' ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
                      background: m.role === 'user'
                        ? 'linear-gradient(135deg, var(--c-signal-light) 0%, transparent 100%)'
                        : 'var(--c-surface-2)',
                      border: `1px solid ${m.role === 'user' ? 'var(--c-signal-dim)' : 'var(--c-border-hi)'}`,
                      color: m.role === 'user' ? 'var(--c-signal)' : 'var(--c-text-dim)',
                      fontFamily: m.role === 'user' ? 'var(--font-mono)' : 'var(--font-body)',
                      fontSize: '0.78rem', lineHeight: 1.55,
                      minWidth: 0, overflow: 'hidden',
                    }}>
                      {m.role === 'user' ? m.content : (
                        <div className="corvin-md">
                          <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents as any}>
                            {isStreaming
                              ? safeMarkdown(m.content || '▌', true)
                              : m.content}
                          </ReactMarkdown>
                          {isStreaming && m.content && (
                            <span style={{ display: 'inline-block', width: 2, height: '1em', background: 'var(--c-signal)', marginLeft: 1, animation: 'corvin-blink 0.7s steps(1) infinite' }} />
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
          <div ref={endRef} />
        </div>

        {/* Input */}
        <form onSubmit={handleSubmit} style={{ padding: '12px 14px', borderTop: '1px solid var(--c-border)', background: 'var(--c-surface)', display: 'flex', gap: 8, flexShrink: 0 }}>
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Ask about this incident..."
            disabled={loading}
            className="corvin-interactive"
            style={{ flex: 1, padding: '9px 13px', borderRadius: 8, background: 'var(--c-surface-2)', border: '1px solid var(--c-border-hi)', color: 'var(--c-text)', fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            style={{
              padding: '0 16px', borderRadius: 8,
              background: loading || !input.trim() ? 'var(--c-surface-3)' : 'var(--c-signal)',
              color: loading || !input.trim() ? 'var(--c-text-faint)' : 'white',
              border: 'none', cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
              fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.75rem',
              transition: 'background 0.15s', whiteSpace: 'nowrap',
            }}
          >
            {loading ? '…' : 'Send'}
          </button>
        </form>
      </div>
    </>
  )
}
