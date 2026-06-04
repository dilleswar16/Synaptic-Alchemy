/**
 * IncidentHeatmap.tsx — Feature 9: Incident Activity Heatmap
 *
 * GitHub-contribution-style 90-day calendar with:
 *  - Large, clickable cells (16 px default, 12 px compact)
 *  - Rich hover tooltip: date, total, per-service breakdown bars
 *  - Severity colour scale from config
 *  - Day-of-week labels + month banners
 */

import { useEffect, useState, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { fetchHeatmap, type HeatmapResponse, type HeatmapDay } from '../api/client'

interface IncidentHeatmapProps {
  days?: number
  serviceFilter?: string
  environmentFilter?: string
  onDayClick?: (date: string) => void
  compact?: boolean
}

// ── Severity colours ───────────────────────────────────────────────────────────

const SEVERITY_COLOURS: Record<HeatmapDay['severity'], string> = {
  none:     'var(--heatmap-none, #1a2235)',
  low:      'var(--heatmap-low, #0e4429)',
  medium:   'var(--heatmap-medium, #006d32)',
  high:     'var(--heatmap-high, #f59e0b)',
  critical: 'var(--heatmap-critical, #ef4444)',
}

const SEVERITY_GLOW: Record<HeatmapDay['severity'], string> = {
  none:     'transparent',
  low:      'rgba(0,109,50,0.6)',
  medium:   'rgba(0,109,50,0.8)',
  high:     'rgba(245,158,11,0.7)',
  critical: 'rgba(239,68,68,0.8)',
}

const SEVERITY_LABELS: Record<HeatmapDay['severity'], string> = {
  none:     'No incidents',
  low:      'Low',
  medium:   'Medium',
  high:     'High',
  critical: 'Critical',
}

const MONTH_NAMES = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
const WEEKDAY_SHORT = ['S','M','T','W','T','F','S']

// ── Date helpers ──────────────────────────────────────────────────────────────

function parseDate(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

function fmtDate(iso: string): string {
  const d = parseDate(iso)
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })
}

function buildWeekColumns(days: HeatmapDay[]): (HeatmapDay | null)[][] {
  if (!days.length) return []
  const first = parseDate(days[0].date)
  const padded: (HeatmapDay | null)[] = [
    ...Array(first.getDay()).fill(null),
    ...days,
  ]
  const cols: (HeatmapDay | null)[][] = []
  for (let i = 0; i < padded.length; i += 7) cols.push(padded.slice(i, i + 7))
  return cols
}

function buildMonthLabels(cols: (HeatmapDay | null)[][]): { col: number; label: string }[] {
  const seen = new Set<string>()
  const labels: { col: number; label: string }[] = []
  cols.forEach((col, ci) => {
    const first = col.find(d => d !== null)
    if (!first) return
    const d = parseDate(first.date)
    const key = `${d.getFullYear()}-${d.getMonth()}`
    if (!seen.has(key)) {
      seen.add(key)
      labels.push({ col: ci, label: MONTH_NAMES[d.getMonth()] })
    }
  })
  return labels
}

// ── Tooltip ───────────────────────────────────────────────────────────────────

// x, y are viewport (clientX/clientY) coords — tooltip uses position:fixed to escape overflow:hidden parents
interface TooltipState { x: number; y: number; day: HeatmapDay }

