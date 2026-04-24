import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchInvestigations,
  startInvestigation,
  type InvestigationSummary,
} from '../api/client'

// ── Start investigation form ──────────────────────────────────────────────────

function StartInvestigationForm() {
  const [service, setService] = useState('')
  const [environment, setEnvironment] = useState('production')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: startInvestigation,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['investigations'] })
      navigate(`/investigations/${data.request_id}`)
    },
    onError: (err: Error) => {
      setError(err.message)
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!service.trim()) {
      setError('Service name is required.')
      return
    }
    mutation.mutate({ service_name: service.trim(), environment, description })
  }

  return (
    <section style={{ marginTop: '2rem', padding: '1rem', border: '1px solid #ddd', borderRadius: '6px' }}>
      <h2>Start New Investigation</h2>
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '0.75rem' }}>
          <label style={{ display: 'block', marginBottom: '0.25rem' }}>
            Service name <span style={{ color: 'red' }}>*</span>
          </label>
          <input
            value={service}
            onChange={(e) => setService(e.target.value)}
            placeholder="e.g. order-service"
            style={{ width: '100%', padding: '0.4rem', boxSizing: 'border-box' }}
          />
        </div>
        <div style={{ marginBottom: '0.75rem' }}>
          <label style={{ display: 'block', marginBottom: '0.25rem' }}>Environment</label>
          <input
            value={environment}
            onChange={(e) => setEnvironment(e.target.value)}
            placeholder="e.g. production"
            style={{ width: '100%', padding: '0.4rem', boxSizing: 'border-box' }}
          />
        </div>
        <div style={{ marginBottom: '0.75rem' }}>
          <label style={{ display: 'block', marginBottom: '0.25rem' }}>Description</label>
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="e.g. Elevated 5xx errors on /orders endpoint"
            style={{ width: '100%', padding: '0.4rem', boxSizing: 'border-box' }}
          />
        </div>
        {error && <p style={{ color: 'red', margin: '0.5rem 0' }}>{error}</p>}
        <button
          type="submit"
          disabled={mutation.isPending}
          style={{ padding: '0.5rem 1.2rem', cursor: 'pointer' }}
        >
          {mutation.isPending ? 'Running investigation…' : 'Start Investigation'}
        </button>
      </form>
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
