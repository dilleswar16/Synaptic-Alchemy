import { useQuery } from '@tanstack/react-query'
import { useState, useRef } from 'react'
import { Link } from 'react-router-dom'
import Layout from '../components/Layout'
import {
  fetchInvestigations,
  fetchBriefing,
  fetchBriefingAudio,
  type InvestigationSummary,
  type BriefingPayload,
} from '../api/client'
import { timeAgo, fmtTs } from '../utils/time'
import { useTypewriter } from '../hooks/useTypewriter'
import { STATUS_CLS } from '../components/StatusBadge'
import { listChaosRuns, type ChaosRunRecord } from '../api/client'
import { PredictiveAlertPanel } from '../components/PredictiveAlertPanel'
import { TopologyRadar } from '../components/TopologyRadar'
import { RoiWidget } from '../components/RoiWidget'
import { KpiStrip } from '../components/KpiStrip'
import { ServiceFleetGrid } from '../components/ServiceFleetGrid'
import { ErrorBudgetBurnChart } from '../components/ErrorBudgetBurnChart'
import { DoraSidebar } from '../components/DoraSidebar'
import IncidentHeatmap from '../components/IncidentHeatmap'
import { useTheme } from '../context/ThemeContext'
import { InfoTooltip } from '../components/Section'

// ── Morning Briefing widget ───────────────────────────────────────────────

function getPunchyGreeting(data: BriefingPayload): string {
  const pending = data.high_confidence_pending
  if (pending > 0) {
    return pending === 1
      ? '1 high-confidence investigation needs your decision.'
      : `${pending} investigations need your call — act now.`
  }
  const { high, medium } = data.confidence_breakdown
  const resolved = high + medium
  if (resolved > 1) return `${resolved} investigations resolved. Fleet is holding.`
  if (resolved === 1) return 'Investigation resolved — fleet is holding.'
  if (data.total_investigations === 0) return 'Fleet nominal. All clear this window.'
  return 'All signals observed. Corvin has the floor.'
}

