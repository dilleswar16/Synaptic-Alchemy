/**
 * RcaSection — Root Cause Analysis panel with confidence meter,
 * root cause card, analysis summary, contributing factors, and fix strategy preview.
 */
import { Link } from 'react-router-dom'
import { Section } from '../Section'
import type { InvestigationResult } from '../../api/client'

interface RcaSectionProps {
  data: InvestigationResult
  requestId: string
}

export function RcaSection({ data, requestId }: RcaSectionProps) {
  const { rca, fix_strategy } = data

  if (!rca) return null

  const confColor = rca.confidence === 'high' ? 'var(--c-green)'
    : rca.confidence === 'low' ? 'var(--c-red)'
    : 'var(--c-yellow)'

  const confWidth = rca.confidence === 'high' ? '85%'
    : rca.confidence === 'medium' ? '52%'
    : '20%'

  const confClass = rca.confidence === 'high' ? 'badge-approved'
    : rca.confidence === 'low' ? 'badge-rejected'
    : 'badge-pending'

  return (
    <Section title="Root Cause Analysis">
      {/* Confidence bar */}
      <div style={{ marginBottom: 22 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: rca.confidence_reasoning ? 10 : 0 }}>
          <span className={`badge ${confClass}`}>{rca.confidence} confidence</span>
          <div style={{ flex: 1, height: 3, background: 'var(--c-surface-3)', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{
              height: '100%', width: confWidth,
              background: confColor, borderRadius: 2,
              transition: 'width 0.8s ease',
            }} />
          </div>
        </div>
        {rca.confidence_reasoning && (
          <p style={{
            margin: 0,
            fontSize: '0.78rem',
            color: 'var(--c-text-faint)',
            lineHeight: 1.6,
            fontStyle: 'italic',
            paddingLeft: 2,
          }}>
            {rca.confidence_reasoning}
          </p>
        )}
      </div>

      {/* Root cause highlighted card */}
      <div style={{
        borderLeft: '3px solid var(--c-red)',
        padding: '14px 18px',
        background: 'rgba(239,68,68,0.04)',
        marginBottom: 20, borderRadius: '0 3px 3px 0',
      }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontSize: '0.6rem', fontWeight: 700,
          letterSpacing: '0.14em', textTransform: 'uppercase',
          color: 'var(--c-red)', marginBottom: 8,
        }}>
          Root Cause
        </div>
        <p style={{ margin: 0, fontFamily: 'var(--font-body)', fontSize: '0.9rem', color: 'var(--c-text)', lineHeight: 1.75 }}>
          {rca.root_cause}
        </p>
      </div>

      {/* Analysis summary */}
      <div style={{ marginBottom: 20 }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontSize: '0.6rem', fontWeight: 700,
          letterSpacing: '0.14em', textTransform: 'uppercase',
          color: 'var(--c-text-muted)', marginBottom: 10,
        }}>
          Analysis
        </div>
        <p style={{ margin: 0, fontFamily: 'var(--font-body)', fontSize: '0.88rem', color: 'var(--c-text-dim)', lineHeight: 1.75 }}>
          {rca.summary}
        </p>
      </div>

      {/* Contributing factors */}
      {rca.contributing_factors?.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <div style={{
            fontFamily: 'var(--font-display)', fontSize: '0.6rem', fontWeight: 700,
            letterSpacing: '0.14em', textTransform: 'uppercase',
            color: 'var(--c-text-muted)', marginBottom: 10,
          }}>
            Contributing Factors ({rca.contributing_factors.length})
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {rca.contributing_factors.map((f: string, i: number) => {
              const fl = f.toLowerCase()
              const chipLabel = (fl.includes('no ') || fl.includes('not ') || fl.includes('healthy') || fl.includes('no issue'))
                ? 'no issue'
                : (fl.includes('pod') || fl.includes('node') || fl.includes('cluster') || fl.includes('aks') || fl.includes('memory') || fl.includes('cpu') || fl.includes('network') || fl.includes('disk'))
                ? 'infra'
                : (fl.includes('deploy') || fl.includes('config') || fl.includes('change') || fl.includes('release'))
                ? 'change'
                : 'app'

              const chipColor = chipLabel === 'no issue' ? 'var(--c-text-faint)'
                : chipLabel === 'infra' ? 'var(--c-yellow)'
                : chipLabel === 'change' ? 'var(--c-signal)'
                : 'var(--c-text-muted)'

              return (
                <div key={i} style={{
                  display: 'flex', alignItems: 'flex-start', gap: 12,
                  padding: '10px 14px',
                  background: 'rgba(249,115,22,0.04)',
                  border: '1px solid rgba(249,115,22,0.1)',
                  borderRadius: 2,
                }}>
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.62rem',
                    color: 'var(--c-signal)', marginTop: 2, flexShrink: 0, fontWeight: 700,
                  }}>
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span style={{
                    fontFamily: 'var(--font-body)', fontSize: '0.85rem',
                    color: 'var(--c-text-dim)', lineHeight: 1.6, flex: 1,
                  }}>
                    {f}
                  </span>
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.57rem',
                    fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase',
                    padding: '2px 6px', borderRadius: 2, flexShrink: 0, marginTop: 2,
                    background: `${chipColor}18`,
                    border: `1px solid ${chipColor}35`,
                    color: chipColor,
                  }}>
                    {chipLabel}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Evidence references — what the model used to reach its conclusion */}
      {rca.evidence_references?.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <div style={{
            fontFamily: 'var(--font-display)', fontSize: '0.6rem', fontWeight: 700,
            letterSpacing: '0.14em', textTransform: 'uppercase',
            color: 'var(--c-text-muted)', marginBottom: 10,
            display: 'flex', alignItems: 'center', gap: 10,
          }}>
            Evidence References
            <span style={{
              fontFamily: 'var(--font-mono)', fontWeight: 400, fontSize: '0.6rem',
              color: 'var(--c-text-faint)', textTransform: 'none', letterSpacing: 0,
            }}>what the model saw</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {rca.evidence_references.map((ref: string, i: number) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'flex-start', gap: 10,
                padding: '8px 14px',
                borderLeft: '2px solid rgba(249,115,22,0.35)',
                background: 'rgba(249,115,22,0.025)',
                borderRadius: '0 3px 3px 0',
              }}>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.6rem',
                  color: 'rgba(249,115,22,0.45)', marginTop: 4, flexShrink: 0,
                }}>
                  ↳
                </span>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.78rem',
                  color: 'var(--c-text-dim)', lineHeight: 1.6,
                }}>
                  {ref}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Fix strategy preview (inline at bottom of RCA) */}
      <div style={{ paddingTop: 16, borderTop: '1px solid var(--c-border)' }}>
        {fix_strategy && fix_strategy.actions?.length > 0 ? (
          <div style={{
            display: 'flex', alignItems: 'flex-start', gap: 14,
            padding: '12px 14px',
            background: 'var(--c-surface-2)',
            border: '1px solid var(--c-border)',
            borderRadius: 3,
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontFamily: 'var(--font-display)', fontSize: '0.62rem', fontWeight: 700,
                letterSpacing: '0.14em', textTransform: 'uppercase',
                color: 'var(--c-text-muted)', marginBottom: 6,
              }}>
                Fix Strategy · {fix_strategy.actions.length} action{fix_strategy.actions.length !== 1 ? 's' : ''}
              </div>
              <p style={{ margin: 0, fontFamily: 'var(--font-body)', fontSize: '0.82rem', color: 'var(--c-text-dim)', lineHeight: 1.6 }}>
                {fix_strategy.summary}
              </p>
            </div>
            <Link
              to={`/investigations/${requestId}/fix-strategy`}
              style={{
                flexShrink: 0,
                fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.62rem',
                letterSpacing: '0.1em', textTransform: 'uppercase',
                color: 'var(--c-signal)', textDecoration: 'none',
                padding: '6px 12px', borderRadius: 2,
                border: '1px solid rgba(249,115,22,0.3)',
                background: 'rgba(249,115,22,0.06)',
                whiteSpace: 'nowrap',
              }}
            >
              View →
            </Link>
          </div>
        ) : (
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-text-faint)',
          }}>
            Fix strategy not yet available.
          </div>
        )}
      </div>
    </Section>
  )
}
