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
  const high = (data.confidence_distribution as any)?.high ?? 0
  const medium = (data.confidence_distribution as any)?.medium ?? 0
  const low = (data.confidence_distribution as any)?.low ?? 0
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '12px', borderRadius: 10, border: '1px solid var(--c-border)' }}>
          <div style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)', textTransform: 'uppercase', marginBottom: 4 }}>Avg MTTR</div>
          <div style={{ fontSize: '1.2rem', fontWeight: 800, color: 'var(--c-signal)' }}>{mttr}<span style={{ fontSize: '0.7rem', fontWeight: 400, marginLeft: 2 }}>min</span></div>
        </div>
        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '12px', borderRadius: 10, border: '1px solid var(--c-border)' }}>
          <div style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)', textTransform: 'uppercase', marginBottom: 4 }}>Investigations</div>
          <div style={{ fontSize: '1.2rem', fontWeight: 800, color: 'var(--c-text)' }}>{total}</div>
        </div>
      </div>
      <div style={{ background: 'rgba(255,255,255,0.02)', padding: '10px 14px', borderRadius: 10, border: '1px solid var(--c-border)' }}>
        <div style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)', textTransform: 'uppercase', marginBottom: 8 }}>Confidence Spread</div>
        <div style={{ height: 6, background: 'rgba(255,255,255,0.05)', borderRadius: 3, display: 'flex', overflow: 'hidden' }}>
          <div style={{ width: `${(high / total) * 100}%`, background: '#22c55e' }} title={`High: ${high}`} />
          <div style={{ width: `${(medium / total) * 100}%`, background: '#f97316' }} title={`Med: ${medium}`} />
          <div style={{ width: `${(low / total) * 100}%`, background: '#ef4444' }} title={`Low: ${low}`} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: '0.65rem' }}>
          <span style={{ color: '#22c55e' }}>High {high}</span>
          <span style={{ color: '#f97316' }}>Med {medium}</span>
          <span style={{ color: '#ef4444' }}>Low {low}</span>
        </div>
      </div>
    </div>
  )
}

function IncidentListCard({ data }: { data: unknown[] }) {
  const items = data.slice(0, 6)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {items.map((item: any, i) => (
        <div key={i} style={{ 
          background: 'rgba(255,255,255,0.02)', 
          border: '1px solid var(--c-border)', 
          borderRadius: 10, 
          padding: '10px 12px',
          transition: 'border-color 0.15s'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--c-signal)', fontSize: '0.7rem', fontWeight: 700 }}>
              {item.service_name}
            </span>
            <span style={{ 
              fontSize: '0.68rem', 
              textTransform: 'uppercase', 
              letterSpacing: '0.05em',
              background: item.approval_status === 'executed' ? 'rgba(34,197,94,0.1)' : 'rgba(249,115,22,0.1)',
              color: item.approval_status === 'executed' ? '#22c55e' : '#f97316',
              padding: '2px 6px',
              borderRadius: 4,
              border: `1px solid ${item.approval_status === 'executed' ? 'rgba(34,197,94,0.2)' : 'rgba(249,115,22,0.2)'}`
            }}>
              {item.approval_status ?? 'pending'}
            </span>
          </div>
          <div style={{ color: 'var(--c-text-dim)', fontSize: '0.68rem', lineHeight: 1.4, marginBottom: 8 }}>
            {item.description?.slice(0, 90)}...
          </div>
          {item.request_id && (
            <Link to={`/investigations/${item.request_id}`} style={{ 
              display: 'inline-flex', 
              alignItems: 'center', 
              gap: 4, 
              color: 'var(--c-text-faint)', 
              fontSize: '0.7rem', 
              textDecoration: 'none',
              transition: 'color 0.15s'
            }}>
              <span style={{ color: 'var(--c-signal)' }}>→</span> Full RCA Report
            </Link>
          )}
        </div>
      ))}
    </div>
  )
}

