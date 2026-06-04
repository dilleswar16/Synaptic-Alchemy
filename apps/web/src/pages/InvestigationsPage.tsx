import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchInvestigations, type InvestigationSummary } from '../api/client'
import { useInvestigationStream, type StreamParams } from '../hooks/useInvestigationStream'
import { useServiceNames, useApplicationPresets, useDefaultEnvironment, useEnvironmentOptions } from '../hooks/useApplicationData'
import StreamingProgress from '../components/StreamingProgress'
import Layout from '../components/Layout'
import { timeAgo, fmtTs } from '../utils/time'
import { STATUS_CLS } from '../components/StatusBadge'
import SimilarityNetworkGraph from '../components/SimilarityNetworkGraph'

// ── Form fields ───────────────────────────────────────────────────────────────

type DropdownOption = { value: string; label: string; disabled?: boolean; note?: string }

function SelectField({
  label,
  value,
  onChange,
  options,
  disabled,
  required,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: DropdownOption[]
  disabled?: boolean
  required?: boolean
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const selected = options.find(o => o.value === value)

  // Close on outside click or Escape
  useEffect(() => {
    if (!open) return
    function handle(e: MouseEvent | KeyboardEvent) {
      if (e instanceof KeyboardEvent) {
        if (e.key === 'Escape') setOpen(false)
        return
      }
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handle)
    document.addEventListener('keydown', handle)
    return () => {
      document.removeEventListener('mousedown', handle)
      document.removeEventListener('keydown', handle)
    }
  }, [open])

  return (
    <div ref={rootRef} style={{ position: 'relative' }}>
      <label style={{
        display: 'block', marginBottom: 6,
        fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 700,
        letterSpacing: '0.14em', textTransform: 'uppercase',
        color: 'var(--c-text-muted)',
      }}>
        {label}{required && <span style={{ color: 'var(--c-signal)', marginLeft: 4 }}>*</span>}
      </label>

      {/* Trigger */}
      <button
        type="button"
        onClick={() => !disabled && setOpen(o => !o)}
        className="corvin-interactive"
        style={{
          width: '100%', boxSizing: 'border-box',
          padding: '9px 30px 9px 12px',
          background: open ? 'var(--c-surface-2)' : 'var(--c-surface)',
          border: `1px solid ${open ? 'var(--c-border-glow)' : 'var(--c-border)'}`,
          borderRadius: open ? '6px 6px 0 0' : 6,
          color: disabled ? 'var(--c-text-faint)' : 'var(--c-text)',
          fontFamily: 'var(--font-mono)', fontSize: '0.82rem',
          textAlign: 'left', cursor: disabled ? 'not-allowed' : 'pointer',
          transition: 'border-color 0.15s, background 0.1s',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}
      >
        <span>
          {selected
            ? <><span style={{ color: 'var(--c-text)' }}>{selected.label}</span>{selected.note && <span style={{ color: 'var(--c-text-faint)', marginLeft: 8, fontSize: '0.72rem' }}>— {selected.note}</span>}</>
            : <span style={{ color: 'var(--c-text-faint)' }}>Select…</span>
          }
        </span>
        <span style={{
          color: open ? 'var(--c-signal)' : 'var(--c-text-faint)',
          fontSize: '0.65rem', transition: 'transform 0.15s, color 0.15s',
          transform: open ? 'rotate(180deg)' : 'none', flexShrink: 0,
        }}>▾</span>
      </button>

      {/* Dropdown panel */}
      {open && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 200,
          background: 'var(--c-surface-3)',
          border: '1px solid var(--c-border-glow)',
          borderTop: '1px solid var(--c-border)',
          borderRadius: '0 0 6px 6px',
          boxShadow: '0 12px 40px rgba(0,0,0,0.4)',
          overflow: 'hidden',
        }}>
          {options.map((opt, i) => {
            const isSelected = opt.value === value
            const isDisabled = opt.disabled
            return (
              <div
                key={opt.value}
                onClick={() => { if (!isDisabled) { onChange(opt.value); setOpen(false) } }}
                style={{
                  padding: '9px 12px',
                  display: 'flex', alignItems: 'center', gap: 8,
                  cursor: isDisabled ? 'not-allowed' : 'pointer',
                  background: isSelected ? 'var(--c-signal-glow)' : 'var(--c-surface-3)',
                  borderTop: i > 0 ? '1px solid var(--c-border)' : 'none',
                  transition: 'background 0.1s',
                  opacity: isDisabled ? 0.4 : 1,
                }}
                onMouseEnter={e => { if (!isDisabled) (e.currentTarget as HTMLDivElement).style.background = isSelected ? 'var(--c-signal-glow)' : 'var(--c-surface-2)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = isSelected ? 'var(--c-signal-glow)' : 'var(--c-surface-3)' }}
              >
                {/* Selected indicator */}
                <span style={{
                  width: 4, height: 4, borderRadius: '50%', flexShrink: 0,
                  background: isSelected ? 'var(--c-signal)' : 'transparent',
                }} />
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: isSelected ? 'var(--c-signal)' : isDisabled ? 'var(--c-text-faint)' : 'var(--c-text)' }}>
                  {opt.label}
                </span>
                {opt.note && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-text-faint)', marginLeft: 'auto' }}>
                    {isDisabled ? '🔒 ' : ''}{opt.note}
                  </span>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function DescriptionField({
  value,
  onChange,
  disabled,
}: {
  value: string; onChange: (v: string) => void; disabled?: boolean
}) {
  return (
    <div>
      <label style={{
        display: 'block', marginBottom: 6,
        fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 700,
        letterSpacing: '0.14em', textTransform: 'uppercase',
        color: 'var(--c-text-muted)',
      }}>
        What are you seeing?
        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 400, fontSize: '0.65rem', color: 'var(--c-text-faint)', marginLeft: 8, textTransform: 'none', letterSpacing: 0 }}>
          optional — feeds directly into the AI prompt
        </span>
      </label>
      <textarea
        value={value}
        onChange={e => onChange(e.target.value)}
        disabled={disabled}
        rows={3}
        placeholder="e.g. Elevated 5xx errors since 14:00, two pods restarted, latency spiked to 4 s on /checkout endpoint…"
        className="corvin-interactive"
        style={{
          width: '100%', boxSizing: 'border-box', padding: '9px 12px',
          resize: 'vertical', minHeight: 72, fontFamily: 'var(--font-body)',
          fontSize: '0.82rem', lineHeight: 1.65,
          background: 'var(--c-surface)', border: '1px solid var(--c-border)',
          borderRadius: 8, color: 'var(--c-text)',
          transition: 'border-color 0.15s',
        }}
        onFocus={e => { e.currentTarget.style.borderColor = 'var(--c-signal-dim)' }}
        onBlur={e => { e.currentTarget.style.borderColor = 'var(--c-border)' }}
      />
    </div>
  )
}

// Service names and presets are loaded from the API at runtime.

// ── Start investigation form ──────────────────────────────────────────────────

function StartInvestigationForm() {
  const { names: serviceNames, loading: servicesLoading } = useServiceNames()
  const { data: presets } = useApplicationPresets()
  const defaultEnv = useDefaultEnvironment()
  const envOptions = useEnvironmentOptions()
  const [service, setService] = useState('')
  const [environment, setEnvironment] = useState(defaultEnv || '')
  const [description, setDescription] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const pendingQueue = useRef<StreamParams[]>([])
  const [queueTotal, setQueueTotal] = useState(0)
  const [queueDone, setQueueDone] = useState(0)
  const queryClient = useQueryClient()

  const { stages, streamText, fetchingEvents, deliveryEvents, isStreaming, isComplete, error, requestId, start, reset } =
    useInvestigationStream()

  const handleComplete = () => {
    if (requestId) queryClient.invalidateQueries({ queryKey: ['investigations'] })
  }

  // Drain queue: after each investigation completes, start the next service
  useEffect(() => {
    if (isComplete && pendingQueue.current.length > 0) {
      const next = pendingQueue.current.shift()!
      setQueueDone(d => d + 1)
      const t = setTimeout(() => { reset(); start(next) }, 1500)
      return () => clearTimeout(t)
    }
  }, [isComplete, start, reset])

  function handlePreset(preset: { service_name: string; environment: string; description: string }) {
    setService(preset.service_name)
    setEnvironment(preset.environment)
    setDescription(preset.description)
    setFormError(null)
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setFormError(null)
    if (!service) { setFormError('Please select a service.'); return }
    if (service === '__all__') {
      const params = serviceNames.map(s => ({ service_name: s, environment, description }))
      pendingQueue.current = params.slice(1)
      setQueueTotal(params.length)
      setQueueDone(0)
      start(params[0])
    } else {
      pendingQueue.current = []
      setQueueTotal(0)
      setQueueDone(0)
      start({ service_name: service, environment, description })
    }
  }

  const showProgress = isStreaming || isComplete || stages.length > 0

  return (
    <div className="panel-signal animate-fade-up" style={{ marginTop: 32 }}>
      {/* Header */}
      <div style={{
        padding: '14px 20px',
        borderBottom: '1px solid var(--c-border)',
        display: 'flex', alignItems: 'center', gap: 10,
        background: 'var(--c-signal-light)',
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
        {/* Simulator preset buttons (loaded from API) */}
        {presets.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{
              fontFamily: 'var(--font-display)', fontSize: '0.68rem', fontWeight: 700,
              letterSpacing: '0.12em', textTransform: 'uppercase',
              color: 'var(--c-text-muted)', marginBottom: 8,
            }}>
              Quick Presets
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {presets.map(preset => (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => handlePreset(preset)}
                  disabled={isStreaming}
                  className="btn-ghost"
                  style={{ padding: '5px 14px', fontSize: '0.75rem', opacity: isStreaming ? 0.5 : 1 }}
                >
                  ⚡ {preset.label}
                </button>
              ))}
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
            <SelectField
              label="Service"
              value={service}
              onChange={setService}
              disabled={isStreaming || servicesLoading}
              required
              options={[
                { value: '', label: servicesLoading ? 'Loading…' : '— Select a service —', disabled: true },
                ...serviceNames.map(n => ({ value: n, label: n })),
                ...(serviceNames.length > 1 ? [{ value: '__all__', label: '— All Services —' }] : []),
              ]}
            />
            <SelectField
              label="Environment"
              value={environment}
              onChange={setEnvironment}
              disabled={isStreaming}
              options={[
                { value: '', label: '— Select environment —', disabled: true },
                ...envOptions.map(e => ({ value: e, label: e })),
              ]}
            />
          </div>
          <div style={{ marginBottom: 16 }}>
            <DescriptionField value={description} onChange={setDescription} disabled={isStreaming} />
          </div>

          {formError && (
            <div style={{
              marginBottom: 12, padding: '8px 12px',
              background: 'var(--c-red-bg)', border: '1px solid var(--c-red-border)',
              borderRadius: 8, fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--c-red)',
            }}>
              {formError}
            </div>
          )}

          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <button type="submit" disabled={isStreaming} className="btn-primary">
              {isStreaming
                ? queueTotal > 1 ? `Running ${queueDone + 1} / ${queueTotal}…` : 'Running…'
                : service === '__all__' ? '▶ Run All Services' : '▶ Start Investigation'}
            </button>
            {isStreaming && queueTotal > 1 && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-text-faint)' }}>
                {queueDone} complete · {queueTotal - queueDone - 1} queued
              </span>
            )}
          </div>
        </form>

        {showProgress && (
          <StreamingProgress
            stages={stages}
            streamText={streamText}
            fetchingEvents={fetchingEvents}
            deliveryEvents={deliveryEvents}
            isStreaming={isStreaming}
            isComplete={isComplete}
            error={error}
            requestId={requestId}
            onReset={() => { pendingQueue.current = []; setQueueTotal(0); setQueueDone(0); reset(); handleComplete() }}
          />
        )}
      </div>
    </div>
  )
}

// ── Investigation list ────────────────────────────────────────────────────────

function InvestigationList({ items, isFiltered }: { items: (InvestigationSummary & { approval_status?: string })[], isFiltered?: boolean }) {
  if (items.length === 0) {
    return (
      <div style={{
        padding: '64px 20px', textAlign: 'center',
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14,
      }}>
        <div style={{
          width: 48, height: 48, borderRadius: '50%',
          background: 'var(--c-surface-3)',
          border: '1px solid var(--c-border-hi)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '1.2rem', color: 'var(--c-text-muted)',
        }}>
          {isFiltered ? '⌕' : '◇'}
        </div>
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.85rem', letterSpacing: '0.04em', color: 'var(--c-text-dim)' }}>
          {isFiltered ? 'No matches found' : 'No investigations yet'}
        </div>
        <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.78rem', color: 'var(--c-text-muted)', maxWidth: 340, lineHeight: 1.7 }}>
          {isFiltered
            ? 'Try adjusting your search or clearing the status filter.'
            : 'Start your first investigation above. Corvin will analyze your Azure services and deliver a structured RCA.'}
        </div>
      </div>
    )
  }

  return (
    <>
      {/* Table header */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '72px 1fr 80px min-content 80px 18px',
        gap: 16,
        padding: '8px 14px',
        borderBottom: '1px solid var(--c-border-hi)',
        background: 'var(--c-surface-2)',
      }}>
        {['TIME', 'SERVICE', 'ENV', 'STATUS', 'AGO', ''].map((h, i) => (
          <span key={i} style={{
            fontFamily: 'var(--font-display)', fontSize: '0.68rem', fontWeight: 700,
            letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--c-text-muted)',
          }}>{h}</span>
        ))}
      </div>

      {items.map((inv) => {
        const status = inv.approval_status ?? 'pending'
        const priority = (inv as any).incident_priority ?? 'P3'
        const priColor = priority === 'P1' ? 'var(--c-red)' : priority === 'P2' ? 'var(--c-signal)' : 'var(--c-text-muted)'
        const priBg = priority === 'P1' ? 'var(--c-error-bg)' : priority === 'P2' ? 'var(--c-signal-light)' : 'var(--c-surface-2)'
        const priBorder = priority === 'P1' ? '1px solid var(--c-error-border)' : priority === 'P2' ? '1px solid var(--c-signal-dim)' : '1px solid var(--c-border)'

        return (
          <Link
            key={inv.request_id}
            to={`/investigations/${inv.request_id}`}
            className="log-row animate-fade-up"
            style={{
              gridTemplateColumns: '72px 1fr 80px min-content 80px 18px',
            }}
          >
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.67rem', color: 'var(--c-text-faint)' }}>
              {fmtTs(inv.completed_at ?? inv.created_at)}
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ 
                fontFamily: 'var(--font-mono)', fontSize: '0.68rem', fontWeight: 800, 
                color: priColor, background: priBg, border: priBorder,
                padding: '2px 6px', borderRadius: 4, flexShrink: 0
              }}>
                {priority}
              </span>
              <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.88rem', color: 'var(--c-text)' }}>
                {inv.service_name}
              </span>
            </div>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.67rem', color: 'var(--c-text-dim)' }}>
              {inv.environment}
            </span>
            <span className={`badge ${STATUS_CLS[status] ?? 'badge-pending'}`} style={{ justifySelf: 'start' }}>{status}</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.67rem', color: 'var(--c-text-faint)', whiteSpace: 'nowrap' }}>
              {timeAgo(inv.completed_at ?? inv.created_at)}
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
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [viewMode, setViewMode] = useState<'list' | 'network'>('list')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['investigations'],
    queryFn: fetchInvestigations,
    refetchInterval: 30_000,
  })

  const items = (data ?? []) as (InvestigationSummary & { approval_status?: string })[]
  const pending = items.filter(inv => (inv.approval_status ?? 'pending') === 'pending').length

  const filteredItems = items.filter(inv => {
    const q = searchQuery.trim().toLowerCase()
    const matchSearch = !q || inv.service_name.toLowerCase().includes(q)
    const matchStatus = statusFilter === 'all' || (inv.approval_status ?? 'pending') === statusFilter
    return matchSearch && matchStatus
  })

  return (
    <Layout>
      {/* ── Command header ───────────────────────────────────────────────── */}
      <div className="animate-fade-up" style={{ marginBottom: 24, display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--c-accent)', marginBottom: 6 }}>
            Investigation Console
          </div>
          <h1 style={{
            margin: 0, fontFamily: 'var(--font-display)', fontSize: '1.6rem', fontWeight: 800,
            letterSpacing: '-0.03em', lineHeight: 1.2,
            color: 'var(--c-text)',
          }}>
            Investigations
          </h1>
          <p style={{ margin: '6px 0 0', fontSize: '0.82rem', color: 'var(--c-text-muted)', lineHeight: 1.5 }}>
            Run AI-powered root cause analysis against your Azure services.
          </p>
        </div>
        {pending > 0 && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '8px 16px',
            background: 'var(--c-warning-bg)',
            border: '1px solid var(--c-warning-border)',
            borderRadius: 8,
          }}>
            <span className="animate-pulse-glow" style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--c-yellow)', display: 'inline-block', flexShrink: 0 }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-yellow)', fontWeight: 600 }}>
              {pending} awaiting approval
            </span>
          </div>
        )}
      </div>

      {/* ── New investigation form (PRIMARY ACTION) ──────────────────────── */}
      <StartInvestigationForm />

      {/* ── Log header + view toggle ──────────────────────────────────────── */}
      <div style={{ marginTop: 28, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{
          fontFamily: 'var(--font-display)', fontSize: '0.7rem', fontWeight: 700,
          letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--c-text-muted)',
          flexShrink: 0,
        }}>
          {viewMode === 'list' ? 'Investigation Log' : 'Similarity Network'}
        </span>
        <div style={{ flex: 1, height: 1, background: 'var(--c-border-hi)' }} />
        {/* List / Network view toggle */}
        <div style={{
          display: 'flex', gap: 2, padding: 3,
          background: 'var(--c-surface-2)', borderRadius: 8,
          border: '1px solid var(--c-border)', flexShrink: 0,
        }}>
          {(['list', 'network'] as const).map(mode => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              style={{
                padding: '4px 12px',
                fontFamily: 'var(--font-mono)', fontSize: '0.68rem', fontWeight: 600,
                borderRadius: 5, border: 'none', cursor: 'pointer',
                background: viewMode === mode ? 'var(--c-accent)' : 'transparent',
                color: viewMode === mode ? '#fff' : 'var(--c-text-muted)',
                transition: 'background 0.15s, color 0.15s',
              }}
            >
              {mode === 'list' ? '≡ List' : '⬡ Network'}
            </button>
          ))}
        </div>
        {data && viewMode === 'list' && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-faint)', flexShrink: 0 }}>
            {filteredItems.length !== items.length
              ? `${filteredItems.length} / ${items.length} records`
              : `${items.length} record${items.length !== 1 ? 's' : ''}`}
          </span>
        )}
      </div>

      {/* ── Network view ─────────────────────────────────────────────────── */}
      {viewMode === 'network' && (
        <div className="panel animate-fade-up-1" style={{ padding: '20px 24px' }}>
          <SimilarityNetworkGraph />
        </div>
      )}

      {/* ── Filter bar + list (list view only) ──────────────────────────── */}
      {viewMode === 'list' && (<>
      <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
        <div style={{ position: 'relative', flex: 1 }}>
          <span style={{
            position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)',
            fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-text-faint)',
            pointerEvents: 'none', userSelect: 'none',
          }}>⌕</span>
          <input
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Filter by service…"
            style={{
              width: '100%', boxSizing: 'border-box',
              padding: '7px 12px 7px 26px',
              fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
            }}
          />
        </div>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          style={{
            padding: '7px 28px 7px 10px',
            fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
            background: 'var(--c-surface-2)', color: statusFilter === 'all' ? 'var(--c-text-dim)' : 'var(--c-text)',
            border: '1px solid var(--c-border)', borderRadius: 8, cursor: 'pointer',
            appearance: 'none',
            backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23666'/%3E%3C/svg%3E")`,
            backgroundRepeat: 'no-repeat', backgroundPosition: 'right 9px center',
          }}
        >
          <option value="all">All Statuses</option>
          <option value="pending">pending</option>
          <option value="approved">approved</option>
          <option value="acknowledged">acknowledged</option>
          <option value="rejected">rejected</option>
          <option value="executed">executed</option>
        </select>
      </div>

      <div className="panel animate-fade-up-1" style={{ overflow: 'hidden' }}>
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
        {data && <InvestigationList items={filteredItems} isFiltered={searchQuery.trim() !== '' || statusFilter !== 'all'} />}
      </div>
      </>)}
    </Layout>
  )
}


// ── Start investigation form ──────────────────────────────────────────────────

