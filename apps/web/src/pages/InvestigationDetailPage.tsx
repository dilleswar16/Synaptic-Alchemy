import { useEffect, useState, useCallback } from 'react'
import { useParams, Link, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import Layout from '../components/Layout'
import {
  fetchInvestigation,
  approveInvestigation,
  rejectInvestigation,
  executeInvestigation,
  generatePostMortem,
  fetchPostMortem,
  type ApprovalResponse,
  type ExecutionResponse,
  type PostMortem,
} from '../api/client'

// ── Helpers ───────────────────────────────────────────────────────────────────

const STATUS_ICONS: Record<string, string> = {
  pending: '◎', approved: '✓', rejected: '✗', executed: '▶',
}
const STATUS_CLS: Record<string, string> = {
  pending: 'badge-pending', approved: 'badge-approved',
  rejected: 'badge-rejected', executed: 'badge-executed',
}

function StatusBadge({ status }: { status: string }) {
  const icon = STATUS_ICONS[status] ?? '○'
  return (
    <span className={`badge ${STATUS_CLS[status] ?? 'badge-pending'}`}>
      {icon} {status}
    </span>
  )
}

// ── Section wrapper ───────────────────────────────────────────────────────────

function Section({ title, children, accent }: { title: string; children: React.ReactNode; accent?: boolean }) {
  return (
    <section style={{ marginTop: 20 }}>
      <div className={accent ? 'panel-signal' : 'panel'} style={{ overflow: 'hidden' }}>
        <div style={{
          padding: '10px 18px',
          borderBottom: '1px solid var(--c-border)',
          background: 'var(--c-surface-2)',
        }}>
          <span style={{
            fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.72rem',
            letterSpacing: '0.14em', textTransform: 'uppercase', color: accent ? 'var(--c-signal)' : 'var(--c-text-muted)',
          }}>
            {title}
          </span>
        </div>
        <div style={{ padding: '16px 18px' }}>
          {children}
        </div>
      </div>
    </section>
  )
}

// ── Info row ──────────────────────────────────────────────────────────────────

function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', marginBottom: 10, minHeight: 20 }}>
      <span style={{ fontFamily: 'var(--font-display)', fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--c-text-muted)', minWidth: 120, paddingTop: 2 }}>
        {label}
      </span>
      <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.85rem', color: 'var(--c-text-dim)', flex: 1 }}>
        {children}
      </div>
    </div>
  )
}

// ── Alert banner ──────────────────────────────────────────────────────────────

function Alert({ ok, message, detail }: { ok: boolean; message: string; detail?: React.ReactNode }) {
  return (
    <div style={{
      padding: '10px 14px',
      background: ok ? 'var(--c-green-bg)' : 'var(--c-red-bg)',
      border: `1px solid ${ok ? 'var(--c-green-border)' : 'var(--c-red-border)'}`,
      borderRadius: 3,
      marginBottom: 14,
    }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: ok ? 'var(--c-green)' : 'var(--c-red)', fontWeight: 600 }}>
        {ok ? '✓' : '✗'} {message}
      </div>
      {detail && <div style={{ marginTop: 8 }}>{detail}</div>}
    </div>
  )
}

// ── Approval section ──────────────────────────────────────────────────────────

type ApprovalAction = 'approve' | 'reject'

interface ApprovalSectionProps {
  requestId: string
  status: string
  pendingAction: ApprovalAction | null
  onClearPendingAction: () => void
}

