import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { SemanticMarkdown } from '../components/SemanticMarkdown'
import { fetchInvestigation } from '../api/client'
import Layout from '../components/Layout'
import { RemediationPreviewPanel } from '../components/RemediationPreviewPanel'
import { FixStrategyFlowchart } from '../components/investigation/FixStrategyFlowchart'

const RISK_CLS: Record<string, string> = {
  high:   'badge-rejected',
  medium: 'badge-pending',
  low:    'badge-approved',
}

const RISK_COLOR: Record<string, string> = {
  high:   'var(--c-red)',
  medium: 'var(--c-yellow)',
  low:    'var(--c-green)',
}

interface Action {
  title: string
  description: string
  risk_level: string
  estimated_impact: string
  requires_approval: boolean
}

export default function FixStrategyPage() {
  const { id } = useParams<{ id: string }>()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['investigation', id],
    queryFn: () => fetchInvestigation(id!),
    enabled: !!id,
  })

  const fixStrategy = data?.fix_strategy

  return (
    <Layout>
      <div style={{ maxWidth: 860 }}>

        {/* ── Header ───────────────────────────────────────────────────────── */}
        <div className="animate-fade-up" style={{ marginBottom: 28 }}>
          <Link to={`/investigations/${id}`} style={{
            fontFamily: 'var(--font-display)', fontSize: '0.8125rem', fontWeight: 500,
            color: 'var(--c-text-muted)', textDecoration: 'none',
          }}>
            ← Investigation
          </Link>
          <div style={{ marginTop: 14 }}>
            <div style={{
              fontSize: '0.75rem', fontWeight: 500,
              letterSpacing: '0.03em', textTransform: 'uppercase',
              color: 'var(--c-signal)', marginBottom: 4,
            }}>
              Fix Strategy
            </div>
            <h1 style={{
              margin: '0 0 14px',
              fontFamily: 'var(--font-display)', fontWeight: 700,
              fontSize: '1.75rem', letterSpacing: '-0.02em',
              color: 'var(--c-text)', lineHeight: 1.2,
            }}>
              {data?.request?.service_name ?? (isLoading ? '…' : 'Fix Strategy')}
            </h1>
            {data && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                {data.request?.environment && (
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.75rem',
                    padding: '3px 10px', borderRadius: 6,
                    background: 'var(--c-signal-glow)', border: '1px solid var(--c-border-glow)',
                    color: 'var(--c-signal)',
                  }}>
                    {data.request.environment}
                  </span>
                )}
                {(fixStrategy?.actions?.length ?? 0) > 0 && (
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
                    padding: '3px 10px', borderRadius: 2,
                    background: 'var(--c-surface-2)', border: '1px solid var(--c-border-hi)',
                    color: 'var(--c-text-dim)', letterSpacing: '0.04em',
                  }}>
                    {fixStrategy?.actions?.length ?? 0} action{(fixStrategy?.actions?.length ?? 0) !== 1 ? 's' : ''}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>

        {/* ── States ───────────────────────────────────────────────────────── */}
        {isLoading && (
          <div style={{
            padding: '32px 0',
            display: 'flex', flexDirection: 'column', gap: 16,
          }}>
            {/* Skeleton: action cards */}
            {[1, 2, 3].map(i => (
              <div key={i} style={{
                background: 'var(--c-surface)',
                border: '1px solid var(--c-border)',
                borderRadius: 8,
                padding: '20px 24px',
                animation: 'shimmer 1.8s linear infinite',
                backgroundImage: 'linear-gradient(90deg, var(--c-surface) 0%, var(--c-surface-2) 45%, var(--c-surface) 100%)',
                backgroundSize: '600px 100%',
              }}>
                <div style={{ height: 14, width: `${55 + i * 10}%`, background: 'var(--c-border-hi)', borderRadius: 3, marginBottom: 12 }} />
                <div style={{ height: 10, width: '80%', background: 'var(--c-border)', borderRadius: 3, marginBottom: 8 }} />
                <div style={{ height: 10, width: '60%', background: 'var(--c-border)', borderRadius: 3 }} />
              </div>
            ))}
          </div>
        )}
        {isError && (
          <div style={{
            padding: '20px 24px',
            background: 'var(--c-surface)',
            border: '1px solid var(--c-red-border)',
            borderLeft: '3px solid var(--c-red)',
            borderRadius: 4,
            fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--c-red)',
          }}>
            ✗ Could not load fix strategy.
          </div>
        )}
        {data && !fixStrategy && (
          <div style={{
            padding: '48px 24px', textAlign: 'center',
            background: 'var(--c-surface)',
            border: '1px solid var(--c-border-hi)',
            borderRadius: 4,
          }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.4rem', color: 'var(--c-text-faint)', marginBottom: 12 }}>—</div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.82rem', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--c-text-muted)', marginBottom: 6 }}>No Fix Strategy Yet</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--c-text-faint)' }}>
              The investigation must complete before a fix strategy is generated.
            </div>
          </div>
        )}

        {/* ── Content ──────────────────────────────────────────────────────── */}
        {fixStrategy && (
          <div className="animate-fade-up-1" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

            <FixStrategyFlowchart serviceName={data.request?.service_name ?? 'service'} actions={fixStrategy.actions} />

            <RemediationPreviewPanel requestId={id!} />

            {/* Summary + Justification layout */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.6fr', gap: 16 }}>
              <div className="panel" style={{ padding: '24px 28px' }}>
                <div style={{
                  fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 800,
                  letterSpacing: '0.14em', textTransform: 'uppercase',
                  color: 'var(--c-signal)', marginBottom: 12,
                }}>
                  Summary
                </div>
                <div className="pm-prose" style={{ color: 'var(--c-text)' }}>
                  <SemanticMarkdown>{fixStrategy.summary}</SemanticMarkdown>
                </div>
              </div>
              <div className="panel" style={{ padding: '24px 28px', background: 'var(--c-surface-2)' }}>
                <div style={{
                  fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 800,
                  letterSpacing: '0.14em', textTransform: 'uppercase',
                  color: 'var(--c-text-muted)', marginBottom: 12,
                }}>
                  Justification
                </div>
                <div className="pm-prose" style={{ color: 'var(--c-text-dim)' }}>
                  <SemanticMarkdown>{fixStrategy.justification}</SemanticMarkdown>
                </div>
              </div>
            </div>

            {/* Actions */}
            {fixStrategy.actions?.length > 0 && (
              <div>
                {/* Section divider */}
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  marginBottom: 12, marginTop: 4,
                }}>
                  <span style={{
                    fontFamily: 'var(--font-display)', fontSize: '0.7rem', fontWeight: 700,
                    letterSpacing: '0.16em', textTransform: 'uppercase',
                    color: 'var(--c-text-muted)', flexShrink: 0,
                  }}>
                    Recommended Actions
                  </span>
                  <div style={{ flex: 1, height: 1, background: 'var(--c-border-hi)' }} />
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
                    color: 'var(--c-text-faint)', flexShrink: 0,
                  }}>
                    {fixStrategy.actions.length}
                  </span>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 16 }}>
                  {fixStrategy.actions.map((action: Action, i: number) => {
                    const riskColor = RISK_COLOR[action.risk_level] ?? 'var(--c-text-faint)'
                    return (
                      <div
                        key={i}
                        className="panel animate-fade-up scan-sweep"
                        style={{
                          overflow: 'hidden',
                          animationDelay: `${i * 60}ms`,
                          borderTop: `3px solid ${riskColor}`,
                        }}
                      >
                        <div style={{ padding: '16px 20px' }}>
                          {/* Title row */}
                          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, marginBottom: 14 }}>
                            {/* Step number circle with risk color */}
                            <div style={{
                              flexShrink: 0, width: 34, height: 34,
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              fontFamily: 'var(--font-mono)', fontWeight: 700,
                              fontSize: '0.75rem', color: riskColor,
                              background: `color-mix(in srgb, ${riskColor} 10%, transparent)`,
                              border: `1px solid color-mix(in srgb, ${riskColor} 30%, transparent)`,
                              borderRadius: 2,
                            }}>
                              {String(i + 1).padStart(2, '0')}
                            </div>
                            <div style={{ flex: 1 }}>
                              <div style={{
                                display: 'flex', alignItems: 'center',
                                gap: 8, flexWrap: 'wrap', marginBottom: 8,
                              }}>
                                <span style={{
                                  fontFamily: 'var(--font-display)', fontWeight: 800,
                                  fontSize: '0.95rem', color: 'var(--c-text)',
                                  letterSpacing: '0.02em',
                                }}>
                                  {action.title}
                                </span>
                                <span className={`badge ${RISK_CLS[action.risk_level] ?? 'badge-pending'}`}>
                                  {action.risk_level} risk
                                </span>
                                {action.requires_approval && (
                                  <span className="badge badge-pending">approval req</span>
                                )}
                              </div>
                              <div className="pm-prose" style={{ color: 'var(--c-text-dim)' }}>
                                <SemanticMarkdown>{action.description}</SemanticMarkdown>
                              </div>
                            </div>
                          </div>

                          {/* Impact footer */}
                          <div style={{
                            display: 'flex', alignItems: 'center', gap: 10,
                            paddingTop: 12,
                            borderTop: '1px solid var(--c-border)',
                          }}>
                            <span style={{
                              fontFamily: 'var(--font-display)', fontSize: '0.68rem', fontWeight: 700,
                              letterSpacing: '0.12em', textTransform: 'uppercase',
                              color: 'var(--c-text-muted)', flexShrink: 0,
                            }}>
                              Estimated Impact
                            </span>
                            <span style={{
                              fontFamily: 'var(--font-mono)', fontSize: '0.75rem',
                              color: 'var(--c-text-dim)',
                            }}>
                              {action.estimated_impact}
                            </span>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </Layout>
  )
}


