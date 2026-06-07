import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchMultiAgentTrace, startMultiAgentInvestigation, type MultiAgentTrace, type MultiAgentResult } from '../../api/client'

const AGENT_COLORS: Record<string, string> = {
  orchestrator: '#6366f1',
  evidence_collector: '#10b981',
  rca_analyst: '#f59e0b',
  fix_strategist: '#ef4444',
}

const AGENT_LABELS: Record<string, string> = {
  orchestrator: 'Orchestrator',
  evidence_collector: 'Evidence Collector',
  rca_analyst: 'RCA Analyst',
  fix_strategist: 'Fix Strategist',
}

export function MultiAgentSection({ requestId }: { requestId: string }) {
  const { data: trace, isLoading, refetch } = useQuery({
    queryKey: ['multi-agent-trace', requestId],
    queryFn: () => fetchMultiAgentTrace(requestId),
    enabled: false,
  })

  return (
    <section style={{ marginTop: '1.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>Multi-Agent Trace</h3>
        <button
          onClick={() => refetch()}
          disabled={isLoading}
          style={{
            padding: '0.25rem 0.75rem',
            fontSize: '0.8rem',
            borderRadius: '4px',
            border: '1px solid #6366f1',
            background: isLoading ? '#e0e7ff' : '#fff',
            color: '#6366f1',
            cursor: isLoading ? 'wait' : 'pointer',
          }}
        >
          {isLoading ? 'Running…' : 'Run Multi-Agent'}
        </button>
      </div>

      {trace && <MultiAgentTraceView trace={trace} />}
    </section>
  )
}

function MultiAgentTraceView({ trace }: { trace: MultiAgentTrace }) {
  return (
    <div style={{ background: '#f8fafc', borderRadius: '8px', padding: '1rem', border: '1px solid #e2e8f0' }}>
      <div style={{ display: 'flex', gap: '1.5rem', marginBottom: '1rem', fontSize: '0.8rem', color: '#64748b' }}>
        <span>Turns: <strong>{trace.turn_count}</strong></span>
        <span>Elapsed: <strong>{trace.total_elapsed_ms.toFixed(0)}ms</strong></span>
        <span>Signal: <strong style={{ color: trace.terminal_signal ? '#10b981' : '#f59e0b' }}>
          {trace.terminal_signal ?? 'incomplete'}
        </strong></span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {trace.turns.map((turn) => (
          <div
            key={turn.turn}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              padding: '0.5rem 0.75rem',
              borderRadius: '6px',
              background: '#fff',
              border: `1px solid ${AGENT_COLORS[turn.agent] ?? '#cbd5e1'}`,
              borderLeftWidth: '3px',
            }}
          >
            <span style={{
              fontSize: '0.7rem',
              fontWeight: 700,
              color: AGENT_COLORS[turn.agent] ?? '#475569',
              minWidth: '120px',
            }}>
              {AGENT_LABELS[turn.agent] ?? turn.agent}
            </span>
            <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
              {turn.elapsed_ms.toFixed(0)}ms
            </span>
            <span style={{
              fontSize: '0.7rem',
              padding: '0.1rem 0.4rem',
              borderRadius: '3px',
              background: turn.status === 'error' ? '#fee2e2' : '#dcfce7',
              color: turn.status === 'error' ? '#dc2626' : '#16a34a',
            }}>
              {turn.status}
            </span>
            {turn.error && (
              <span style={{ fontSize: '0.7rem', color: '#dc2626' }}>{turn.error}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Standalone launcher for new multi-agent investigations ──

export function MultiAgentLauncher() {
  const [form, setForm] = useState({ service_name: '', description: '', environment: '', priority: 'P2' })
  const [result, setResult] = useState<MultiAgentResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.service_name || !form.description) return
    setLoading(true)
    setError(null)
    try {
      const res = await startMultiAgentInvestigation(form)
      setResult(res)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Multi-agent investigation failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ padding: '1rem' }}>
      <h3 style={{ margin: '0 0 1rem', fontSize: '1rem' }}>Launch Multi-Agent Investigation</h3>
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxWidth: '400px' }}>
        <input
          placeholder="Service name"
          value={form.service_name}
          onChange={(e) => setForm(f => ({ ...f, service_name: e.target.value }))}
          style={{ padding: '0.4rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
        />
        <input
          placeholder="Description of the issue"
          value={form.description}
          onChange={(e) => setForm(f => ({ ...f, description: e.target.value }))}
          style={{ padding: '0.4rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
        />
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <select
            value={form.environment}
            onChange={(e) => setForm(f => ({ ...f, environment: e.target.value }))}
            style={{ padding: '0.4rem', borderRadius: '4px', border: '1px solid #cbd5e1', flex: 1 }}
          >
            <option value="prod">prod</option>
            <option value="staging">staging</option>
            <option value="dev">dev</option>
          </select>
          <select
            value={form.priority}
            onChange={(e) => setForm(f => ({ ...f, priority: e.target.value }))}
            style={{ padding: '0.4rem', borderRadius: '4px', border: '1px solid #cbd5e1', flex: 1 }}
          >
            <option value="P1">P1</option>
            <option value="P2">P2</option>
            <option value="P3">P3</option>
          </select>
        </div>
        <button
          type="submit"
          disabled={loading}
          style={{
            padding: '0.5rem',
            borderRadius: '4px',
            border: 'none',
            background: '#6366f1',
            color: '#fff',
            cursor: loading ? 'wait' : 'pointer',
          }}
        >
          {loading ? 'Running agents…' : 'Start Multi-Agent Investigation'}
        </button>
      </form>

      {error && <p style={{ color: '#dc2626', marginTop: '0.5rem', fontSize: '0.8rem' }}>{error}</p>}

      {result && (
        <div style={{ marginTop: '1rem' }}>
          <p style={{ fontSize: '0.8rem', color: '#475569' }}>
            ✓ Completed — Confidence: <strong>{result.confidence}</strong>
          </p>
          <p style={{ fontSize: '0.8rem', color: '#1e293b' }}>{result.root_cause}</p>
          <MultiAgentTraceView trace={result.trace} />
        </div>
      )}
    </div>
  )
}
