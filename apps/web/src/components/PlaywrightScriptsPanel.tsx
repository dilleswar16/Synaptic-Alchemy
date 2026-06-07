/**
 * PlaywrightScriptsPanel — import, manage and execute Playwright .spec.ts files
 * directly from the Corvin Validations page.
 */
import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listPlaywrightScripts,
  uploadPlaywrightScript,
  deletePlaywrightScript,
  runPlaywrightScript,
  getPlaywrightRunHistory,
  type PlaywrightScript,
  type PlaywrightRunResult,
  type PlaywrightTestResult,
} from '../api/client'

// ── Helpers ───────────────────────────────────────────────────────────────────

function statusColor(status: string) {
  if (status === 'pass' || status === 'passed') return 'var(--c-green)'
  if (status === 'fail' || status === 'failed') return 'var(--c-red)'
  if (status === 'running') return 'var(--c-info)'
  if (status === 'timedOut') return 'var(--c-warning)'
  return 'var(--c-text-faint)'
}

function statusBg(status: string) {
  if (status === 'pass' || status === 'passed') return 'rgba(34,197,94,0.10)'
  if (status === 'fail' || status === 'failed') return 'rgba(239,68,68,0.10)'
  if (status === 'running') return 'rgba(100,160,255,0.10)'
  if (status === 'timedOut') return 'rgba(251,191,36,0.10)'
  return 'var(--c-surface-3)'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    pass: '✓ PASSED', fail: '✗ FAILED', running: '⟳ RUNNING',
    error: '⚠ ERROR', passed: '✓', failed: '✗', skipped: '⊘', timedOut: '⏱',
  }
  return map[status] ?? status.toUpperCase()
}

function testIcon(status: string) {
  if (status === 'passed') return '✓'
  if (status === 'skipped') return '⊘'
  if (status === 'timedOut') return '⏱'
  return '✗'
}

function reltime(iso: string) {
  const d = Date.now() - new Date(iso).getTime()
  const s = Math.floor(d / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  return `${Math.floor(m / 60)}h ago`
}

const PW_ACCENT = '#a78bfa'
const PW_ACCENT_BG = 'rgba(167,139,250,0.12)'
const PW_ACCENT_BORDER = 'rgba(167,139,250,0.35)'

// ── Test result row ───────────────────────────────────────────────────────────

function TestResultRow({ test }: { test: PlaywrightTestResult }) {
  const passed = test.status === 'passed'
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 10,
      padding: '7px 12px', borderRadius: 6,
      background: passed ? 'rgba(34,197,94,0.06)' : 'rgba(239,68,68,0.06)',
      border: `1px solid ${passed ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)'}`,
    }}>
      <span style={{
        fontSize: '0.8rem', flexShrink: 0, marginTop: 1,
        color: statusColor(test.status),
      }}>
        {testIcon(test.status)}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: '0.75rem', color: 'var(--c-text)', fontWeight: 500, lineHeight: 1.4 }}>
          {test.title}
        </div>
        {test.error && (
          <div style={{
            fontSize: '0.68rem', color: 'var(--c-red)',
            fontFamily: 'var(--font-mono)', marginTop: 4,
            whiteSpace: 'pre-wrap', lineHeight: 1.5,
          }}>
            {test.error}
          </div>
        )}
      </div>
      <span style={{
        fontSize: '0.63rem', color: 'var(--c-text-faint)',
        fontFamily: 'var(--font-mono)', flexShrink: 0,
      }}>
        {test.duration_ms}ms
      </span>
    </div>
  )
}

// ── Run history row ───────────────────────────────────────────────────────────

