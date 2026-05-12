/**
 * ServiceHealthGauge — V3.5
 *
 * SVG arc gauge (220° sweep) showing the Corvin Score for a single service.
 * Color: green ≥ 80 | amber 50–79 | red < 50
 * Animated arc fill on mount. Click navigates to filtered investigations list.
 */

import { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchServiceScore, type ServiceScore } from '../api/client'

const SIZE = 140
const STROKE = 11
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

const COLOR_MAP: Record<string, string> = {
  green: '#22c55e',
  amber: '#f59e0b',
  red:   '#ef4444',
}

const BG_ARC = buildArc(1)

interface Props {
  serviceName: string
  environment?: string
}

export function ServiceHealthGauge({ serviceName, environment = 'dev' }: Props) {
  const navigate = useNavigate()
  const [data, setData] = useState<ServiceScore | null>(null)
  const [displayed, setDisplayed] = useState(0)
  const [loading, setLoading] = useState(true)
  const animRef = useRef<number | null>(null)

  useEffect(() => {
    setLoading(true)
    fetchServiceScore(serviceName, environment)
      .then(d => {
        setData(d)
        let start: number | null = null
        const target = d.score
        const step = (ts: number) => {
          if (!start) start = ts
          const elapsed = ts - start
          const progress = Math.min(elapsed / 900, 1)
          const eased = 1 - Math.pow(1 - progress, 3)
          setDisplayed(Math.round(target * eased))
          if (progress < 1) {
            animRef.current = requestAnimationFrame(step)
          }
        }
        animRef.current = requestAnimationFrame(step)
      })
      .catch(() => setData(null))
      .finally(() => setLoading(false))
    return () => { if (animRef.current) cancelAnimationFrame(animRef.current) }
  }, [serviceName, environment])

  const colour = data ? (COLOR_MAP[data.color] ?? '#f59e0b') : 'var(--c-text-faint)'
  const fraction = data ? scoreFraction(displayed) : 0
  const arcPath = buildArc(fraction)

  return (
    <button
      onClick={() => navigate(`/investigations?filter=${encodeURIComponent(serviceName)}`)}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 6,
        padding: '10px 12px',
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
            d={arcPath}
            fill="none"
            stroke={colour}
            strokeWidth={STROKE}
            strokeLinecap="round"
            style={{ filter: `drop-shadow(0 0 5px ${colour}88)` }}
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
                fontFamily: 'var(--font-mono)', fontSize: '1.9rem',
                fontWeight: 700, lineHeight: 1, color: colour,
                letterSpacing: '-0.02em',
              }}>
                {data ? displayed : '—'}
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
