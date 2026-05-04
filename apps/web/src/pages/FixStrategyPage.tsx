import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { fetchInvestigation } from '../api/client'
import Layout from '../components/Layout'

const RISK_CLS: Record<string, string> = {
  high:   'badge-rejected',
  medium: 'badge-pending',
  low:    'badge-approved',
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
        {/* Back + title */}
        <div className="animate-fade-up" style={{ marginBottom: 24 }}>
          <Link to={`/investigations/${id}`} style={{
            fontFamily: 'var(--font-display)', fontSize: '0.7rem', fontWeight: 700,
            letterSpacing: '0.1em', textTransform: 'uppercase',
            color: 'var(--c-text-muted)', textDecoration: 'none',
          }}>
            ← Investigation
          </Link>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginTop: 12 }}>
            <h1 style={{ margin: 0, fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '1.8rem', letterSpacing: '0.04em', color: 'var(--c-text)' }}>
              FIX STRATEGY
            </h1>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-text-faint)' }}>
              #{id?.substring(0, 8)}…
            </span>
          </div>
        </div>

        {isLoading && (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--c-text-faint)' }}>Loading…</div>
        )}
        {isError && (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--c-red)' }}>✗ Could not load fix strategy.</div>
        )}
        {data && !fixStrategy && (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--c-text-faint)' }}>
            Fix strategy not yet available for this investigation.
          </div>
        )}

        {fixStrategy && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {/* Summary */}
            <div className="panel animate-fade-up" style={{ padding: '16px 20px' }}>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: '0.62rem', fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--c-text-muted)', marginBottom: 10 }}>
                Summary
              </div>
              <p style={{ margin: 0, fontFamily: 'var(--font-body)', fontSize: '0.88rem', color: 'var(--c-text-dim)', lineHeight: 1.7 }}>
                {fixStrategy.summary}
              </p>
            </div>

            {/* Justification */}
            <div className="panel animate-fade-up-1" style={{ padding: '16px 20px' }}>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: '0.62rem', fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--c-text-muted)', marginBottom: 10 }}>
                Justification
              </div>
              <p style={{ margin: 0, fontFamily: 'var(--font-body)', fontSize: '0.88rem', color: 'var(--c-text-dim)', lineHeight: 1.7 }}>
                {fixStrategy.justification}
              </p>
            </div>

            {/* Actions */}
            {fixStrategy.actions?.length > 0 && (
              <div>
                <div style={{
                  fontFamily: 'var(--font-display)', fontSize: '0.62rem', fontWeight: 700,
                  letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--c-text-muted)',
                  marginBottom: 12,
                }}>
                  Recommended Actions ({fixStrategy.actions.length})
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {fixStrategy.actions.map((action: Action, i: number) => (
                    <div
                      key={i}
                      className="panel-signal animate-fade-up scan-sweep"
                      style={{ padding: '16px 20px', animationDelay: `${i * 50}ms`, overflow: 'hidden' }}
                    >
                      {/* Header row */}
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, marginBottom: 10 }}>
                        {/* Step number */}
                        <div style={{
                          flexShrink: 0, width: 28, height: 28,
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          background: 'rgba(249,115,22,0.12)', border: '1px solid rgba(249,115,22,0.25)',
                          borderRadius: 2,
                          fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.7rem', color: 'var(--c-signal)',
                        }}>
                          {String(i + 1).padStart(2, '0')}
                        </div>
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
                            <span style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.92rem', color: 'var(--c-text)', letterSpacing: '0.02em' }}>
                              {action.title}
                            </span>
                            <span className={`badge ${RISK_CLS[action.risk_level] ?? 'badge-pending'}`}>
                              {action.risk_level} risk
                            </span>
                            {action.requires_approval && (
                              <span className="badge badge-pending">approval req</span>
                            )}
                          </div>
                          <p style={{ margin: 0, fontFamily: 'var(--font-body)', fontSize: '0.83rem', color: 'var(--c-text-dim)', lineHeight: 1.65 }}>
                            {action.description}
                          </p>
                        </div>
                      </div>
                      {/* Impact */}
                      <div style={{ paddingLeft: 42, display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontFamily: 'var(--font-display)', fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--c-text-muted)' }}>
                          Impact
                        </span>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-text-dim)' }}>
                          {action.estimated_impact}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </Layout>
  )
}