function BriefingWidget({ data }: { data: BriefingPayload }) {
  const greeting = getPunchyGreeting(data)

  const { displayed: narrative, done: typingDone } = useTypewriter(data.narrative, 14)
  const typing = !typingDone

  const urgent = data.high_confidence_pending > 0
  const fmtTime = new Date().toISOString().substring(11, 16) + ' UTC'
  const conf = data.confidence_breakdown
  const confTotal = conf.high + conf.medium + conf.low
  const maxConf = Math.max(conf.high, conf.medium, conf.low, 1)

  // Voice TTS state
  const [voiceState, setVoiceState] = useState<'idle' | 'loading' | 'playing' | 'error'>('idle')
  const [voiceError, setVoiceError] = useState('')
  const audioRef = useRef<HTMLAudioElement | null>(null)

  async function handleVoice() {
    if (voiceState === 'playing') {
      audioRef.current?.pause()
      setVoiceState('idle')
      return
    }
    setVoiceState('loading')
    setVoiceError('')
    try {
      const blob = await fetchBriefingAudio(data.period_hours)
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audioRef.current = audio
      audio.onended = () => { setVoiceState('idle'); URL.revokeObjectURL(url) }
      audio.onerror = () => { setVoiceState('error'); setVoiceError('Playback failed'); URL.revokeObjectURL(url) }
      await audio.play()
      setVoiceState('playing')
    } catch (err) {
      setVoiceState('error')
      setVoiceError((err as Error).message)
    }
  }

  return (
    <div
      className="animate-fade-up"
      style={{
        marginBottom: 16,
        background: 'var(--c-surface)',
        border: `1px solid ${urgent ? 'var(--c-warning-border)' : 'var(--c-border)'}`,
        borderLeft: `3px solid ${urgent ? 'var(--c-signal)' : 'var(--c-border-hi)'}`,
        borderRadius: 'var(--radius-lg)',
        overflow: 'hidden',
        position: 'relative',
      }}
    >

      {/* Header bar */}
      <div style={{
        position: 'relative',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '9px 20px',
        borderBottom: '1px solid var(--c-border)',
        background: 'var(--c-surface-2)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {urgent && (
            <span
              className="animate-pulse-glow"
              style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--c-signal)', display: 'inline-block', flexShrink: 0 }}
            />
          )}
          <span style={{
            fontSize: '0.75rem', fontWeight: 600,
            letterSpacing: '0.03em', textTransform: 'uppercase',
            color: urgent ? 'var(--c-signal)' : 'var(--c-text-muted)',
          }}>
            Daily Briefing
          </span>
          <InfoTooltip text="GPT-5.1 synthesised summary of the last 24-hour operational window. Combines investigation outcomes, SLO health, confidence levels, and service activity into a single executive-ready narrative. Refreshes every hour." />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-text-faint)' }}>
            {fmtTime} · {data.period_hours}h window
          </span>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.6875rem',
            padding: '2px 8px', borderRadius: 4,
            background: 'var(--c-surface-3)',
            color: 'var(--c-text-muted)',
          }}>
            GPT-5.1
          </span>
          {/* Voice button */}
          <button
            onClick={handleVoice}
            title={voiceState === 'playing' ? 'Stop voice briefing' : 'Play voice briefing (Azure TTS)'}
            style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.65rem', fontWeight: 700,
              padding: '3px 9px', borderRadius: 6, cursor: 'pointer',
              background: voiceState === 'playing' ? 'var(--c-info-bg)' : 'var(--c-signal-light)',
              color: voiceState === 'playing' ? 'var(--c-info)' : voiceState === 'error' ? 'var(--c-error)' : 'var(--c-signal)',
              border: `1px solid ${voiceState === 'playing' ? 'var(--c-info-border)' : 'var(--c-signal-dim)'}`,
              transition: 'all 0.15s',
            }}
          >
            {voiceState === 'loading' ? '…' : voiceState === 'playing' ? '⏹ Stop' : '▶ Hear'}
          </button>
          {voiceState === 'error' && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-error)' }}>
              {voiceError}
            </span>
          )}
        </div>
      </div>

      {/* Body */}
      <div style={{ position: 'relative', padding: '20px 24px 18px', display: 'grid', gridTemplateColumns: '1fr auto', gap: 24 }}>
        {/* Left: greeting + narrative + chips */}
        <div>
          {/* Punchy operational greeting */}
          <div style={{
            fontFamily: 'var(--font-display)', fontWeight: 800,
            fontSize: '1.3rem', letterSpacing: '-0.02em',
            color: urgent ? 'var(--c-signal)' : 'var(--c-text)',
            marginBottom: 12,
          }}>
            {greeting}
          </div>

          {/* Typewriter narrative */}
          <div style={{
            fontFamily: 'var(--font-body)', fontSize: '0.9rem', lineHeight: 1.75,
            color: 'var(--c-text-dim)', marginBottom: 18,
            minHeight: '4.4em',
          }}>
            {narrative}
            {/* Blinking cursor while typing */}
            <span style={{
              display: 'inline-block', width: 2, height: '0.85em', verticalAlign: 'middle',
              background: 'var(--c-signal)', marginLeft: 2,
              animation: typing ? 'signal-pulse 0.7s ease-in-out infinite' : 'none',
              opacity: typing ? 1 : 0,
              transition: 'opacity 0.3s',
            }} />
          </div>

          {/* Alert chips */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
            {data.high_confidence_pending > 0 && (
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                fontSize: '0.75rem', fontWeight: 500,
                padding: '4px 10px', borderRadius: 6,
                background: 'var(--c-warning-bg)',
                border: '1px solid var(--c-warning-border)',
                color: 'var(--c-warning)',
              }}>
                <span style={{ width: 5, height: 5, borderRadius: '50%', background: 'var(--c-warning)', display: 'inline-block', flexShrink: 0 }} />
                {data.high_confidence_pending} high-conf needs approval
              </span>
            )}
            {data.top_services.map((svc, i) => (
              <span key={i} style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.68rem',
                padding: '4px 10px', borderRadius: 6,
                background: 'var(--c-surface-2)',
                border: '1px solid var(--c-border-hi)',
                color: 'var(--c-text-dim)',
              }}>
                {svc.service} <span style={{ color: 'var(--c-text-faint)' }}>×{svc.count}</span>
              </span>
            ))}
          </div>
        </div>

        {/* Right: confidence mini-chart */}
        {confTotal > 0 && (
          <div style={{
            display: 'flex', flexDirection: 'column', justifyContent: 'center',
            gap: 8, minWidth: 140,
            borderLeft: '1px solid var(--c-border)',
            paddingLeft: 24,
          }}>
            <div style={{
              fontSize: '0.6875rem', fontWeight: 600,
              letterSpacing: '0.03em', textTransform: 'uppercase',
              color: 'var(--c-text-faint)', marginBottom: 4,
            }}>
              Confidence
            </div>
            {[
              { label: 'HIGH',   value: conf.high,   color: 'var(--c-green)'  },
              { label: 'MEDIUM', value: conf.medium, color: 'var(--c-yellow)' },
              { label: 'LOW',    value: conf.low,    color: 'var(--c-red)'    },
            ].map(b => (
              <div key={b.label} style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                <span style={{
                  fontSize: '0.6875rem', fontWeight: 500,
                  letterSpacing: '0.03em', textTransform: 'uppercase',
                  color: b.value > 0 ? 'var(--c-text-muted)' : 'var(--c-text-faint)',
                  minWidth: 44,
                }}>
                  {b.label}
                </span>
                <div style={{
                  height: 4, borderRadius: 2,
                  width: b.value > 0 ? `${Math.max((b.value / maxConf) * 72, 6)}px` : '4px',
                  background: b.value > 0 ? b.color : 'var(--c-surface-3)',
                  transition: 'width 0.6s ease-out',
                }} />
                <span style={{
                  fontFamily: 'var(--font-mono)', fontWeight: 700,
                  fontSize: '0.72rem',
                  color: b.value > 0 ? b.color : 'var(--c-text-faint)',
                  minWidth: 18,
                }}>
                  {b.value > 0 ? b.value : '·'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}



// ── War Games Launch Pad (dashboard widget) ───────────────────────────────────

const RUN_STATUS_META: Record<string, { color: string; icon: string }> = {
  armed:     { color: '#b45309',        icon: '⚡' },
  running:   { color: 'var(--c-info)',  icon: '⟳' },
  completed: { color: 'var(--c-green)', icon: '✓' },
  failed:    { color: 'var(--c-red)',   icon: '✗' },
  aborted:   { color: 'var(--c-text-faint)', icon: '⊘' },
}

function WarGamesLaunchPad() {
  const { data: runs = [] } = useQuery<ChaosRunRecord[]>({
    queryKey: ['chaos-runs-dashboard'],
    queryFn: () => listChaosRuns(5),
    refetchInterval: 30_000,
    retry: false,
  })

  const activeRun = runs.find(r => r.status === 'running')
  const k8sRuns = runs.filter(r => r.experiment_type.startsWith('k8s_'))
  const totalRuns = runs.length

  return (
    <div style={{ marginTop: 40, borderTop: '1px solid var(--c-border)', paddingTop: 40, marginBottom: 40 }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, marginBottom: 20 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ fontSize: '0.7rem', color: 'var(--c-text-muted)', fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
              War Games
            </span>
            <InfoTooltip text="Chaos engineering control panel. Level-1 experiments run real kubectl commands against your AKS cluster with guaranteed auto-rollback. Alert simulations test Corvin's detection pipeline without touching infrastructure." />
          </div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.15rem', fontWeight: 800, color: 'var(--c-text)', margin: 0, letterSpacing: '-0.02em' }}>
            Chaos Experiment Studio
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: '0.77rem', color: 'var(--c-text-faint)', lineHeight: 1.5 }}>
            Deliberately break things to prove the system holds — or find what breaks before production does.
          </p>
        </div>
        <Link
          to="/war-games"
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '7px 16px', fontSize: '0.78rem', fontWeight: 600,
            background: 'var(--c-surface-2)', border: '1px solid var(--c-border)',
            borderRadius: 8, color: 'var(--c-text-dim)', textDecoration: 'none',
            flexShrink: 0, whiteSpace: 'nowrap', transition: 'border-color 0.15s',
          }}
        >
          Open Studio →
        </Link>
      </div>

      {/* Active run alert */}
      {activeRun && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '10px 16px', marginBottom: 16,
          background: 'rgba(100,160,255,0.08)', border: '1px solid rgba(100,160,255,0.3)',
          borderRadius: 8,
        }}>
          <span style={{ animation: 'spin 1.5s linear infinite', fontSize: '1rem' }}>⟳</span>
          <div style={{ flex: 1 }}>
            <span style={{ fontWeight: 700, fontSize: '0.82rem', color: 'var(--c-info)' }}>
              Experiment Running: {activeRun.experiment_name}
            </span>
            <span style={{ fontSize: '0.72rem', color: 'var(--c-text-faint)', marginLeft: 10, fontFamily: 'var(--font-mono)' }}>
              {activeRun.service_name} · {activeRun.namespace}
            </span>
          </div>
          <Link to="/war-games" style={{ fontSize: '0.72rem', color: 'var(--c-info)', textDecoration: 'none', fontWeight: 600 }}>
            View →
          </Link>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Experiment categories */}
        <div style={{
          background: 'var(--c-surface)', border: '1px solid var(--c-border)',
          borderRadius: 10, overflow: 'hidden',
        }}>
          <div style={{
            padding: '10px 16px', background: 'var(--c-surface-2)',
            borderBottom: '1px solid var(--c-border)',
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <span>⚗️</span>
            <span style={{ fontWeight: 700, fontSize: '0.75rem' }}>Experiment Types</span>
          </div>
          {[
            { icon: '💥', label: 'Pod Termination', desc: 'Force-delete pods, measure restart time', blast: 'LIMITED', blastColor: 'var(--c-green)' },
            { icon: '📉', label: 'Replica Scale-Down', desc: 'Reduce to 1 replica, test HPA recovery', blast: 'MODERATE', blastColor: '#b45309' },
            { icon: '🔥', label: 'Resource Pressure', desc: 'Throttle CPU/memory, trigger OOMKill', blast: 'MODERATE', blastColor: '#b45309' },
            { icon: '⏸', label: 'Rollout Pause', desc: 'Pause deployment, detect stuck release', blast: 'LIMITED', blastColor: 'var(--c-green)' },
            { icon: '🌊', label: 'Cascading Failure', desc: 'Scale to 0, trigger cross-service cascade', blast: 'WIDE', blastColor: 'var(--c-red)' },
          ].map(exp => (
            <div key={exp.label} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '9px 16px', borderBottom: '1px solid var(--c-border)',
              fontSize: '0.75rem',
            }}>
              <span style={{ fontSize: '1rem', flexShrink: 0 }}>{exp.icon}</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, color: 'var(--c-text)', marginBottom: 1 }}>{exp.label}</div>
                <div style={{ color: 'var(--c-text-faint)', fontSize: '0.68rem' }}>{exp.desc}</div>
              </div>
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.58rem', fontWeight: 700,
                color: exp.blastColor, background: `${exp.blastColor}18`,
                border: `1px solid ${exp.blastColor}30`,
                borderRadius: 3, padding: '1px 5px', flexShrink: 0,
              }}>
                {exp.blast}
              </span>
            </div>
          ))}
        </div>

        {/* Recent runs */}
        <div style={{
          background: 'var(--c-surface)', border: '1px solid var(--c-border)',
          borderRadius: 10, overflow: 'hidden',
        }}>
          <div style={{
            padding: '10px 16px', background: 'var(--c-surface-2)',
            borderBottom: '1px solid var(--c-border)',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span>📋</span>
              <span style={{ fontWeight: 700, fontSize: '0.75rem' }}>Recent Runs</span>
            </div>
            {totalRuns > 0 && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--c-text-faint)' }}>
                {k8sRuns.length} kubectl · {totalRuns - k8sRuns.length} simulated
              </span>
            )}
          </div>
          {runs.length === 0 ? (
            <div style={{ padding: '32px 16px', textAlign: 'center' }}>
              <div style={{ fontSize: '1.6rem', opacity: 0.3, marginBottom: 8 }}>⚗️</div>
              <div style={{ fontSize: '0.78rem', color: 'var(--c-text-muted)', marginBottom: 12 }}>No experiments run yet</div>
              <Link
                to="/war-games"
                style={{
                  fontSize: '0.75rem', fontWeight: 600, padding: '6px 14px',
                  background: 'var(--c-surface-2)', border: '1px solid var(--c-border)',
                  borderRadius: 6, color: 'var(--c-text-dim)', textDecoration: 'none',
                }}
              >
                Open Chaos Studio →
              </Link>
            </div>
          ) : (
            runs.map(run => {
              const meta = RUN_STATUS_META[run.status] ?? RUN_STATUS_META.failed
              const isK8s = run.experiment_type.startsWith('k8s_')
              const d = Date.now() - new Date(run.created_at).getTime()
              const ago = d < 60_000 ? `${Math.floor(d / 1000)}s ago` : d < 3_600_000 ? `${Math.floor(d / 60_000)}m ago` : `${Math.floor(d / 3_600_000)}h ago`
              return (
                <div key={run.id} style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '9px 16px', borderBottom: '1px solid var(--c-border)',
                }}>
                  <span style={{ color: meta.color, fontSize: '0.85rem', flexShrink: 0 }}>{meta.icon}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '0.74rem', fontWeight: 600, color: 'var(--c-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {run.experiment_name || run.experiment_type}
                    </div>
                    <div style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)' }}>
                      {run.service_name}
                    </div>
                  </div>
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.58rem', fontWeight: 700,
                    color: isK8s ? 'var(--c-green)' : '#b45309',
                    background: isK8s ? 'rgba(34,197,94,0.1)' : 'rgba(251,191,36,0.1)',
                    border: `1px solid ${isK8s ? 'rgba(34,197,94,0.25)' : 'rgba(251,191,36,0.25)'}`,
                    borderRadius: 3, padding: '1px 5px', flexShrink: 0,
                  }}>
                    {isK8s ? 'kubectl' : 'sim'}
                  </span>
                  <span style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                    {ago}
                  </span>
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { theme: _theme } = useTheme()

  const { data: recent } = useQuery<(InvestigationSummary & { approval_status?: string })[]>({
    queryKey: ['investigations'],
    queryFn: fetchInvestigations,
    refetchInterval: 30_000,
  })

  const { data: briefing } = useQuery<BriefingPayload>({
    queryKey: ['briefing'],
    queryFn: () => fetchBriefing(24),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: false,
  })

  const top5 = (recent ?? []).slice(0, 5)

  return (
    <Layout>
      {/* ── 1. KPI STRIP (sticky) ──────────────────────────────────────── */}
      <KpiStrip />

      {/* ── 2. AI BRIEFING (full-width, always visible) ───────────────── */}
      {briefing
        ? <BriefingWidget data={briefing} />
        : (
          <div style={{
            marginBottom: 16,
            padding: '14px 20px',
            background: 'var(--c-surface)',
            border: '1px solid var(--c-border)',
            borderRadius: 'var(--radius-lg)',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.72rem',
            color: 'var(--c-text-faint)',
          }}>
            Loading AI briefing…
          </div>
        )
      }

      {/* ── 3. FLEET VIEW: Service Grid + DORA sidebar ────────────────── */}
      <div className="dash-fleet-view">
        <ServiceFleetGrid />
        <DoraSidebar />
      </div>

      {/* ── 4. ERROR BUDGET BURN CHART (full width) ───────────────────── */}
      <ErrorBudgetBurnChart />

      {/* ── 5. OPS ROW: Investigation Queue + Predictive Alerts ───────── */}
      <div className="dash-ops-row">
        {/* Left: top-5 investigation queue */}
        <div className="panel dash-inv-queue animate-fade-up">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <span style={{
              display: 'flex', alignItems: 'center', gap: 6,
              fontFamily: 'var(--font-display)', fontSize: '0.75rem', fontWeight: 700,
              textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--c-text-muted)',
            }}>
              Recent Investigations
              <InfoTooltip text="The 5 most recent Corvin investigation events for this fleet. Each row links to the full investigation — RCA, evidence chain, fix strategy, and execution log. Refreshes every 30 seconds." />
            </span>
            <Link to="/investigations" style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.7rem', fontWeight: 700,
              color: 'var(--c-signal)', textDecoration: 'none', letterSpacing: '0.04em',
            }}>
              View all →
            </Link>
          </div>
          {/* Table header */}
          <div style={{
            display: 'grid', gridTemplateColumns: '90px 1fr 120px 68px 16px',
            gap: 16, padding: '7px 10px',
            borderBottom: '1px solid var(--c-border-hi)',
            background: 'var(--c-surface-2)',
            borderRadius: '6px 6px 0 0',
          }}>
            {['TIME', 'SERVICE', 'STATUS', 'AGO', ''].map((h, i) => (
              <span key={i} style={{
                fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 700,
                letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--c-text-muted)',
              }}>{h}</span>
            ))}
          </div>
          {top5.length === 0 ? (
            <div style={{ padding: '32px 12px', textAlign: 'center', color: 'var(--c-text-muted)', fontSize: '0.8rem' }}>
              No investigations yet.{' '}
              <Link to="/investigations" style={{ color: 'var(--c-accent)', fontWeight: 600, textDecoration: 'none' }}>
                Start one
              </Link>
            </div>
          ) : (
            top5.map((inv, i) => (
              <Link
                key={inv.request_id}
                to={`/investigations/${inv.request_id}`}
                className="log-row animate-fade-up"
                style={{ gridTemplateColumns: '90px 1fr 120px 68px 16px', animationDelay: `${i * 30}ms` }}
              >
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-faint)' }}>
                  {fmtTs(inv.completed_at ?? inv.created_at)}
                </span>
                <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.85rem', color: 'var(--c-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {inv.service_name}
                </span>
                <span className={`badge ${STATUS_CLS[inv.approval_status ?? 'pending'] ?? 'badge-pending'}`}>
                  {inv.approval_status ?? 'pending'}
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-faint)' }}>
                  {timeAgo(inv.completed_at ?? inv.created_at)}
                </span>
                <span style={{ color: 'var(--c-text-faint)', fontSize: '0.75rem' }}>→</span>
              </Link>
            ))
          )}
        </div>

        {/* Right: predictive alerts */}
        <PredictiveAlertPanel />
      </div>

      {/* ── 5. TOPOLOGY (full width) ────────────────────────────────── */}
      <TopologyRadar />

      {/* ── 5b. INCIDENT HEATMAP (Feature 9) ─────────────────────── */}
      <div className="panel animate-fade-up" style={{ marginTop: 20, padding: '20px 24px' }}>
        <IncidentHeatmap days={90} />
      </div>

      {/* ── 6. ROI ───────────────────────────────────────────────────── */}
      <div style={{ marginBottom: 40 }}>
        <RoiWidget />
      </div>

      {/* ── 7. WAR GAMES LAUNCH PAD ─────────────────────────────────── */}
      <WarGamesLaunchPad />
    </Layout>
  )
}

