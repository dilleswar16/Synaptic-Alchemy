import { useQuery } from '@tanstack/react-query'
import { useState, useRef } from 'react'
import { Link } from 'react-router-dom'
import Layout from '../components/Layout'
import {
  fetchInvestigationStats,
  fetchInvestigations,
  fetchBriefing,
  fetchBriefingAudio,
  type InvestigationStats,
  type InvestigationSummary,
  type BriefingPayload,
} from '../api/client'
import { timeAgo, fmtTs } from '../utils/time'
import { useTypewriter } from '../hooks/useTypewriter'
import { STATUS_CLS } from '../components/StatusBadge'
import { ServiceHealthGauge } from '../components/ServiceHealthGauge'
import { SimulateAlertPanel } from '../components/SimulateAlertPanel'
import { PredictiveAlertPanel } from '../components/PredictiveAlertPanel'
import { TopologyRadar } from '../components/TopologyRadar'
import { RoiWidget } from '../components/RoiWidget'
import { DoraWidget } from '../components/DoraWidget'
import { PlatformPulse } from '../components/PlatformPulse'
import { useTheme } from '../context/ThemeContext'

// ── Morning Briefing widget ───────────────────────────────────────────────

function BriefingWidget({ data }: { data: BriefingPayload }) {
  const hour = new Date().getUTCHours()
  const greeting =
    hour < 12 ? 'GOOD MORNING' : hour < 17 ? 'GOOD AFTERNOON' : 'GOOD EVENING'

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
            GPT-4.1
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
          {/* Greeting */}
          <div style={{
            fontFamily: 'var(--font-display)', fontWeight: 700,
            fontSize: '1.25rem', letterSpacing: '-0.01em',
            color: 'var(--c-text)', marginBottom: 12,
          }}>
            {greeting.charAt(0) + greeting.slice(1).toLowerCase()}, Operator
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
                padding: '4px 10px', borderRadius: 2,
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

// ── Pipeline hero ─────────────────────────────────────────────────────────────

const PIPELINE_STAGES = [
  { stage: 'TRIGGER',     sub: 'Azure alerts' },
  { stage: 'ENRICH',      sub: 'AKS + logs'   },
  { stage: 'INVESTIGATE', sub: 'GPT-4.1 RCA'  },
  { stage: 'APPROVE',     sub: 'Human gate'    },
  { stage: 'EXECUTE',     sub: 'Fix strategy'  },
]

function HeroBand({
  stats,
  recent,
}: {
  stats: InvestigationStats
  recent: (InvestigationSummary & { approval_status?: string })[]
}) {
  const lastTs = recent.length > 0
    ? timeAgo(recent[0].completed_at ?? recent[0].created_at)
    : null

  return (
    <div
      className="animate-fade-up"
      style={{
        position: 'relative',
        overflow: 'hidden',
        marginBottom: 20,
        background: 'var(--c-surface)',
        border: '1px solid var(--c-border)',
        borderRadius: 'var(--radius-lg)',
      }}
    >
      <div style={{ position: 'relative', display: 'grid', gridTemplateColumns: '1fr auto', gap: 0, padding: '28px 32px' }}>

        {/* ── Left: identity + pipeline ── */}
        <div style={{ paddingRight: 32 }}>
          {/* Status beacon */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12 }}>
            <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: 'var(--c-success)', flexShrink: 0 }} />
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.75rem', fontWeight: 500,
              color: 'var(--c-success)',
            }}>
              System Operational
            </span>
          </div>

          <h1 style={{
            margin: '0 0 10px',
            fontFamily: 'var(--font-display)', fontWeight: 700,
            fontSize: '1.75rem', letterSpacing: '-0.02em',
            color: 'var(--c-text)', lineHeight: 1.2,
          }}>
            Operations Center
          </h1>
          <p style={{
            margin: '0 0 28px',
            fontFamily: 'var(--font-body)', fontSize: '0.85rem',
            color: 'var(--c-text-dim)', lineHeight: 1.6, maxWidth: 480,
          }}>
            Azure-native SRE intelligence — enriches live alerts with AKS cluster evidence,
            generates GPT-4.1 root cause analysis, and gates every fix through human approval
            before execution.
          </p>

          {/* Pipeline flow */}
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 0 }}>
            {PIPELINE_STAGES.map((s, i) => (
              <div key={s.stage} style={{ display: 'flex', alignItems: 'flex-start', gap: 0 }}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{
                    display: 'inline-flex', alignItems: 'center', gap: 5,
                    padding: '5px 12px',
                    border: '1px solid var(--c-border-hi)',
                    borderRadius: 6,
                    background: 'var(--c-surface-2)',
                  }}>
                    <span style={{
                      width: 6, height: 6, borderRadius: '50%',
                      background: 'var(--c-signal)', display: 'inline-block', flexShrink: 0,
                    }} />
                    <span style={{
                      fontSize: '0.75rem', fontWeight: 500,
                      color: 'var(--c-text)',
                    }}>
                      {s.stage}
                    </span>
                  </div>
                  <div style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
                    color: 'var(--c-text-muted)', marginTop: 6, textAlign: 'center',
                  }}>
                    {s.sub}
                  </div>
                </div>
                {i < PIPELINE_STAGES.length - 1 && (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '8px 3px 0', flexShrink: 0 }}>
                    <div style={{ width: 32, height: 1, background: 'linear-gradient(90deg, var(--c-signal), var(--c-signal-dim))', opacity: 0.5 }} />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* ── Right: hero number ── */}
        <div style={{
          display: 'flex', flexDirection: 'column', justifyContent: 'center',
          alignItems: 'flex-end',
          borderLeft: '1px solid var(--c-border)',
          paddingLeft: 40,
          minWidth: 180,
        }}>
          <div style={{
            fontFamily: 'var(--font-display)', fontSize: '0.6875rem', fontWeight: 600,
            letterSpacing: '0.03em', textTransform: 'uppercase',
            color: 'var(--c-text-muted)', marginBottom: 4,
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--c-red)' }} />
            Live Today
          </div>
          <div
            className="animate-count-up"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '3.5rem',
              fontWeight: 700,
              color: 'var(--c-signal)',
              lineHeight: 1,
              letterSpacing: '-0.02em',
            }}
          >
            {stats.today_count}
          </div>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
            color: 'var(--c-text-faint)', marginTop: 6, textAlign: 'right',
          }}>
            {stats.total_investigations} all time
          </div>
          {lastTs && (
            <div style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
              color: 'var(--c-text-muted)', marginTop: 3, textAlign: 'right',
            }}>
              last: {lastTs}
            </div>
          )}
          {stats.avg_mttr_minutes != null && (
            <div style={{
              marginTop: 12, padding: '4px 12px',
              border: '1px solid var(--c-border-hi)', borderRadius: 2,
              background: 'var(--c-surface-2)',
              fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
              color: 'var(--c-text-dim)',
            }}>
              <span style={{ color: 'var(--c-text-muted)', marginRight: 4 }}>avg MTTR</span>
              <span style={{ fontWeight: 700, color: 'var(--c-text)' }}>{stats.avg_mttr_minutes}m</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Metric card ───────────────────────────────────────────────────────────────

function MetricCard({
  label,
  value,
  sub,
  accent,
  delay = 0,
}: {
  label: string
  value: string | number
  sub?: string
  accent?: string
  delay?: number
}) {
  const empty = value === '—' || value === 0
  return (
    <div
      className="metric-card animate-fade-up scan-sweep"
      style={{
        animationDelay: `${delay}ms`,
        overflow: 'hidden',
        borderTop: !empty && accent ? `2px solid ${accent}` : undefined,
      }}
    >
      <div style={{
        fontFamily: 'var(--font-display)',
        fontSize: '0.7rem',
        fontWeight: 700,
        letterSpacing: '0.14em',
        textTransform: 'uppercase',
        color: 'var(--c-text-muted)',
      }}>
        {label}
      </div>
      <div style={{
        fontFamily: 'var(--font-mono)',
        fontSize: '1.75rem',
        fontWeight: 700,
        color: empty ? 'var(--c-text-faint)' : (accent ?? 'var(--c-text)'),
        lineHeight: 1.1,
        letterSpacing: '-0.01em',
        marginTop: 6,
      }}>
        {value}
      </div>
      {sub && (
        <div style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '0.65rem',
          color: empty ? 'var(--c-text-faint)' : 'var(--c-text-muted)',
          marginTop: 4,
        }}>
          {sub}
        </div>
      )}
    </div>
  )
}

