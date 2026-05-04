import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import Layout from '../components/Layout'
import {
  fetchInvestigationStats,
  fetchInvestigations,
  type InvestigationStats,
  type InvestigationSummary,
} from '../api/client'

// ── Helpers ───────────────────────────────────────────────────────────────────

function timeAgo(date: Date): string {
  const s = Math.floor((Date.now() - date.getTime()) / 1000)
  if (s < 60)    return `${s}s ago`
  if (s < 3600)  return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return         `${Math.floor(s / 86400)}d ago`
}

function fmtTs(iso: string) {
  try { return new Date(iso).toISOString().substring(11, 19) + 'Z' }
  catch { return '—' }
}

// ── Stat counter ──────────────────────────────────────────────────────────────

function BigCounter({
  label,
  value,
  sub,
  color = 'var(--c-text)',
  delay = 0,
}: {
  label: string
  value: string | number
  sub?: string
  color?: string
  delay?: number
}) {
  return (
    <div className="animate-count-up" style={{ animationDelay: `${delay}ms` }}>
      <div style={{
        fontFamily: 'var(--font-display)',
        fontSize: '0.68rem',
        fontWeight: 700,
        letterSpacing: '0.14em',
        textTransform: 'uppercase',
        color: 'var(--c-text-muted)',
        marginBottom: 6,
      }}>
        {label}
      </div>
      <div style={{
        fontFamily: 'var(--font-mono)',
        fontSize: '3.5rem',
        fontWeight: 700,
        color,
        lineHeight: 1,
        letterSpacing: '-0.02em',
      }}>
        {value}
      </div>
      {sub && (
        <div style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '0.68rem',
          color: 'var(--c-text-faint)',
          marginTop: 4,
          letterSpacing: '0.04em',
        }}>
          {sub}
        </div>
      )}
    </div>
  )
}

// ── Metric card ───────────────────────────────────────────────────────────────

function MetricCard({
  label,
  value,
  sub,
  delay = 0,
}: {
  label: string
  value: string | number
  sub?: string
  delay?: number
}) {
  return (
    <div className="metric-card animate-fade-up scan-sweep" style={{ animationDelay: `${delay}ms`, overflow: 'hidden' }}>
      <div style={{
        fontFamily: 'var(--font-display)',
        fontSize: '0.62rem',
        fontWeight: 700,
        letterSpacing: '0.14em',
        textTransform: 'uppercase',
        color: 'var(--c-text-muted)',
      }}>
        {label}
      </div>
      <div style={{
        fontFamily: 'var(--font-mono)',
        fontSize: '1.8rem',
        fontWeight: 700,
        color: 'var(--c-text)',
        lineHeight: 1.1,
        letterSpacing: '-0.01em',
        marginTop: 4,
      }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-faint)', marginTop: 2 }}>
          {sub}
        </div>
      )}
    </div>
  )
}

// ── Stacked bar ───────────────────────────────────────────────────────────────

interface SegmentProps {
  label: string
  value: number
  total: number
  color: string
}

