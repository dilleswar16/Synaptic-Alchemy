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
import '../styles/KpiStrip.css'

export function KpiStrip() {
  const { data: slo } = useQuery({ queryKey: ['slo-summary'], queryFn: getSloSummary, staleTime: 60_000 })
  const { data: stats } = useQuery({ queryKey: ['inv-stats'], queryFn: fetchInvestigationStats, staleTime: 30_000 })

  const kpis: { label: string; value: string; sub?: string; accent?: 'ok' | 'warn' | 'crit' | 'info' }[] = [
    {
      label: 'Services Compliant',
      value: slo ? `${slo.compliant}/${slo.total}` : '—',
      sub: slo ? `${slo.no_data} no data` : undefined,
      accent: slo && slo.breached > 0 ? 'crit' : slo && slo.at_risk > 0 ? 'warn' : 'ok',
    },
    {
      label: 'SLO Breaches',
      value: slo ? String(slo.breached) : '—',
      sub: slo ? `${slo.at_risk} at risk` : undefined,
      accent: slo && slo.breached > 0 ? 'crit' : slo && slo.at_risk > 0 ? 'warn' : 'ok',
    },
    {
      label: 'Active Investigations',
      value: stats ? String(stats.approval_distribution.pending + stats.approval_distribution.approved) : '—',
      sub: stats ? `${stats.today_count} today` : undefined,
      accent: 'info',
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
    },
    {
      label: 'Auto-Resolved',
      value: stats ? `${Math.round(stats.auto_resolved_rate * 100)}%` : '—',
      sub: 'of investigations',
      accent: stats && stats.auto_resolved_rate >= 0.6 ? 'ok' : 'warn',
    },
    {
      label: 'High-Confidence RCA',
      value: stats ? String(stats.confidence_distribution.high) : '—',
      sub: stats ? `of ${stats.total_investigations} total` : undefined,
      accent: 'info',
    },
  ]

  return (
    <div className="kpi-strip" role="region" aria-label="Fleet KPI strip">
      {kpis.map(k => (
        <div key={k.label} className={`kpi-cell kpi-${k.accent ?? 'info'}`}>
          <span className="kpi-value">{k.value}</span>
          <span className="kpi-label">{k.label}</span>
          {k.sub && <span className="kpi-sub">{k.sub}</span>}
        </div>
      ))}
    </div>
  )
}