function ApprovalSection({ requestId, status, pendingAction, onClearPendingAction }: ApprovalSectionProps) {
  const queryClient = useQueryClient()
  const [confirmingAction, setConfirmingAction] = useState<ApprovalAction | null>(pendingAction)
  const [outcome, setOutcome] = useState<{ ok: boolean; message: string } | null>(null)

  useEffect(() => {
    if (pendingAction) setConfirmingAction(pendingAction)
  }, [pendingAction])

  const onSuccess = (data: ApprovalResponse) => {
    setOutcome({ ok: true, message: data.message })
    setConfirmingAction(null)
    onClearPendingAction()
    queryClient.invalidateQueries({ queryKey: ['investigation', requestId] })
  }
  const onError = (err: Error) => {
    setOutcome({ ok: false, message: err.message })
    setConfirmingAction(null)
  }

  const approveMutation = useMutation({ mutationFn: () => approveInvestigation(requestId), onSuccess, onError })
  const rejectMutation  = useMutation({ mutationFn: () => rejectInvestigation(requestId),  onSuccess, onError })
  const isPending = approveMutation.isPending || rejectMutation.isPending

  return (
    <Section title="Approval Decision" accent>
      <InfoRow label="Current Status">
        <StatusBadge status={status} />
      </InfoRow>

      {outcome && <Alert ok={outcome.ok} message={outcome.message} />}

      {status === 'pending' && !confirmingAction && !outcome && (
        <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
          <button className="btn-success" onClick={() => setConfirmingAction('approve')}>
            ✓ Approve
          </button>
          <button className="btn-danger" onClick={() => setConfirmingAction('reject')}>
            ✗ Reject
          </button>
        </div>
      )}

      {status === 'pending' && confirmingAction && !outcome && (
        <div style={{
          marginTop: 12, padding: '14px 16px',
          background: confirmingAction === 'approve' ? 'var(--c-green-bg)' : 'var(--c-red-bg)',
          border: `1px solid ${confirmingAction === 'approve' ? 'var(--c-green-border)' : 'var(--c-red-border)'}`,
          borderRadius: 3,
        }}>
          <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.82rem', color: 'var(--c-text-dim)', marginBottom: 12 }}>
            {confirmingAction === 'approve'
              ? 'Confirm approval — this will allow the fix strategy to be executed against the cluster.'
              : 'Confirm rejection — no fix will be executed for this investigation.'}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              disabled={isPending}
              onClick={() => confirmingAction === 'approve' ? approveMutation.mutate() : rejectMutation.mutate()}
              className={confirmingAction === 'approve' ? 'btn-success' : 'btn-danger'}
            >
              {isPending ? 'Processing…' : `Confirm ${confirmingAction === 'approve' ? 'Approval' : 'Rejection'}`}
            </button>
            <button
              disabled={isPending}
              onClick={() => { setConfirmingAction(null); onClearPendingAction() }}
              className="btn-ghost"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {status !== 'pending' && !outcome && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--c-text-muted)', marginTop: 8 }}>
          {status === 'approved' && 'Decision locked — proceed to execution below.'}
          {status === 'rejected' && 'This investigation was rejected. No execution will occur.'}
          {status === 'executed' && 'Fix strategy has already been executed.'}
        </div>
      )}
    </Section>
  )
}

// ── Execution section ─────────────────────────────────────────────────────────

function ExecutionSection({ requestId, status }: { requestId: string; status: string }) {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)
  const [outcome, setOutcome] = useState<{ ok: boolean; data: ExecutionResponse | null; message: string } | null>(null)

  const executeMutation = useMutation({
    mutationFn: () => executeInvestigation(requestId),
    onSuccess: (data) => {
      setOutcome({ ok: data.all_succeeded, data, message: data.message })
      setConfirming(false)
      queryClient.invalidateQueries({ queryKey: ['investigation', requestId] })
    },
    onError: (err: Error) => {
      setOutcome({ ok: false, data: null, message: err.message })
      setConfirming(false)
    },
  })

  if (status !== 'approved' && status !== 'executed') return null

  return (
    <Section title="Execution">
      {status === 'executed' && !outcome && (
        <Alert ok message="Fix strategy has already been executed." />
      )}

      {outcome && (
        <Alert
          ok={outcome.ok}
          message={outcome.message}
          detail={outcome.data?.outcomes?.length ? (
            <ul style={{ margin: 0, paddingLeft: '1.2rem' }}>
              {outcome.data.outcomes.map((o, i) => (
                <li key={i} style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: o.success ? 'var(--c-green)' : 'var(--c-red)', marginBottom: 3 }}>
                  <strong>{o.title}:</strong> {o.detail}
                </li>
              ))}
            </ul>
          ) : undefined}
        />
      )}

      {status === 'approved' && !outcome && !confirming && (
        <button className="btn-primary" onClick={() => setConfirming(true)}>
          ▶ Execute Fix Strategy
        </button>
      )}

      {status === 'approved' && confirming && !outcome && (
        <div style={{
          marginTop: 12, padding: '14px 16px',
          background: 'var(--c-signal-glow)',
          border: '1px solid var(--c-border-glow)',
          borderRadius: 3,
        }}>
          <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.82rem', color: 'var(--c-text-dim)', marginBottom: 12 }}>
            Confirm execution — Corvin will run every approved action against the live cluster.
            This operation is irreversible.
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              disabled={executeMutation.isPending}
              onClick={() => executeMutation.mutate()}
              className="btn-primary"
            >
              {executeMutation.isPending ? 'Executing…' : 'Confirm Execute'}
            </button>
            <button disabled={executeMutation.isPending} onClick={() => setConfirming(false)} className="btn-ghost">
              Cancel
            </button>
          </div>
        </div>
      )}
    </Section>
  )
}

