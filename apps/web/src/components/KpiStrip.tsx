/**
 * KpiStrip — sticky 8-metric command strip at the top of the dashboard.
 *
 * Data sources:
 *   - getSloSummary()         → SLO counts (compliant / at_risk / breached)
 *   - fetchInvestigationStats() → active investigations, MTTR, auto-resolved
 *   - fetchRoi()              → cost saved, hours saved
 */

import { useQuery } from '@tanstack/react-query'
import {
  getSloSummary,
  fetchInvestigationStats,
} from '../api/client'
import { InfoTooltip } from './Section'
import '../styles/KpiStrip.css'

export function KpiStrip() {
  const { data: slo } = useQuery({ queryKey: ['slo-summary'], queryFn: getSloSummary, staleTime: 60_000 })
  const { data: stats } = useQuery({ queryKey: ['inv-stats'], queryFn: fetchInvestigationStats, staleTime: 30_000 })

  const kpis: { label: string; value: string; sub?: string; accent?: 'ok' | 'warn' | 'crit' | 'info'; tooltip: string }[] = [
    {
      label: 'Services Compliant',
      value: slo ? `${slo.compliant}/${slo.total}` : '—',
      sub: slo ? `${slo.no_data} no data` : undefined,
      accent: slo && slo.breached > 0 ? 'crit' : slo && slo.at_risk > 0 ? 'warn' : 'ok',
      tooltip: 'Ratio of services currently meeting their SLO targets. A service is compliant when its 30-day error budget burn rate is below 1.0×. Breaching and at-risk services are excluded.',
    },
    {
      label: 'SLO Breaches',
      value: slo ? String(slo.breached) : '—',
      sub: slo ? `${slo.at_risk} at risk` : undefined,
      accent: slo && slo.breached > 0 ? 'crit' : slo && slo.at_risk > 0 ? 'warn' : 'ok',
      tooltip: 'Services whose SLO error budget is fully exhausted — burn rate >1.2× over the 30-day window. Each breach means the agreed reliability target has been missed for this period.',
    },
    {
      label: 'Active Investigations',
      value: stats ? String(stats.approval_distribution.pending + stats.approval_distribution.approved) : '—',
      sub: stats ? `${stats.today_count} today` : undefined,
      accent: 'info',
      tooltip: 'Investigations currently in the human-approval pipeline — either awaiting engineer sign-off (pending) or approved and queued for execution. Excludes completed and rejected investigations.',
    },
    {
      label: 'Avg MTTR',
      value: stats?.avg_mttr_minutes != null
        ? stats.avg_mttr_minutes < 60
          ? `${Math.round(stats.avg_mttr_minutes)}m`
          : `${(stats.avg_mttr_minutes / 60).toFixed(1)}h`
        : '—',
      sub: 'mean time to resolve',
      accent: stats?.avg_mttr_minutes != null && stats.avg_mttr_minutes < 30 ? 'ok' : 'warn',
      tooltip: 'Mean time from alert trigger to approved fix execution across all completed investigations. Includes AI analysis time and human approval latency. Lower is better — target is sub-30 minutes.',
    },
    {
      label: 'Auto-Resolved',
      value: stats ? `${Math.round(stats.auto_resolved_rate * 100)}%` : '—',
      sub: 'of investigations',
      accent: stats && stats.auto_resolved_rate >= 0.6 ? 'ok' : 'warn',
      tooltip: 'Percentage of investigations where Corvin autonomously identified the root cause and the engineer approved the fix without any manual diagnosis. Reflects the platform\'s autonomous resolution rate.',
    },
    {
      label: 'High-Confidence RCA',
      value: stats ? String(stats.confidence_distribution.high) : '—',
      sub: stats ? `of ${stats.total_investigations} total` : undefined,
      accent: 'info',
      tooltip: 'Investigations where Corvin\'s root cause analysis was rated HIGH confidence — meaning strong, unambiguous evidence chains with corroborating signals across multiple data sources.',
    },
  ]

  return (
    <div className="kpi-strip" role="region" aria-label="Fleet KPI strip">
      {kpis.map(k => (
        <div key={k.label} className={`kpi-cell kpi-${k.accent ?? 'info'}`}>
          <span className="kpi-value">{k.value}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 4 }}>
            <span className="kpi-label" style={{ marginTop: 0 }}>{k.label}</span>
            <InfoTooltip text={k.tooltip} />
          </div>
          {k.sub && <span className="kpi-sub">{k.sub}</span>}
        </div>
      ))}
    </div>
  )
}
