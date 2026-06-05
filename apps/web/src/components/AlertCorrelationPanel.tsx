/**
 * AlertCorrelationPanel — redesigned V5.4
 *
 * Auto-loads on mount, environment filter, rich group cards with:
 * - Correlation type badges (TEMPORAL / TOPOLOGY / SEMANTIC MATCH / SAME SERVICE)
 * - LLM-generated unified summaries
 * - Per-alert timeline with severity dots
 * - Approve/reject with clear semantics
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchCorrelatedAlerts,
  approveCorrelationAction,
  type CorrelationGroup,
  type CorrelatedAlertsResponse,
} from '../api/client'

// ── Constants ─────────────────────────────────────────────────────────────────

const SEV_COLOR: Record<string, string> = {
  critical: 'var(--c-red)',
  high:     'var(--c-signal)',
  medium:   '#b45309',
  low:      'var(--c-green)',
  info:     'var(--c-text-faint)',
}
const SEV_BG: Record<string, string> = {
  critical: 'rgba(239,68,68,0.08)',
  high:     'rgba(220,38,38,0.08)',
  medium:   'rgba(251,191,36,0.08)',
  low:      'rgba(34,197,94,0.08)',
  info:     'var(--c-surface-3)',
}

const REASON_META: Record<string, { label: string; color: string; bg: string; border: string; desc: string }> = {
  same_service: {
    label: 'SAME SERVICE',
    color: 'var(--c-primary)',
    bg: 'rgba(0,122,188,0.08)',
    border: 'rgba(0,122,188,0.25)',
    desc: 'Multiple alerts from the same service within a 5-minute window — likely a single root cause firing repeatedly.',
  },
  temporal: {
    label: 'TEMPORAL',
    color: '#b45309',
    bg: 'rgba(251,191,36,0.08)',
    border: 'rgba(251,191,36,0.3)',
    desc: 'Alerts from related services within a 10-minute window — temporal proximity suggests a shared upstream trigger.',
  },
  topology: {
    label: 'TOPOLOGY SPREAD',
    color: '#7c3aed',
    bg: 'rgba(124,58,237,0.08)',
    border: 'rgba(124,58,237,0.25)',
    desc: 'Alerts across topologically-adjacent services — suggests a cascading failure propagating through the service graph.',
  },
  semantic: {
    label: 'SEMANTIC MATCH',
    color: '#0d9488',
    bg: 'rgba(13,148,136,0.08)',
    border: 'rgba(13,148,136,0.25)',
    desc: 'Alert titles share high term overlap (Jaccard > 0.7) — likely the same failure pattern across different services.',
  },
}

const ENVIRONMENTS = ['all', 'dev', 'staging', 'production']

// ── Helpers ───────────────────────────────────────────────────────────────────

function reltime(iso: string) {
  const d = Date.now() - new Date(iso).getTime()
  const m = Math.floor(d / 60_000)
  if (m < 60) return `${m}m ago`
  return `${Math.floor(m / 60)}h ago`
}

function SevDot({ severity }: { severity: string }) {
  return (
    <span style={{
      display: 'inline-block', width: 7, height: 7, borderRadius: '50%',
      background: SEV_COLOR[severity] ?? 'var(--c-text-faint)',
      flexShrink: 0, marginTop: 2,
    }} />
  )
}

// ── Group card ────────────────────────────────────────────────────────────────

function GroupCard({
  group,
  onApprove,
  onReject,
  actioning,
}: {
  group: CorrelationGroup
  onApprove: (id: string) => void
  onReject: (id: string) => void
  actioning: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const reason = REASON_META[group.correlation_reason] ?? REASON_META.temporal
  const sevColor = SEV_COLOR[group.severity] ?? 'var(--c-text-faint)'

  return (
    <div style={{
      background: 'var(--c-surface)',
      border: '1px solid var(--c-border)',
      borderLeft: `3px solid ${sevColor}`,
      borderRadius: 10,
      overflow: 'hidden',
    }}>
      {/* Card header */}
      <div style={{
        padding: '13px 16px',
        background: 'var(--c-surface-2)',
        borderBottom: expanded ? '1px solid var(--c-border)' : 'none',
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            {/* Badge row */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 7, flexWrap: 'wrap' }}>
              {/* Severity */}
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.6rem', fontWeight: 800,
                letterSpacing: '0.07em', textTransform: 'uppercase',
                color: sevColor, background: SEV_BG[group.severity] ?? 'var(--c-surface-3)',
                border: `1px solid ${sevColor}30`,
                borderRadius: 4, padding: '1px 6px',
              }}>
                {group.severity}
              </span>
              {/* Correlation type */}
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.6rem', fontWeight: 700,
                letterSpacing: '0.06em', textTransform: 'uppercase',
                color: reason.color, background: reason.bg,
                border: `1px solid ${reason.border}`,
                borderRadius: 4, padding: '1px 6px',
              }}>
                {reason.label}
              </span>
              {/* Alert count */}
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.6rem', fontWeight: 700,
                color: 'var(--c-text-faint)', background: 'var(--c-surface-3)',
                border: '1px solid var(--c-border)', borderRadius: 4, padding: '1px 6px',
              }}>
                {group.alert_count} alert{group.alert_count !== 1 ? 's' : ''}
              </span>
              {/* Approval status */}
              {group.approval_status !== 'pending' && (
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.6rem', fontWeight: 700,
                  letterSpacing: '0.06em', textTransform: 'uppercase',
                  color: group.approval_status === 'approved' ? 'var(--c-green)' : 'var(--c-text-faint)',
                  background: group.approval_status === 'approved' ? 'rgba(34,197,94,0.1)' : 'var(--c-surface-3)',
                  border: `1px solid ${group.approval_status === 'approved' ? 'rgba(34,197,94,0.25)' : 'var(--c-border)'}`,
                  borderRadius: 4, padding: '1px 6px',
                }}>
                  {group.approval_status === 'approved' ? '✓ SUPPRESSED' : '✗ KEPT'}
                </span>
              )}
            </div>

            {/* Service + environment */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6,
              fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-text-dim)',
            }}>
              <span style={{ fontWeight: 700 }}>{group.service_name}</span>
              <span style={{ color: 'var(--c-text-faint)' }}>·</span>
              <span style={{ color: 'var(--c-text-faint)' }}>{group.environment}</span>
            </div>

            {/* Unified summary */}
            {group.unified_summary && (
              <p style={{
                margin: 0, fontSize: '0.78rem', color: 'var(--c-text-dim)',
                lineHeight: 1.55,
              }}>
                {group.unified_summary}
              </p>
            )}

            {/* Reason tooltip */}
            <p style={{
              margin: '6px 0 0', fontSize: '0.68rem', color: 'var(--c-text-faint)',
              lineHeight: 1.4, fontStyle: 'italic',
            }}>
              {reason.desc}
            </p>
          </div>

          {/* Actions */}
          <div style={{ flexShrink: 0 }}>
            {group.suppression_recommended && group.approval_status === 'pending' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5, alignItems: 'flex-end' }}>
                <button
                  onClick={() => onApprove(group.group_id)}
                  disabled={actioning}
                  style={{
                    padding: '5px 12px', fontSize: '0.72rem', fontWeight: 700,
                    background: 'var(--c-signal)', color: '#fff',
                    border: '1px solid var(--c-signal)', borderRadius: 6,
                    cursor: actioning ? 'not-allowed' : 'pointer',
                    fontFamily: 'var(--font-body)', whiteSpace: 'nowrap',
                    transition: 'all 0.12s',
                  }}
                >
                  {actioning ? '⟳' : '✓ Suppress Group'}
                </button>
                <button
                  onClick={() => onReject(group.group_id)}
                  disabled={actioning}
                  style={{
                    padding: '5px 12px', fontSize: '0.72rem', fontWeight: 600,
                    background: 'none', color: 'var(--c-text-faint)',
                    border: '1px solid var(--c-border)', borderRadius: 6,
                    cursor: actioning ? 'not-allowed' : 'pointer',
                    fontFamily: 'var(--font-body)', whiteSpace: 'nowrap',
                    transition: 'all 0.12s',
                  }}
                >
                  ✗ Keep Separate
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Alert timeline */}
      <div style={{ padding: '8px 16px' }}>
        <button
          onClick={() => setExpanded(e => !e)}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            fontSize: '0.7rem', color: 'var(--c-text-faint)',
            padding: 0, display: 'flex', alignItems: 'center', gap: 5,
            fontFamily: 'var(--font-body)',
          }}
        >
          <span>{expanded ? '▼' : '▶'}</span>
          <span>{expanded ? 'Hide' : 'Show'} {group.alert_count} alert{group.alert_count !== 1 ? 's' : ''}</span>
        </button>

        {expanded && (
          <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 1 }}>
            {group.alerts.map((alert, idx) => (
              <div
                key={alert.alert_id}
                style={{
                  display: 'flex', alignItems: 'flex-start', gap: 10,
                  padding: '6px 0',
                  borderBottom: idx < group.alerts.length - 1 ? '1px solid var(--c-border)' : 'none',
                }}
              >
                {/* Timeline dot + connector */}
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0, paddingTop: 3 }}>
                  <SevDot severity={alert.severity} />
                  {idx < group.alerts.length - 1 && (
                    <div style={{ width: 1, flex: 1, background: 'var(--c-border)', minHeight: 8, marginTop: 3 }} />
                  )}
                </div>
                {/* Alert details */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--c-text)', lineHeight: 1.3, fontWeight: 500 }}>
                    {alert.title}
                  </div>
                  <div style={{ display: 'flex', gap: 8, marginTop: 2 }}>
                    <span style={{ fontSize: '0.65rem', fontFamily: 'var(--font-mono)', color: 'var(--c-text-faint)' }}>
                      {alert.service_name}
                    </span>
                    <span style={{
                      fontSize: '0.6rem', fontWeight: 700, textTransform: 'uppercase',
                      color: SEV_COLOR[alert.severity] ?? 'var(--c-text-faint)',
                    }}>
                      {alert.severity}
                    </span>
                  </div>
                </div>
                {/* Time */}
                <div style={{
                  flexShrink: 0, fontSize: '0.65rem',
                  fontFamily: 'var(--font-mono)', color: 'var(--c-text-faint)',
                  whiteSpace: 'nowrap', paddingTop: 2,
                }}>
                  {alert.created_at ? reltime(alert.created_at) : '—'}
                </div>
                {/* Similarity score */}
                <div style={{
                  flexShrink: 0, fontSize: '0.63rem',
                  fontFamily: 'var(--font-mono)', color: 'var(--c-text-faint)',
                  paddingTop: 2,
                }}>
                  {(alert.similarity_score * 100).toFixed(0)}%
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main panel ────────────────────────────────────────────────────────────────

export default function AlertCorrelationPanel() {
  const qc = useQueryClient()
  const [env, setEnv] = useState('all')

  const { data, isLoading, error, refetch, isFetching } = useQuery<CorrelatedAlertsResponse>({
    queryKey: ['correlated-alerts', env],
    queryFn: () => fetchCorrelatedAlerts(env === 'all' ? undefined : env),
    staleTime: 30_000,
    retry: false,
  })

  const approveMut = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'approve' | 'reject' }) =>
      approveCorrelationAction(id, action),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['correlated-alerts'] }),
  })

  const groups = data?.correlation_groups ?? []
  const approved = groups.filter(g => g.approval_status === 'approved').length
  const pending = groups.filter(g => g.approval_status === 'pending' && g.suppression_recommended).length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
        padding: '16px 20px',
        background: 'var(--c-surface)',
        border: '1px solid var(--c-border)',
        borderRadius: 10,
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
            <span style={{ fontSize: '1rem' }}>🔗</span>
            <span style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.95rem', color: 'var(--c-text)' }}>
              Alert Correlation Engine
            </span>
          </div>
          <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--c-text-faint)', lineHeight: 1.5 }}>
            Groups related predictive alerts using temporal proximity, service topology, and semantic similarity.
            Suppress duplicate alert clusters to reduce on-call noise.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0, alignItems: 'center' }}>
          {/* Environment filter */}
          <select
            value={env}
            onChange={e => setEnv(e.target.value)}
            style={{
              padding: '6px 10px', fontSize: '0.75rem',
              background: 'var(--c-bg)', border: '1px solid var(--c-border)',
              borderRadius: 6, color: 'var(--c-text)',
              fontFamily: 'var(--font-body)',
            }}
          >
            {ENVIRONMENTS.map(e => (
              <option key={e} value={e}>{e === 'all' ? 'All Environments' : e.charAt(0).toUpperCase() + e.slice(1)}</option>
            ))}
          </select>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            style={{
              padding: '6px 14px', fontSize: '0.78rem', fontWeight: 600,
              background: isFetching ? 'var(--c-surface-3)' : 'var(--c-surface-2)',
              border: '1px solid var(--c-border-hi)', borderRadius: 6,
              color: isFetching ? 'var(--c-text-faint)' : 'var(--c-text-dim)',
              cursor: isFetching ? 'not-allowed' : 'pointer',
              fontFamily: 'var(--font-body)', transition: 'all 0.12s',
            }}
          >
            {isFetching ? '⟳ Analyzing…' : '↺ Refresh'}
          </button>
        </div>
      </div>

      {/* Stats strip */}
      {data && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
          {[
            { label: 'Open Alerts', value: data.total_alerts, color: 'var(--c-text)', bg: 'var(--c-surface)' },
            { label: 'Groups Found', value: groups.length, color: 'var(--c-primary)', bg: 'rgba(0,122,188,0.06)' },
            { label: 'Suppress Candidates', value: pending, color: 'var(--c-signal)', bg: 'rgba(220,38,38,0.06)' },
            { label: 'Suppressed', value: approved, color: 'var(--c-green)', bg: 'rgba(34,197,94,0.06)' },
          ].map(s => (
            <div key={s.label} style={{
              padding: '12px 16px', background: s.bg,
              border: '1px solid var(--c-border)', borderRadius: 8,
              display: 'flex', flexDirection: 'column', gap: 3,
            }}>
              <span style={{
                fontFamily: 'var(--font-display)', fontWeight: 800,
                fontSize: '1.5rem', color: s.color, lineHeight: 1,
              }}>
                {s.value}
              </span>
              <span style={{ fontSize: '0.68rem', color: 'var(--c-text-faint)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>
                {s.label}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{
          padding: '10px 14px', color: 'var(--c-red)', fontSize: '0.78rem',
          background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
          borderRadius: 8, fontFamily: 'var(--font-mono)',
        }}>
          {(error as Error).message}
        </div>
      )}

      {/* Loading skeleton */}
      {isLoading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[0, 1, 2].map(i => (
            <div key={i} className="pulse-skeleton" style={{ height: 96, borderRadius: 10 }} />
          ))}
        </div>
      )}

      {/* Group cards */}
      {!isLoading && groups.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {groups.map(g => (
            <GroupCard
              key={g.group_id}
              group={g}
              onApprove={id => approveMut.mutate({ id, action: 'approve' })}
              onReject={id => approveMut.mutate({ id, action: 'reject' })}
              actioning={approveMut.isPending && approveMut.variables?.id === g.group_id}
            />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && data && groups.length === 0 && (
        <div style={{
          textAlign: 'center', padding: '48px 24px',
          border: '1px dashed var(--c-border)', borderRadius: 10,
          background: 'var(--c-surface)',
        }}>
          <div style={{ fontSize: '2rem', marginBottom: 10, opacity: 0.4 }}>🔗</div>
          <div style={{ fontWeight: 700, color: 'var(--c-text)', marginBottom: 6 }}>No correlated groups detected</div>
          <p style={{ margin: 0, fontSize: '0.77rem', color: 'var(--c-text-faint)', lineHeight: 1.6 }}>
            {data.total_alerts === 0
              ? 'No open predictive alerts. Corvin sees nothing requiring correlation right now.'
              : `${data.total_alerts} open alert${data.total_alerts !== 1 ? 's' : ''} found but all appear independent — no temporal, topological, or semantic correlations detected.`}
          </p>
        </div>
      )}

      {/* Ungrouped note */}
      {data && data.ungrouped_count > 0 && groups.length > 0 && (
        <p style={{ margin: 0, fontSize: '0.72rem', color: 'var(--c-text-faint)', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
          {data.ungrouped_count} alert{data.ungrouped_count !== 1 ? 's' : ''} not correlated to any group
        </p>
      )}
    </div>
  )
}
