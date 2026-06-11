/**
 * CapacityForecastPanel — redesigned V5.4
 *
 * Linear regression forecasts with:
 * - Service selector with environment + namespace dropdowns
 * - Usage bars with gradient color coding
 * - Trend indicators (fast ↑↑ / rising ↑ / stable → / declining ↓)
 * - Hours-to-exhaustion countdown with urgency color
 * - Scaling recommendations with cost impact + replica/limit changes
 * - AI-generated narrative
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchCapacityForecast,
  approveScalingAction,
  type CapacityForecastReport,
  type ResourceForecast,
  type ScalingRecommendation,
} from '../api/client'

// ── Constants ─────────────────────────────────────────────────────────────────

const RISK_META: Record<string, { color: string; bg: string; icon: string }> = {
  critical: { color: 'var(--c-red)',     bg: 'rgba(239,68,68,0.08)',    icon: '🔴' },
  high:     { color: 'var(--c-signal)',  bg: 'rgba(220,38,38,0.08)',    icon: '🟠' },
  medium:   { color: '#b45309',          bg: 'rgba(251,191,36,0.08)',   icon: '🟡' },
  low:      { color: 'var(--c-green)',   bg: 'rgba(34,197,94,0.08)',    icon: '🟢' },
}

const TREND_META: Record<string, { label: string; icon: string; color: string }> = {
  increasing: { label: 'Rising Fast', icon: '⬆⬆', color: 'var(--c-red)' },
  stable:     { label: 'Stable',      icon: '→',  color: 'var(--c-text-faint)' },
  decreasing: { label: 'Declining',   icon: '⬇',  color: 'var(--c-green)' },
}

// ── Resource forecast card ────────────────────────────────────────────────────

function ResourceCard({ forecast }: { forecast: ResourceForecast }) {
  const meta = TREND_META[forecast.trend_direction] ?? TREND_META.stable
  const usageColor = forecast.current_usage_pct < 70 ? 'var(--c-green)' :
                     forecast.current_usage_pct < 85 ? '#b45309' : 'var(--c-red)'
  const exhaustionColor = !forecast.hours_until_exhaustion ? 'transparent' :
                          forecast.hours_until_exhaustion < 6 ? 'var(--c-red)' :
                          forecast.hours_until_exhaustion < 24 ? '#b45309' : 'var(--c-green)'

  return (
    <div style={{
      background: 'var(--c-surface)',
      border: '1px solid var(--c-border)',
      borderRadius: 10,
      padding: '14px 16px',
      display: 'flex', flexDirection: 'column', gap: 10,
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 2,
      }}>
        <div>
          <div style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--c-text-muted)', marginBottom: 1 }}>
            {forecast.resource_type.replace('_', ' ')}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: '1.6rem', fontWeight: 800,
              color: usageColor, lineHeight: 1,
            }}>
              {forecast.current_usage_pct.toFixed(1)}%
            </span>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.7rem', fontWeight: 600,
              color: meta.color,
            }}>
              {meta.icon} {meta.label}
            </span>
          </div>
        </div>
      </div>

      {/* Usage bar */}
      <div style={{ height: 6, background: 'var(--c-border)', borderRadius: 3, overflow: 'hidden' }}>
        <div
          style={{
            height: '100%',
            width: `${Math.min(100, forecast.current_usage_pct)}%`,
            background: `linear-gradient(90deg, ${usageColor} 0%, ${usageColor}80 100%)`,
            transition: 'width 0.6s ease-out',
          }}
        />
      </div>

      {/* Metrics row */}
      <div style={{ display: 'flex', gap: 12, fontSize: '0.7rem' }}>
        {/* Trend slope */}
        <div>
          <div style={{ color: 'var(--c-text-faint)', marginBottom: 2 }}>Trend/h</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: meta.color }}>
            {forecast.trend_slope_per_hour > 0 ? '+' : ''}{forecast.trend_slope_per_hour.toFixed(2)}%
          </div>
        </div>

        {/* Time to exhaustion */}
        {forecast.hours_until_exhaustion !== null && (
          <div>
            <div style={{ color: 'var(--c-text-faint)', marginBottom: 2 }}>To 100%</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: exhaustionColor }}>
              {forecast.hours_until_exhaustion < 1 ? '<1h' : `${Math.round(forecast.hours_until_exhaustion)}h`}
            </div>
          </div>
        )}

        {/* Confidence */}
        <div>
          <div style={{ color: 'var(--c-text-faint)', marginBottom: 2 }}>Conf.</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--c-text-dim)' }}>
            {forecast.confidence.charAt(0).toUpperCase()} ({forecast.data_points_analyzed})
          </div>
        </div>
      </div>

      {/* Recommendation */}
      <p style={{
        margin: 0, fontSize: '0.7rem', color: 'var(--c-text-faint)',
        lineHeight: 1.4, fontStyle: 'italic',
      }}>
        {forecast.recommendation}
      </p>
    </div>
  )
}

