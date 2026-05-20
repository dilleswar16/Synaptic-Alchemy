/**
 * ApimChart — universal chart renderer for APIM analytics tool results.
 *
 * Dispatches to the correct chart type based on `chart_type` from the backend:
 *   "area"    → Recharts AreaChart (time-series)
 *   "bar"     → Recharts BarChart
 *   "pie"     → Recharts PieChart
 *   "heatmap" → Nivo HeatMap (fund × hour-of-day)
 *   "tiles"   → custom KPI tile grid
 *   "table"   → plain data table
 *
 * All charts use the Corvin dark theme palette.
 */

import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { useState as _useHeatmapState } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ApimChartData {
  rows: Record<string, unknown>[]
  columns: string[]
  chart_type: 'area' | 'bar' | 'pie' | 'heatmap' | 'table' | 'tiles'
  title: string
  subtitle: string
  template_name: string
  time_range_minutes?: number
  api_filter?: string
  row_count: number
  error?: string
}

interface ApimChartProps {
  data: ApimChartData
  /** compact mode: shorter height for inline-in-chat rendering */
  compact?: boolean
}

// ── Theme palette ─────────────────────────────────────────────────────────────

const PALETTE = [
  '#0d9488', // teal (primary)
  '#38bdf8', // sky blue
  '#34d399', // emerald
  '#2dd4bf', // teal-300
  '#fb7185', // rose
  '#fbbf24', // amber
  '#22d3ee', // cyan
  '#f472b6', // pink
]

const CHART_STYLE: React.CSSProperties = {
  fontSize: '0.68rem',
  fontFamily: 'var(--font-mono)',
}

const AXIS_TICK = { fill: 'var(--c-text-faint)', fontSize: 10 }
const GRID_STROKE = 'var(--c-border)'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: false })
  } catch { return iso }
}

function fmtDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString('en-AU', { month: 'short', day: 'numeric' }) + ' ' +
      d.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: false })
  } catch { return iso }
}

function isTimestamp(val: unknown): boolean {
  if (typeof val !== 'string') return false
  return /^\d{4}-\d{2}-\d{2}T/.test(val)
}

function numericCols(columns: string[], sample: Record<string, unknown>): string[] {
  return columns.filter(c => typeof sample[c] === 'number')
}

function firstTimestampCol(columns: string[], sample: Record<string, unknown>): string | null {
  return columns.find(c => isTimestamp(sample[c] as string)) ?? null
}

/** True when rows have both a categorical "fund" dimension and a numeric "hour" dimension */
function isHeatmapCompatible(rows: Record<string, unknown>[], columns: string[]): boolean {
  if (rows.length === 0) return false
  const lower = columns.map(c => c.toLowerCase())
  const hasFund = lower.some(c => c.includes('fund') || c === 'id')
  const hasHour = lower.some(c => c.includes('hour') || c === 'x')
  const hasCount = lower.some(c => c.includes('count') || c.includes('request') || c === 'y')
  return hasFund && hasHour && hasCount
}

// Custom Tooltip ──────────────────────────────────────────────────────────────

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'var(--c-surface-2)', border: '1px solid var(--c-border-hi)',
      borderRadius: 8, padding: '8px 12px', fontSize: '0.7rem', fontFamily: 'var(--font-mono)',
      boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
    }}>
      {label && <div style={{ color: 'var(--c-text-faint)', marginBottom: 6 }}>{label}</div>}
      {payload.map((p: any, i: number) => (
        <div key={i} style={{ color: p.color ?? PALETTE[i], marginBottom: 2 }}>
          {p.name}: <strong>{typeof p.value === 'number' ? p.value.toLocaleString() : p.value}</strong>
        </div>
      ))}
    </div>
  )
}

// ── Sub-chart renderers ───────────────────────────────────────────────────────

