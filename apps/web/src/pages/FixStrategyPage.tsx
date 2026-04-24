import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

async function fetchInvestigation(id: string) {
  const res = await fetch(`/api/investigations/${id}`)
  if (!res.ok) throw new Error(`API error ${res.status}`)
  return res.json()
}

export default function FixStrategyPage() {
  const { id } = useParams<{ id: string }>()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['investigation', id],
    queryFn: () => fetchInvestigation(id!),
    enabled: !!id,
  })

  const fixStrategy = data?.fix_strategy

  return (
    <main style={{ fontFamily: 'sans-serif', padding: '2rem' }}>
      <Link to={`/investigations/${id}`}>← Back to investigation</Link>
      <h1>Fix Strategy</h1>
      <p style={{ color: '#666' }}>Investigation ID: {id}</p>

      {isLoading && <p>Loading…</p>}
      {isError && <p>Could not load fix strategy.</p>}

      {data && !fixStrategy && (
        <p style={{ color: '#888' }}>Fix strategy not yet available for this investigation.</p>
      )}

      {fixStrategy && (
        <>
          <section>
            <h2>Summary</h2>
            <p>{fixStrategy.summary}</p>
          </section>

          <section>
            <h2>Justification</h2>
            <p>{fixStrategy.justification}</p>
          </section>

          {fixStrategy.actions?.length > 0 && (
            <section>
              <h2>Recommended Actions</h2>
              <p style={{ color: '#888', fontSize: '0.9rem' }}>
                All actions require human review before execution (V1).
              </p>
              <ol>
                {fixStrategy.actions.map((action: {
                  title: string
                  description: string
                  risk_level: string
                  estimated_impact: string
                }, i: number) => (
                  <li key={i} style={{ marginBottom: '1rem' }}>
                    <strong>{action.title}</strong>
                    {' '}
                    <span style={{
                      background: action.risk_level === 'high' ? '#ffe0e0'
                        : action.risk_level === 'medium' ? '#fff4e0' : '#e0ffe0',
                      padding: '0 6px',
                      borderRadius: '3px',
                      fontSize: '0.85rem',
                    }}>
                      {action.risk_level} risk
                    </span>
                    <p style={{ margin: '4px 0' }}>{action.description}</p>
                    <p style={{ color: '#666', fontSize: '0.9rem' }}>
                      Impact: {action.estimated_impact}
                    </p>
                  </li>
                ))}
              </ol>
            </section>
          )}
        </>
      )}
    </main>
  )
}
