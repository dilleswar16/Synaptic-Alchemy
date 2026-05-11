/**
 * StreamingProgress — V3 Streaming AI Visualizer
 *
 * Renders the live investigation SSE stream with:
 * - Stage progress tracker (evidence → rca → fix_strategy → complete)
 * - Live prose typewriter for RCA and fix_strategy token streams
 * - Structured summary cards after each stage completes
 * - Degraded/fallback banners when generation used a fallback path
 */

import { useState, useEffect, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { StageEvent } from '../hooks/useInvestigationStream'

// ── Utility: Stream Token Parser ────────────────────────────────────────────

/**
 * Strips JSON structural characters from a raw token stream so the
 * TypewriterPanel shows readable prose rather than raw JSON fragments.
 */
function parseStreamToken(raw: string): string {
  if (!raw) return ''
  let s = raw.replace(/"[a-zA-Z0-9_]+":\s*/g, '') // remove JSON keys
  s = s.replace(/[{}\[\]]/g, '')                   // remove brackets
  s = s.replace(/(^"|"$)/g, '')                    // strip wrapping quotes
  s = s.replace(/\\n/g, '\n')
  s = s.replace(/\\"/g, '"')
  return s.trim()
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface StreamingProgressProps {
  stages: StageEvent[]
  streamText: Record<string, string>
  fetchingEvents: StageEvent[]
  isStreaming: boolean
  isComplete: boolean
  error: string | null
  requestId: string | null
  onReset: () => void
}

// ── Stage config ──────────────────────────────────────────────────────────────

const STAGES = ['evidence', 'rca', 'fix_strategy'] as const
type StageName = typeof STAGES[number]

const STAGE_LABELS: Record<StageName, string> = {
  evidence:     'Evidence Collection',
  rca:          'Root Cause Analysis',
  fix_strategy: 'Fix Strategy',
}

// ── Evidence accordion ────────────────────────────────────────────────────────

interface FetchingRow {
  source: string
  table: string
  source_status: 'running' | 'done'
  count: number
  elapsed_ms: number
}

const SOURCE_LABEL: Record<string, string> = {
  container_logs:   'Container Logs',
  apim_logs:        'APIM Logs',
  aks_context:      'AKS Context',
  activity_changes: 'Activity Changes',
  elastic_logs:     'Elastic Logs',
  elastic_metrics:  'Elastic Metrics',
}

function fmtMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}

function EvidenceAccordion({
  fetchingRows,
  totalElapsedMs,
  isActive,
}: {
  fetchingRows: FetchingRow[]
  totalElapsedMs?: number
  isActive: boolean
}) {
  const [open, setOpen] = useState(false)

  // Auto-open as soon as evidence collection starts so the SRE sees live progress
  useEffect(() => {
    if (isActive) setOpen(true)
  }, [isActive])

  if (fetchingRows.length === 0) return null

  // Deduplicate: done event replaces the running event for the same source
  const rowMap = new Map<string, FetchingRow>()
  for (const row of fetchingRows) rowMap.set(row.source, row)
  const rows = Array.from(rowMap.values())

  const doneRows   = rows.filter(r => r.source_status === 'done')
  const nonEmpty   = doneRows.filter(r => r.count > 0).length
  const totalRecs  = doneRows.reduce((s, r) => s + r.count, 0)
  const anyRunning = rows.some(r => r.source_status === 'running')

  return (
    <div style={{ marginTop: 12, border: '1px solid var(--c-border)', borderRadius: 4, overflow: 'hidden' }}>
      {/* Toggle header */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 10,
          padding: '8px 14px', background: 'none', border: 'none',
          cursor: 'pointer', textAlign: 'left',
        }}
      >
        <span style={{
          fontSize: '0.6rem', color: 'var(--c-text-faint)',
          transition: 'transform 0.15s', transform: open ? 'rotate(90deg)' : 'none',
          display: 'inline-block', flexShrink: 0,
        }}>▶</span>
        {anyRunning && (
          <span className="animate-pulse-glow" style={{
            width: 6, height: 6, borderRadius: '50%',
            background: 'var(--c-signal)', flexShrink: 0, display: 'inline-block',
          }} />
        )}
        <span style={{
          fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.62rem',
          letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--c-text-muted)',
        }}>
          Evidence Sources
        </span>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: '0.67rem',
          color: 'var(--c-text-faint)', marginLeft: 'auto',
        }}>
          {anyRunning
            ? <span className="animate-pulse-glow" style={{ color: 'var(--c-signal)' }}>querying…</span>
            : <>{nonEmpty} sources&nbsp;·&nbsp;{totalRecs} records{totalElapsedMs !== undefined && <>&nbsp;·&nbsp;{fmtMs(totalElapsedMs)}</>}</>
          }
        </span>
      </button>

      {/* Per-source rows */}
      {open && (
        <div style={{ borderTop: '1px solid var(--c-border)' }}>
          {rows.map(row => {
            const running = row.source_status === 'running'
            const hasData = row.count > 0
            return (
              <div key={row.source} style={{
                display: 'grid', gridTemplateColumns: '18px 1fr 52px 60px',
                alignItems: 'center', gap: 10,
                padding: '7px 14px', borderBottom: '1px solid var(--c-border)',
              }}>
                {/* Status icon */}
                <span style={{
                  fontSize: running ? '1rem' : '0.6rem', lineHeight: 1,
                  color: running ? 'var(--c-signal)' : hasData ? 'var(--c-green)' : 'var(--c-text-faint)',
                }} className={running ? 'animate-pulse-glow' : ''}>
                  {running ? '⟳' : hasData ? '●' : '○'}
                </span>

                {/* Source name + KQL table */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.72rem', fontWeight: hasData ? 600 : 400,
                    color: running ? 'var(--c-signal)' : hasData ? 'var(--c-text-dim)' : 'var(--c-text-faint)',
                  }}>
                    {SOURCE_LABEL[row.source] ?? row.source}
                  </span>
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--c-text-faint)',
                  }}>
                    {row.table}
                  </span>
                </div>

                {/* Row count */}
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.67rem', textAlign: 'right',
                  color: running ? 'var(--c-text-faint)' : hasData ? 'var(--c-text-dim)' : 'var(--c-text-faint)',
                }}>
                  {running ? '…' : hasData ? `${row.count}` : '—'}
                </span>

                {/* Elapsed */}
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.67rem', textAlign: 'right',
                  color: running ? 'transparent' : 'var(--c-text-faint)',
                }}>
                  {running ? '' : fmtMs(row.elapsed_ms)}
                </span>
              </div>
            )
          })}

          {/* Wall-clock total */}
          {!anyRunning && totalElapsedMs !== undefined && (
            <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '5px 14px' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.63rem', color: 'var(--c-text-faint)' }}>
                total {fmtMs(totalElapsedMs)}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Stage progress tracker ────────────────────────────────────────────────────

function StageTracker({ stages }: { stages: StageEvent[] }) {
  const stageMap = new Map<string, StageEvent['status']>()
  stages.forEach(s => { stageMap.set(s.stage, s.status) })

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 0, marginBottom: 28 }}>
      {STAGES.map((key, i) => {
        const status = stageMap.get(key)
        const active = status === 'started'
        const done   = status === 'complete'
        return (
          <div key={key} style={{ display: 'flex', alignItems: 'center', flex: 1 }}>
            {/* Node */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, flexShrink: 0 }}>
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '0.8rem',
                  fontWeight: 800,
                  transition: 'all 0.3s ease',
                  background: done
                    ? 'var(--c-green)'
                    : active
                    ? 'rgba(249,115,22,0.15)'
                    : 'rgba(255,255,255,0.04)',
                  border: done
                    ? '2px solid var(--c-green)'
                    : active
                    ? '2px solid var(--c-signal)'
                    : '2px solid var(--c-border)',
                  color: done ? '#0b0f1a' : active ? 'var(--c-signal)' : 'var(--c-text-faint)',
                  boxShadow: active ? '0 0 16px rgba(249,115,22,0.5)' : 'none',
                }}
                className={active ? 'animate-pulse-glow' : ''}
              >
                {done ? '✓' : i + 1}
              </div>
              <span style={{
                fontSize: '0.65rem',
                fontWeight: 600,
                letterSpacing: '0.05em',
                textTransform: 'uppercase',
                color: done ? 'var(--c-green)' : active ? 'var(--c-signal)' : 'var(--c-text-faint)',
                whiteSpace: 'nowrap',
              }}>
                {STAGE_LABELS[key]}
              </span>
            </div>
            {/* Connector */}
            {i < STAGES.length - 1 && (
              <div style={{
                flex: 1,
                height: 2,
                marginTop: -20,
                background: done ? 'var(--c-green)' : 'var(--c-border)',
                transition: 'background 0.4s ease',
              }} />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Model thinking / reasoning panel ────────────────────────────────────────

function ThinkingPanel({ text, isActive, label = 'Model Reasoning' }: { text: string; isActive: boolean; label?: string }) {
  const [open, setOpen] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Auto-open the first time content arrives
  useEffect(() => {
    if (text && !open) setOpen(true)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [!!text])

  useEffect(() => {
    if (open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [text, open])

  if (!text) return null

  return (
    <div style={{
      marginTop: 12,
      border: '1px solid rgba(139,92,246,0.25)',
      borderRadius: 6,
      overflow: 'hidden',
      background: 'rgba(139,92,246,0.05)',
    }}>
      {/* Toggle header */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 10,
          padding: '8px 14px', background: 'none', border: 'none',
          cursor: 'pointer', textAlign: 'left',
        }}
      >
        <span style={{
          fontSize: '0.6rem', color: 'rgba(167,139,250,0.7)',
          transition: 'transform 0.15s', transform: open ? 'rotate(90deg)' : 'none',
          display: 'inline-block', flexShrink: 0,
        }}>▶</span>
        {isActive && (
          <span className="animate-pulse-glow" style={{
            width: 7, height: 7, borderRadius: '50%',
            background: 'rgba(139,92,246,0.9)', flexShrink: 0,
            display: 'inline-block',
          }} />
        )}
        <span style={{
          fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.62rem',
          letterSpacing: '0.12em', textTransform: 'uppercase', color: 'rgba(167,139,250,0.8)',
        }}>
          {label}{isActive ? ' · live' : ''}
        </span>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
          color: 'rgba(139,92,246,0.5)', marginLeft: 'auto',
        }}>
          {open ? 'collapse' : `${text.length} chars · click to expand`}
        </span>
      </button>

      {open && (
        <div
          ref={scrollRef}
          style={{
            borderTop: '1px solid rgba(139,92,246,0.15)',
            padding: '12px 16px',
            maxHeight: 220,
            overflowY: 'auto',
            fontSize: '0.8rem',
            lineHeight: 1.7,
            color: 'rgba(196,181,253,0.85)',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            fontFamily: 'var(--font-body)',
          }}
        >
          {text}
          {isActive && <span className="animate-cursor" style={{ color: 'rgba(139,92,246,0.9)', fontWeight: 700 }}>▋</span>}
        </div>
      )}
    </div>
  )
}

// ── Live typewriter panel ─────────────────────────────────────────────────────

function TypewriterPanel({ stage, text }: { stage: string; text: string }) {
  const tokenCount = text.length
  const label = STAGE_LABELS[stage as StageName] ?? stage
  const parsedText = useMemo(() => parseStreamToken(text), [text])
  const [displayed, setDisplayed] = useState('')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Reset when parsedText is cleared (new investigation)
  useEffect(() => {
    if (!parsedText) setDisplayed('')
  }, [parsedText])

  // Char-by-char typewriter: add 4 chars every 12 ms ≈ 333 chars/sec
  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    if (displayed.length >= parsedText.length) return
    timerRef.current = setTimeout(() => {
      setDisplayed(parsedText.slice(0, displayed.length + 4))
    }, 12)
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [displayed, parsedText])

  // Auto-scroll as displayed text grows
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [displayed])

  return (
    <div
      style={{
        marginTop: 16,
        borderRadius: 8,
        border: '1px solid var(--c-border-glow)',
        background: 'rgba(249,115,22,0.03)',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div style={{
        padding: '8px 14px',
        borderBottom: '1px solid var(--c-border)',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        background: 'rgba(249,115,22,0.04)',
      }}>
        <span className="animate-pulse-glow" style={{
          width: 8, height: 8, borderRadius: '50%',
          background: 'var(--c-signal)', flexShrink: 0,
          display: 'inline-block',
        }} />
        <span style={{ fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--c-signal)' }}>
          {label} · generating
        </span>
        <span style={{ marginLeft: 'auto', fontSize: '0.68rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)' }}>
          {tokenCount > 0 ? `${tokenCount} chars` : '…'}
        </span>
      </div>
      {/* Live token text */}
      <div
        ref={scrollRef}
        style={{
          padding: '14px 16px',
          maxHeight: 200,
          overflowY: 'auto',
          fontSize: '0.82rem',
          lineHeight: 1.75,
          color: 'var(--c-text-muted)',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          fontFamily: 'var(--font-body)',
        }}
      >
        {displayed || <span style={{ color: 'var(--c-text-faint)' }}>Waiting for tokens…</span>}
        <span className="animate-cursor" style={{ color: 'var(--c-signal)', fontWeight: 700 }}>▋</span>
      </div>
    </div>
  )
}

// ── RCA summary card ──────────────────────────────────────────────────────────

function RCASummary({ s }: { s: StageEvent }) {
  const factors = Array.isArray(s.contributing_factors) ? (s.contributing_factors as string[]) : []
  const degraded = s.degraded === true

  return (
    <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
      {degraded && (
        <div style={{
          padding: '8px 14px',
          borderRadius: 6,
          background: 'rgba(251,191,36,0.08)',
          border: '1px solid rgba(251,191,36,0.25)',
          fontSize: '0.75rem',
          color: 'var(--c-yellow)',
        }}>
          ⚠ RCA generated via fallback path ({String(s.generation_status ?? '')}) — result may be lower quality.
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 10 }}>
        {/* Confidence */}
        {typeof s.confidence === 'string' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--c-text-faint)' }}>Confidence</span>
            <span className={`badge ${s.confidence === 'high' ? 'badge-approved' : s.confidence === 'low' ? 'badge-rejected' : 'badge-pending'}`}>
              {s.confidence}
            </span>
          </div>
        )}

        {/* Summary */}
        {typeof s.summary === 'string' && (
          <div style={{ padding: '12px 14px', borderRadius: 8, background: 'rgba(255,255,255,0.02)', border: '1px solid var(--c-border)' }}>
            <div style={{ fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--c-text-faint)', marginBottom: 6 }}>Summary</div>
            <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--c-text-muted)', lineHeight: 1.65 }}>{s.summary}</p>
          </div>
        )}

        {/* Root cause */}
        {typeof s.root_cause === 'string' && (
          <div style={{ padding: '12px 14px', borderRadius: 8, background: 'rgba(248,113,113,0.04)', border: '1px solid rgba(248,113,113,0.15)' }}>
            <div style={{ fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--c-red)', marginBottom: 6 }}>Root Cause</div>
            <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--c-text-muted)', lineHeight: 1.65 }}>{s.root_cause}</p>
          </div>
        )}

        {/* Confidence reasoning */}
        {typeof s.confidence_reasoning === 'string' && s.confidence_reasoning && (
          <div style={{ padding: '10px 14px', borderRadius: 6, background: 'rgba(249,115,22,0.04)', border: '1px solid rgba(249,115,22,0.15)' }}>
            <div style={{ fontSize: '0.65rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--c-signal)', marginBottom: 5 }}>Why this confidence</div>
            <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--c-text-muted)', lineHeight: 1.6, fontStyle: 'italic' }}>{s.confidence_reasoning as string}</p>
          </div>
        )}

        {/* Contributing factors */}
        {factors.length > 0 && (
          <div style={{ padding: '12px 14px', borderRadius: 8, background: 'rgba(255,255,255,0.02)', border: '1px solid var(--c-border)' }}>
            <div style={{ fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--c-text-faint)', marginBottom: 8 }}>Contributing Factors</div>
            <ul style={{ margin: 0, paddingLeft: '1.2rem', display: 'flex', flexDirection: 'column', gap: 4 }}>
              {factors.map((f, i) => (
                <li key={i} style={{ fontSize: '0.82rem', color: 'var(--c-text-muted)', lineHeight: 1.5 }}>{f}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Evidence references */}
        {(() => {
          const refs = Array.isArray(s.evidence_references) ? (s.evidence_references as string[]) : []
          if (!refs.length) return null
          return (
            <div style={{ padding: '12px 14px', borderRadius: 8, background: 'rgba(255,255,255,0.015)', border: '1px solid var(--c-border)' }}>
              <div style={{ fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--c-text-faint)', marginBottom: 8 }}>
                Evidence References <span style={{ fontWeight: 400, opacity: 0.6 }}>· what the model saw</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {refs.map((r, i) => (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'flex-start', gap: 8,
                    padding: '7px 12px',
                    borderLeft: '2px solid rgba(249,115,22,0.4)',
                    background: 'rgba(249,115,22,0.03)',
                    borderRadius: '0 4px 4px 0',
                  }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'rgba(249,115,22,0.5)', marginTop: 3, flexShrink: 0 }}>↳</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--c-text-dim)', lineHeight: 1.55 }}>{r}</span>
                  </div>
                ))}
              </div>
            </div>
          )
        })()}
      </div>
    </div>
  )
}

// ── Fix strategy summary card ─────────────────────────────────────────────────

function FixStrategySummary({ s }: { s: StageEvent }) {
  const actions = Array.isArray(s.action_summaries) ? (s.action_summaries as string[]) : []
  const degraded = s.degraded === true

  return (
    <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
      {degraded && (
        <div style={{
          padding: '8px 14px',
          borderRadius: 6,
          background: 'rgba(251,191,36,0.08)',
          border: '1px solid rgba(251,191,36,0.25)',
          fontSize: '0.75rem',
          color: 'var(--c-yellow)',
        }}>
          ⚠ Fix strategy generated via fallback path ({String(s.generation_status ?? '')}).
        </div>
      )}
      {typeof s.summary === 'string' && (
        <div style={{ padding: '12px 14px', borderRadius: 8, background: 'rgba(249,115,22,0.04)', border: '1px solid rgba(249,115,22,0.2)' }}>
          <div style={{ fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--c-signal)', marginBottom: 6 }}>Strategy</div>
          <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--c-text-muted)', lineHeight: 1.65 }}>{s.summary}</p>
        </div>
      )}
      {actions.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {actions.map((a, i) => (
            <div key={i} style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 10,
              padding: '10px 14px',
              borderRadius: 8,
              background: 'rgba(255,255,255,0.02)',
              border: '1px solid var(--c-border)',
            }}>
              <span style={{
                flexShrink: 0,
                width: 22,
                height: 22,
                borderRadius: '50%',
              background: 'rgba(249,115,22,0.1)',
              border: '1px solid rgba(249,115,22,0.3)',
                color: 'var(--c-signal)',
                fontSize: '0.7rem',
                fontWeight: 800,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                {i + 1}
              </span>
              <span style={{ fontSize: '0.82rem', color: 'var(--c-text-muted)', lineHeight: 1.5, paddingTop: 2 }}>{a}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Stage panel ───────────────────────────────────────────────────────────────

function StagePanel({
  stageKey,
  stageEvents,
  streamText,
  isActiveStage,
  fetchingEvents,
}: {
  stageKey: string
  stageEvents: StageEvent[]
  streamText: Record<string, string>
  isActiveStage: boolean
  fetchingEvents: FetchingRow[]
}) {
  const latest = stageEvents.at(-1)
  if (!latest) return null

  const done   = latest.status === 'complete'
  const active = latest.status === 'started'
  const text   = streamText[stageKey] ?? ''

  return (
    <div
      className="glass animate-fade-up"
      style={{
        padding: '16px 20px',
        borderColor: done ? 'rgba(52,211,153,0.2)' : active ? 'var(--c-border-glow)' : 'var(--c-border)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{
          width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
          background: done ? 'var(--c-green)' : active ? 'var(--c-signal)' : 'var(--c-text-faint)',
        }} className={active ? 'animate-pulse-glow' : ''} />
        <span style={{ fontWeight: 700, fontSize: '0.82rem', color: done ? 'var(--c-text)' : active ? 'var(--c-signal)' : 'var(--c-text-muted)' }}>
          {STAGE_LABELS[stageKey as StageName] ?? stageKey}
        </span>
        <span style={{ fontSize: '0.72rem', color: 'var(--c-text-faint)', marginLeft: 'auto' }}>
          {latest.message}
        </span>
      </div>

      {/* Model reasoning tokens — shown for RCA stage whenever thinking text arrives */}
      {stageKey === 'rca' && !!streamText['rca_thinking'] && (
        <ThinkingPanel
          text={streamText['rca_thinking']}
          isActive={active && isActiveStage}
          label="Model Reasoning"
        />
      )}

      {/* Fix strategy reasoning — shown when the model reasoned about the strategy */}
      {stageKey === 'fix_strategy' && !!streamText['fix_thinking'] && (
        <ThinkingPanel
          text={streamText['fix_thinking']}
          isActive={active && isActiveStage}
          label="Strategy Reasoning"
        />
      )}

      {/* Live token stream */}
      {active && text && isActiveStage && (
        <TypewriterPanel stage={stageKey} text={text} />
      )}

      {/* Structured results after complete */}
      {stageKey === 'evidence' && (() => {
        // Live fetchingEvents take priority (real-time streaming).
        // Fall back to sources[] from the complete event (e.g. post-reset view).
        const rows: FetchingRow[] = fetchingEvents.length > 0
          ? fetchingEvents
          : done && Array.isArray(latest.sources)
          ? (latest.sources as Record<string, unknown>[]).map(s => ({
              source:        String(s.source ?? ''),
              table:         String(s.table ?? ''),
              source_status: 'done' as const,
              count:         Number(s.count ?? 0),
              elapsed_ms:    Number(s.elapsed_ms ?? 0),
            }))
          : []
        const totalMs = done ? (Number(latest.total_elapsed_ms) || undefined) : undefined
        return <EvidenceAccordion fetchingRows={rows} totalElapsedMs={totalMs} isActive={active} />
      })()}
      {done && stageKey === 'rca' && <RCASummary s={latest} />}
      {done && stageKey === 'fix_strategy' && <FixStrategySummary s={latest} />}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function StreamingProgress({
  stages,
  streamText,
  fetchingEvents,
  isStreaming,
  isComplete,
  error,
  requestId,
  onReset,
}: StreamingProgressProps) {
  const navigate = useNavigate()

  if (!isStreaming && !isComplete && stages.length === 0) return null

  // Group events by stage
  const byStage = new Map<string, StageEvent[]>()
  stages.forEach(s => {
    if (!byStage.has(s.stage)) byStage.set(s.stage, [])
    byStage.get(s.stage)!.push(s)
  })

  // Active stage is the last non-complete stage that has started
  const activeStage = isStreaming
    ? (stages.filter(s => s.stage !== 'complete' && s.stage !== 'error').at(-1)?.stage ?? null)
    : null

  return (
    <section style={{ marginTop: 32, display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {isStreaming && (
            <span className="animate-pulse-glow" style={{
              width: 8, height: 8, borderRadius: '50%',
              background: 'var(--c-signal)',
              display: 'inline-block',
            }} />
          )}
          <h3 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 700, color: 'var(--c-text)' }}>
            {isStreaming
              ? 'Investigation in progress…'
              : isComplete && !error
              ? 'Investigation complete'
              : 'Investigation failed'}
          </h3>
        </div>
        <button onClick={onReset} className="btn-ghost" style={{ padding: '4px 12px', fontSize: '0.75rem' }}>
          Clear
        </button>
      </div>

      {/* Stage tracker */}
      <StageTracker stages={stages} />

      {/* Error */}
      {error && (
        <div style={{
          padding: '14px 16px',
          borderRadius: 8,
          background: 'rgba(248,113,113,0.08)',
          border: '1px solid rgba(248,113,113,0.25)',
          color: 'var(--c-red)',
          fontSize: '0.82rem',
        }}>
          {error}
        </div>
      )}

      {/* Stage panels */}
      {STAGES.map(key => {
        const events = byStage.get(key)
        if (!events || events.length === 0) return null
        const stageFetchingRows: FetchingRow[] = key === 'evidence'
          ? fetchingEvents.map(e => ({
              source:        String(e.source ?? ''),
              table:         String(e.table ?? ''),
              source_status: (e.source_status as 'running' | 'done') ?? 'done',
              count:         Number(e.count ?? 0),
              elapsed_ms:    Number(e.elapsed_ms ?? 0),
            }))
          : []
        return (
          <StagePanel
            key={key}
            stageKey={key}
            stageEvents={events}
            streamText={streamText}
            isActiveStage={activeStage === key}
            fetchingEvents={stageFetchingRows}
          />
        )
      })}

      {/* Complete CTA */}
      {isComplete && !error && requestId && (
        <div
          className="glass glass-accent animate-fade-up"
          style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
        >
          <div>
            <div style={{ fontWeight: 700, fontSize: '0.85rem', color: 'var(--c-green)' }}>
              ✓ Investigation complete
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--c-text-faint)', marginTop: 2 }}>
              ID: <code style={{ color: 'var(--c-signal)' }}>{requestId}</code>
            </div>
          </div>
          <button
            className="btn-primary"
            onClick={() => navigate(`/investigations/${requestId}`)}
          >
            View Results →
          </button>
        </div>
      )}
    </section>
  )
}

