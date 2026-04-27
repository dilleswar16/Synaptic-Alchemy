import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchInvestigations, type InvestigationSummary } from '../api/client'
import { useInvestigationStream } from '../hooks/useInvestigationStream'
import StreamingProgress from '../components/StreamingProgress'

// ── Start investigation form ──────────────────────────────────────────────────

function StartInvestigationForm() {
  const [service, setService] = useState('')
  const [environment, setEnvironment] = useState('production')
  const [description, setDescription] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const { stages, streamText, isStreaming, isComplete, error, requestId, start, reset } =
    useInvestigationStream()

  // When the stream completes successfully, refresh the investigations list.
  const handleComplete = () => {
    if (requestId) {
      queryClient.invalidateQueries({ queryKey: ['investigations'] })
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setFormError(null)
    if (!service.trim()) {
      setFormError('Service name is required.')
      return
    }
    start({ service_name: service.trim(), environment, description })
  }

  const showProgress = isStreaming || isComplete || stages.length > 0

  return (
    <section style={{ marginTop: '2rem', padding: '1rem 1.5rem', border: '1px solid #ddd', borderRadius: '6px' }}>
      <h2 style={{ marginTop: 0 }}>Start New Investigation</h2>

      <form onSubmit={handleSubmit}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '0.75rem' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.25rem', fontSize: '0.9rem', fontWeight: 500 }}>
              Service name <span style={{ color: 'red' }}>*</span>
            </label>
            <input
              value={service}
              onChange={(e) => setService(e.target.value)}
              placeholder="e.g. order-service"
              disabled={isStreaming}
              style={{ width: '100%', padding: '0.4rem', boxSizing: 'border-box', borderRadius: '4px', border: '1px solid #d9d9d9' }}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.25rem', fontSize: '0.9rem', fontWeight: 500 }}>
              Environment
            </label>
            <input
              value={environment}
              onChange={(e) => setEnvironment(e.target.value)}
              placeholder="e.g. production"
              disabled={isStreaming}
              style={{ width: '100%', padding: '0.4rem', boxSizing: 'border-box', borderRadius: '4px', border: '1px solid #d9d9d9' }}
            />
          </div>
        </div>
        <div style={{ marginBottom: '0.75rem' }}>
          <label style={{ display: 'block', marginBottom: '0.25rem', fontSize: '0.9rem', fontWeight: 500 }}>
            Description
          </label>
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="e.g. Elevated 5xx errors on /orders endpoint"
            disabled={isStreaming}
            style={{ width: '100%', padding: '0.4rem', boxSizing: 'border-box', borderRadius: '4px', border: '1px solid #d9d9d9' }}
          />
        </div>

        {formError && (
          <p style={{ color: '#cf1322', margin: '0 0 0.5rem', fontSize: '0.9rem' }}>{formError}</p>
        )}

        <button
          type="submit"
          disabled={isStreaming}
          style={{
            padding: '8px 20px',
            background: isStreaming ? '#b7b7b7' : '#1677ff',
            color: '#fff',
            border: 'none',
            borderRadius: '6px',
            cursor: isStreaming ? 'not-allowed' : 'pointer',
            fontWeight: 600,
          }}
        >
          {isStreaming ? '⏳ Investigating…' : '🔍 Start Investigation'}
        </button>
      </form>

      {showProgress && (
        <StreamingProgress
          stages={stages}
          streamText={streamText}
          isStreaming={isStreaming}
          isComplete={isComplete}
          error={error}
          requestId={requestId}
          onReset={() => { reset(); handleComplete() }}
        />
      )}
    </section>
  )
}

// ── Investigation list ────────────────────────────────────────────────────────

function InvestigationList({ items }: { items: InvestigationSummary[] }) {
  if (items.length === 0) {
    return <p style={{ color: '#888' }}>No investigations yet. Use the form above to start one.</p>
  }
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '1rem' }}>
      <thead>
        <tr style={{ background: '#f4f4f4', textAlign: 'left' }}>
          <th style={{ padding: '0.5rem' }}>Service</th>
          <th style={{ padding: '0.5rem' }}>Environment</th>
          <th style={{ padding: '0.5rem' }}>Trigger</th>
          <th style={{ padding: '0.5rem' }}>Completed</th>
          <th style={{ padding: '0.5rem' }}>Actions</th>
        </tr>
      </thead>
      <tbody>
        {items.map((inv) => (
          <tr key={inv.request_id} style={{ borderBottom: '1px solid #eee' }}>
            <td style={{ padding: '0.5rem' }}>{inv.service_name}</td>
            <td style={{ padding: '0.5rem' }}>{inv.environment}</td>
            <td style={{ padding: '0.5rem' }}>{inv.trigger_source}</td>
            <td style={{ padding: '0.5rem', fontSize: '0.85rem', color: '#666' }}>
              {new Date(inv.completed_at).toLocaleString()}
            </td>
            <td style={{ padding: '0.5rem' }}>
              <Link to={`/investigations/${inv.request_id}`}>View →</Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function InvestigationsPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['investigations'],
    queryFn: fetchInvestigations,
  })

  return (
    <main style={{ fontFamily: 'sans-serif', padding: '2rem', maxWidth: '900px', margin: '0 auto' }}>
      <h1>Corvin – Investigations</h1>

      <section>
        <h2>Recent Investigations</h2>
        {isLoading && <p>Loading…</p>}
        {isError && <p style={{ color: 'red' }}>Could not reach Corvin API.</p>}
        {data && <InvestigationList items={data} />}
      </section>

      <StartInvestigationForm />
    </main>
  )
}
