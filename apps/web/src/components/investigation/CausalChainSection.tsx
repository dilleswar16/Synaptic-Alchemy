import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchCausalChain, type CausalChain } from '../../api/client'

interface Props {
  requestId: string
}

const CATEGORY_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  trigger: { bg: 'var(--c-error-bg)', border: 'var(--c-error-border)', text: 'var(--c-red)' },
  failure: { bg: 'var(--c-warning-bg)', border: 'var(--c-warning-border)', text: 'var(--c-amber)' },
  cascade: { bg: 'var(--c-signal-light)', border: 'var(--c-signal-dim)', text: 'var(--c-signal)' },
  impact: { bg: 'var(--c-info-bg)', border: 'var(--c-info-border)', text: 'var(--c-info)' },
}

const CATEGORY_ICONS: Record<string, string> = {
  trigger: '⚡',
  failure: '🔥',
  cascade: '🔗',
  impact: '💥',
}

export function CausalChainSection({ requestId }: Props) {
  const [expanded, setExpanded] = useState(false)
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['causal-chain', requestId],
    queryFn: () => fetchCausalChain(requestId),
    enabled: expanded,
    staleTime: 300_000,
    retry: false,
  })

  return (
    <section style={{ marginTop: 24 }}>
      <div className="panel" style={{ overflow: 'hidden' }}>
        <div style={{
          padding: '12px 20px', borderBottom: '1px solid var(--c-border)',
          background: 'var(--c-surface-2)', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span style={{ fontWeight: 600, fontSize: '0.8125rem', letterSpacing: '0.02em', color: 'var(--c-text-dim)' }}>
            Causal Reasoning Chain
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', padding: '2px 7px', borderRadius: 4, background: 'var(--c-signal-glow)', color: 'var(--c-signal)', fontWeight: 700 }}>
            AI
          </span>
        </div>
        <div style={{ padding: '16px 20px' }}>
          {!expanded && (
            <button
              onClick={() => setExpanded(true)}
              style={{
                background: 'var(--c-signal-glow)', border: '1px solid var(--c-signal-dim)',
                color: 'var(--c-signal)', padding: '8px 16px', borderRadius: 6,
                cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: '0.75rem',
                fontWeight: 600,
              }}
            >
              ⚡ Generate Causal Chain
            </button>
          )}

      {isLoading && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '16px 0' }}>
          <span style={{
            width: 10, height: 10, borderRadius: '50%',
            border: '1.5px solid var(--c-signal)', borderTopColor: 'transparent',
            display: 'inline-block', animation: 'skeleton-sweep 0.7s linear infinite',
          }} />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-signal)' }}>
            Analyzing causal relationships…
          </span>
        </div>
      )}

      {error && (
        <div style={{ color: 'var(--c-red)', fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
          Failed to generate causal chain.{' '}
          <button onClick={() => refetch()} style={{ color: 'var(--c-signal)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>
            Retry
          </button>
        </div>
      )}

      {data && <CausalChainDiagram chain={data} />}
        </div>
      </div>
    </section>
  )
}

function CausalChainDiagram({ chain }: { chain: CausalChain }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Summary */}
      {chain.summary && (
        <p style={{
          margin: 0, fontFamily: 'var(--font-body)', fontSize: '0.82rem',
          color: 'var(--c-text-dim)', lineHeight: 1.6, fontStyle: 'italic',
        }}>
          {chain.summary}
        </p>
      )}

      {/* Flow visualization */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 0, position: 'relative' }}>
        {chain.nodes.map((node, i) => {
          const colors = CATEGORY_COLORS[node.category] || CATEGORY_COLORS.cascade
          const icon = CATEGORY_ICONS[node.category] || '●'
          const edgeToNext = chain.edges.find(e => e.from_id === node.id)

          return (
            <div key={node.id}>
              {/* Node */}
              <div style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '10px 14px', borderRadius: 8,
                background: colors.bg, border: `1px solid ${colors.border}`,
              }}>
                <span style={{ fontSize: '1rem', flexShrink: 0 }}>{icon}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.6rem', fontWeight: 700,
                    textTransform: 'uppercase', letterSpacing: '0.08em', color: colors.text,
                    display: 'block', marginBottom: 2,
                  }}>
                    {node.category}
                  </span>
                  <span style={{
                    fontFamily: 'var(--font-body)', fontSize: '0.8rem',
                    color: 'var(--c-text)', fontWeight: 500,
                  }}>
                    {node.label}
                  </span>
                </div>
              </div>

              {/* Edge arrow + label */}
              {edgeToNext && i < chain.nodes.length - 1 && (
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  paddingLeft: 20, height: 28,
                }}>
                  <div style={{
                    width: 1, height: '100%', background: 'var(--c-border-hi)',
                  }} />
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
                    color: 'var(--c-text-faint)', fontStyle: 'italic',
                  }}>
                    ↓ {edgeToNext.label || 'caused'}
                  </span>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 8 }}>
        {Object.entries(CATEGORY_COLORS).map(([cat, colors]) => (
          <span key={cat} style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            fontFamily: 'var(--font-mono)', fontSize: '0.6rem',
            padding: '2px 8px', borderRadius: 4,
            background: colors.bg, border: `1px solid ${colors.border}`, color: colors.text,
          }}>
            {CATEGORY_ICONS[cat]} {cat}
          </span>
        ))}
      </div>
    </div>
  )
}
