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
        border: `1px solid ${urgent ? 'rgba(249,115,22,0.4)' : 'var(--c-border-hi)'}`,
        borderLeft: `3px solid ${urgent ? 'var(--c-signal)' : 'var(--c-border-hi)'}`,
        borderRadius: 4,
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      {/* Atmospheric grid */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        backgroundImage:
          'linear-gradient(90deg, rgba(249,115,22,0.018) 1px, transparent 1px),' +
          'linear-gradient(rgba(249,115,22,0.018) 1px, transparent 1px)',
        backgroundSize: '36px 36px',
      }} />

      {/* Header bar */}
      <div style={{
        position: 'relative',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '9px 20px',
        borderBottom: '1px solid var(--c-border)',
        background: 'var(--c-surface-2)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {urgent && (
            <span
              className="animate-pulse-glow"
              style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--c-signal)', display: 'inline-block', flexShrink: 0 }}
            />
          )}
          <span style={{
            fontFamily: 'var(--font-display)', fontWeight: 700,
            fontSize: '0.64rem', letterSpacing: '0.2em', textTransform: 'uppercase',
            color: urgent ? 'var(--c-signal)' : 'var(--c-text-muted)',
          }}>
            Daily Briefing
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--c-text-faint)', letterSpacing: '0.04em' }}>
            {fmtTime} · {data.period_hours}h window
          </span>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.58rem', letterSpacing: '0.06em',
            padding: '2px 7px', borderRadius: 2,
            background: 'rgba(249,115,22,0.07)',
            border: '1px solid rgba(249,115,22,0.15)',
            color: 'var(--c-text-faint)',
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
              background: voiceState === 'playing' ? 'rgba(59,130,246,0.2)' : 'rgba(249,115,22,0.1)',
              color: voiceState === 'playing' ? '#60a5fa' : voiceState === 'error' ? '#ef4444' : 'var(--c-signal)',
              border: `1px solid ${voiceState === 'playing' ? 'rgba(59,130,246,0.3)' : 'rgba(249,115,22,0.2)'}`,
              transition: 'all 0.15s',
            }}
          >
            {voiceState === 'loading' ? '…' : voiceState === 'playing' ? '⏹ Stop' : '▶ Hear'}
          </button>
          {voiceState === 'error' && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.58rem', color: '#ef4444' }}>
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
            fontFamily: 'var(--font-display)', fontWeight: 900,
            fontSize: '1.4rem', letterSpacing: '0.12em', textTransform: 'uppercase',
            color: 'var(--c-text)', marginBottom: 16,
            background: 'linear-gradient(135deg, var(--c-text) 0%, var(--c-signal) 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}>
            {greeting}, OPERATOR
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
                display: 'inline-flex', alignItems: 'center', gap: 6,
                fontFamily: 'var(--font-display)', fontWeight: 700,
                fontSize: '0.6rem', letterSpacing: '0.1em', textTransform: 'uppercase',
                padding: '5px 12px', borderRadius: 2,
                background: 'rgba(249,115,22,0.1)',
                border: '1px solid rgba(249,115,22,0.4)',
                color: 'var(--c-signal)',
              }}>
                <span style={{ width: 5, height: 5, borderRadius: '50%', background: 'var(--c-signal)', display: 'inline-block', flexShrink: 0 }} />
                {data.high_confidence_pending} HIGH-CONF NEEDS APPROVAL
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
              fontFamily: 'var(--font-display)', fontWeight: 700,
              fontSize: '0.58rem', letterSpacing: '0.15em', textTransform: 'uppercase',
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
                  fontFamily: 'var(--font-display)', fontWeight: 700,
                  fontSize: '0.52rem', letterSpacing: '0.1em', textTransform: 'uppercase',
                  color: b.value > 0 ? 'var(--c-text-muted)' : 'var(--c-text-faint)',
                  minWidth: 44,
                }}>
                  {b.label}
                </span>
                <div style={{
                  height: 4, borderRadius: 2,
                  width: b.value > 0 ? `${Math.max((b.value / maxConf) * 72, 6)}px` : '4px',
                  background: b.value > 0 ? b.color : 'var(--c-surface-3)',
                  transition: 'width 0.9s cubic-bezier(0.34,1.2,0.64,1)',
                  boxShadow: b.value > 0 ? `0 0 6px color-mix(in srgb, ${b.color} 40%, transparent)` : 'none',
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
        background: 'linear-gradient(135deg, rgba(249, 115, 22, 0.08) 0%, rgba(59, 130, 246, 0.04) 100%), var(--c-surface)',
        border: '1px solid var(--c-border-hi)',
        borderLeft: '4px solid var(--c-signal)',
        borderRadius: 8,
        boxShadow: '0 0 60px rgba(249, 115, 22, 0.12), 0 4px 24px rgba(0, 0, 0, 0.3)',
      }}
    >
      {/* Atmospheric grid overlay */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        backgroundImage:
          'linear-gradient(90deg, rgba(249,115,22,0.015) 1px, transparent 1px),' +
          'linear-gradient(rgba(249,115,22,0.015) 1px, transparent 1px)',
        backgroundSize: '52px 52px',
      }} />
      {/* Ambient glow top-right */}
      <div style={{
        position: 'absolute', top: -100, right: -100,
        width: 360, height: 360, borderRadius: '50%',
        background: 'radial-gradient(ellipse, rgba(249,115,22,0.12) 0%, transparent 65%)',
        pointerEvents: 'none',
        filter: 'blur(40px)',
      }} />

      <div style={{ position: 'relative', display: 'grid', gridTemplateColumns: '1fr auto', gap: 0, padding: '28px 32px' }}>

        {/* ── Left: identity + pipeline ── */}
        <div style={{ paddingRight: 32 }}>
          {/* Status beacon */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <span
              className="animate-pulse-glow"
              style={{ display: 'inline-block', width: 7, height: 7, borderRadius: '50%', background: 'var(--c-signal)', flexShrink: 0 }}
            />
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.62rem', fontWeight: 600,
              letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--c-signal)',
            }}>
              System Operational
            </span>
          </div>

          <h1 style={{
            margin: '0 0 12px',
            fontFamily: 'var(--font-display)', fontWeight: 900,
            fontSize: '3.2rem', letterSpacing: '0.06em',
            color: 'var(--c-text)', lineHeight: 1,
            background: 'linear-gradient(180deg, var(--c-text) 0%, var(--c-signal) 60%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}>
            OPERATIONS CENTER
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
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                    padding: '6px 14px',
                    border: '1px solid rgba(249,115,22,0.28)',
                    borderRadius: 2,
                    background: 'rgba(249,115,22,0.07)',
                  }}>
                    <span style={{
                      width: 7, height: 7, borderRadius: '50%',
                      background: 'var(--c-signal)', display: 'inline-block', flexShrink: 0,
                      boxShadow: '0 0 6px rgba(249,115,22,0.6)',
                    }} />
                    <span style={{
                      fontFamily: 'var(--font-display)', fontWeight: 700,
                      fontSize: '0.72rem', letterSpacing: '0.1em', textTransform: 'uppercase',
                      color: 'var(--c-text)',
                    }}>
                      {s.stage}
                    </span>
                  </div>
                  <div style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.62rem',
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
            fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 700,
            letterSpacing: '0.18em', textTransform: 'uppercase',
            color: 'var(--c-text-muted)', marginBottom: 4,
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--c-red)', boxShadow: '0 0 8px var(--c-red)' }} className="animate-pulse-glow" />
            Live Today
          </div>
          <div
            className="animate-count-up"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '5.5rem',
              fontWeight: 700,
              color: 'var(--c-signal)',
              lineHeight: 1,
              animation: 'count-up 0.5s 0.1s ease both, glow-pulse 3s 0.6s ease-in-out infinite',
              letterSpacing: '-0.02em',
              textShadow: '0 0 24px rgba(249,115,22,0.3)',
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
              fontFamily: 'var(--font-mono)', fontSize: '0.62rem',
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
        fontSize: '0.62rem',
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
        textShadow: empty ? 'none' : `0 0 12px color-mix(in srgb, ${accent ?? 'var(--c-text)'} 30%, transparent)`,
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

