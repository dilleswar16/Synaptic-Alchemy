/**
 * PostMortemSection — generate, view, and download a blameless post-mortem.
 */
import { useCallback, useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { SemanticMarkdown } from '../SemanticMarkdown'
import { generatePostMortem, fetchPostMortem, type PostMortem } from '../../api/client'
import { Section, AlertBanner } from '../Section'
import { Modal } from '../Modal'

interface PostMortemSectionProps {
  requestId: string
  isExecuted: boolean
  serviceName: string
  duration?: string
}

export function PostMortemSection({ requestId, isExecuted, serviceName, duration }: PostMortemSectionProps) {
  const queryClient = useQueryClient()
  const [modalOpen, setModalOpen] = useState(false)

  const { data: existing, isLoading: checking } = useQuery<PostMortem>({
    queryKey: ['postmortem', requestId],
    queryFn: () => fetchPostMortem(requestId),
    retry: false,
  })

  const generateMutation = useMutation({
    mutationFn: () => generatePostMortem(requestId),
    onSuccess: (data) => queryClient.setQueryData(['postmortem', requestId], data),
  })

  // Zero-click auto-generation: fire when status is executed and no PM exists
  useEffect(() => {
    if (isExecuted && !existing && !generateMutation.isPending && !generateMutation.isError && !generateMutation.data) {
      generateMutation.mutate()
    }
  }, [isExecuted, existing, generateMutation])

  const pm: PostMortem | undefined = existing ?? generateMutation.data

  const downloadMarkdown = useCallback(() => {
    if (!pm) return
    const blob = new Blob([pm.markdown], { type: 'text/markdown' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href = url
    a.download = `postmortem-${requestId}.md`
    a.click()
    URL.revokeObjectURL(url)
  }, [pm, requestId])

  return (
    <Section
      title="Blameless Post-Mortem"
      headerRight={
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {!isExecuted && (
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.62rem', fontWeight: 700,
              letterSpacing: '0.1em', padding: '2px 7px', borderRadius: 2,
              background: 'rgba(251,191,36,0.1)', border: '1px solid rgba(251,191,36,0.3)',
              color: 'var(--c-yellow)', textTransform: 'uppercase',
            }}>
              PREVIEW
            </span>
          )}
          {pm && (
            <>
              <button onClick={() => setModalOpen(true)} className="btn-ghost" style={{ fontSize: '0.75rem', padding: '4px 10px' }}>
                👁 View Report
              </button>
              <button onClick={downloadMarkdown} className="btn-ghost" style={{ fontSize: '0.75rem', padding: '4px 10px' }}>
                ↓ Markdown
              </button>
            </>
          )}
        </div>
      }
    >
      <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.82rem', color: 'var(--c-text-muted)', marginBottom: 20 }}>
        AI-generated incident report with timeline, impact, and prevention recommendations.
      </div>

      {generateMutation.isPending && (
        <div style={{
          padding: '24px', borderRadius: 12, border: '1px dashed var(--c-border)',
          background: 'rgba(255,255,255,0.02)', textAlign: 'center',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12
        }}>
          <div className="animate-pulse-glow" style={{ width: 20, height: 20, borderRadius: '50%', border: '2px solid var(--c-signal)', borderTopColor: 'transparent', animation: 'spin 1s linear infinite' }} />
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-signal)', fontWeight: 700, letterSpacing: '0.05em' }}>
            DRAFTING BLAMELESS POST-MORTEM...
          </div>
        </div>
      )}

      {generateMutation.isError && (
        <AlertBanner ok={false} message={(generateMutation.error as Error).message} />
      )}

      {pm && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Executive Summary Header */}
          <div style={{ 
            display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12,
            padding: '16px', background: 'rgba(255,255,255,0.03)', 
            border: '1px solid var(--c-border)', borderRadius: 12
          }}>
            <div style={{ textAlign: 'center', borderRight: '1px solid var(--c-border)' }}>
              <div style={{ fontSize: '0.55rem', fontWeight: 800, color: 'var(--c-text-faint)', textTransform: 'uppercase', marginBottom: 4 }}>Service</div>
              <div style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--c-text)' }}>{serviceName}</div>
            </div>
            <div style={{ textAlign: 'center', borderRight: '1px solid var(--c-border)' }}>
              <div style={{ fontSize: '0.55rem', fontWeight: 800, color: 'var(--c-text-faint)', textTransform: 'uppercase', marginBottom: 4 }}>TTR (Resolution)</div>
              <div style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--c-green)' }}>{duration || '—'}</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.55rem', fontWeight: 800, color: 'var(--c-text-faint)', textTransform: 'uppercase', marginBottom: 4 }}>Learning Loop</div>
              <div style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--c-signal)' }}>CAPTURED</div>
            </div>
          </div>

          <div style={{ 
            background: 'var(--c-surface-2)', padding: '16px 20px', borderRadius: 12, 
            border: '1px solid var(--c-border)', maxHeight: 200, overflowY: 'hidden',
            position: 'relative'
          }}>
             <div className="pm-prose" style={{ opacity: 0.6, fontSize: '0.8rem' }}>
                <SemanticMarkdown>{pm.markdown.slice(0, 500) + '...'}</SemanticMarkdown>
             </div>
             <div style={{ 
                position: 'absolute', bottom: 0, left: 0, right: 0, height: 80,
                background: 'linear-gradient(to top, var(--c-surface-2), transparent)',
                display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
                paddingBottom: 16
             }}>
                <button onClick={() => setModalOpen(true)} className="btn-primary" style={{ fontSize: '0.72rem', padding: '6px 16px' }}>
                  Read Full Post-Mortem
                </button>
             </div>
          </div>
        </div>
      )}

      <Modal isOpen={modalOpen} onClose={() => setModalOpen(false)}>
        <div className="pm-prose">
          <SemanticMarkdown>{pm?.markdown || ''}</SemanticMarkdown>
        </div>
      </Modal>
    </Section>
  )
}
