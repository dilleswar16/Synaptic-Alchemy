/**
 * ServiceHealthGauge — V3.5
 *
 * SVG arc gauge (220° sweep) showing the Corvin Score for a single service.
 * Color: green ≥ 80 | amber 50–79 | red < 50
 * Animated arc fill on mount. Click navigates to filtered investigations list.
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchServiceScore, type ServiceScore } from '../api/client'

const SIZE = 112
const STROKE = 10
const RADIUS = (SIZE - STROKE) / 2
const CENTER = SIZE / 2
const SWEEP_DEG = 220
const GAP_DEG = 360 - SWEEP_DEG

function scoreFraction(score: number) {
  return Math.max(0, Math.min(score, 100)) / 100
}

function buildArc(fraction: number): string {
  const totalRad = (SWEEP_DEG * Math.PI) / 180
  const startDeg = 90 + GAP_DEG / 2
  const startRad = (startDeg * Math.PI) / 180
  const endRad = startRad + totalRad * fraction

  const x1 = CENTER + RADIUS * Math.cos(startRad)
  const y1 = CENTER + RADIUS * Math.sin(startRad)
  const x2 = CENTER + RADIUS * Math.cos(endRad)
  const y2 = CENTER + RADIUS * Math.sin(endRad)

  const largeArc = fraction * SWEEP_DEG > 180 ? 1 : 0
  return `M ${x1} ${y1} A ${RADIUS} ${RADIUS} 0 ${largeArc} 1 ${x2} ${y2}`
}

const CIRCUMFERENCE = 2 * Math.PI * RADIUS
const ARC_LENGTH = (SWEEP_DEG / 360) * CIRCUMFERENCE

const COLOR_MAP: Record<string, string> = {
  green: 'var(--c-green)',
  amber: 'var(--c-signal)',
  red:   'var(--c-red)',
}

const BG_ARC = buildArc(1)

interface Props {
  serviceName: string
  environment?: string
}

export function ServiceHealthGauge({ serviceName, environment = 'dev' }: Props) {
  const navigate = useNavigate()
  const [data, setData] = useState<ServiceScore | null>(null)
  const [loading, setLoading] = useState(true)
  const [animatedScore, setAnimatedScore] = useState(0)

  useEffect(() => {
    setLoading(true)
    fetchServiceScore(serviceName, environment)
      .then(d => {
        setData(d)
        // Counter animation for the text number
        let start: number | null = null
        const target = d.score
        const step = (ts: number) => {
          if (!start) start = ts
          const elapsed = ts - start
          const progress = Math.min(elapsed / 1000, 1)
          const eased = 1 - Math.pow(1 - progress, 3)
          setAnimatedScore(Math.round(target * eased))
          if (progress < 1) requestAnimationFrame(step)
        }
        requestAnimationFrame(step)
      })
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [serviceName, environment])

  const colour = data ? (COLOR_MAP[data.color] ?? 'var(--c-signal)') : 'var(--c-text-faint)'
  
  // Wait a tiny bit after loading to trigger the CSS transition
  const fraction = data && !loading ? scoreFraction(data.score) : 0
  const dashOffset = ARC_LENGTH * (1 - fraction)

  return (
    <button
      onClick={() => navigate(`/investigations?filter=${encodeURIComponent(serviceName)}`)}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 6,
        padding: '8px 10px',
        borderRadius: 8,
        background: 'var(--c-surface-2)',
        border: '1px solid var(--c-border)',
        cursor: 'pointer',
        transition: 'border-color 0.2s',
        outline: 'none',
      }}
      title={`View investigations for ${serviceName}`}
    >
      {/* SVG Gauge */}
      <div style={{ position: 'relative', width: SIZE, height: SIZE }}>
        <svg width={SIZE} height={SIZE} style={{ overflow: 'visible' }}>
          <path
            d={BG_ARC}
            fill="none"
            stroke="rgba(148,163,184,0.12)"
            strokeWidth={STROKE}
            strokeLinecap="round"
          />
          <path
            d={BG_ARC}
            fill="none"
            stroke={colour}
            strokeWidth={STROKE}
            strokeLinecap="round"
            strokeDasharray={ARC_LENGTH}
            strokeDashoffset={dashOffset}
            style={{ 
              filter: `drop-shadow(0 0 6px color-mix(in srgb, ${colour} 60%, transparent))`,
              transition: 'stroke-dashoffset 1s cubic-bezier(0.34, 1.56, 0.64, 1), stroke 0.3s ease'
            }}
          />
        </svg>
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
        }}>
          {loading ? (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--c-text-faint)' }}>…</span>
          ) : (
            <>
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: '1.5rem',
                fontWeight: 700, lineHeight: 1, color: colour,
                letterSpacing: '-0.02em',
                textShadow: `0 0 10px color-mix(in srgb, ${colour} 40%, transparent)`
              }}>
                {data ? animatedScore : '—'}
              </span>
              <span style={{
                fontFamily: 'var(--font-display)', fontSize: '0.58rem',
                fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase',
                color: 'var(--c-text-muted)', marginTop: 3,
              }}>
                {data?.label ?? 'No data'}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Service name */}
      <div style={{ textAlign: 'center' }}>
        <p style={{
          margin: 0, fontFamily: 'var(--font-display)', fontWeight: 700,
          fontSize: '0.75rem', color: 'var(--c-text)', letterSpacing: '0.04em',
          maxWidth: 110, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {serviceName}
        </p>
        {data && data.total > 0 && (
          <p style={{
            margin: '2px 0 0', fontFamily: 'var(--font-mono)',
            fontSize: '0.58rem', color: 'var(--c-text-faint)',
          }}>
            {data.total} incident{data.total !== 1 ? 's' : ''}
            {data.avg_mttr_minutes != null ? ` · ${Math.round(data.avg_mttr_minutes)}m MTTR` : ''}
          </p>
        )}
        {data && data.total === 0 && (
          <p style={{ margin: '2px 0 0', fontFamily: 'var(--font-mono)', fontSize: '0.58rem', color: 'var(--c-text-faint)' }}>
            No incidents
          </p>
        )}
      </div>
    </button>
  )
}
