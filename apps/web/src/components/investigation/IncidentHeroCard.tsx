/**
 * IncidentHeroCard — permanent top-of-page summary for any investigation.
 *
 * Shows three things immediately, no scrolling required:
 *   WHAT BROKE   — service + environment + confidence
 *   WHY IT BROKE — one-line root cause
 *   WHAT TO DO   — top fix action title
 *
 * This is always visible, not a 3AM-mode feature. The detail sections below
 * exist for operators who want to dig deeper.
 */
import type { InvestigationResult } from '../../api/client'

const CONF_COLOUR: Record<string, string> = {
  high:   '#22c55e',
  medium: '#f59e0b',
  low:    '#ef4444',
}

interface Props {
  data: InvestigationResult
  approvalStatus: string
}

const STATUS_COLOUR: Record<string, string> = {
  pending:  '#f97316',
  approved: '#22c55e',
  rejected: '#ef4444',
  executed: '#60a5fa',
}

export function IncidentHeroCard({ data, approvalStatus }: Props) {
  const { rca, fix_strategy, request } = data
  if (!rca) return null

  const confColour   = CONF_COLOUR[rca.confidence]  ?? '#94a3b8'
  const statusColour = STATUS_COLOUR[approvalStatus] ?? '#94a3b8'
  const topAction    = fix_strategy?.actions?.[0]

  const confPct = rca.confidence === 'high' ? 85 : rca.confidence === 'medium' ? 52 : 20

  return (
    <div
      className="animate-fade-up"
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: 2,
        borderRadius: 14,
        overflow: 'hidden',
        border: '1.5px solid var(--c-border-hi)',
        marginBottom: 28,
        background: 'var(--c-surface)',
        boxShadow: '0 4px 32px rgba(0,0,0,0.28)',
      }}
    >
      {/* ── WHAT BROKE ── */}
      <div style={{
        padding: '22px 26px',
        background: `linear-gradient(160deg, color-mix(in srgb, #ef4444 10%, var(--c-surface)) 0%, var(--c-surface) 100%)`,
        borderRight: '1px solid var(--c-border)',
        display: 'flex', flexDirection: 'column', gap: 10,
      }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.65rem',
          letterSpacing: '0.22em', textTransform: 'uppercase', color: '#ef4444',
        }}>
          ① What Broke
        </div>
        <div style={{
          fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '1.55rem',
          letterSpacing: '0.04em', color: 'var(--c-text)', lineHeight: 1.1,
        }}>
          {request.service_name.toUpperCase()}
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.7rem', padding: '2px 9px',
            borderRadius: 999, background: 'rgba(249,115,22,0.1)',
            border: '1px solid rgba(249,115,22,0.25)', color: 'var(--c-signal)',
          }}>
            {request.environment}
          </span>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.7rem', padding: '2px 9px',
            borderRadius: 999, background: `color-mix(in srgb, ${statusColour} 12%, transparent)`,
            border: `1px solid color-mix(in srgb, ${statusColour} 30%, transparent)`,
            color: statusColour, textTransform: 'uppercase', letterSpacing: '0.06em',
          }}>
            {approvalStatus}
          </span>
        </div>
        {/* confidence mini-bar */}
        <div style={{ marginTop: 4 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>RCA Confidence</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: confColour, fontWeight: 700 }}>{rca.confidence.toUpperCase()}</span>
          </div>
          <div style={{ height: 4, background: 'var(--c-surface-2)', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{ width: `${confPct}%`, height: '100%', background: confColour, borderRadius: 2, transition: 'width 0.6s ease-out' }} />
          </div>
        </div>
      </div>

      {/* ── WHY IT BROKE ── */}
      <div style={{
        padding: '22px 26px',
        background: `linear-gradient(160deg, color-mix(in srgb, #f97316 8%, var(--c-surface)) 0%, var(--c-surface) 100%)`,
        borderRight: '1px solid var(--c-border)',
        display: 'flex', flexDirection: 'column', gap: 10,
      }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.65rem',
          letterSpacing: '0.22em', textTransform: 'uppercase', color: '#f97316',
        }}>
          ② Why It Broke
        </div>
        <div style={{
          fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: '0.95rem',
          color: 'var(--c-text)', lineHeight: 1.5, flexGrow: 1,
        }}>
          {rca.root_cause}
        </div>
        {rca.contributing_factors?.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 2 }}>
            {rca.contributing_factors.slice(0, 2).map((f, i) => (
              <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
                <span style={{ color: '#f97316', fontSize: '0.7rem', marginTop: 1, flexShrink: 0 }}>▸</span>
                <span style={{ fontFamily: 'var(--font-body)', fontSize: '0.78rem', color: 'var(--c-text-dim)', lineHeight: 1.45 }}>{f}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── WHAT TO DO ── */}
      <div style={{
        padding: '22px 26px',
        background: `linear-gradient(160deg, color-mix(in srgb, #22c55e 8%, var(--c-surface)) 0%, var(--c-surface) 100%)`,
        display: 'flex', flexDirection: 'column', gap: 10,
      }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.65rem',
          letterSpacing: '0.22em', textTransform: 'uppercase', color: '#22c55e',
        }}>
          ③ What To Do
        </div>
        {topAction ? (
          <>
            <div style={{
              fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: '0.95rem',
              color: 'var(--c-text)', lineHeight: 1.5,
            }}>
              {topAction.title}
            </div>
            {topAction.description && (
              <div style={{
                fontFamily: 'var(--font-body)', fontSize: '0.78rem',
                color: 'var(--c-text-dim)', lineHeight: 1.55,
              }}>
                {topAction.description.slice(0, 160)}{topAction.description.length > 160 ? '…' : ''}
              </div>
            )}
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 2 }}>
              {topAction.risk_level && (
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.68rem', padding: '2px 7px',
                  borderRadius: 999,
                  background: topAction.risk_level === 'high' ? 'rgba(239,68,68,0.12)' : topAction.risk_level === 'medium' ? 'rgba(249,115,22,0.12)' : 'rgba(34,197,94,0.12)',
                  border: `1px solid ${topAction.risk_level === 'high' ? 'rgba(239,68,68,0.3)' : topAction.risk_level === 'medium' ? 'rgba(249,115,22,0.3)' : 'rgba(34,197,94,0.3)'}`,
                  color: topAction.risk_level === 'high' ? '#ef4444' : topAction.risk_level === 'medium' ? '#f97316' : '#22c55e',
                  textTransform: 'uppercase', letterSpacing: '0.08em',
                }}>
                  {topAction.risk_level} risk
                </span>
              )}
              {topAction.requires_approval && (
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.68rem', padding: '2px 7px',
                  borderRadius: 999, background: 'rgba(139,92,246,0.1)',
                  border: '1px solid rgba(139,92,246,0.25)', color: '#a78bfa',
                  textTransform: 'uppercase', letterSpacing: '0.08em',
                }}>
                  Approval required
                </span>
              )}
            </div>
          </>
        ) : (
          <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.88rem', color: 'var(--c-text-muted)', fontStyle: 'italic' }}>
            No fix strategy generated yet.
          </div>
        )}
        {fix_strategy?.actions && fix_strategy.actions.length > 1 && (
          <div style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
            color: 'var(--c-text-faint)', marginTop: 4,
          }}>
            +{fix_strategy.actions.length - 1} more action{fix_strategy.actions.length > 2 ? 's' : ''} — see Fix Strategy below
          </div>
        )}
      </div>
    </div>
  )
}
