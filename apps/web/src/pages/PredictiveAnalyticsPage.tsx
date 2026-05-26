import { useMemo, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import Layout from '../components/Layout'
import { HeroAlertSection } from '../components/HeroAlertSection'
import { SignalDetailDrawer } from '../components/SignalDetailDrawer'
import {
  fetchFixPreview,
  fetchInvestigations,
  fetchPredictiveAlerts,
  fetchServiceScore,
  fetchSlaCountdown,
  fetchTopology,
  fetchTopologyLive,
  type PredictiveAlert,
} from '../api/client'
import { fmtTs, timeAgo } from '../utils/time'

const KNOWN_SERVICES = ['fundapis', 'fundsso', 'partnerapis']

const SEVERITY_WEIGHT: Record<PredictiveAlert['severity'], number> = {
  critical: 1,
  high: 0.8,
  medium: 0.55,
  low: 0.3,
}

const CONFIDENCE_WEIGHT: Record<PredictiveAlert['confidence'], number> = {
  high: 1,
  medium: 0.75,
  low: 0.45,
}

function etaMinutes(eta: string | null): number | null {
  if (!eta) return null
  const diff = (new Date(eta).getTime() - Date.now()) / 60000
  return Number.isFinite(diff) ? diff : null
}

function formatEta(eta: string | null): string {
  const mins = etaMinutes(eta)
  if (mins == null) return 'No breach projected'
  if (mins <= 0) return 'Breach now'
  if (mins < 60) return `${Math.round(mins)}m`
  const h = Math.floor(mins / 60)
  const m = Math.round(mins % 60)
  return `${h}h ${m}m`
}

function toRiskScore(alerts: PredictiveAlert[]): number {
  if (alerts.length === 0) return 0
  const weighted = alerts.map((a) => {
    const sev = SEVERITY_WEIGHT[a.severity] ?? 0.4
    const conf = CONFIDENCE_WEIGHT[a.confidence] ?? 0.5
    const mins = etaMinutes(a.estimated_breach_at)
    const proximity = mins == null ? 0.5 : mins <= 0 ? 1 : Math.max(0.15, 1 - Math.min(mins, 240) / 240)
    const ratio = a.threshold_value > 0 ? Math.min(1.3, a.signal_value / a.threshold_value) : 0.5
    return sev * conf * proximity * ratio
  })

  const avg = weighted.reduce((s, v) => s + v, 0) / weighted.length
  return Math.max(0, Math.min(100, Math.round(avg * 100)))
}

function riskBand(score: number): 'low' | 'watch' | 'high' | 'critical' {
  if (score >= 75) return 'critical'
  if (score >= 55) return 'high'
  if (score >= 35) return 'watch'
  return 'low'
}

export default function PredictiveAnalyticsPage() {
  const queryClient = useQueryClient()
  const [feedback, setFeedback] = useState<Record<string, 'useful' | 'wrong'>>({})

  const { data: alerts = [], isLoading: loadingAlerts } = useQuery({
    queryKey: ['predictive-alerts', 'page'],
    queryFn: () => fetchPredictiveAlerts(true),
    refetchInterval: 45_000,
    staleTime: 20_000,
  })

  const { data: investigations = [] } = useQuery({
    queryKey: ['investigations', 'page'],
    queryFn: fetchInvestigations,
    refetchInterval: 45_000,
    staleTime: 20_000,
  })

  const { data: topology } = useQuery({
    queryKey: ['topology', 'predictive-page'],
    queryFn: async () => {
      try {
        return await fetchTopologyLive()
      } catch {
        return fetchTopology()
      }
    },
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  const serviceSet = useMemo(() => {
    const fromAlerts = alerts.map((a) => a.service_name)
    const fromRecent = investigations.slice(0, 20).map((i) => i.service_name)
    const merged = Array.from(new Set([...KNOWN_SERVICES, ...fromAlerts, ...fromRecent]))
    return merged.slice(0, 8)
  }, [alerts, investigations])

  const scoreQueries = useQueries({
    queries: serviceSet.map((service) => ({
      queryKey: ['service-score', service, 'dev'],
      queryFn: () => fetchServiceScore(service, 'dev'),
      staleTime: 60_000,
    })),
  })

  const requestIds = useMemo(() => {
    const ids = alerts
      .map((a) => a.source_request_id)
      .filter((v): v is string => Boolean(v))
    return Array.from(new Set(ids)).slice(0, 6)
  }, [alerts])

  const slaQueries = useQueries({
    queries: requestIds.map((requestId) => ({
      queryKey: ['sla-countdown', requestId],
      queryFn: () => fetchSlaCountdown(requestId),
      staleTime: 45_000,
      retry: false,
    })),
  })

  const previewQueries = useQueries({
    queries: requestIds.map((requestId) => ({
      queryKey: ['fix-preview', requestId, 'predictive-page'],
      queryFn: () => fetchFixPreview(requestId),
      staleTime: 45_000,
      retry: false,
    })),
  })

  const riskScore = toRiskScore(alerts)
  const band = riskBand(riskScore)

  const actionable = alerts.filter((a) => {
    const mins = etaMinutes(a.estimated_breach_at)
    return a.severity === 'critical' || a.severity === 'high' || (mins != null && mins <= 30)
  })

  const avgBreachMins = useMemo(() => {
    const mins = alerts.map((a) => etaMinutes(a.estimated_breach_at)).filter((m): m is number => m != null && m >= 0)
    if (mins.length === 0) return null
    return Math.round(mins.reduce((s, v) => s + v, 0) / mins.length)
  }, [alerts])

  const scoreRows = useMemo(() => {
    return scoreQueries
      .map((q, idx) => ({ service: serviceSet[idx], data: q.data }))
      .filter((row) => Boolean(row.data))
      .sort((a, b) => (a.data?.score ?? 0) - (b.data?.score ?? 0))
  }, [scoreQueries, serviceSet])

  const slaRows = useMemo(() => {
    return slaQueries.map((q) => q.data).filter((v): v is NonNullable<typeof v> => Boolean(v))
      .sort((a, b) => (a.estimated_breach_in_seconds ?? Number.MAX_SAFE_INTEGER) - (b.estimated_breach_in_seconds ?? Number.MAX_SAFE_INTEGER))
  }, [slaQueries])

  const topRisks = useMemo(() => {
    return [...alerts]
      .sort((a, b) => {
        const aScore = (SEVERITY_WEIGHT[a.severity] ?? 0.4) * (CONFIDENCE_WEIGHT[a.confidence] ?? 0.5)
        const bScore = (SEVERITY_WEIGHT[b.severity] ?? 0.4) * (CONFIDENCE_WEIGHT[b.confidence] ?? 0.5)
        return bScore - aScore
      })
      .slice(0, 6)
  }, [alerts])

  const timeline = useMemo(() => {
    const predictiveEvents = alerts.slice(0, 10).map((a) => ({
      id: `alert-${a.id}`,
      ts: a.created_at,
      kind: 'predictive',
      title: `${a.service_name}: ${a.title}`,
      subtitle: `${a.severity.toUpperCase()} · ${a.confidence.toUpperCase()} · ETA ${formatEta(a.estimated_breach_at)}`,
    }))

    const incidentEvents = investigations.slice(0, 10).map((i) => ({
      id: `inv-${i.request_id}`,
      ts: i.completed_at ?? i.created_at,
      kind: 'investigation',
      title: `${i.service_name}: investigation ${i.approval_status}`,
      subtitle: `${i.trigger_source.replace('_', ' ')} · ${timeAgo(i.completed_at ?? i.created_at)}`,
    }))

    return [...predictiveEvents, ...incidentEvents]
      .sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime())
      .slice(0, 14)
  }, [alerts, investigations])

  const bestPreview = useMemo(() => {
    for (const q of previewQueries) {
      if (q.data && q.data.items.length > 0) return q.data
    }
    return null
  }, [previewQueries])

  const conversionPct = alerts.length > 0
    ? Math.round((alerts.filter((a) => Boolean(a.investigation_request_id)).length / alerts.length) * 100)
    : 0

  const confidenceBreakdown = useMemo(() => {
    const counts = { high: 0, medium: 0, low: 0 }
    alerts.forEach((a) => { counts[a.confidence] += 1 })
    return counts
  }, [alerts])

  const podNodes = (topology?.nodes ?? []).filter((n) => n.kind.toLowerCase().includes('pod'))
  const hotPods = podNodes.filter((n) => (n.cpu_utilization_pct ?? 0) >= 85 || (n.memory_utilization_pct ?? 0) >= 85)

  const [drawerAlert, setDrawerAlert] = useState<PredictiveAlert | null>(null)
  const closeDrawer = useCallback(() => setDrawerAlert(null), [])

  return (
    <Layout>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--c-text-muted)', marginBottom: 6 }}>
            Intelligence Layer
          </div>
          <h1 style={{ margin: 0, fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '1.9rem', letterSpacing: '-0.03em', color: 'var(--c-text)' }}>
            Predictive Analytics Command Center
          </h1>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            className="btn"
            onClick={() => queryClient.invalidateQueries({ queryKey: ['predictive-alerts'] })}
            style={{ fontSize: '0.75rem' }}
          >
            Refresh Signals
          </button>
          <Link to="/corvin" className="btn btn-primary" style={{ fontSize: '0.75rem', textDecoration: 'none' }}>
            Ask Corvin
          </Link>
        </div>
      </div>

      {/* Hero Alert Section */}
      <HeroAlertSection alert={topRisks[0] ?? null} loading={loadingAlerts} />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10, marginBottom: 12 }}>
        {[
          { label: 'Incident Risk Score', value: loadingAlerts ? null : `${riskScore}/100`, sub: loadingAlerts ? 'scanning…' : band.toUpperCase(), color: band === 'critical' ? 'var(--c-red)' : band === 'high' ? 'var(--c-warning)' : band === 'watch' ? 'var(--c-info)' : 'var(--c-green)' },
          { label: 'Live Predictive Signals', value: loadingAlerts ? null : alerts.length, sub: loadingAlerts ? 'analyzing services…' : 'active patterns', color: 'var(--c-text)' },
          { label: 'Actionable Now', value: loadingAlerts ? null : actionable.length, sub: 'near-breach or high severity', color: 'var(--c-signal)' },
          { label: 'Avg Time To Breach', value: loadingAlerts ? null : (avgBreachMins == null ? '—' : `${avgBreachMins}m`), sub: 'across ETA-enabled signals', color: 'var(--c-warning)' },
          { label: 'Predictions Investigated', value: loadingAlerts ? null : `${conversionPct}%`, sub: 'signal-to-investigation conversion', color: 'var(--c-green)' },
        ].map((m) => (
          <div key={m.label} className="panel" style={{ padding: '14px 14px 12px', borderTop: `2px solid ${m.value == null ? 'var(--c-border)' : m.color}` }}>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.66rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--c-text-muted)', marginBottom: 6 }}>{m.label}</div>
            {m.value == null ? (
              <div className="skeleton-shimmer" style={{ height: 28, borderRadius: 6, marginBottom: 4 }} />
            ) : (
              <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 800, fontSize: '1.5rem', color: m.color }}>{m.value}</div>
            )}
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.66rem', color: 'var(--c-text-faint)' }}>{m.sub}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: 12, marginBottom: 12 }}>
        <div className="panel" style={{ padding: '16px 18px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.9rem', color: 'var(--c-text)' }}>Top Emerging Risks</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text-faint)' }}>{topRisks.length} ranked signals</div>
          </div>
          {loadingAlerts && (
            <div style={{ display: 'grid', gap: 8 }}>
              {[0, 1, 2].map((i) => (
                <div key={i} style={{ border: '1px solid var(--c-border)', borderRadius: 8, background: 'var(--c-surface-2)', padding: '10px 12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, marginBottom: 6 }}>
                    <div className="skeleton-shimmer" style={{ height: 14, width: 100, borderRadius: 4 }} />
                    <div className="skeleton-shimmer" style={{ height: 14, width: 80, borderRadius: 4 }} />
                  </div>
                  <div className="skeleton-shimmer" style={{ height: 12, width: '80%', borderRadius: 4, marginBottom: 6 }} />
                  <div style={{ display: 'flex', gap: 8 }}>
                    <div className="skeleton-shimmer" style={{ height: 12, width: 60, borderRadius: 4 }} />
                    <div className="skeleton-shimmer" style={{ height: 12, width: 50, borderRadius: 4 }} />
                  </div>
                </div>
              ))}
            </div>
          )}
          {!loadingAlerts && topRisks.length === 0 && <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--c-text-faint)' }}>No predictive signals right now.</div>}
          <div style={{ display: 'grid', gap: 8 }}>
            {topRisks.map((a) => {
              return (
                <div key={a.id} onClick={() => setDrawerAlert(a)} style={{ border: '1px solid var(--c-border)', borderRadius: 8, background: 'var(--c-surface-2)', padding: '10px 12px', cursor: 'pointer', transition: 'border-color 0.15s, box-shadow 0.15s' }} onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--c-signal)'; e.currentTarget.style.boxShadow = '0 0 12px color-mix(in srgb, var(--c-signal) 15%, transparent)' }} onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--c-border)'; e.currentTarget.style.boxShadow = 'none' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, marginBottom: 4 }}>
                    <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.78rem', color: 'var(--c-text)' }}>{a.service_name}</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-muted)' }}>{a.severity.toUpperCase()} · {a.confidence.toUpperCase()}</div>
                  </div>
                  <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.76rem', color: 'var(--c-text-dim)', marginBottom: 6 }}>{a.title}</div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-warning)' }}>ETA: {formatEta(a.estimated_breach_at)}</span>
                    {a.blast_radius_users > 0 && (
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-red)', fontWeight: 600 }}>
                        Impact: {a.blast_radius_users.toLocaleString()} user errors / {a.blast_radius_requests.toLocaleString()} req
                      </span>
                    )}
                    {a.change_correlation && (
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-signal)' }}>
                        {a.change_correlation}
                      </span>
                    )}
                    {a.related_count > 1 && (
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-info)', background: 'color-mix(in srgb, var(--c-info) 12%, transparent)', padding: '1px 6px', borderRadius: 4 }}>
                        {a.related_count} signals · click to inspect
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        <div className="panel" style={{ padding: '16px 18px' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.9rem', color: 'var(--c-text)', marginBottom: 10 }}>Confidence Meter</div>
          {loadingAlerts ? (
            <div style={{ display: 'grid', gap: 10 }}>
              {[0, 1, 2].map((i) => (
                <div key={i}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <div className="skeleton-shimmer" style={{ height: 12, width: 50, borderRadius: 4 }} />
                    <div className="skeleton-shimmer" style={{ height: 12, width: 40, borderRadius: 4 }} />
                  </div>
                  <div className="skeleton-shimmer" style={{ height: 7, borderRadius: 999 }} />
                </div>
              ))}
            </div>
          ) : (
          <>
          {(['high', 'medium', 'low'] as const).map((c) => {
            const val = confidenceBreakdown[c]
            const total = Math.max(alerts.length, 1)
            const pct = Math.round((val / total) * 100)
            const color = c === 'high' ? 'var(--c-green)' : c === 'medium' ? 'var(--c-warning)' : 'var(--c-red)'
            return (
              <div key={c} style={{ marginBottom: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-mono)', fontSize: '0.67rem', color: 'var(--c-text-muted)', marginBottom: 4 }}>
                  <span>{c.toUpperCase()}</span>
                  <span>{val} ({pct}%)</span>
                </div>
                <div style={{ height: 7, borderRadius: 999, background: 'var(--c-surface-3)', overflow: 'hidden' }}>
                  <div style={{ width: `${pct}%`, height: '100%', background: color }} />
                </div>
              </div>
            )
          })}
          </>
          )}

          <div style={{ marginTop: 14, borderTop: '1px solid var(--c-border)', paddingTop: 12 }}>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.74rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--c-text-muted)', marginBottom: 8 }}>
              Learning Loop
            </div>
            <div style={{ display: 'grid', gap: 6 }}>
              {topRisks.slice(0, 3).map((a) => (
                <div key={`feedback-${a.id}`} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-muted)' }}>{a.service_name}</span>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button className="btn" style={{ fontSize: '0.64rem', padding: '4px 8px' }} onClick={() => setFeedback((prev) => ({ ...prev, [a.id]: 'useful' }))}>Useful</button>
                    <button className="btn" style={{ fontSize: '0.64rem', padding: '4px 8px' }} onClick={() => setFeedback((prev) => ({ ...prev, [a.id]: 'wrong' }))}>Wrong</button>
                  </div>
                </div>
              ))}
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--c-text-faint)', marginTop: 8 }}>
              feedback captured: {Object.keys(feedback).length}
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
        <div className="panel" style={{ padding: '16px 18px' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.9rem', color: 'var(--c-text)', marginBottom: 10 }}>SLA Breach Forecast</div>
          {loadingAlerts && slaRows.length === 0 && (
            <div style={{ display: 'grid', gap: 8 }}>
              {[0, 1].map((i) => (
                <div key={i} style={{ border: '1px solid var(--c-border)', borderRadius: 8, background: 'var(--c-surface-2)', padding: '10px 12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                    <div className="skeleton-shimmer" style={{ height: 14, width: 90, borderRadius: 4 }} />
                    <div className="skeleton-shimmer" style={{ height: 14, width: 80, borderRadius: 4 }} />
                  </div>
                  <div className="skeleton-shimmer" style={{ height: 11, width: '70%', borderRadius: 4 }} />
                </div>
              ))}
            </div>
          )}
          {!loadingAlerts && slaRows.length === 0 && <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-text-faint)' }}>SLA forecast appears when predictive alerts are linked to recent investigations.</div>}
          <div style={{ display: 'grid', gap: 8 }}>
            {slaRows.map((row) => {
              const breachMins = row.estimated_breach_in_seconds == null ? null : Math.round(row.estimated_breach_in_seconds / 60)
              return (
                <div key={`${row.service_name}-${row.environment}`} style={{ border: '1px solid var(--c-border)', borderRadius: 8, background: 'var(--c-surface-2)', padding: '10px 12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.78rem', color: 'var(--c-text)' }}>{row.service_name}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.66rem', color: row.breached ? 'var(--c-red)' : 'var(--c-warning)' }}>
                      {row.breached ? 'Breached' : breachMins == null ? 'No breach ETA' : `${breachMins}m to breach`}
                    </span>
                  </div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.67rem', color: 'var(--c-text-muted)' }}>
                    error rate {row.current_error_rate.toFixed(3)} · remaining budget {Math.max(0, Math.round(row.remaining_budget_seconds / 60))}m
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        <div className="panel" style={{ padding: '16px 18px' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.9rem', color: 'var(--c-text)', marginBottom: 10 }}>Service Risk Ranking</div>
          <div style={{ display: 'grid', gap: 8 }}>
            {loadingAlerts && scoreRows.length === 0 ? (
              [0, 1, 2].map((i) => (
                <div key={i} style={{ border: '1px solid var(--c-border)', borderRadius: 8, background: 'var(--c-surface-2)', padding: '10px 12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <div className="skeleton-shimmer" style={{ height: 14, width: 90, borderRadius: 4 }} />
                    <div className="skeleton-shimmer" style={{ height: 14, width: 50, borderRadius: 4 }} />
                  </div>
                  <div className="skeleton-shimmer" style={{ height: 11, width: '70%', borderRadius: 4 }} />
                </div>
              ))
            ) : (
            scoreRows.slice(0, 6).map((row) => (
              <div key={row.service} style={{ border: '1px solid var(--c-border)', borderRadius: 8, background: 'var(--c-surface-2)', padding: '10px 12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.78rem', color: 'var(--c-text)' }}>{row.service}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.72rem', color: (row.data?.score ?? 0) < 50 ? 'var(--c-red)' : (row.data?.score ?? 0) < 75 ? 'var(--c-warning)' : 'var(--c-green)' }}>
                    {row.data?.score ?? 0}/100
                  </span>
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.67rem', color: 'var(--c-text-muted)' }}>
                  {row.data?.label} · incidents {row.data?.total ?? 0} · avg MTTR {row.data?.avg_mttr_minutes ?? '—'}m
                </div>
              </div>
            ))
            )}
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div className="panel" style={{ padding: '16px 18px' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.9rem', color: 'var(--c-text)', marginBottom: 10 }}>What Changed Timeline</div>
          <div style={{ display: 'grid', gap: 7 }}>
            {loadingAlerts && timeline.length === 0 ? (
              [0, 1, 2].map((i) => (
                <div key={i} style={{ borderLeft: '2px solid var(--c-border)', paddingLeft: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 4 }}>
                    <div className="skeleton-shimmer" style={{ height: 12, width: 130, borderRadius: 4 }} />
                    <div className="skeleton-shimmer" style={{ height: 12, width: 60, borderRadius: 4 }} />
                  </div>
                  <div className="skeleton-shimmer" style={{ height: 10, width: '60%', borderRadius: 4 }} />
                </div>
              ))
            ) : (
            timeline.map((e) => (
              <div key={e.id} style={{ borderLeft: `2px solid ${e.kind === 'predictive' ? 'var(--c-warning)' : 'var(--c-info)'}`, paddingLeft: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <span style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: '0.76rem', color: 'var(--c-text)' }}>{e.title}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.64rem', color: 'var(--c-text-faint)' }}>{fmtTs(e.ts)}</span>
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-muted)' }}>{e.subtitle}</div>
              </div>
            ))
            )}
          </div>
        </div>

        <div className="panel" style={{ padding: '16px 18px' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.9rem', color: 'var(--c-text)', marginBottom: 10 }}>Remediation Outcome Simulator</div>
          {loadingAlerts && !bestPreview && (
            <div style={{ display: 'grid', gap: 8 }}>
              {[0, 1].map((i) => (
                <div key={i} style={{ border: '1px solid var(--c-border)', borderRadius: 8, background: 'var(--c-surface-2)', padding: '10px 12px' }}>
                  <div className="skeleton-shimmer" style={{ height: 14, width: 120, borderRadius: 4, marginBottom: 6 }} />
                  <div className="skeleton-shimmer" style={{ height: 10, width: '80%', borderRadius: 4, marginBottom: 6 }} />
                  <div className="skeleton-shimmer" style={{ height: 10, width: '50%', borderRadius: 4 }} />
                </div>
              ))}
            </div>
          )}
          {!loadingAlerts && !bestPreview && (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-text-faint)' }}>
              No live fix preview available yet. Trigger an investigation from a predictive signal to see simulation outcomes.
            </div>
          )}
          {bestPreview && (
            <>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.67rem', color: 'var(--c-text-muted)', marginBottom: 8 }}>
                {bestPreview.service_name} · replicas {bestPreview.current_replica_count} · throttle {bestPreview.cpu_throttle_events_per_min}/min
              </div>
              <div style={{ display: 'grid', gap: 8 }}>
                {bestPreview.items.slice(0, 3).map((item, idx) => (
                  <div key={`${item.title}-${idx}`} style={{ border: '1px solid var(--c-border)', borderRadius: 8, background: 'var(--c-surface-2)', padding: '10px 12px' }}>
                    <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.75rem', color: 'var(--c-text)', marginBottom: 4 }}>{item.title}</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.64rem', color: 'var(--c-text-faint)', marginBottom: 4 }}>{item.action_type}</div>
                    <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.72rem', color: 'var(--c-text-dim)' }}>
                      {item.proposed_command}
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-info)', marginTop: 5 }}>
                      predicted: {item.predicted_after_state}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      <div className="panel" style={{ marginTop: 12, padding: '14px 16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.76rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--c-text-muted)' }}>Topology Stress Snapshot</div>
            {loadingAlerts ? (
              <div className="skeleton-shimmer" style={{ height: 12, width: 160, borderRadius: 4, marginTop: 4 }} />
            ) : (
            <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.78rem', color: 'var(--c-text-dim)' }}>
              {hotPods.length} hot pod{hotPods.length !== 1 ? 's' : ''} out of {podNodes.length} observed pod{podNodes.length !== 1 ? 's' : ''}
            </div>
            )}
          </div>
          <Link to="/" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-signal)', textDecoration: 'none' }}>
            Back to Dashboard →
          </Link>
        </div>
      </div>

      <SignalDetailDrawer alert={drawerAlert} open={drawerAlert !== null} onClose={closeDrawer} />
    </Layout>
  )
}
