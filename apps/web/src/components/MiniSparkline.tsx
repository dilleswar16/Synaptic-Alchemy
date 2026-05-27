/**
 * MiniSparkline — Tiny inline SVG sparkline chart.
 * Shows a filled area + line from a data array.
 */

interface Props {
  data: number[]
  width?: number
  height?: number
  color?: string
  loading?: boolean
}

export function MiniSparkline({
  data,
  width = 120,
  height = 32,
  color = 'var(--c-signal)',
  loading = false,
}: Props) {
  if (loading || data.length < 2) {
    return (
      <div
        className="skeleton-shimmer"
        style={{ width, height, borderRadius: 4 }}
      />
    )
  }

  const pad = 2
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1

  const points = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (width - 2 * pad)
    const y = pad + (1 - (v - min) / range) * (height - 2 * pad)
    return { x, y }
  })

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')
  const areaPath = `${linePath} L${points[points.length - 1].x},${height} L${points[0].x},${height} Z`

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <defs>
        <linearGradient id={`spark-fill-${color.replace(/[^a-zA-Z0-9]/g, '')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.25} />
          <stop offset="100%" stopColor={color} stopOpacity={0.02} />
        </linearGradient>
      </defs>
      <path
        d={areaPath}
        fill={`url(#spark-fill-${color.replace(/[^a-zA-Z0-9]/g, '')})`}
      />
      <path
        d={linePath}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Current value dot */}
      <circle
        cx={points[points.length - 1].x}
        cy={points[points.length - 1].y}
        r={2.5}
        fill={color}
        style={{ filter: `drop-shadow(0 0 3px ${color})` }}
      />
    </svg>
  )
}
