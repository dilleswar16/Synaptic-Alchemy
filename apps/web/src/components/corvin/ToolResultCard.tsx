/**
 * ToolResultCard — renders a rich data card in the Corvin Command Center
 * right panel for each tool result received from the agent.
 *
 * Each tool_name maps to a different card layout. Unknown tools fall back
 * to a compact JSON viewer.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'

interface ToolResultCardProps {
  toolName: string
  data: unknown
  timestamp: string
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const CARD_STYLE: React.CSSProperties = {
  background: 'var(--c-surface-2)',
  border: '1px solid var(--c-border-hi)',
  borderRadius: 12,
  padding: '14px 16px',
  marginBottom: 10,
  fontSize: '0.75rem',
  fontFamily: 'var(--font-body)',
  color: 'var(--c-text-dim)',
  animation: 'fadeSlideIn 0.25s ease',
}

const LABEL: React.CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: '0.65rem',
  color: 'var(--c-signal)',
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  marginBottom: 8,
  display: 'flex',
  alignItems: 'center',
  gap: 6,
}

const ROW: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  borderBottom: '1px solid var(--c-border)',
  padding: '5px 0',
  alignItems: 'center',
}

function Pill({ value, color = '#f97316' }: { value: string | number; color?: string }) {
  return (
    <span style={{
      background: `${color}22`,
      border: `1px solid ${color}55`,
      color,
      borderRadius: 6,
      padding: '2px 8px',
      fontFamily: 'var(--font-mono)',
      fontSize: '0.7rem',
    }}>
      {value}
    </span>
  )
}

function ToolIcon({ name }: { name: string }) {
  const icons: Record<string, string> = {
    get_platform_stats: '📊',
    list_recent_incidents: '📋',
    get_investigation_detail: '🔍',
    get_predictive_alerts: '⚠️',
    get_service_score: '🎯',
    get_roi: '💰',
    get_service_topology: '🗺️',
    get_blast_radius: '💥',
    get_postmortem: '📄',
    get_similar_incidents: '🔁',
    get_site_knowledge: '🏗️',
    get_runbook: '📖',
    run_kql: '🔬',
    get_aks_health: '☸️',
    run_elastic_query: '📡',
  }
  return <span>{icons[name] ?? '🛠️'}</span>
}

function ToolLabel({ name }: { name: string }) {
  const labels: Record<string, string> = {
    get_platform_stats: 'Platform Stats',
    list_recent_incidents: 'Recent Incidents',
    get_investigation_detail: 'Investigation Detail',
    get_predictive_alerts: 'Predictive Alerts',
    get_service_score: 'Service Score',
    get_roi: 'ROI Metrics',
    get_service_topology: 'Service Topology',
    get_blast_radius: 'Blast Radius',
    get_postmortem: 'Post-Mortem',
    get_similar_incidents: 'Similar Incidents',
    get_site_knowledge: 'CHAD Architecture',
    get_runbook: 'Runbook',
    run_kql: 'Log Analytics Query',
    get_aks_health: 'AKS Health',
    run_elastic_query: 'Elastic Logs',
  }
  return <span>{labels[name] ?? name.replace(/_/g, ' ')}</span>
}

// ── Card variants ─────────────────────────────────────────────────────────────

function PlatformStatsCard({ data }: { data: Record<string, unknown> }) {
  const mttr = typeof data.avg_mttr_minutes === 'number' ? data.avg_mttr_minutes.toFixed(1) : '—'
  const total = data.total_investigations ?? 0
  const today = data.today_investigations ?? 0
  const high = (data.confidence_breakdown as any)?.high ?? 0
  const medium = (data.confidence_breakdown as any)?.medium ?? 0
  const low = (data.confidence_breakdown as any)?.low ?? 0
  return (
    <div>
      <div style={ROW}><span>Total investigations</span><Pill value={String(total)} /></div>
      <div style={ROW}><span>Today</span><Pill value={String(today)} /></div>
      <div style={ROW}><span>Avg MTTR</span><Pill value={`${mttr} min`} /></div>
      <div style={{ marginTop: 10, fontSize: '0.7rem', color: 'var(--c-text-muted)' }}>
        Confidence: &nbsp;
        <span style={{ color: '#22c55e' }}>High {high}</span> ·&nbsp;
        <span style={{ color: '#f97316' }}>Med {medium}</span> ·&nbsp;
        <span style={{ color: '#ef4444' }}>Low {low}</span>
      </div>
    </div>
  )
}

function IncidentListCard({ data }: { data: unknown[] }) {
  const items = data.slice(0, 8)
  return (
    <div>
      {items.map((item: any, i) => (
        <div key={i} style={{ ...ROW, flexDirection: 'column', alignItems: 'flex-start', gap: 2 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--c-signal)', fontSize: '0.68rem' }}>
              {item.service_name} · {item.environment}
            </span>
            <Pill value={item.approval_status ?? 'pending'} color={item.approval_status === 'approved' ? '#22c55e' : '#f97316'} />
          </div>
          <span style={{ color: 'var(--c-text-faint)', fontSize: '0.67rem' }}>{item.description?.slice(0, 80)}</span>
          {item.request_id && (
            <Link to={`/investigations/${item.request_id}`} style={{ color: 'var(--c-signal)', fontSize: '0.65rem', textDecoration: 'none' }}>
              → View investigation
            </Link>
          )}
        </div>
      ))}
    </div>
  )
}

function ServiceScoreCard({ data }: { data: Record<string, unknown> }) {
  const score = typeof data.score === 'number' ? data.score : 0
  const hue = score > 70 ? '#22c55e' : score > 40 ? '#f97316' : '#ef4444'
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: '2.5rem', fontFamily: 'var(--font-display)', color: hue, lineHeight: 1 }}>
        {score.toFixed(0)}
      </div>
      <div style={{ color: 'var(--c-text-muted)', marginTop: 4 }}>/ 100 — {String(data.service_name ?? '')}</div>
      <div style={{ fontSize: '0.68rem', color: 'var(--c-text-faint)', marginTop: 6 }}>{String(data.summary ?? '')}</div>
    </div>
  )
}

function InvestigationResultCard({ data }: { data: any }) {
  const rca = data.rca || {}
  const fix = data.fix_strategy || {}
  const req = data.request || {}
  const actions = fix.actions || []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <div style={{ ...LABEL, color: 'var(--c-text)', fontSize: '0.7rem', marginBottom: 4 }}>RCA SUMMARY</div>
        <div style={{ fontSize: '0.78rem', color: 'var(--c-text)', fontWeight: 500, lineHeight: 1.4 }}>{rca.summary}</div>
      </div>

      <div style={{ padding: '8px 10px', background: 'rgba(249,115,22,0.06)', borderRadius: 8, borderLeft: '3px solid #f97316' }}>
        <div style={{ ...LABEL, fontSize: '0.6rem', marginBottom: 2 }}>ROOT CAUSE</div>
        <div style={{ fontSize: '0.72rem', color: 'var(--c-text-dim)', lineHeight: 1.5 }}>{rca.root_cause}</div>
      </div>

      {actions.length > 0 && (
        <div>
          <div style={{ ...LABEL, fontSize: '0.6rem', marginBottom: 6 }}>PROPOSED REMEDIATION</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {actions.map((a: any, i: number) => (
              <div key={i} style={{ padding: '6px 8px', background: 'var(--c-surface)', border: '1px solid var(--c-border)', borderRadius: 6 }}>
                <div style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--c-signal)' }}>{a.title}</div>
                <div style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)', marginTop: 2 }}>{a.description?.slice(0, 100)}…</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', gap: 12, borderTop: '1px solid var(--c-border)', paddingTop: 10 }}>
        <div>
          <div style={{ fontSize: '0.6rem', color: 'var(--c-text-faint)', textTransform: 'uppercase' }}>Status</div>
          <div style={{ fontSize: '0.7rem', color: req.approval_status === 'rejected' ? '#ef4444' : '#22c55e', fontWeight: 600 }}>{req.approval_status?.toUpperCase()}</div>
        </div>
        <div>
          <div style={{ fontSize: '0.6rem', color: 'var(--c-text-faint)', textTransform: 'uppercase' }}>Service</div>
          <div style={{ fontSize: '0.7rem', color: 'var(--c-text)', fontWeight: 600 }}>{req.service_name} ({req.environment})</div>
        </div>
        <div style={{ marginLeft: 'auto' }}>
          <Link to={`/investigations/${req.id}`} style={{ fontSize: '0.65rem', color: 'var(--c-signal)', textDecoration: 'none', borderBottom: '1px solid currentColor' }}>
            Full Report →
          </Link>
        </div>
      </div>
    </div>
  )
}

function RoiCard({ data }: { data: Record<string, unknown> }) {
  return (
    <div>
      <div style={ROW}><span>Hours saved</span><Pill value={`${Number(data.hours_saved ?? 0).toFixed(1)} h`} color="#22c55e" /></div>
      <div style={ROW}><span>Cost saved</span><Pill value={`$${Number(data.cost_saved ?? 0).toFixed(0)}`} color="#22c55e" /></div>
      <div style={ROW}><span>Auto-resolved</span><Pill value={String(data.auto_resolved_count ?? 0)} /></div>
    </div>
  )
}

function AlertListCard({ data }: { data: unknown[] }) {
  const severityColor = (s: string) => s === 'high' ? '#ef4444' : s === 'medium' ? '#f97316' : '#eab308'
  return (
    <div>
      {data.slice(0, 6).map((a: any, i) => (
        <div key={i} style={{ ...ROW, flexDirection: 'column', alignItems: 'flex-start', gap: 2 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text)' }}>{a.title}</span>
            <Pill value={a.severity ?? 'unknown'} color={severityColor(a.severity)} />
          </div>
          <span style={{ color: 'var(--c-text-faint)', fontSize: '0.67rem' }}>{a.summary?.slice(0, 80)}</span>
        </div>
      ))}
    </div>
  )
}

function AksHealthCard({ data }: { data: Record<string, unknown> }) {
  const pods: any[] = (data.pods as any[]) ?? []
  return (
    <div>
      {pods.slice(0, 8).map((p, i) => (
        <div key={i} style={ROW}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.67rem' }}>{String(p.name ?? p.pod_name ?? '').split('-').slice(-2).join('-')}</span>
          <div style={{ display: 'flex', gap: 6 }}>
            <Pill value={p.phase ?? 'Unknown'} color={p.phase === 'Running' ? '#22c55e' : '#ef4444'} />
            {p.restart_count != null && <Pill value={`↺ ${p.restart_count}`} color={p.restart_count > 0 ? '#ef4444' : '#6b7280'} />}
          </div>
        </div>
      ))}
    </div>
  )
}

function KqlResultCard({ data }: { data: unknown[] }) {
  if (!Array.isArray(data) || data.length === 0) {
    return <div style={{ color: 'var(--c-text-muted)', fontFamily: 'var(--font-mono)', fontSize: '0.7rem' }}>No results returned from Log Analytics.</div>
  }
  const cols = Object.keys(data[0] as object)
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.67rem', fontFamily: 'var(--font-mono)' }}>
        <thead>
          <tr>
            {cols.map(c => <th key={c} style={{ textAlign: 'left', color: 'var(--c-signal)', padding: '4px 6px', borderBottom: '1px solid var(--c-border)' }}>{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.slice(0, 10).map((row: any, i) => (
            <tr key={i}>
              {cols.map(c => <td key={c} style={{ padding: '4px 6px', borderBottom: '1px solid var(--c-border)', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{String(row[c] ?? '')}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {data.length > 10 && <div style={{ color: 'var(--c-text-faint)', marginTop: 4 }}>+ {data.length - 10} more rows</div>}
    </div>
  )
}

function TextDataCard({ data }: { data: string }) {
  return (
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', whiteSpace: 'pre-wrap', color: 'var(--c-text-dim)', maxHeight: 300, overflowY: 'auto' }}>
      {data.slice(0, 2000)}{data.length > 2000 ? '\n…' : ''}
    </div>
  )
}

function JsonFallbackCard({ data }: { data: unknown }) {
  const [expanded, setExpanded] = useState(false)
  const text = JSON.stringify(data, null, 2)
  return (
    <div>
      <pre style={{ fontFamily: 'var(--font-mono)', fontSize: '0.67rem', color: 'var(--c-text-dim)', whiteSpace: 'pre-wrap', maxHeight: expanded ? 'none' : 120, overflow: 'hidden', margin: 0 }}>
        {text}
      </pre>
      {text.length > 300 && (
        <button onClick={() => setExpanded(e => !e)} style={{ marginTop: 6, background: 'none', border: 'none', color: 'var(--c-signal)', cursor: 'pointer', fontSize: '0.7rem', fontFamily: 'var(--font-mono)' }}>
          {expanded ? '▲ Collapse' : '▼ Expand'}
        </button>
      )}
    </div>
  )
}

// ── Main export ───────────────────────────────────────────────────────────────

export function ToolResultCard({ toolName, data, timestamp }: ToolResultCardProps) {
  const renderBody = () => {
    if (data === null || data === undefined) return <div style={{ color: 'var(--c-text-faint)' }}>No data returned.</div>
    if (typeof data === 'string') return <TextDataCard data={data} />
    const d = data as any

    switch (toolName) {
      case 'get_platform_stats':    return <PlatformStatsCard data={d} />
      case 'get_investigation_detail': return <InvestigationResultCard data={d} />
      case 'list_recent_incidents':
      case 'get_similar_incidents': return Array.isArray(d) ? <IncidentListCard data={d} /> : <JsonFallbackCard data={d} />
      case 'get_service_score':     return <ServiceScoreCard data={d} />
      case 'get_roi':               return <RoiCard data={d} />
      case 'get_predictive_alerts': return Array.isArray(d) ? <AlertListCard data={d} /> : <JsonFallbackCard data={d} />
      case 'get_aks_health':        return <AksHealthCard data={d} />
      case 'run_kql':               return Array.isArray(d) ? <KqlResultCard data={d} /> : <JsonFallbackCard data={d} />
      case 'run_elastic_query':     return Array.isArray(d) ? <KqlResultCard data={d} /> : <JsonFallbackCard data={d} />
      case 'get_site_knowledge':
      case 'get_runbook':           return typeof d === 'string' ? <TextDataCard data={d} /> : <JsonFallbackCard data={d} />
      default:                      return <JsonFallbackCard data={d} />
    }
  }

  return (
    <div style={CARD_STYLE}>
      <div style={LABEL}>
        <ToolIcon name={toolName} />
        <ToolLabel name={toolName} />
        <span style={{ marginLeft: 'auto', color: 'var(--c-text-faint)', fontSize: '0.6rem' }}>
          {new Date(timestamp).toLocaleTimeString()}
        </span>
      </div>
      {renderBody()}
    </div>
  )
}

/** Compact "tool calling" skeleton shown while the tool is executing. */
export function ToolCallingSkeleton({ toolName }: { toolName: string }) {
  return (
    <div style={{
      ...CARD_STYLE,
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      opacity: 0.75,
    }}>
      <div style={{ width: 18, height: 18, borderRadius: '50%', border: '2px solid var(--c-signal)', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite', flexShrink: 0 }} />
      <div>
        <div style={{ ...LABEL, marginBottom: 2 }}>
          <ToolIcon name={toolName} /> <ToolLabel name={toolName} />
        </div>
        <div style={{ color: 'var(--c-text-faint)', fontSize: '0.67rem' }}>Querying live data…</div>
      </div>
    </div>
  )
}
