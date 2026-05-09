/**
 * PostMortemSection — generate, view, and download a blameless post-mortem.
 */
import { useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { generatePostMortem, fetchPostMortem, type PostMortem } from '../../api/client'
import { Section, AlertBanner } from '../Section'

interface PostMortemSectionProps {
  requestId: string
  isExecuted: boolean
}

export function PostMortemSection({ requestId, isExecuted }: PostMortemSectionProps) {
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
            <button onClick={downloadMarkdown} className="btn-ghost" style={{ fontSize: '0.75rem', padding: '4px 10px' }}>
              ↓ .md
            </button>
          )}
          {!pm && !checking && (
            <button
              onClick={() => generateMutation.mutate()}
              disabled={generateMutation.isPending}
              className="btn-primary"
              style={{ fontSize: '0.78rem', padding: '5px 12px' }}
            >
              {generateMutation.isPending ? 'Generating…' : '▶ Generate'}
            </button>
          )}
          {checking && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-text-faint)' }}>
              Checking…
            </span>
          )}
        </div>
      }
    >
      <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.82rem', color: 'var(--c-text-muted)', marginBottom: pm ? 18 : 0 }}>
        AI-generated incident report with timeline, impact, and prevention recommendations.
      </div>

      {generateMutation.isError && (
        <AlertBanner ok={false} message={(generateMutation.error as Error).message} />
      )}

      {pm && (
        <div className="pm-prose" style={{ borderTop: '1px solid var(--c-border)', paddingTop: 18, marginTop: 8 }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{pm.markdown}</ReactMarkdown>
        </div>
      )}
    </Section>
  )
}
