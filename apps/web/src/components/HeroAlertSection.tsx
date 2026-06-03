import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { investigatePredictiveAlert, type PredictiveAlert } from '../api/client'

function etaMinutes(eta: string | null): number | null {
  if (!eta) return null
  const diff = (new Date(eta).getTime() - Date.now()) / 60000
  return Number.isFinite(diff) ? diff : null
}

function formatCountdown(eta: string | null): { hours: number; minutes: number; seconds: number } {
  const mins = etaMinutes(eta)
  if (mins == null || mins <= 0) return { hours: 0, minutes: 0, seconds: 0 }
  const totalSeconds = Math.max(0, Math.floor(mins * 60))
  return {
    hours: Math.floor(totalSeconds / 3600),
    minutes: Math.floor((totalSeconds % 3600) / 60),
    seconds: totalSeconds % 60,
  }
}

function getSeverityColor(severity: string): string {
  if (severity === 'critical') return 'var(--c-red)'
  if (severity === 'high') return 'var(--c-warning)'
  return 'var(--c-signal)'
}

export function HeroAlertSection({ alert, loading = false }: { alert: PredictiveAlert | null; loading?: boolean }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [countdown, setCountdown] = useState(formatCountdown(alert?.estimated_breach_at ?? null))
  const [premortemLoading, setPremortemLoading] = useState(false)

  const mutation = useMutation({
    mutationFn: (id: string) => investigatePredictiveAlert(id),
    onSuccess: (payload) => {
      queryClient.invalidateQueries({ queryKey: ['predictive-alerts'] })
      navigate(`/investigations/${payload.request_id}`)
    },
  })

  useEffect(() => {
    if (!alert) return
    const timer = setInterval(() => {
      setCountdown(formatCountdown(alert.estimated_breach_at))
    }, 1000)
    return () => clearInterval(timer)
  }, [alert])

  if (loading) {
    return (
      <div
        style={{
          position: 'relative',
          overflow: 'hidden',
          borderRadius: 12,
          marginBottom: 24,
          background: 'linear-gradient(135deg, var(--c-surface-2) 0%, var(--c-surface) 100%)',
          border: '2px solid var(--c-border-hi)',
          padding: '28px 32px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <div className="skeleton-shimmer" style={{ height: 22, width: 140, borderRadius: 6 }} />
          <div className="skeleton-shimmer" style={{ height: 22, width: 120, borderRadius: 6 }} />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
          <div>
            <div className="skeleton-shimmer" style={{ height: 12, width: 60, borderRadius: 4, marginBottom: 8 }} />
            <div className="skeleton-shimmer" style={{ height: 20, width: 140, borderRadius: 4, marginBottom: 10 }} />
            <div className="skeleton-shimmer" style={{ height: 14, width: '90%', borderRadius: 4, marginBottom: 8 }} />
            <div className="skeleton-shimmer" style={{ height: 12, width: '60%', borderRadius: 4 }} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
            <div className="skeleton-shimmer" style={{ height: 12, width: 120, borderRadius: 4 }} />
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, width: '100%' }}>
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton-shimmer" style={{ height: 54, borderRadius: 8 }} />
              ))}
            </div>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 16 }}>
          <div className="skeleton-shimmer" style={{ height: 10, borderRadius: 999 }} />
          <div className="skeleton-shimmer" style={{ height: 10, borderRadius: 999 }} />
        </div>
        <div style={{
          position: 'absolute', bottom: 16, left: 32, right: 32,
          fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-text-faint)',
          textAlign: 'center',
        }}>
          Scanning Azure services for predictive signals…
        </div>
      </div>
    )
  }

  if (!alert) {
    return (
      <div
        style={{
          background: 'linear-gradient(135deg, var(--c-surface-2) 0%, var(--c-surface) 100%)',
          border: '1px solid var(--c-border-hi)',
          borderRadius: 12,
          padding: '32px 40px',
          marginBottom: 24,
          textAlign: 'center',
        }}
      >
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '1.2rem', color: 'var(--c-text)', marginBottom: 8 }}>
          ✓ All Systems Healthy
        </div>
        <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.9rem', color: 'var(--c-text-muted)' }}>
          No predictive breaches detected. Corvin is continuously monitoring for emerging risks.
        </div>
      </div>
    )
  }

  const severityColor = getSeverityColor(alert.severity)
  const confidenceColor = alert.confidence === 'high' ? 'var(--c-green)' : alert.confidence === 'medium' ? 'var(--c-warning)' : 'var(--c-info)'
  const mins = etaMinutes(alert.estimated_breach_at)
  const hasEta = alert.estimated_breach_at != null && mins != null && mins > 0
  const isImminentBreach = hasEta && mins <= 30

  return (
    <div
      style={{
        position: 'relative',
        overflow: 'hidden',
        borderRadius: 12,
        marginBottom: 24,
        background: `linear-gradient(135deg, color-mix(in srgb, ${severityColor} 12%, var(--c-surface-2)) 0%, var(--c-surface-2) 100%)`,
        border: `2px solid color-mix(in srgb, ${severityColor} 40%, var(--c-border-hi))`,
        boxShadow: `0 0 40px color-mix(in srgb, ${severityColor} 15%, transparent), 0 8px 32px color-mix(in srgb, ${severityColor} 10%, transparent)`,
      }}
    >
      {/* Animated glow background */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          pointerEvents: 'none',
          background: `radial-gradient(circle at 100% 0%, color-mix(in srgb, ${severityColor} 25%, transparent) 0%, transparent 50%)`,
          animation: 'pulse-glow 4s ease-in-out infinite',
        }}
      />

      <div style={{ position: 'relative', padding: '40px 48px' }}>
        {/* Top status bar */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28, flexWrap: 'wrap', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div
              style={{
                width: 16,
                height: 16,
                borderRadius: '50%',
                background: severityColor,
                boxShadow: `0 0 12px ${severityColor}`,
                animation: isImminentBreach ? 'pulse 0.5s ease-in-out infinite' : 'none',
              }}
            />
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.12em', color: severityColor }}>
              {alert.severity.toUpperCase()} ALERT
            </div>
          </div>
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.72rem',
              color: confidenceColor,
              padding: '4px 12px',
              borderRadius: 999,
              border: `1px solid ${confidenceColor}`,
              background: 'var(--c-surface)',
            }}
          >
            {alert.confidence_pct?.toFixed(0) ?? alert.confidence}% CONFIDENCE
          </div>
        </div>

        {/* Main content grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 40, alignItems: 'center', marginBottom: 32 }}>
          {/* Left: Service & Title */}
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--c-text-muted)', marginBottom: 6 }}>
              Service
            </div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '2rem', letterSpacing: '-0.02em', color: severityColor, marginBottom: 16 }}>
              {alert.service_name.toUpperCase()}
            </div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '1.1rem', color: 'var(--c-text)', lineHeight: 1.4, marginBottom: 16 }}>
              {alert.title}
            </div>
            <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.95rem', color: 'var(--c-text-dim)', lineHeight: 1.6 }}>
              Signal: <span style={{ color: severityColor, fontWeight: 700 }}>{alert.signal_value?.toFixed(1)}%</span> of threshold{' '}
              <span style={{ color: 'var(--c-text-muted)', fontWeight: 600 }}>{alert.threshold_value?.toFixed(1)}%</span>
            </div>
          </div>

          {/* Right: Dramatic countdown or "No breach projected" */}
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--c-text-muted)', marginBottom: 12 }}>
              {hasEta ? 'Time Until Breach' : 'Breach Forecast'}
            </div>
            {hasEta ? (
              <>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(3, 1fr)',
                    gap: 8,
                    marginBottom: 20,
                  }}
                >
                  {[
                    { value: countdown.hours, label: 'H' },
                    { value: countdown.minutes, label: 'M' },
                    { value: countdown.seconds, label: 'S' },
                  ].map((item, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: 'var(--c-surface)',
                        border: `2px solid color-mix(in srgb, ${severityColor} 30%, var(--c-border))`,
                        borderRadius: 8,
                        padding: '12px 8px',
                        animation: `slideInDown 0.4s ease-out ${idx * 0.1}s both`,
                      }}
                    >
                      <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 900, fontSize: '1.8rem', color: severityColor, lineHeight: 1 }}>
                        {String(item.value).padStart(2, '0')}
                      </div>
                      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', color: 'var(--c-text-muted)', marginTop: 6 }}>
                        {item.label}
                      </div>
                    </div>
                  ))}
                </div>

                {isImminentBreach && (
                  <div
                    style={{
                      fontFamily: 'var(--font-display)',
                      fontWeight: 700,
                      fontSize: '0.85rem',
                      color: 'var(--c-red)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.08em',
                      animation: 'pulse 1s ease-in-out infinite',
                    }}
                  >
                    ⚠ Breach Imminent
                  </div>
                )}
              </>
            ) : (
              <div style={{
                padding: '16px 20px',
                borderRadius: 8,
                background: 'color-mix(in srgb, var(--c-green) 8%, var(--c-surface))',
                border: '1px solid color-mix(in srgb, var(--c-green) 25%, var(--c-border))',
              }}>
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '1.1rem', color: 'var(--c-green)', marginBottom: 6 }}>
                  No Breach Projected
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-text-muted)' }}>
                  Trend is flat or declining. Signal below threshold.
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Metric bars */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 28 }}>
          {/* Signal bar */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '0.75rem', color: 'var(--c-text-muted)' }}>
                Current Signal
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.75rem', color: severityColor }}>
                {alert.signal_value?.toFixed(1)}%
              </div>
            </div>
            <div
              style={{
                position: 'relative',
                height: 12,
                borderRadius: 999,
                background: 'var(--c-surface)',
                border: `1px solid var(--c-border)`,
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  position: 'absolute',
                  left: 0,
                  top: 0,
                  bottom: 0,
                  width: `${Math.min((alert.signal_value ?? 0) / (alert.threshold_value ?? 100) * 100, 100)}%`,
                  background: `linear-gradient(90deg, color-mix(in srgb, ${severityColor} 50%, transparent), ${severityColor})`,
                  transition: 'width 0.5s ease',
                  borderRadius: 999,
                }}
              />
            </div>
          </div>

          {/* Confidence bar */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '0.75rem', color: 'var(--c-text-muted)' }}>
                Prediction Confidence
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.75rem', color: confidenceColor }}>
                {alert.confidence_pct?.toFixed(0) ?? '0'}%
              </div>
            </div>
            <div
              style={{
                position: 'relative',
                height: 12,
                borderRadius: 999,
                background: 'var(--c-surface)',
                border: `1px solid var(--c-border)`,
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  position: 'absolute',
                  left: 0,
                  top: 0,
                  bottom: 0,
                  width: `${Math.min(alert.confidence_pct ?? 0, 100)}%`,
                  background: `linear-gradient(90deg, color-mix(in srgb, ${confidenceColor} 50%, transparent), ${confidenceColor})`,
                  transition: 'width 0.5s ease',
                  borderRadius: 999,
                }}
              />
            </div>
          </div>
        </div>

        {/* Dynamic intel strip — blast radius, change correlation, related signals */}
        {(alert.blast_radius_users > 0 || alert.change_correlation || alert.related_count > 1) && (
          <div style={{
            display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 20,
            padding: '10px 14px', borderRadius: 8,
            background: 'color-mix(in srgb, var(--c-surface) 80%, var(--c-surface-3))',
            border: '1px solid var(--c-border)',
          }}>
            {alert.blast_radius_users > 0 && (
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
                color: 'var(--c-red)', fontWeight: 700,
                display: 'inline-flex', alignItems: 'center', gap: 5,
              }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>
                {alert.blast_radius_users.toLocaleString()} user-affecting errors
                {alert.blast_radius_requests > 0 && (
                  <span style={{ color: 'var(--c-text-faint)', fontWeight: 400 }}>
                    {' '}/ {alert.blast_radius_requests.toLocaleString()} total requests
                  </span>
                )}
              </span>
            )}
            {alert.change_correlation && (
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
                color: 'var(--c-warning)', fontWeight: 600,
                display: 'inline-flex', alignItems: 'center', gap: 5,
              }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
                {alert.change_correlation}
              </span>
            )}
            {alert.related_count > 1 && (
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
                color: 'var(--c-info)', fontWeight: 600,
                display: 'inline-flex', alignItems: 'center', gap: 5,
              }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>
                {alert.related_count} related signals
              </span>
            )}
          </div>
        )}

        {/* Action buttons */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <button
            disabled={mutation.isPending}
            onClick={() => mutation.mutate(alert.id)}
            style={{
              flex: isImminentBreach ? 2 : 1,
              padding: '12px 24px',
              borderRadius: 8,
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              fontSize: '0.9rem',
              letterSpacing: '-0.01em',
              textTransform: 'uppercase',
              background: severityColor,
              color: '#fff',
              border: 'none',
              cursor: mutation.isPending ? 'not-allowed' : 'pointer',
              transition: 'all 0.2s ease',
              boxShadow: `0 4px 16px color-mix(in srgb, ${severityColor} 40%, transparent)`,
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.transform = 'translateY(-2px)'
              e.currentTarget.style.boxShadow = `0 8px 24px color-mix(in srgb, ${severityColor} 50%, transparent)`
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.transform = 'translateY(0)'
              e.currentTarget.style.boxShadow = `0 4px 16px color-mix(in srgb, ${severityColor} 40%, transparent)`
            }}
          >
            {mutation.isPending ? '🔄 Launching Investigation…' : '🔍 Investigate Now'}
          </button>
          <button
            style={{
              padding: '12px 24px',
              borderRadius: 8,
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              fontSize: '0.9rem',
              letterSpacing: '-0.01em',
              textTransform: 'uppercase',
              background: 'var(--c-surface)',
              color: 'var(--c-text)',
              border: '1px solid var(--c-border-hi)',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.background = 'color-mix(in srgb, var(--c-surface) 80%, var(--c-text))'
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.background = 'var(--c-surface)'
            }}
          >
            📋 View RCA
          </button>
          <button
            style={{
              padding: '12px 24px',
              borderRadius: 8,
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              fontSize: '0.9rem',
              letterSpacing: '-0.01em',
              textTransform: 'uppercase',
              background: premortemLoading ? 'var(--c-surface-2)' : 'var(--c-surface)',
              color: premortemLoading ? 'var(--c-text-muted)' : 'var(--c-text)',
              border: '1px solid var(--c-border-hi)',
              cursor: premortemLoading ? 'not-allowed' : 'pointer',
              transition: 'all 0.2s ease',
              opacity: premortemLoading ? 0.6 : 1,
            }}
            onClick={() => {
              setPremortemLoading(true)
              navigate('/predictive-analytics')
            }}
            disabled={premortemLoading}
            onMouseOver={(e) => {
              if (!premortemLoading) {
                e.currentTarget.style.background = 'color-mix(in srgb, var(--c-surface) 80%, var(--c-text))'
              }
            }}
            onMouseOut={(e) => {
              if (!premortemLoading) {
                e.currentTarget.style.background = 'var(--c-surface)'
              }
            }}
          >
            {premortemLoading ? (
              <span style={{ display: 'inline-block', animation: 'spin 0.8s linear infinite' }}>⏳</span>
            ) : (
              '⚗️ Pre-Mortem'
            )}
          </button>
        </div>
      </div>

      <style>{`
        @keyframes pulse-glow {
          0%, 100% { opacity: 0.4; }
          50% { opacity: 0.8; }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.6; }
        }
        @keyframes slideInDown {
          from {
            opacity: 0;
            transform: translateY(-20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
