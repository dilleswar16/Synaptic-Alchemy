/**
 * JourneyBuilderModal — Visual step builder for user journey validations.
 * Progressive disclosure: What → How → Steps → Test → Save
 * Designed so a 5-year-old can understand the flow.
 */
import { useState, useCallback } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Modal } from './Modal'
import {
  createValidation,
  dryRunValidation,
  generatePlaywrightScript,
  type JourneyAuthConfig,
  type JourneyStep,
  type JourneyStepAssertion,
  type JourneyStepExtraction,
  type JourneyConfig,
  type DryRunResult,
  type PlaywrightResult,
} from '../api/client'

// ── Styles ────────────────────────────────────────────────────────────────────

const SECTION_STYLE: React.CSSProperties = {
  border: '1px solid var(--c-border)', borderRadius: 8, padding: 14,
  background: 'var(--c-surface-2)', marginBottom: 12,
}

const LABEL_STYLE: React.CSSProperties = {
  fontSize: '0.68rem', fontWeight: 700, letterSpacing: '0.06em',
  color: 'var(--c-text-muted)', display: 'block', marginBottom: 4,
  textTransform: 'uppercase',
}

const INPUT_STYLE: React.CSSProperties = {
  width: '100%', boxSizing: 'border-box' as const,
}

const SMALL_BTN: React.CSSProperties = {
  fontSize: '0.72rem', padding: '4px 10px', borderRadius: 4,
  border: '1px solid var(--c-border)', background: 'none',
  color: 'var(--c-text)', cursor: 'pointer',
}

const STEP_CARD: React.CSSProperties = {
  border: '1px solid var(--c-border)', borderRadius: 8, padding: 12,
  background: 'var(--c-surface-1)', marginBottom: 8,
}

const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'] as const
const AUTH_TYPES = [
  { value: 'none', label: 'None' },
  { value: 'bearer', label: 'Bearer Token' },
  { value: 'api_key', label: 'API Key' },
  { value: 'oauth2_client_credentials', label: 'OAuth2 Client Credentials' },
  { value: 'custom_header', label: 'Custom Header' },
] as const

// ── Auth Panel ────────────────────────────────────────────────────────────────

function AuthPanel({ auth, onChange }: { auth: JourneyAuthConfig; onChange: (a: JourneyAuthConfig) => void }) {
  return (
    <div style={SECTION_STYLE}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: '0.9rem' }}>🔐</span>
        <span style={{ ...LABEL_STYLE, marginBottom: 0 }}>Authentication</span>
      </div>

      <select
        value={auth.type}
        onChange={e => onChange({ type: e.target.value as JourneyAuthConfig['type'] })}
        className="input"
        style={{ ...INPUT_STYLE, marginBottom: 8 }}
      >
        {AUTH_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
      </select>

      {auth.type === 'bearer' && (
        <input className="input" style={INPUT_STYLE} placeholder="Bearer token" value={auth.token || ''}
          onChange={e => onChange({ ...auth, token: e.target.value })} />
      )}

      {auth.type === 'api_key' && (
        <div style={{ display: 'flex', gap: 6 }}>
          <input className="input" style={{ flex: 1 }} placeholder="Header name (e.g. X-API-Key)" value={auth.header_name || ''}
            onChange={e => onChange({ ...auth, header_name: e.target.value })} />
          <input className="input" style={{ flex: 2 }} placeholder="API Key value" value={auth.key || ''}
            onChange={e => onChange({ ...auth, key: e.target.value })} />
        </div>
      )}

      {auth.type === 'oauth2_client_credentials' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <input className="input" style={INPUT_STYLE} placeholder="Token URL" value={auth.token_url || ''}
            onChange={e => onChange({ ...auth, token_url: e.target.value })} />
          <div style={{ display: 'flex', gap: 6 }}>
            <input className="input" style={{ flex: 1 }} placeholder="Client ID" value={auth.client_id || ''}
              onChange={e => onChange({ ...auth, client_id: e.target.value })} />
            <input className="input" style={{ flex: 1 }} placeholder="Client Secret" type="password" value={auth.client_secret || ''}
              onChange={e => onChange({ ...auth, client_secret: e.target.value })} />
          </div>
          <input className="input" style={INPUT_STYLE} placeholder="Scope (optional)" value={auth.scope || ''}
            onChange={e => onChange({ ...auth, scope: e.target.value })} />
        </div>
      )}

      {auth.type === 'custom_header' && (
        <div style={{ display: 'flex', gap: 6 }}>
          <input className="input" style={{ flex: 1 }} placeholder="Header name" value={auth.header_name || ''}
            onChange={e => onChange({ ...auth, header_name: e.target.value })} />
          <input className="input" style={{ flex: 2 }} placeholder="Header value" value={auth.header_value || ''}
            onChange={e => onChange({ ...auth, header_value: e.target.value })} />
        </div>
      )}
    </div>
  )
}

