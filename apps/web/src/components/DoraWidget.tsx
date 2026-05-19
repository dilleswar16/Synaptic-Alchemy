/**
 * DoraWidget — DORA four-key engineering metrics panel.
 *
 * Tiles:
 *   1. Incident Frequency   (deployment_frequency — incidents/day)
 *   2. Lead Time (MTTR)     (avg investigation duration in minutes)
 *   3. Change Failure Rate  (% high-confidence incidents)
 *   4. Recovery Trend       (improving / stable / degrading vs prior period)
 */
import { useQuery } from '@tanstack/react-query'
import { fetchDora } from '../api/client'

const TREND_COLOR: Record<string, string> = {
  improving:  '#22c55e',
  stable:     '#f59e0b',
  degrading:  '#ef4444',
}

const TREND_LABEL: Record<string, string> = {
  improving:  '↑ Improving',
  stable:     '→ Stable',
  degrading:  '↓ Degrading',
}

interface Tile {
  label: string
  value: string
  sub: string
  color: string
}

function LoadingSkeleton() {
  return (
    <div className="panel" style={{ padding: '20px 22px' }}>
      <div style={{
        width: '9rem', height: '0.55rem', borderRadius: 4,
        background: 'var(--c-surface-2)', marginBottom: 6,
        animation: 'skeleton-pulse 1.4s ease-in-out infinite',
      }} />
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 2, marginTop: 18, borderRadius: 10, overflow: 'hidden',
        border: '1px solid var(--c-border)',
      }}>
        {[0, 1, 2, 3].map(i => (
          <div key={i} style={{ padding: '16px 18px', background: 'var(--c-surface)' }}>
            {['60%', '80%', '90%'].map((w, j) => (
              <div key={j} style={{
                width: w, height: j === 1 ? '1.75rem' : '0.55rem',
                borderRadius: 4, background: 'var(--c-surface-2)',
                marginBottom: 6, animation: 'skeleton-pulse 1.4s ease-in-out infinite',
              }} />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

export function DoraWidget() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['dora'],
    queryFn: () => fetchDora(30),
    staleTime: 300_000,
    retry: false,
  })

  if (isLoading) return <LoadingSkeleton />

  if (isError || !data) {
    return (
      <div className="panel" style={{ padding: '20px 22px', textAlign: 'center' }}>
        <p style={{ color: 'var(--c-text-muted)', fontSize: '0.875rem', margin: 0 }}>
          DORA metrics unavailable
        </p>
      </div>
    )
  }

  const trend     = data.mttr_trend ?? 'stable'
  const trendClr  = TREND_COLOR[trend]

  const tiles: Tile[] = [
    {
      label: 'Incident Frequency',
      value: `${data.deployment_frequency}/day`,
      sub:   `${data.total_investigations} incidents · ${data.period_days}d`,
      color: '#3b82f6',
    },
    {
      label: 'Lead Time (MTTR)',
      value: data.mttr_minutes > 0
        ? `${data.mttr_minutes < 60
            ? `${data.mttr_minutes}m`
            : `${(data.mttr_minutes / 60).toFixed(1)}h`}`
        : '—',
      sub:   data.mttr_prior_minutes > 0
        ? `Prior: ${data.mttr_prior_minutes < 60
            ? `${data.mttr_prior_minutes}m`
            : `${(data.mttr_prior_minutes / 60).toFixed(1)}h`}`
        : 'No prior data',
      color: '#8b5cf6',
    },
    {
      label: 'Change Failure Rate',
      value: `${data.change_failure_rate_pct}%`,
      sub:   `${data.high_confidence_count} high-confidence`,
      color: data.change_failure_rate_pct > 60 ? '#ef4444' : '#f59e0b',
    },
    {
      label: 'Recovery Trend',
      value: TREND_LABEL[trend],
      sub:   `vs prior ${data.period_days}d period`,
      color: trendClr,
    },
  ]

  return (
    <div className="panel" style={{ padding: '20px 22px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 16 }}>
        <span style={{
          fontSize: '0.65rem', fontWeight: 700, letterSpacing: '0.08em',
          textTransform: 'uppercase', color: 'var(--c-text-muted)',
        }}>
          DORA Metrics
        </span>
        <span style={{
          fontSize: '0.7rem', color: 'var(--c-text-muted)',
          background: 'var(--c-surface-2)', padding: '1px 7px', borderRadius: 4,
        }}>
          Last {data.period_days} days
        </span>
      </div>

      {/* Tiles */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 2,
        borderRadius: 10,
        overflow: 'hidden',
        border: '1px solid var(--c-border)',
      }}>
        {tiles.map((tile, i) => (
          <div
            key={i}
            style={{
              padding: '16px 18px',
              background: 'var(--c-surface)',
              borderRight: i < tiles.length - 1 ? '1px solid var(--c-border)' : 'none',
            }}
          >
            <div style={{
              fontSize: '0.65rem', fontWeight: 600, letterSpacing: '0.06em',
              textTransform: 'uppercase', color: 'var(--c-text-muted)',
              marginBottom: 8,
            }}>
              {tile.label}
            </div>
            <div style={{
              fontSize: '1.55rem', fontWeight: 700, color: tile.color,
              lineHeight: 1.1, marginBottom: 6,
            }}>
              {tile.value}
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--c-text-muted)' }}>
              {tile.sub}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
