/**
 * ExecutionSection — shows after approval, lets the operator trigger execution
 * with a mandatory 2-step confirmation.
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { executeInvestigation, type ExecutionResponse } from '../../api/client'
import { Section, AlertBanner } from '../Section'

interface ExecutionSectionProps {
  requestId: string
  status: string
}

export function ExecutionSection({ requestId, status }: ExecutionSectionProps) {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)
  const [outcome, setOutcome] = useState<{
    ok: boolean; data: ExecutionResponse | null; message: string
  } | null>(null)

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
        <AlertBanner ok message="Fix strategy has already been executed." />
      )}

      {outcome && (
        <AlertBanner
          ok={outcome.ok}
          message={outcome.message}
          detail={outcome.data?.outcomes?.length ? (
            <ul style={{ margin: 0, paddingLeft: '1.2rem' }}>
              {outcome.data.outcomes.map((o, i) => (
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
          <div style={{
            fontFamily: 'var(--font-body)', fontSize: '0.82rem',
            color: 'var(--c-text-dim)', marginBottom: 12,
          }}>
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
            <button
              disabled={executeMutation.isPending}
              onClick={() => setConfirming(false)}
              className="btn-ghost"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </Section>
  )
}
