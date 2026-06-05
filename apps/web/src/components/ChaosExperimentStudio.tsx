/**
 * ChaosExperimentStudio — Level-1 Kubernetes Chaos Engineering
 *
 * Two-panel layout:
 *   Left  — Experiment library: 5 K8s experiments + 4 alert simulations
 *   Right — Selected experiment details: hypothesis, commands, blast radius,
 *           prerequisites, arm → confirm → execute → live status → history
 *
 * Safety gates:
 *   1. ARM   — shows exact kubectl commands, requires user to read
 *   2. CONFIRM — red button + "EXECUTE" text confirmation
 *   3. ABORT — available any time during running state
 *   4. Auto-rollback — backend restores cluster state after duration
 */
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  armChaosExperiment,
  executeChaosRun,
  getChaosRunStatus,
  abortChaosRun,
  listChaosRuns,
  simulateAlert,
  type ChaosRunRecord,
  type SimulatorPreset,
} from '../api/client'
import { useApplicationPresets } from '../hooks/useApplicationData'

// ── Constants ─────────────────────────────────────────────────────────────────

const BLAST_COLORS: Record<string, { bg: string; border: string; text: string; label: string }> = {
  limited:  { bg: 'rgba(34,197,94,0.08)',  border: 'rgba(34,197,94,0.25)',  text: 'var(--c-green)',   label: 'LIMITED' },
  moderate: { bg: 'rgba(251,191,36,0.08)', border: 'rgba(251,191,36,0.25)', text: '#b45309',          label: 'MODERATE' },
  wide:     { bg: 'rgba(239,68,68,0.08)',  border: 'rgba(239,68,68,0.25)',  text: 'var(--c-red)',     label: 'WIDE' },
}

const STATUS_META: Record<string, { color: string; bg: string; label: string; icon: string }> = {
  armed:     { color: '#b45309',        bg: 'rgba(251,191,36,0.1)',   label: 'ARMED',     icon: '⚡' },
  running:   { color: 'var(--c-info)',  bg: 'rgba(100,160,255,0.1)', label: 'RUNNING',   icon: '⟳' },
  completed: { color: 'var(--c-green)', bg: 'rgba(34,197,94,0.1)',   label: 'COMPLETED', icon: '✓' },
  failed:    { color: 'var(--c-red)',   bg: 'rgba(239,68,68,0.1)',   label: 'FAILED',    icon: '✗' },
  aborted:   { color: 'var(--c-text-faint)', bg: 'var(--c-surface-3)', label: 'ABORTED', icon: '⊘' },
}

const K8S_ICON_MAP: Record<string, string> = {
  k8s_pod_kill:          '💥',
  k8s_scale_down:        '📉',
  k8s_resource_pressure: '🔥',
  k8s_rollout_pause:     '⏸',
  k8s_cascading:         '🌊',
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function isK8sExperiment(preset: SimulatorPreset) {
  return preset.scenario_id.startsWith('k8s_')
}

function experimentTypeFromScenario(scenarioId: string): string {
  const prefixes = ['k8s_pod_kill', 'k8s_scale_down', 'k8s_resource_pressure', 'k8s_rollout_pause', 'k8s_cascading']
  return prefixes.find(p => scenarioId.startsWith(p)) ?? 'unknown'
}

function reltime(iso: string) {
  const d = Date.now() - new Date(iso).getTime()
  const s = Math.floor(d / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  return `${Math.floor(m / 60)}h ago`
}

function StatusBadge({ status }: { status: string }) {
  const meta = STATUS_META[status] ?? STATUS_META.failed
  return (
    <span style={{
      fontFamily: 'var(--font-mono)', fontSize: '0.61rem', fontWeight: 700,
      color: meta.color, background: meta.bg,
      border: `1px solid ${meta.color}30`,
      borderRadius: 4, padding: '1px 7px', letterSpacing: '0.06em',
    }}>
      {meta.icon} {meta.label}
    </span>
  )
}

// ── Run history row ───────────────────────────────────────────────────────────

function RunHistoryRow({ run }: { run: ChaosRunRecord }) {
  const blast = run.catalogue?.blast_radius
  const blastMeta = BLAST_COLORS[blast ?? 'limited']
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '9px 14px',
      borderBottom: '1px solid var(--c-border)',
      fontSize: '0.75rem',
    }}>
      <StatusBadge status={run.status} />
      <span style={{ flex: 1, color: 'var(--c-text)', fontWeight: 600 }}>
        {run.experiment_name || run.experiment_type}
      </span>
      <span style={{ color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)', fontSize: '0.67rem' }}>
        {run.service_name}
      </span>
      {blast && (
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: '0.6rem', fontWeight: 700,
          color: blastMeta.text, background: blastMeta.bg,
          border: `1px solid ${blastMeta.border}`,
          borderRadius: 3, padding: '1px 5px',
        }}>
          {blastMeta.label}
        </span>
      )}
      <span style={{ color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)', fontSize: '0.65rem' }}>
        {reltime(run.created_at)}
        {run.duration_seconds ? ` · ${run.duration_seconds}s` : ''}
      </span>
    </div>
  )
}

