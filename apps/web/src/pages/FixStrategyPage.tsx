import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { SemanticMarkdown } from '../components/SemanticMarkdown'
import { fetchInvestigation, executeSingleAction } from '../api/client'
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
  action_type?: string
  target_service?: string
  target_namespace?: string
  risk_level: string
  estimated_impact: string
  requires_approval: boolean
}

export default function FixStrategyPage() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['investigation', id],
    queryFn: () => fetchInvestigation(id!),
    enabled: !!id,
  })

  const fixStrategy = data?.fix_strategy
  const approvalStatus = data?.request?.approval_status ?? 'pending'
  const canExecute = approvalStatus === 'approved' || approvalStatus === 'executed'

  // Track per-action execution state: 'idle' | 'running' | 'success' | 'failed'
  const [actionStates, setActionStates] = useState<Record<number, 'idle' | 'running' | 'success' | 'failed'>>({})
  const [actionResults, setActionResults] = useState<Record<number, string>>({})
  const [actionLogs, setActionLogs] = useState<Record<number, string[]>>({})

  const executeMutation = useMutation({
    mutationFn: (actionIndex: number) => executeSingleAction(id!, actionIndex),
    onMutate: (actionIndex) => {
      setActionStates(prev => ({ ...prev, [actionIndex]: 'running' }))
    },
    onSuccess: (result, actionIndex) => {
      setActionStates(prev => ({ ...prev, [actionIndex]: result.success ? 'success' : 'failed' }))
      setActionResults(prev => ({ ...prev, [actionIndex]: result.detail }))
      setActionLogs(prev => ({ ...prev, [actionIndex]: result.logs ?? [] }))
      queryClient.invalidateQueries({ queryKey: ['investigation', id] })
    },
    onError: (err: Error, actionIndex) => {
      setActionStates(prev => ({ ...prev, [actionIndex]: 'failed' }))
      setActionResults(prev => ({ ...prev, [actionIndex]: err.message }))
    },
  })

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
                    padding: '3px 10px', borderRadius: 6,
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

                {/* Execution progress bar */}
                {Object.keys(actionStates).length > 0 && (
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    marginBottom: 12, padding: '10px 14px',
                    background: 'var(--c-surface-2)',
                    border: '1px solid var(--c-border-hi)',
                    borderRadius: 6,
                  }}>
                    <span style={{
                      fontFamily: 'var(--font-display)', fontSize: '0.7rem',
                      fontWeight: 700, color: 'var(--c-text-muted)',
                    }}>
                      Execution Progress
                    </span>
                    <div style={{ display: 'flex', gap: 6, flex: 1 }}>
                      {fixStrategy.actions.map((_: Action, idx: number) => {
                        const s = actionStates[idx] ?? 'idle'
                        const bg = s === 'success' ? 'var(--c-green)' : s === 'failed' ? 'var(--c-red)' : s === 'running' ? 'var(--c-signal)' : 'var(--c-border)'
                        return (
                          <div key={idx} style={{
                            flex: 1, height: 6, borderRadius: 3,
                            background: bg, transition: 'background 0.3s',
                            animation: s === 'running' ? 'shimmer 1.5s linear infinite' : undefined,
                          }} />
                        )
                      })}
                    </div>
                    <span style={{
                      fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
                      color: 'var(--c-text-dim)',
                    }}>
                      {Object.values(actionStates).filter(s => s === 'success').length}/{fixStrategy.actions.length}
                    </span>
                  </div>
                )}

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 16 }}>
                  {fixStrategy.actions.map((action: Action, i: number) => {
                    const riskColor = RISK_COLOR[action.risk_level] ?? 'var(--c-text-faint)'
                    const state = actionStates[i] ?? 'idle'
                    const stepBorderColor = state === 'success' ? 'var(--c-green)' : state === 'failed' ? 'var(--c-red)' : riskColor
                    return (
                      <div
                        key={i}
                        className="panel animate-fade-up scan-sweep"
                        style={{
                          overflow: 'hidden',
                          animationDelay: `${i * 60}ms`,
                          borderTop: `3px solid ${stepBorderColor}`,
                          opacity: state === 'success' ? 0.7 : 1,
                          transition: 'opacity 0.3s, border-color 0.3s',
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
                              borderRadius: 8,
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
                                {action.action_type && (
                                  <span style={{
                                    fontFamily: 'var(--font-mono)', fontSize: '0.58rem',
                                    padding: '2px 8px', borderRadius: 4,
                                    background: action.action_type.toLowerCase() === 'manual'
                                      ? 'color-mix(in srgb, #f59e0b 12%, transparent)'
                                      : 'color-mix(in srgb, var(--c-green) 12%, transparent)',
                                    border: `1px solid ${action.action_type.toLowerCase() === 'manual' ? '#f59e0b33' : 'var(--c-success-border)'}`,
                                    color: action.action_type.toLowerCase() === 'manual' ? '#f59e0b' : 'var(--c-green)',
                                  }}>
                                    {action.action_type.toLowerCase() === 'manual' ? '👤 Human action' : '⚡ Auto-executable'}
                                  </span>
                                )}
                                {action.requires_approval && (
                                  <span className="badge badge-pending">approval req</span>
                                )}
                                {action.target_service && (
                                  <span style={{
                                    fontFamily: 'var(--font-mono)', fontSize: '0.6rem',
                                    padding: '1px 7px', borderRadius: 4,
                                    background: 'color-mix(in srgb, var(--c-signal) 10%, transparent)',
                                    border: '1px solid var(--c-border)',
                                    color: 'var(--c-signal)',
                                  }}>
                                    → {action.target_namespace ? `${action.target_namespace}/` : ''}{action.target_service}
                                  </span>
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

                          {/* Per-action execute button */}
                          <div style={{
                            paddingTop: 12, marginTop: 12,
                            borderTop: '1px solid var(--c-border)',
                            display: 'flex', alignItems: 'center', gap: 10,
                          }}>
                            {state === 'idle' && canExecute && (
                              <button
                                onClick={() => executeMutation.mutate(i)}
                                style={{
                                  fontFamily: 'var(--font-display)', fontSize: '0.72rem', fontWeight: 700,
                                  padding: '6px 16px', borderRadius: 6, border: 'none', cursor: 'pointer',
                                  background: 'var(--c-signal)', color: '#fff',
                                  letterSpacing: '0.04em',
                                  transition: 'opacity 0.15s',
                                }}
                                onMouseOver={(e) => (e.currentTarget.style.opacity = '0.85')}
                                onMouseOut={(e) => (e.currentTarget.style.opacity = '1')}
                              >
                                ▶ Execute Step {i + 1}
                              </button>
                            )}
                            {state === 'idle' && !canExecute && (
                              <span style={{
                                fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
                                color: 'var(--c-text-faint)',
                              }}>
                                ⏳ Awaiting approval
                              </span>
                            )}
                            {state === 'running' && (
                              <span style={{
                                fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
                                color: 'var(--c-signal)', fontWeight: 600,
                              }}>
                                ⟳ Executing…
                              </span>
                            )}
                            {state === 'success' && (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                <span style={{
                                  fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
                                  color: 'var(--c-green)', fontWeight: 700,
                                }}>
                                  ✓ Executed
                                </span>
                                {actionResults[i] && (
                                  <span style={{
                                    fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
                                    color: 'var(--c-text-dim)',
                                  }}>
                                    {actionResults[i]}
                                  </span>
                                )}
                              </div>
                            )}
                            {state === 'failed' && (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                <span style={{
                                  fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
                                  color: 'var(--c-red)', fontWeight: 700,
                                }}>
                                  ✗ Failed
                                </span>
                                {actionResults[i] && (
                                  <span style={{
                                    fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
                                    color: 'var(--c-text-dim)',
                                  }}>
                                    {actionResults[i]}
                                  </span>
                                )}
                                <button
                                  onClick={() => executeMutation.mutate(i)}
                                  style={{
                                    fontFamily: 'var(--font-display)', fontSize: '0.68rem', fontWeight: 600,
                                    padding: '4px 12px', borderRadius: 5, border: '1px solid var(--c-red-border)',
                                    background: 'transparent', color: 'var(--c-red)', cursor: 'pointer',
                                    marginTop: 4, width: 'fit-content',
                                  }}
                                >
                                  ↻ Retry
                                </button>
                              </div>
                            )}
                          </div>

                          {/* Execution log terminal */}
                          {(actionLogs[i]?.length ?? 0) > 0 && (
                            <div style={{
                              marginTop: 12, padding: '10px 14px',
                              background: '#0d1117',
                              border: '1px solid var(--c-border)',
                              borderRadius: 6,
                              maxHeight: 160,
                              overflowY: 'auto',
                            }}>
                              <div style={{
                                fontFamily: 'var(--font-mono)', fontSize: '0.6rem',
                                fontWeight: 700, color: '#8b949e',
                                letterSpacing: '0.1em', textTransform: 'uppercase',
                                marginBottom: 6,
                              }}>
                                Execution Log
                              </div>
                              {actionLogs[i].map((line, li) => (
                                <div key={li} style={{
                                  fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
                                  color: line.includes('✓') ? '#3fb950' : line.includes('✗') ? '#f85149' : '#c9d1d9',
                                  lineHeight: 1.7,
                                  whiteSpace: 'pre-wrap',
                                  wordBreak: 'break-all',
                                }}>
                                  {line}
                                </div>
                              ))}
                            </div>
                          )}
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