function HeatmapTooltip({ tooltip, cellSize }: {
  tooltip: TooltipState
  cellSize: number
}) {
  const TIP_W = 256
  const APPROX_H = 200
  const flipBelow = tooltip.y < APPROX_H
  const { day } = tooltip

  const services = day.services ? Object.entries(day.services).sort((a, b) => b[1] - a[1]) : []
  const topServices = services.slice(0, 5)
  const maxSvc = topServices[0]?.[1] ?? 1
  const color = SEVERITY_COLOURS[day.severity]

  // Clamp horizontal position to viewport edges
  const rawLeft = tooltip.x - TIP_W / 2
  const clampedLeft = Math.max(12, Math.min(rawLeft, window.innerWidth - TIP_W - 12))

  return (
    <div
      role="tooltip"
      style={{
        // position:fixed + portal = escapes all overflow:hidden and CSS transforms
        position: 'fixed',
        left: clampedLeft,
        top: flipBelow ? tooltip.y + cellSize + 8 : tooltip.y - 10,
        transform: flipBelow ? 'none' : 'translateY(-100%)',
        zIndex: 99999,
        pointerEvents: 'none',
        width: TIP_W,
        background: 'var(--c-surface, #161d2e)',
        border: `1px solid ${day.count > 0 ? color : 'var(--c-border, #2d3748)'}`,
        borderRadius: 10,
        padding: '12px 14px',
        boxShadow: day.count > 0
          ? `0 12px 40px rgba(0,0,0,0.45), 0 0 0 1px ${color}22`
          : '0 8px 24px rgba(0,0,0,0.3)',
        backdropFilter: 'blur(16px)',
        animation: 'fadeIn 0.1s ease',
      }}
    >
      <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--c-text, #e2e8f0)', marginBottom: 6, letterSpacing: '0.02em' }}>
        {fmtDate(day.date)}
      </div>

      {day.count === 0 ? (
        <div style={{ fontSize: '0.68rem', color: 'var(--c-text-muted, #64748b)' }}>No incidents</div>
      ) : (<>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: topServices.length ? 10 : 0 }}>
          <span style={{ fontSize: '1.1rem', fontWeight: 800, fontFamily: 'var(--font-mono)', color }}>{day.count}</span>
          <span style={{ fontSize: '0.68rem', color: 'var(--c-text-muted)' }}>
            investigation{day.count !== 1 ? 's' : ''}
          </span>
          <span style={{
            marginLeft: 'auto', fontSize: '0.6rem', fontWeight: 700,
            padding: '2px 6px', borderRadius: 10,
            background: `${color}22`, color, border: `1px solid ${color}44`,
            textTransform: 'uppercase', letterSpacing: '0.08em',
          }}>
            {SEVERITY_LABELS[day.severity]}
          </span>
        </div>

        {topServices.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <div style={{ fontSize: '0.58rem', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--c-text-muted)', marginBottom: 2 }}>
              By service
            </div>
            {topServices.map(([svc, cnt]) => (
              <div key={svc} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{
                  fontSize: '0.64rem', color: 'var(--c-text, #e2e8f0)',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  flex: '0 0 auto', maxWidth: 90,
                }}>
                  {svc}
                </div>
                <div style={{ flex: 1, height: 5, background: 'var(--c-border)', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{
                    width: `${Math.round((cnt / maxSvc) * 100)}%`,
                    height: '100%', background: color, borderRadius: 3,
                  }} />
                </div>
                <span style={{ fontSize: '0.62rem', fontFamily: 'var(--font-mono)', color, flexShrink: 0 }}>{cnt}</span>
              </div>
            ))}
            {services.length > 5 && (
              <div style={{ fontSize: '0.6rem', color: 'var(--c-text-muted)', marginTop: 2 }}>
                +{services.length - 5} more services
              </div>
            )}
          </div>
        )}
      </>)}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function IncidentHeatmap({
  days = 90, serviceFilter, environmentFilter, onDayClick, compact = false,
}: IncidentHeatmapProps) {
  const [data, setData] = useState<HeatmapResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)
  const [activeDate, setActiveDate] = useState<string | null>(null)

  useEffect(() => {
    setIsLoading(true); setError(null)
    fetchHeatmap(days, serviceFilter, environmentFilter)
      .then(setData)
      .catch(e => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setIsLoading(false))
  }, [days, serviceFilter, environmentFilter])

  const handleMouseEnter = useCallback((e: React.MouseEvent, day: HeatmapDay) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    // Use viewport coordinates so tooltip renders via position:fixed, escaping overflow:hidden parents
    setTooltip({
      x: rect.left + rect.width / 2,
      y: rect.top,
      day,
    })
  }, [])

  const CELL = compact ? 12 : 16
  const GAP  = compact ? 2 : 3

  if (isLoading) return (
    <div id="incident-heatmap" style={{ padding: compact ? 0 : '4px 0' }}>
      <div style={{ display: 'flex', gap: GAP, flexWrap: 'nowrap', overflowX: 'auto' }}>
        {Array.from({ length: 13 }).map((_, i) => (
          <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: GAP }}>
            {Array.from({ length: 7 }).map((_, j) => (
              <div key={j} className="pulse-skeleton" style={{
                width: CELL, height: CELL, borderRadius: 3,
              }} />
            ))}
          </div>
        ))}
      </div>
    </div>
  )

  if (error) return (
    <div id="incident-heatmap" style={{ padding: '12px', fontSize: '0.78rem', color: 'var(--c-red)' }}>
      ⚠ {error}
    </div>
  )

  if (!data || data.days.length === 0) return (
    <div id="incident-heatmap" style={{ padding: '12px', fontSize: '0.78rem', color: 'var(--c-text-muted)' }}>
      No investigation data in the last {days} days.
    </div>
  )

  const columns = buildWeekColumns(data.days)
  const monthLabels = buildMonthLabels(columns)

  const totalWidth = columns.length * (CELL + GAP) - GAP

  return (
    <div id="incident-heatmap" style={{ position: 'relative', userSelect: 'none' }}>

      {/* ── Header ───────────────────────────────────────────────────── */}
      {!compact && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
          <div>
            <div style={{
              fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 700,
              letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--c-accent)',
              marginBottom: 4,
            }}>
              Incident Activity
            </div>
            <div style={{ fontSize: '0.82rem', color: 'var(--c-text-muted)' }}>
              Last {days} days &nbsp;·&nbsp;
              <strong style={{ color: 'var(--c-text)' }}>{data.total_incidents}</strong> investigations &nbsp;·&nbsp;
              Peak <strong style={{ color: 'var(--c-text)' }}>{data.max_count}</strong>/day
            </div>
          </div>
          {/* Legend */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: '0.65rem', color: 'var(--c-text-muted)' }}>None</span>
            {(['none','low','medium','high','critical'] as const).map(s => (
              <div key={s} title={SEVERITY_LABELS[s]} style={{
                width: CELL, height: CELL, borderRadius: 3,
                background: SEVERITY_COLOURS[s],
                border: '1px solid rgba(255,255,255,0.04)',
              }} />
            ))}
            <span style={{ fontSize: '0.65rem', color: 'var(--c-text-muted)' }}>Critical</span>
          </div>
        </div>
      )}

      {/* ── Calendar grid ─────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 6, overflowX: 'auto', paddingBottom: 4 }}>
        {/* Weekday labels */}
        {!compact && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: GAP, paddingTop: 18, marginRight: 2 }}>
            {WEEKDAY_SHORT.map((d, i) => (
              <div key={i} style={{
                width: 14, height: CELL, display: 'flex', alignItems: 'center',
                fontSize: '0.58rem', color: i % 2 === 1 ? 'var(--c-text-muted)' : 'transparent',
                fontFamily: 'var(--font-mono)', userSelect: 'none',
              }}>
                {i % 2 === 1 ? d : ''}
              </div>
            ))}
          </div>
        )}

        <div style={{ position: 'relative', minWidth: totalWidth }}>
          {/* Month labels */}
          <div style={{ position: 'relative', height: compact ? 0 : 18, marginBottom: compact ? 0 : 2 }}>
            {!compact && monthLabels.map(({ col, label }) => (
              <span key={`${col}-${label}`} style={{
                position: 'absolute',
                left: col * (CELL + GAP),
                fontSize: '0.65rem', color: 'var(--c-text-muted)',
                fontFamily: 'var(--font-mono)',
                whiteSpace: 'nowrap',
              }}>
                {label}
              </span>
            ))}
          </div>

          {/* Cells */}
          <div
            style={{ display: 'flex', gap: GAP }}
            onMouseLeave={() => setTooltip(null)}
          >
            {columns.map((col, ci) => (
              <div key={ci} style={{ display: 'flex', flexDirection: 'column', gap: GAP }}>
                {col.map((day, ri) => day === null ? (
                  <div key={`e-${ci}-${ri}`} style={{ width: CELL, height: CELL, borderRadius: 3 }} />
                ) : (
                  <div
                    key={day.date}
                    id={`heatmap-cell-${day.date}`}
                    onClick={() => {
                      if (day.count === 0) return
                      const n = activeDate === day.date ? null : day.date
                      setActiveDate(n)
                      if (n) onDayClick?.(n)
                    }}
                    onMouseEnter={e => handleMouseEnter(e, day)}
                    style={{
                      width: CELL,
                      height: CELL,
                      borderRadius: 3,
                      background: SEVERITY_COLOURS[day.severity],
                      cursor: day.count > 0 ? 'pointer' : 'default',
                      transition: 'transform 0.12s ease, box-shadow 0.12s ease',
                      transform: activeDate === day.date ? 'scale(1.45)' : undefined,
                      boxShadow: activeDate === day.date
                        ? `0 0 0 2px var(--c-accent), 0 0 10px ${SEVERITY_GLOW[day.severity]}`
                        : 'none',
                      border: '1px solid rgba(255,255,255,0.04)',
                    }}
                    onMouseOver={e => {
                      if (day.count > 0) {
                        (e.currentTarget as HTMLDivElement).style.transform = activeDate === day.date ? 'scale(1.45)' : 'scale(1.35)'
                        ;(e.currentTarget as HTMLDivElement).style.boxShadow = `0 0 8px ${SEVERITY_GLOW[day.severity]}`
                        ;(e.currentTarget as HTMLDivElement).style.zIndex = '10'
                      }
                    }}
                    onMouseOut={e => {
                      if (day.count > 0 && activeDate !== day.date) {
                        (e.currentTarget as HTMLDivElement).style.transform = ''
                        ;(e.currentTarget as HTMLDivElement).style.boxShadow = 'none'
                        ;(e.currentTarget as HTMLDivElement).style.zIndex = ''
                      }
                    }}
                  />
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Tooltip rendered into document.body via portal — escapes overflow:hidden and transform stacking contexts */}
      {tooltip && createPortal(
        <HeatmapTooltip tooltip={tooltip} cellSize={CELL} />,
        document.body,
      )}
    </div>
  )
}
