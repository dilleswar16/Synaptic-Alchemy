/**
 * ExecutionSection — shows after approval, lets the operator trigger execution.
 *
 * Two modes:
 *   1. "Run All" — streams execution via SSE, showing step-by-step progress
 *      with execution logs and live pod logs after each action.
 *   2. Legacy fallback — batch execute (old button still works if SSE fails).
 */
import { useState, useRef, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  executeInvestigation,
  streamExecuteAll,
  executeSingleAction,
  type ExecutionResponse,
  type ExecutionStreamEvent,
  type SingleActionResult,
} from '../../api/client'
import { previewSeenKey } from '../RemediationPreviewPanel'
import { Section, AlertBanner } from '../Section'

interface ExecutionSectionProps {
  requestId: string
  status: string
  /** Fix strategy actions — passed from parent to show step-by-step UI */
  actions?: Array<{ title: string; action_type?: string; target_service?: string; target_namespace?: string; risk_level?: string }>
}

type StepState = 'idle' | 'running' | 'success' | 'failed'

interface StepResult {
  state: StepState
  detail?: string
  logs: string[]
  podLogs: Array<{ pod: string; logs: string }>
}

export function ExecutionSection({ requestId, status, actions = [] }: ExecutionSectionProps) {
  const queryClient = useQueryClient()
  const previewSeen = typeof window !== 'undefined' && !!window.sessionStorage.getItem(previewSeenKey(requestId))
  const [confirming, setConfirming] = useState(false)
  const [mode, setMode] = useState<'idle' | 'streaming' | 'done'>('idle')
  const [steps, setSteps] = useState<StepResult[]>([])
  const [allSucceeded, setAllSucceeded] = useState<boolean | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const logEndRef = useRef<HTMLDivElement | null>(null)

  // Legacy batch outcome (kept for backwards compat)
  const [legacyOutcome, setLegacyOutcome] = useState<{
    ok: boolean; data: ExecutionResponse | null; message: string
  } | null>(null)

  const legacyMutation = useMutation({
    mutationFn: () => executeInvestigation(requestId),
    onSuccess: (data) => {
      setLegacyOutcome({ ok: data.all_succeeded, data, message: data.message })
      setConfirming(false)
      queryClient.invalidateQueries({ queryKey: ['investigation', requestId] })
    },
    onError: (err: Error) => {
      setLegacyOutcome({ ok: false, data: null, message: err.message })
      setConfirming(false)
    },
  })

  // Single-action mutation for step-by-step manual execution
  const singleMutation = useMutation({
    mutationFn: (idx: number) => executeSingleAction(requestId, idx),
    onMutate: (idx) => {
      setSteps(prev => {
        const next = [...prev]
        next[idx] = { ...next[idx], state: 'running' }
        return next
      })
    },
    onSuccess: (result: SingleActionResult, idx: number) => {
      setSteps(prev => {
        const next = [...prev]
        next[idx] = {
          state: result.success ? 'success' : 'failed',
          detail: result.detail,
          logs: result.logs ?? [],
          podLogs: [],
        }
        return next
      })
      queryClient.invalidateQueries({ queryKey: ['investigation', requestId] })
    },
    onError: (err: Error, idx: number) => {
      setSteps(prev => {
        const next = [...prev]
        next[idx] = { state: 'failed', detail: err.message, logs: [], podLogs: [] }
        return next
      })
    },
  })

  // Auto-scroll to latest log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [steps])

  // Initialize step state when actions arrive
  useEffect(() => {
    if (actions.length > 0 && steps.length === 0) {
      setSteps(actions.map(() => ({ state: 'idle' as StepState, logs: [], podLogs: [] })))
    }
  }, [actions.length])

  function startStreamExecution() {
    setConfirming(false)
    setMode('streaming')
    setSteps(actions.map(() => ({ state: 'idle' as StepState, logs: [], podLogs: [] })))
    setAllSucceeded(null)

    const controller = streamExecuteAll(
      requestId,
      (evt: ExecutionStreamEvent) => {
        if (evt.event === 'action_start' && evt.action_index != null) {
          setSteps(prev => {
            const next = [...prev]
            next[evt.action_index!] = { ...next[evt.action_index!], state: 'running' }
            return next
          })
        }
        if (evt.event === 'action_complete' && evt.action_index != null) {
          setSteps(prev => {
            const next = [...prev]
            next[evt.action_index!] = {
              state: evt.success ? 'success' : 'failed',
              detail: evt.detail,
              logs: evt.logs ?? [],
              podLogs: next[evt.action_index!]?.podLogs ?? [],
            }
            return next
          })
        }
        if (evt.event === 'pod_logs' && evt.action_index != null) {
          setSteps(prev => {
            const next = [...prev]
            next[evt.action_index!] = {
              ...next[evt.action_index!],
              podLogs: evt.pod_logs ?? [],
            }
            return next
          })
        }
        if (evt.event === 'done') {
          setMode('done')
          setAllSucceeded(evt.all_succeeded ?? false)
          queryClient.invalidateQueries({ queryKey: ['investigation', requestId] })
        }
      },
      () => {
        setMode('done')
        setAllSucceeded(false)
      },
    )
    abortRef.current = controller
  }

  if (status !== 'approved' && status !== 'executed') return null

  const hasActions = actions.length > 0
  const completedCount = steps.filter(s => s.state === 'success' || s.state === 'failed').length

  return (
    <Section title="Execution">
      {/* Already executed banner (only when no active stream) */}
      {status === 'executed' && mode === 'idle' && !legacyOutcome && (
        <AlertBanner ok message="Fix strategy has already been executed." />
      )}

      {/* Legacy outcome display */}
      {legacyOutcome && mode === 'idle' && (
        <AlertBanner
          ok={legacyOutcome.ok}
          message={legacyOutcome.message}
          detail={legacyOutcome.data?.outcomes?.length ? (
            <ul style={{ margin: 0, paddingLeft: '1.2rem' }}>
              {legacyOutcome.data.outcomes.map((o, i) => (
                <li key={i} style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
                  color: o.success ? 'var(--c-green)' : 'var(--c-red)', marginBottom: 3,
                }}>
                  <strong>{o.title}:</strong> {o.detail}
                </li>
              ))}
            </ul>
          ) : undefined}
        />
      )}

      {/* ── Confirmation gate ── */}
      {status === 'approved' && mode === 'idle' && !legacyOutcome && !confirming && (
        previewSeen ? (
          <div style={{ display: 'flex', gap: 10 }}>
            {hasActions && (
              <button className="btn-primary" onClick={() => setConfirming(true)}>
                ▶ Run All Steps
              </button>
            )}
            {!hasActions && (
              <button className="btn-primary" onClick={() => setConfirming(true)}>
                ▶ Execute Fix Strategy
              </button>
            )}
          </div>
        ) : (
          <AlertBanner
            ok={false}
            message="Execution locked until remediation preview is reviewed."
            detail={(
              <Link to={`/investigations/${requestId}/fix-strategy`} style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem' }}>
                Open Fix Preview →
              </Link>
            )}
          />
        )
      )}

      {/* ── Confirm dialog ── */}
      {confirming && mode === 'idle' && (
        <div style={{
          marginTop: 12, padding: '14px 16px',
          background: 'var(--c-signal-glow)',
          border: '1px solid var(--c-border-glow)',
          borderRadius: 8,
        }}>
          <div style={{
            fontFamily: 'var(--font-body)', fontSize: '0.82rem',
            color: 'var(--c-text-dim)', marginBottom: 12,
          }}>
            {hasActions
              ? `Confirm execution — Corvin will run ${actions.length} action(s) step-by-step against the live cluster with live log streaming.`
              : 'Confirm execution — Corvin will run every approved action against the live cluster. This operation is irreversible.'}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => hasActions ? startStreamExecution() : legacyMutation.mutate()}
              disabled={legacyMutation.isPending}
              className="btn-primary"
            >
              {legacyMutation.isPending ? 'Executing…' : 'Confirm Execute'}
            </button>
            <button
              onClick={() => setConfirming(false)}
              disabled={legacyMutation.isPending}
              className="btn-ghost"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* ── Step-by-step execution panel ── */}
      {(mode === 'streaming' || mode === 'done') && hasActions && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 0, marginTop: 8 }}>
          {/* Progress header */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 12,
            padding: '10px 14px',
            background: 'var(--c-surface-2)',
            border: '1px solid var(--c-border-hi)',
            borderRadius: '6px 6px 0 0',
          }}>
            <span style={{
              fontFamily: 'var(--font-display)', fontSize: '0.7rem',
              fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase',
              color: mode === 'streaming' ? 'var(--c-signal)' : allSucceeded ? 'var(--c-green)' : 'var(--c-red)',
            }}>
              {mode === 'streaming' ? '⟳ Executing…' : allSucceeded ? '✓ All Complete' : '✗ Completed with errors'}
            </span>
            <div style={{ display: 'flex', gap: 4, flex: 1 }}>
              {steps.map((s, idx) => (
                <div key={idx} style={{
                  flex: 1, height: 5, borderRadius: 2,
                  background: s.state === 'success' ? 'var(--c-green)'
                    : s.state === 'failed' ? 'var(--c-red)'
                    : s.state === 'running' ? 'var(--c-signal)'
                    : 'var(--c-border)',
                  transition: 'background 0.3s',
                }} />
              ))}
            </div>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-dim)',
            }}>
              {completedCount}/{actions.length}
            </span>
          </div>

          {/* Step cards */}
          <div style={{
            border: '1px solid var(--c-border-hi)',
            borderTop: 'none',
            borderRadius: '0 0 6px 6px',
            overflow: 'hidden',
          }}>
            {steps.map((step, idx) => (
              <div key={idx} style={{
                borderBottom: idx < steps.length - 1 ? '1px solid var(--c-border)' : undefined,
                opacity: step.state === 'idle' ? 0.5 : 1,
                transition: 'opacity 0.3s',
              }}>
                {/* Step header */}
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '10px 14px',
                  background: step.state === 'running' ? 'color-mix(in srgb, var(--c-signal) 5%, transparent)' : 'transparent',
                }}>
                  {/* Status icon */}
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.75rem', fontWeight: 700,
                    width: 22, textAlign: 'center',
                    color: step.state === 'success' ? 'var(--c-green)'
                      : step.state === 'failed' ? 'var(--c-red)'
                      : step.state === 'running' ? 'var(--c-signal)'
                      : 'var(--c-text-faint)',
                  }}>
                    {step.state === 'success' ? '✓' : step.state === 'failed' ? '✗' : step.state === 'running' ? '⟳' : (idx + 1)}
                  </span>
                  {/* Title */}
                  <span style={{
                    fontFamily: 'var(--font-display)', fontSize: '0.78rem', fontWeight: 600,
                    color: 'var(--c-text)', flex: 1,
                  }}>
                    {actions[idx]?.title ?? `Step ${idx + 1}`}
                  </span>
                  {/* Action type badge + auto/manual chip */}
                  {actions[idx]?.action_type && (
                    <>
                      <span style={{
                        fontFamily: 'var(--font-mono)', fontSize: '0.6rem',
                        padding: '2px 8px', borderRadius: 4,
                        background: 'var(--c-surface-2)', border: '1px solid var(--c-border)',
                        color: 'var(--c-text-dim)',
                      }}>
                        {actions[idx].action_type}
                      </span>
                      <span style={{
                        fontFamily: 'var(--font-mono)', fontSize: '0.56rem',
                        padding: '2px 7px', borderRadius: 4,
                        background: actions[idx].action_type!.toLowerCase() === 'manual'
                          ? 'color-mix(in srgb, #f59e0b 12%, transparent)'
                          : 'color-mix(in srgb, var(--c-green) 12%, transparent)',
                        border: `1px solid ${actions[idx].action_type!.toLowerCase() === 'manual' ? '#f59e0b33' : 'var(--c-success-border)'}`,
                        color: actions[idx].action_type!.toLowerCase() === 'manual' ? '#f59e0b' : 'var(--c-green)',
                      }}>
                        {actions[idx].action_type!.toLowerCase() === 'manual' ? '👤 Human' : '⚡ Auto'}
                      </span>
                    </>
                  )}
                  {/* Target service/namespace badge */}
                  {actions[idx]?.target_service && (
                    <span style={{
                      fontFamily: 'var(--font-mono)', fontSize: '0.58rem',
                      padding: '2px 8px', borderRadius: 4,
                      background: 'color-mix(in srgb, var(--c-signal) 10%, transparent)',
                      border: '1px solid var(--c-border)',
                      color: 'var(--c-signal)',
                    }}>
                      → {actions[idx].target_namespace ? `${actions[idx].target_namespace}/` : ''}{actions[idx].target_service}
                    </span>
                  )}
                  {/* Manual execute button for step-by-step mode */}
                  {mode === 'done' && step.state === 'idle' && (
                    <button
                      onClick={() => singleMutation.mutate(idx)}
                      style={{
                        fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 600,
                        padding: '3px 10px', borderRadius: 4, border: 'none',
                        background: 'var(--c-signal)', color: '#fff', cursor: 'pointer',
                      }}
                    >
                      ▶ Run
                    </button>
                  )}
                  {step.state === 'failed' && mode === 'done' && (
                    <button
                      onClick={() => singleMutation.mutate(idx)}
                      style={{
                        fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 600,
                        padding: '3px 10px', borderRadius: 4,
                        border: '1px solid var(--c-red-border)',
                        background: 'transparent', color: 'var(--c-red)', cursor: 'pointer',
                      }}
                    >
                      ↻ Retry
                    </button>
                  )}
                </div>

                {/* Detail text */}
                {step.detail && (
                  <div style={{
                    padding: '0 14px 6px 46px',
                    fontFamily: 'var(--font-mono)', fontSize: '0.68rem',
                    color: step.state === 'success' ? 'var(--c-green)' : step.state === 'failed' ? 'var(--c-red)' : 'var(--c-text-dim)',
                  }}>
                    {step.detail}
                  </div>
                )}

                {/* Execution logs terminal */}
                {step.logs.length > 0 && (
                  <div style={{
                    margin: '4px 14px 8px 46px', padding: '8px 12px',
                    background: '#0d1117',
                    border: '1px solid var(--c-border)',
                    borderRadius: 6,
                    maxHeight: 120,
                    overflowY: 'auto',
                  }}>
                    <div style={{
                      fontFamily: 'var(--font-mono)', fontSize: '0.55rem',
                      fontWeight: 700, color: '#8b949e',
                      letterSpacing: '0.1em', textTransform: 'uppercase',
                      marginBottom: 4,
                    }}>
                      Execution Log
                    </div>
                    {step.logs.map((line, li) => (
                      <div key={li} style={{
                        fontFamily: 'var(--font-mono)', fontSize: '0.62rem',
                        color: line.includes('✓') ? '#3fb950' : line.includes('✗') ? '#f85149' : '#c9d1d9',
                        lineHeight: 1.65, whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                      }}>
                        {line}
                      </div>
                    ))}
                  </div>
                )}

                {/* Live pod logs */}
                {step.podLogs.length > 0 && (
                  <div style={{
                    margin: '0 14px 10px 46px', padding: '8px 12px',
                    background: '#0a0e14',
                    border: '1px solid #1a2332',
                    borderRadius: 6,
                    maxHeight: 180,
                    overflowY: 'auto',
                  }}>
                    <div style={{
                      fontFamily: 'var(--font-mono)', fontSize: '0.55rem',
                      fontWeight: 700, color: '#4ec9b0',
                      letterSpacing: '0.1em', textTransform: 'uppercase',
                      marginBottom: 6,
                    }}>
                      Live Pod Logs
                    </div>
                    {step.podLogs.map((pl, pi) => (
                      <div key={pi} style={{ marginBottom: pi < step.podLogs.length - 1 ? 8 : 0 }}>
                        <div style={{
                          fontFamily: 'var(--font-mono)', fontSize: '0.58rem',
                          color: '#569cd6', fontWeight: 600, marginBottom: 2,
                        }}>
                          pod/{pl.pod}
                        </div>
                        <pre style={{
                          margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.6rem',
                          color: '#d4d4d4', lineHeight: 1.55,
                          whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                        }}>
                          {pl.logs || '(no output)'}
                        </pre>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
            <div ref={logEndRef} />
          </div>
        </div>
      )}
    </Section>
  )
}
