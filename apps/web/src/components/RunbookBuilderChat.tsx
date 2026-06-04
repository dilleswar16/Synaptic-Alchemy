import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  startRunbookSession,
  streamRunbookMessage,
  approveRunbookDraft,
  saveRunbook,
  type RunbookDraft,
} from '../api/client'

interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
}

export default function RunbookBuilderChat({ requestId, serviceName, environment = '' }: {
  requestId: string
  serviceName: string
  environment?: string
}) {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState<RunbookDraft | null>(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<string>('idle')
  const [error, setError] = useState<string | null>(null)
  const [showDraft, setShowDraft] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleStart() {
    setLoading(true)
    setError(null)
    try {
      const res = await startRunbookSession(requestId, serviceName, environment)
      setSessionId(res.session_id)
      setStatus(res.status)
      if (res.initial_response) {
        setMessages([{ role: 'assistant', content: res.initial_response, timestamp: new Date().toISOString() }])
      }
      if (res.draft) setDraft(res.draft)
    } catch (e: any) {
      setError(e.message || 'Failed to start session')
    } finally {
      setLoading(false)
    }
  }

  async function handleSend() {
    if (!sessionId || !input.trim()) return
    const userMsg = input.trim()
    const assistantTs = new Date().toISOString()
    setInput('')
    let assistantIndex = -1
    setMessages((prev) => {
      assistantIndex = prev.length + 1
      return [
        ...prev,
        { role: 'user', content: userMsg, timestamp: new Date().toISOString() },
        { role: 'assistant', content: '', timestamp: assistantTs },
      ]
    })
    setLoading(true)
    setError(null)

    streamRunbookMessage(
      sessionId,
      userMsg,
      (event) => {
        if (event.type === 'token') {
          setMessages((prev) => {
            if (assistantIndex < 0 || assistantIndex >= prev.length) return prev
            const next = [...prev]
            next[assistantIndex] = {
              ...next[assistantIndex],
              content: `${next[assistantIndex].content || ''}${event.text || ''}`,
            }
            return next
          })
          return
        }

        if (event.type === 'done') {
          if (event.draft) setDraft(event.draft)
          setLoading(false)
          return
        }

        if (event.type === 'error') {
          setError(event.error || 'Send failed')
          setLoading(false)
        }
      },
      (err) => {
        setError(err.message || 'Send failed')
        setLoading(false)
      },
    )
  }

  async function handleApprove() {
    if (!sessionId) return
    setLoading(true)
    try {
      const res = await approveRunbookDraft(sessionId)
      setStatus(res.status)
      setDraft(res.draft)
      setMessages((prev) => [...prev, { role: 'system', content: '✓ Draft approved. You can now save it.', timestamp: new Date().toISOString() }])
    } catch (e: any) {
      setError(e.message || 'Approval failed')
    } finally {
      setLoading(false)
    }
  }

  async function handleSave() {
    if (!sessionId) return
    setLoading(true)
    try {
      const res = await saveRunbook(sessionId)
      setStatus('saved')
      setMessages((prev) => [...prev, { role: 'system', content: `✓ Runbook saved to: ${res.path}`, timestamp: new Date().toISOString() }])
    } catch (e: any) {
      setError(e.message || 'Save failed')
    } finally {
      setLoading(false)
    }
  }

  // Not started yet
  if (!sessionId) {
    return (
      <div style={{
        background: 'var(--c-surface)',
        border: '1px solid var(--c-border)',
        borderRadius: 12,
        padding: 24,
      }}>
        <h4 style={{ margin: '0 0 8px', fontFamily: 'var(--font-display)' }}>📝 Runbook Builder</h4>
        <p style={{ fontSize: '0.82rem', color: 'var(--c-text-muted)', margin: '0 0 12px' }}>
          Start a conversational session to build or iterate on a runbook for this incident.
        </p>
        {error && <div style={{ color: 'var(--c-red)', fontSize: '0.8rem', marginBottom: 8 }}>{error}</div>}
        <button className="btn-primary" onClick={handleStart} disabled={loading} style={{ fontSize: '0.82rem' }}>
          {loading ? 'Starting…' : 'Start Runbook Session'}
        </button>
      </div>
    )
  }

  return (
    <div style={{
      background: 'var(--c-surface)',
      border: '1px solid var(--c-border)',
      borderRadius: 12,
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column',
      maxHeight: 520,
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px',
        borderBottom: '1px solid var(--c-border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <span style={{ fontWeight: 700, fontSize: '0.88rem' }}>📝 Runbook Builder</span>
        <div style={{ display: 'flex', gap: 6 }}>
          {draft && (
            <button
              onClick={() => setShowDraft(!showDraft)}
              style={{
                fontSize: '0.72rem',
                padding: '3px 8px',
                background: showDraft ? 'var(--c-link)' : 'transparent',
                color: showDraft ? '#fff' : 'var(--c-link)',
                border: '1px solid var(--c-link)',
                borderRadius: 4,
                cursor: 'pointer',
              }}
            >
              {showDraft ? 'Hide Draft' : `View Draft v${draft.version}`}
            </button>
          )}
          {status === 'drafting' && draft && (
            <button className="btn-primary" onClick={handleApprove} disabled={loading} style={{ fontSize: '0.72rem', padding: '3px 8px' }}>
              ✓ Approve Draft
            </button>
          )}
          {status === 'approved' && (
            <button className="btn-primary" onClick={handleSave} disabled={loading} style={{ fontSize: '0.72rem', padding: '3px 8px' }}>
              💾 Save to KB
            </button>
          )}
        </div>
      </div>

      {/* Draft preview */}
      {showDraft && draft && (
        <div style={{
          padding: '12px 16px',
          background: 'var(--c-bg)',
          borderBottom: '1px solid var(--c-border)',
          maxHeight: 180,
          overflow: 'auto',
          fontSize: '0.78rem',
          lineHeight: 1.5,
        }}>
          <div className="runbook-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{draft.content}</ReactMarkdown>
          </div>
        </div>
      )}

      {/* Messages */}
      <div style={{ flex: 1, overflow: 'auto', padding: '12px 16px' }}>
        {messages.map((msg, i) => (
          <div key={i} style={{
            marginBottom: 10,
            display: 'flex',
            flexDirection: 'column',
            alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
          }}>
            <div style={{
              maxWidth: '85%',
              padding: '8px 12px',
              borderRadius: 8,
              fontSize: '0.82rem',
              lineHeight: 1.4,
              background: msg.role === 'user' ? 'var(--c-link)' : msg.role === 'system' ? 'var(--c-bg)' : 'var(--c-border)',
              color: msg.role === 'user' ? '#fff' : 'var(--c-text)',
            }}>
              {msg.role === 'user' ? (
                msg.content
              ) : (
                <div className="runbook-markdown">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>
              )}
            </div>
            <span style={{ fontSize: '0.65rem', color: 'var(--c-text-muted)', marginTop: 2 }}>
              {new Date(msg.timestamp).toLocaleTimeString()}
            </span>
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>

      {/* Input */}
      {status !== 'saved' && (
        <div style={{
          padding: '10px 16px',
          borderTop: '1px solid var(--c-border)',
          display: 'flex',
          gap: 8,
        }}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder={status === 'approved' ? 'Draft approved — save to KB' : 'Iterate on the runbook…'}
            disabled={loading || status === 'approved'}
            style={{
              flex: 1,
              padding: '8px 12px',
              borderRadius: 6,
              border: '1px solid var(--c-border)',
              background: 'var(--c-bg)',
              color: 'var(--c-text)',
              fontSize: '0.82rem',
            }}
          />
          <button className="btn-primary" onClick={handleSend} disabled={loading || !input.trim() || status === 'approved'} style={{ fontSize: '0.8rem' }}>
            Send
          </button>
        </div>
      )}

      {error && (
        <div style={{ padding: '6px 16px', fontSize: '0.78rem', color: 'var(--c-red)' }}>{error}</div>
      )}
    </div>
  )
}
