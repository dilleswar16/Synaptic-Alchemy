import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { SemanticMarkdown } from '../components/SemanticMarkdown'
import { fetchInvestigation, executeSingleAction, createGithubIssue } from '../api/client'
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

  const [githubError, setGithubError] = useState<string | null>(null)
  const [agentNote, setAgentNote] = useState<string | null>(null)
  const githubMutation = useMutation({
    mutationFn: () => createGithubIssue(id!),
    onSuccess: (result) => {
      setGithubError(null)
      setAgentNote(result.agent_note ?? null)
      queryClient.invalidateQueries({ queryKey: ['investigation', id] })
    },
    onError: (err: Error) => setGithubError(err.message),
  })

  const existingIssueUrl = data?.fix_strategy?.github_issue_url
  const existingIssueNumber = data?.fix_strategy?.github_issue_number

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

                {/* ── GitHub Issue button / badge ── */}
                {fixStrategy && (
                  existingIssueUrl ? (
                    <a
                      href={existingIssueUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: 6,
                        fontFamily: 'var(--font-mono)', fontSize: '0.7rem', fontWeight: 700,
                        padding: '4px 12px', borderRadius: 6,
                        background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)',
                        color: 'var(--c-green)', textDecoration: 'none',
                      }}
                    >
                      <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
                      </svg>
                      #{existingIssueNumber} on GitHub
                    </a>
                  ) : (
                    <button
                      onClick={() => githubMutation.mutate()}
                      disabled={githubMutation.isPending}
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: 6,
                        fontFamily: 'var(--font-body)', fontSize: '0.78rem', fontWeight: 600,
                        padding: '5px 14px', borderRadius: 6, cursor: githubMutation.isPending ? 'not-allowed' : 'pointer',
                        background: githubMutation.isPending ? 'var(--c-surface-3)' : 'var(--c-surface-2)',
                        border: '1px solid var(--c-border-hi)',
                        color: githubMutation.isPending ? 'var(--c-text-faint)' : 'var(--c-text)',
                        transition: 'all 0.15s',
                      }}
                    >
                      <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
                      </svg>
                      {githubMutation.isPending ? 'Creating issue…' : 'Create GitHub Issue'}
                    </button>
                  )
                )}
              </div>
            )}
            {githubError && (
              <div style={{
                marginTop: 10, padding: '8px 12px',
                background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)',
                borderRadius: 6, fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: 'var(--c-red)',
              }}>
                {githubError}
              </div>
            )}
            {agentNote && (
              <div style={{
                marginTop: 10, padding: '10px 14px',
                background: 'rgba(59,130,246,0.07)', border: '1px solid rgba(59,130,246,0.25)',
                borderRadius: 6, fontSize: '0.78rem', lineHeight: 1.5, color: 'var(--c-text-muted)',
              }}>
                <span style={{ fontWeight: 600, color: 'var(--c-text)' }}>Next step — assign to ChAD Agency:</span>{' '}
                {agentNote}
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
                <details>
                  <summary style={{
                    fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 800,
                    letterSpacing: '0.14em', textTransform: 'uppercase', cursor: 'pointer',
                    color: 'var(--c-signal)', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    listStyle: 'none'
                  }}>
                    <span>Summary</span>
                    <span style={{ fontSize: '0.6rem', color: 'var(--c-text-muted)' }}>▼ Read</span>
                  </summary>
                  <div className="pm-prose" style={{ color: 'var(--c-text)', marginTop: 12 }}>
                    <SemanticMarkdown>{fixStrategy.summary}</SemanticMarkdown>
                  </div>
                </details>
              </div>
              <div className="panel" style={{ padding: '24px 28px', background: 'var(--c-surface-2)' }}>
                <details>
                  <summary style={{
                    fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 800,
                    letterSpacing: '0.14em', textTransform: 'uppercase', cursor: 'pointer',
                    color: 'var(--c-text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    listStyle: 'none'
                  }}>
                    <span>Justification</span>
                    <span style={{ fontSize: '0.6rem' }}>▼ Read</span>
                  </summary>
                  <div className="pm-prose" style={{ color: 'var(--c-text-dim)', marginTop: 12 }}>
                    <SemanticMarkdown>{fixStrategy.justification}</SemanticMarkdown>
                  </div>
                </details>
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
                              <details style={{ marginTop: 8 }}>
                                <summary style={{
                                  cursor: 'pointer', fontFamily: 'var(--font-display)',
                                  fontSize: '0.75rem', fontWeight: 600, color: 'var(--c-text-muted)',
                                  listStyle: 'none', display: 'inline-flex', alignItems: 'center', gap: 6,
                                  background: 'var(--c-surface-2)', padding: '4px 10px', borderRadius: 6, border: '1px solid var(--c-border)'
                                }}>
                                  View Description
                                </summary>
                                <div className="pm-prose" style={{ color: 'var(--c-text-dim)', marginTop: 12, paddingLeft: 12, borderLeft: '2px solid var(--c-border-hi)' }}>
                                  <SemanticMarkdown>{action.description}</SemanticMarkdown>
                                </div>
                              </details>
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


