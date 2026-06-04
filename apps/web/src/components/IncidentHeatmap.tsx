/**
 * IncidentHeatmap.tsx — Feature 9: Incident Heatmap Calendar
 *
 * GitHub-contribution-style 90-day heatmap of investigation density.
 * Five severity colour shades from investigation.yaml thresholds.
 *
 * Clicking a day fires the optional onDayClick callback with the ISO date
 * so parent components can filter the investigations list.
 */

import { useEffect, useState, useRef } from 'react'
import { fetchHeatmap, type HeatmapResponse, type HeatmapDay } from '../../api/client'

// ── Types ─────────────────────────────────────────────────────────────────────

interface IncidentHeatmapProps {
  /** Number of days to display (default 90, capped by server) */
  days?: number
  serviceFilter?: string
  environmentFilter?: string
  /** Called when user clicks a day cell */
  onDayClick?: (date: string) => void
  /** Compact mode: hide legend and controls */
  compact?: boolean
}

// ── Severity colour map (CSS vars for dark/light mode support) ─────────────

const SEVERITY_COLOURS: Record<HeatmapDay['severity'], string> = {
  none:     'var(--heatmap-none)',
  low:      'var(--heatmap-low)',
  medium:   'var(--heatmap-medium)',
  high:     'var(--heatmap-high)',
  critical: 'var(--heatmap-critical)',
}

const SEVERITY_LABELS: Record<HeatmapDay['severity'], string> = {
  none:     'None',
  low:      'Low',
  medium:   'Medium',
  high:     'High',
  critical: 'Critical',
}

const WEEKDAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                     'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// ── Utility ───────────────────────────────────────────────────────────────────