// ── Live run panel ────────────────────────────────────────────────────────────

function LiveRunPanel({ runId, onDone }: { runId: string; onDone: () => void }) {
  const qc = useQueryClient()
  const [aborting, setAborting] = useState(false)

  const { data: run } = useQuery({
    queryKey: ['chaos-run', runId],
    queryFn: () => getChaosRunStatus(runId),
    refetchInterval: (q) => {
      const status = q.state.data?.status
      return status === 'running' || status === 'armed' ? 2000 : false
    },
  })

  useEffect(() => {
    if (run && !['running', 'armed'].includes(run.status)) {
      qc.invalidateQueries({ queryKey: ['chaos-runs'] })
      onDone()
    }
  }, [run?.status])

  const abortMut = useMutation({
    mutationFn: () => abortChaosRun(runId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['chaos-run', runId] }); setAborting(false) },
  })

  if (!run) return <div style={{ padding: 16, color: 'var(--c-text-faint)', fontSize: '0.8rem' }}>Loading…</div>

  const meta = STATUS_META[run.status] ?? STATUS_META.running
  const elapsed = run.started_at
    ? Math.floor((Date.now() - new Date(run.started_at).getTime()) / 1000)
    : 0

  return (
    <div style={{
      border: `1px solid ${meta.color}40`,
      borderRadius: 10, overflow: 'hidden',
      background: 'var(--c-surface)',
    }}>
      {/* Status header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '12px 16px',
        background: meta.bg,
        borderBottom: `1px solid ${meta.color}30`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: '1.1rem', animation: run.status === 'running' ? 'spin 1.5s linear infinite' : 'none' }}>
            {meta.icon}
          </span>
          <div>
            <div style={{ fontWeight: 700, fontSize: '0.82rem', color: meta.color }}>
              {run.experiment_name} — {meta.label}
            </div>
            <div style={{ fontSize: '0.68rem', fontFamily: 'var(--font-mono)', color: 'var(--c-text-faint)', marginTop: 2 }}>
              {run.service_name} · {run.namespace}
              {run.started_at && ` · ${elapsed}s elapsed`}
            </div>
          </div>
        </div>
        {run.status === 'running' && (
          <button
            onClick={() => { setAborting(true); abortMut.mutate() }}
            disabled={aborting}
            style={{
              padding: '5px 14px', fontSize: '0.72rem', fontWeight: 700,
              background: 'rgba(239,68,68,0.15)', color: 'var(--c-red)',
              border: '1px solid rgba(239,68,68,0.3)', borderRadius: 6,
              cursor: aborting ? 'not-allowed' : 'pointer', fontFamily: 'var(--font-body)',
            }}
          >
            {aborting ? 'Aborting…' : '⏹ Abort & Rollback'}
          </button>
        )}
      </div>

      {/* Progress bar for running */}
      {run.status === 'running' && (
        <div style={{ height: 3, background: 'var(--c-border)' }}>
          <div style={{
            height: '100%',
            width: `${Math.min(100, (elapsed / run.duration_seconds) * 100)}%`,
            background: 'var(--c-info)',
            transition: 'width 1s linear',
          }} />
        </div>
      )}

      {/* Output log */}
      {run.output && (
        <pre style={{
          margin: 0, padding: '12px 16px',
          fontFamily: 'var(--font-mono)', fontSize: '0.67rem',
          color: 'var(--c-text-dim)', lineHeight: 1.65,
          whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          maxHeight: 200, overflowY: 'auto',
          background: 'var(--c-bg)',
        }}>
          {run.output}
        </pre>
      )}

      {/* Rollback status */}
      {run.rollback_status && (
        <div style={{
          padding: '8px 16px', fontSize: '0.72rem',
          color: run.rollback_status === 'complete' ? 'var(--c-green)' : 'var(--c-warning)',
          borderTop: '1px solid var(--c-border)',
          background: 'var(--c-surface-2)',
          fontFamily: 'var(--font-mono)',
        }}>
          {run.rollback_status === 'complete' ? '✓ Rollback complete — cluster restored' : `⚠ Rollback: ${run.rollback_status}`}
        </div>
      )}
    </div>
  )
}

