/**
 * ServiceCard — compact card for the fleet grid.
 *
 * Shows per-service SLO health at a glance:
 *   • Donut ring (SVG) — SLO compliance %
 *   • Gradient error-budget bar
 *   • Health badge (Healthy / At Risk / Breaching)
 *   • Data-source badge (simulated / connector)
 *   • "Corvin active" pulse dot when hasPendingInvestigation
 *   • Link to investigation queue filtered by service
 */

import { Link } from 'react-router-dom'
import type { SloStatusEntry } from '../api/client'
import '../styles/ServiceCard.css'

interface Props {
  entry: SloStatusEntry
  hasPendingInvestigation?: boolean
}

function healthLabel(snap: SloStatusEntry['latest_snapshot'], target: number) {
  if (!snap || snap.measured_pct == null) return { label: 'No Data', cls: 'no-data' }
  if (snap.burn_rate != null && snap.burn_rate > 1.2) return { label: 'Breaching', cls: 'crit' }
  if (snap.burn_rate != null && snap.burn_rate > 0.7) return { label: 'At Risk', cls: 'warn' }
  if (snap.measured_pct >= target) return { label: 'Healthy', cls: 'ok' }
  return { label: 'Degraded', cls: 'warn' }
}

function DonutRing({ pct, cls }: { pct: number; cls: string }) {
  const r = 26
  const circ = 2 * Math.PI * r
  const filled = Math.max(0, Math.min(1, pct / 100)) * circ
  const gap = circ - filled
  return (
    <svg className="donut" width="68" height="68" viewBox="0 0 68 68" aria-hidden>
      <circle cx="34" cy="34" r={r} fill="none" stroke="var(--c-border, #e5e7eb)" strokeWidth="7" />
      <circle
        cx="34" cy="34" r={r}
        fill="none"
        strokeWidth="7"
        strokeLinecap="round"
        strokeDasharray={`${filled} ${gap}`}
        strokeDashoffset={circ * 0.25}
        className={`donut-arc donut-${cls}`}
      />
      <text x="34" y="38" textAnchor="middle" className="donut-label">
        {pct.toFixed(1)}
      </text>
    </svg>
  )
}

function BudgetBar({ pct, cls }: { pct: number; cls: string }) {
  const clamped = Math.max(0, Math.min(100, pct))
  return (
    <div className="budget-bar-track" title={`Error budget: ${pct.toFixed(1)}%`}>
      <div className={`budget-bar-fill budget-bar-${cls}`} style={{ width: `${clamped}%` }} />
    </div>
  )
}

export function ServiceCard({ entry, hasPendingInvestigation = false }: Props) {
  const snap = entry.latest_snapshot
  const budgetPct = snap?.error_budget_pct ?? 0
  const burnRate = snap?.burn_rate ?? null
  const { label, cls } = healthLabel(snap, entry.target_pct)

  // Friendly service display name
  const displayName = entry.service_name
    .replace(/-/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())

  return (
    <div className={`service-card svc-${cls}`} role="article" aria-label={`Service card: ${entry.service_name}`}>
      {/* Pulse dot for active Corvin investigation */}
      {hasPendingInvestigation && (
        <span className="corvin-pulse" title="Corvin investigation active" aria-label="Corvin active">
          <span className="pulse-dot" />
          <span className="pulse-label">Corvin active</span>
        </span>
      )}

      {/* SLI type badge */}
      <span className={`sli-badge sli-${entry.sli_type}`}>
        {entry.sli_type === 'availability' ? 'AVAIL' : 'LATENCY'}
      </span>

      {/* Service name */}
      <div className="svc-name" title={entry.service_name}>{displayName}</div>

      {/* Donut ring */}
      <DonutRing pct={snap?.measured_pct ?? 0} cls={cls} />

      {/* Target SLO */}
      <div className="slo-target">target {entry.target_pct}%</div>

      {/* Error budget bar */}
      <div className="budget-label-row">
        <span className="budget-label-text">Error budget</span>
        <span className={`budget-pct budget-pct-${cls}`}>
          {snap ? `${budgetPct.toFixed(1)}%` : '—'}
        </span>
      </div>
      <BudgetBar pct={budgetPct} cls={cls} />

      {/* Burn rate */}
      {burnRate != null && (
        <div className={`burn-rate burn-${cls}`}>
          ⚡ burn {burnRate.toFixed(2)}×
        </div>
      )}

      {/* Health badge */}
      <div className={`health-badge badge-${cls}`}>{label}</div>

      {/* Data source */}
      {snap?.data_source === 'simulated' && (
        <span className="datasource-tag">simulated</span>
      )}

      {/* Link to investigation queue for this service */}
      <Link
        to={`/investigations?service=${encodeURIComponent(entry.service_name)}`}
        className="svc-card-link"
        aria-label={`View investigations for ${entry.service_name}`}
      >
        View investigations →
      </Link>
    </div>
  )
}
