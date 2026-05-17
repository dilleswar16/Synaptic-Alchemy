/**
 * EvidenceSection — evidence bundle display with collapsible source rows
 * and a 5-segment signal bar indicator.
 */
import { useState } from 'react'
import type { EvidenceBundle } from '../../api/client'

const ADAPTER_LABEL: Record<string, string> = {
  elastic_logs:           'Elastic Logs',
  elastic_metrics:        'Elastic Metrics',
  log_analytics_apim:     'Log Analytics APIM',
  aks_context:            'AKS Context',
  azure_activity_changes: 'Azure Activity',
}

function buildSummary(name: string, items: unknown[], count: number): string {
  if (count === 0) return '—'
  const first = items[0] as Record<string, unknown> | undefined
  if (name === 'elastic_logs') {
    const errors = items.filter((r: any) => /error|exception|fatal/i.test(JSON.stringify(r))).length
    return errors > 0 ? `${count} log events · ${errors} errors/exceptions` : `${count} log events`
  }
  if (name === 'elastic_metrics') {
    return `${count} metric data points`
  }
  if (name === 'log_analytics_apim') {
    const codes5xx = items.filter((r: any) => String(r?.responseCode ?? r?.StatusCode ?? '').startsWith('5')).length
    return codes5xx > 0 ? `${count} APIM events · ${codes5xx} 5xx responses` : `${count} APIM events`
  }
  if (name === 'aks_context') {
    const pods = first ? Object.keys(first).filter(k => k.toLowerCase().includes('pod')).length : 0
    return pods > 0 ? `AKS context captured · ${pods} pod field(s)` : 'AKS context captured'
  }
  if (name === 'azure_activity_changes') {
    return `${count} Azure activity event${count !== 1 ? 's' : ''}`
  }
  return `${count} record${count !== 1 ? 's' : ''}`
}

function EvidenceSourceRow({
  name, records,
}: {
  name: string
  records: Record<string, unknown>[] | Record<string, unknown>
}) {
  const [open, setOpen] = useState(false)
  const items: unknown[] = Array.isArray(records)
    ? records
    : Object.keys(records).length > 0 ? [records] : []
  const count   = items.length
  const preview = items.slice(0, 10)
  const summary = buildSummary(name, items, count)

  return (
    <div style={{ borderBottom: '1px solid var(--c-border)' }}>
      <button
        onClick={() => count > 0 && setOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 12,
          padding: '10px 0', background: 'none', border: 'none',
          cursor: count > 0 ? 'pointer' : 'default', textAlign: 'left',
        }}
      >
        <span style={{ fontSize: '0.65rem', color: count > 0 ? 'var(--c-signal)' : 'var(--c-text-faint)', flexShrink: 0, width: 10 }}>
          {count > 0 ? '●' : '○'}
        </span>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: '0.75rem',
          color: count > 0 ? 'var(--c-text)' : 'var(--c-text-faint)', flex: 1,
        }}>
          {ADAPTER_LABEL[name] ?? name}
        </span>
        
        {count > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
              color: 'var(--c-text-faint)', textAlign: 'right',
            }}>
              {summary}
            </span>
          </div>
        )}
        
        {count === 0 && (
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.68rem',
            color: 'var(--c-text-faint)', minWidth: 70, textAlign: 'right',
          }}>
            —
          </span>
        )}

        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--c-text-faint)',
          marginLeft: 10, flexShrink: 0, transition: 'transform 0.15s',
          transform: open ? 'rotate(90deg)' : 'none', display: 'inline-block',
        }}>▶</span>
      </button>

      {open && count > 0 && (
        <div style={{ margin: '0 0 12px 22px', border: '1px solid var(--c-border)', borderRadius: 3, overflow: 'hidden' }}>
          <div style={{
            padding: '4px 12px', borderBottom: '1px solid var(--c-border)',
            background: 'var(--c-surface-2)',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--c-text-faint)' }}>
              {count > 10 ? `first 10 of ${count} records` : `${count} record${count !== 1 ? 's' : ''}`}
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--c-signal)' }}>JSON</span>
          </div>
          <pre style={{
            margin: 0, padding: '12px 14px',
            fontFamily: 'var(--font-mono)', fontSize: '0.68rem',
            color: 'var(--c-text-dim)', lineHeight: 1.6,
            overflowX: 'auto', maxHeight: 300, overflowY: 'auto',
            background: 'var(--c-surface)',
          }}>
            {JSON.stringify(
              !Array.isArray(records) ? preview[0] : preview,
              null, 2,
            )}
          </pre>
        </div>
      )}
    </div>
  )
}

export function EvidenceSection({ evidence }: { evidence: EvidenceBundle }) {
  const [isOpen, setIsOpen] = useState(false)
  
  const sources = [
    { name: 'elastic_logs',           data: evidence.elastic_logs },
    { name: 'elastic_metrics',        data: evidence.elastic_metrics },
    { name: 'log_analytics_apim',     data: evidence.log_analytics_apim },
    { name: 'aks_context',            data: evidence.aks_context },
    { name: 'azure_activity_changes', data: evidence.azure_activity_changes },
  ]

  const totalRecords = sources.reduce((sum, s) => {
    if (Array.isArray(s.data)) return sum + s.data.length
    return sum + (Object.keys(s.data).length > 0 ? 1 : 0)
  }, 0)
  const activeSources = sources.filter(s =>
    Array.isArray(s.data) ? s.data.length > 0 : Object.keys(s.data).length > 0
  ).length

  const segHeights = [14, 11, 8, 12, 9]

  return (
    <section style={{ marginTop: 20 }}>
      <div className="panel" style={{ overflow: 'hidden' }}>
        <button 
          onClick={() => setIsOpen(!isOpen)}
          style={{
            width: '100%',
            padding: '12px 18px',
            borderBottom: isOpen ? '1px solid var(--c-border)' : 'none',
            background: 'linear-gradient(90deg, var(--c-surface-2), transparent)',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            border: 'none', cursor: 'pointer', textAlign: 'left'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className={isOpen ? "animate-pulse-glow" : ""} style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--c-signal)' }} />
            <span style={{
              fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.68rem',
              letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--c-text-muted)',
            }}>
              Telemetry Intelligence &middot; {totalRecords} points
            </span>
            <span style={{ fontSize: '0.6rem', color: 'var(--c-text-faint)', marginLeft: 8 }}>
              {isOpen ? '▼' : '▶'}
            </span>
          </div>
          {/* Signal bar */}
          <span style={{
            display: 'inline-flex', gap: 3,
            alignItems: 'flex-end', verticalAlign: 'middle', height: 14,
          }}>
            {sources.map((s, i) => {
              const active = Array.isArray(s.data)
                ? s.data.length > 0
                : Object.keys(s.data).length > 0
              return (
                <span key={i} style={{
                  display: 'inline-block', width: 3,
                  height: active ? segHeights[i] : 4,
                  borderRadius: 1,
                  background: active ? 'var(--c-signal)' : 'rgba(255,255,255,0.1)',
                  transition: 'height 0.3s ease, background 0.3s ease',
                  opacity: active ? 1 : 0.3
                }} />
              )
            })}
          </span>
        </button>
        {isOpen && (
          <div style={{ padding: '16px 18px' }}>
            {sources.map(s => (
              <EvidenceSourceRow key={s.name} name={s.name} records={s.data} />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