function RunHistoryRow({ run }: { run: PlaywrightRunResult }) {
  const [expanded, setExpanded] = useState(false)
  const res = run.result_json ?? {}
  const tests: PlaywrightTestResult[] = res.tests ?? []
  const total = res.total ?? tests.length
  const failed = res.failed_count ?? tests.filter(t => t.status !== 'passed').length
  const passed = total - failed

  return (
    <div style={{ borderBottom: '1px solid var(--c-border)' }}>
      {/* Run summary row */}
      <button
        onClick={() => setExpanded(e => !e)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', padding: '9px 16px',
          background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left',
          gap: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>
          {/* Status badge */}
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.63rem', fontWeight: 700,
            color: statusColor(run.status),
            background: statusBg(run.status),
            borderRadius: 4, padding: '2px 7px',
            flexShrink: 0,
          }}>
            {statusLabel(run.status)}
          </span>
          {/* Time */}
          <span style={{ fontSize: '0.72rem', color: 'var(--c-text-faint)', flexShrink: 0 }}>
            {new Date(run.started_at).toLocaleString()}
          </span>
          <span style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
            {reltime(run.started_at)}
          </span>
          {/* Duration */}
          {run.duration_ms !== null && (
            <span style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
              {(run.duration_ms / 1000).toFixed(1)}s
            </span>
          )}
          {/* Pass count */}
          {total > 0 && (
            <span style={{
              fontSize: '0.63rem', fontFamily: 'var(--font-mono)',
              color: failed > 0 ? 'var(--c-red)' : 'var(--c-green)',
              flexShrink: 0,
            }}>
              {passed}/{total} tests
            </span>
          )}
        </div>
        <span style={{ fontSize: '0.68rem', color: 'var(--c-text-faint)', flexShrink: 0 }}>
          {expanded ? '▲ Hide' : '▶ Results'}
        </span>
      </button>

      {/* Expanded test results */}
      {expanded && (
        <div style={{ padding: '0 16px 12px' }}>
          {tests.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {tests.map((t, i) => <TestResultRow key={i} test={t} />)}
            </div>
          ) : (
            <pre style={{
              margin: 0, fontSize: '0.63rem', fontFamily: 'var(--font-mono)',
              color: 'var(--c-text-faint)', whiteSpace: 'pre-wrap', lineHeight: 1.6,
              background: 'var(--c-bg)', padding: '10px 12px', borderRadius: 6,
              maxHeight: 240, overflow: 'auto',
            }}>
              {run.output || 'No output captured.'}
            </pre>
          )}
          {tests.length > 0 && run.output && (
            <details style={{ marginTop: 8 }}>
              <summary style={{
                fontSize: '0.67rem', color: 'var(--c-text-faint)',
                cursor: 'pointer', padding: '2px 0',
              }}>
                Raw output
              </summary>
              <pre style={{
                marginTop: 6, fontSize: '0.62rem', fontFamily: 'var(--font-mono)',
                color: 'var(--c-text-faint)', whiteSpace: 'pre-wrap', lineHeight: 1.5,
                background: 'var(--c-bg)', padding: '8px 10px', borderRadius: 6,
                maxHeight: 200, overflow: 'auto',
              }}>
                {run.output}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  )
}

// ── Script card ───────────────────────────────────────────────────────────────

function ScriptCard({ script }: { script: PlaywrightScript }) {
  const qc = useQueryClient()
  const [showHistory, setShowHistory] = useState(false)
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)

  const { data: history = [], isLoading: histLoading, refetch: refetchHistory } = useQuery({
    queryKey: ['playwright-runs', script.id],
    queryFn: () => getPlaywrightRunHistory(script.id),
    enabled: showHistory,
  })

  const deleteMut = useMutation({
    mutationFn: () => deletePlaywrightScript(script.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['playwright-scripts'] }),
  })

  async function handleRun() {
    setRunning(true)
    setRunError(null)
    try {
      await runPlaywrightScript(script.id)
      if (!showHistory) setShowHistory(true)
      await refetchHistory()
    } catch (err: unknown) {
      setRunError(err instanceof Error ? err.message : 'Run failed')
    } finally {
      setRunning(false)
    }
  }

  const lastRun = history[0] ?? null

  return (
    <div style={{
      background: 'var(--c-surface)',
      border: '1px solid var(--c-border)',
      borderRadius: 10,
      overflow: 'hidden',
    }}>
      {/* Card header */}
      <div style={{
        padding: '14px 18px',
        display: 'flex', alignItems: 'flex-start',
        justifyContent: 'space-between', gap: 12,
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Name + badges row */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
            <span style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--c-text)' }}>
              {script.name}
            </span>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.61rem',
              background: 'var(--c-surface-3)', border: '1px solid var(--c-border)',
              borderRadius: 4, padding: '1px 6px', color: 'var(--c-text-faint)',
            }}>
              {script.filename}
            </span>
            {lastRun && (
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.61rem', fontWeight: 700,
                color: statusColor(lastRun.status),
                background: statusBg(lastRun.status),
                borderRadius: 4, padding: '1px 6px',
              }}>
                {statusLabel(lastRun.status)}
              </span>
            )}
          </div>
          {/* Description */}
          {script.description && (
            <p style={{ margin: '0 0 4px', fontSize: '0.74rem', color: 'var(--c-text-faint)', lineHeight: 1.4 }}>
              {script.description}
            </p>
          )}
          {/* Meta */}
          <div style={{
            display: 'flex', gap: 12, fontSize: '0.65rem',
            color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)',
          }}>
            <span>Uploaded {new Date(script.created_at).toLocaleDateString()}</span>
            <span>{script.content_length.toLocaleString()} chars</span>
            {history.length > 0 && (
              <span>{history.length} run{history.length !== 1 ? 's' : ''}</span>
            )}
          </div>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: 6, flexShrink: 0, alignItems: 'center' }}>
          <button
            onClick={handleRun}
            disabled={running}
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '7px 16px', fontSize: '0.78rem',
              background: running ? 'var(--c-surface-3)' : PW_ACCENT,
              color: running ? 'var(--c-text-faint)' : '#fff',
              border: `1px solid ${running ? 'var(--c-border)' : PW_ACCENT_BORDER}`,
              borderRadius: 6, cursor: running ? 'not-allowed' : 'pointer',
              fontWeight: 700, fontFamily: 'var(--font-body)', transition: 'all 0.15s',
            }}
          >
            {running ? '⟳ Running…' : '▶ Run'}
          </button>

          <button
            onClick={() => setShowHistory(h => !h)}
            style={{
              padding: '7px 12px', fontSize: '0.76rem',
              background: showHistory ? PW_ACCENT_BG : 'var(--c-surface-3)',
              border: `1px solid ${showHistory ? PW_ACCENT_BORDER : 'var(--c-border)'}`,
              borderRadius: 6, cursor: 'pointer',
              color: showHistory ? PW_ACCENT : 'var(--c-text-dim)',
              fontFamily: 'var(--font-body)', fontWeight: 500, transition: 'all 0.15s',
            }}
          >
            {showHistory ? '▲ History' : '▼ History'}
          </button>

          <button
            onClick={() => {
              if (window.confirm(`Delete "${script.name}"?`)) deleteMut.mutate()
            }}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--c-text-faint)', fontSize: '0.95rem', padding: '4px 6px',
            }}
          >
            ✕
          </button>
        </div>
      </div>

      {/* Run error */}
      {runError && (
        <div style={{
          padding: '6px 18px 10px', color: 'var(--c-red)', fontSize: '0.75rem',
          fontFamily: 'var(--font-mono)', lineHeight: 1.5,
        }}>
          {runError}
        </div>
      )}

      {/* Run history */}
      {showHistory && (
        <div style={{ borderTop: '1px solid var(--c-border)', background: 'var(--c-surface-2)' }}>
          {/* History header */}
          <div style={{
            padding: '8px 16px', fontSize: '0.65rem',
            color: 'var(--c-text-faint)', letterSpacing: '0.07em',
            textTransform: 'uppercase', fontFamily: 'var(--font-mono)',
            borderBottom: history.length > 0 ? '1px solid var(--c-border)' : 'none',
          }}>
            Run History
          </div>
          {histLoading && (
            <div style={{ padding: '12px 16px', fontSize: '0.75rem', color: 'var(--c-text-faint)' }}>
              Loading…
            </div>
          )}
          {!histLoading && history.length === 0 && (
            <div style={{
              padding: '16px', fontSize: '0.75rem',
              color: 'var(--c-text-faint)', fontStyle: 'italic',
              textAlign: 'center',
            }}>
              No runs yet — click <strong>▶ Run</strong> to execute this script.
            </div>
          )}
          {history.map(run => <RunHistoryRow key={run.id} run={run} />)}
        </div>
      )}
    </div>
  )
}