// ── Post-mortem section ───────────────────────────────────────────────────────

function PostMortemSection({ requestId }: { requestId: string }) {
  const queryClient = useQueryClient()

  const { data: existing, isLoading: checking } = useQuery<PostMortem>({
    queryKey: ['postmortem', requestId],
    queryFn: () => fetchPostMortem(requestId),
    retry: false,
  })

  const generateMutation = useMutation({
    mutationFn: () => generatePostMortem(requestId),
    onSuccess: (data) => queryClient.setQueryData(['postmortem', requestId], data),
  })

  const pm: PostMortem | undefined = existing ?? generateMutation.data

  const downloadMarkdown = useCallback(() => {
    if (!pm) return
    const blob = new Blob([pm.markdown], { type: 'text/markdown' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href = url; a.download = `postmortem-${requestId}.md`; a.click()
    URL.revokeObjectURL(url)
  }, [pm, requestId])

  return (
    <Section title="Blameless Post-Mortem">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: pm ? 18 : 0 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.82rem', color: 'var(--c-text-muted)' }}>
            AI-generated incident report with timeline, impact, and prevention recommendations.
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
          {pm && (
            <button onClick={downloadMarkdown} className="btn-ghost" style={{ fontSize: '0.75rem', padding: '6px 12px' }}>
              ↓ .md
            </button>
          )}
          {!pm && !checking && (
            <button
              onClick={() => generateMutation.mutate()}
              disabled={generateMutation.isPending}
              className="btn-primary"
              style={{ fontSize: '0.78rem', padding: '7px 14px' }}
            >
              {generateMutation.isPending ? 'Generating…' : '▶ Generate'}
            </button>
          )}
          {checking && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-text-faint)' }}>Checking…</span>
          )}
        </div>
      </div>

      {generateMutation.isError && (
        <Alert ok={false} message={(generateMutation.error as Error).message} />
      )}

      {pm && (
        <div className="pm-prose" style={{ borderTop: '1px solid var(--c-border)', paddingTop: 18, marginTop: 4 }}>
          <ReactMarkdown>{pm.markdown}</ReactMarkdown>
        </div>
      )}
    </Section>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function InvestigationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [searchParams, setSearchParams] = useSearchParams()

  const rawAction = searchParams.get('action')
  const pendingAction: ApprovalAction | null =
    rawAction === 'approve' || rawAction === 'reject' ? rawAction : null
  const clearPendingAction = () => setSearchParams({})

  const { data, isLoading, isError } = useQuery({
    queryKey: ['investigation', id],
    queryFn: () => fetchInvestigation(id!),
    enabled: !!id,
  })

  const approvalStatus = data?.request?.approval_status ?? 'pending'

  return (
    <Layout>
      <div style={{ maxWidth: 860 }}>
        {/* Page header */}
        <div className="animate-fade-up" style={{ marginBottom: 28 }}>
          <Link to="/investigations" style={{
            fontFamily: 'var(--font-display)', fontSize: '0.7rem', fontWeight: 700,
            letterSpacing: '0.1em', textTransform: 'uppercase',
            color: 'var(--c-text-muted)', textDecoration: 'none',
          }}>
            ← Investigations
          </Link>
          <div style={{ marginTop: 14 }}>
            <div style={{
              fontFamily: 'var(--font-display)', fontSize: '0.62rem', fontWeight: 700,
              letterSpacing: '0.18em', textTransform: 'uppercase',
              color: 'var(--c-signal)', marginBottom: 6,
            }}>
              Investigation
            </div>
            <h1 style={{
              margin: '0 0 14px',
              fontFamily: 'var(--font-display)', fontWeight: 900,
              fontSize: '2.2rem', letterSpacing: '0.04em',
              color: 'var(--c-text)', lineHeight: 1,
            }}>
              {data?.request?.service_name?.toUpperCase() ?? (isLoading ? '…' : 'INVESTIGATION')}
            </h1>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              {data?.request?.environment && (
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
                  padding: '3px 10px', borderRadius: 2,
                  background: 'rgba(249,115,22,0.08)',
                  border: '1px solid rgba(249,115,22,0.2)',
                  color: 'var(--c-signal)', letterSpacing: '0.04em',
                }}>
                  {data.request.environment}
                </span>
              )}
              {data?.request?.trigger_source && (
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
                  padding: '3px 10px', borderRadius: 2,
                  background: 'var(--c-surface-2)',
                  border: '1px solid var(--c-border-hi)',
                  color: 'var(--c-text-dim)', letterSpacing: '0.04em',
                }}>
                  {data.request.trigger_source.replace(/_/g, ' ')}
                </span>
              )}
              {data && <StatusBadge status={approvalStatus} />}
              {data?.request?.id && (
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.62rem',
                  color: 'var(--c-text-faint)', letterSpacing: '0.04em',
                }}>
                  #{data.request.id.substring(0, 8)}…
                </span>
              )}
            </div>
          </div>
        </div>

        {isLoading && (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--c-text-faint)' }}>
            Loading…
          </div>
        )}
        {isError && (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--c-red)' }}>
            ✗ Could not load investigation.
          </div>
        )}

        {data && (
          <>
            {/* ── Request context ─── */}
            {data.request?.description && (
              <Section title="Context">
                <p style={{
                  margin: 0,
                  fontFamily: 'var(--font-body)', fontSize: '0.88rem',
                  color: 'var(--c-text-dim)', lineHeight: 1.75,
                }}>
                  {data.request.description}
                </p>
              </Section>
            )}

            {/* ── RCA ─── */}
            {data.rca && (
              <Section title="Root Cause Analysis">
                {/* Confidence bar */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 22 }}>
                  <span className={`badge ${
                    data.rca.confidence === 'high' ? 'badge-approved'
                    : data.rca.confidence === 'low' ? 'badge-rejected'
                    : 'badge-pending'
                  }`}>
                    {data.rca.confidence} confidence
                  </span>
                  <div style={{ flex: 1, height: 3, background: 'var(--c-surface-3)', borderRadius: 2, overflow: 'hidden' }}>
                    <div style={{
                      height: '100%',
                      width: data.rca.confidence === 'high' ? '85%' : data.rca.confidence === 'medium' ? '52%' : '20%',
                      background: data.rca.confidence === 'high' ? 'var(--c-green)'
                        : data.rca.confidence === 'medium' ? 'var(--c-yellow)' : 'var(--c-red)',
                      borderRadius: 2,
                      transition: 'width 0.8s ease',
                    }} />
                  </div>
                </div>

                {/* Root cause — highlighted card */}
                <div style={{
                  borderLeft: '3px solid var(--c-red)',
                  padding: '14px 18px',
                  background: 'rgba(239,68,68,0.04)',
                  marginBottom: 20,
                  borderRadius: '0 3px 3px 0',
                }}>
                  <div style={{
                    fontFamily: 'var(--font-display)', fontSize: '0.6rem', fontWeight: 700,
                    letterSpacing: '0.14em', textTransform: 'uppercase',
                    color: 'var(--c-red)', marginBottom: 8,
                  }}>
                    Root Cause
                  </div>
                  <p style={{
                    margin: 0,
                    fontFamily: 'var(--font-body)', fontSize: '0.9rem',
                    color: 'var(--c-text)', lineHeight: 1.75,
                  }}>
                    {data.rca.root_cause}
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
                  <p style={{
                    margin: 0,
                    fontFamily: 'var(--font-body)', fontSize: '0.88rem',
                    color: 'var(--c-text-dim)', lineHeight: 1.75,
                  }}>
                    {data.rca.summary}
                  </p>
                </div>

                {/* Contributing factors */}
                {data.rca.contributing_factors?.length > 0 && (
                  <div>
                    <div style={{
                      fontFamily: 'var(--font-display)', fontSize: '0.6rem', fontWeight: 700,
                      letterSpacing: '0.14em', textTransform: 'uppercase',
                      color: 'var(--c-text-muted)', marginBottom: 10,
                    }}>
                      Contributing Factors ({data.rca.contributing_factors.length})
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {data.rca.contributing_factors.map((f: string, i: number) => (
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
                            color: 'var(--c-text-dim)', lineHeight: 1.6,
                          }}>
                            {f}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--c-border)' }}>
                  <Link to={`/investigations/${id}/fix-strategy`} style={{
                    fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.72rem',
                    letterSpacing: '0.1em', textTransform: 'uppercase',
                    color: 'var(--c-signal)', textDecoration: 'none',
                  }}>
                    View Fix Strategy →
                  </Link>
                </div>
              </Section>
            )}

            {!data.rca && (
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--c-text-faint)', marginTop: 20 }}>
                RCA not yet available for this investigation.
              </div>
            )}

            <ApprovalSection
              requestId={id!}
              status={approvalStatus}
              pendingAction={pendingAction}
              onClearPendingAction={clearPendingAction}
            />

            <ExecutionSection requestId={id!} status={approvalStatus} />

            {approvalStatus === 'executed' && (
              <PostMortemSection requestId={id!} />
            )}
          </>
        )}
      </div>
    </Layout>
  )
}

