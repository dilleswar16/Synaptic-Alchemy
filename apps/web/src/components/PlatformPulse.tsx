import { useState, useEffect } from 'react'

const PULSE_EVENTS = [
  "Corvin: Monitoring APIM 4xx rates for fundapis",
  "Intelligence: Trend analysis detected slight memory growth in fundsso",
  "Storage: Persistence layer synced 47 investigations",
  "Corvin: Ready to investigate partnerapis JWT failures",
  "Knowledge: CHAD Site Map updated with latest AKS topology",
  "System: Daily Briefing narrative generated via GPT-4.1",
  "Audit: 3 approvals pending in the operations queue",
  "Corvin: Correlating Elastic logs with APIM latency spikes",
]

export function PlatformPulse() {
  const [index, setIndex] = useState(0)
  const [visible, setVisible] = useState(true)

  useEffect(() => {
    const timer = setInterval(() => {
      setVisible(false)
      setTimeout(() => {
        setIndex((prev) => (prev + 1) % PULSE_EVENTS.length)
        setVisible(true)
      }, 500)
    }, 5000)
    return () => clearInterval(timer)
  }, [])

  return (
    <div style={{
      background: 'var(--c-surface-2)',
      border: '1px solid var(--c-border)',
      borderRadius: 6,
      padding: '6px 14px',
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      height: 32,
      overflow: 'hidden',
      marginBottom: 16
    }}>
      <span className="animate-pulse-glow" style={{ 
        width: 6, height: 6, borderRadius: '50%', background: 'var(--c-signal)', flexShrink: 0 
      }} />
      <span style={{ 
        fontFamily: 'var(--font-mono)', 
        fontSize: '0.7rem', 
        color: 'var(--c-signal)', 
        textTransform: 'uppercase',
        fontWeight: 700,
        letterSpacing: '0.1em'
      }}>
        Pulse
      </span>
      <div style={{ 
        fontFamily: 'var(--font-mono)', 
        fontSize: '0.68rem', 
        color: 'var(--c-text-muted)',
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateY(0)' : 'translateY(10px)',
        transition: 'all 0.5s ease',
        whiteSpace: 'nowrap',
        textOverflow: 'ellipsis',
        overflow: 'hidden'
      }}>
        {PULSE_EVENTS[index]}
      </div>
    </div>
  )
}
