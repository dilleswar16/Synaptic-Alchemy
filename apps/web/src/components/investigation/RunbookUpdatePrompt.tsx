/**
 * RunbookUpdatePrompt — V3.9 learning loop UI.
 *
 * Shown on InvestigationDetailPage when approval_status = 'executed'.
 * Prompts the operator to commit the fix as a runbook step.
 * One click → LLM generates the step → appended to knowledge/runbooks/<service>.md
 */
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { updateRunbook, type RunbookUpdateResult } from '../../api/client'

interface Props {
  requestId: string
  serviceName: string
}

export function RunbookUpdatePrompt({ requestId, serviceName }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [result, setResult] = useState<RunbookUpdateResult | null>(null)

  const mutation = useMutation({
    mutationFn: () => updateRunbook(requestId),
    onSuccess: (data) => setResult(data),
  })

  if (result) {
    return (
      <div style={{
        borderRadius: 10, overflow: 'hidden',
        border: '1.5px solid rgba(34,197,94,0.3)',
        background: 'linear-gradient(160deg, rgba(34,197,94,0.06) 0%, var(--c-surface) 100%)',
      }}>
        <div style={{
          padding: '14px 18px',
          display: 'flex', alignItems: 'center', gap: 10,
          borderBottom: '1px solid rgba(34,197,94,0.15)',
        }}>
          <span style={{ fontSize: '1.1rem' }}>✅</span>
          <div>
            <div style={{
              fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.62rem',
              letterSpacing: '0.14em', textTransform: 'uppercase', color: '#22c55e',
            }}>
              Runbook Updated
            </div>
            <div style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.68rem',
              color: 'var(--c-text-dim)', marginTop: 2,
            }}>
              {result.message} — Corvin learned from this incident.
            </div>
          </div>
        </div>
        <div style={{ padding: '12px 18px' }}>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.63rem',
            color: 'var(--c-text-muted)', marginBottom: 8,
          }}>
            knowledge/runbooks/{serviceName}.md
          </div>
          <pre style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
            color: 'var(--c-text-dim)', lineHeight: 1.65,
            background: 'var(--c-surface-2)', borderRadius: 6, padding: '12px 14px',
            margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            border: '1px solid var(--c-border)',
            maxHeight: 260, overflowY: 'auto',
          }}>
            {result.content}
          </pre>
        </div>
      </div>
    )
  }

  return (
    <div style={{
      borderRadius: 10, overflow: 'hidden',
      border: '1.5px solid rgba(245,158,11,0.3)',
      background: 'linear-gradient(160deg, rgba(245,158,11,0.07) 0%, var(--c-surface) 100%)',
    }}>
      <button
        onClick={() => setExpanded(e => !e)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', gap: 12, padding: '14px 18px',
          background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left',
          borderBottom: expanded ? '1px solid rgba(245,158,11,0.15)' : 'none',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: '1rem' }}>✏️</span>
          <div>
            <div style={{
              fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.62rem',
              letterSpacing: '0.14em', textTransform: 'uppercase', color: '#f59e0b',
            }}>
              This Fix Worked — Update the Runbook?
            </div>
            <div style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.66rem',
              color: 'var(--c-text-dim)', marginTop: 2,
            }}>
              Corvin will generate a resolution step and append it to the {serviceName} runbook.
            </div>
          </div>
        </div>
        <span style={{ color: 'var(--c-text-faint)', fontSize: '0.8rem' }}>
          {expanded ? '▲' : '▼'}
        </span>
      </button>

      {expanded && (
        <div style={{ padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{
            fontFamily: 'var(--font-body)', fontSize: '0.83rem',
            color: 'var(--c-text-dim)', lineHeight: 1.65,
          }}>
            Corvin will call <strong>GPT-5.1</strong> to write a concise runbook step from this investigation's
            root cause and fix actions, then append it to{' '}
            <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
              knowledge/runbooks/{serviceName}.md
            </code>
            {' '}and the learnings log.
          </div>
          {mutation.isError && (
            <div style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
              color: '#ef4444', padding: '8px 10px', borderRadius: 6,
              background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
            }}>
              ✗ {(mutation.error as Error).message}
            </div>
          )}
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            style={{
              alignSelf: 'flex-start',
              fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.7rem',
              letterSpacing: '0.1em', textTransform: 'uppercase',
              padding: '9px 20px', borderRadius: 8, border: 'none', cursor: 'pointer',
              background: mutation.isPending ? 'var(--c-surface-2)' : '#f59e0b',
              color: mutation.isPending ? 'var(--c-text-muted)' : '#0d0f17',
              boxShadow: mutation.isPending ? 'none' : '0 0 18px rgba(245,158,11,0.4)',
              cursor: mutation.isPending ? 'not-allowed' : 'pointer',
              transition: 'all 0.18s',
            }}
          >
            {mutation.isPending ? 'Generating…' : '✏ Generate & Save Runbook Step'}
          </button>
        </div>
      )}
    </div>
  )
}
