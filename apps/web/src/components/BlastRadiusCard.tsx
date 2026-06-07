/**
 * BlastRadiusCard — V3.5
 *
 * Shows which services share a failure domain with the incident.
 * Severity is derived from downstream service coupling count.
 */

import { useEffect, useState } from 'react'
import { fetchBlastRadius, type BlastRadiusEstimate } from '../api/client'
import { InfoTooltip } from './Section'

function deriveSeverity(blast: BlastRadiusEstimate): 'critical' | 'high' | 'medium' | 'low' {
  if (blast.affected_services.length >= 5) return 'critical'
  if (blast.affected_services.length >= 3) return 'high'
  if (blast.affected_services.length >= 2) return 'medium'
  return 'low'
}

const SEVERITY_COLOUR: Record<string, string> = {
  critical: 'var(--c-red)',
  high:     'var(--c-signal)',
  medium:   'var(--c-yellow)',
  low:      'var(--c-green)',
}

const SEVERITY_BG: Record<string, string> = {
  critical: 'var(--c-error-bg)',
  high:     'var(--c-signal-glow)',
  medium:   'var(--c-warning-bg)',
  low:      'var(--c-success-bg)',
}

const SEVERITY_BORDER: Record<string, string> = {
  critical: 'var(--c-error-border)',
  high:     'var(--c-border-glow)',
  medium:   'var(--c-warning-border)',
  low:      'var(--c-success-border)',
}

const INFO_TEXT =
  'Cross-references live Kubernetes pod topology and API gateway routing data to identify every service sharing a failure domain with this incident. Severity reflects downstream service coupling — the more services affected, the wider the blast radius.'

interface Props {
  requestId: string
}

export function BlastRadiusCard({ requestId }: Props) {
  const [data, setData] = useState<BlastRadiusEstimate | null | undefined>(undefined)

  useEffect(() => {
    fetchBlastRadius(requestId).then(d => setData(d))
  }, [requestId])

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

  if (!data) return null

  const severity = deriveSeverity(data)
  const accentColour = SEVERITY_COLOUR[severity]

  // Affected services excluding primary (shown separately)
  const downstream = data.affected_services.filter(s => s !== data.service_name)

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
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
        <div style={{
          position: 'relative', width: 34, height: 34, flexShrink: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center'
        }}>
          <div style={{
            position: 'absolute', inset: 0,
            borderRadius: '50%',
            background: accentColour,
            opacity: 0.15,
            animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite'
          }} />
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={accentColour} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ filter: `drop-shadow(0 0 4px color-mix(in srgb, ${accentColour} 60%, transparent))` }}>
            <circle cx="12" cy="12" r="10" />
            <circle cx="12" cy="12" r="6" />
            <circle cx="12" cy="12" r="2" />
            <line x1="12" y1="2" x2="12" y2="4" />
            <line x1="12" y1="20" x2="12" y2="22" />
            <line x1="2" y1="12" x2="4" y2="12" />
            <line x1="20" y1="12" x2="22" y2="12" />
          </svg>
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ fontWeight: 600, fontSize: '0.8125rem', color: 'var(--c-text)' }}>
              Blast Radius
            </span>
            <span style={{
              fontWeight: 500, fontSize: '0.6875rem', textTransform: 'uppercase',
              color: accentColour,
              padding: '2px 7px',
              border: `1px solid color-mix(in srgb, ${accentColour} 27%, transparent)`,
              borderRadius: 6,
            }}>
              {severity}
            </span>
            <InfoTooltip text={INFO_TEXT} />
          </div>
          <p style={{
            margin: 0,
            fontFamily: 'var(--font-mono)', fontSize: '0.78rem',
            color: 'var(--c-text-dim)', lineHeight: 1.5,
          }}>
            <span style={{ color: 'var(--c-text)', fontWeight: 700 }}>{data.affected_services.length}</span>
            {' '}service{data.affected_services.length !== 1 ? 's' : ''} in failure domain
            {data.replica_count > 0 && (
              <span style={{ color: 'var(--c-text-faint)' }}>
                {' · '}<span style={{ color: 'var(--c-text)', fontWeight: 700 }}>{data.replica_count}</span> pod{data.replica_count !== 1 ? 's' : ''} in AKS
              </span>
            )}
          </p>
          {data.affected_services.length > 0 && (
            <p style={{
              margin: '4px 0 0',
              fontFamily: 'var(--font-mono)', fontSize: '0.68rem',
              color: 'var(--c-text-faint)',
            }}>
              <span style={{ color: accentColour, fontWeight: 700 }}>{data.service_name}</span>
              {downstream.length > 0 && (
                <span> · {downstream.map((s, i) => (
                  <span key={s}>
                    {i > 0 && ' · '}
                    <span style={{ color: 'var(--c-text-dim)' }}>{s}</span>
                  </span>
                ))}</span>
              )}
            </p>
          )}
        </div>
      </div>

      {/* Right: rationale */}
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
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
