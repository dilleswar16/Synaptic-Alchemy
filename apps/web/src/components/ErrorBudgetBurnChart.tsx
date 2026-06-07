/**
 * ErrorBudgetBurnChart — horizontal bar chart of SLO error budget consumption.
 *
 * Sorted by burn_rate descending (most at-risk first).
 * Pure CSS gradients — no Recharts dependency.
 * Shows top-N services (default 20) with ⚡ badge when burn_rate > 1.0.
 *
 * Data: listSloStatus() → availability SLOs only (de-duped by service_name)
 */

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listSloStatus } from '../api/client'
import { InfoTooltip } from './Section'
import '../styles/ErrorBudgetBurnChart.css'

const MAX_ROWS = 20

function burnClass(burn: number): string {
  if (burn > 1.2) return 'crit'
  if (burn > 0.7) return 'warn'
  return 'ok'
}

export function ErrorBudgetBurnChart() {
  const [showAll, setShowAll] = useState(false)

  const { data: sloList = [], isLoading } = useQuery({
    queryKey: ['slo-status'],
    queryFn: () => listSloStatus(),
    staleTime: 30_000,
  })

  // Deduplicate — prefer availability; collect latest snapshot per service
  const rows = useMemo(() => {
    const map = new Map<string, { service: string; budgetPct: number; burnRate: number; target: number }>()
    for (const entry of sloList) {
      const snap = entry.latest_snapshot
      if (!snap || snap.burn_rate == null) continue
      const existing = map.get(entry.service_name)
      if (!existing || entry.sli_type === 'availability') {
        map.set(entry.service_name, {
          service: entry.service_name,
          budgetPct: snap.error_budget_pct ?? 0,
          burnRate: snap.burn_rate,
          target: entry.target_pct,
        })
      }
    }
    return Array.from(map.values()).sort((a, b) => b.burnRate - a.burnRate)
  }, [sloList])

  const displayed = showAll ? rows : rows.slice(0, MAX_ROWS)

  const breachCount = rows.filter(r => r.burnRate > 1.2).length
  const atRiskCount = rows.filter(r => r.burnRate > 0.7 && r.burnRate <= 1.2).length

  return (
    <section className="ebc-section" aria-label="Error budget burn chart">
      <div className="ebc-header">
        <div>
          <h3 className="ebc-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            Error Budget Burn Rate
            <InfoTooltip text="Each service's rate of SLO error budget consumption over the 30-day rolling window. A burn rate >1.0× means the budget will be exhausted before the window ends. Breaching (>1.2×) services are consuming budget faster than their reliability target allows." />
          </h3>
          <p className="ebc-subtitle">
            Services sorted by burn rate — critical SLOs consuming budget fastest
            {breachCount > 0 && (
              <span className="ebc-alert-tag ebc-alert-crit"> ⚡ {breachCount} breaching</span>
            )}
            {atRiskCount > 0 && (
              <span className="ebc-alert-tag ebc-alert-warn"> ⚠ {atRiskCount} at risk</span>
            )}
          </p>
        </div>
        <div className="ebc-legend">
          <span className="ebc-legend-item ebc-ok">Healthy</span>
          <span className="ebc-legend-item ebc-warn">At Risk (&gt;0.7×)</span>
          <span className="ebc-legend-item ebc-crit">Breaching (&gt;1.2×)</span>
        </div>
      </div>

      {isLoading ? (
        <div className="ebc-empty">Loading burn data…</div>
      ) : rows.length === 0 ? (
        <div className="ebc-empty">No SLO snapshot data available yet.</div>
      ) : (
        <>
          <div className="ebc-chart" role="list">
            {/* Column headers */}
            <div className="ebc-row ebc-header-row" aria-hidden>
              <span className="ebc-svc-col">Service</span>
              <span className="ebc-bar-col">Error Budget Remaining</span>
              <span className="ebc-burn-col">Burn Rate</span>
              <span className="ebc-target-col">Target</span>
            </div>

            {displayed.map(row => {
              const cls = burnClass(row.burnRate)
              const clamped = Math.max(0, Math.min(100, row.budgetPct))
              const over = row.budgetPct < 0
              return (
                <div key={row.service} className={`ebc-row ebc-data-row ebc-row-${cls}`} role="listitem">
                  <span className="ebc-svc-col">
                    {row.burnRate > 1.0 && <span className="ebc-lightning">⚡</span>}
                    {row.service.replace(/-/g, '\u200B-')}
                  </span>
                  <span className="ebc-bar-col">
                    <div className="ebc-bar-track">
                      {over ? (
                        <div className="ebc-bar-overrun" />
                      ) : (
                        <div
                          className={`ebc-bar-fill ebc-fill-${cls}`}
                          style={{ width: `${clamped}%` }}
                        />
                      )}
                    </div>
                    <span className={`ebc-budget-pct ebc-pct-${cls}`}>
                      {over ? `${row.budgetPct.toFixed(1)}% 🔴` : `${row.budgetPct.toFixed(1)}%`}
                    </span>
                  </span>
                  <span className={`ebc-burn-col ebc-burn-val-${cls}`}>
                    {row.burnRate.toFixed(2)}×
                  </span>
                  <span className="ebc-target-col ebc-target-val">
                    {row.target}%
                  </span>
                </div>
              )
            })}
          </div>

          {rows.length > MAX_ROWS && (
            <button
              className="ebc-show-more"
              onClick={() => setShowAll(v => !v)}
            >
              {showAll ? `Show top ${MAX_ROWS}` : `Show all ${rows.length} services`}
            </button>
          )}
        </>
      )}
    </section>
  )
}
