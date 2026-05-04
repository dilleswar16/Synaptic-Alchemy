import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchInvestigations, type InvestigationSummary } from '../api/client'
import { useInvestigationStream } from '../hooks/useInvestigationStream'
import StreamingProgress from '../components/StreamingProgress'
import Layout from '../components/Layout'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtTs(iso: string) {
  try { return new Date(iso).toISOString().substring(11, 19) + 'Z' } catch { return '—' }
}

const STATUS_CLS: Record<string, string> = {
  pending: 'badge-pending', approved: 'badge-approved',
  rejected: 'badge-rejected', executed: 'badge-executed',
}

// ── Form field ────────────────────────────────────────────────────────────────

function Field({
  label,
  value,
  onChange,
  placeholder,
  disabled,
  required,
}: {
  label: string; value: string; onChange: (v: string) => void
  placeholder?: string; disabled?: boolean; required?: boolean
}) {
  return (
    <div>
      <label style={{
        display: 'block', marginBottom: 6,
        fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 700,
        letterSpacing: '0.14em', textTransform: 'uppercase',
        color: 'var(--c-text-muted)',
      }}>
        {label}{required && <span style={{ color: 'var(--c-signal)', marginLeft: 4 }}>*</span>}
      </label>
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        style={{ width: '100%', boxSizing: 'border-box', padding: '9px 12px' }}
      />
    </div>
  )
}

// ── Start investigation form ──────────────────────────────────────────────────

function StartInvestigationForm() {
  const [service, setService] = useState('')
  const [environment, setEnvironment] = useState('production')
  const [description, setDescription] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const { stages, streamText, isStreaming, isComplete, error, requestId, start, reset } =
    useInvestigationStream()

  const handleComplete = () => {
    if (requestId) queryClient.invalidateQueries({ queryKey: ['investigations'] })
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setFormError(null)
    if (!service.trim()) { setFormError('Service name is required.'); return }
    start({ service_name: service.trim(), environment, description })
  }

  const showProgress = isStreaming || isComplete || stages.length > 0

  return (
    <div className="panel-signal animate-fade-up" style={{ marginTop: 32 }}>
      {/* Header */}
      <div style={{
        padding: '14px 20px',
        borderBottom: '1px solid var(--c-border)',
        display: 'flex', alignItems: 'center', gap: 10,
        background: 'rgba(249,115,22,0.04)',
      }}>
        <div style={{
          width: 8, height: 8, borderRadius: '50%',
          background: isStreaming ? 'var(--c-signal)' : 'var(--c-text-faint)',
        }} className={isStreaming ? 'animate-pulse-glow' : ''} />
        <span style={{
          fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.8rem',
          letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--c-text)',
        }}>
          {isStreaming ? 'Investigation Running' : 'New Investigation'}
        </span>
      </div>

      {/* Form */}
      <div style={{ padding: '20px 24px' }}>
        <form onSubmit={handleSubmit}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
            <Field label="Service Name" value={service} onChange={setService} placeholder="order-service" disabled={isStreaming} required />
            <Field label="Environment"  value={environment} onChange={setEnvironment} placeholder="production" disabled={isStreaming} />
          </div>
          <div style={{ marginBottom: 16 }}>
            <Field label="Description" value={description} onChange={setDescription} placeholder="Elevated 5xx errors on /checkout endpoint…" disabled={isStreaming} />
          </div>

          {formError && (
            <div style={{
              marginBottom: 12, padding: '8px 12px',
              background: 'var(--c-red-bg)', border: '1px solid var(--c-red-border)',
              borderRadius: 2, fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--c-red)',
            }}>
              {formError}
            </div>
          )}

          <button type="submit" disabled={isStreaming} className="btn-primary">
            {isStreaming ? 'Running Investigation…' : '▶ Start Investigation'}
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
      </div>
    </div>
  )
}

// ── Investigation list ────────────────────────────────────────────────────────

function InvestigationList({ items }: { items: (InvestigationSummary & { approval_status?: string })[] }) {
  if (items.length === 0) {
    return (
      <div style={{ padding: '40px 20px', textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--c-text-faint)' }}>
        No investigations yet — use the form below to run one.
      </div>
    )
  }

  return (
    <>
      {/* Table header */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '80px 1fr 120px 110px 140px 20px',
        gap: 16,
        padding: '8px 14px',
        borderBottom: '1px solid var(--c-border-hi)',
        background: 'var(--c-surface-2)',
      }}>
        {['TIME', 'SERVICE', 'ENVIRONMENT', 'STATUS', 'COMPLETED', ''].map((h, i) => (
          <span key={i} style={{
            fontFamily: 'var(--font-display)', fontSize: '0.6rem', fontWeight: 700,
            letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--c-text-muted)',
          }}>{h}</span>
        ))}
      </div>

      {items.map((inv, i) => {
        const status = inv.approval_status ?? 'pending'
        const ts = new Date(inv.completed_at ?? inv.created_at)
        return (
          <Link
            key={inv.request_id}
            to={`/investigations/${inv.request_id}`}
            className="log-row animate-fade-up"
            style={{
              gridTemplateColumns: '80px 1fr 120px 110px 140px 20px',
              animationDelay: `${i * 25}ms`,
            }}
          >
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.67rem', color: 'var(--c-text-faint)' }}>
              {fmtTs(inv.completed_at ?? inv.created_at)}
            </span>
            <div>
              <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.88rem', color: 'var(--c-text)' }}>
                {inv.service_name}
              </span>
            </div>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.67rem', color: 'var(--c-text-dim)' }}>
              {inv.environment}
            </span>
            <span className={`badge ${STATUS_CLS[status] ?? 'badge-pending'}`}>{status}</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.67rem', color: 'var(--c-text-faint)', whiteSpace: 'nowrap' }}>
              {ts.toLocaleString()}
            </span>
            <span className="log-arrow" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--c-text-faint)', textAlign: 'right', transition: 'color 0.15s' }}>
              →
            </span>
          </Link>
        )
      })}
    </>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function InvestigationsPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['investigations'],
    queryFn: fetchInvestigations,
    refetchInterval: 30_000,
  })

  return (
    <Layout>
      {/* Header */}
      <div className="animate-fade-up" style={{ marginBottom: 28 }}>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 700, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--c-signal)', marginBottom: 4 }}>
          Investigation Log
        </div>
        <h1 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: '2rem', fontWeight: 900, letterSpacing: '0.04em', color: 'var(--c-text)' }}>
          INVESTIGATIONS
        </h1>
      </div>

      {/* Investigation table */}
      <div className="panel animate-fade-up-1" style={{ overflow: 'hidden', marginBottom: 8 }}>
        {isLoading && (
          <div style={{ padding: '40px 20px', fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--c-text-faint)', textAlign: 'center' }}>
            Loading…
          </div>
        )}
        {isError && (
          <div style={{ padding: '40px 20px', fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--c-red)', textAlign: 'center' }}>
            ✗ Could not reach Corvin API.
          </div>
        )}
        {data && <InvestigationList items={data as (InvestigationSummary & { approval_status?: string })[]} />}
      </div>

      {data && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-faint)', marginBottom: 4, textAlign: 'right' }}>
          {data.length} record{data.length !== 1 ? 's' : ''}
        </div>
      )}

      {/* New investigation form */}
      <StartInvestigationForm />
    </Layout>
  )
}


// ── Start investigation form ──────────────────────────────────────────────────

