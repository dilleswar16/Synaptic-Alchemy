/**
 * SimilarIncidentsSection — collapsible list of past incidents from incident memory.
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Section } from '../Section'
import type { SimilarIncident } from '../../api/client'

const CONF_CLS: Record<string, string> = {
  high: 'badge-approved', medium: 'badge-pending', low: 'badge-rejected',
}

export function SimilarIncidentsSection({ incidents }: { incidents: SimilarIncident[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  if (incidents.length === 0) return null

  return (
    <Section title={`Similar Past Incidents · ${incidents.length} found`} info="Previous Corvin investigations resolved for the same service and environment, surfaced to reveal recurring failure modes and reduce repeated diagnostic effort across your team.">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {incidents.map((inc) => {
          const date   = inc.completed_at.slice(0, 10)
          const time   = inc.completed_at.slice(11, 19)
          const isOpen = expandedId === inc.request_id

          return (
            <div
              key={inc.request_id}
              style={{
                background: 'var(--c-surface-2)',
                border: `1px solid ${isOpen ? 'var(--c-border-hi)' : 'var(--c-border)'}`,
                borderRadius: 6,
                overflow: 'hidden',
                transition: 'border-color 0.15s',
              }}
            >
              <button
                onClick={() => setExpandedId(isOpen ? null : inc.request_id)}
                style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: 10,
                  padding: '11px 14px', background: 'none', border: 'none',
                  cursor: 'pointer', textAlign: 'left',
                  borderBottom: isOpen ? '1px solid var(--c-border)' : 'none',
                }}
              >
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-text-muted)' }}>
                  {date} {time}Z
                </span>
                <span className={`badge ${CONF_CLS[inc.confidence] ?? 'badge-pending'}`}
                  style={{ fontSize: '0.65rem', padding: '1px 7px' }}>
                  {inc.confidence}
                </span>
                <span style={{
                  marginLeft: 'auto', fontFamily: 'var(--font-mono)',
                  fontSize: '0.65rem',
                  color: isOpen ? 'var(--c-signal)' : 'var(--c-text-muted)',
                  transition: 'color 0.15s',
                }}>
                  {isOpen ? '▲ hide' : '▼ expand'}
                </span>
              </button>

              {!isOpen && (
                <div style={{
                  padding: '0 14px 11px',
                  fontFamily: 'var(--font-body)', fontSize: '0.82rem',
                  color: 'var(--c-text-dim)', lineHeight: 1.5,
                  display: '-webkit-box', WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical', overflow: 'hidden',
                }}>
                  {inc.root_cause}
                </div>
              )}

              {isOpen && (
                <div style={{ padding: '14px' }}>
                  <div style={{
                    fontFamily: 'var(--font-display)', fontSize: '0.68rem', fontWeight: 700,
                    letterSpacing: '0.13em', textTransform: 'uppercase',
                    color: 'var(--c-text-muted)', marginBottom: 6,
                  }}>
                    Root Cause
                  </div>
                  <p style={{ margin: '0 0 14px', fontFamily: 'var(--font-body)', fontSize: '0.85rem', color: 'var(--c-text)', lineHeight: 1.7 }}>
                    {inc.root_cause}
                  </p>
                  <div style={{
                    fontFamily: 'var(--font-display)', fontSize: '0.68rem', fontWeight: 700,
                    letterSpacing: '0.13em', textTransform: 'uppercase',
                    color: 'var(--c-text-muted)', marginBottom: 6,
                  }}>
                    Summary
                  </div>
                  <p style={{ margin: '0 0 14px', fontFamily: 'var(--font-body)', fontSize: '0.83rem', color: 'var(--c-text-dim)', lineHeight: 1.65 }}>
                    {inc.rca_summary}
                  </p>
                  <Link
                    to={`/investigations/${inc.request_id}`}
                    style={{
                      fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.65rem',
                      letterSpacing: '0.1em', textTransform: 'uppercase',
                      color: 'var(--c-signal)', textDecoration: 'none',
                    }}
                  >
                    Full Investigation →
                  </Link>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </Section>
  )
}
