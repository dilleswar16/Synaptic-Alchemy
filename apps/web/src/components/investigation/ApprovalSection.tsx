/**
 * ApprovalSection — approve / reject / acknowledge decision panel.
 *
 * When isInformational=true (service healthy, no real fix needed) the panel
 * replaces the Approve/Reject buttons with a single "Acknowledge & Close"
 * action, avoiding the confusing "approve doing nothing" anti-pattern.
 */
import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { approveInvestigation, rejectInvestigation, acknowledgeInvestigation, type ApprovalResponse } from '../../api/client'
import { Section, InfoRow, AlertBanner } from '../Section'
import { StatusBadge } from '../StatusBadge'

export type ApprovalAction = 'approve' | 'reject'

interface ApprovalSectionProps {
  requestId: string
  status: string
  pendingAction: ApprovalAction | null
  onClearPendingAction: () => void
  /** RCA confidence score (0–100). Drives the Predicted Outcome gauge. */
  confidence?: number
  /**
   * True when the RCA concluded no incident exists and no real fix is needed.
   * Replaces the Approve/Reject UI with a single "Acknowledge & Close" button.
   */
  isInformational?: boolean
}

export function ApprovalSection({
  requestId,
  status,
  pendingAction,
  onClearPendingAction,
  confidence = 75,
  isInformational = false,
}: ApprovalSectionProps) {
  const degradedPct = Math.max(10, 100 - confidence)
  const restoredPct = confidence
  const queryClient = useQueryClient()
  const [confirmingAction, setConfirmingAction] = useState<ApprovalAction | null>(pendingAction)
  const [confirmingAck, setConfirmingAck] = useState(false)
  const [outcome, setOutcome] = useState<{ ok: boolean; message: string } | null>(null)

  useEffect(() => {
    if (pendingAction) setConfirmingAction(pendingAction)
  }, [pendingAction])

  const onSuccess = (data: ApprovalResponse) => {
    setOutcome({ ok: true, message: data.message })
    setConfirmingAction(null)
    setConfirmingAck(false)
    onClearPendingAction()
    queryClient.invalidateQueries({ queryKey: ['investigation', requestId] })
  }
  const onError = (err: Error) => {
    setOutcome({ ok: false, message: err.message })
    setConfirmingAction(null)
    setConfirmingAck(false)
  }

  const approveMutation     = useMutation({ mutationFn: () => approveInvestigation(requestId),     onSuccess, onError })
  const rejectMutation      = useMutation({ mutationFn: () => rejectInvestigation(requestId),      onSuccess, onError })
  const acknowledgeMutation = useMutation({ mutationFn: () => acknowledgeInvestigation(requestId), onSuccess, onError })
  const isPending = approveMutation.isPending || rejectMutation.isPending || acknowledgeMutation.isPending

  return (
    <Section title="Approval Decision" accent id="approval-section">

      {/* ── Informational banner (healthy service, no fix needed) ── */}
      {isInformational && status === 'pending' && (
        <div style={{
          marginBottom: 16, padding: '14px 16px',
          background: 'rgba(34,197,94,0.06)',
          border: '1px solid rgba(34,197,94,0.25)',
          borderRadius: 6,
          display: 'flex', alignItems: 'flex-start', gap: 12,
        }}>
          <span style={{ fontSize: '1.2rem', lineHeight: 1 }}>✅</span>
          <div>
            <div style={{ fontWeight: 700, fontSize: '0.8rem', color: 'var(--c-green)', marginBottom: 4 }}>
              Service Confirmed Healthy — No Action Required
            </div>
            <div style={{ fontSize: '0.76rem', color: 'var(--c-text-dim)', lineHeight: 1.55 }}>
              Corvin's RCA found no active incident. All recommended actions are informational only.
              Acknowledge to close this investigation without executing any changes.
            </div>
          </div>
        </div>
      )}

      {/* ── Predicted outcome gauge (only for real incidents) ── */}
      {!isInformational && status === 'pending' && (
        <div style={{
          marginBottom: 16, padding: '12px',
          background: 'rgba(34,197,94,0.03)',
          border: '1px solid var(--c-success-border)',
          borderRadius: 8, display: 'flex', flexDirection: 'column', gap: 10,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: '0.8rem' }}>✨</span>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--c-success)', letterSpacing: '0.02em' }}>Predicted Outcome</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{ flex: 1 }}>
              <div style={{ height: 4, background: 'var(--c-surface-3)', borderRadius: 2, overflow: 'hidden', position: 'relative' }}>
                <div style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: `${degradedPct}%`, background: 'var(--c-error)' }} />
                <div style={{ position: 'absolute', left: `${degradedPct}%`, top: 0, height: '100%', width: `${restoredPct - degradedPct}%`, background: 'var(--c-success)', opacity: 0.5, borderLeft: '2px solid #fff' }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: '0.7rem', fontFamily: 'var(--font-mono)' }}>
                <span style={{ color: 'var(--c-error)' }}>Degraded: {degradedPct}%</span>
                <span style={{ color: 'var(--c-success)' }}>Predicted: {restoredPct}%</span>
              </div>
            </div>
            <div style={{ fontSize: '0.65rem', color: 'var(--c-text-dim)', lineHeight: 1.4, fontStyle: 'italic' }}>
              Corvin estimates this fix will restore <b>{restoredPct}%</b> of service health.
            </div>
          </div>
        </div>
      )}

      <InfoRow label="Current Status">
        <StatusBadge status={status} />
      </InfoRow>

      {outcome && <AlertBanner ok={outcome.ok} message={outcome.message} />}

      {/* ── INFORMATIONAL: single Acknowledge button ── */}
      {isInformational && status === 'pending' && !outcome && (
        <>
          {!confirmingAck && (
            <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
              <button className="btn-success" onClick={() => setConfirmingAck(true)}>
                ✓ Acknowledge &amp; Close
              </button>
            </div>
          )}
          {confirmingAck && (
            <div style={{
              marginTop: 12, padding: '14px 16px',
              background: 'rgba(34,197,94,0.06)',
              border: '1px solid rgba(34,197,94,0.25)',
              borderRadius: 3,
            }}>
              <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.82rem', color: 'var(--c-text-dim)', marginBottom: 12 }}>
                Confirm — close this investigation as informational. No changes will be made to the cluster.
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button disabled={isPending} onClick={() => acknowledgeMutation.mutate()} className="btn-success">
                  {isPending ? 'Closing…' : 'Confirm Close'}
                </button>
                <button disabled={isPending} onClick={() => setConfirmingAck(false)} className="btn-ghost">
                  Cancel
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* ── REAL INCIDENT: Approve / Reject buttons ── */}
      {!isInformational && status === 'pending' && !confirmingAction && !outcome && (
        <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
          <button className="btn-success" onClick={() => setConfirmingAction('approve')}>
            ✓ Approve
          </button>
          <button className="btn-danger" onClick={() => setConfirmingAction('reject')}>
            ✗ Reject
          </button>
        </div>
      )}

      {!isInformational && status === 'pending' && confirmingAction && !outcome && (
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
          {status === 'rejected' && (isInformational
            ? 'Acknowledged — confirmed healthy, closed as informational.'
            : 'This investigation was rejected. No execution will occur.')}
          {status === 'executed' && 'Fix strategy has already been executed.'}
        </div>
      )}
    </Section>
  )
}
