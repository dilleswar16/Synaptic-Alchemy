import { useState } from 'react'
import { fetchCapacityForecast, approveScalingAction, type CapacityForecastReport } from '../api/client'

const RISK_COLORS: Record<string, string> = {
  critical: 'var(--c-red)',
  high: 'var(--c-signal)',
  medium: 'var(--c-amber)',
  low: 'var(--c-green)',
}

const TREND_ICONS: Record<string, string> = {
  rising_fast: '⬆⬆',
  rising: '⬆',
  stable: '→',
  declining: '⬇',
}

export default function CapacityForecastPanel() {
  const [service, setService] = useState('')
  const [report, setReport] = useState<CapacityForecastReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [approving, setApproving] = useState<string | null>(null)

  async function runForecast() {
    if (!service.trim()) return
    setLoading(true)
    setError(null)
    try {
      const result = await fetchCapacityForecast(service.trim())
      setReport(result)
    } catch (e: any) {
      setError(e.message || 'Forecast failed')
    } finally {
      setLoading(false)
    }
  }

  async function handleApprove(actionType: string) {
    if (!report) return
    setApproving(actionType)
    try {
      await approveScalingAction(report.service_name, actionType)
      // Refresh
      await runForecast()
    } catch (e: any) {
      setError(e.message || 'Approval failed')
    } finally {
      setApproving(null)
    }
  }

  return (
    <div style={{
      background: 'var(--c-surface)',
      border: '1px solid var(--c-border)',
      borderRadius: 12,
      padding: 24,
    }}>
      <h3 style={{ margin: '0 0 16px', fontFamily: 'var(--font-display)', fontSize: '1.1rem' }}>
        📈 AI Capacity Forecaster
      </h3>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <input
          type="text"
          placeholder="Service name (e.g. payments-api)"
          value={service}
          onChange={(e) => setService(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && runForecast()}
          style={{
            flex: 1,
            padding: '8px 12px',
            borderRadius: 6,
            border: '1px solid var(--c-border)',
            background: 'var(--c-bg)',
            color: 'var(--c-text)',
            fontSize: '0.85rem',
            fontFamily: 'var(--font-mono)',
          }}
        />
        <button className="btn-primary" onClick={runForecast} disabled={loading || !service.trim()} style={{ fontSize: '0.8rem' }}>
          {loading ? 'Forecasting…' : 'Forecast'}
        </button>
      </div>

      {error && <div style={{ color: 'var(--c-red)', fontSize: '0.82rem', marginBottom: 12 }}>{error}</div>}

      {report && (
        <>
          {/* Risk badge */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
            <span style={{
              fontSize: '0.75rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              color: RISK_COLORS[report.overall_risk] || 'var(--c-text-muted)',
              background: 'var(--c-bg)',
              padding: '3px 10px',
              borderRadius: 4,
              border: `1px solid ${RISK_COLORS[report.overall_risk] || 'var(--c-border)'}`,
            }}>
              {report.overall_risk} risk
            </span>
            <span style={{ fontSize: '0.78rem', color: 'var(--c-text-muted)' }}>
              Window: {report.analyzed_window_hours}h • {report.namespace}/{report.environment}
            </span>
          </div>

          {/* Resource forecasts */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, marginBottom: 16 }}>
            {report.forecasts.map((f) => (
              <div key={f.resource_type} style={{
                border: '1px solid var(--c-border)',
                borderRadius: 8,
                padding: 12,
              }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--c-text-muted)', textTransform: 'uppercase', marginBottom: 4 }}>
                  {f.resource_type.replace('_', ' ')}
                </div>
                <div style={{ fontSize: '1.4rem', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                  {f.current_usage_pct.toFixed(1)}%
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--c-text-muted)', marginTop: 4 }}>
                  {TREND_ICONS[f.trend_direction] || '?'} {f.trend_direction}
                  {f.hours_until_exhaustion != null && (
                    <span style={{ color: f.hours_until_exhaustion < 24 ? 'var(--c-red)' : 'var(--c-amber)' }}>
                      {' '}• {f.hours_until_exhaustion.toFixed(0)}h to exhaustion
                    </span>
                  )}
                </div>
                <div style={{ fontSize: '0.7rem', color: 'var(--c-text-muted)', marginTop: 2 }}>
                  Confidence: {f.confidence} ({f.data_points_analyzed} pts)
                </div>
              </div>
            ))}
          </div>

          {/* Scaling recommendations */}
          {report.scaling_recommendations.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <h4 style={{ fontSize: '0.85rem', margin: '0 0 8px' }}>Scaling Recommendations</h4>
              {report.scaling_recommendations.map((rec, i) => (
                <div key={i} style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '10px 12px',
                  border: '1px solid var(--c-border)',
                  borderRadius: 6,
                  marginBottom: 6,
                }}>
                  <div>
                    <div style={{ fontSize: '0.82rem', fontWeight: 600 }}>
                      {rec.action_type.replace('_', ' ')} — {rec.target_service}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--c-text-muted)' }}>
                      {rec.reason}
                    </div>
                    {rec.recommended_replicas != null && (
                      <div style={{ fontSize: '0.75rem', color: 'var(--c-text-muted)' }}>
                        Replicas: {rec.current_replicas} → {rec.recommended_replicas}
                      </div>
                    )}
                  </div>
                  <button
                    className="btn-primary"
                    onClick={() => handleApprove(rec.action_type)}
                    disabled={approving === rec.action_type}
                    style={{ fontSize: '0.75rem', padding: '4px 10px', flexShrink: 0 }}
                  >
                    {approving === rec.action_type ? '…' : '✓ Approve'}
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* AI Narrative */}
          {report.ai_narrative && (
            <div style={{
              background: 'var(--c-bg)',
              border: '1px solid var(--c-border)',
              borderRadius: 8,
              padding: 14,
              fontSize: '0.82rem',
              lineHeight: 1.5,
              color: 'var(--c-text-muted)',
              whiteSpace: 'pre-wrap',
            }}>
              <strong style={{ color: 'var(--c-text)' }}>AI Analysis:</strong>{' '}
              {report.ai_narrative}
            </div>
          )}
        </>
      )}
    </div>
  )
}
