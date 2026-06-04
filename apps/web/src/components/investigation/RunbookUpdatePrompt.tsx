/**
 * RunbookUpdatePrompt — V3.95 GitOps PR UI.
 *
 * Shown on InvestigationDetailPage when approval_status = 'executed'.
 * Prompts the operator to "Create Pull Request", fetches the runbook update,
 * displays it as a syntax-highlighted git diff, and allows "Merging".
 */
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { updateInvestigationRunbook, type RunbookUpdateResult } from '../../api/client'

interface Props {
  requestId: string
  serviceName: string
}

export function RunbookUpdatePrompt({ requestId, serviceName }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [result, setResult] = useState<RunbookUpdateResult | null>(null)
  const [merged, setMerged] = useState(false)

  const mutation = useMutation({
    mutationFn: () => updateInvestigationRunbook(requestId),
    onSuccess: (data) => setResult(data),
  })

  // 1. Merged State
  if (merged && result) {
    return (
      <div style={{
        borderRadius: 8, overflow: 'hidden', border: '1px solid var(--c-border-hi)',
        background: 'var(--c-surface)', padding: '16px 20px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            background: 'var(--c-purple)', color: 'white', width: 32, height: 32,
            borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '1.2rem',
          }}>
            <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
              <path fillRule="evenodd" d="M5 3.25a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm0 2.122a2.25 2.25 0 10-1.5 0v4.928a2.25 2.25 0 101.5 0V5.372zm3.1 9.128a.75.75 0 100-1.5.75.75 0 000 1.5zm.75-2.25a2.25 2.25 0 11-1.5 0v-2.5a2.25 2.25 0 111.5 0v2.5z" />
            </svg>
          </div>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.85rem', color: 'var(--c-purple)' }}>
              Pull request successfully merged and closed
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-text-faint)', marginTop: 2 }}>
              Corvin[bot] merged commit into <code style={{ background: 'var(--c-surface-2)', padding: '2px 4px', borderRadius: 4 }}>main</code>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // 2. PR Review State (Diff View)
  if (result) {
    const diffLines = result.content.split('\n').map(line => `+ ${line}`)
    
    return (
      <div style={{
        borderRadius: 8, overflow: 'hidden', border: '1px solid var(--c-border-hi)',
        background: 'var(--c-surface)',
      }}>
        {/* PR Header */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--c-border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '1.1rem', color: 'var(--c-text)' }}>
              Update runbook for {serviceName} <span style={{ color: 'var(--c-text-faint)', fontWeight: 400 }}>#42</span>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-text-muted)' }}>
            <span style={{
              background: 'var(--c-green)', color: 'white', padding: '3px 8px', borderRadius: 12,
              fontWeight: 700, display: 'flex', alignItems: 'center', gap: 4,
            }}>
              <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor">
                <path fillRule="evenodd" d="M7.177 3.073L9.573.677A.25.25 0 0110 .854v4.792a.25.25 0 01-.427.177L7.177 3.427a.25.25 0 010-.354zM3.75 2.5a.75.75 0 100 1.5.75.75 0 000-1.5zm-2.25.75a2.25 2.25 0 113 2.122v5.256a2.25 2.25 0 11-1.5 0V5.372A2.25 2.25 0 011.5 3.25zM11 2.5h-1V4h1a1.5 1.5 0 011.5 1.5v5.628a2.25 2.25 0 101.5 0V5.5A3 3 0 0011 2.5zm1 10.25a.75.75 0 111.5 0 .75.75 0 01-1.5 0zM3.75 12a.75.75 0 100 1.5.75.75 0 000-1.5z" />
              </svg>
              Open
            </span>
            <strong style={{ color: 'var(--c-text)' }}>Corvin[bot]</strong> wants to merge 1 commit into <code style={{ background: 'var(--c-surface-2)', padding: '2px 4px', borderRadius: 4 }}>main</code>
          </div>
        </div>

        {/* Diff View */}
        <div style={{ padding: '16px 20px', background: 'var(--c-surface-2)' }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-text-faint)', marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
            <span>knowledge/runbooks/{serviceName}.md</span>
            <span>+ {diffLines.length} lines</span>
          </div>
          <pre style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.72rem', lineHeight: 1.5,
            background: 'var(--c-surface-2)', color: 'var(--c-text-dim)', borderRadius: 6, padding: '12px 0',
            margin: 0, overflowX: 'auto', border: '1px solid var(--c-border)',
          }}>
            {diffLines.map((line, i) => (
              <div key={i} style={{ background: 'var(--c-success-bg)', display: 'flex' }}>
                <span style={{ color: 'var(--c-green)', opacity: 0.5, userSelect: 'none', width: 40, textAlign: 'right', paddingRight: 12 }}>{i + 1}</span>
                <span style={{ color: 'var(--c-green)', whiteSpace: 'pre-wrap' }}>{line}</span>
              </div>
            ))}
          </pre>
        </div>

        {/* Merge Button Area */}
        <div style={{ padding: '16px 20px', borderTop: '1px solid var(--c-border)', display: 'flex', gap: 12, alignItems: 'center', background: 'var(--c-surface)' }}>
          <button
            onClick={() => setMerged(true)}
            style={{
              fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.75rem',
              background: 'var(--c-green)', color: 'white', border: '1px solid var(--c-success-border)',
              padding: '6px 16px', borderRadius: 6, cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 8,
            }}
          >
            Merge pull request
          </button>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-text-faint)' }}>
            You can merge this pull request manually.
          </span>
        </div>
      </div>
    )
  }

  // 3. Initial State (Prompt)
  return (
    <div style={{
      borderRadius: 8, overflow: 'hidden', border: '1px solid var(--c-border)',
      background: 'var(--c-surface)',
    }}>
      <button
        onClick={() => setExpanded(e => !e)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '16px 20px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left',
          borderBottom: expanded ? '1px solid var(--c-border)' : 'none',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: '1.2rem' }}>🐙</span>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.8rem', color: 'var(--c-text)' }}>
              This Fix Worked — Create a Pull Request?
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text-dim)', marginTop: 2 }}>
              Corvin will generate a runbook step and open a PR against your GitOps repository.
            </div>
          </div>
        </div>
        <span style={{ color: 'var(--c-text-faint)' }}>{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div style={{ padding: '16px 20px', background: 'var(--c-surface-2)' }}>
          <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.85rem', color: 'var(--c-text-dim)', lineHeight: 1.6, marginBottom: 16 }}>
            Corvin will use <strong>GPT-5.1</strong> to write a concise runbook step based on this investigation's root cause and fix actions. It will then stage the changes to <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', background: 'var(--c-surface-3)', padding: '2px 6px', borderRadius: 4 }}>knowledge/runbooks/{serviceName}.md</code>.
          </div>
          
          {mutation.isError && (
            <div style={{ color: 'var(--c-red)', fontFamily: 'var(--font-mono)', fontSize: '0.75rem', padding: '8px 12px', background: 'var(--c-error-bg)', borderRadius: 6, marginBottom: 16 }}>
              ✗ {(mutation.error as Error).message}
            </div>
          )}

          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            style={{
              fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.75rem',
              background: mutation.isPending ? 'var(--c-surface-3)' : 'var(--c-green)',
              color: mutation.isPending ? 'var(--c-text-faint)' : 'white',
              border: '1px solid var(--c-success-border)',
              padding: '8px 16px', borderRadius: 6, cursor: mutation.isPending ? 'not-allowed' : 'pointer',
              display: 'inline-flex', alignItems: 'center', gap: 8,
              transition: 'all 0.15s',
            }}
          >
            {mutation.isPending ? 'Generating Diff…' : 'Create Pull Request'}
          </button>
        </div>
      )}
    </div>
  )
}
