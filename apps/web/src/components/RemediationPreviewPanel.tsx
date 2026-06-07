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
    return (
      <div className="panel scan-sweep" style={{ minHeight: 220, padding: '22px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <div style={{ height: 12, width: 120, background: 'var(--c-border-hi)', borderRadius: 3, marginBottom: 8 }} />
            <div style={{ height: 18, width: 200, background: 'var(--c-border-hi)', borderRadius: 4 }} />
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            {[1, 2, 3].map(i => (
              <div key={i} style={{ height: 50, width: 70, background: 'var(--c-border-hi)', borderRadius: 8 }} />
            ))}
          </div>
        </div>
        <div style={{ height: 80, width: '100%', background: 'var(--c-border)', borderRadius: 8 }} />
      </div>
    )
  }
  if (!data) return null

  return (
    <div className="panel animate-fade-up" style={{ padding: '22px 24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', marginBottom: 18 }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: '0.75rem', letterSpacing: '0.03em', textTransform: 'uppercase', color: 'var(--c-text-muted)', marginBottom: 5 }}>
            Remediation Preview
          </div>
          <div style={{ fontWeight: 700, fontSize: '1.125rem', color: 'var(--c-text)' }}>
            What Corvin Will Run
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ padding: '10px 12px', borderRadius: 8, border: '1px solid var(--c-border)', background: 'var(--c-surface-2)' }}>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.65rem', letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--c-text-faint)', marginBottom: 3 }}>Replicas</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '1rem', color: 'var(--c-text)' }}>{data.current_replica_count}</div>
          </div>
          <div style={{ padding: '10px 12px', borderRadius: 8, border: '1px solid var(--c-border)', background: 'var(--c-surface-2)' }}>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.65rem', letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--c-text-faint)', marginBottom: 3 }}>Throttle</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '1rem', color: 'var(--c-signal)' }}>{data.cpu_throttle_events_per_min}/min</div>
          </div>
          <div style={{ padding: '10px 12px', borderRadius: 8, border: '1px solid var(--c-border)', background: 'var(--c-surface-2)' }}>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.65rem', letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--c-text-faint)', marginBottom: 3 }}>Restarts</div>
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
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.8rem', color: 'var(--c-text)' }}>{item.title}</div>
                  {item.target_service && (
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', padding: '1px 7px', borderRadius: 4, background: 'color-mix(in srgb, var(--c-signal) 10%, transparent)', border: '1px solid var(--c-border)', color: 'var(--c-signal)' }}>
                      → {item.target_namespace ? `${item.target_namespace}/` : ''}{item.target_service}
                    </span>
                  )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: accent }}>{item.action_type}</div>
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.56rem',
                    padding: '1px 7px', borderRadius: 4,
                    background: item.action_type.toLowerCase() === 'manual'
                      ? 'color-mix(in srgb, #f59e0b 12%, transparent)'
                      : 'color-mix(in srgb, var(--c-green) 12%, transparent)',
                    border: `1px solid ${item.action_type.toLowerCase() === 'manual' ? '#f59e0b33' : 'var(--c-success-border)'}`,
                    color: item.action_type.toLowerCase() === 'manual' ? '#f59e0b' : 'var(--c-green)',
                  }}>
                    {item.action_type.toLowerCase() === 'manual' ? '👤 Human' : '⚡ Auto'}
                  </span>
                </div>
              </div>
              <details style={{ background: 'var(--c-surface)' }}>
                <summary style={{
                  cursor: 'pointer', fontFamily: 'var(--font-display)',
                  fontSize: '0.7rem', fontWeight: 700, color: 'var(--c-text-muted)',
                  listStyle: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                  padding: '8px 0', borderBottom: '1px solid var(--c-border)'
                }}>
                  <span style={{ fontSize: '0.6rem' }}>▼</span> View Code & State Diffs
                </summary>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 1, background: 'var(--c-border)' }}>
                  {[
                    ['Current State', item.current_state],
                    ['Proposed Command', item.proposed_command],
                    ['After State', item.predicted_after_state],
                  ].map(([label, value], i) => (
                    <div key={i} style={{ padding: '14px 14px 16px', background: 'var(--c-surface)' }}>
                      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.65rem', letterSpacing: '0.12em', textTransform: 'uppercase', color: i === 1 ? accent : 'var(--c-text-faint)', marginBottom: 8 }}>{label}</div>
                      <div style={{ fontFamily: i === 1 ? 'var(--font-mono)' : 'var(--font-body)', fontSize: '0.76rem', color: 'var(--c-text-dim)', lineHeight: 1.7 }}>{value}</div>
                    </div>
                  ))}
                </div>
                {item.operator_notes.length > 0 && (
                  <div style={{ padding: '12px 14px', background: 'color-mix(in srgb, var(--c-signal) 6%, var(--c-surface-2))', borderTop: '1px solid var(--c-border)' }}>
                    <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.65rem', letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--c-text-faint)', marginBottom: 6 }}>Operator Notes</div>
                    {item.operator_notes.map((note, noteIndex) => (
                      <div key={noteIndex} style={{ fontFamily: 'var(--font-body)', fontSize: '0.74rem', color: 'var(--c-text-muted)', lineHeight: 1.6 }}>{note}</div>
                    ))}
                  </div>
                )}
              </details>
            </div>
          )
        })}
      </div>
    </div>
  )
}