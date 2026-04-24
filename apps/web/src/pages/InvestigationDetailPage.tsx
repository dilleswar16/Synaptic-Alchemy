import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

async function fetchInvestigation(id: string) {
  const res = await fetch(`/api/investigations/${id}`)
  if (!res.ok) throw new Error(`API error ${res.status}`)
  return res.json()
}

export default function InvestigationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['investigation', id],
    queryFn: () => fetchInvestigation(id!),
    enabled: !!id,
  })

  return (
    <main style={{ fontFamily: 'sans-serif', padding: '2rem' }}>
      <Link to="/">← Back to investigations</Link>
      <h1>Investigation Detail</h1>
      <p style={{ color: '#666' }}>ID: {id}</p>

      {isLoading && <p>Loading…</p>}
      {isError && <p>Could not load investigation.</p>}

      {data && (
        <>
          <section>
            <h2>Request</h2>
            <pre style={{ background: '#f4f4f4', padding: '1rem' }}>
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
        </>
      )}
    </main>
  )
}
