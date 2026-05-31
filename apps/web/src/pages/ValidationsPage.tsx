/**
 * ValidationsPage — user journey tests, chaos stubs, health checks; pass/fail tracking.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import Layout from '../components/Layout'
import { Modal } from '../components/Modal'
import { JourneyBuilderModal } from '../components/JourneyBuilderModal'
import {
  listValidations,
  createValidation,
  deleteValidation,
  triggerValidationRun,
  type ValidationDefinition,
  type ValidationRun,
  type ValidationStepResult,
} from '../api/client'

// ── Constants ──────────────────────────────────────────────────────────────────

const VALIDATION_TYPES = [
  'health_check', 'endpoint', 'synthetic', 'user_journey', 'slo_gate', 'chaos',
] as const

type ValidationType = typeof VALIDATION_TYPES[number]

const TYPE_COLORS: Record<ValidationType, { fg: string; bg: string }> = {
  health_check: { fg: 'var(--c-info)', bg: 'rgba(100,160,255,0.12)' },
  endpoint: { fg: 'var(--c-text)', bg: 'var(--c-surface-3)' },
  synthetic: { fg: '#2dd4bf', bg: 'rgba(45,212,191,0.12)' },
  user_journey: { fg: '#a78bfa', bg: 'rgba(167,139,250,0.12)' },
  slo_gate: { fg: '#c084fc', bg: 'rgba(192,132,252,0.12)' },
  chaos: { fg: 'var(--c-warning)', bg: 'rgba(255,193,7,0.12)' },
}

const STATUS_COLORS: Record<string, string> = {
  pass: 'var(--c-green)',
  fail: 'var(--c-red)',
  error: 'var(--c-warning)',
  running: 'var(--c-info)',
}

const DEFAULT_CONFIGS: Record<ValidationType, string> = {
  health_check: '{\n  "url": "https://your-service/health"\n}',
  endpoint: '{\n  "steps": [\n    { "url": "https://your-service/api/resource", "method": "GET", "expected_status": 200 }\n  ]\n}',
  synthetic: '{\n  "steps": [\n    { "url": "https://your-service/api/login", "method": "POST", "expected_status": 200 },\n    { "url": "https://your-service/api/dashboard", "method": "GET", "expected_status": 200 }\n  ]\n}',
  user_journey: '{\n  "steps": [\n    { "url": "https://your-service/api/login", "method": "POST", "expected_status": 200 },\n    { "url": "https://your-service/api/data", "method": "GET", "expected_status": 200 }\n  ]\n}',
  slo_gate: '{\n  "slo_config_id": 1\n}',
  chaos: '{\n  "target_service": "my-service",\n  "failure_mode": "latency",\n  "duration_seconds": 60,\n  "note": "Chaos is currently a stub — always passes"\n}',
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function relativeTime(iso: string | null): string {
  if (!iso) return 'Never'
  const diff = Date.now() - new Date(iso).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

function TypeBadge({ type }: { type: string }) {
  const c = TYPE_COLORS[type as ValidationType] ?? { fg: 'var(--c-text)', bg: 'var(--c-surface-3)' }
  return (
    <span style={{
      fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.07em',
      color: c.fg, background: c.bg, borderRadius: 4, padding: '2px 6px',
      textTransform: 'uppercase', fontFamily: 'var(--font-mono)',
    }}>
      {type.replace('_', ' ')}
    </span>
  )
}

function StatusChip({ status }: { status: string | null }) {
  if (!status) return <span style={{ fontSize: '0.68rem', color: 'var(--c-text-muted)' }}>NEVER RUN</span>
  const color = STATUS_COLORS[status] ?? 'var(--c-text-muted)'
  return (
    <span style={{
      fontSize: '0.65rem', fontWeight: 700, letterSpacing: '0.07em',
      color, border: `1px solid ${color}`, borderRadius: 3,
      padding: '1px 6px', fontFamily: 'var(--font-mono)',
    }}>
      {status.toUpperCase()}
    </span>
  )
}

// ── Step results ───────────────────────────────────────────────────────────────

function StepResults({ run }: { run: ValidationRun }) {
  const steps: ValidationStepResult[] = run.result_json?.steps ?? []
  if (steps.length === 0) {
    return <div style={{ fontSize: '0.75rem', color: 'var(--c-text-muted)' }}>No step details.</div>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 8 }}>
      {steps.map((step, i) => (
        <div key={i} style={{
          display: 'flex', gap: 10, alignItems: 'flex-start',
          background: 'var(--c-surface-2)', borderRadius: 6, padding: '6px 10px',
          fontSize: '0.72rem',
        }}>
          <span style={{ fontSize: '0.8rem', marginTop: 1 }}>
            {step.ok ? <span style={{ color: 'var(--c-green)' }}>✓</span> : <span style={{ color: 'var(--c-red)' }}>✗</span>}
          </span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 600 }}>{step.step_name ?? `Step ${step.step_index ?? i + 1}`}</div>
            {step.status_code && (
              <span style={{ color: 'var(--c-text-muted)', fontFamily: 'var(--font-mono)' }}>
                {step.status_code}
                {step.expected_status ? ` / expected ${step.expected_status}` : ''}
              </span>
            )}
            {step.duration_ms != null && (
              <span style={{ color: 'var(--c-text-faint)', marginLeft: 8, fontFamily: 'var(--font-mono)' }}>
                {step.duration_ms}ms
              </span>
            )}
            {step.note && <div style={{ color: 'var(--c-text-muted)', marginTop: 2 }}>{step.note}</div>}
            {step.error && <div style={{ color: 'var(--c-red)', marginTop: 2 }}>{step.error}</div>}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Validation Card ────────────────────────────────────────────────────────────

function ValidationCard({
  defn,
  onDelete,
}: {
  defn: ValidationDefinition
  onDelete: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [runResult, setRunResult] = useState<ValidationRun | null>(null)
  const qc = useQueryClient()

  const runMut = useMutation({
    mutationFn: () => triggerValidationRun(defn.id),
    onSuccess: (run) => {
      setRunResult(run)
      setExpanded(true)
      qc.invalidateQueries({ queryKey: ['validations'] })
    },
  })

  const deleteMut = useMutation({
    mutationFn: () => deleteValidation(defn.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['validations'] })
      onDelete()
    },
  })

  const lastStatus = runResult?.status ?? defn.last_run_status
  const lastTime = runResult?.started_at ?? defn.last_run_at
  const lastDuration = runResult?.duration_ms ?? null

  return (
    <div style={{
      background: 'var(--c-surface-1)', border: '1px solid var(--c-border)',
      borderRadius: 10, overflow: 'hidden',
    }}>
      <div style={{ padding: '14px 16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 6 }}>
              <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>{defn.name}</span>
              <TypeBadge type={defn.validation_type} />
              {!defn.enabled && (
                <span style={{ fontSize: '0.6rem', color: 'var(--c-text-muted)' }}>DISABLED</span>
              )}
            </div>
            {defn.description && (
              <div style={{ fontSize: '0.73rem', color: 'var(--c-text-muted)', marginBottom: 8 }}>
                {defn.description}
              </div>
            )}
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
              <StatusChip status={lastStatus} />
              <span style={{ fontSize: '0.68rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)' }}>
                {relativeTime(lastTime)}
              </span>
              {lastDuration != null && (
                <span style={{ fontSize: '0.68rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)' }}>
                  {lastDuration}ms
                </span>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
            <button
              onClick={() => setExpanded(v => !v)}
              style={{
                background: 'var(--c-surface-2)', border: '1px solid var(--c-border)',
                borderRadius: 6, padding: '5px 10px', fontSize: '0.72rem',
                cursor: 'pointer', color: 'var(--c-text)',
              }}
            >
              {expanded ? '▲' : '▼'}
            </button>
            <button
              onClick={() => runMut.mutate()}
              disabled={runMut.isPending}
              className="btn-primary"
              style={{ padding: '5px 12px', fontSize: '0.72rem', minWidth: 72 }}
            >
              {runMut.isPending ? '…' : '▶ Run'}
            </button>
            <button
              onClick={() => { if (window.confirm(`Delete "${defn.name}"?`)) deleteMut.mutate() }}
              disabled={deleteMut.isPending}
              style={{
                background: 'none', border: '1px solid var(--c-border)',
                borderRadius: 6, padding: '5px 8px', fontSize: '0.72rem',
                cursor: 'pointer', color: 'var(--c-red)',
              }}
            >
              ×
            </button>
          </div>
        </div>

        {runMut.isError && (
          <div style={{ marginTop: 8, fontSize: '0.72rem', color: 'var(--c-red)' }}>
            Run failed: {(runMut.error as Error)?.message}
          </div>
        )}
      </div>

      {expanded && (runResult || defn.last_run_status) && (
        <div style={{ borderTop: '1px solid var(--c-border)', padding: '12px 16px', background: 'var(--c-surface-2)' }}>
          {runResult ? (
            <StepResults run={runResult} />
          ) : (
            <div style={{ fontSize: '0.73rem', color: 'var(--c-text-muted)' }}>
              Run the validation to see step details.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Create Modal ───────────────────────────────────────────────────────────────

function CreateValidationModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    name: '',
    description: '',
    validation_type: 'health_check' as ValidationType,
    application_id: '',
    config_json: DEFAULT_CONFIGS['health_check'],
    enabled: true,
  })
  const [jsonError, setJsonError] = useState<string | null>(null)

  const createMut = useMutation({
    mutationFn: () => {
      let parsed: Record<string, unknown>
      try {
        parsed = JSON.parse(form.config_json)
      } catch {
        throw new Error('Invalid JSON in config')
      }
      return createValidation({
        name: form.name,
        description: form.description || undefined,
        validation_type: form.validation_type,
        application_id: form.application_id || undefined,
        config_json: parsed,
        enabled: form.enabled,
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['validations'] })
      onClose()
    },
    onError: (err: Error) => setJsonError(err.message),
  })

  const handleTypeChange = (t: ValidationType) => {
    setForm(f => ({ ...f, validation_type: t, config_json: DEFAULT_CONFIGS[t] }))
  }

  return (
    <Modal isOpen onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div>
          <label style={{ fontSize: '0.72rem', color: 'var(--c-text-muted)', display: 'block', marginBottom: 4 }}>
            NAME *
          </label>
          <input
            autoFocus
            value={form.name}
            onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
            placeholder="e.g. Auth service health check"
            style={{ width: '100%', boxSizing: 'border-box' }}
            className="input"
          />
        </div>

        <div>
          <label style={{ fontSize: '0.72rem', color: 'var(--c-text-muted)', display: 'block', marginBottom: 4 }}>
            TYPE *
          </label>
          <select
            value={form.validation_type}
            onChange={e => handleTypeChange(e.target.value as ValidationType)}
            className="input"
            style={{ width: '100%' }}
          >
            {VALIDATION_TYPES.map(t => (
              <option key={t} value={t}>{t.replace('_', ' ')}</option>
            ))}
          </select>
        </div>

        <div>
          <label style={{ fontSize: '0.72rem', color: 'var(--c-text-muted)', display: 'block', marginBottom: 4 }}>
            DESCRIPTION
          </label>
          <input
            value={form.description}
            onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
            placeholder="Optional description"
            style={{ width: '100%', boxSizing: 'border-box' }}
            className="input"
          />
        </div>

        <div>
          <label style={{ fontSize: '0.72rem', color: 'var(--c-text-muted)', display: 'block', marginBottom: 4 }}>
            APPLICATION ID (optional)
          </label>
          <input
            value={form.application_id}
            onChange={e => setForm(f => ({ ...f, application_id: e.target.value }))}
            placeholder="Leave blank for global"
            style={{ width: '100%', boxSizing: 'border-box' }}
            className="input"
          />
        </div>

        <div>
          <label style={{ fontSize: '0.72rem', color: 'var(--c-text-muted)', display: 'block', marginBottom: 4 }}>
            CONFIG JSON *
          </label>
          <textarea
            value={form.config_json}
            onChange={e => {
              setForm(f => ({ ...f, config_json: e.target.value }))
              setJsonError(null)
            }}
            rows={8}
            spellCheck={false}
            style={{
              width: '100%', boxSizing: 'border-box', fontFamily: 'var(--font-mono)',
              fontSize: '0.75rem', resize: 'vertical',
            }}
            className="input"
          />
          {jsonError && <div style={{ color: 'var(--c-red)', fontSize: '0.72rem', marginTop: 4 }}>{jsonError}</div>}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input
            type="checkbox"
            id="enabled-chk"
            checked={form.enabled}
            onChange={e => setForm(f => ({ ...f, enabled: e.target.checked }))}
          />
          <label htmlFor="enabled-chk" style={{ fontSize: '0.8rem', cursor: 'pointer' }}>Enabled</label>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
          <button onClick={onClose} style={{
            padding: '7px 16px', background: 'none',
            border: '1px solid var(--c-border)', borderRadius: 6, cursor: 'pointer',
            color: 'var(--c-text)', fontSize: '0.82rem',
          }}>
            Cancel
          </button>
          <button
            onClick={() => createMut.mutate()}
            disabled={!form.name || createMut.isPending}
            className="btn-primary"
            style={{ padding: '7px 16px', fontSize: '0.82rem' }}
          >
            {createMut.isPending ? 'Creating…' : 'Create'}
          </button>
        </div>

        {createMut.isError && (
          <div style={{ color: 'var(--c-red)', fontSize: '0.72rem' }}>
            {(createMut.error as Error)?.message}
          </div>
        )}
      </div>
    </Modal>
  )
}

// ── Summary strip ──────────────────────────────────────────────────────────────

function SummaryStrip({ entries }: { entries: ValidationDefinition[] }) {
  const total = entries.length
  const passing = entries.filter(e => e.last_run_status === 'pass').length
  const failing = entries.filter(e => e.last_run_status === 'fail' || e.last_run_status === 'error').length
  const disabled = entries.filter(e => !e.enabled).length

  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
      {[
        { label: 'Total', value: total, color: 'var(--c-text)' },
        { label: 'Passing', value: passing, color: 'var(--c-green)' },
        { label: 'Failing', value: failing, color: 'var(--c-red)' },
        { label: 'Disabled', value: disabled, color: 'var(--c-text-muted)' },
      ].map(s => (
        <div key={s.label} style={{
          background: 'var(--c-surface-1)', border: '1px solid var(--c-border)',
          borderRadius: 8, padding: '8px 16px', display: 'flex', gap: 8, alignItems: 'baseline',
        }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 800, fontSize: '1.3rem', color: s.color }}>
            {s.value}
          </span>
          <span style={{ fontSize: '0.68rem', color: 'var(--c-text-muted)', letterSpacing: '0.05em' }}>
            {s.label.toUpperCase()}
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function ValidationsPage() {
  const [appFilter, setAppFilter] = useState<string>('')
  const [showCreate, setShowCreate] = useState(false)
  const [showJourneyBuilder, setShowJourneyBuilder] = useState(false)
  const [typeFilter, setTypeFilter] = useState<string>('')

  const { data: allDefs = [], isLoading, isError } = useQuery({
    queryKey: ['validations', appFilter],
    queryFn: () => listValidations(appFilter || undefined),
    refetchInterval: 60_000,
  })

  const filtered = typeFilter ? allDefs.filter(d => d.validation_type === typeFilter) : allDefs
  const appIds = [...new Set(allDefs.map(e => e.application_id).filter(Boolean) as string[])]

  return (
    <Layout>
      <div style={{ padding: '28px 32px', maxWidth: 1100, margin: '0 auto' }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: '1.4rem', fontWeight: 800 }}>Validations</h1>
            <p style={{ margin: '4px 0 0', fontSize: '0.8rem', color: 'var(--c-text-muted)' }}>
              Health checks · user journeys · chaos stubs · SLO gates
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {appIds.length > 0 && (
              <select
                value={appFilter}
                onChange={e => setAppFilter(e.target.value)}
                className="input"
                style={{ fontSize: '0.78rem', padding: '6px 10px' }}
              >
                <option value="">All Apps</option>
                {appIds.map(id => (
                  <option key={id} value={id}>{id.slice(0, 8)}…</option>
                ))}
              </select>
            )}
            <select
              value={typeFilter}
              onChange={e => setTypeFilter(e.target.value)}
              className="input"
              style={{ fontSize: '0.78rem', padding: '6px 10px' }}
            >
              <option value="">All Types</option>
              {VALIDATION_TYPES.map(t => (
                <option key={t} value={t}>{t.replace('_', ' ')}</option>
              ))}
            </select>
            <button
              onClick={() => setShowJourneyBuilder(true)}
              className="btn-primary"
              style={{ padding: '7px 14px', fontSize: '0.8rem', background: 'rgba(167,139,250,0.18)', border: '1px solid #a78bfa', color: '#a78bfa' }}
            >
              🛤️ Journey Builder
            </button>
            <button
              onClick={() => setShowCreate(true)}
              className="btn-primary"
              style={{ padding: '7px 14px', fontSize: '0.8rem' }}
            >
              + Add Validation
            </button>
          </div>
        </div>

        <SummaryStrip entries={allDefs} />

        {isLoading && (
          <div style={{ color: 'var(--c-text-muted)', textAlign: 'center', padding: 60 }}>
            Loading validations…
          </div>
        )}
        {isError && (
          <div style={{ color: 'var(--c-red)', textAlign: 'center', padding: 60 }}>
            Failed to load validations. Is the backend running?
          </div>
        )}

        {!isLoading && !isError && filtered.length === 0 && (
          <div style={{
            textAlign: 'center', padding: '60px 20px',
            border: '1px dashed var(--c-border)', borderRadius: 10,
          }}>
            <div style={{ fontSize: '2rem', marginBottom: 12 }}>✓</div>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>
              {allDefs.length > 0 ? 'No matches for current filter' : 'No validations defined'}
            </div>
            <div style={{ color: 'var(--c-text-muted)', fontSize: '0.82rem', maxWidth: 380, margin: '0 auto' }}>
              Click "Add Validation" to create a health check, endpoint test, or user journey.
            </div>
          </div>
        )}

        {!isLoading && filtered.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {filtered.map(defn => (
              <ValidationCard
                key={defn.id}
                defn={defn}
                onDelete={() => {/* handled by mutation invalidation */}}
              />
            ))}
          </div>
        )}

        {showCreate && <CreateValidationModal onClose={() => setShowCreate(false)} />}
        {showJourneyBuilder && <JourneyBuilderModal onClose={() => setShowJourneyBuilder(false)} />}
      </div>
    </Layout>
  )
}