function AreaChartView({ data, compact }: { data: ApimChartData; compact: boolean }) {
  const { rows, columns } = data
  if (!rows.length) return <EmptyState />
  const sample = rows[0]
  const tsCol = firstTimestampCol(columns, sample)
  const valueKey = tsCol ? columns.find(c => c !== tsCol) : columns[0]

  // Build recharts-friendly data
  const chartData = rows.map(r => {
    const out: Record<string, unknown> = {}
    columns.forEach(c => { out[c] = r[c] })
    if (tsCol && typeof r[tsCol] === 'string') {
      out['_label'] = data.time_range_minutes && data.time_range_minutes <= 1440
        ? fmtTime(r[tsCol] as string)
        : fmtDate(r[tsCol] as string)
    }
    return out
  })

  const xKey = tsCol ? '_label' : (valueKey ?? columns[0])
  const seriesKeys = tsCol
    ? columns.filter(c => c !== tsCol)
    : columns.filter(c => c !== xKey)

  const height = compact ? 180 : 240

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={chartData} style={CHART_STYLE} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
        <defs>
          {seriesKeys.map((k, i) => (
            <linearGradient key={k} id={`grad-${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={PALETTE[i % PALETTE.length]} stopOpacity={0.35} />
              <stop offset="95%" stopColor={PALETTE[i % PALETTE.length]} stopOpacity={0.02} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
        <XAxis dataKey={xKey} tick={AXIS_TICK} interval="preserveStartEnd" />
        <YAxis tick={AXIS_TICK} width={48} />
        <Tooltip content={<ChartTooltip />} />
        {seriesKeys.length > 1 && <Legend wrapperStyle={{ fontSize: '0.65rem', color: 'var(--c-text-faint)' }} />}
        {seriesKeys.map((k, i) => (
          <Area
            key={k}
            type="monotone"
            dataKey={k}
            stroke={PALETTE[i % PALETTE.length]}
            strokeWidth={1.5}
            fill={`url(#grad-${i})`}
            dot={false}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  )
}

function BarChartView({ data, compact }: { data: ApimChartData; compact: boolean }) {
  const { rows, columns } = data
  if (!rows.length) return <EmptyState />
  const sample = rows[0]
  const numCols = numericCols(columns, sample)
  const catCol = columns.find(c => !numCols.includes(c)) ?? columns[0]
  const seriesKeys = numCols

  const height = compact ? 180 : 260

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={rows as any[]}
        style={CHART_STYLE}
        margin={{ top: 6, right: 12, left: 0, bottom: rows.length > 6 ? 40 : 0 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
        <XAxis
          dataKey={catCol}
          tick={{ ...AXIS_TICK, angle: rows.length > 6 ? -30 : 0, textAnchor: rows.length > 6 ? 'end' : 'middle' }}
          interval={0}
        />
        <YAxis tick={AXIS_TICK} width={48} />
        <Tooltip content={<ChartTooltip />} />
        {seriesKeys.length > 1 && <Legend wrapperStyle={{ fontSize: '0.65rem', color: 'var(--c-text-faint)' }} />}
        {seriesKeys.map((k, i) => (
          <Bar key={k} dataKey={k} fill={PALETTE[i % PALETTE.length]} radius={[3, 3, 0, 0]} maxBarSize={40} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}

function PieChartView({ data, compact }: { data: ApimChartData; compact: boolean }) {
  const { rows, columns } = data
  if (!rows.length) return <EmptyState />
  const sample = rows[0]
  const numCols = numericCols(columns, sample)
  const labelCol = columns.find(c => !numCols.includes(c)) ?? columns[0]
  const valueCol = numCols[0] ?? columns[1]

  const pieData = rows.map((r, i) => ({
    name: String(r[labelCol]),
    value: Number(r[valueCol] ?? 0),
    color: PALETTE[i % PALETTE.length],
  }))

  const height = compact ? 170 : 220
  const outerR = compact ? 60 : 80

  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart style={CHART_STYLE}>
        <Pie
          data={pieData}
          cx="45%"
          cy="50%"
          outerRadius={outerR}
          innerRadius={outerR * 0.55}
          dataKey="value"
          paddingAngle={2}
          label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
          labelLine={false}
        >
          {pieData.map((entry, i) => (
            <Cell key={i} fill={entry.color} stroke="transparent" />
          ))}
        </Pie>
        <Tooltip content={<ChartTooltip />} />
        <Legend
          wrapperStyle={{ fontSize: '0.65rem', color: 'var(--c-text-faint)' }}
          layout="vertical"
          align="right"
          verticalAlign="middle"
        />
      </PieChart>
    </ResponsiveContainer>
  )
}

function HeatmapView({ data, compact }: { data: ApimChartData; compact: boolean }) {
  const { rows } = data
  const [tooltip, setTooltip] = _useHeatmapState<{ fund: string; hour: number; count: number; x: number; y: number } | null>(null)
  if (!rows.length) return <EmptyState />

  // Build fund → hour → count matrix
  const grouped: Record<string, Record<number, number>> = {}
  rows.forEach(r => {
    const fund = String(r['FundCode'] ?? r['id'] ?? 'Unknown')
    const hour = Number(r['HourOfDay'] ?? r['x'] ?? 0)
    const count = Number(r['RequestCount'] ?? r['y'] ?? 0)
    if (!grouped[fund]) grouped[fund] = {}
    grouped[fund][hour] = (grouped[fund][hour] ?? 0) + count
  })

  const funds = Object.keys(grouped).sort()
  const hours = Array.from({ length: 24 }, (_, i) => i)
  let maxVal = 1
  funds.forEach(f => hours.forEach(h => { maxVal = Math.max(maxVal, grouped[f][h] ?? 0) }))

  // 5-stop color ramp: empty → faint → warm → hot → peak
  function cellColor(v: number): { bg: string; border: string } {
    if (v === 0) return { bg: 'var(--c-surface-3)', border: 'var(--c-border)' }
    const t = Math.pow(v / maxVal, 0.5)
    if (t < 0.2) return { bg: 'rgba(13,148,136,0.12)', border: 'rgba(13,148,136,0.2)' }
    if (t < 0.45) return { bg: 'rgba(13,148,136,0.3)', border: 'rgba(13,148,136,0.4)' }
    if (t < 0.7) return { bg: 'rgba(15,118,110,0.55)', border: 'rgba(15,118,110,0.65)' }
    if (t < 0.9) return { bg: 'rgba(17,94,89,0.75)', border: 'rgba(17,94,89,0.85)' }
    return { bg: '#0f766e', border: '#115e59' }
  }

  const cellH = compact ? 36 : 48
  const labelW = 72
  const gap = 3

  return (
    <div style={{ position: 'relative', userSelect: 'none' }}>
      {/* Column headers (hours) */}
      <div style={{ display: 'flex', alignItems: 'flex-end', paddingLeft: labelW, marginBottom: 6, gap }}>
        {hours.map(h => (
          <div key={h} style={{
            flex: 1, textAlign: 'center',
            fontSize: '0.6rem', color: h % 3 === 0 ? 'var(--c-text-muted)' : 'transparent',
            fontFamily: 'var(--font-mono)', fontWeight: 500,
          }}>
            {String(h).padStart(2, '0')}
          </div>
        ))}
      </div>

      {/* Grid rows */}
      {funds.map(fund => (
        <div key={fund} style={{ display: 'flex', alignItems: 'center', marginBottom: gap }}>
          {/* Fund label */}
          <div style={{
            width: labelW, minWidth: labelW, textAlign: 'right', paddingRight: 10,
            fontSize: '0.72rem', fontWeight: 600, color: 'var(--c-text)',
            fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {fund}
          </div>

          {/* Cells */}
          <div style={{ display: 'flex', flex: 1, gap }}>
            {hours.map(h => {
              const v = grouped[fund][h] ?? 0
              const { bg, border } = cellColor(v)
              const isPeak = v === maxVal && v > 0
              return (
                <div
                  key={h}
                  style={{
                    flex: 1,
                    height: cellH,
                    borderRadius: 6,
                    background: bg,
                    border: `1px solid ${border}`,
                    cursor: v > 0 ? 'crosshair' : 'default',
                    transition: 'transform 0.12s, box-shadow 0.12s',
                    boxShadow: isPeak ? '0 0 6px rgba(13,148,136,0.2)' : 'none',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}
                  onMouseEnter={e => {
                    if (v > 0) {
                      const rect = (e.target as HTMLElement).getBoundingClientRect()
                      setTooltip({ fund, hour: h, count: v, x: rect.left + rect.width / 2, y: rect.top })
                    }
                  }}
                  onMouseLeave={() => setTooltip(null)}
                >
                  {/* Show count inside large cells when value is significant */}
                  {v > 0 && !compact && cellH >= 44 && (
                    <span style={{
                      fontSize: '0.6rem', fontWeight: 700,
                      fontFamily: 'var(--font-mono)',
                      color: Math.pow(v / maxVal, 0.5) > 0.5 ? 'rgba(255,255,255,0.9)' : 'var(--c-text-muted)',
                      lineHeight: 1,
                    }}>
                      {v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}

      {/* Color legend */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14, paddingLeft: labelW }}>
        <span style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)' }}>0</span>
        <div style={{ display: 'flex', gap: 2, flex: 1, maxWidth: 180 }}>
          {['rgba(13,148,136,0.12)', 'rgba(13,148,136,0.3)', 'rgba(15,118,110,0.55)', 'rgba(17,94,89,0.75)', '#0f766e'].map((c, i) => (
            <div key={i} style={{ flex: 1, height: 8, borderRadius: 4, background: c }} />
          ))}
        </div>
        <span style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)' }}>{maxVal.toLocaleString()}</span>
      </div>

      {/* Hover tooltip */}
      {tooltip && (
        <div style={{
          position: 'fixed',
          left: tooltip.x, top: tooltip.y - 52,
          transform: 'translateX(-50%)',
          background: 'var(--c-surface)', border: '1px solid var(--c-border-hi)',
          borderRadius: 10, padding: '8px 14px',
          fontSize: '0.75rem', fontFamily: 'var(--font-mono)',
          color: 'var(--c-text)', pointerEvents: 'none',
          zIndex: 9999, whiteSpace: 'nowrap',
          boxShadow: 'var(--shadow-lg)',
        }}>
          <div style={{ fontWeight: 600, color: 'var(--c-signal)', marginBottom: 2 }}>{tooltip.fund}</div>
          <div>
            <span style={{ color: 'var(--c-text-muted)' }}>{String(tooltip.hour).padStart(2, '0')}:00</span>
            {' — '}
            <span style={{ fontWeight: 700 }}>{tooltip.count.toLocaleString()}</span>
            <span style={{ color: 'var(--c-text-muted)' }}> requests</span>
          </div>
        </div>
      )}
    </div>
  )
}

function TilesView({ data }: { data: ApimChartData }) {
  const { rows } = data
  if (!rows.length) return <EmptyState />
  const row = rows[0]
  const entries = Object.entries(row).filter(([, v]) => v !== null && v !== undefined)

  const metricColors: Record<string, string> = {
    SuccessRate: 'var(--c-green)',
    ErrorCount: 'var(--c-red)',
    AvgResponseTimeMs: 'var(--c-signal)',
    UniqueMembers: 'var(--c-info)',
    TotalRequests: 'var(--c-purple)',
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 8 }}>
      {entries.map(([key, val]) => {
        const color = metricColors[key] ?? 'var(--c-text-muted)'
        const isRate = key.toLowerCase().includes('rate')
        const isMs = key.toLowerCase().includes('ms')
        const suffix = isRate ? '%' : isMs ? 'ms' : ''
        return (
          <div key={key} style={{
            background: `${color}10`,
            border: `1px solid ${color}30`,
            borderRadius: 10,
            padding: '10px 12px',
          }}>
            <div style={{ fontSize: '0.6rem', color: 'var(--c-text-faint)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 6 }}>
              {key.replace(/([A-Z])/g, ' $1').trim()}
            </div>
            <div style={{ fontSize: '1.25rem', fontWeight: 800, color, fontFamily: 'var(--font-display)', lineHeight: 1 }}>
              {typeof val === 'number' ? val.toLocaleString() : String(val)}
              {suffix && <span style={{ fontSize: '0.65rem', fontWeight: 400, marginLeft: 2 }}>{suffix}</span>}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function TableView({ data, compact }: { data: ApimChartData; compact: boolean }) {
  const { rows, columns } = data
  if (!rows.length) return <EmptyState />
  const displayRows = compact ? rows.slice(0, 8) : rows

  const numericSet = new Set(columns.filter(c => typeof rows[0][c] === 'number'))

  return (
    <div style={{ overflowX: 'auto', overflowY: 'auto', maxHeight: compact ? 240 : 360, borderRadius: 8, border: '1px solid var(--c-border)' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.68rem', fontFamily: 'var(--font-mono)' }}>
        <thead>
          <tr style={{ background: 'var(--c-surface-2)', position: 'sticky', top: 0, zIndex: 1 }}>
            {columns.map(c => (
              <th key={c} style={{
                padding: '7px 10px', textAlign: 'left', borderBottom: '1px solid var(--c-border)',
                color: 'var(--c-signal)', fontWeight: 700, letterSpacing: '0.05em',
                whiteSpace: 'nowrap', textTransform: 'uppercase', fontSize: '0.6rem',
              }}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {displayRows.map((row, i) => (
            <tr key={i} style={{ borderBottom: '1px solid var(--c-border)', background: i % 2 === 0 ? 'transparent' : 'var(--c-surface-2)' }}>
              {columns.map(c => {
                const v = row[c]
                const isNum = numericSet.has(c)
                const display = isTimestamp(v) ? fmtDate(v as string) : (v === null || v === undefined) ? '—' : String(v)
                return (
                  <td key={c} style={{
                    padding: '6px 10px',
                    textAlign: isNum ? 'right' : 'left',
                    fontWeight: isNum ? 600 : 400,
                    color: isNum ? 'var(--c-text)' : 'var(--c-text-dim)',
                    whiteSpace: 'nowrap', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis',
                  } as React.CSSProperties}>
                    {display}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {compact && rows.length > 8 && (
        <div style={{ textAlign: 'center', padding: '6px', color: 'var(--c-text-faint)', fontSize: '0.65rem', borderTop: '1px solid var(--c-border)' }}>
          +{rows.length - 8} more rows
        </div>
      )}
    </div>
  )
}

function EmptyState() {
  return (
    <div style={{ textAlign: 'center', padding: '24px 0', color: 'var(--c-text-faint)', fontSize: '0.72rem', fontFamily: 'var(--font-mono)' }}>
      No data returned for this time range / filter.
      <br />
      <span style={{ fontSize: '0.65rem', opacity: 0.6 }}>Try a wider time window or "all" API filter.</span>
    </div>
  )
}

function ErrorState({ message }: { message: string }) {
  return (
    <div style={{ padding: '12px 14px', borderRadius: 8, background: 'var(--c-error-bg)', border: '1px solid var(--c-error-border)', color: 'var(--c-red)', fontSize: '0.72rem', fontFamily: 'var(--font-mono)' }}>
      ⚠ {message}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ApimChart({ data, compact = false }: ApimChartProps) {
  if (!data) return null

  const { chart_type, title, subtitle, error, row_count, time_range_minutes, api_filter } = data

  return (
    <div style={{
      marginTop: 4,
      background: 'var(--c-surface-2)',
      border: '1px solid var(--c-border-hi)',
      borderRadius: 12,
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{ padding: '10px 14px 6px', borderBottom: '1px solid var(--c-border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <div style={{ fontWeight: 700, fontSize: '0.78rem', color: 'var(--c-text)', fontFamily: 'var(--font-body)' }}>
            {title}
          </div>
          <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
            {api_filter && api_filter !== 'all' && (
              <span style={{ padding: '2px 7px', borderRadius: 4, background: 'var(--c-signal-light)', border: '1px solid var(--c-signal-dim)', color: 'var(--c-signal)', fontSize: '0.62rem', fontFamily: 'var(--font-mono)' }}>
                {api_filter}
              </span>
            )}
            {time_range_minutes && (
              <span style={{ padding: '2px 7px', borderRadius: 4, background: 'var(--c-surface-3)', border: '1px solid var(--c-border)', color: 'var(--c-text-faint)', fontSize: '0.62rem', fontFamily: 'var(--font-mono)' }}>
                {time_range_minutes >= 10080 ? `${Math.round(time_range_minutes / 10080)}w`
                  : time_range_minutes >= 1440 ? `${Math.round(time_range_minutes / 1440)}d`
                  : time_range_minutes >= 60 ? `${Math.round(time_range_minutes / 60)}h`
                  : `${time_range_minutes}m`}
              </span>
            )}
            {row_count !== undefined && (
              <span style={{ padding: '2px 7px', borderRadius: 4, background: 'var(--c-info-bg)', border: '1px solid var(--c-info-border)', color: 'var(--c-info)', fontSize: '0.62rem', fontFamily: 'var(--font-mono)' }}>
                {row_count} rows
              </span>
            )}
          </div>
        </div>
        {subtitle && !compact && (
          <div style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)', marginTop: 3 }}>
            {subtitle}
          </div>
        )}
      </div>

      {/* Chart body */}
      <div style={{ padding: compact ? '10px 10px' : '12px 14px' }}>
        {error ? (
          <ErrorState message={error} />
        ) : chart_type === 'area' ? (
          <AreaChartView data={data} compact={compact} />
        ) : chart_type === 'bar' ? (
          <BarChartView data={data} compact={compact} />
        ) : chart_type === 'pie' ? (
          <PieChartView data={data} compact={compact} />
        ) : chart_type === 'heatmap' && isHeatmapCompatible(data.rows, data.columns) ? (
          <HeatmapView data={data} compact={compact} />
        ) : chart_type === 'heatmap' ? (
          // Data doesn't have fund×hour structure — fall back to bar chart
          <BarChartView data={data} compact={compact} />
        ) : chart_type === 'tiles' ? (
          <TilesView data={data} />
        ) : (
          <TableView data={data} compact={compact} />
        )}
      </div>
    </div>
  )
}