function ServiceScoreCard({ data }: { data: Record<string, unknown> }) {
  const score = typeof data.score === 'number' ? data.score : 0
  const color = score > 80 ? '#22c55e' : score > 50 ? '#f97316' : '#ef4444'
  return (
    <div style={{ textAlign: 'center', padding: '10px 0' }}>
      <div style={{ position: 'relative', width: 100, height: 100, margin: '0 auto' }}>
        <svg viewBox="0 0 36 36" style={{ width: '100%', height: '100%', transform: 'rotate(-90deg)' }}>
          <circle cx="18" cy="18" r="16" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="3" />
          <circle cx="18" cy="18" r="16" fill="none" stroke={color} strokeWidth="3" 
            strokeDasharray={`${score}, 100`} strokeLinecap="round" style={{ transition: 'stroke-dasharray 0.8s ease' }} />
        </svg>
        <div style={{ 
          position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', 
          alignItems: 'center', justifyContent: 'center' 
        }}>
          <div style={{ fontSize: '1.6rem', fontWeight: 800, color: color }}>{score}</div>
          <div style={{ fontSize: '0.65rem', textTransform: 'uppercase', color: 'var(--c-text-faint)' }}>score</div>
        </div>
      </div>
      <div style={{ marginTop: 12 }}>
        <div style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--c-text)' }}>{String(data.service_name ?? '')}</div>
        <div style={{ fontSize: '0.65rem', color: color, textTransform: 'uppercase', letterSpacing: '0.1em', marginTop: 2 }}>{String(data.label ?? '')}</div>
      </div>
    </div>
  )
}

function InvestigationResultCard({ data }: { data: any }) {
  const rca = data.rca || {}
  const fix = data.fix_strategy || {}
  const req = data.request || {}
  const actions = fix.actions || []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ background: 'linear-gradient(135deg, rgba(249,115,22,0.1), rgba(0,0,0,0))', padding: '14px', borderRadius: 12, border: '1px solid rgba(249,115,22,0.2)' }}>
        <div style={{ ...LABEL, color: 'var(--c-signal)', fontSize: '0.65rem', marginBottom: 6 }}>Root Cause Summary</div>
        <div style={{ fontSize: '0.82rem', color: 'var(--c-text)', fontWeight: 600, lineHeight: 1.5 }}>{rca.summary}</div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ fontSize: '0.68rem', color: 'var(--c-text-faint)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Remediation Steps</div>
        {actions.slice(0, 2).map((a: any, i: number) => (
          <div key={i} style={{ 
            padding: '8px 12px', 
            background: 'rgba(255,255,255,0.02)', 
            border: '1px solid var(--c-border)', 
            borderRadius: 8,
            display: 'flex',
            gap: 10,
            alignItems: 'center'
          }}>
            <span style={{ color: 'var(--c-signal)', fontSize: '0.8rem' }}>●</span>
            <div style={{ fontSize: '0.72rem', color: 'var(--c-text-dim)' }}>{a.title}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--c-border)', paddingTop: 12 }}>
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '0.68rem', color: 'var(--c-text-faint)', textTransform: 'uppercase' }}>Confidence</div>
            <div style={{ fontSize: '0.7rem', color: rca.confidence === 'high' ? '#22c55e' : '#f97316', fontWeight: 700 }}>{rca.confidence?.toUpperCase()}</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '0.68rem', color: 'var(--c-text-faint)', textTransform: 'uppercase' }}>Status</div>
            <div style={{ fontSize: '0.7rem', color: 'var(--c-text)', fontWeight: 700 }}>{req.approval_status?.toUpperCase()}</div>
          </div>
        </div>
        <Link to={`/investigations/${req.id}`} style={{ 
          background: 'var(--c-signal)', 
          color: '#fff', 
          padding: '5px 12px', 
          borderRadius: 6, 
          fontSize: '0.65rem', 
          fontWeight: 700, 
          textDecoration: 'none',
          boxShadow: '0 2px 8px rgba(249,115,22,0.3)'
        }}>
          Full Report →
        </Link>
      </div>
    </div>
  )
}