// ── Log row ───────────────────────────────────────────────────────────────────

function LogRow({ inv, index }: { inv: InvestigationSummary & { approval_status?: string, incident_priority?: string }; index: number }) {
  const status = inv.approval_status ?? 'pending'
  const tsStr = inv.completed_at ?? inv.created_at
  const priority = inv.incident_priority ?? 'P3'
  
  const priColor = priority === 'P1' ? 'var(--c-red)' : priority === 'P2' ? 'var(--c-signal)' : 'var(--c-text-muted)'
  const priBg = priority === 'P1' ? 'var(--c-error-bg)' : priority === 'P2' ? 'var(--c-signal-light)' : 'var(--c-surface-2)'
  const priBorder = priority === 'P1' ? '1px solid var(--c-error-border)' : priority === 'P2' ? '1px solid var(--c-signal-dim)' : '1px solid var(--c-border)'

  return (
    <Link
      to={`/investigations/${inv.request_id}`}
      className="log-row animate-fade-up"
      style={{
        gridTemplateColumns: '100px 1fr 120px 120px 100px 20px',
        animationDelay: `${index * 35}ms`,
      }}
    >
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text-faint)', letterSpacing: '0.02em' }}>
        {fmtTs(tsStr)}
      </span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ 
          fontFamily: 'var(--font-mono)', fontSize: '0.68rem', fontWeight: 800, 
          color: priColor, background: priBg, border: priBorder,
          padding: '2px 6px', borderRadius: 4, flexShrink: 0
        }}>
          {priority}
        </span>
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.9rem', color: 'var(--c-text)' }}>
          {inv.service_name}
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-faint)' }}>
          {inv.environment}
        </span>
      </div>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-muted)' }}>
        {inv.trigger_source.replace('_', ' ')}
      </span>
      <span className={`badge ${STATUS_CLS[status] ?? 'badge-pending'}`}>{status}</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-faint)', textAlign: 'right' }}>
        {timeAgo(tsStr)}
      </span>
      <span className="log-arrow" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--c-text-faint)', textAlign: 'right', transition: 'color 0.15s' }}>
        →
      </span>
    </Link>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { theme: _theme } = useTheme()

  const { data: stats } = useQuery<InvestigationStats>({
    queryKey: ['stats'],
    queryFn: fetchInvestigationStats,
    refetchInterval: 30_000,
  })

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

  const conf = stats?.confidence_distribution
  const appr = stats?.approval_distribution

  return (
    <Layout>
      {/* ── 1. CONTEXT: Morning Briefing ────────────────────────────────── */}
      {briefing && <BriefingWidget data={briefing} />}

      {/* ── 2. IDENTITY: Hero band + metric cards ─────────────────────── */}
      {stats && (
        <div style={{ marginBottom: 24 }}>
          <HeroBand stats={stats} recent={recent ?? []} />

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8, marginBottom: 8 }}>
            <MetricCard
              label="Avg MTTR"
              value={stats.avg_mttr_minutes != null ? `${stats.avg_mttr_minutes}m` : '—'}
              sub="pipeline time"
              accent="var(--c-signal)"
              delay={80}
            />
            <MetricCard
              label="High Confidence"
              value={conf && (conf.high + conf.medium + conf.low) > 0
                ? `${Math.round((conf.high / (conf.high + conf.medium + conf.low)) * 100)}%`
                : '—'}
              sub="of all RCAs"
              accent="var(--c-green)"
              delay={100}
            />
            <MetricCard
              label="Executed"
              value={appr?.executed ?? '—'}
              sub="fix strategies run"
              accent="var(--c-signal)"
              delay={120}
            />
            <MetricCard
              label="Rejected"
              value={appr?.rejected ?? '—'}
              sub="investigations rejected"
              accent="var(--c-red)"
              delay={140}
            />
          </div>
        </div>
      )}

      {/* ── 3. PULSE: Real-time background activity ───────────────────── */}
      <PlatformPulse />

      {/* ── 4. ACTIVE QUEUE: Recent investigations ────────────────────── */}
      <div className="animate-fade-up" style={{ marginBottom: 24 }}>
        <div style={{
          fontFamily: 'var(--font-display)',
          fontSize: '0.75rem',
          fontWeight: 500,
          letterSpacing: '0.03em',
          textTransform: 'uppercase',
          color: 'var(--c-signal)',
          marginBottom: 4,
        }}>
          Operations Center
        </div>
        <div style={{
          fontFamily: 'var(--font-display)',
          fontSize: '1.5rem',
          lineHeight: 1.2,
          letterSpacing: '-0.01em',
          fontWeight: 700,
          color: 'var(--c-text)',
          marginBottom: 16
        }}>
          Active Investigation Queue
        </div>

        <div className="panel" style={{ overflow: 'hidden' }}>
          {/* Table header */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '100px 1fr 120px 120px 100px 20px',
            gap: 16,
            padding: '10px 14px',
            borderBottom: '1px solid var(--c-border-hi)',
            background: 'var(--c-surface-2)',
          }}>
            {['TIME', 'SERVICE', 'SOURCE', 'STATUS', 'AGO', ''].map((h, i) => (
              <span key={i} className="section-label">{h}</span>
            ))}
          </div>

          {/* Rows */}
          {(recent ?? []).slice(0, 8).map((inv, i) => (
            <LogRow key={inv.request_id} inv={inv} index={i} />
          ))}

          {(recent ?? []).length === 0 && (
            <div style={{ padding: '40px 20px', textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--c-text-faint)' }}>
              No investigations yet — start one from the <Link to="/investigations" style={{ color: 'var(--c-signal)' }}>Investigations</Link> page.
            </div>
          )}

          {/* Footer */}
          {(recent ?? []).length > 8 && (
            <div style={{ padding: '10px 14px', borderTop: '1px solid var(--c-border)', textAlign: 'center' }}>
              <Link to="/investigations" style={{
                fontFamily: 'var(--font-display)',
                fontSize: '0.72rem',
                fontWeight: 700,
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
                color: 'var(--c-signal)',
                textDecoration: 'none',
              }}>
                View All {(recent ?? []).length} Investigations →
              </Link>
            </div>
          )}
        </div>
      </div>

      {/* ── 5. HEALTH & RISK: Service State + Topology ────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 12, marginBottom: 16, alignItems: 'start' }}>
        <div className="panel animate-fade-up" style={{ padding: '18px 20px' }}>
          <div style={{
            fontSize: '0.75rem', fontWeight: 600,
            letterSpacing: '0.03em', textTransform: 'uppercase',
            color: 'var(--c-text-muted)', marginBottom: 16,
          }}>
            Service Health
          </div>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-start', flexWrap: 'nowrap', overflowX: 'auto', paddingBottom: 4 }}>
            <ServiceHealthGauge serviceName="fundapis" environment="dev" />
            <ServiceHealthGauge serviceName="fundsso" environment="dev" />
            <ServiceHealthGauge serviceName="partnerapis" environment="dev" />
          </div>
        </div>

        <PredictiveAlertPanel />
      </div>

      <div style={{ marginBottom: 16 }}>
        <TopologyRadar />
      </div>

      {/* ── 6. VALUE: ROI + DORA ─────────────────────────────────────── */}
      <div style={{ marginBottom: 16 }}>
        <RoiWidget />
      </div>
      <div style={{ marginBottom: 24 }}>
        <DoraWidget />
      </div>

      {/* ── 7. TOOLS: Chaos Engineering (Red Team) ────────────────────── */}
      <div style={{ marginTop: 40, borderTop: '1px solid var(--c-border)', paddingTop: 40 }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
           <div style={{ fontSize: '0.75rem', color: 'var(--c-text-muted)', fontWeight: 500, letterSpacing: '0.03em', textTransform: 'uppercase' }}>System Stress Testing</div>
           <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.25rem', fontWeight: 700, color: 'var(--c-text)', marginTop: 4 }}>Chaos Control Center</h2>
        </div>
        <SimulateAlertPanel />
      </div>
    </Layout>
  )
}