// ── Vertical bar chart ───────────────────────────────────────────────────────

function VerticalBars({ bars }: { bars: { label: string; value: number; color: string }[] }) {
  const max = Math.max(...bars.map(b => b.value), 1)
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', paddingTop: 4 }}>
      {bars.map((bar, i) => (
        <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5 }}>
          {/* Count */}
          <span style={{
            fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.92rem',
            color: bar.value > 0 ? bar.color : 'var(--c-text-faint)',
            minHeight: '1.2em',
          }}>
            {bar.value > 0 ? bar.value : '·'}
          </span>
          {/* Bar track */}
          <div style={{ width: '100%', height: 80, position: 'relative', borderRadius: '2px 2px 0 0', overflow: 'hidden' }}>
            <div style={{
              position: 'absolute', inset: 0,
              background: 'var(--c-surface-3)',
            }} />
            <div style={{
              position: 'absolute', bottom: 0, left: 0, right: 0,
              height: bar.value > 0 ? `${Math.max((bar.value / max) * 100, 5)}%` : '0%',
              background: bar.value > 0
                ? `linear-gradient(180deg, color-mix(in srgb, ${bar.color} 25%, white) 0%, ${bar.color} 100%)`
                : 'transparent',
              transition: 'height 0.8s cubic-bezier(0.34, 1.2, 0.64, 1)',
              boxShadow: bar.value > 0 ? `0 -4px 16px color-mix(in srgb, ${bar.color} 30%, transparent)` : 'none',
            }} />
          </div>
          {/* Label */}
          <div style={{ borderTop: '1px solid var(--c-border-hi)', width: '100%', paddingTop: 6, textAlign: 'center' }}>
            <span style={{
              fontFamily: 'var(--font-display)', fontWeight: 700,
              fontSize: '0.55rem', letterSpacing: '0.1em', textTransform: 'uppercase',
              color: bar.value > 0 ? 'var(--c-text-dim)' : 'var(--c-text-faint)',
            }}>
              {bar.label}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Log row ───────────────────────────────────────────────────────────────────

function LogRow({ inv, index }: { inv: InvestigationSummary & { approval_status?: string }; index: number }) {
  const status = inv.approval_status ?? 'pending'
  const tsStr = inv.completed_at ?? inv.created_at
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
      <div>
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.9rem', color: 'var(--c-text)' }}>
          {inv.service_name}
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-faint)', marginLeft: 8 }}>
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
  const { theme } = useTheme()
  const isLight = theme === 'light'

  const { data: stats, isLoading: statsLoading, isError: statsError, refetch: statsRefetch } = useQuery<InvestigationStats>({
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
      {/* ── Morning Briefing ──────────────────────────────────────────── */}
      {briefing && <BriefingWidget data={briefing} />}

      {/* ── V3.5: Service Health + Alert Simulator ───────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 12, marginBottom: 16, alignItems: 'start' }}>
        <div className="panel animate-fade-up" style={{ padding: '18px 20px', background: isLight ? 'linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%)' : undefined }}>
          <div style={{
            fontFamily: 'var(--font-display)', fontWeight: 700,
            fontSize: '0.62rem', letterSpacing: '0.18em', textTransform: 'uppercase',
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

        <SimulateAlertPanel />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(360px, 0.95fr) minmax(420px, 1.05fr)', gap: 12, marginBottom: 16, alignItems: 'start' }}>
        <PredictiveAlertPanel />
        <TopologyRadar />
      </div>

      <div style={{ marginBottom: 16 }}>
        <RoiWidget />
      </div>

      <div className="animate-fade-up" style={{ marginBottom: 14 }}>
        <div style={{
          fontFamily: 'var(--font-display)',
          fontSize: '0.64rem',
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
          color: 'var(--c-signal)',
          marginBottom: 4,
          fontWeight: 800,
        }}>
          Operations Center
        </div>
        <div style={{
          fontFamily: 'var(--font-display)',
          fontSize: '2rem',
          lineHeight: 1,
          letterSpacing: '0.03em',
          fontWeight: 900,
          color: 'var(--c-text)',
          marginBottom: 16
        }}>
          Live Investigation Overview
        </div>
        <PlatformPulse />
      </div>

      {/* ── Hero band ─────────────────────────────────────────────────────── */}
      {stats && (
        <HeroBand stats={stats} recent={recent ?? []} />
      )}
      {!stats && !statsLoading && (
        <div className="animate-fade-up" style={{ marginBottom: 32, display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 700, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--c-signal)', marginBottom: 4 }}>
              Operations Center
            </div>
            <h1 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: '2.2rem', fontWeight: 900, letterSpacing: '0.04em', color: 'var(--c-text)', lineHeight: 1 }}>
              SRE DASHBOARD
            </h1>
          </div>
        </div>
      )}

      {statsLoading && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8, marginBottom: 12 }}>
            {[0, 1, 2, 3].map(i => (
              <div key={i} className="metric-card scan-sweep" style={{ minHeight: 108 }}>
                <div style={{ width: 90, height: 10, borderRadius: 999, background: 'var(--c-surface-3)', marginBottom: 10 }} />
                <div style={{ width: 56, height: 24, borderRadius: 6, background: 'var(--c-surface-3)', marginBottom: 8 }} />
                <div style={{ width: 120, height: 8, borderRadius: 999, background: 'var(--c-surface-3)' }} />
              </div>
            ))}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 12 }}>
            {[0, 1].map(i => (
              <div key={i} className="panel scan-sweep" style={{ padding: '18px 20px' }}>
                <div style={{ width: 130, height: 10, borderRadius: 999, background: 'var(--c-surface-3)', marginBottom: 16 }} />
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                  {[0, 1, 2].map(b => (
                    <div key={b} style={{ height: 100, borderRadius: 8, background: 'var(--c-surface-3)' }} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {statsError && (
        <div className="animate-fade-up" style={{
          marginBottom: 24,
          padding: '22px 28px',
          background: 'var(--c-surface)',
          border: '1px solid var(--c-red-border)',
          borderLeft: '3px solid var(--c-red)',
          borderRadius: 4,
          display: 'flex',
          alignItems: 'flex-start',
          gap: 18,
        }}>
          <div style={{
            width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
            border: '1px solid var(--c-red-border)',
            background: 'var(--c-red-bg)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: 'var(--font-mono)', fontSize: '0.9rem', color: 'var(--c-red)',
          }}>✗</div>
          <div style={{ flex: 1 }}>
            <div style={{
              fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.82rem',
              letterSpacing: '0.1em', textTransform: 'uppercase',
              color: 'var(--c-red)', marginBottom: 6,
            }}>
              API Unreachable
            </div>
            <div style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.74rem',
              color: 'var(--c-text-muted)', lineHeight: 1.65, marginBottom: 12,
            }}>
              Cannot connect to the Corvin API at{' '}
              <code style={{ color: 'var(--c-text-dim)', background: 'var(--c-surface-2)', padding: '1px 6px', borderRadius: 2 }}>
                localhost:8000
              </code>
              {' '}— check that the FastAPI server is running.
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <button
                onClick={() => statsRefetch()}
                className="btn-ghost"
                style={{ fontSize: '0.72rem', padding: '5px 12px' }}
              >
                ↺ Retry
              </button>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text-faint)' }}>
                uvicorn apps.api.main:app --reload --port 8000
              </span>
            </div>
          </div>
        </div>
      )}

      {stats && (
        <>
          {/* ── Metric row ────────────────────────────────────────────────── */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8, marginBottom: 16 }}>
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

          {/* ── Charts row ────────────────────────────────────────────────── */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 12, marginBottom: 16 }}>
            <div className="panel animate-fade-up-3" style={{ padding: '18px 20px', background: isLight ? 'linear-gradient(180deg, #ffffff 0%, #f7f9ff 100%)' : undefined }}>
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 16 }}>
                <span className="section-label">RCA Confidence</span>
                {conf && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-faint)' }}>
                    {conf.high + conf.medium + conf.low} total
                  </span>
                )}
              </div>
              {conf && (
                <VerticalBars bars={[
                  { label: 'HIGH',   value: conf.high,   color: 'var(--c-green)'  },
                  { label: 'MEDIUM', value: conf.medium, color: 'var(--c-yellow)' },
                  { label: 'LOW',    value: conf.low,    color: 'var(--c-red)'    },
                ]} />
              )}
            </div>

            <div className="panel animate-fade-up-4" style={{ padding: '18px 20px', background: isLight ? 'linear-gradient(180deg, #ffffff 0%, #f7f9ff 100%)' : undefined }}>
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 16 }}>
                <span className="section-label">Approval Pipeline</span>
                {appr && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-faint)' }}>
                    {appr.pending + appr.approved + appr.executed + appr.rejected} total
                  </span>
                )}
              </div>
              {appr && (
                <VerticalBars bars={[
                  { label: 'EXEC',   value: appr.executed, color: 'var(--c-signal)' },
                  { label: 'APPR',   value: appr.approved, color: 'var(--c-green)'  },
                  { label: 'PEND',   value: appr.pending,  color: 'var(--c-yellow)' },
                  { label: 'REJ',    value: appr.rejected, color: 'var(--c-red)'    },
                ]} />
              )}
            </div>
          </div>

          {/* ── Recent services ───────────────────────────────────────────── */}
          {stats.recent_services.length > 0 && (
            <div className="panel animate-fade-up-5" style={{ padding: '14px 20px', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap', background: isLight ? 'linear-gradient(180deg, #ffffff 0%, #f7f9ff 100%)' : undefined }}>
              <span className="section-label" style={{ flexShrink: 0 }}>Active Services</span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {stats.recent_services.map(svc => (
                  <span key={svc} style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.72rem',
                    padding: '5px 14px',
                    borderRadius: 8,
                    background: isLight ? 'rgba(0,102,204,0.08)' : 'rgba(249,115,22,0.08)',
                    border: isLight ? '1px solid rgba(0,102,204,0.22)' : '1px solid rgba(249,115,22,0.2)',
                    color: isLight ? 'var(--c-info)' : 'var(--c-signal)',
                    letterSpacing: '0.04em',
                  }}>
                    {svc}
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Recent investigations ──────────────────────────────────────── */}
      <div className="panel" style={{ overflow: 'hidden', background: isLight ? 'linear-gradient(180deg, #ffffff 0%, #f9fbff 100%)' : undefined }}>
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
        {(recent ?? []).slice(0, 10).map((inv, i) => (
          <LogRow key={inv.request_id} inv={inv} index={i} />
        ))}

        {(recent ?? []).length === 0 && (
          <div style={{ padding: '40px 20px', textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--c-text-faint)' }}>
            No investigations yet — start one from the{' '}
            <Link to="/investigations" style={{ color: 'var(--c-signal)' }}>Investigations</Link> page.
          </div>
        )}

        {/* Footer */}
        {(recent ?? []).length > 10 && (
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
    </Layout>
  )
}

