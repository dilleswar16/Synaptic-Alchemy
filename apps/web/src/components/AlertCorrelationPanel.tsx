import { useState } from 'react'
import { fetchCorrelatedAlerts, approveCorrelationAction, type CorrelationGroup, type CorrelatedAlertsResponse } from '../api/client'

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'var(--c-red)',
  high: 'var(--c-signal)',
  medium: 'var(--c-amber)',
  low: 'var(--c-green)',
  info: 'var(--c-text-muted)',
}

export default function AlertCorrelationPanel() {
  const [data, setData] = useState<CorrelatedAlertsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  async function loadCorrelations() {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchCorrelatedAlerts()
      setData(result)
    } catch (e: any) {
      setError(e.message || 'Failed to load correlations')
    } finally {
      setLoading(false)
    }
  }

  async function handleAction(groupId: string, action: 'approve' | 'reject') {
    setActionLoading(groupId)
    try {
      await approveCorrelationAction(groupId, action)
      // Refresh data
      await loadCorrelations()
    } catch (e: any) {
      setError(e.message || 'Action failed')
    } finally {
      setActionLoading(null)
    }
  }

  return (
    <div style={{
      background: 'var(--c-surface)',
      border: '1px solid var(--c-border)',
      borderRadius: 12,
      padding: 24,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h3 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: '1.1rem' }}>
          🔗 Alert Correlation Engine
        </h3>
        <button
          className="btn-primary"
          onClick={loadCorrelations}
          disabled={loading}
          style={{ fontSize: '0.8rem', padding: '6px 14px' }}
        >
          {loading ? 'Analyzing…' : 'Run Correlation'}
        </button>
      </div>

      {error && (
        <div style={{ color: 'var(--c-red)', fontSize: '0.82rem', marginBottom: 12 }}>{error}</div>
      )}

      {data && (
        <div style={{ marginBottom: 12, display: 'flex', gap: 16, fontSize: '0.8rem', color: 'var(--c-text-muted)' }}>
          <span>Total Alerts: <strong style={{ color: 'var(--c-text)' }}>{data.total_alerts}</strong></span>
          <span>Groups: <strong style={{ color: 'var(--c-text)' }}>{data.correlation_groups.length}</strong></span>
          <span>Suppression Candidates: <strong style={{ color: 'var(--c-signal)' }}>{data.suppression_candidates}</strong></span>
        </div>
      )}

      {data?.correlation_groups.map((group) => (
        <CorrelationGroupCard
          key={group.group_id}
          group={group}
          onAction={handleAction}
          actionLoading={actionLoading === group.group_id}
        />
      ))}

      {data && data.correlation_groups.length === 0 && (
        <div style={{ textAlign: 'center', padding: 32, color: 'var(--c-text-muted)', fontSize: '0.85rem' }}>
          No correlated alert groups detected. All alerts appear independent.
        </div>
      )}
    </div>
  )
}

function CorrelationGroupCard({ group, onAction, actionLoading }: {
  group: CorrelationGroup
  onAction: (groupId: string, action: 'approve' | 'reject') => void
  actionLoading: boolean
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div style={{
      border: '1px solid var(--c-border)',
      borderRadius: 8,
      padding: 16,
      marginBottom: 12,
      borderLeft: `3px solid ${SEVERITY_COLORS[group.severity] || 'var(--c-border)'}`,
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{
              fontSize: '0.7rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              color: SEVERITY_COLORS[group.severity],
              letterSpacing: '0.5px',
            }}>
              {group.severity}
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--c-text-muted)' }}>
              {group.service_name} / {group.environment}
            </span>
            <span style={{
              fontSize: '0.7rem',
              background: 'var(--c-border)',
              borderRadius: 4,
              padding: '1px 6px',
            }}>
              {group.alert_count} alerts
            </span>
          </div>
          <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 4 }}>
            {group.correlation_reason}
          </div>
          {group.unified_summary && (
            <div style={{ fontSize: '0.8rem', color: 'var(--c-text-muted)', lineHeight: 1.4 }}>
              {group.unified_summary}
            </div>
          )}
        </div>

        {group.suppression_recommended && group.approval_status === 'pending' && (
          <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
            <button
              className="btn-primary"
              onClick={() => onAction(group.group_id, 'approve')}
              disabled={actionLoading}
              style={{ fontSize: '0.75rem', padding: '4px 10px' }}
            >
              ✓ Suppress
            </button>
            <button
              onClick={() => onAction(group.group_id, 'reject')}
              disabled={actionLoading}
              style={{
                fontSize: '0.75rem',
                padding: '4px 10px',
                background: 'transparent',
                border: '1px solid var(--c-border)',
                borderRadius: 6,
                color: 'var(--c-text-muted)',
                cursor: 'pointer',
              }}
            >
              ✗ Keep
            </button>
          </div>
        )}

        {group.approval_status !== 'pending' && (
          <span style={{
            fontSize: '0.7rem',
            fontWeight: 600,
            color: group.approval_status === 'approved' ? 'var(--c-green)' : 'var(--c-text-muted)',
            textTransform: 'uppercase',
          }}>
            {group.approval_status}
          </span>
        )}
      </div>

      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          marginTop: 8,
          fontSize: '0.75rem',
          color: 'var(--c-link)',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          padding: 0,
        }}
      >
        {expanded ? '▾ Hide alerts' : '▸ Show alerts'}
      </button>

      {expanded && (
        <div style={{ marginTop: 8 }}>
          {group.alerts.map((alert) => (
            <div key={alert.alert_id} style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '4px 0',
              fontSize: '0.78rem',
              borderBottom: '1px solid var(--c-border)',
            }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: SEVERITY_COLORS[alert.severity], flexShrink: 0 }} />
              <span style={{ flex: 1 }}>{alert.title}</span>
              <span style={{ color: 'var(--c-text-muted)', fontSize: '0.7rem' }}>{alert.service_name}</span>
              <span style={{ color: 'var(--c-text-muted)', fontSize: '0.7rem' }}>
                {new Date(alert.created_at).toLocaleTimeString()}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