// ── Main panel ────────────────────────────────────────────────────────────────

export function PlaywrightScriptsPanel({ appId }: { appId?: string }) {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const { data: scripts = [], isLoading } = useQuery({
    queryKey: ['playwright-scripts', appId],
    queryFn: () => listPlaywrightScripts(appId),
    refetchInterval: 30_000,
  })

  async function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadError(null)
    try {
      const content = await file.text()
      // Derive a readable name from the filename
      const name = file.name
        .replace(/\.spec\.(ts|js)$/i, '')
        .replace(/[_-]/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase())
      await uploadPlaywrightScript({
        name,
        filename: file.name,
        script_content: content,
        application_id: appId,
      })
      qc.invalidateQueries({ queryKey: ['playwright-scripts'] })
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div style={{ marginTop: 36 }}>
      {/* Section header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        alignItems: 'center', marginBottom: 16,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 3, height: 18, background: PW_ACCENT, borderRadius: 2 }} />
          <span style={{ fontWeight: 800, fontSize: '0.92rem', color: 'var(--c-text)' }}>
            Playwright Scripts
          </span>
          {scripts.length > 0 && (
            <span style={{
              fontSize: '0.65rem', fontWeight: 700,
              background: PW_ACCENT_BG, color: PW_ACCENT,
              border: `1px solid ${PW_ACCENT_BORDER}`,
              borderRadius: 4, padding: '1px 7px',
              fontFamily: 'var(--font-mono)',
            }}>
              {scripts.length}
            </span>
          )}
          <span style={{
            fontSize: '0.7rem', color: 'var(--c-text-faint)',
            background: 'var(--c-surface-3)', border: '1px solid var(--c-border)',
            borderRadius: 4, padding: '1px 7px', fontFamily: 'var(--font-mono)',
          }}>
            .spec.ts
          </span>
        </div>

        {/* Import button */}
        <div>
          <input
            ref={fileRef}
            type="file"
            accept=".ts,.js,.spec.ts,.spec.js"
            onChange={handleFileSelect}
            style={{ display: 'none' }}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            style={{
              display: 'flex', alignItems: 'center', gap: 7,
              padding: '7px 16px', fontSize: '0.8rem',
              background: PW_ACCENT_BG,
              border: `1px solid ${PW_ACCENT_BORDER}`,
              borderRadius: 6, color: PW_ACCENT, cursor: uploading ? 'not-allowed' : 'pointer',
              fontFamily: 'var(--font-body)', fontWeight: 600, transition: 'all 0.15s',
            }}
            onMouseEnter={e => { if (!uploading) e.currentTarget.style.background = 'rgba(167,139,250,0.22)' }}
            onMouseLeave={e => { e.currentTarget.style.background = PW_ACCENT_BG }}
          >
            <span style={{ fontSize: '0.9rem' }}>↑</span>
            {uploading ? 'Uploading…' : 'Import .spec.ts'}
          </button>
        </div>
      </div>

      {/* Upload error */}
      {uploadError && (
        <div style={{
          color: 'var(--c-red)', fontSize: '0.78rem', marginBottom: 12,
          padding: '8px 14px', background: 'rgba(239,68,68,0.08)',
          border: '1px solid rgba(239,68,68,0.2)', borderRadius: 6,
        }}>
          {uploadError}
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <p style={{ color: 'var(--c-text-muted)', fontSize: '0.78rem' }}>Loading scripts…</p>
      )}

      {/* Empty state */}
      {!isLoading && scripts.length === 0 && (
        <div style={{
          textAlign: 'center', padding: '40px 20px',
          border: `1px dashed ${PW_ACCENT_BORDER}`,
          borderRadius: 10, background: PW_ACCENT_BG,
        }}>
          <div style={{ fontSize: '2rem', marginBottom: 10, opacity: 0.35 }}>⊞</div>
          <div style={{ fontWeight: 700, marginBottom: 6, color: 'var(--c-text)' }}>
            No Playwright scripts imported yet
          </div>
          <div style={{
            color: 'var(--c-text-muted)', fontSize: '0.78rem',
            maxWidth: 420, margin: '0 auto', lineHeight: 1.6,
          }}>
            Import a <code style={{ fontFamily: 'var(--font-mono)', background: 'var(--c-surface-3)', padding: '1px 5px', borderRadius: 3 }}>.spec.ts</code> or{' '}
            <code style={{ fontFamily: 'var(--font-mono)', background: 'var(--c-surface-3)', padding: '1px 5px', borderRadius: 3 }}>.spec.js</code> file
            to run end-to-end API and UI tests directly from Corvin — with full run history and test-level results.
          </div>
          <button
            onClick={() => fileRef.current?.click()}
            style={{
              marginTop: 16, padding: '8px 20px', fontSize: '0.8rem',
              background: PW_ACCENT, color: '#fff', border: 'none',
              borderRadius: 6, cursor: 'pointer', fontWeight: 700,
              fontFamily: 'var(--font-body)',
            }}
          >
            ↑ Import Script
          </button>
        </div>
      )}

      {/* Script cards */}
      {scripts.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {scripts.map(script => (
            <ScriptCard key={script.id} script={script} />
          ))}
        </div>
      )}
    </div>
  )
}
