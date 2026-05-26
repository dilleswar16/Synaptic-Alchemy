import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { investigatePredictiveAlert, type PredictiveAlert } from '../api/client'
import { timeAgo } from '../utils/time'

function getSeverityColor(s: string) {
  switch (s) {
    case 'critical': return 'var(--c-red)'
    case 'high': return 'var(--c-warning)'
    case 'medium': return '#e0a040'
    default: return 'var(--c-info)'
  }
}

function getConfidenceColor(c: string) {
  switch (c) {
    case 'high': return 'var(--c-green)'
    case 'medium': return 'var(--c-warning)'
    default: return 'var(--c-info)'
  }
}

interface Props {
  alert: PredictiveAlert | null
  open: boolean
  onClose: () => void
}

export function SignalDetailDrawer({ alert, open, onClose }: Props) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const overlayRef = useRef<HTMLDivElement>(null)

  const mutation = useMutation({
    mutationFn: (id: string) => investigatePredictiveAlert(id),
    onSuccess: (payload) => {
      queryClient.invalidateQueries({ queryKey: ['predictive-alerts'] })
      onClose()
      navigate(`/investigations/${payload.request_id}`)
    },
  })

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  // Close on overlay click
  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === overlayRef.current) onClose()
  }

  if (!open || !alert) return null

  const sevColor = getSeverityColor(alert.severity)
  const confColor = getConfidenceColor(alert.confidence)
  const signalPct = Math.min((alert.signal_value / alert.threshold_value) * 100, 100)

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        background: 'rgba(0,0,0,0.5)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        justifyContent: 'flex-end',
        animation: 'drawer-fade-in 0.2s ease-out',
      }}
    >
      <div
        style={{
          width: 440,
          maxWidth: '92vw',
          height: '100%',
          background: 'var(--c-surface)',
          borderLeft: '1px solid var(--c-border-hi)',
          boxShadow: '-8px 0 40px rgba(0,0,0,0.3)',
          overflowY: 'auto',
          animation: 'drawer-slide-in 0.25s ease-out',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Header */}
        <div style={{
          padding: '20px 24px 16px',
          borderBottom: `2px solid ${sevColor}`,
          background: `linear-gradient(135deg, color-mix(in srgb, ${sevColor} 8%, var(--c-surface)) 0%, var(--c-surface) 100%)`,
          position: 'sticky',
          top: 0,
          zIndex: 1,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
            <div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--c-text-muted)', marginBottom: 4 }}>
                Signal Detail
              </div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '1.3rem', color: sevColor, letterSpacing: '-0.02em' }}>
                {alert.service_name.toUpperCase()}
              </div>
            </div>
            <button
              onClick={onClose}
              style={{
                background: 'none',
                border: '1px solid var(--c-border)',
                borderRadius: 6,
                color: 'var(--c-text-muted)',
                cursor: 'pointer',
                padding: '4px 8px',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.72rem',
              }}
            >
              ESC ✕
            </button>
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.62rem', fontWeight: 700,
              padding: '2px 8px', borderRadius: 999, border: `1px solid ${sevColor}`,
              color: sevColor, textTransform: 'uppercase',
            }}>
              {alert.severity}
            </span>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.62rem', fontWeight: 700,
              padding: '2px 8px', borderRadius: 999, border: `1px solid ${confColor}`,
              color: confColor, textTransform: 'uppercase',
            }}>
              {alert.confidence} confidence
            </span>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.62rem',
              padding: '2px 8px', borderRadius: 999,
              background: 'var(--c-surface-2)', color: 'var(--c-text-muted)',
            }}>
              {alert.alert_type.replace(/_/g, ' ')}
            </span>
          </div>
        </div>

        {/* Body */}
        <div style={{ padding: '20px 24px', flex: 1 }}>

          {/* Title */}
          <div style={{
            fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '1rem',
            color: 'var(--c-text)', lineHeight: 1.4, marginBottom: 16,
          }}>
            {alert.title}
          </div>

          {/* Signal vs Threshold Gauge */}
          <div style={{
            background: 'var(--c-surface-2)', borderRadius: 10, padding: '14px 16px',
            border: '1px solid var(--c-border)', marginBottom: 16,
          }}>
            <div style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.62rem', textTransform: 'uppercase',
              letterSpacing: '0.1em', color: 'var(--c-text-muted)', marginBottom: 10,
            }}>
              Signal vs Threshold
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '1.1rem', color: sevColor }}>
                {alert.signal_value.toFixed(1)}%
              </span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--c-text-muted)' }}>
                / {alert.threshold_value.toFixed(1)}%
              </span>
            </div>
            <div style={{
              height: 8, borderRadius: 999, background: 'var(--c-surface-3)',
              overflow: 'hidden', position: 'relative',
            }}>
              <div style={{
                height: '100%', borderRadius: 999,
                width: `${signalPct}%`,
                background: `linear-gradient(90deg, ${sevColor}, color-mix(in srgb, ${sevColor} 70%, var(--c-warning)))`,
                transition: 'width 0.5s ease',
              }} />
              {/* Threshold marker */}
              <div style={{
                position: 'absolute', top: -3, bottom: -3, left: '100%',
                width: 2, background: 'var(--c-red)', borderRadius: 999,
                boxShadow: '0 0 6px var(--c-red)',
              }} />
            </div>
            <div style={{
              display: 'flex', justifyContent: 'space-between', marginTop: 4,
              fontFamily: 'var(--font-mono)', fontSize: '0.58rem', color: 'var(--c-text-faint)',
            }}>
              <span>0%</span>
              <span style={{ color: 'var(--c-red)' }}>threshold</span>
            </div>
          </div>

          {/* ETA */}
          <div style={{
            background: 'var(--c-surface-2)', borderRadius: 10, padding: '14px 16px',
            border: '1px solid var(--c-border)', marginBottom: 16,
          }}>
            <div style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.62rem', textTransform: 'uppercase',
              letterSpacing: '0.1em', color: 'var(--c-text-muted)', marginBottom: 8,
            }}>
              Breach Forecast
            </div>
            {alert.estimated_breach_at ? (
              <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '1rem', color: 'var(--c-red)' }}>
                {new Date(alert.estimated_breach_at).toLocaleString()}
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: 'var(--c-green)', boxShadow: '0 0 6px var(--c-green)',
                }} />
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.85rem', color: 'var(--c-green)' }}>
                  No breach projected
                </span>
              </div>
            )}
          </div>

          {/* Rationale */}
          <div style={{
            background: 'var(--c-surface-2)', borderRadius: 10, padding: '14px 16px',
            border: '1px solid var(--c-border)', marginBottom: 16,
          }}>
            <div style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.62rem', textTransform: 'uppercase',
              letterSpacing: '0.1em', color: 'var(--c-text-muted)', marginBottom: 8,
            }}>
              Analysis Rationale
            </div>
            <div style={{
              fontFamily: 'var(--font-body)', fontSize: '0.82rem', color: 'var(--c-text-dim)',
              lineHeight: 1.6, whiteSpace: 'pre-wrap',
            }}>
              {alert.rationale}
            </div>
          </div>

          {/* Summary */}
          <div style={{
            background: 'var(--c-surface-2)', borderRadius: 10, padding: '14px 16px',
            border: '1px solid var(--c-border)', marginBottom: 16,
          }}>
            <div style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.62rem', textTransform: 'uppercase',
              letterSpacing: '0.1em', color: 'var(--c-text-muted)', marginBottom: 8,
            }}>
              Summary
            </div>
            <div style={{
              fontFamily: 'var(--font-body)', fontSize: '0.82rem', color: 'var(--c-text-dim)',
              lineHeight: 1.6,
            }}>
              {alert.summary}
            </div>
          </div>

          {/* Metadata grid */}
          <div style={{
            display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10,
            marginBottom: 20,
          }}>
            {[
              { label: 'Confidence', value: `${alert.confidence_pct?.toFixed(0) ?? '—'}%` },
              { label: 'Related Signals', value: `${alert.related_count}` },
              { label: 'Environment', value: alert.environment },
              { label: 'Detected', value: timeAgo(alert.created_at) },
            ].map((m) => (
              <div key={m.label} style={{
                background: 'var(--c-surface-2)', borderRadius: 8, padding: '10px 12px',
                border: '1px solid var(--c-border)',
              }}>
                <div style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.58rem', textTransform: 'uppercase',
                  letterSpacing: '0.1em', color: 'var(--c-text-faint)', marginBottom: 4,
                }}>
                  {m.label}
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.85rem', color: 'var(--c-text)' }}>
                  {m.value}
                </div>
              </div>
            ))}
          </div>

          {/* Change Correlation (if present) */}
          {alert.change_correlation && (
            <div style={{
              background: 'color-mix(in srgb, var(--c-signal) 8%, var(--c-surface-2))',
              borderRadius: 10, padding: '14px 16px',
              border: '1px solid color-mix(in srgb, var(--c-signal) 30%, var(--c-border))',
              marginBottom: 16,
            }}>
              <div style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.62rem', textTransform: 'uppercase',
                letterSpacing: '0.1em', color: 'var(--c-signal)', marginBottom: 8,
              }}>
                Change Correlation
              </div>
              <div style={{
                fontFamily: 'var(--font-body)', fontSize: '0.82rem', color: 'var(--c-text)',
                lineHeight: 1.5,
              }}>
                {alert.change_correlation}
              </div>
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div style={{
          padding: '16px 24px', borderTop: '1px solid var(--c-border)',
          background: 'var(--c-surface-2)',
          display: 'flex', gap: 10,
          position: 'sticky', bottom: 0,
        }}>
          <button
            className="btn btn-primary"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate(alert.id)}
            style={{ flex: 1, fontSize: '0.78rem', fontWeight: 700 }}
          >
            {mutation.isPending ? 'Investigating…' : 'Investigate This Signal'}
          </button>
          {alert.source_request_id && (
            <button
              className="btn"
              onClick={() => { onClose(); navigate(`/investigations/${alert.source_request_id}`) }}
              style={{ fontSize: '0.72rem' }}
            >
              View Source
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
