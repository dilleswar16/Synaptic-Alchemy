import { useMemo, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import Layout from '../components/Layout'
import { HeroAlertSection } from '../components/HeroAlertSection'
import { SignalDetailDrawer } from '../components/SignalDetailDrawer'
import { RiskScoreGauge } from '../components/RiskScoreGauge'
import { MiniSparkline } from '../components/MiniSparkline'
import { buildDemoAlerts } from '../data/demoAlerts'
import { useServiceNames } from '../hooks/useApplicationData'
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
import { timeAgo } from '../utils/time'

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
    const ratio = a.threshold_value > 0 ? Math.min(1.3, a.signal_value / a.threshold_value) : 0.5
    // No breach projected + far from threshold → much lower proximity
    const proximity = mins == null
      ? (ratio >= 0.8 ? 0.5 : ratio >= 0.5 ? 0.3 : 0.1)
      : mins <= 0 ? 1 : Math.max(0.15, 1 - Math.min(mins, 240) / 240)
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

// ── Pure severity helpers (no component state dependency) ──────────────
const sevColor = (s: string) =>
  s === 'critical' ? 'var(--c-red)' : s === 'high' ? 'var(--c-warning)' : s === 'medium' ? '#e0a040' : 'var(--c-info)'

const sevIcon = (t: string) =>
  t.includes('cpu') ? '\u26A1'
    : t.includes('memory') || t.includes('oom') ? '\uD83E\uDDE0'
    : t.includes('error') || t.includes('5xx') ? '\uD83D\uDEA8'
    : t.includes('latency') ? '\u23F1\uFE0F'
    : t.includes('disk') ? '\uD83D\uDCBE'
    : '\u26A0\uFE0F'

export default function PredictiveAnalyticsPage() {
  const queryClient = useQueryClient()
  const { names: registeredServices } = useServiceNames()
  const [feedback, setFeedback] = useState<Record<string, 'useful' | 'wrong'>>({})
  const [demoMode, setDemoMode] = useState(false)

  const { data: rawAlerts = [], isLoading: loadingAlerts } = useQuery({
    queryKey: ['predictive-alerts', 'page'],
    queryFn: () => fetchPredictiveAlerts(true),
    refetchInterval: 45_000,
    staleTime: 20_000,
  })

  const alerts: PredictiveAlert[] = demoMode ? buildDemoAlerts(registeredServices) : rawAlerts

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
    const merged = Array.from(new Set([...registeredServices, ...fromAlerts, ...fromRecent]))
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
      subtitle: `${i.trigger_source.replaceAll('_', ' ')} · ${timeAgo(i.completed_at ?? i.created_at)}`,
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

  const podNodes = useMemo(
    () => (topology?.nodes ?? []).filter((n) => n.kind.toLowerCase().includes('pod')),
    [topology],
  )
  const hotPods = useMemo(
    () => podNodes.filter((n) => (n.cpu_utilization_pct ?? 0) >= 85 || (n.memory_utilization_pct ?? 0) >= 85),
    [podNodes],
  )

  const [drawerAlert, setDrawerAlert] = useState<PredictiveAlert | null>(null)
  const closeDrawer = useCallback(() => setDrawerAlert(null), [])

  const [heroService, setHeroService] = useState<string | null>(null)

  const heroServices = useMemo(() => {
    return Array.from(new Set(topRisks.map((a) => a.service_name)))
  }, [topRisks])

  const heroAlert = useMemo(() => {
    if (heroService) return topRisks.find((a) => a.service_name === heroService) ?? topRisks[0] ?? null
    return topRisks[0] ?? null
  }, [heroService, topRisks])

  const isLoading = loadingAlerts && !demoMode

  return (
    <Layout>
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.68rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--c-text-muted)', marginBottom: 4 }}>Intelligence Layer</div>
          <h1 style={{ margin: 0, fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '1.9rem', letterSpacing: '-0.03em', color: 'var(--c-text)' }}>
            Predictive Analytics
          </h1>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            className={demoMode ? 'btn btn-primary' : 'btn'}
            onClick={() => setDemoMode((v) => !v)}
            style={{ fontSize: '0.72rem', ...(demoMode ? { boxShadow: '0 0 16px color-mix(in srgb, var(--c-signal) 40%, transparent)', animation: 'pulse 2s ease-in-out infinite' } : {}) }}
          >
            {demoMode ? '\u25CF LIVE DEMO' : '\u25CB Demo Mode'}
          </button>
          <button className="btn" onClick={() => queryClient.invalidateQueries({ queryKey: ['predictive-alerts'] })} style={{ fontSize: '0.72rem' }}>Refresh</button>
          <Link to="/corvin" className="btn btn-primary" style={{ fontSize: '0.72rem', textDecoration: 'none' }}>Ask Corvin</Link>
        </div>
      </div>

      {/* ── Hero service selector ───────────────────────────────────────── */}
      {!isLoading && heroServices.length > 1 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
          <button
            onClick={() => setHeroService(null)}
            style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.66rem', fontWeight: 700,
              padding: '4px 12px', borderRadius: 999, cursor: 'pointer',
              background: heroService === null ? 'var(--c-signal)' : 'var(--c-surface-2)',
              color: heroService === null ? '#fff' : 'var(--c-text-muted)',
              border: `1px solid ${heroService === null ? 'var(--c-signal)' : 'var(--c-border-hi)'}`,
              transition: 'all 0.15s',
            }}
          >
            Top Risk
          </button>
          {heroServices.map((svc) => (
            <button
              key={svc}
              onClick={() => setHeroService(svc)}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.66rem', fontWeight: 700,
                padding: '4px 12px', borderRadius: 999, cursor: 'pointer',
                background: heroService === svc ? 'var(--c-signal)' : 'var(--c-surface-2)',
                color: heroService === svc ? '#fff' : 'var(--c-text-muted)',
                border: `1px solid ${heroService === svc ? 'var(--c-signal)' : 'var(--c-border-hi)'}`,
                transition: 'all 0.15s',
              }}
            >
              {svc}
            </button>
          ))}
        </div>
      )}

      {/* ── Hero ────────────────────────────────────────────────────────── */}
      <HeroAlertSection alert={heroAlert} loading={isLoading} />

      {/* ── KPI Row: Gauge + Cards ──────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '150px 1fr', gap: 12, marginBottom: 16 }}>
        <div className="panel" style={{ padding: '14px 12px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', borderTop: `2px solid ${band === 'critical' ? 'var(--c-red)' : band === 'high' ? 'var(--c-warning)' : band === 'watch' ? 'var(--c-info)' : 'var(--c-green)'}` }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.58rem', textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--c-text-muted)', marginBottom: 6 }}>Risk Score</div>
          <RiskScoreGauge score={riskScore} size={105} loading={isLoading} />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
          {[
            { label: 'Signals', value: isLoading ? null : alerts.length, sub: 'active', color: 'var(--c-text)', spark: demoMode ? [1, 2, 2, 3, 4, 5, 6] : [alerts.length, alerts.length] },
            { label: 'Actionable', value: isLoading ? null : actionable.length, sub: 'near-breach', color: 'var(--c-signal)', spark: demoMode ? [0, 1, 1, 2, 3, 3, 4] : [actionable.length, actionable.length] },
            { label: 'Avg Breach', value: isLoading ? null : (avgBreachMins == null ? '\u2014' : `${avgBreachMins}m`), sub: 'ETA signals', color: 'var(--c-warning)', spark: demoMode ? [120, 95, 80, 60, 45, 30, 27] : [] },
            { label: 'Investigated', value: isLoading ? null : `${conversionPct}%`, sub: 'converted', color: 'var(--c-green)', spark: demoMode ? [5, 12, 18, 25, 30, 33, 33] : [] },
          ].map((m) => (
            <div key={m.label} className="panel" style={{ padding: '12px', borderTop: `2px solid ${m.value == null ? 'var(--c-border)' : m.color}` }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.56rem', textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--c-text-muted)', marginBottom: 6 }}>{m.label}</div>
              {m.value == null ? (
                <div className="skeleton-shimmer" style={{ height: 26, borderRadius: 6, marginBottom: 4 }} />
              ) : (
                <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 6, marginBottom: 2 }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 800, fontSize: '1.4rem', lineHeight: 1, color: m.color }}>{m.value}</div>
                  {m.spark.length >= 2 && <MiniSparkline data={m.spark} width={56} height={22} color={m.color} />}
                </div>
              )}
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.56rem', color: 'var(--c-text-faint)' }}>{m.sub}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Row 2: Emerging Risks + Confidence ──────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 0.6fr', gap: 12, marginBottom: 14 }}>
        {/* Emerging Risks */}
        <div className="panel" style={{ padding: '16px 18px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.88rem', color: 'var(--c-text)' }}>Emerging Risks</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--c-text-faint)' }}>{topRisks.length} signals</div>
          </div>
          {isLoading && (
            <div style={{ display: 'grid', gap: 6 }}>
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton-shimmer" style={{ height: 52, borderRadius: 8 }} />
              ))}
            </div>
          )}
          {!isLoading && topRisks.length === 0 && <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-text-faint)' }}>No signals detected.</div>}
          <div style={{ display: 'grid', gap: 6 }}>
            {topRisks.map((a) => {
              const sc = sevColor(a.severity)
              const pct = Math.min((a.signal_value / a.threshold_value) * 100, 100)
              return (
                <div
                  key={a.id}
                  onClick={() => setDrawerAlert(a)}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '4px 1fr',
                    borderRadius: 8,
                    overflow: 'hidden',
                    background: 'var(--c-surface-2)',
                    border: '1px solid var(--c-border)',
                    cursor: 'pointer',
                    transition: 'border-color 0.15s, box-shadow 0.15s, transform 0.15s',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.borderColor = sc; e.currentTarget.style.boxShadow = `0 0 16px color-mix(in srgb, ${sc} 20%, transparent)`; e.currentTarget.style.transform = 'translateY(-1px)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--c-border)'; e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.transform = 'none' }}
                >
                  {/* Severity color strip */}
                  <div style={{ background: sc }} />
                  <div style={{ padding: '10px 12px 10px 10px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 3 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ fontSize: '0.82rem' }}>{sevIcon(a.alert_type)}</span>
                        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.78rem', color: 'var(--c-text)' }}>{a.service_name}</span>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.56rem', padding: '1px 5px', borderRadius: 999, border: `1px solid ${sc}`, color: sc, fontWeight: 700, textTransform: 'uppercase' }}>{a.severity}</span>
                      </div>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--c-warning)', fontWeight: 600 }}>{formatEta(a.estimated_breach_at)}</span>
                    </div>
                    <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.73rem', color: 'var(--c-text-dim)', marginBottom: 6, lineHeight: 1.3 }}>{a.title}</div>
                    {/* Signal strength bar */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ flex: 1, height: 4, borderRadius: 999, background: 'var(--c-surface-3)', overflow: 'hidden' }}>
                        <div style={{ width: `${pct}%`, height: '100%', borderRadius: 999, background: `linear-gradient(90deg, ${sc}, color-mix(in srgb, ${sc} 60%, var(--c-warning)))`, transition: 'width 0.5s ease' }} />
                      </div>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.56rem', color: sc, fontWeight: 700, minWidth: 32, textAlign: 'right' }}>{a.signal_value.toFixed(0)}%</span>
                    </div>
                    {/* Impact badges */}
                    {(a.blast_radius_users > 0 || a.change_correlation) && (
                      <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
                        {a.blast_radius_users > 0 && (
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.56rem', color: 'var(--c-red)', background: 'var(--c-error-bg)', padding: '1px 6px', borderRadius: 4, fontWeight: 600 }}>
                            {a.blast_radius_users.toLocaleString()} users impacted
                          </span>
                        )}
                        {a.change_correlation && (
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.56rem', color: 'var(--c-signal)', background: 'var(--c-signal-light)', padding: '1px 6px', borderRadius: 4 }}>
                            {a.change_correlation.length > 50 ? a.change_correlation.slice(0, 50) + '...' : a.change_correlation}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Confidence + Learning */}
        <div className="panel" style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.88rem', color: 'var(--c-text)', marginBottom: 14 }}>Signal Confidence</div>
          {isLoading ? (
            <div className="skeleton-shimmer" style={{ width: 100, height: 100, borderRadius: '50%', margin: '0 auto 16px' }} />
          ) : (
            <>
              {/* Confidence donut */}
              <div style={{ position: 'relative', width: 110, height: 110, margin: '0 auto 16px' }}>
                <svg width={110} height={110} viewBox="0 0 110 110">
                  {(['low', 'medium', 'high'] as const).map((c, i) => {
                    const total = Math.max(alerts.length, 1)
                    const pct = confidenceBreakdown[c] / total
                    const prevPcts = (['low', 'medium', 'high'] as const).slice(0, i).reduce((s, k) => s + confidenceBreakdown[k] / total, 0)
                    const r = 45
                    const circ = 2 * Math.PI * r
                    const color = c === 'high' ? 'var(--c-green)' : c === 'medium' ? 'var(--c-warning)' : 'var(--c-red)'
                    return (
                      <circle key={c} cx={55} cy={55} r={r} fill="none" stroke={color} strokeWidth={10}
                        strokeDasharray={`${pct * circ} ${circ}`}
                        strokeDashoffset={-prevPcts * circ}
                        style={{ transform: 'rotate(-90deg)', transformOrigin: '55px 55px', transition: 'stroke-dasharray 0.6s ease' }}
                      />
                    )
                  })}
                </svg>
                <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 900, fontSize: '1.1rem', color: 'var(--c-text)', lineHeight: 1 }}>{alerts.length}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.52rem', color: 'var(--c-text-faint)', letterSpacing: '0.08em' }}>SIGNALS</div>
                </div>
              </div>
              {/* Legend */}
              <div style={{ display: 'grid', gap: 6, marginBottom: 12 }}>
                {(['high', 'medium', 'low'] as const).map((c) => {
                  const color = c === 'high' ? 'var(--c-green)' : c === 'medium' ? 'var(--c-warning)' : 'var(--c-red)'
                  return (
                    <div key={c} style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--c-text-muted)' }}>
                      <div style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
                      <span style={{ flex: 1 }}>{c.toUpperCase()}</span>
                      <span style={{ fontWeight: 700, color: 'var(--c-text)' }}>{confidenceBreakdown[c]}</span>
                    </div>
                  )
                })}
              </div>
            </>
          )}
          {/* Learning Loop */}
          <div style={{ borderTop: '1px solid var(--c-border)', paddingTop: 12, marginTop: 'auto' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.56rem', textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--c-text-faint)', marginBottom: 8 }}>Feedback Loop</div>
            {topRisks.slice(0, 3).map((a) => (
              <div key={`fb-${a.id}`} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--c-text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 100 }}>{a.service_name}</span>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button className="btn" style={{ fontSize: '0.56rem', padding: '2px 6px', ...(feedback[a.id] === 'useful' ? { background: 'var(--c-success-bg)', borderColor: 'var(--c-green)', color: 'var(--c-green)' } : {}) }} onClick={() => setFeedback((p) => ({ ...p, [a.id]: 'useful' }))}>
                    {feedback[a.id] === 'useful' ? '\u2713' : '\u2191'}
                  </button>
                  <button className="btn" style={{ fontSize: '0.56rem', padding: '2px 6px', ...(feedback[a.id] === 'wrong' ? { background: 'var(--c-error-bg)', borderColor: 'var(--c-red)', color: 'var(--c-red)' } : {}) }} onClick={() => setFeedback((p) => ({ ...p, [a.id]: 'wrong' }))}>
                    {feedback[a.id] === 'wrong' ? '\u2717' : '\u2193'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Row 3: SLA + Service Ranking ─────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
        {/* SLA Breach Forecast */}
        <div className="panel" style={{ padding: '16px 18px' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.88rem', color: 'var(--c-text)', marginBottom: 12 }}>SLA Breach Forecast</div>
          {isLoading && slaRows.length === 0 && (
            <div style={{ display: 'grid', gap: 6 }}>{[0, 1].map((i) => <div key={i} className="skeleton-shimmer" style={{ height: 52, borderRadius: 8 }} />)}</div>
          )}
          {!isLoading && slaRows.length === 0 && (
            <div style={{ padding: '20px 16px', borderRadius: 8, background: 'var(--c-surface-2)', border: '1px dashed var(--c-border)', textAlign: 'center' }}>
              <div style={{ fontSize: '1.4rem', marginBottom: 6 }}>{'\u2705'}</div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.82rem', color: 'var(--c-green)', marginBottom: 4 }}>Within SLA Budget</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--c-text-faint)' }}>Forecasts appear when signals are linked to investigations</div>
            </div>
          )}
          <div style={{ display: 'grid', gap: 6 }}>
            {slaRows.map((row) => {
              const breachMins = row.estimated_breach_in_seconds == null ? null : Math.round(row.estimated_breach_in_seconds / 60)
              const isActiveIssue = row.current_error_rate > 0.001
              const urgency = row.breached ? (isActiveIssue ? 'var(--c-red)' : 'var(--c-warning)') : breachMins != null && breachMins < 30 ? 'var(--c-warning)' : 'var(--c-green)'
              const budgetPct = Math.max(0, Math.min(100, (row.remaining_budget_seconds / Math.max(row.monthly_budget_seconds, 1)) * 100))
              const statusLabel = row.breached
                ? (isActiveIssue ? 'BREACHED' : 'BUDGET SPENT')
                : breachMins == null ? 'Safe' : `${breachMins}m`
              return (
                <div key={`${row.service_name}-${row.environment}`} style={{ display: 'grid', gridTemplateColumns: '4px 1fr', borderRadius: 8, overflow: 'hidden', background: 'var(--c-surface-2)', border: '1px solid var(--c-border)' }}>
                  <div style={{ background: urgency }} />
                  <div style={{ padding: '10px 12px 10px 10px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                      <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.76rem', color: 'var(--c-text)' }}>{row.service_name}</span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', fontWeight: 700, color: urgency }}>
                        {statusLabel}
                      </span>
                    </div>
                    <div style={{ height: 4, borderRadius: 999, background: 'var(--c-surface-3)', overflow: 'hidden', marginBottom: 4 }}>
                      <div style={{ width: `${budgetPct}%`, height: '100%', borderRadius: 999, background: urgency, transition: 'width 0.5s ease' }} />
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.58rem', color: 'var(--c-text-faint)' }}>
                      err {row.current_error_rate.toFixed(3)} | budget {Math.max(0, Math.round(row.remaining_budget_seconds / 60))}m
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Service Risk Ranking */}
        <div className="panel" style={{ padding: '16px 18px' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.88rem', color: 'var(--c-text)', marginBottom: 12 }}>Service Health Ranking</div>
          {isLoading && scoreRows.length === 0 ? (
            <div style={{ display: 'grid', gap: 6 }}>{[0, 1, 2].map((i) => <div key={i} className="skeleton-shimmer" style={{ height: 48, borderRadius: 8 }} />)}</div>
          ) : (
            <div style={{ display: 'grid', gap: 8 }}>
              {scoreRows.slice(0, 6).map((row, idx) => {
                const score = row.data?.score ?? 0
                const barColor = score < 50 ? 'var(--c-red)' : score < 75 ? 'var(--c-warning)' : 'var(--c-green)'
                return (
                  <div key={row.service}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.58rem', color: 'var(--c-text-faint)', width: 14 }}>#{idx + 1}</span>
                        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.76rem', color: 'var(--c-text)' }}>{row.service}</span>
                      </div>
                      <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 800, fontSize: '0.82rem', color: barColor }}>{score}</span>
                    </div>
                    <div style={{ height: 6, borderRadius: 999, background: 'var(--c-surface-3)', overflow: 'hidden', marginBottom: 3 }}>
                      <div style={{ width: `${score}%`, height: '100%', borderRadius: 999, background: `linear-gradient(90deg, color-mix(in srgb, ${barColor} 60%, transparent), ${barColor})`, transition: 'width 0.6s ease' }} />
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.54rem', color: 'var(--c-text-faint)' }}>
                      {row.data?.label} | {row.data?.total ?? 0} incidents | MTTR {row.data?.avg_mttr_minutes ?? '?'}m
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* ── Row 4: Timeline + Remediation ───────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
        {/* Timeline */}
        <div className="panel" style={{ padding: '16px 18px' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.88rem', color: 'var(--c-text)', marginBottom: 12 }}>Event Timeline</div>
          {isLoading && timeline.length === 0 ? (
            <div style={{ display: 'grid', gap: 8 }}>{[0, 1, 2].map((i) => <div key={i} className="skeleton-shimmer" style={{ height: 36, borderRadius: 6 }} />)}</div>
          ) : (
            <div style={{ position: 'relative' }}>
              {/* Vertical connector line */}
              {timeline.length > 1 && (
                <div style={{ position: 'absolute', left: 5, top: 6, bottom: 6, width: 1, background: 'var(--c-border)' }} />
              )}
              <div style={{ display: 'grid', gap: 4 }}>
                {timeline.map((e) => {
                  const dotColor = e.kind === 'predictive' ? 'var(--c-warning)' : 'var(--c-info)'
                  return (
                    <div key={e.id} style={{ display: 'grid', gridTemplateColumns: '12px 1fr auto', gap: 8, alignItems: 'start', padding: '4px 0' }}>
                      {/* Dot */}
                      <div style={{ width: 10, height: 10, borderRadius: '50%', background: dotColor, marginTop: 2, boxShadow: `0 0 6px ${dotColor}`, position: 'relative', zIndex: 1 }} />
                      {/* Content */}
                      <div>
                        <div style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: '0.72rem', color: 'var(--c-text)', lineHeight: 1.3 }}>{e.title}</div>
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.58rem', color: 'var(--c-text-faint)' }}>{e.subtitle}</div>
                      </div>
                      {/* Timestamp */}
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.56rem', color: 'var(--c-text-faint)', whiteSpace: 'nowrap' }}>{timeAgo(e.ts)}</div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>

        {/* Remediation Simulator */}
        <div className="panel" style={{ padding: '16px 18px' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.88rem', color: 'var(--c-text)', marginBottom: 12 }}>Remediation Preview</div>
          {isLoading && !bestPreview && (
            <div style={{ display: 'grid', gap: 6 }}>{[0, 1].map((i) => <div key={i} className="skeleton-shimmer" style={{ height: 60, borderRadius: 8 }} />)}</div>
          )}
          {!isLoading && !bestPreview && (
            <div style={{ padding: '24px 16px', borderRadius: 8, background: 'var(--c-surface-2)', border: '1px dashed var(--c-border)', textAlign: 'center' }}>
              <div style={{ fontSize: '1.4rem', marginBottom: 6 }}>{'\uD83D\uDD2E'}</div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.82rem', color: 'var(--c-text-dim)', marginBottom: 4 }}>No Simulations Yet</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--c-text-faint)' }}>Investigate a signal to generate fix previews</div>
            </div>
          )}
          {bestPreview && (
            <>
              <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', padding: '2px 8px', borderRadius: 999, background: 'var(--c-surface-3)', color: 'var(--c-text-muted)' }}>{bestPreview.service_name}</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', padding: '2px 8px', borderRadius: 999, background: 'var(--c-surface-3)', color: 'var(--c-text-muted)' }}>replicas: {bestPreview.current_replica_count}</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', padding: '2px 8px', borderRadius: 999, background: 'var(--c-surface-3)', color: 'var(--c-text-muted)' }}>throttle: {bestPreview.cpu_throttle_events_per_min}/min</span>
              </div>
              <div style={{ display: 'grid', gap: 8 }}>
                {bestPreview.items.slice(0, 3).map((item, idx) => (
                  <div key={`${item.title}-${idx}`} style={{ borderRadius: 8, background: 'var(--c-surface-2)', border: '1px solid var(--c-border)', overflow: 'hidden' }}>
                    <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--c-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.72rem', color: 'var(--c-text)' }}>{item.title}</span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.56rem', padding: '1px 6px', borderRadius: 4, background: 'var(--c-info-bg)', color: 'var(--c-info)' }}>{item.action_type}</span>
                    </div>
                    <div style={{ padding: '8px 12px' }}>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.66rem', color: 'var(--c-text-dim)', marginBottom: 6, lineHeight: 1.4 }}>{item.proposed_command}</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--c-green)', boxShadow: '0 0 4px var(--c-green)' }} />
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--c-green)' }}>{item.predicted_after_state}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* ── Row 5: Topology ─────────────────────────────────────────────── */}
      <div className="panel" style={{ padding: '16px 18px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.88rem', color: 'var(--c-text)' }}>Infrastructure Topology</div>
            {!isLoading && (
              <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.58rem', color: hotPods.length > 0 ? 'var(--c-red)' : 'var(--c-green)', fontWeight: 700 }}>
                  {hotPods.length} hot
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.58rem', color: 'var(--c-text-faint)' }}>/ {podNodes.length} pods</span>
              </div>
            )}
          </div>
          <Link to="/" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.64rem', color: 'var(--c-signal)', textDecoration: 'none' }}>Dashboard {'\u2192'}</Link>
        </div>
        {isLoading && <div className="skeleton-shimmer" style={{ height: 40, borderRadius: 8 }} />}
        {!isLoading && podNodes.length === 0 && (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text-faint)', textAlign: 'center', padding: 12 }}>No pod telemetry available</div>
        )}
        {!isLoading && podNodes.length > 0 && (
          <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
            {podNodes.slice(0, 30).map((pod, i) => {
              const cpu = pod.cpu_utilization_pct ?? 0
              const mem = pod.memory_utilization_pct ?? 0
              const peak = Math.max(cpu, mem)
              const color = peak >= 85 ? 'var(--c-red)' : peak >= 60 ? 'var(--c-warning)' : 'var(--c-green)'
              const label = pod.label ?? `pod-${i}`
              return (
                <div
                  key={pod.id ?? i}
                  title={`${label}\nCPU: ${cpu.toFixed(0)}%  MEM: ${mem.toFixed(0)}%`}
                  style={{
                    width: 34, height: 34, borderRadius: 6,
                    background: `color-mix(in srgb, ${color} 15%, var(--c-surface-2))`,
                    border: `1px solid color-mix(in srgb, ${color} 50%, var(--c-border))`,
                    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 1,
                    cursor: 'default',
                    ...(peak >= 85 ? { animation: 'pulse 2s ease-in-out infinite', boxShadow: `0 0 10px color-mix(in srgb, ${color} 30%, transparent)` } : {}),
                  }}
                >
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.52rem', fontWeight: 700, color, lineHeight: 1 }}>{cpu.toFixed(0)}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.44rem', color: 'var(--c-text-faint)', lineHeight: 1 }}>{mem.toFixed(0)}</span>
                </div>
              )
            })}
          </div>
        )}
        {/* Pod legend */}
        {!isLoading && podNodes.length > 0 && (
          <div style={{ display: 'flex', gap: 12, marginTop: 8, justifyContent: 'flex-end' }}>
            {[{ label: 'Hot (>85%)', color: 'var(--c-red)' }, { label: 'Warm (>60%)', color: 'var(--c-warning)' }, { label: 'Cool', color: 'var(--c-green)' }].map((l) => (
              <div key={l.label} style={{ display: 'flex', alignItems: 'center', gap: 4, fontFamily: 'var(--font-mono)', fontSize: '0.52rem', color: 'var(--c-text-faint)' }}>
                <div style={{ width: 6, height: 6, borderRadius: 2, background: l.color }} />{l.label}
              </div>
            ))}
          </div>
        )}
      </div>

      <SignalDetailDrawer alert={drawerAlert} open={drawerAlert !== null} onClose={closeDrawer} />
    </Layout>
  )
}
