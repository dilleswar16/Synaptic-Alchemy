import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchSlaCountdown } from '../../api/client'

function fmt(seconds: number | null) {
  if (seconds == null) return 'Stable'
  if (seconds <= 0) return 'Now'
  const total = Math.round(seconds)
  const hrs = Math.floor(total / 3600)
  const mins = Math.floor((total % 3600) / 60)
  const secs = total % 60
  if (hrs > 0) return `${hrs}h ${mins}m`
  if (mins > 0) return `${mins}m ${secs}s`
  return `${secs}s`
}

const COLOR: Record<string, string> = {
  green: 'var(--c-green)',
  amber: 'var(--c-yellow)',
  red: 'var(--c-red)',
}

export function SlaCountdownCard({ requestId, status }: { requestId: string; status: string }) {
  const { data } = useQuery({
    queryKey: ['sla', requestId],
    queryFn: () => fetchSlaCountdown(requestId),
    enabled: status !== 'executed',
    refetchInterval: 45_000,
  })
  const [eta, setEta] = useState<number | null>(null)

  useEffect(() => {
    setEta(data?.estimated_breach_in_seconds ?? null)
  }, [data?.estimated_breach_in_seconds])

  useEffect(() => {
    if (eta == null || eta <= 0) return
    const timer = window.setInterval(() => {
      setEta((current) => (current == null ? null : Math.max(0, current - 1)))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [eta])

  if (!data || status === 'executed') return null

  const accent = COLOR[data.severity] ?? 'var(--c-signal)'
  const burnPct = Math.min(100, (data.seconds_already_down_this_month / Math.max(data.monthly_budget_seconds, 1)) * 100)

  return (
    <div style={{
      marginBottom: 12,
      padding: '14px 18px',
      borderRadius: 8,
      border: `1px solid color-mix(in srgb, ${accent} 35%, var(--c-border-hi))`,
      background: `linear-gradient(135deg, color-mix(in srgb, ${accent} 10%, transparent) 0%, var(--c-surface) 100%)`,
      boxShadow: `0 0 26px color-mix(in srgb, ${accent} 18%, transparent)`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 10 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.62rem', letterSpacing: '0.15em', textTransform: 'uppercase', color: accent, marginBottom: 4 }}>
            SLA Countdown
          </div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '1.15rem', color: 'var(--c-text)' }}>
            {data.breached ? `SLA ${data.sla_target_percent}% budget exhausted` : `${data.sla_target_percent}% breach in ${fmt(eta)}`}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.1rem', color: accent, fontWeight: 700 }}>{Math.round(burnPct)}%</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.64rem', color: 'var(--c-text-faint)' }}>budget consumed</div>
        </div>
      </div>
      <div style={{ height: 8, borderRadius: 999, background: 'var(--c-surface-2)', overflow: 'hidden', marginBottom: 10 }}>
        <div style={{ width: `${burnPct}%`, height: '100%', background: accent, boxShadow: `0 0 16px ${accent}` }} />
      </div>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text-muted)' }}>
        <span>remaining {fmt(data.remaining_budget_seconds)}</span>
        <span>error rate {(data.current_error_rate * 100).toFixed(1)}%</span>
        <span>burned {Math.round(data.seconds_already_down_this_month / 60)}m this month</span>
      </div>
    </div>
  )
}