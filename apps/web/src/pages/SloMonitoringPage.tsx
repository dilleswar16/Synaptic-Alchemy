/**
 * SloMonitoringPage — error budget gauges and trend sparklines for all SLO configs.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import Layout from '../components/Layout'
import {
  listSloStatus,
  getSloSummary,
  getSloHistory,
  refreshSloSnapshots,
  type SloStatusEntry,
  type SloSnapshot,
} from '../api/client'

// ── Helpers ────────────────────────────────────────────────────────────────────

function budgetColor(pct: number | null): string {
  if (pct === null) return 'var(--c-text-muted)'
  if (pct <= 10) return 'var(--c-red)'
  if (pct <= 35) return 'var(--c-warning)'
  return 'var(--c-green)'
}

function burnRateLabel(rate: number | null): { label: string; color: string } {
  if (rate === null) return { label: '—', color: 'var(--c-text-muted)' }
  if (rate > 2) return { label: `${rate.toFixed(1)}× 🔥`, color: 'var(--c-red)' }
  if (rate > 1) return { label: `${rate.toFixed(1)}×`, color: 'var(--c-warning)' }
  return { label: `${rate.toFixed(2)}×`, color: 'var(--c-green)' }
}

function complianceChip(snap: SloSnapshot | null) {
  if (!snap) return <span style={{ color: 'var(--c-text-muted)', fontSize: '0.7rem' }}>NO DATA</span>
  const color = snap.is_compliant ? 'var(--c-green)' : 'var(--c-red)'
  const label = snap.is_compliant ? 'COMPLIANT' : 'BREACHED'
  return (
    <span style={{
      fontSize: '0.65rem', fontWeight: 700, letterSpacing: '0.08em',
      color, border: `1px solid ${color}`, borderRadius: 3,
      padding: '1px 6px', fontFamily: 'var(--font-mono)',
    }}>
      {label}
    </span>
  )
}

// ── Error budget radial gauge ──────────────────────────────────────────────────

function BudgetGauge({ pct, size = 80 }: { pct: number | null; size?: number }) {
  const sw = 7
  const r = (size - sw) / 2
  const circ = 2 * Math.PI * r
  const progress = pct === null ? 0 : Math.min(Math.max(pct, 0), 100) / 100
  const offset = circ * (1 - progress)
  const color = budgetColor(pct)
  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--c-surface-3)" strokeWidth={sw} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke={color} strokeWidth={sw} strokeLinecap="round"
          strokeDasharray={circ} strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.8s ease-out', filter: `drop-shadow(0 0 4px ${color})` }}
        />
      </svg>
      <div style={{
        position: 'absolute', inset: 0, display: 'flex',
        flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      }}>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: '0.9rem', fontWeight: 800, color,
        }}>
          {pct === null ? '—' : `${Math.round(pct)}%`}
        </span>
      </div>
    </div>
  )
}

// ── Sparkline ──────────────────────────────────────────────────────────────────

function BudgetSparkline({ history, width = 100, height = 28 }: {
  history: SloSnapshot[];
  width?: number;
  height?: number;
}) {
  const pts = [...history].reverse().slice(-20).map(s => s.error_budget_pct ?? 50)
  if (pts.length < 2) return null
  const min = Math.min(...pts)
  const max = Math.max(...pts)
  const range = max - min || 1
  const toY = (v: number) => height - ((v - min) / range) * (height - 4) - 2
  const toX = (i: number) => (i / (pts.length - 1)) * width
  const d = pts.map((v, i) => `${i === 0 ? 'M' : 'L'}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ')
  return (
    <svg width={width} height={height} style={{ display: 'block', overflow: 'visible' }}>
      <path d={d} fill="none" stroke="var(--c-info)" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// ── SLO Card ──────────────────────────────────────────────────────────────────

function SloCard({ entry, onSelect }: { entry: SloStatusEntry; onSelect: () => void }) {
  const snap = entry.latest_snapshot
  const measured = snap?.measured_pct ?? null
  const budget = snap?.error_budget_pct ?? null
  const burn = burnRateLabel(snap?.burn_rate ?? null)

  return (
    <div
      onClick={onSelect}
      style={{
        background: 'var(--c-surface-1)', border: '1px solid var(--c-border)',
        borderRadius: 10, padding: '16px', cursor: 'pointer',
        display: 'flex', flexDirection: 'column', gap: 10,
        transition: 'border-color 0.2s, box-shadow 0.2s',
      }}
      onMouseEnter={e => {
        const el = e.currentTarget as HTMLDivElement
        el.style.borderColor = 'var(--c-accent)'
        el.style.boxShadow = '0 0 12px rgba(var(--c-accent-rgb, 100,160,255), 0.15)'
      }}
      onMouseLeave={e => {
        const el = e.currentTarget as HTMLDivElement
        el.style.borderColor = 'var(--c-border)'
        el.style.boxShadow = 'none'
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: '0.875rem', marginBottom: 2 }}>{entry.service_name}</div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span style={{
              fontSize: '0.65rem', fontWeight: 700, fontFamily: 'var(--font-mono)',
              color: entry.sli_type === 'availability' ? 'var(--c-info)' : 'var(--c-warning)',
              textTransform: 'uppercase', letterSpacing: '0.06em',
            }}>
              {entry.sli_type}
            </span>
            {complianceChip(snap)}
          </div>
        </div>
        <BudgetGauge pct={budget} size={68} />
      </div>

      {/* Metrics row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <div style={{ background: 'var(--c-surface-2)', borderRadius: 6, padding: '6px 8px' }}>
          <div style={{ fontSize: '0.6rem', color: 'var(--c-text-muted)', marginBottom: 2, letterSpacing: '0.06em' }}>
            MEASURED
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.95rem' }}>
            {measured !== null ? `${measured.toFixed(3)}%` : '—'}
          </div>
        </div>
        <div style={{ background: 'var(--c-surface-2)', borderRadius: 6, padding: '6px 8px' }}>
          <div style={{ fontSize: '0.6rem', color: 'var(--c-text-muted)', marginBottom: 2, letterSpacing: '0.06em' }}>
            TARGET
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.95rem' }}>
            {entry.target_pct}%
          </div>
        </div>
      </div>

      {/* Burn rate */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <span style={{ fontSize: '0.6rem', color: 'var(--c-text-muted)', letterSpacing: '0.06em' }}>
            BURN RATE&nbsp;
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.82rem', color: burn.color }}>
            {burn.label}
          </span>
        </div>
        {snap && (
          <span style={{
            fontSize: '0.6rem', color: 'var(--c-text-faint)',
            fontFamily: 'var(--font-mono)',
          }}>
            {snap.data_source === 'simulated' ? '~sim' : '⬤ live'}
          </span>
        )}
      </div>

      {/* Budget bar */}
      <div>
        <div style={{
          height: 4, borderRadius: 2, background: 'var(--c-surface-3)', overflow: 'hidden',
        }}>
          <div style={{
            height: '100%', borderRadius: 2,
            width: `${Math.max(0, Math.min(100, budget ?? 0))}%`,
            background: budgetColor(budget),
            transition: 'width 0.8s ease-out',
          }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 2 }}>
          <span style={{ fontSize: '0.58rem', color: 'var(--c-text-faint)' }}>0% budget</span>
          <span style={{ fontSize: '0.58rem', color: 'var(--c-text-faint)' }}>100% budget</span>
        </div>
      </div>
    </div>
  )
}