// ── Assertion Row ──────────────────────────────────────────────────────────────

function AssertionRow({ assertion, onChange, onRemove }: {
  assertion: JourneyStepAssertion; onChange: (a: JourneyStepAssertion) => void; onRemove: () => void
}) {
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center', marginBottom: 4 }}>
      <select className="input" style={{ width: 160 }} value={assertion.type}
        onChange={e => onChange({ ...assertion, type: e.target.value as JourneyStepAssertion['type'] })}>
        <option value="body_contains">Body contains</option>
        <option value="json_path_equals">JSON path equals</option>
        <option value="json_path_exists">JSON path exists</option>
        <option value="max_latency_ms">Max latency (ms)</option>
      </select>
      {(assertion.type === 'json_path_equals' || assertion.type === 'json_path_exists') && (
        <input className="input" style={{ flex: 1 }} placeholder="$.path.to.field" value={assertion.path || ''}
          onChange={e => onChange({ ...assertion, path: e.target.value })} />
      )}
      {assertion.type !== 'json_path_exists' && (
        <input className="input" style={{ flex: 1 }} placeholder="Expected value" value={assertion.value || ''}
          onChange={e => onChange({ ...assertion, value: e.target.value })} />
      )}
      <button onClick={onRemove} style={{ ...SMALL_BTN, color: 'var(--c-red)', border: 'none' }}>✕</button>
    </div>
  )
}

// ── Extraction Row ──────────────────────────────────────────────────────────────

function ExtractionRow({ extraction, onChange, onRemove }: {
  extraction: JourneyStepExtraction; onChange: (e: JourneyStepExtraction) => void; onRemove: () => void
}) {
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center', marginBottom: 4 }}>
      <input className="input" style={{ width: 120 }} placeholder="Variable name" value={extraction.variable}
        onChange={e => onChange({ ...extraction, variable: e.target.value })} />
      <select className="input" style={{ width: 100 }} value={extraction.source}
        onChange={e => onChange({ ...extraction, source: e.target.value as 'json_path' | 'header' })}>
        <option value="json_path">JSON path</option>
        <option value="header">Header</option>
      </select>
      <input className="input" style={{ flex: 1 }}
        placeholder={extraction.source === 'json_path' ? '$.data.token' : 'X-Request-Id'}
        value={extraction.source === 'json_path' ? extraction.path || '' : extraction.header || ''}
        onChange={e => {
          if (extraction.source === 'json_path') onChange({ ...extraction, path: e.target.value })
          else onChange({ ...extraction, header: e.target.value })
        }} />
      <button onClick={onRemove} style={{ ...SMALL_BTN, color: 'var(--c-red)', border: 'none' }}>✕</button>
    </div>
  )
}

// ── Step Card ──────────────────────────────────────────────────────────────────

