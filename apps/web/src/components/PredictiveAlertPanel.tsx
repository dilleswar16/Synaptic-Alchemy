import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { fetchPredictiveAlerts, investigatePredictiveAlert } from '../api/client'

const SEVERITY_COLOR: Record<string, string> = {
  critical: 'var(--c-red)',
  high: 'var(--c-signal)',
  medium: 'var(--c-yellow)',
  low: 'var(--c-green)',
}

function etaLabel(eta: string | null) {
  if (!eta) return 'No ETA'
  const diffMs = new Date(eta).getTime() - Date.now()
  if (diffMs <= 0) return 'Breach imminent'
  const mins = Math.round(diffMs / 60000)
  if (mins < 60) return `${mins}m to breach`
  const hours = Math.floor(mins / 60)
  return `${hours}h ${mins % 60}m to breach`
}

export function PredictiveAlertPanel() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
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
    return <div className="panel scan-sweep" style={{ minHeight: 196 }} />
  }

  const alerts = (data ?? []).slice(0, 3)

  return (
    <div className="panel animate-fade-up" style={{ padding: '18px 20px', overflow: 'hidden', position: 'relative' }}>
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        background: 'radial-gradient(circle at 85% 10%, rgba(249,115,22,0.12), transparent 35%)',
      }} />
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.72rem', letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--c-signal)', marginBottom: 5 }}>
            Pre-Mortem Mode
          </div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '1.25rem', color: 'var(--c-text)', letterSpacing: '0.03em' }}>
            Predictive Detections
          </div>
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text-faint)' }}>
          {alerts.length} live signal{alerts.length !== 1 ? 's' : ''}
        </div>
      </div>

      {alerts.length === 0 && (
        <div style={{
          padding: '20px 18px', borderRadius: 6,
          border: '1px solid var(--c-border-hi)', background: 'var(--c-surface-2)',
          fontFamily: 'var(--font-mono)', fontSize: '0.74rem', color: 'var(--c-text-muted)',
        }}>
          No predictive signals are active. Corvin is continuously watching for error acceleration, memory pressure, and restart instability.
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
        {alerts.map((alert, index) => {
          const accent = SEVERITY_COLOR[alert.severity] ?? 'var(--c-signal)'
          return (
            <div key={alert.id} className="scan-sweep" style={{
              animationDelay: `${index * 70}ms`,
              border: `1px solid color-mix(in srgb, ${accent} 35%, var(--c-border-hi))`,
              background: `linear-gradient(180deg, color-mix(in srgb, ${accent} 10%, transparent) 0%, var(--c-surface-2) 100%)`,
              borderRadius: 8, padding: '16px 16px 14px',
              boxShadow: `0 12px 30px color-mix(in srgb, ${accent} 18%, transparent)`,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 10 }}>
                <span style={{
                  fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.68rem',
                  letterSpacing: '0.16em', textTransform: 'uppercase', color: accent,
                }}>
                  {alert.alert_type.replace(/_/g, ' ')}
                </span>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-text-muted)',
                  padding: '3px 8px', borderRadius: 999, border: '1px solid var(--c-border)',
                }}>
                  {etaLabel(alert.estimated_breach_at)}
                </span>
              </div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.98rem', color: 'var(--c-text)', marginBottom: 8, lineHeight: 1.15 }}>
                {alert.title}
              </div>
              <p style={{ margin: '0 0 12px', fontFamily: 'var(--font-body)', fontSize: '0.82rem', color: 'var(--c-text-dim)', lineHeight: 1.6 }}>
                {alert.summary}
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
                <div style={{ padding: '10px 12px', borderRadius: 6, background: 'var(--c-surface)', border: '1px solid var(--c-border)' }}>
                  <div style={{ fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--c-text-faint)', marginBottom: 4 }}>Signal</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '1rem', color: accent }}>{alert.signal_value}</div>
                </div>
                <div style={{ padding: '10px 12px', borderRadius: 6, background: 'var(--c-surface)', border: '1px solid var(--c-border)' }}>
                  <div style={{ fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--c-text-faint)', marginBottom: 4 }}>Target</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '1rem', color: 'var(--c-text)' }}>{alert.threshold_value}</div>
                </div>
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text-muted)', marginBottom: 14 }}>
                {alert.service_name} · {alert.environment} · confidence {alert.confidence}
              </div>
              <button
                className="btn-primary"
                disabled={mutation.isPending}
                onClick={() => mutation.mutate(alert.id)}
                style={{ width: '100%', justifyContent: 'center' }}
              >
                {mutation.isPending ? 'Launching…' : 'Investigate Now'}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}