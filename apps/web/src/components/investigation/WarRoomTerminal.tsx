import { useEffect, useState, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { API_BASE } from '../../api/baseUrl'

interface WarRoomProps {
  requestId: string
  onClose: () => void
}

export function WarRoomTerminal({ requestId, onClose }: WarRoomProps) {
  const [alphaText, setAlphaText] = useState('')
  const [betaText, setBetaText] = useState('')
  const [status, setStatus] = useState<'idle' | 'running' | 'complete' | 'error'>('idle')
  const [message, setMessage] = useState('')
  const [judgeRca, setJudgeRca] = useState<any>(null)
  const [isExpanded, setIsExpanded] = useState(false)
  const [typedRootCause, setTypedRootCause] = useState('')
  const [typedSummary, setTypedSummary] = useState('')
  const alphaRef = useRef<HTMLDivElement>(null)
  const betaRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setStatus('running')
    setMessage('Summoning Agents...')
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
            if (data.agent === 'alpha') {
              setAlphaText((prev) => prev + data.message)
            } else if (data.agent === 'beta') {
              setBetaText((prev) => prev + data.message)
            }
          } else if (data.status === 'complete') {
            setStatus('complete')
            setMessage(data.message)
            setJudgeRca({
              summary: data.summary,
              root_cause: data.root_cause,
              confidence: data.confidence
            })
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

    source.onerror = (err) => {
      console.error('SSE Connection Error:', err)
      setStatus('error')
      setMessage('Lost connection to Debate Orchestrator.')
      source.close()
    }

    return () => source.close()
  }, [requestId])

  useEffect(() => {
    if (alphaRef.current) alphaRef.current.scrollTop = alphaRef.current.scrollHeight
    if (betaRef.current) betaRef.current.scrollTop = betaRef.current.scrollHeight
  }, [alphaText, betaText])

  const handleApply = () => {
    window.location.reload()
  }

  // Simulated typing effect for Judge output
  useEffect(() => {
    if (judgeRca) {
      let r = 0;
      let s = 0;
      const rText = judgeRca.root_cause || '';
      const sText = judgeRca.summary || '';
      
      const timer = setInterval(() => {
        let changed = false;
        if (r < rText.length) {
          r += Math.min(10, rText.length - r);
          setTypedRootCause(rText.substring(0, r));
          changed = true;
        } else if (s < sText.length) {
          s += Math.min(10, sText.length - s);
          setTypedSummary(sText.substring(0, s));
          changed = true;
        }
        
        if (!changed) clearInterval(timer);
      }, 30);
      
      return () => clearInterval(timer);
    }
  }, [judgeRca])

  const content = (
    <div style={{
      background: 'var(--c-bg)',
      border: '1px solid var(--c-purple)',
      borderRadius: 12,
      overflow: 'hidden',
      boxShadow: isExpanded ? '0 0 40px rgba(168, 85, 247, 0.3)' : '0 0 15px rgba(168, 85, 247, 0.1)',
      display: 'flex',
      flexDirection: 'column',
      width: '100%',
      height: isExpanded ? '100%' : 'auto',
      maxHeight: isExpanded ? '100%' : 'auto'
    }}>
      <div style={{
        padding: '10px 14px',
        background: 'var(--c-surface-2)',
        borderBottom: '1px solid var(--c-purple)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontSize: '0.75rem', fontWeight: 800,
          letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--c-purple)',
          display: 'flex', alignItems: 'center', gap: 8
        }}>
          ⚔️ Agent Consensus Engine
          {status === 'running' && <span className="animate-pulse-glow" style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--c-purple)' }} />}
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <button onClick={() => setIsExpanded(!isExpanded)} style={{ background: 'none', border: 'none', color: 'var(--c-text-dim)', cursor: 'pointer', fontSize: '1.1rem' }} title={isExpanded ? "Collapse" : "Expand"}>
            {isExpanded ? '🗗' : '⛶'}
          </button>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--c-text-faint)', cursor: 'pointer', fontSize: '1.2rem' }}>×</button>
        </div>
      </div>

      <div style={{ padding: '8px 14px', fontSize: '0.75rem', color: 'var(--c-text-dim)', fontFamily: 'var(--font-mono)', borderBottom: '1px solid var(--c-border)' }}>
        {status === 'complete' ? '✅ ' : '⏳ '} {message}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, background: 'var(--c-border)', flex: isExpanded ? 1 : 'none', minHeight: 0 }}>
        <div style={{ background: 'var(--c-surface)', padding: 16, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <div style={{ fontSize: '0.7rem', fontWeight: 800, color: 'var(--c-yellow)', marginBottom: 8, textTransform: 'uppercase', flexShrink: 0 }}>
            Agent Alpha (Infra)
          </div>
          <div ref={alphaRef} className="pm-prose corvin-md" style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--c-text)', 
            whiteSpace: 'pre-wrap', maxHeight: isExpanded ? 'none' : 300, overflowY: 'auto', flex: 1
          }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{alphaText + (status === 'running' ? ' ▌' : '')}</ReactMarkdown>
          </div>
        </div>
        
        <div style={{ background: 'var(--c-surface)', padding: 16, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <div style={{ fontSize: '0.7rem', fontWeight: 800, color: 'var(--c-green)', marginBottom: 8, textTransform: 'uppercase', flexShrink: 0 }}>
            Agent Beta (Network)
          </div>
          <div ref={betaRef} className="pm-prose corvin-md" style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--c-text)', 
            whiteSpace: 'pre-wrap', maxHeight: isExpanded ? 'none' : 300, overflowY: 'auto', flex: 1
          }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{betaText + (status === 'running' ? ' ▌' : '')}</ReactMarkdown>
          </div>
        </div>
      </div>

      {status === 'complete' && judgeRca && (
        <div style={{ background: 'var(--c-surface-2)', padding: 16, borderTop: '1px solid var(--c-purple)', animation: 'fade-in 0.5s ease-out' }}>
          <div style={{ fontSize: '0.8rem', fontWeight: 800, color: 'var(--c-purple)', marginBottom: 12, textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: 8 }}>
            ⚖️ Judge Verdict
            <span style={{ 
              fontSize: '0.65rem', padding: '2px 6px', borderRadius: 4, 
              background: judgeRca.confidence === 'high' ? 'var(--c-green-bg)' : 'var(--c-yellow-bg)',
              color: judgeRca.confidence === 'high' ? 'var(--c-green)' : 'var(--c-yellow)'
            }}>
              {judgeRca.confidence.toUpperCase()} CONFIDENCE
            </span>
          </div>
          
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: '0.7rem', color: 'var(--c-text-dim)', marginBottom: 4, fontWeight: 700 }}>ROOT CAUSE:</div>
            <div className="corvin-md" style={{ fontSize: '0.8rem', color: 'var(--c-text)', fontFamily: 'var(--font-body)', lineHeight: 1.5 }}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{typedRootCause}</ReactMarkdown>
            </div>
          </div>
          
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: '0.7rem', color: 'var(--c-text-dim)', marginBottom: 4, fontWeight: 700 }}>SUMMARY:</div>
            <div className="corvin-md" style={{ fontSize: '0.8rem', color: 'var(--c-text)', fontFamily: 'var(--font-body)', lineHeight: 1.5 }}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{typedSummary}</ReactMarkdown>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
            <button onClick={onClose} style={{
              padding: '6px 12px', borderRadius: 6, border: '1px solid var(--c-border-hi)',
              background: 'transparent', color: 'var(--c-text-dim)', cursor: 'pointer',
              fontSize: '0.75rem', fontWeight: 600
            }}>
              Dismiss
            </button>
            <button onClick={handleApply} style={{
              padding: '6px 16px', borderRadius: 6, border: 'none',
              background: 'var(--c-purple)', color: 'white', cursor: 'pointer',
              fontSize: '0.75rem', fontWeight: 700, boxShadow: '0 2px 8px rgba(168, 85, 247, 0.3)'
            }}>
              Apply RCA to Investigation
            </button>
          </div>
        </div>
      )}
    </div>
  )

  if (isExpanded) {
    return (
      <div style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(5px)',
        zIndex: 9999, padding: '40px', display: 'flex',
        alignItems: 'center', justifyContent: 'center'
      }}>
        {content}
      </div>
    )
  }

  return (
    <div style={{ marginBottom: 24 }}>
      {content}
    </div>
  )
}