function StepCard({ step, index, onChange, onRemove, onMoveUp, onMoveDown, isFirst, isLast }: {
  step: JourneyStep; index: number
  onChange: (s: JourneyStep) => void; onRemove: () => void
  onMoveUp: () => void; onMoveDown: () => void
  isFirst: boolean; isLast: boolean
}) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div style={STEP_CARD}>
      {/* Step Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--c-text-muted)', minWidth: 20 }}>
          #{index + 1}
        </span>
        <input className="input" style={{ flex: 1 }} placeholder={`Step ${index + 1} name`} value={step.name}
          onChange={e => onChange({ ...step, name: e.target.value })} />
        <button onClick={onMoveUp} disabled={isFirst} style={{ ...SMALL_BTN, opacity: isFirst ? 0.3 : 1 }}>↑</button>
        <button onClick={onMoveDown} disabled={isLast} style={{ ...SMALL_BTN, opacity: isLast ? 0.3 : 1 }}>↓</button>
        <button onClick={() => setExpanded(!expanded)} style={SMALL_BTN}>{expanded ? '−' : '+'}</button>
        <button onClick={onRemove} style={{ ...SMALL_BTN, color: 'var(--c-red)' }}>🗑</button>
      </div>

      {expanded && (
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {/* Method + URL */}
          <div style={{ display: 'flex', gap: 6 }}>
            <select className="input" style={{ width: 90 }} value={step.method || 'GET'}
              onChange={e => onChange({ ...step, method: e.target.value })}>
              {METHODS.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
            <input className="input" style={{ flex: 1 }} placeholder="/api/resource (or full URL)"
              value={step.url || ''} onChange={e => onChange({ ...step, url: e.target.value })} />
            <input className="input" style={{ width: 55 }} placeholder="200" type="number"
              value={step.expected_status ?? 200} onChange={e => onChange({ ...step, expected_status: parseInt(e.target.value) || 200 })} />
          </div>

          {/* Headers */}
          <div>
            <span style={{ ...LABEL_STYLE, fontSize: '0.62rem' }}>HEADERS (key: value, one per line)</span>
            <textarea className="input" rows={2}
              style={{ ...INPUT_STYLE, fontFamily: 'var(--font-mono)', fontSize: '0.72rem', resize: 'vertical' }}
              placeholder="Content-Type: application/json"
              value={Object.entries(step.headers || {}).map(([k, v]) => `${k}: ${v}`).join('\n')}
              onChange={e => {
                const headers: Record<string, string> = {}
                e.target.value.split('\n').forEach(line => {
                  const idx = line.indexOf(':')
                  if (idx > 0) headers[line.slice(0, idx).trim()] = line.slice(idx + 1).trim()
                })
                onChange({ ...step, headers })
              }}
            />
          </div>

          {/* Body */}
          {(step.method === 'POST' || step.method === 'PUT' || step.method === 'PATCH') && (
            <div>
              <span style={{ ...LABEL_STYLE, fontSize: '0.62rem' }}>REQUEST BODY (JSON)</span>
              <textarea className="input" rows={3}
                style={{ ...INPUT_STYLE, fontFamily: 'var(--font-mono)', fontSize: '0.72rem', resize: 'vertical' }}
                placeholder='{"username": "test", "password": "{{password}}"}'
                value={step.body ? JSON.stringify(step.body, null, 2) : ''}
                onChange={e => {
                  try { onChange({ ...step, body: JSON.parse(e.target.value) }) } catch { /* let user type */ }
                }}
              />
            </div>
          )}

          {/* Assertions */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ ...LABEL_STYLE, fontSize: '0.62rem', marginBottom: 0 }}>ASSERTIONS</span>
              <button onClick={() => onChange({
                ...step, assertions: [...(step.assertions || []), { type: 'body_contains', value: '' }]
              })} style={SMALL_BTN}>+ Add</button>
            </div>
            {(step.assertions || []).map((a, ai) => (
              <AssertionRow key={ai} assertion={a}
                onChange={na => {
                  const updated = [...(step.assertions || [])]
                  updated[ai] = na
                  onChange({ ...step, assertions: updated })
                }}
                onRemove={() => onChange({ ...step, assertions: (step.assertions || []).filter((_, i) => i !== ai) })}
              />
            ))}
          </div>

          {/* Variable Extraction */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ ...LABEL_STYLE, fontSize: '0.62rem', marginBottom: 0 }}>EXTRACT VARIABLES</span>
              <button onClick={() => onChange({
                ...step, extract: [...(step.extract || []), { variable: '', source: 'json_path', path: '' }]
              })} style={SMALL_BTN}>+ Add</button>
            </div>
            {(step.extract || []).map((ex, ei) => (
              <ExtractionRow key={ei} extraction={ex}
                onChange={ne => {
                  const updated = [...(step.extract || [])]
                  updated[ei] = ne
                  onChange({ ...step, extract: updated })
                }}
                onRemove={() => onChange({ ...step, extract: (step.extract || []).filter((_, i) => i !== ei) })}
              />
            ))}
            {(step.extract || []).length > 0 && (
              <div style={{ fontSize: '0.62rem', color: 'var(--c-text-muted)', marginTop: 2 }}>
                💡 Use <code>{'{{variable_name}}'}</code> in later steps to reference extracted values
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Dry Run Results ────────────────────────────────────────────────────────────

function DryRunResults({ result }: { result: DryRunResult }) {
  return (
    <div style={{ ...SECTION_STYLE, border: result.passed ? '1px solid var(--c-green)' : '1px solid var(--c-red)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: '1.1rem' }}>{result.passed ? '✅' : '❌'}</span>
        <span style={{ fontWeight: 700, fontSize: '0.85rem' }}>
          {result.passed ? 'All Steps Passed' : 'Journey Failed'}
        </span>
        <span style={{ fontSize: '0.72rem', color: 'var(--c-text-muted)', marginLeft: 'auto' }}>
          {result.duration_ms}ms total
        </span>
      </div>
      {result.steps.map((s, i) => (
        <div key={i} style={{
          display: 'flex', alignItems: 'center', gap: 6, padding: '4px 8px',
          borderRadius: 4, marginBottom: 3,
          background: s.skipped ? 'rgba(128,128,128,0.08)' : s.ok ? 'rgba(72,199,142,0.08)' : 'rgba(255,85,85,0.08)',
        }}>
          <span style={{ fontSize: '0.75rem' }}>
            {s.skipped ? '⏭️' : s.ok ? '✓' : '✗'}
          </span>
          <span style={{ fontSize: '0.75rem', fontWeight: 600, flex: 1 }}>{s.step_name}</span>
          {s.status_code && (
            <span style={{ fontSize: '0.68rem', fontFamily: 'var(--font-mono)', color: 'var(--c-text-muted)' }}>
              {s.status_code}
            </span>
          )}
          {s.duration_ms != null && (
            <span style={{ fontSize: '0.68rem', color: 'var(--c-text-muted)' }}>{s.duration_ms}ms</span>
          )}
          {s.error && !s.skipped && (
            <span style={{ fontSize: '0.65rem', color: 'var(--c-red)' }}>{s.error}</span>
          )}
          {s.extracted_vars && Object.keys(s.extracted_vars).length > 0 && (
            <span style={{ fontSize: '0.62rem', color: 'var(--c-info)' }}>
              📦 {Object.keys(s.extracted_vars).join(', ')}
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Playwright Panel ──────────────────────────────────────────────────────────

function PlaywrightPanel({ script, filename }: PlaywrightResult) {
  const [copied, setCopied] = useState(false)
  return (
    <div style={SECTION_STYLE}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ ...LABEL_STYLE, marginBottom: 0 }}>🎭 PLAYWRIGHT SCRIPT — {filename}</span>
        <button style={SMALL_BTN} onClick={() => {
          navigator.clipboard.writeText(script); setCopied(true); setTimeout(() => setCopied(false), 2000)
        }}>{copied ? '✓ Copied' : 'Copy'}</button>
      </div>
      <pre style={{
        fontSize: '0.7rem', fontFamily: 'var(--font-mono)', background: 'var(--c-surface-1)',
        borderRadius: 6, padding: 10, overflow: 'auto', maxHeight: 250, margin: 0,
        border: '1px solid var(--c-border)',
      }}>{script}</pre>
    </div>
  )
}

// ── Main Modal ────────────────────────────────────────────────────────────────

export function JourneyBuilderModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()

  // Journey metadata
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [abortOnFailure, setAbortOnFailure] = useState(true)
  const [applicationId, setApplicationId] = useState('')

  // Auth
  const [auth, setAuth] = useState<JourneyAuthConfig>({ type: 'none' })

  // Steps
  const [steps, setSteps] = useState<JourneyStep[]>([
    { name: 'Step 1', type: 'http', method: 'GET', url: '', expected_status: 200, assertions: [], extract: [] },
  ])

  // Results
  const [dryRunResult, setDryRunResult] = useState<DryRunResult | null>(null)
  const [playwrightResult, setPlaywrightResult] = useState<PlaywrightResult | null>(null)

  // Build config
  const buildConfig = useCallback((): JourneyConfig => ({
    base_url: baseUrl,
    auth: auth.type !== 'none' ? auth : undefined,
    abort_on_failure: abortOnFailure,
    steps,
  }), [baseUrl, auth, abortOnFailure, steps])

  // Mutations
  const dryRunMut = useMutation({
    mutationFn: () => dryRunValidation(buildConfig()),
    onSuccess: (data) => setDryRunResult(data),
  })

  const playwrightMut = useMutation({
    mutationFn: () => generatePlaywrightScript(buildConfig(), name || 'User Journey Test'),
    onSuccess: (data) => setPlaywrightResult(data),
  })

  const saveMut = useMutation({
    mutationFn: () => createValidation({
      name,
      description: description || undefined,
      validation_type: 'user_journey',
      application_id: applicationId || undefined,
      config_json: buildConfig() as unknown as Record<string, unknown>,
      enabled: true,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['validations'] })
      onClose()
    },
  })

  // Step management
  const updateStep = (idx: number, s: JourneyStep) => {
    const updated = [...steps]
    updated[idx] = s
    setSteps(updated)
  }
  const removeStep = (idx: number) => setSteps(steps.filter((_, i) => i !== idx))
  const moveStep = (from: number, to: number) => {
    const updated = [...steps]
    const [moved] = updated.splice(from, 1)
    updated.splice(to, 0, moved)
    setSteps(updated)
  }
  const addStep = () => setSteps([...steps, {
    name: `Step ${steps.length + 1}`, type: 'http', method: 'GET', url: '', expected_status: 200, assertions: [], extract: [],
  }])

  return (
    <Modal isOpen onClose={onClose}>
      <div style={{ maxHeight: '80vh', overflow: 'auto', padding: '0 2px' }}>
        {/* Title */}
        <h2 style={{ margin: '0 0 4px 0', fontSize: '1.1rem' }}>🛤️ Journey Builder</h2>
        <p style={{ fontSize: '0.72rem', color: 'var(--c-text-muted)', margin: '0 0 16px 0' }}>
          Build a user journey test: define what you're testing, how to authenticate, and what each step should do.
        </p>

        {/* ─── Section 1: What are you testing? ─── */}
        <div style={SECTION_STYLE}>
          <span style={{ ...LABEL_STYLE }}>📋 What are you testing?</span>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <input className="input" style={{ flex: 2 }} placeholder="Journey name (e.g. Login → Dashboard)"
              value={name} onChange={e => setName(e.target.value)} autoFocus />
            <input className="input" style={{ flex: 1 }} placeholder="App ID (optional)"
              value={applicationId} onChange={e => setApplicationId(e.target.value)} />
          </div>
          <input className="input" style={INPUT_STYLE} placeholder="Description (optional)"
            value={description} onChange={e => setDescription(e.target.value)} />
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <input className="input" style={{ flex: 1 }} placeholder="Base URL (e.g. https://api.myservice.com)"
              value={baseUrl} onChange={e => setBaseUrl(e.target.value)} />
            <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.72rem', whiteSpace: 'nowrap' }}>
              <input type="checkbox" checked={abortOnFailure} onChange={e => setAbortOnFailure(e.target.checked)} />
              Stop on failure
            </label>
          </div>
          {baseUrl && (
            <div style={{ fontSize: '0.62rem', color: 'var(--c-text-muted)', marginTop: 4 }}>
              💡 Steps can use relative paths — they'll resolve against: {baseUrl}
            </div>
          )}
        </div>

        {/* ─── Section 2: Authentication ─── */}
        <AuthPanel auth={auth} onChange={setAuth} />

        {/* ─── Section 3: Steps ─── */}
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={LABEL_STYLE}>🚶 Steps ({steps.length})</span>
            <button onClick={addStep} style={{ ...SMALL_BTN, background: 'rgba(100,160,255,0.12)', borderColor: 'var(--c-info)' }}>
              + Add Step
            </button>
          </div>
          {steps.map((step, i) => (
            <StepCard key={i} step={step} index={i}
              onChange={s => updateStep(i, s)}
              onRemove={() => removeStep(i)}
              onMoveUp={() => moveStep(i, i - 1)}
              onMoveDown={() => moveStep(i, i + 1)}
              isFirst={i === 0} isLast={i === steps.length - 1}
            />
          ))}
          {steps.length === 0 && (
            <div style={{ textAlign: 'center', color: 'var(--c-text-muted)', padding: 20, fontSize: '0.8rem' }}>
              No steps yet. Click "Add Step" to begin building your journey.
            </div>
          )}
        </div>

        {/* ─── Section 4: Test It ─── */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <button
            onClick={() => { setDryRunResult(null); dryRunMut.mutate() }}
            disabled={steps.length === 0 || dryRunMut.isPending}
            style={{
              ...SMALL_BTN, flex: 1, padding: '8px 12px', fontWeight: 700,
              background: 'rgba(72,199,142,0.12)', borderColor: 'var(--c-green)',
            }}
          >
            {dryRunMut.isPending ? '⏳ Running…' : '▶ Test Journey (Dry Run)'}
          </button>
          <button
            onClick={() => { setPlaywrightResult(null); playwrightMut.mutate() }}
            disabled={steps.length === 0 || playwrightMut.isPending}
            style={{ ...SMALL_BTN, flex: 1, padding: '8px 12px', fontWeight: 700, background: 'rgba(167,139,250,0.12)', borderColor: '#a78bfa' }}
          >
            {playwrightMut.isPending ? '⏳ Generating…' : '🎭 Generate Playwright'}
          </button>
        </div>

        {/* Results */}
        {dryRunMut.isError && (
          <div style={{ color: 'var(--c-red)', fontSize: '0.72rem', marginBottom: 8 }}>
            Dry run error: {(dryRunMut.error as Error)?.message}
          </div>
        )}
        {dryRunResult && <DryRunResults result={dryRunResult} />}
        {playwrightResult && <PlaywrightPanel {...playwrightResult} />}

        {/* ─── Section 5: Save ─── */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8, borderTop: '1px solid var(--c-border)', paddingTop: 12 }}>
          <button onClick={onClose} style={{
            padding: '8px 18px', background: 'none', border: '1px solid var(--c-border)',
            borderRadius: 6, cursor: 'pointer', color: 'var(--c-text)', fontSize: '0.82rem',
          }}>Cancel</button>
          <button
            onClick={() => saveMut.mutate()}
            disabled={!name || steps.length === 0 || saveMut.isPending}
            className="btn-primary"
            style={{ padding: '8px 18px', fontSize: '0.82rem' }}
          >
            {saveMut.isPending ? 'Saving…' : '💾 Save Journey'}
          </button>
        </div>
        {saveMut.isError && (
          <div style={{ color: 'var(--c-red)', fontSize: '0.72rem', marginTop: 6 }}>
            {(saveMut.error as Error)?.message}
          </div>
        )}
      </div>
    </Modal>
  )
}