// ── Experiment detail panel ───────────────────────────────────────────────────

function ExperimentDetail({ preset }: { preset: SimulatorPreset }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const isK8s = isK8sExperiment(preset)
  const expType = experimentTypeFromScenario(preset.scenario_id)
  const blast = isK8s ? (
    expType.includes('cascading') ? 'wide' :
    expType.includes('resource') || expType.includes('scale') ? 'moderate' : 'limited'
  ) : null
  const blastMeta = blast ? BLAST_COLORS[blast] : null

  // ARM flow state
  const [armedRun, setArmedRun] = useState<ChaosRunRecord | null>(null)
  const [confirmText, setConfirmText] = useState('')
  const [liveRunId, setLiveRunId] = useState<string | null>(null)
  const [armError, setArmError] = useState<string | null>(null)

  const armMut = useMutation({
    mutationFn: () => armChaosExperiment(preset.id, preset.environment),
    onSuccess: (run) => { setArmedRun(run); setArmError(null) },
    onError: (e: Error) => setArmError(e.message),
  })

  const execMut = useMutation({
    mutationFn: () => executeChaosRun(armedRun!.id),
    onSuccess: (run) => { setLiveRunId(run.id); setArmedRun(null); setConfirmText('') },
    onError: (e: Error) => setArmError(e.message),
  })

  const [simFiring, setSimFiring] = useState(false)
  const [simError, setSimError] = useState<string | null>(null)

  async function fireSimulation() {
    setSimFiring(true); setSimError(null)
    try {
      const result = await simulateAlert({
        service_name: preset.service_name,
        environment: preset.environment,
        scenario: preset.scenario_id,
      })
      navigate(`/investigations/${result.request_id}`)
    } catch (e) {
      setSimError(e instanceof Error ? e.message : 'Simulation failed')
      setSimFiring(false)
    }
  }

  function reset() { setArmedRun(null); setConfirmText(''); setArmError(null); setLiveRunId(null) }

  // catalogue: armedRun?.catalogue — available for future hypothesis display
  const prerequisites: string[] = (isK8s ? [
    'No active P1 incident on the target service',
    'Cluster reachable from the Corvin server (kubectl on PATH)',
    ...(expType.includes('cascading') ? ['⚠️ HIGH IMPACT: All pods for this service will be terminated'] : []),
  ] : []) as string[]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Experiment header */}
      <div style={{
        padding: '16px 20px',
        background: 'var(--c-surface-2)',
        border: '1px solid var(--c-border)',
        borderRadius: 10,
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: '1.5rem' }}>
              {isK8s ? (K8S_ICON_MAP[expType] ?? '⚗️') : '☣️'}
            </span>
            <div>
              <div style={{ fontWeight: 800, fontSize: '0.92rem', color: 'var(--c-text)', marginBottom: 3 }}>
                {preset.label}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{
                  fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.07em',
                  fontFamily: 'var(--font-mono)', textTransform: 'uppercase',
                  color: isK8s ? 'var(--c-green)' : 'var(--c-warning)',
                  background: isK8s ? 'rgba(34,197,94,0.1)' : 'rgba(251,191,36,0.1)',
                  border: `1px solid ${isK8s ? 'rgba(34,197,94,0.25)' : 'rgba(251,191,36,0.25)'}`,
                  borderRadius: 3, padding: '1px 6px',
                }}>
                  {isK8s ? 'LEVEL 1 · REAL KUBECTL' : 'ALERT SIMULATION'}
                </span>
                {blastMeta && (
                  <span style={{
                    fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.07em',
                    fontFamily: 'var(--font-mono)', textTransform: 'uppercase',
                    color: blastMeta.text, background: blastMeta.bg,
                    border: `1px solid ${blastMeta.border}`,
                    borderRadius: 3, padding: '1px 6px',
                  }}>
                    {blastMeta.label} BLAST
                  </span>
                )}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 6, flexShrink: 0, fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-faint)' }}>
            <span>{preset.service_name}</span>
            <span>·</span>
            <span>{preset.environment}</span>
          </div>
        </div>

        <p style={{ margin: 0, fontSize: '0.77rem', color: 'var(--c-text-faint)', lineHeight: 1.65 }}>
          {preset.description}
        </p>
      </div>

      {/* Live run */}
      {liveRunId && (
        <LiveRunPanel runId={liveRunId} onDone={() => { qc.invalidateQueries({ queryKey: ['chaos-runs'] }) }} />
      )}

      {!liveRunId && (
        <>
          {/* Hypothesis (K8s only) */}
          {isK8s && (
            <div style={{
              padding: '14px 16px',
              background: 'rgba(0,122,188,0.05)',
              border: '1px solid rgba(0,122,188,0.2)',
              borderRadius: 8,
            }}>
              <div style={{ fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--c-primary)', marginBottom: 6 }}>
                Hypothesis
              </div>
              <p style={{ margin: 0, fontSize: '0.77rem', color: 'var(--c-text-dim)', lineHeight: 1.6 }}>
                {armedRun?.catalogue?.hypothesis ?? (
                  expType === 'k8s_pod_kill' ? 'When a pod is force-terminated, AKS should reschedule and restart it within 60 seconds. No more than 5% of in-flight requests should fail during the recovery window.' :
                  expType === 'k8s_scale_down' ? 'With a single replica, the service should still respond to health checks. MTTR for the single pod should be < 10s.' :
                  expType === 'k8s_resource_pressure' ? 'Corvin should detect elevated CPU throttling or memory pressure within 5 minutes. MTTR after limit restoration should be < 2 min.' :
                  expType === 'k8s_rollout_pause' ? 'Corvin should surface a "stuck deployment" detection within the observation window.' :
                  'Corvin should detect the primary outage within 3 minutes AND detect downstream impact on dependent services.'
                )}
              </p>
            </div>
          )}

          {/* Prerequisites */}
          {prerequisites.length > 0 && (
            <div style={{
              padding: '12px 16px',
              background: 'var(--c-surface-2)',
              border: '1px solid var(--c-border)',
              borderRadius: 8,
            }}>
              <div style={{ fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--c-text-muted)', marginBottom: 8 }}>
                Prerequisites
              </div>
              {prerequisites.map((p, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 5 }}>
                  <span style={{ fontSize: '0.7rem', color: 'var(--c-text-faint)', flexShrink: 0, marginTop: 1 }}>□</span>
                  <span style={{ fontSize: '0.74rem', color: p.startsWith('⚠') ? 'var(--c-warning)' : 'var(--c-text-dim)', lineHeight: 1.4 }}>{p}</span>
                </div>
              ))}
            </div>
          )}

          {/* Armed: show command preview + confirm */}
          {armedRun && (
            <div style={{
              border: '1px solid rgba(251,191,36,0.4)',
              borderRadius: 10, overflow: 'hidden',
              background: 'var(--c-surface)',
            }}>
              <div style={{
                padding: '10px 16px',
                background: 'rgba(251,191,36,0.08)',
                borderBottom: '1px solid rgba(251,191,36,0.25)',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              }}>
                <span style={{ fontWeight: 700, fontSize: '0.78rem', color: '#b45309' }}>
                  ⚡ Experiment Armed — Review Commands
                </span>
                <button onClick={reset} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-text-faint)', fontSize: '1rem' }}>×</button>
              </div>
              <div style={{ padding: '12px 16px' }}>
                <div style={{ fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--c-text-muted)', marginBottom: 8 }}>
                  Commands to execute
                </div>
                <pre style={{
                  margin: '0 0 12px', padding: '10px 14px',
                  background: 'var(--c-bg)', border: '1px solid var(--c-border)',
                  borderRadius: 6, fontFamily: 'var(--font-mono)', fontSize: '0.69rem',
                  color: 'var(--c-text-dim)', lineHeight: 1.65, whiteSpace: 'pre-wrap',
                }}>
                  {armedRun.commands.join('\n')}
                </pre>
                {armedRun.rollback_commands.length > 0 && (
                  <>
                    <div style={{ fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--c-text-muted)', marginBottom: 6 }}>
                      Auto-rollback after {armedRun.duration_seconds}s
                    </div>
                    <pre style={{
                      margin: '0 0 14px', padding: '8px 14px',
                      background: 'rgba(34,197,94,0.05)', border: '1px solid rgba(34,197,94,0.2)',
                      borderRadius: 6, fontFamily: 'var(--font-mono)', fontSize: '0.69rem',
                      color: 'var(--c-green)', lineHeight: 1.65, whiteSpace: 'pre-wrap',
                    }}>
                      {armedRun.rollback_commands.join('\n')}
                    </pre>
                  </>
                )}
                <div style={{ fontSize: '0.72rem', color: 'var(--c-text-muted)', marginBottom: 8 }}>
                  Type <strong style={{ fontFamily: 'var(--font-mono)', color: 'var(--c-red)' }}>EXECUTE</strong> to confirm and run
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    value={confirmText}
                    onChange={e => setConfirmText(e.target.value)}
                    placeholder="Type EXECUTE to confirm"
                    style={{
                      flex: 1, padding: '7px 12px',
                      background: 'var(--c-bg)', border: `1px solid ${confirmText === 'EXECUTE' ? 'var(--c-red)' : 'var(--c-border-hi)'}`,
                      borderRadius: 6, color: 'var(--c-text)',
                      fontFamily: 'var(--font-mono)', fontSize: '0.78rem',
                    }}
                    onKeyDown={e => e.key === 'Enter' && confirmText === 'EXECUTE' && execMut.mutate()}
                  />
                  <button
                    onClick={() => execMut.mutate()}
                    disabled={confirmText !== 'EXECUTE' || execMut.isPending}
                    style={{
                      padding: '7px 18px', fontWeight: 700, fontSize: '0.78rem',
                      background: confirmText === 'EXECUTE' ? 'var(--c-red)' : 'var(--c-surface-3)',
                      color: confirmText === 'EXECUTE' ? '#fff' : 'var(--c-text-faint)',
                      border: `1px solid ${confirmText === 'EXECUTE' ? 'var(--c-red)' : 'var(--c-border)'}`,
                      borderRadius: 6, cursor: confirmText === 'EXECUTE' ? 'pointer' : 'not-allowed',
                      fontFamily: 'var(--font-body)', transition: 'all 0.15s',
                    }}
                  >
                    {execMut.isPending ? 'Launching…' : '🔴 Execute'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Errors */}
          {(armError || simError) && (
            <div style={{
              padding: '8px 14px', color: 'var(--c-red)', fontSize: '0.75rem',
              fontFamily: 'var(--font-mono)', background: 'rgba(239,68,68,0.08)',
              border: '1px solid rgba(239,68,68,0.2)', borderRadius: 6,
            }}>
              {armError || simError}
            </div>
          )}

          {/* Primary action buttons */}
          {!armedRun && (
            isK8s ? (
              <button
                onClick={() => armMut.mutate()}
                disabled={armMut.isPending}
                style={{
                  padding: '12px', fontWeight: 700, fontSize: '0.82rem',
                  background: armMut.isPending ? 'var(--c-surface-3)' : 'rgba(251,191,36,0.12)',
                  color: armMut.isPending ? 'var(--c-text-faint)' : '#b45309',
                  border: `1px solid ${armMut.isPending ? 'var(--c-border)' : 'rgba(251,191,36,0.4)'}`,
                  borderRadius: 8, cursor: armMut.isPending ? 'not-allowed' : 'pointer',
                  fontFamily: 'var(--font-body)', width: '100%',
                  transition: 'all 0.15s',
                }}
              >
                {armMut.isPending ? '⟳ Arming…' : '⚡ Arm Experiment'}
              </button>
            ) : (
              <button
                onClick={fireSimulation}
                disabled={simFiring}
                style={{
                  padding: '12px', fontWeight: 700, fontSize: '0.82rem',
                  background: simFiring ? 'var(--c-surface-3)' : 'var(--c-signal)',
                  color: simFiring ? 'var(--c-text-faint)' : '#fff',
                  border: `1px solid ${simFiring ? 'var(--c-border)' : 'var(--c-signal)'}`,
                  borderRadius: 8, cursor: simFiring ? 'not-allowed' : 'pointer',
                  fontFamily: 'var(--font-body)', width: '100%',
                  boxShadow: simFiring ? 'none' : '0 0 20px rgba(220,38,38,0.25)',
                  transition: 'all 0.15s',
                }}
              >
                {simFiring ? '⟳ Firing simulation…' : `⚡ Fire Alert Simulation → ${preset.service_name}`}
              </button>
            )
          )}
        </>
      )}
    </div>
  )
}

// ── Main Studio ───────────────────────────────────────────────────────────────

export function ChaosExperimentStudio() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { data: presets, loading } = useApplicationPresets()
  const [showHistory, setShowHistory] = useState(false)

  const k8sPresets = presets.filter(isK8sExperiment)
  const simPresets = presets.filter(p => !isK8sExperiment(p))
  const selectedPreset = presets.find(p => p.id === selectedId) ?? null

  const { data: runs = [] } = useQuery({
    queryKey: ['chaos-runs'],
    queryFn: () => listChaosRuns(10),
    refetchInterval: 10_000,
  })

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 20, alignItems: 'start' }}>

      {/* ── Left panel: experiment library ─────────────────────────────── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

        {/* Level-1 Kubernetes experiments */}
        <div style={{
          border: '1px solid var(--c-border)',
          borderRadius: 10, overflow: 'hidden',
          background: 'var(--c-surface)',
        }}>
          <div style={{
            padding: '10px 14px',
            background: 'var(--c-surface-2)',
            borderBottom: '1px solid var(--c-border)',
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <span style={{ fontSize: '0.7rem' }}>⚗️</span>
            <span style={{ fontWeight: 700, fontSize: '0.75rem', color: 'var(--c-text)' }}>Level-1 · kubectl Experiments</span>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.6rem', fontWeight: 700,
              color: 'var(--c-green)', background: 'rgba(34,197,94,0.1)',
              border: '1px solid rgba(34,197,94,0.25)', borderRadius: 3, padding: '1px 5px',
            }}>LIVE</span>
          </div>
          {loading ? (
            <div style={{ padding: '12px 14px', fontSize: '0.75rem', color: 'var(--c-text-faint)' }}>Loading…</div>
          ) : k8sPresets.length === 0 ? (
            <div style={{ padding: '12px 14px', fontSize: '0.75rem', color: 'var(--c-text-faint)', fontStyle: 'italic' }}>
              No Level-1 presets found. Add presets in Applications → Simulator Presets.
            </div>
          ) : (
            k8sPresets.map(preset => {
              const expType = experimentTypeFromScenario(preset.scenario_id)
              const blast = expType.includes('cascading') ? 'wide' : expType.includes('resource') || expType.includes('scale') ? 'moderate' : 'limited'
              const blastMeta = BLAST_COLORS[blast]
              const isSelected = selectedId === preset.id
              return (
                <button
                  key={preset.id}
                  onClick={() => setSelectedId(isSelected ? null : preset.id)}
                  style={{
                    display: 'flex', alignItems: 'flex-start', gap: 10,
                    padding: '10px 14px', textAlign: 'left', width: '100%',
                    background: isSelected ? 'rgba(239,68,68,0.06)' : 'none',
                    border: 'none',
                    borderLeft: `3px solid ${isSelected ? 'var(--c-red)' : 'transparent'}`,
                    borderBottom: '1px solid var(--c-border)',
                    cursor: 'pointer', transition: 'all 0.12s',
                  }}
                >
                  <span style={{ fontSize: '1.1rem', flexShrink: 0, marginTop: 1 }}>
                    {K8S_ICON_MAP[expType] ?? '⚗️'}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: '0.76rem', color: isSelected ? 'var(--c-red)' : 'var(--c-text)', marginBottom: 2 }}>
                      {preset.label}
                    </div>
                    <div style={{
                      fontFamily: 'var(--font-mono)', fontSize: '0.63rem',
                      color: blastMeta.text, background: blastMeta.bg,
                      border: `1px solid ${blastMeta.border}`,
                      borderRadius: 3, padding: '0px 5px',
                      display: 'inline-block',
                    }}>
                      {blastMeta.label} BLAST
                    </div>
                  </div>
                </button>
              )
            })
          )}
        </div>

        {/* Alert simulations */}
        <div style={{
          border: '1px solid var(--c-border)',
          borderRadius: 10, overflow: 'hidden',
          background: 'var(--c-surface)',
        }}>
          <div style={{
            padding: '10px 14px',
            background: 'var(--c-surface-2)',
            borderBottom: '1px solid var(--c-border)',
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <span style={{ fontSize: '0.7rem' }}>☣️</span>
            <span style={{ fontWeight: 700, fontSize: '0.75rem', color: 'var(--c-text)' }}>Alert Simulations</span>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.6rem', fontWeight: 700,
              color: '#b45309', background: 'rgba(251,191,36,0.1)',
              border: '1px solid rgba(251,191,36,0.3)', borderRadius: 3, padding: '1px 5px',
            }}>SIMULATED</span>
          </div>
          {simPresets.map(preset => {
            const isSelected = selectedId === preset.id
            return (
              <button
                key={preset.id}
                onClick={() => setSelectedId(isSelected ? null : preset.id)}
                style={{
                  display: 'flex', alignItems: 'flex-start', gap: 10,
                  padding: '10px 14px', textAlign: 'left', width: '100%',
                  background: isSelected ? 'rgba(220,38,38,0.06)' : 'none',
                  border: 'none',
                  borderLeft: `3px solid ${isSelected ? 'var(--c-signal)' : 'transparent'}`,
                  borderBottom: '1px solid var(--c-border)',
                  cursor: 'pointer', transition: 'all 0.12s',
                }}
              >
                <span style={{ fontSize: '1.1rem', flexShrink: 0, marginTop: 1 }}>☣️</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: '0.76rem', color: isSelected ? 'var(--c-signal)' : 'var(--c-text)', marginBottom: 2 }}>
                    {preset.label}
                  </div>
                  <div style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)' }}>
                    {preset.service_name}
                  </div>
                </div>
              </button>
            )
          })}
        </div>

        {/* Run history toggle */}
        {runs.length > 0 && (
          <button
            onClick={() => setShowHistory(h => !h)}
            style={{
              padding: '8px 14px', fontSize: '0.75rem', fontWeight: 600,
              background: 'var(--c-surface-2)', border: '1px solid var(--c-border)',
              borderRadius: 8, cursor: 'pointer', color: 'var(--c-text-dim)',
              fontFamily: 'var(--font-body)', textAlign: 'left',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            }}
          >
            <span>Run History ({runs.length})</span>
            <span>{showHistory ? '▲' : '▼'}</span>
          </button>
        )}
      </div>

      {/* ── Right panel ────────────────────────────────────────────────── */}
      <div>
        {selectedPreset ? (
          <ExperimentDetail key={selectedPreset.id} preset={selectedPreset} />
        ) : (
          <div style={{
            border: '1px dashed var(--c-border)',
            borderRadius: 10, padding: '48px 32px',
            textAlign: 'center',
            background: 'var(--c-surface)',
          }}>
            <div style={{ fontSize: '2.5rem', marginBottom: 12, opacity: 0.3 }}>⚗️</div>
            <div style={{ fontWeight: 700, marginBottom: 8, color: 'var(--c-text)' }}>
              Select an experiment
            </div>
            <p style={{ margin: '0 auto', fontSize: '0.78rem', color: 'var(--c-text-faint)', lineHeight: 1.6, maxWidth: 380 }}>
              Choose a <strong>Level-1 Kubernetes experiment</strong> to run real kubectl chaos against your AKS cluster,
              or an <strong>Alert Simulation</strong> to test Corvin's investigation pipeline without touching infrastructure.
            </p>
            <div style={{ marginTop: 20, display: 'flex', gap: 16, justifyContent: 'center', fontSize: '0.72rem', color: 'var(--c-text-faint)' }}>
              {[
                { icon: '⚗️', label: `${k8sPresets.length} real kubectl experiments` },
                { icon: '☣️', label: `${simPresets.length} alert simulations` },
                { icon: '🔁', label: 'Auto-rollback guaranteed' },
              ].map(item => (
                <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span>{item.icon}</span> {item.label}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Inline history under detail */}
        {showHistory && runs.length > 0 && (
          <div style={{
            marginTop: 16, border: '1px solid var(--c-border)',
            borderRadius: 10, overflow: 'hidden', background: 'var(--c-surface)',
          }}>
            <div style={{
              padding: '9px 14px', background: 'var(--c-surface-2)',
              borderBottom: '1px solid var(--c-border)',
              fontSize: '0.7rem', fontWeight: 700, color: 'var(--c-text-muted)',
              textTransform: 'uppercase', letterSpacing: '0.06em',
            }}>
              Recent Runs
            </div>
            {runs.map(run => <RunHistoryRow key={run.id} run={run} />)}
          </div>
        )}
      </div>
    </div>
  )
}