// ── Detail drawer ──────────────────────────────────────────────────────────────

function SloDetail({ entry, onClose }: { entry: SloStatusEntry; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ['slo-history', entry.id],
    queryFn: () => getSloHistory(entry.id),
  })

  const history = data?.history ?? []

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 80, display: 'flex',
      alignItems: 'flex-end', justifyContent: 'flex-end',
      background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)',
    }}
      onClick={onClose}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: 520, height: '100vh', background: 'var(--c-surface-1)',
          borderLeft: '1px solid var(--c-border)', overflowY: 'auto',
          padding: 24, display: 'flex', flexDirection: 'column', gap: 20,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div style={{ fontWeight: 800, fontSize: '1.1rem' }}>{entry.service_name}</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--c-text-muted)', marginTop: 2 }}>
              {entry.sli_type.toUpperCase()} · {entry.time_window_days}d window · target {entry.target_pct}%
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', fontSize: '1.2rem',
            cursor: 'pointer', color: 'var(--c-text-muted)',
          }}>✕</button>
        </div>

        {/* Latest snapshot summary */}
        {entry.latest_snapshot && (
          <div style={{
            display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10,
          }}>
            {[
              { label: 'Measured', value: entry.latest_snapshot.measured_pct !== null ? `${entry.latest_snapshot.measured_pct.toFixed(3)}%` : '—' },
              { label: 'Budget left', value: entry.latest_snapshot.error_budget_pct !== null ? `${entry.latest_snapshot.error_budget_pct.toFixed(1)}%` : '—' },
              { label: 'Burn rate', value: entry.latest_snapshot.burn_rate !== null ? `${entry.latest_snapshot.burn_rate.toFixed(2)}×` : '—' },
            ].map(m => (
              <div key={m.label} style={{ background: 'var(--c-surface-2)', borderRadius: 6, padding: '8px 10px' }}>
                <div style={{ fontSize: '0.6rem', color: 'var(--c-text-muted)', letterSpacing: '0.06em', marginBottom: 4 }}>
                  {m.label.toUpperCase()}
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700 }}>{m.value}</div>
              </div>
            ))}
          </div>
        )}

        {/* Sparkline */}
        {!isLoading && history.length > 1 && (
          <div>
            <div style={{ fontSize: '0.7rem', color: 'var(--c-text-muted)', marginBottom: 8 }}>
              BUDGET TREND (last {history.length} snapshots)
            </div>
            <BudgetSparkline history={history} width={440} height={56} />
          </div>
        )}

        {/* History table */}
        <div>
          <div style={{ fontSize: '0.7rem', color: 'var(--c-text-muted)', marginBottom: 8 }}>
            SNAPSHOT HISTORY
          </div>
          {isLoading ? (
            <div style={{ color: 'var(--c-text-faint)', fontSize: '0.8rem' }}>Loading…</div>
          ) : history.length === 0 ? (
            <div style={{ color: 'var(--c-text-faint)', fontSize: '0.8rem' }}>No snapshots yet</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {history.map(snap => (
                <div key={snap.id} style={{
                  display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 80px',
                  gap: 8, fontSize: '0.72rem', fontFamily: 'var(--font-mono)',
                  padding: '4px 0', borderBottom: '1px solid var(--c-border)',
                  color: 'var(--c-text)',
                }}>
                  <span style={{ color: 'var(--c-text-muted)' }}>
                    {new Date(snap.sampled_at).toLocaleString()}
                  </span>
                  <span>{snap.measured_pct !== null ? `${snap.measured_pct.toFixed(3)}%` : '—'}</span>
                  <span style={{ color: budgetColor(snap.error_budget_pct) }}>
                    {snap.error_budget_pct !== null ? `${snap.error_budget_pct.toFixed(1)}% left` : '—'}
                  </span>
                  <span style={{ color: snap.is_compliant ? 'var(--c-green)' : 'var(--c-red)' }}>
                    {snap.is_compliant ? 'OK' : 'BREACH'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Summary bar ────────────────────────────────────────────────────────────────

function SummaryBar() {
  const { data } = useQuery({
    queryKey: ['slo-summary'],
    queryFn: getSloSummary,
    refetchInterval: 60_000,
  })

  const stats = [
    { label: 'Total', value: data?.total ?? '—', color: 'var(--c-text)' },
    { label: 'Compliant', value: data?.compliant ?? '—', color: 'var(--c-green)' },
    { label: 'At Risk', value: data?.at_risk ?? '—', color: 'var(--c-warning)' },
    { label: 'Breached', value: data?.breached ?? '—', color: 'var(--c-red)' },
    { label: 'No Data', value: data?.no_data ?? '—', color: 'var(--c-text-muted)' },
  ]

  return (
    <div style={{
      display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20,
    }}>
      {stats.map(s => (
        <div key={s.label} style={{
          background: 'var(--c-surface-1)', border: '1px solid var(--c-border)',
          borderRadius: 8, padding: '8px 16px', display: 'flex', gap: 8, alignItems: 'baseline',
          minWidth: 90,
        }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 800, fontSize: '1.3rem', color: s.color }}>
            {s.value}
          </span>
          <span style={{ fontSize: '0.68rem', color: 'var(--c-text-muted)', letterSpacing: '0.05em' }}>
            {s.label.toUpperCase()}
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function SloMonitoringPage() {
  const [appFilter, setAppFilter] = useState<string>('')
  const [selected, setSelected] = useState<SloStatusEntry | null>(null)
  const qc = useQueryClient()

  const { data: allEntries = [], isLoading, isError } = useQuery({
    queryKey: ['slo-status', appFilter],
    queryFn: () => listSloStatus(appFilter || undefined),
    refetchInterval: 120_000,
  })

  const refreshMut = useMutation({
    mutationFn: () => refreshSloSnapshots(appFilter || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['slo-status'] })
      qc.invalidateQueries({ queryKey: ['slo-summary'] })
    },
  })

  // Collect unique app IDs for filter
  const appIds = [...new Set(allEntries.map(e => e.application_id))]

  return (
    <Layout>
      <div style={{ padding: '28px 32px', maxWidth: 1400, margin: '0 auto' }}>
        {/* Page header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: '1.4rem', fontWeight: 800 }}>SLO Monitoring</h1>
            <p style={{ margin: '4px 0 0', fontSize: '0.8rem', color: 'var(--c-text-muted)' }}>
              Error budget gauges · burn rates · snapshot history
            </p>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            {appIds.length > 0 && (
              <select
                value={appFilter}
                onChange={e => setAppFilter(e.target.value)}
                style={{
                  background: 'var(--c-surface-2)', border: '1px solid var(--c-border)',
                  color: 'var(--c-text)', borderRadius: 6, padding: '6px 10px',
                  fontSize: '0.8rem', cursor: 'pointer',
                }}
              >
                <option value="">All Applications</option>
                {appIds.map(id => (
                  <option key={id} value={id}>{id.slice(0, 8)}…</option>
                ))}
              </select>
            )}
            <button
              onClick={() => refreshMut.mutate()}
              disabled={refreshMut.isPending}
              className="btn-primary"
              style={{ padding: '7px 14px', fontSize: '0.8rem' }}
            >
              {refreshMut.isPending ? 'Refreshing…' : '↻ Refresh'}
            </button>
          </div>
        </div>

        <SummaryBar />

        {isLoading && (
          <div style={{ color: 'var(--c-text-muted)', textAlign: 'center', padding: 60 }}>
            Loading SLO configs…
          </div>
        )}
        {isError && (
          <div style={{ color: 'var(--c-red)', textAlign: 'center', padding: 60 }}>
            Failed to load SLO data. Is the backend running?
          </div>
        )}

        {!isLoading && !isError && allEntries.length === 0 && (
          <div style={{
            textAlign: 'center', padding: '60px 20px',
            border: '1px dashed var(--c-border)', borderRadius: 10,
          }}>
            <div style={{ fontSize: '2rem', marginBottom: 12 }}>◑</div>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>No SLO configs found</div>
            <div style={{ color: 'var(--c-text-muted)', fontSize: '0.82rem', maxWidth: 380, margin: '0 auto' }}>
              Create applications with SLO configs in the Applications panel, then click Refresh to compute the first snapshot.
            </div>
          </div>
        )}

        {!isLoading && allEntries.length > 0 && (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
            gap: 14,
          }}>
            {allEntries.map(entry => (
              <SloCard
                key={entry.id}
                entry={entry}
                onSelect={() => setSelected(entry)}
              />
            ))}
          </div>
        )}

        {selected && (
          <SloDetail entry={selected} onClose={() => setSelected(null)} />
        )}
      </div>
    </Layout>
  )
}