// ── Recommendation card ───────────────────────────────────────────────────────

function RecommendationCard({
  rec,
  onApprove,
  approving,
}: {
  rec: ScalingRecommendation
  onApprove: () => void
  approving: boolean
}) {
  const priorityColor = rec.priority === 'critical' ? 'var(--c-red)' :
                        rec.priority === 'high' ? 'var(--c-signal)' : '#b45309'

  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 12,
      padding: '12px 16px',
      background: 'var(--c-surface)',
      border: `1px solid ${priorityColor}40`,
      borderLeft: `3px solid ${priorityColor}`,
      borderRadius: 8,
    }}>
      <div style={{ flex: 1 }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6,
        }}>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.62rem', fontWeight: 800,
            textTransform: 'uppercase', letterSpacing: '0.06em',
            color: priorityColor, background: `${priorityColor}18`,
            border: `1px solid ${priorityColor}30`,
            borderRadius: 4, padding: '1px 6px',
          }}>
            {rec.priority}
          </span>
          <span style={{ fontWeight: 700, fontSize: '0.82rem', color: 'var(--c-text)' }}>
            {rec.action_type.replace('_', ' ').toUpperCase()}
          </span>
          <span style={{ fontSize: '0.75rem', color: 'var(--c-text-dim)', fontFamily: 'var(--font-mono)' }}>
            {rec.target_service}
          </span>
        </div>

        <p style={{ margin: '0 0 8px', fontSize: '0.75rem', color: 'var(--c-text-dim)', lineHeight: 1.4 }}>
          {rec.reason}
        </p>

        {/* Changes */}
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          {rec.recommended_replicas !== null && (
            <div style={{ fontSize: '0.73rem' }}>
              <span style={{ color: 'var(--c-text-faint)' }}>Replicas: </span>
              <span style={{
                fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--c-text)',
              }}>
                {rec.current_replicas} → {rec.recommended_replicas}
              </span>
            </div>
          )}
          {rec.recommended_resource_limit && (
            <div style={{ fontSize: '0.73rem' }}>
              <span style={{ color: 'var(--c-text-faint)' }}>Limit: </span>
              <span style={{
                fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--c-text)',
              }}>
                {rec.current_resource_limit || '—'} → {rec.recommended_resource_limit}
              </span>
            </div>
          )}
          {rec.estimated_monthly_cost_delta !== 0 && (
            <div style={{ fontSize: '0.73rem' }}>
              <span style={{ color: 'var(--c-text-faint)' }}>Cost: </span>
              <span style={{
                fontFamily: 'var(--font-mono)', fontWeight: 700,
                color: rec.estimated_monthly_cost_delta > 0 ? 'var(--c-signal)' : 'var(--c-green)',
              }}>
                {rec.estimated_monthly_cost_delta > 0 ? '+' : ''}\${Math.abs(rec.estimated_monthly_cost_delta).toFixed(0)}/mo
              </span>
            </div>
          )}
        </div>
      </div>

      <button
        onClick={onApprove}
        disabled={approving}
        style={{
          padding: '6px 14px', fontSize: '0.74rem', fontWeight: 700,
          background: approving ? 'var(--c-surface-3)' : priorityColor,
          color: approving ? 'var(--c-text-faint)' : '#fff',
          border: `1px solid ${approving ? 'var(--c-border)' : priorityColor}`,
          borderRadius: 6, cursor: approving ? 'not-allowed' : 'pointer',
          fontFamily: 'var(--font-body)', whiteSpace: 'nowrap', flexShrink: 0,
          transition: 'all 0.12s',
        }}
      >
        {approving ? '⟳' : '✓ Approve'}
      </button>
    </div>
  )
}

