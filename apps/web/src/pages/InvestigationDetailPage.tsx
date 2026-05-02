import { useEffect, useState } from 'react'
import { useParams, Link, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchInvestigation,
  approveInvestigation,
  rejectInvestigation,
  executeInvestigation,
  type ApprovalResponse,
  type ExecutionResponse,
} from '../api/client'

// ── Approval status badge ─────────────────────────────────────────────────────

const STATUS_STYLE: Record<string, { background: string; color: string; label: string }> = {
  pending:  { background: '#fff7e6', color: '#d46b08', label: '⏳ Pending Review' },
  approved: { background: '#f6ffed', color: '#389e0d', label: '✅ Approved' },
  rejected: { background: '#fff1f0', color: '#cf1322', label: '❌ Rejected' },
  executed: { background: '#e6f4ff', color: '#0958d9', label: '🚀 Executed' },
}

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLE[status] ?? { background: '#f5f5f5', color: '#555', label: status }
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 10px',
      borderRadius: '12px',
      fontSize: '0.85rem',
      fontWeight: 600,
      background: s.background,
      color: s.color,
    }}>
      {s.label}
    </span>
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

  // When Teams card sets ?action=approve / ?action=reject, immediately surface the confirm prompt
  useEffect(() => {
    if (pendingAction) setConfirmingAction(pendingAction)
  }, [pendingAction])

  const onSuccess = (data: ApprovalResponse) => {
    setOutcome({ ok: true, message: data.message })
    setConfirmingAction(null)
    onClearPendingAction()
    // Refetch the investigation so approval_status updates in the UI
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
    <section style={{ marginTop: '2rem', padding: '1.2rem 1.5rem', border: '1px solid #e8e8e8', borderRadius: '8px', background: '#fafafa' }}>
      <h2 style={{ marginTop: 0 }}>Approval</h2>
      <p>Status: <StatusBadge status={status} /></p>

      {outcome && (
        <p style={{ padding: '8px 12px', borderRadius: '6px', background: outcome.ok ? '#f6ffed' : '#fff1f0', color: outcome.ok ? '#389e0d' : '#cf1322', fontWeight: 500 }}>
          {outcome.message}
        </p>
      )}

      {status === 'pending' && !confirmingAction && !outcome && (
        <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem' }}>
          <button
            onClick={() => setConfirmingAction('approve')}
            style={{ padding: '8px 20px', background: '#52c41a', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 600 }}>
            ✅ Approve
          </button>
          <button
            onClick={() => setConfirmingAction('reject')}
            style={{ padding: '8px 20px', background: '#ff4d4f', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 600 }}>
            ❌ Reject
          </button>
        </div>
      )}

      {status === 'pending' && confirmingAction && !outcome && (
        <div style={{ marginTop: '0.75rem', padding: '1rem', background: confirmingAction === 'approve' ? '#f6ffed' : '#fff1f0', borderRadius: '6px', border: `1px solid ${confirmingAction === 'approve' ? '#b7eb8f' : '#ffa39e'}` }}>
          <p style={{ margin: '0 0 0.75rem', fontWeight: 500 }}>
            {confirmingAction === 'approve'
              ? '✅ Confirm approval — this will allow the fix strategy to be executed.'
              : '❌ Confirm rejection — no fix will be executed for this investigation.'}
          </p>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              disabled={isPending}
              onClick={() => confirmingAction === 'approve' ? approveMutation.mutate() : rejectMutation.mutate()}
              style={{ padding: '7px 18px', background: confirmingAction === 'approve' ? '#52c41a' : '#ff4d4f', color: '#fff', border: 'none', borderRadius: '6px', cursor: isPending ? 'not-allowed' : 'pointer', fontWeight: 600, opacity: isPending ? 0.7 : 1 }}>
              {isPending ? 'Processing…' : `Confirm ${confirmingAction === 'approve' ? 'Approve' : 'Reject'}`}
            </button>
            <button
              disabled={isPending}
              onClick={() => { setConfirmingAction(null); onClearPendingAction() }}
              style={{ padding: '7px 18px', background: '#fff', border: '1px solid #d9d9d9', borderRadius: '6px', cursor: 'pointer' }}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

// ── Execution section ─────────────────────────────────────────────────────────

interface ExecutionSectionProps {
  requestId: string
  status: string
}

function ExecutionSection({ requestId, status }: ExecutionSectionProps) {
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
    <section style={{ marginTop: '1.5rem', padding: '1.2rem 1.5rem', border: '1px solid #e8e8e8', borderRadius: '8px', background: '#fafafa' }}>
      <h2 style={{ marginTop: 0 }}>Execution</h2>

      {status === 'executed' && !outcome && (
        <p style={{ color: '#0958d9' }}>This investigation has already been executed.</p>
      )}

      {outcome && (
        <div style={{ padding: '8px 12px', borderRadius: '6px', background: outcome.ok ? '#f6ffed' : '#fff1f0', color: outcome.ok ? '#389e0d' : '#cf1322' }}>
          <p style={{ margin: 0, fontWeight: 500 }}>{outcome.message}</p>
          {outcome.data?.outcomes?.length ? (
            <ul style={{ marginTop: '0.5rem' }}>
              {outcome.data.outcomes.map((o, i) => (
                <li key={i}>
                  <strong>{o.title}:</strong> {o.success ? '✅' : '❌'} {o.detail}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      )}

      {status === 'approved' && !outcome && !confirming && (
        <button
          onClick={() => setConfirming(true)}
          style={{ padding: '8px 20px', background: '#0958d9', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 600 }}>
          🚀 Execute Fix Strategy
        </button>
      )}

      {status === 'approved' && confirming && !outcome && (
        <div style={{ marginTop: '0.5rem', padding: '1rem', background: '#e6f4ff', borderRadius: '6px', border: '1px solid #91caff' }}>
          <p style={{ margin: '0 0 0.75rem', fontWeight: 500 }}>
            🚀 Confirm execution — Corvin will run every approved action against the live cluster.
          </p>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              disabled={executeMutation.isPending}
              onClick={() => executeMutation.mutate()}
              style={{ padding: '7px 18px', background: '#0958d9', color: '#fff', border: 'none', borderRadius: '6px', cursor: executeMutation.isPending ? 'not-allowed' : 'pointer', fontWeight: 600, opacity: executeMutation.isPending ? 0.7 : 1 }}>
              {executeMutation.isPending ? 'Executing…' : 'Confirm Execute'}
            </button>
            <button
              disabled={executeMutation.isPending}
              onClick={() => setConfirming(false)}
              style={{ padding: '7px 18px', background: '#fff', border: '1px solid #d9d9d9', borderRadius: '6px', cursor: 'pointer' }}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function InvestigationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [searchParams, setSearchParams] = useSearchParams()

  // Teams card buttons set ?action=approve or ?action=reject
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
    <main style={{ fontFamily: 'sans-serif', padding: '2rem', maxWidth: '860px', margin: '0 auto' }}>
      <Link to="/">← Back to investigations</Link>
      <h1>Investigation Detail</h1>
      <p style={{ color: '#666', fontSize: '0.9rem' }}>ID: {id}</p>

      {isLoading && <p>Loading…</p>}
      {isError && <p style={{ color: '#cf1322' }}>Could not load investigation.</p>}

      {data && (
        <>
          <section>
            <h2>Request</h2>
            <pre style={{ background: '#f4f4f4', padding: '1rem', borderRadius: '6px', overflowX: 'auto' }}>
              {JSON.stringify(data.request ?? data, null, 2)}
            </pre>
          </section>

          {data.rca && (
            <section>
              <h2>Root Cause Analysis</h2>
              <p><strong>Summary:</strong> {data.rca.summary}</p>
              <p><strong>Root Cause:</strong> {data.rca.root_cause}</p>
              <p><strong>Confidence:</strong> {data.rca.confidence}</p>
              {data.rca.contributing_factors?.length > 0 && (
                <>
                  <p><strong>Contributing Factors:</strong></p>
                  <ul>
                    {data.rca.contributing_factors.map((f: string, i: number) => (
                      <li key={i}>{f}</li>
                    ))}
                  </ul>
                </>
              )}
              <Link to={`/investigations/${id}/fix-strategy`}>View Fix Strategy →</Link>
            </section>
          )}

          {!data.rca && (
            <p style={{ color: '#888' }}>RCA not yet available for this investigation.</p>
          )}

          <ApprovalSection
            requestId={id!}
            status={approvalStatus}
            pendingAction={pendingAction}
            onClearPendingAction={clearPendingAction}
          />

          <ExecutionSection requestId={id!} status={approvalStatus} />
        </>
      )}
    </main>
  )
}
