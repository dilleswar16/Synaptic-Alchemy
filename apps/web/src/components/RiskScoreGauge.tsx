/**
 * RiskScoreGauge — Animated SVG radial gauge for the incident risk score.
 * Shows a ring from 0–100 with color-coded gradient and centered number.
 */

interface Props {
  score: number
  size?: number
  loading?: boolean
}

function bandColor(score: number): string {
  if (score >= 75) return 'var(--c-red)'
  if (score >= 55) return 'var(--c-warning)'
  if (score >= 35) return 'var(--c-info)'
  return 'var(--c-green)'
}

function bandLabel(score: number): string {
  if (score >= 75) return 'CRITICAL'
  if (score >= 55) return 'HIGH'
  if (score >= 35) return 'WATCH'
  return 'LOW'
}

export function RiskScoreGauge({ score, size = 140, loading = false }: Props) {
  const strokeWidth = 10
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const progress = loading ? 0 : Math.min(score, 100) / 100
  const offset = circumference * (1 - progress)
  const color = loading ? 'var(--c-border)' : bandColor(score)

  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: 'rotate(-90deg)' }}>
        {/* Background ring */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--c-surface-3)"
          strokeWidth={strokeWidth}
        />
        {/* Progress ring */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{
            transition: 'stroke-dashoffset 1s ease-out, stroke 0.3s ease',
            filter: loading ? 'none' : `drop-shadow(0 0 6px ${color})`,
          }}
        />
      </svg>
      {/* Center text */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {loading ? (
          <div
            className="skeleton-shimmer"
            style={{ width: 40, height: 24, borderRadius: 6 }}
          />
        ) : (
          <>
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontWeight: 900,
                fontSize: size * 0.22,
                color,
                lineHeight: 1,
              }}
            >
              {score}
            </div>
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontWeight: 700,
                fontSize: size * 0.075,
                color: 'var(--c-text-muted)',
                letterSpacing: '0.1em',
                marginTop: 2,
              }}
            >
              {bandLabel(score)}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
