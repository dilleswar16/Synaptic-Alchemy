/**
 * PostMortemSection — generate, view, and download a blameless post-mortem.
 */
import { useCallback, useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { SemanticMarkdown } from '../SemanticMarkdown'
import { generatePostMortem, fetchPostMortem, type PostMortem } from '../../api/client'
import { Section, AlertBanner } from '../Section'
import { Modal } from '../Modal'
import { exportPostMortemPdf } from '../../utils/postmortemPdf'

interface PostMortemSectionProps {
  requestId: string
  isExecuted: boolean
  hasRca?: boolean
  serviceName: string
  duration?: string
}

export function PostMortemSection({ requestId, isExecuted, hasRca, serviceName, duration }: PostMortemSectionProps) {
  const queryClient = useQueryClient()
  const [modalOpen, setModalOpen] = useState(false)
  const [pdfLoading, setPdfLoading] = useState(false)

  const { data: existing } = useQuery<PostMortem>({
    queryKey: ['postmortem', requestId],
    queryFn: () => fetchPostMortem(requestId),
    retry: false,
  })

  const generateMutation = useMutation({
    mutationFn: () => generatePostMortem(requestId),
    onSuccess: (data) => queryClient.setQueryData(['postmortem', requestId], data),
  })

  // Guard: prevent double-call from React StrictMode double-effect invocation
  const autoGenFiredRef = useRef(false)

  // Auto-generation: fire when RCA is complete (executed or just has RCA) and no PM exists yet
  const shouldAutoGenerate = (isExecuted || hasRca) && !existing && !generateMutation.isPending && !generateMutation.isError && !generateMutation.data
  useEffect(() => {
    if (shouldAutoGenerate && !autoGenFiredRef.current) {
      autoGenFiredRef.current = true
      generateMutation.mutate()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldAutoGenerate])

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

  const downloadPdf = useCallback(async () => {
    if (!pm || pdfLoading) return
    setPdfLoading(true)
    try {
      await exportPostMortemPdf(pm)
    } finally {
      setPdfLoading(false)
    }
  }, [pm, pdfLoading])

  return (
    <Section
      title="Blameless Post-Mortem"
      headerRight={
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {!isExecuted && (
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.7rem', fontWeight: 700,
              letterSpacing: '0.1em', padding: '2px 7px', borderRadius: 2,
              background: 'var(--c-warning-bg)', border: '1px solid var(--c-warning-border)',
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
              <button onClick={downloadPdf} disabled={pdfLoading} className="btn-ghost" style={{ fontSize: '0.75rem', padding: '4px 10px', color: pdfLoading ? 'var(--c-text-faint)' : 'var(--c-signal)', opacity: pdfLoading ? 0.6 : 1 }}>
                {pdfLoading ? '⏳ Generating…' : '📄 Export PDF'}
              </button>
              <button
                onClick={() => { autoGenFiredRef.current = false; generateMutation.mutate() }}
                className="btn-ghost"
                style={{ fontSize: '0.75rem', padding: '4px 10px', color: 'var(--c-text-muted)' }}
                title="Re-generate post-mortem"
              >
                ↺ Regenerate
              </button>
            </>
          )}
        </div>
      }
    >
      <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.82rem', color: 'var(--c-text-muted)', marginBottom: 20 }}>
        AI-generated incident report with timeline, impact, and prevention recommendations.
      </div>

      {generateMutation.isPending && !pm && (
        <div style={{
          padding: '24px', borderRadius: 12, border: '1px dashed var(--c-border)',
          background: 'var(--c-surface-2)', textAlign: 'center',
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

      {/* Fallback: RCA exists, not generating, no PM yet — manual trigger */}
      {!pm && !generateMutation.isPending && !generateMutation.isError && (hasRca || isExecuted) && (
        <div style={{
          padding: '28px', borderRadius: 12, border: '1px dashed var(--c-border)',
          background: 'var(--c-surface-2)', textAlign: 'center',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14,
        }}>
          <div style={{ fontSize: '2rem' }}>📄</div>
          <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.82rem', color: 'var(--c-text-muted)' }}>
            No post-mortem generated yet.
          </div>
          <button
            onClick={() => generateMutation.mutate()}
            className="btn-primary"
            style={{ fontSize: '0.75rem', padding: '7px 18px' }}
          >
            Generate Post-Mortem
          </button>
        </div>
      )}

      {pm && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Executive Summary Header */}
          <div style={{ 
            display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12,
            padding: '16px', background: 'var(--c-surface-2)', 
            border: '1px solid var(--c-border)', borderRadius: 12
          }}>
            <div style={{ textAlign: 'center', borderRight: '1px solid var(--c-border)' }}>
              <div style={{ fontSize: '0.68rem', fontWeight: 800, color: 'var(--c-text-faint)', textTransform: 'uppercase', marginBottom: 4 }}>Service</div>
              <div style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--c-text)' }}>{serviceName}</div>
            </div>
            <div style={{ textAlign: 'center', borderRight: '1px solid var(--c-border)' }}>
              <div style={{ fontSize: '0.68rem', fontWeight: 800, color: 'var(--c-text-faint)', textTransform: 'uppercase', marginBottom: 4 }}>TTR (Resolution)</div>
              <div style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--c-green)' }}>{duration || '—'}</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.68rem', fontWeight: 800, color: 'var(--c-text-faint)', textTransform: 'uppercase', marginBottom: 4 }}>Learning Loop</div>
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
