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
import { SimulateAlertPanel } from '../components/SimulateAlertPanel'
import { PredictiveAlertPanel } from '../components/PredictiveAlertPanel'
import { TopologyRadar } from '../components/TopologyRadar'
import { RoiWidget } from '../components/RoiWidget'
import { KpiStrip } from '../components/KpiStrip'
import { ServiceFleetGrid } from '../components/ServiceFleetGrid'
import { ErrorBudgetBurnChart } from '../components/ErrorBudgetBurnChart'
import { DoraSidebar } from '../components/DoraSidebar'
import IncidentHeatmap from '../components/IncidentHeatmap'
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
          {/* Greeting */}
          <div style={{
            fontFamily: 'var(--font-display)', fontWeight: 800,
            fontSize: '1.3rem', letterSpacing: '-0.02em',
            background: 'linear-gradient(135deg, var(--c-text) 0%, var(--c-text-dim) 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            marginBottom: 12,
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



// ── Main page ─────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { theme: _theme } = useTheme()
  const [briefingOpen, setBriefingOpen] = useState(false)

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

      {/* ── 2. FLEET VIEW: Service Grid + DORA sidebar ────────────────── */}
      <div className="dash-fleet-view">
        <ServiceFleetGrid />
        <DoraSidebar />
      </div>

      {/* ── 3. ERROR BUDGET BURN CHART (full width) ───────────────────── */}
      <ErrorBudgetBurnChart />

      {/* ── 4. OPS ROW: Investigation Queue + Predictive Alerts ───────── */}
      <div className="dash-ops-row">
        {/* Left: top-5 investigation queue */}
        <div className="panel dash-inv-queue animate-fade-up">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <span style={{
              fontFamily: 'var(--font-display)', fontSize: '0.75rem', fontWeight: 700,
              textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--c-text-muted)',
            }}>
              Recent Investigations
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
            display: 'grid', gridTemplateColumns: '90px 1fr 100px 80px 16px',
            gap: 12, padding: '7px 10px',
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
                style={{ gridTemplateColumns: '90px 1fr 100px 80px 16px', animationDelay: `${i * 30}ms` }}
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

      {/* ── 6. ROI + AI Briefing ─────────────────────────────────────── */}
      <div className="dash-bottom-row">
        <RoiWidget />

        {/* AI Briefing — collapsed by default */}
        <div className="panel dash-briefing-collapsible animate-fade-up">
          <button
            className="dash-briefing-toggle"
            onClick={() => setBriefingOpen(v => !v)}
            aria-expanded={briefingOpen}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {(briefing?.high_confidence_pending ?? 0) > 0 && (
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--c-signal)', display: 'inline-block', flexShrink: 0 }} />
              )}
              <span>AI Briefing</span>
            </span>
            <span style={{ fontSize: '0.9rem', transform: briefingOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>▾</span>
          </button>
          {briefingOpen && briefing && (
            <div style={{ borderTop: '1px solid var(--c-border)', padding: '0' }}>
              <BriefingWidget data={briefing} />
            </div>
          )}
          {briefingOpen && !briefing && (
            <div style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--c-text-muted)', fontSize: '0.8rem' }}>
              Loading AI briefing…
            </div>
          )}
        </div>
      </div>

      {/* ── 7. CHAOS (collapsed) ──────────────────────────────────────── */}
      <div style={{ marginTop: 40, borderTop: '1px solid var(--c-border)', paddingTop: 40 }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div style={{ fontSize: '0.7rem', color: 'var(--c-text-muted)', fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
            System Stress Testing
          </div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.2rem', fontWeight: 800, color: 'var(--c-text)', marginTop: 6, letterSpacing: '-0.02em' }}>
            Chaos Control Center
          </h2>
        </div>
        <SimulateAlertPanel />
      </div>
    </Layout>
  )
}