function parseDate(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

function isoFromDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Group flat day list into columns of 7 (one column = one week, Sun→Sat). */
function buildWeekColumns(days: HeatmapDay[]): HeatmapDay[][] {
  if (days.length === 0) return []
  // Pad the start so the first day aligns to its correct weekday
  const first = parseDate(days[0].date)
  const startOffset = first.getDay() // 0=Sun
  const padded: (HeatmapDay | null)[] = [
    ...Array(startOffset).fill(null),
    ...days,
  ]
  const columns: HeatmapDay[][] = []
  for (let i = 0; i < padded.length; i += 7) {
    columns.push(padded.slice(i, i + 7) as HeatmapDay[])
  }
  return columns
}

/** Return month label positions for each column. */
function buildMonthLabels(columns: (HeatmapDay | null)[][]): Array<{ col: number; label: string }> {
  const seen = new Set<string>()
  const labels: Array<{ col: number; label: string }> = []
  columns.forEach((col, ci) => {
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

interface TooltipState {
  x: number
  y: number
  day: HeatmapDay
}

// ── Main component ────────────────────────────────────────────────────────────

export default function IncidentHeatmap({
  days = 90,
  serviceFilter,
  environmentFilter,
  onDayClick,
  compact = false,
}: IncidentHeatmapProps) {
  const [data, setData] = useState<HeatmapResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)
  const [activeDate, setActiveDate] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setIsLoading(true)
    setError(null)
    fetchHeatmap(days, serviceFilter, environmentFilter)
      .then(setData)
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load heatmap'))
      .finally(() => setIsLoading(false))
  }, [days, serviceFilter, environmentFilter])

  if (isLoading) {
    return (
      <div className="heatmap-wrapper" id="incident-heatmap">
        <div className="heatmap-skeleton">
          {Array.from({ length: 13 }).map((_, i) => (
            <div key={i} className="heatmap-col-skeleton">
              {Array.from({ length: 7 }).map((_, j) => (
                <div key={j} className="heatmap-cell-skeleton pulse-skeleton" />
              ))}
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="heatmap-wrapper" id="incident-heatmap">
        <div className="heatmap-error">⚠️ {error}</div>
      </div>
    )
  }

  if (!data || data.days.length === 0) {
    return (
      <div className="heatmap-wrapper" id="incident-heatmap">
        <div className="heatmap-empty">No investigation data in the last {days} days.</div>
      </div>
    )
  }

  const columns = buildWeekColumns(data.days)
  const monthLabels = buildMonthLabels(columns)

  const handleCellClick = (day: HeatmapDay) => {
    if (day.count === 0) return
    const newActive = activeDate === day.date ? null : day.date
    setActiveDate(newActive)
    if (newActive) onDayClick?.(newActive)
  }

  const handleMouseEnter = (e: React.MouseEvent, day: HeatmapDay) => {
    const rect = (e.target as HTMLElement).getBoundingClientRect()
    const containerRect = containerRef.current?.getBoundingClientRect()
    setTooltip({
      x: rect.left - (containerRect?.left ?? 0) + rect.width / 2,
      y: rect.top - (containerRect?.top ?? 0),
      day,
    })
  }

  const handleMouseLeave = () => setTooltip(null)

  const CELL_SIZE = compact ? 10 : 13
  const CELL_GAP = 2

  return (
    <div className="heatmap-wrapper" id="incident-heatmap" ref={containerRef}>
      {!compact && (
        <div className="heatmap-header">
          <div className="heatmap-title">
            📅 Incident Activity
            <span className="heatmap-subtitle"> — last {days} days</span>
          </div>
          <div className="heatmap-stats">
            <span className="heatmap-stat">
              <strong>{data.total_incidents}</strong> investigations
            </span>
            <span className="heatmap-stat-divider">·</span>
            <span className="heatmap-stat">
              Peak <strong>{data.max_count}</strong>/day
            </span>
          </div>
        </div>
      )}

      <div className="heatmap-scroll-wrapper">
        {/* Month labels */}
        <div className="heatmap-month-row" style={{ paddingLeft: compact ? 0 : 28 }}>
          {monthLabels.map(({ col, label }) => (
            <span
              key={`${col}-${label}`}
              className="heatmap-month-label"
              style={{ left: col * (CELL_SIZE + CELL_GAP) }}
            >
              {label}
            </span>
          ))}
        </div>

        <div className="heatmap-inner">
          {/* Weekday labels */}
          {!compact && (
            <div className="heatmap-weekday-labels">
              {WEEKDAY_LABELS.map((d, i) => (
                <span key={d} className={`heatmap-weekday-label ${i % 2 === 1 ? 'visible' : ''}`}>
                  {i % 2 === 1 ? d : ''}
                </span>
              ))}
            </div>
          )}

          {/* Grid */}
          <div
            className="heatmap-grid"
            style={{ gap: CELL_GAP, gridTemplateColumns: `repeat(${columns.length}, ${CELL_SIZE}px)` }}
            onMouseLeave={handleMouseLeave}
          >
            {columns.map((col, ci) => (
              <div key={ci} className="heatmap-col" style={{ gap: CELL_GAP }}>
                {col.map((day, ri) =>
                  day === null ? (
                    <div
                      key={`empty-${ci}-${ri}`}
                      className="heatmap-cell empty"
                      style={{ width: CELL_SIZE, height: CELL_SIZE }}
                    />
                  ) : (
                    <div
                      key={day.date}
                      id={`heatmap-cell-${day.date}`}
                      className={`heatmap-cell ${day.count > 0 ? 'interactive' : ''} ${activeDate === day.date ? 'active' : ''}`}
                      style={{
                        width: CELL_SIZE,
                        height: CELL_SIZE,
                        background: SEVERITY_COLOURS[day.severity],
                        cursor: day.count > 0 ? 'pointer' : 'default',
                        transform: activeDate === day.date ? 'scale(1.3)' : undefined,
                      }}
                      onClick={() => handleCellClick(day)}
                      onMouseEnter={e => handleMouseEnter(e, day)}
                    />
                  ),
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div
          className="heatmap-tooltip"
          style={{
            left: tooltip.x,
            top: tooltip.y - 8,
            transform: 'translate(-50%, -100%)',
          }}
          role="tooltip"
        >
          <div className="heatmap-tooltip-date">{tooltip.day.date}</div>
          <div className="heatmap-tooltip-count">
            {tooltip.day.count === 0
              ? 'No incidents'
              : `${tooltip.day.count} investigation${tooltip.day.count !== 1 ? 's' : ''}`}
          </div>
          {tooltip.day.count > 0 && (
            <div
              className="heatmap-tooltip-severity"
              style={{ color: SEVERITY_COLOURS[tooltip.day.severity] }}
            >
              {SEVERITY_LABELS[tooltip.day.severity]}
            </div>
          )}
        </div>
      )}

      {/* Legend */}
      {!compact && (
        <div className="heatmap-legend">
          <span className="heatmap-legend-label">Less</span>
          {(['none', 'low', 'medium', 'high', 'critical'] as const).map(s => (
            <div
              key={s}
              className="heatmap-legend-cell"
              style={{ background: SEVERITY_COLOURS[s] }}
              title={SEVERITY_LABELS[s]}
            />
          ))}
          <span className="heatmap-legend-label">More</span>
        </div>
      )}
    </div>
  )
}