// ── Main panel ────────────────────────────────────────────────────────────────

export default function CapacityForecastPanel() {
  const qc = useQueryClient()
  const [service, setService] = useState('')
  const [env, setEnv] = useState('dev')
  const [ns, setNs] = useState('default')

  const { data: report, isLoading, error, refetch, isFetching } = useQuery<CapacityForecastReport>({
    queryKey: ['capacity-forecast', service, env, ns],
    queryFn: () => service ? fetchCapacityForecast(service, env, ns) : Promise.reject(new Error('Select a service')),
    enabled: !!service,
    staleTime: 120_000,
    retry: false,
  })

  const approveMut = useMutation({
    mutationFn: (actionType: string) => approveScalingAction(service, actionType),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['capacity-forecast'] }),
  })

  const risk = report?.overall_risk ?? 'low'
  const riskMeta = RISK_META[risk] ?? RISK_META.low

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
        padding: '16px 20px',
        background: 'var(--c-surface)',
        border: '1px solid var(--c-border)',
        borderRadius: 10,
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
            <span style={{ fontSize: '1rem' }}>📈</span>
            <span style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.95rem', color: 'var(--c-text)' }}>
              Capacity Forecaster
            </span>
          </div>
          <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--c-text-faint)', lineHeight: 1.5 }}>
            Linear regression on container resource metrics. Predicts CPU/memory exhaustion and recommends scaling actions.
          </p>
        </div>
      </div>

      {/* Input controls */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 8 }}>
        <div>
          <label style={{ display: 'block', fontSize: '0.68rem', fontWeight: 600, color: 'var(--c-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Service
          </label>
          <input
            type="text"
            placeholder="e.g. fundapis"
            value={service}
            onChange={e => setService(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && refetch()}
            style={{
              width: '100%', padding: '7px 10px',
              background: 'var(--c-bg)', border: '1px solid var(--c-border-hi)',
              borderRadius: 6, color: 'var(--c-text)',
              fontFamily: 'var(--font-mono)', fontSize: '0.78rem',
              boxSizing: 'border-box',
            }}
          />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: '0.68rem', fontWeight: 600, color: 'var(--c-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Environment
          </label>
          <select
            value={env}
            onChange={e => setEnv(e.target.value)}
            style={{
              width: '100%', padding: '7px 10px',
              background: 'var(--c-bg)', border: '1px solid var(--c-border-hi)',
              borderRadius: 6, color: 'var(--c-text)',
              fontFamily: 'var(--font-mono)', fontSize: '0.78rem',
              boxSizing: 'border-box',
            }}
          >
            <option value="dev">dev</option>
            <option value="staging">staging</option>
            <option value="prod">prod</option>
          </select>
        </div>
        <div>
          <label style={{ display: 'block', fontSize: '0.68rem', fontWeight: 600, color: 'var(--c-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Namespace
          </label>
          <select
            value={ns}
            onChange={e => setNs(e.target.value)}
            style={{
              width: '100%', padding: '7px 10px',
              background: 'var(--c-bg)', border: '1px solid var(--c-border-hi)',
              borderRadius: 6, color: 'var(--c-text)',
              fontFamily: 'var(--font-mono)', fontSize: '0.78rem',
              boxSizing: 'border-box',
            }}
          >
            <option value="default">default</option>
            <option value="acme-retail">acme-retail</option>
            <option value="ingestion">ingestion</option>
            <option value="kube-system">kube-system</option>
          </select>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <label style={{ display: 'block', fontSize: '0.68rem', fontWeight: 600, color: 'var(--c-text-muted)', marginBottom: 4, visibility: 'hidden', height: 16 }}>
            ─
          </label>
          <button
            onClick={() => refetch()}
            disabled={isFetching || !service}
            style={{
              padding: '7px 14px', fontSize: '0.78rem', fontWeight: 600,
              background: isFetching ? 'var(--c-surface-3)' : 'var(--c-surface-2)',
              border: '1px solid var(--c-border-hi)', borderRadius: 6,
              color: isFetching ? 'var(--c-text-faint)' : 'var(--c-text-dim)',
              cursor: isFetching || !service ? 'not-allowed' : 'pointer',
              fontFamily: 'var(--font-body)', transition: 'all 0.12s',
            }}
          >
            {isFetching ? '⟳ Forecasting…' : 'Forecast'}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          padding: '10px 14px', color: 'var(--c-red)', fontSize: '0.78rem',
          background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
          borderRadius: 8, fontFamily: 'var(--font-mono)',
        }}>
          {(error as Error).message}
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[0, 1, 2, 3].map(i => (
            <div key={i} className="pulse-skeleton" style={{ height: 80, borderRadius: 10 }} />
          ))}
        </div>
      )}

      {/* Report */}
      {report && (
        <>
          {/* Risk + metadata */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.6rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.07em',
              color: riskMeta.color, background: riskMeta.bg,
              border: `1px solid ${riskMeta.color}40`,
              borderRadius: 6, padding: '2px 8px',
            }}>
              {riskMeta.icon} {risk} risk
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)' }}>
              {report.analyzed_window_hours}h window
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)' }}>
              {report.namespace}/{report.environment}
            </span>
          </div>

          {/* Resource forecasts grid */}
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 10,
          }}>
            {report.forecasts.map(f => (
              <ResourceCard key={f.resource_type} forecast={f} />
            ))}
          </div>

          {/* Scaling recommendations */}
          {report.scaling_recommendations.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <h4 style={{
                margin: 0, fontSize: '0.85rem', fontWeight: 700, color: 'var(--c-text)',
                display: 'flex', alignItems: 'center', gap: 8,
              }}>
                <span>⚙️</span> Scaling Recommendations
              </h4>
              {report.scaling_recommendations.map((rec, i) => (
                <RecommendationCard
                  key={i}
                  rec={rec}
                  onApprove={() => approveMut.mutate(rec.action_type)}
                  approving={approveMut.isPending && approveMut.variables === rec.action_type}
                />
              ))}
            </div>
          )}

          {/* AI narrative */}
          {report.ai_narrative && (
            <div style={{
              padding: '14px 16px',
              background: 'var(--c-bg)', border: '1px solid var(--c-border)',
              borderRadius: 8,
              fontFamily: 'var(--font-mono)', fontSize: '0.75rem',
              color: 'var(--c-text-dim)', lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
            }}>
              <span style={{ fontWeight: 700, color: 'var(--c-text)' }}>AI Analysis:</span>
              {'\n'}{report.ai_narrative}
            </div>
          )}
        </>
      )}

      {/* Empty state */}
      {!isLoading && !report && (
        <div style={{
          textAlign: 'center', padding: '48px 24px',
          border: '1px dashed var(--c-border)', borderRadius: 10,
          background: 'var(--c-surface)',
        }}>
          <div style={{ fontSize: '2.2rem', marginBottom: 10, opacity: 0.4 }}>📈</div>
          <div style={{ fontWeight: 700, color: 'var(--c-text)', marginBottom: 6 }}>Enter a service name</div>
          <p style={{ margin: '0 auto', fontSize: '0.77rem', color: 'var(--c-text-faint)', lineHeight: 1.6, maxWidth: 380 }}>
            Forecast resource exhaustion using linear regression on historical container metrics from investigations.
            Select a service, environment, and namespace to begin.
          </p>
        </div>
      )}
    </div>
  )
}
