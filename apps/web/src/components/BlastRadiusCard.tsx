/**
 * BlastRadiusCard — V3.5
 *
 * Amber impact banner shown at the top of InvestigationDetailPage.
 * Lazy-fetches blast radius data from /investigations/{id}/blast-radius.
 */

import { useEffect, useState } from 'react'
import { fetchBlastRadius, type BlastRadiusEstimate } from '../api/client'

function deriveSeverity(blast: BlastRadiusEstimate): 'critical' | 'high' | 'medium' | 'low' {
  if (blast.estimated_users > 5000 || blast.revenue_risk_per_min > 300) return 'critical'
  if (blast.estimated_users > 2000 || blast.revenue_risk_per_min > 100) return 'high'
  if (blast.estimated_users > 500) return 'medium'
  return 'low'
}

const SEVERITY_COLOUR: Record<string, string> = {
  critical: 'var(--c-red)',
  high:     '#f59e0b',
  medium:   '#f59e0b',
  low:      'var(--c-green)',
}

const SEVERITY_BG: Record<string, string> = {
  critical: 'rgba(239,68,68,0.08)',
  high:     'rgba(245,158,11,0.08)',
  medium:   'rgba(245,158,11,0.06)',
  low:      'rgba(34,197,94,0.07)',
}

const SEVERITY_BORDER: Record<string, string> = {
  critical: 'rgba(239,68,68,0.35)',
  high:     'rgba(245,158,11,0.35)',
  medium:   'rgba(245,158,11,0.25)',
  low:      'rgba(34,197,94,0.25)',
}

interface Props {
  requestId: string
}

export function BlastRadiusCard({ requestId }: Props) {
  const [data, setData] = useState<BlastRadiusEstimate | null | undefined>(undefined) // undefined = loading

  useEffect(() => {
    fetchBlastRadius(requestId).then(d => setData(d))
  }, [requestId])

  // Loading skeleton
  if (data === undefined) {
    return (
      <div style={{
        height: 72, borderRadius: 6,
        background: 'var(--c-surface)',
        border: '1px solid var(--c-border)',
        marginBottom: 12,
        animation: 'pulse 1.5s ease-in-out infinite',
      }} />
    )
  }

  // No data or empty
  if (!data) return null

  const severity = deriveSeverity(data)
  const accentColour = SEVERITY_COLOUR[severity]

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 16,
      borderRadius: 6,
      border: `1px solid ${SEVERITY_BORDER[severity]}`,
      background: SEVERITY_BG[severity],
      padding: '12px 18px',
      marginBottom: 12,
    }}>
      {/* Left: icon + impact summary */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <span style={{ fontSize: '1.4rem', lineHeight: 1, marginTop: 2 }}>💥</span>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{
              fontFamily: 'var(--font-display)', fontWeight: 800,
              fontSize: '0.78rem', letterSpacing: '0.06em',
              color: 'var(--c-text)',
            }}>
              Blast Radius Estimate
            </span>
            <span style={{
              fontFamily: 'var(--font-display)', fontWeight: 700,
              fontSize: '0.54rem', letterSpacing: '0.14em', textTransform: 'uppercase',
              color: accentColour,
              padding: '2px 7px',
              border: `1px solid ${accentColour}44`,
              borderRadius: 2,
            }}>
              {severity}
            </span>
          </div>
          <p style={{
            margin: 0,
            fontFamily: 'var(--font-mono)', fontSize: '0.78rem',
            color: 'var(--c-text-dim)', lineHeight: 1.5,
          }}>
            <span style={{ color: 'var(--c-text)', fontWeight: 700 }}>~{data.estimated_users.toLocaleString()}</span> users
            {' · '}
            <span style={{ color: 'var(--c-text)', fontWeight: 700 }}>{data.affected_services.length}</span> service{data.affected_services.length !== 1 ? 's' : ''} affected
            {' · '}
            <span style={{ color: accentColour, fontWeight: 700 }}>
              {data.currency} {data.revenue_risk_per_min.toFixed(2)}
            </span>/min revenue risk
          </p>
          {data.affected_services.length > 1 && (
            <p style={{
              margin: '3px 0 0',
              fontFamily: 'var(--font-mono)', fontSize: '0.68rem',
              color: 'var(--c-text-faint)',
            }}>
              {data.affected_services.join(' · ')}
            </p>
          )}
        </div>
      </div>

      {/* Right: replica count + rationale */}
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        {data.replica_count > 0 && (
          <p style={{
            margin: '0 0 3px', fontFamily: 'var(--font-mono)',
            fontSize: '0.7rem', color: 'var(--c-text-muted)',
          }}>
            <span style={{ color: 'var(--c-text)', fontWeight: 700 }}>{data.replica_count}</span> pod{data.replica_count !== 1 ? 's' : ''} in AKS
          </p>
        )}
        <p style={{
          margin: 0, maxWidth: 220,
          fontFamily: 'var(--font-body)', fontSize: '0.68rem',
          color: 'var(--c-text-faint)', fontStyle: 'italic',
        }}>
          {data.rationale}
        </p>
      </div>
    </div>
  )
}
