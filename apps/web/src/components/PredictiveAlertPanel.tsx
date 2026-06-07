import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { fetchPredictiveAlerts, investigatePredictiveAlert, type PredictiveAlert } from '../api/client'

const SEVERITY_COLOR: Record<string, string> = {
  critical: 'var(--c-red)',
  high: 'var(--c-signal)',
  medium: 'var(--c-yellow)',
  low: 'var(--c-green)',
}

type AlertState = 'breached' | 'near' | 'watch' | 'early'

function toNumber(value: unknown): number {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

function getAlertState(signal: number, target: number): AlertState {
  const safeTarget = Math.max(target, 1)
  if (signal >= safeTarget) return 'breached'
  if (signal >= safeTarget * 0.9) return 'near'
  if (signal >= safeTarget * 0.6) return 'watch'
  return 'early'
}

function stateMeta(state: AlertState) {
  if (state === 'breached') {
    return {
      label: 'Action Recommended',
      chipBg: 'var(--c-error-bg)',
      chipBorder: 'var(--c-error-border)',
      chipText: 'var(--c-red)',
      helper: 'Signal is above the configured threshold.',
    }
  }
  if (state === 'near') {
    return {
      label: 'Near Threshold',
      chipBg: 'var(--c-warning-bg)',
      chipBorder: 'var(--c-warning-border)',
      chipText: 'var(--c-warning)',
      helper: 'Signal is approaching threshold and should be reviewed soon.',
    }
  }
  if (state === 'watch') {
    return {
      label: 'Watch',
      chipBg: 'var(--c-info-bg)',
      chipBorder: 'var(--c-info-border)',
      chipText: 'var(--c-info)',
      helper: 'Signal is below threshold but trending in a risky direction.',
    }
  }
  return {
    label: 'Early Signal',
    chipBg: 'var(--c-surface)',
    chipBorder: 'var(--c-border-hi)',
    chipText: 'var(--c-text-muted)',
    helper: 'Low-confidence early pattern. Keep monitoring.',
  }
}

function formatAlertTitle(alert: PredictiveAlert, state: AlertState): string {
  if (alert.alert_type !== 'memory_pressure') return alert.title
  if (state === 'breached') return 'Memory threshold breached'
  if (state === 'near') return 'Memory near threshold'
  if (state === 'watch') return 'Memory building'
  return 'Memory trending up'
}

export function PredictiveAlertPanel() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [openingAlertId, setOpeningAlertId] = useState<string | null>(null)
  const { data, isLoading } = useQuery({
    queryKey: ['predictive-alerts'],
    queryFn: () => fetchPredictiveAlerts(true),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  const mutation = useMutation({
    mutationFn: (id: string) => investigatePredictiveAlert(id),
    onSuccess: (payload) => {
      queryClient.invalidateQueries({ queryKey: ['predictive-alerts'] })
      navigate(`/investigations/${payload.request_id}`)
    },
  })

  if (isLoading) {
    return (
      <div className="panel animate-fade-up" style={{ padding: '18px 20px', overflow: 'hidden', position: 'relative' }}>
        <div style={{ position: 'relative' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '0.75rem', letterSpacing: '0.03em', textTransform: 'uppercase', color: 'var(--c-text-muted)', marginBottom: 5 }}>
            Pre-Mortem Mode
          </div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '1.125rem', color: 'var(--c-text)', letterSpacing: '-0.01em', marginBottom: 18 }}>
            Predictive Detections
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[0, 1, 2].map(i => (
            <div key={i} style={{
              borderRadius: 8, padding: '16px 16px 14px', animationDelay: `${i * 80}ms`,
              border: '1px solid var(--c-border-hi)', background: 'var(--c-surface-2)',
              display: 'flex', flexDirection: 'column', gap: 8,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{
                  width: 10, height: 10, borderRadius: '50%', background: 'var(--c-signal)',
                  animation: 'pulse-glow 1.2s ease-in-out infinite', animationDelay: `${i * 200}ms`,
                  boxShadow: '0 0 6px var(--c-signal)',
                }} />
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--c-text-muted)' }}>
                  Scanning for predictive signals
                  <span style={{ animation: 'blink 1s step-end infinite' }}>...</span>
                </span>
              </div>
              <div style={{ height: 10, borderRadius: 4, background: 'var(--c-border-hi)', width: `${60 + i * 15}%`, overflow: 'hidden', position: 'relative' }}>
                <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(90deg, transparent, rgba(13,148,136,0.4), transparent)', animation: 'shimmerSlide 1.5s ease-in-out infinite', animationDelay: `${i * 200}ms` }} />
              </div>
              <div style={{ height: 8, borderRadius: 4, background: 'var(--c-border-hi)', width: '40%' }} />
            </div>
          ))}
        </div>
      </div>
    )
  }

  const alerts = (data ?? []).slice(0, 3)
  const enrichedAlerts = alerts.map((alert) => {
    const signal = toNumber(alert.signal_value)
    const target = Math.max(toNumber(alert.threshold_value), 1)
    const state = getAlertState(signal, target)
    const ratioPct = Math.max(0, Math.min((signal / target) * 100, 130))
    return { alert, signal, target, state, ratioPct }
  })
  const actionableCount = enrichedAlerts.filter((a) => a.state === 'breached' || a.state === 'near').length
  const watchCount = enrichedAlerts.length - actionableCount

  function handlePrimaryAction(alertId: string, state: AlertState) {
    if (state === 'breached' || state === 'near') {
      mutation.mutate(alertId)
      return
    }

    setOpeningAlertId(alertId)
    navigate('/predictive-analytics')
  }

  return (
    <div className="panel animate-fade-up" style={{ padding: '18px 20px', overflow: 'hidden', position: 'relative' }}>
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        background: 'radial-gradient(circle at 85% 10%, var(--c-signal-glow), transparent 35%)',
      }} />
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '0.75rem', letterSpacing: '0.03em', textTransform: 'uppercase', color: 'var(--c-text-muted)', marginBottom: 5 }}>
            Pre-Mortem Mode
          </div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '1.125rem', color: 'var(--c-text)', letterSpacing: '-0.01em' }}>
            Predictive Detections
          </div>
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text-faint)' }}>
          {alerts.length} live signal{alerts.length !== 1 ? 's' : ''}
        </div>
      </div>

      {alerts.length > 0 && (
        <div style={{
          marginBottom: 14,
          display: 'flex',
          gap: 8,
          flexWrap: 'wrap',
        }}>
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.68rem',
            color: actionableCount > 0 ? 'var(--c-error)' : 'var(--c-text-muted)',
            padding: '4px 10px',
            borderRadius: 999,
            border: `1px solid ${actionableCount > 0 ? 'var(--c-error-border)' : 'var(--c-border)'}`,
            background: actionableCount > 0 ? 'var(--c-error-bg)' : 'var(--c-surface-2)',
          }}>
            {actionableCount} actionable
          </span>
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.68rem',
            color: 'var(--c-info)',
            padding: '4px 10px',
            borderRadius: 999,
            border: '1px solid var(--c-info-border)',
            background: 'var(--c-info-bg)',
          }}>
            {watchCount} watch
          </span>
        </div>
      )}

      {alerts.length === 0 && (
        <div style={{
          padding: '20px 18px', borderRadius: 6,
          border: '1px solid var(--c-border-hi)', background: 'var(--c-surface-2)',
          fontFamily: 'var(--font-mono)', fontSize: '0.74rem', color: 'var(--c-text-muted)',
        }}>
          No predictive signals are active. Corvin is continuously watching for error acceleration, memory pressure, and restart instability.
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
        {enrichedAlerts.map(({ alert, signal, target, state, ratioPct }, index) => {
          const accent = SEVERITY_COLOR[alert.severity] ?? 'var(--c-signal)'
          const meta = stateMeta(state)
          const dynamicTitle = formatAlertTitle(alert, state)
          const isPremortem = state === 'watch' || state === 'early'
          const ctaLabel = state === 'breached' || state === 'near' ? 'Investigate' : 'Pre-Mortem'
          const ctaBg = state === 'breached' || state === 'near' ? 'var(--c-signal)' : 'var(--c-surface)'
          const ctaText = state === 'breached' || state === 'near' ? '#fff' : 'var(--c-text)'
          const ctaBorder = state === 'breached' || state === 'near' ? '1px solid transparent' : '1px solid var(--c-border-hi)'
          const isOpening = openingAlertId === alert.id
          const isDisabled = mutation.isPending || isOpening

          return (
            <div key={alert.id} className="scan-sweep" style={{
              animationDelay: `${index * 70}ms`,
              border: `1px solid color-mix(in srgb, ${accent} 35%, var(--c-border-hi))`,
              background: `linear-gradient(180deg, color-mix(in srgb, ${accent} 10%, transparent) 0%, var(--c-surface-2) 100%)`,
              borderRadius: 8, padding: '12px 14px',
              boxShadow: `0 12px 30px color-mix(in srgb, ${accent} 18%, transparent)`,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
                <span style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.64rem',
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  color: meta.chipText,
                  padding: '3px 8px',
                  borderRadius: 999,
                  border: `1px solid ${meta.chipBorder}`,
                  background: meta.chipBg,
                }}>
                  {meta.label}
                </span>
                <span style={{
                  fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.64rem',
                  letterSpacing: '0.16em', textTransform: 'uppercase', color: accent,
                }}>
                  {alert.alert_type.replace(/_/g, ' ')}
                </span>
              </div>

              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.95rem', color: 'var(--c-text)', marginBottom: 8, lineHeight: 1.2 }}>
                {dynamicTitle}
              </div>

              <div style={{ marginBottom: 10 }}>
                <div style={{
                  position: 'relative',
                  height: 6,
                  borderRadius: 999,
                  background: 'var(--c-surface)',
                  border: '1px solid var(--c-border)',
                  overflow: 'hidden',
                }}>
                  <div style={{
                    position: 'absolute',
                    left: 0,
                    top: 0,
                    bottom: 0,
                    width: `${ratioPct}%`,
                    background: `linear-gradient(90deg, color-mix(in srgb, ${accent} 55%, transparent), ${accent})`,
                    transition: 'width 0.35s ease',
                  }} />
                  <div style={{
                    position: 'absolute',
                    left: '100%',
                    top: -2,
                    width: 2,
                    height: 10,
                    transform: 'translateX(-2px)',
                    background: 'var(--c-text-faint)',
                    opacity: 0.5,
                  }} />
                </div>
                <div style={{
                  marginTop: 4,
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.62rem',
                  color: 'var(--c-text-faint)',
                }}>
                  <span>{signal.toFixed(1)}% / {target.toFixed(1)}%</span>
                  <span>{alert.service_name}</span>
                </div>
              </div>

              <button
                disabled={isDisabled}
                onClick={() => handlePrimaryAction(alert.id, state)}
                style={{
                  width: '100%',
                  justifyContent: 'center',
                  display: 'inline-flex',
                  alignItems: 'center',
                  borderRadius: 6,
                  fontFamily: 'var(--font-display)',
                  fontWeight: 700,
                  fontSize: '0.8rem',
                  letterSpacing: '-0.01em',
                  padding: '8px 12px',
                  background: ctaBg,
                  color: ctaText,
                  border: ctaBorder,
                  transition: 'all 0.15s ease',
                  cursor: isDisabled ? 'not-allowed' : 'pointer',
                  opacity: isDisabled ? 0.7 : 1,
                }}
              >
                {isPremortem && isOpening ? 'Opening Pre-Mortem…' : mutation.isPending ? 'Starting...' : ctaLabel}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}