function StackedBar({ segments }: { segments: SegmentProps[] }) {
  const total = segments.reduce((s, seg) => s + seg.value, 0)
  return (
    <div>
      {/* Bar */}
      <div style={{ height: 6, borderRadius: 2, background: 'var(--c-surface-3)', display: 'flex', overflow: 'hidden', marginBottom: 10 }}>
        {segments.map((seg, i) => (
          <div key={i} style={{
            width: `${total > 0 ? (seg.value / total) * 100 : 0}%`,
            background: seg.color,
            transition: 'width 0.6s ease',
          }} />
        ))}
      </div>
      {/* Legend */}
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
        {segments.map((seg, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <div style={{ width: 8, height: 8, borderRadius: 1, background: seg.color, flexShrink: 0 }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              {seg.label}
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text)', fontWeight: 600 }}>
              {seg.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Log row ───────────────────────────────────────────────────────────────────

const STATUS_CLS: Record<string, string> = {
  pending: 'badge-pending',
  approved: 'badge-approved',
  rejected: 'badge-rejected',
  executed: 'badge-executed',
}

function LogRow({ inv, index }: { inv: InvestigationSummary & { approval_status?: string }; index: number }) {
  const status = inv.approval_status ?? 'pending'
  const ts = new Date(inv.completed_at ?? inv.created_at)
  return (
    <Link
      to={`/investigations/${inv.request_id}`}
      className="log-row animate-fade-up"
      style={{
        gridTemplateColumns: '80px 1fr 100px 110px 90px 20px',
        animationDelay: `${index * 35}ms`,
      }}
    >
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text-faint)', letterSpacing: '0.02em' }}>
        {fmtTs(inv.completed_at ?? inv.created_at)}
      </span>
      <div>
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.9rem', color: 'var(--c-text)' }}>
          {inv.service_name}
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-faint)', marginLeft: 8 }}>
          {inv.environment}
        </span>
      </div>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-muted)' }}>
        {inv.trigger_source.replace('_', ' ')}
      </span>
      <span className={`badge ${STATUS_CLS[status] ?? 'badge-pending'}`}>{status}</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-faint)', textAlign: 'right' }}>
        {timeAgo(ts)}
      </span>
      <span className="log-arrow" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--c-text-faint)', textAlign: 'right', transition: 'color 0.15s' }}>
        →
      </span>
    </Link>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { data: stats, isLoading: statsLoading, isError: statsError } = useQuery<InvestigationStats>({
    queryKey: ['stats'],
    queryFn: fetchInvestigationStats,
    refetchInterval: 30_000,
  })

  const { data: recent } = useQuery<(InvestigationSummary & { approval_status?: string })[]>({
    queryKey: ['investigations'],
    queryFn: fetchInvestigations,
    refetchInterval: 30_000,
  })

  const conf = stats?.confidence_distribution
  const appr = stats?.approval_distribution

  return (
    <Layout>
      {/* ── Page header ───────────────────────────────────────────────────── */}
      <div className="animate-fade-up" style={{ marginBottom: 32, display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 700, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--c-signal)', marginBottom: 4 }}>
            Operations Center
          </div>
          <h1 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: '2.2rem', fontWeight: 900, letterSpacing: '0.04em', color: 'var(--c-text)', lineHeight: 1 }}>
            SRE DASHBOARD
          </h1>
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-text-faint)', textAlign: 'right' }}>
          <div>auto-refresh 30s</div>
          {stats && <div style={{ color: 'var(--c-text-muted)', marginTop: 2 }}>{stats.total_investigations} total records</div>}
        </div>
      </div>

      {statsLoading && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--c-text-faint)', marginBottom: 24 }}>
          Loading…
        </div>
      )}
      {statsError && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--c-red)', marginBottom: 24 }}>
          ✗ Could not reach API — is the server running?
        </div>
      )}

      {stats && (
        <>
          {/* ── Hero row ──────────────────────────────────────────────────── */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 12 }}>
            {/* Today counter — full left accent */}
            <div className="panel-signal animate-count-up scan-sweep" style={{ padding: '24px 28px', overflow: 'hidden' }}>
              <BigCounter
                label="Investigations Today"
                value={stats.today_count}
                sub={recent && recent.length > 0 ? `last: ${timeAgo(new Date(recent[0].completed_at ?? recent[0].created_at))}` : 'none yet'}
                color="var(--c-signal)"
              />
            </div>
            {/* Total */}
            <div className="panel-signal animate-count-up scan-sweep" style={{ padding: '24px 28px', overflow: 'hidden', borderLeftColor: 'var(--c-green)', animationDelay: '60ms' }}>
              <BigCounter
                label="Total Investigations"
                value={stats.total_investigations}
                sub="all time"
                color="var(--c-green)"
                delay={60}
              />
            </div>
            {/* Auto-resolved */}
            <div className="panel-signal animate-count-up scan-sweep" style={{ padding: '24px 28px', overflow: 'hidden', borderLeftColor: 'var(--c-blue)', animationDelay: '120ms' }}>
              <BigCounter
                label="Auto-Resolved"
                value={`${Math.round(stats.auto_resolved_rate * 100)}%`}
                sub="reached executed state"
                color="var(--c-blue)"
                delay={120}
              />
            </div>
          </div>

          {/* ── Metric row ────────────────────────────────────────────────── */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 8, marginBottom: 16 }}>
            <MetricCard
              label="Avg MTTR"
              value={stats.avg_mttr_minutes != null ? `${stats.avg_mttr_minutes}m` : '—'}
              sub="pipeline time"
              delay={80}
            />
            <MetricCard
              label="High Confidence"
              value={conf && (conf.high + conf.medium + conf.low) > 0
                ? `${Math.round((conf.high / (conf.high + conf.medium + conf.low)) * 100)}%`
                : '—'}
              sub="of all RCAs"
              delay={100}
            />
            <MetricCard
              label="Executed"
              value={appr?.executed ?? '—'}
              sub="fix strategies run"
              delay={120}
            />
            <MetricCard
              label="Rejected"
              value={appr?.rejected ?? '—'}
              sub="investigations rejected"
              delay={140}
            />
          </div>

          {/* ── Charts row ────────────────────────────────────────────────── */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
            <div className="panel animate-fade-up-3" style={{ padding: '18px 20px' }}>
              <div className="section-label" style={{ marginBottom: 14 }}>RCA Confidence</div>
              {conf && (
                <StackedBar segments={[
                  { label: 'HIGH',   value: conf.high,   total: conf.high + conf.medium + conf.low, color: 'var(--c-green)'  },
                  { label: 'MEDIUM', value: conf.medium, total: conf.high + conf.medium + conf.low, color: 'var(--c-yellow)' },
                  { label: 'LOW',    value: conf.low,    total: conf.high + conf.medium + conf.low, color: 'var(--c-red)'    },
                ]} />
              )}
            </div>

            <div className="panel animate-fade-up-4" style={{ padding: '18px 20px' }}>
              <div className="section-label" style={{ marginBottom: 14 }}>Approval Pipeline</div>
              {appr && (
                <StackedBar segments={[
                  { label: 'EXECUTED', value: appr.executed, total: appr.pending + appr.approved + appr.executed + appr.rejected, color: 'var(--c-signal)'  },
                  { label: 'APPROVED', value: appr.approved, total: appr.pending + appr.approved + appr.executed + appr.rejected, color: 'var(--c-green)'   },
                  { label: 'PENDING',  value: appr.pending,  total: appr.pending + appr.approved + appr.executed + appr.rejected, color: 'var(--c-yellow)'  },
                  { label: 'REJECTED', value: appr.rejected, total: appr.pending + appr.approved + appr.executed + appr.rejected, color: 'var(--c-red)'     },
                ]} />
              )}
            </div>
          </div>

          {/* ── Recent services ───────────────────────────────────────────── */}
          {stats.recent_services.length > 0 && (
            <div className="panel animate-fade-up-5" style={{ padding: '14px 20px', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 16 }}>
              <span className="section-label" style={{ flexShrink: 0 }}>Active Services</span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {stats.recent_services.map(svc => (
                  <span key={svc} style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.72rem',
                    padding: '3px 10px',
                    borderRadius: 2,
                    background: 'rgba(249,115,22,0.08)',
                    border: '1px solid rgba(249,115,22,0.2)',
                    color: 'var(--c-signal)',
                    letterSpacing: '0.04em',
                  }}>
                    {svc}
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Recent investigations ──────────────────────────────────────── */}
      <div className="panel" style={{ overflow: 'hidden' }}>
        {/* Table header */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '80px 1fr 100px 110px 90px 20px',
          gap: 16,
          padding: '10px 14px',
          borderBottom: '1px solid var(--c-border-hi)',
          background: 'var(--c-surface-2)',
        }}>
          {['TIME', 'SERVICE', 'SOURCE', 'STATUS', 'AGO', ''].map((h, i) => (
            <span key={i} className="section-label">{h}</span>
          ))}
        </div>

        {/* Rows */}
        {(recent ?? []).slice(0, 10).map((inv, i) => (
          <LogRow key={inv.request_id} inv={inv} index={i} />
        ))}

        {(recent ?? []).length === 0 && (
          <div style={{ padding: '40px 20px', textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--c-text-faint)' }}>
            No investigations yet — start one from the{' '}
            <Link to="/investigations" style={{ color: 'var(--c-signal)' }}>Investigations</Link> page.
          </div>
        )}

        {/* Footer */}
        {(recent ?? []).length > 10 && (
          <div style={{ padding: '10px 14px', borderTop: '1px solid var(--c-border)', textAlign: 'center' }}>
            <Link to="/investigations" style={{
              fontFamily: 'var(--font-display)',
              fontSize: '0.72rem',
              fontWeight: 700,
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              color: 'var(--c-signal)',
              textDecoration: 'none',
            }}>
              View All {(recent ?? []).length} Investigations →
            </Link>
          </div>
        )}
      </div>
    </Layout>
  )
}


// ── Metric card ───────────────────────────────────────────────────────────────

