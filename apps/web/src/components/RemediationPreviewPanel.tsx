import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchFixPreview } from '../api/client'

export function previewSeenKey(requestId: string) {
  return `corvin-preview-viewed:${requestId}`
}

const RISK_COLOR: Record<string, string> = {
  high: 'var(--c-red)',
  medium: 'var(--c-yellow)',
  low: 'var(--c-green)',
}

export function RemediationPreviewPanel({ requestId }: { requestId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['fix-preview', requestId],
    queryFn: () => fetchFixPreview(requestId),
    enabled: !!requestId,
  })

  useEffect(() => {
    if (!data) return
    window.sessionStorage.setItem(previewSeenKey(requestId), new Date().toISOString())
  }, [data, requestId])

  if (isLoading) {
    return <div className="panel scan-sweep" style={{ minHeight: 220 }} />
  }
  if (!data) return null

  return (
    <div className="panel animate-fade-up" style={{ padding: '22px 24px', background: 'linear-gradient(180deg, var(--c-surface) 0%, color-mix(in srgb, var(--c-signal) 3%, var(--c-surface)) 100%)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', marginBottom: 18 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.64rem', letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--c-signal)', marginBottom: 5 }}>
            Remediation Preview
          </div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '1.3rem', color: 'var(--c-text)' }}>
            What Corvin Will Run
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ padding: '10px 12px', borderRadius: 8, border: '1px solid var(--c-border)', background: 'var(--c-surface-2)' }}>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.54rem', letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--c-text-faint)', marginBottom: 3 }}>Replicas</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '1rem', color: 'var(--c-text)' }}>{data.current_replica_count}</div>
          </div>
          <div style={{ padding: '10px 12px', borderRadius: 8, border: '1px solid var(--c-border)', background: 'var(--c-surface-2)' }}>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.54rem', letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--c-text-faint)', marginBottom: 3 }}>Throttle</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '1rem', color: 'var(--c-signal)' }}>{data.cpu_throttle_events_per_min}/min</div>
          </div>
          <div style={{ padding: '10px 12px', borderRadius: 8, border: '1px solid var(--c-border)', background: 'var(--c-surface-2)' }}>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.54rem', letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--c-text-faint)', marginBottom: 3 }}>Restarts</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '1rem', color: 'var(--c-yellow)' }}>{data.restart_count}</div>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gap: 14 }}>
        {data.items.map((item, index) => {
          const accent = RISK_COLOR[item.risk_level] ?? 'var(--c-signal)'
          return (
            <div key={`${item.title}-${index}`} style={{ borderRadius: 12, overflow: 'hidden', border: `1px solid color-mix(in srgb, ${accent} 30%, var(--c-border-hi))` }}>
              <div style={{ padding: '10px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, background: 'var(--c-surface-2)', borderBottom: '1px solid var(--c-border)' }}>
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.8rem', color: 'var(--c-text)' }}>{item.title}</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: accent }}>{item.action_type}</div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 1, background: 'var(--c-border)' }}>
                {[
                  ['Current State', item.current_state],
                  ['Proposed Command', item.proposed_command],
                  ['After State', item.predicted_after_state],
                ].map(([label, value], i) => (
                  <div key={i} style={{ padding: '14px 14px 16px', background: 'var(--c-surface)' }}>
                    <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.54rem', letterSpacing: '0.12em', textTransform: 'uppercase', color: i === 1 ? accent : 'var(--c-text-faint)', marginBottom: 8 }}>{label}</div>
                    <div style={{ fontFamily: i === 1 ? 'var(--font-mono)' : 'var(--font-body)', fontSize: '0.76rem', color: 'var(--c-text-dim)', lineHeight: 1.7 }}>{value}</div>
                  </div>
                ))}
              </div>
              {item.operator_notes.length > 0 && (
                <div style={{ padding: '12px 14px', background: 'color-mix(in srgb, var(--c-signal) 6%, var(--c-surface-2))', borderTop: '1px solid var(--c-border)' }}>
                  <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.54rem', letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--c-text-faint)', marginBottom: 6 }}>Operator Notes</div>
                  {item.operator_notes.map((note, noteIndex) => (
                    <div key={noteIndex} style={{ fontFamily: 'var(--font-body)', fontSize: '0.74rem', color: 'var(--c-text-muted)', lineHeight: 1.6 }}>{note}</div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}