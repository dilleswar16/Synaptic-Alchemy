/**
 * DoraSidebar — 360px sidebar with 4 DORA ring gauges + ROI summary.
 *
 * Placed to the right of ServiceFleetGrid in the main fleet view.
 * Uses radial SVG arcs (not a chart library) to visualise each metric.
 *
 * Data:
 *   - fetchDora(30)  → DoraMetrics
 *   - fetchRoi()     → RoiStats
 */

import { useQuery } from '@tanstack/react-query'
import { fetchDora } from '../api/client'
import '../styles/DoraSidebar.css'

const TREND_ICON: Record<string, string> = {
  improving: '↑',
  stable:    '→',
  degrading: '↓',
}
const TREND_CLS: Record<string, string> = {
  improving: 'ok',
  stable:    'warn',
  degrading: 'crit',
}

/** Arc gauge — fills a semi-circle proportional to value/max. */
function ArcGauge({
  value, max, label, unit, cls,
}: { value: number; max: number; label: string; unit: string; cls: string }) {
  const pct = Math.min(1, Math.max(0, value / max))
  const radius = 34
  const circ = Math.PI * radius  // half-circle
  const filled = pct * circ
  const gap = circ - filled

  // Arc path for a top semi-circle
  const cx = 48, cy = 52
  return (
    <div className={`arc-gauge arc-${cls}`} aria-label={`${label}: ${value} ${unit}`}>
      <svg width="96" height="56" viewBox="0 0 96 56" aria-hidden>
        <path
          d={`M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`}
          fill="none"
          stroke="var(--c-border, #e5e7eb)"
          strokeWidth="7"
          strokeLinecap="round"
        />
        <path
          d={`M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`}
          fill="none"
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${gap + 100}`}
          className={`arc-fill arc-fill-${cls}`}
        />
        <text x={cx} y={cy - 4} textAnchor="middle" className="arc-value-text">
          {value < 10 && unit !== 'm' ? value.toFixed(2) : Math.round(value)}
        </text>
        <text x={cx} y={cy + 10} textAnchor="middle" className="arc-unit-text">
          {unit}
        </text>
      </svg>
      <div className="arc-label">{label}</div>
    </div>
  )
}

export function DoraSidebar() {
  const { data: dora } = useQuery({
    queryKey: ['dora'],
    queryFn: () => fetchDora(30),
    staleTime: 300_000,
    retry: false,
  })

  const trendCls = dora ? TREND_CLS[dora.mttr_trend] ?? 'warn' : 'warn'
  const trendIcon = dora ? TREND_ICON[dora.mttr_trend] ?? '→' : '→'

  return (
    <aside className="dora-sidebar" aria-label="DORA metrics and ROI sidebar">
      <h3 className="dora-sidebar-title">DORA · 30 days</h3>

      {/* Arc gauges */}
      <div className="dora-gauges">
        <ArcGauge
          value={dora?.deployment_frequency ?? 0}
          max={10}
          label="Incident Freq"
          unit="/day"
          cls={
            (dora?.deployment_frequency ?? 0) < 2 ? 'ok'
            : (dora?.deployment_frequency ?? 0) < 5 ? 'warn'
            : 'crit'
          }
        />
        <ArcGauge
          value={dora ? Math.round(dora.mttr_minutes) : 0}
          max={120}
          label="MTTR"
          unit="min"
          cls={
            (dora?.mttr_minutes ?? 999) < 30 ? 'ok'
            : (dora?.mttr_minutes ?? 999) < 60 ? 'warn'
            : 'crit'
          }
        />
        <ArcGauge
          value={dora ? Math.round(dora.change_failure_rate_pct) : 0}
          max={100}
          label="Failure Rate"
          unit="%"
          cls={
            (dora?.change_failure_rate_pct ?? 100) < 20 ? 'ok'
            : (dora?.change_failure_rate_pct ?? 100) < 40 ? 'warn'
            : 'crit'
          }
        />
        <ArcGauge
          value={dora?.high_confidence_count ?? 0}
          max={Math.max(dora?.total_investigations ?? 1, 1)}
          label="High-Conf RCA"
          unit="cases"
          cls="info"
        />
      </div>

      {/* Recovery trend */}
      {dora && (
        <div className={`dora-trend dora-trend-${trendCls}`}>
          <span className="trend-icon">{trendIcon}</span>
          <span className="trend-label">
            Recovery {dora.mttr_trend}
            {dora.mttr_prior_minutes > 0 && (
              <span className="trend-delta">
                {' '}({Math.round(dora.mttr_prior_minutes)}m → {Math.round(dora.mttr_minutes)}m)
              </span>
            )}
          </span>
        </div>
      )}

      {!dora && (
        <div className="dora-empty">No DORA data yet. Run at least one investigation.</div>
      )}
    </aside>
  )
}