function RoiCard({ data }: { data: Record<string, unknown> }) {
  const hours = Number(data.hours_saved ?? 0).toFixed(1)
  const cost = Number(data.cost_saved ?? 0).toLocaleString()
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ 
        background: 'linear-gradient(135deg, rgba(34,197,94,0.15), rgba(0,0,0,0.2))', 
        padding: '20px', 
        borderRadius: 15, 
        border: '1px solid rgba(34,197,94,0.3)',
        textAlign: 'center',
        position: 'relative',
        overflow: 'hidden'
      }}>
        {/* Decorative glow */}
        <div style={{ position: 'absolute', top: -20, right: -20, width: 80, height: 80, background: 'rgba(34,197,94,0.2)', filter: 'blur(30px)', borderRadius: '50%' }} />
        
        <div style={{ fontSize: '0.7rem', color: 'rgba(34,197,94,0.8)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 4 }}>Total Cost Savings</div>
        <div style={{ fontSize: '2.4rem', fontWeight: 900, color: '#fff', letterSpacing: '-0.02em', lineHeight: 1 }}>
          <span style={{ fontSize: '1.2rem', verticalAlign: 'top', marginRight: 2, opacity: 0.7 }}>$</span>{cost}
        </div>
        <div style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.5)', marginTop: 8 }}>Estimated across {data.period_months ?? 1} month(s)</div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '14px', borderRadius: 12, border: '1px solid var(--c-border)', textAlign: 'center' }}>
          <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#22c55e' }}>{hours}<span style={{ fontSize: '0.7rem', fontWeight: 400, marginLeft: 2 }}>h</span></div>
          <div style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)', textTransform: 'uppercase', marginTop: 2 }}>Hours Saved</div>
        </div>
        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '14px', borderRadius: 12, border: '1px solid var(--c-border)', textAlign: 'center' }}>
          <div style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--c-text)' }}>{String(data.auto_resolved_count ?? 0)}</div>
          <div style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)', textTransform: 'uppercase', marginTop: 2 }}>Auto-Resolved</div>
        </div>
      </div>
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

function TopologyCard({ data }: { data: any }) {
  const nodes = data.nodes || []
  const edges = data.edges || []
  return (
    <div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
        {nodes.map((n: any, i: number) => (
          <div key={i} style={{ 
            padding: '4px 10px', 
            background: n.status === 'hot' ? 'rgba(239,68,68,0.1)' : 'var(--c-surface)', 
            border: `1px solid ${n.status === 'hot' ? 'rgba(239,68,68,0.3)' : 'var(--c-border)'}`,
            borderRadius: 6,
            fontSize: '0.65rem'
          }}>
            <span style={{ marginRight: 6 }}>{n.kind === 'pod' ? '📦' : n.kind === 'service' ? '⚙️' : '🌐'}</span>
            <span style={{ fontWeight: 600, color: n.status === 'hot' ? '#ef4444' : 'var(--c-text)' }}>{n.label}</span>
          </div>
        ))}
      </div>
      <div style={{ borderTop: '1px solid var(--c-border)', paddingTop: 8 }}>
        {edges.slice(0, 5).map((e: any, i: number) => (
          <div key={i} style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)', marginBottom: 2 }}>
            {e.source} <span style={{ color: 'var(--c-signal)' }}>→ {e.label} →</span> {e.target}
          </div>
        ))}
        {edges.length > 5 && <div style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)', marginTop: 4 }}>+ {edges.length - 5} more connections</div>}
      </div>
    </div>
  )
}

// ── Main export ───────────────────────────────────────────────────────────────

export function ToolResultCard({ toolName, data, timestamp }: ToolResultCardProps) {
  const [collapsed, setCollapsed] = useState(true)

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
      case 'get_blast_radius':      return <JsonFallbackCard data={d} />
      case 'get_service_topology':  return <TopologyCard data={d} />
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
      <div 
        style={{ ...LABEL, cursor: 'pointer', margin: collapsed ? 0 : LABEL.marginBottom }} 
        onClick={() => setCollapsed(!collapsed)}
      >
        <span style={{ fontSize: '0.8rem', color: 'var(--c-text-faint)' }}>{collapsed ? '▶' : '▼'}</span>
        <ToolIcon name={toolName} />
        <ToolLabel name={toolName} />
        <span style={{ marginLeft: 'auto', color: 'var(--c-text-faint)', fontSize: '0.65rem' }}>
          {new Date(timestamp).toLocaleTimeString()}
        </span>
      </div>
      {!collapsed && renderBody()}
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
