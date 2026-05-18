/**
 * RoiWidget — V3.9 ROI Dashboard panel.
 *
 * Shows the business case in big numbers: incidents handled, MTTR saved,
 * hours saved, cost saved. Answers "what's the business case?" before judges ask.
 */
import { useQuery } from '@tanstack/react-query'
import { fetchRoi } from '../api/client'

/** Per-colour tinted backgrounds using rgba so all browsers are happy. */
const TINTS: Record<string, string> = {
  '#f97316': 'rgba(249,115,22,0.08)',
  '#22c55e': 'rgba(34,197,94,0.08)',
  '#3b82f6': 'rgba(59,130,246,0.08)',
  '#f59e0b': 'rgba(245,158,11,0.08)',
}

function LoadingSkeleton() {
  const bar = (w: string, h = '0.7rem') => (
    <div style={{
      width: w, height: h, borderRadius: 4,
      background: 'var(--c-surface-2)', marginBottom: 6,
      animation: 'skeleton-pulse 1.4s ease-in-out infinite',
    }} />
  )
  return (
    <div className="panel" style={{ padding: '20px 22px' }}>
      {bar('6rem', '0.55rem')}
      {bar('12rem', '1rem')}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 2, marginTop: 18, borderRadius: 10, overflow: 'hidden',
        border: '1px solid var(--c-border)',
      }}>
        {[0, 1, 2, 3].map(i => (
          <div key={i} style={{ padding: '16px 18px', background: 'var(--c-surface)' }}>
            {bar('60%', '0.5rem')}
            {bar('80%', '1.75rem')}
            {bar('90%', '0.55rem')}
          </div>
        ))}
      </div>
    </div>
  )
}

export function RoiWidget() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['roi'],
    queryFn: fetchRoi,
    staleTime: 300_000,
    retry: false,
  })

  if (isLoading) return <LoadingSkeleton />

  if (isError) {
    return (
      <div className="panel" style={{ padding: '20px 22px', textAlign: 'center' }}>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
          color: 'var(--c-text-faint)', padding: '32px 0',
        }}>
          ✗ ROI data unavailable — check API connection
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="panel" style={{ padding: '20px 22px', textAlign: 'center' }}>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
          color: 'var(--c-text-faint)', padding: '32px 0',
        }}>
          No completed investigations yet — ROI will appear after the first resolved incident.
        </div>
      </div>
    )
  }

  const savingStr = data.cost_saved >= 1000
    ? `${data.currency} ${(data.cost_saved / 1000).toFixed(1)}k`
    : `${data.currency} ${Math.round(data.cost_saved)}`

  const mttrSavedMin = Math.max(0, data.baseline_mttr_minutes - data.corvin_mttr_minutes)

  const stats = [
    {
      label:   'Incidents Handled',
      value:   String(data.total_incidents),
      sub:     `${data.incidents_per_day.toFixed(1)}/day avg`,
      colour:  '#f97316',
    },
    {
      label:   'MTTR Reduction',
      value:   `${data.mttr_reduction_pct}%`,
      sub:     `${Math.round(data.corvin_mttr_minutes)}min vs ${Math.round(data.baseline_mttr_minutes)}min baseline`,
      colour:  '#22c55e',
    },
    {
      label:   'Engineer Hours Saved',
      value:   `${data.hours_saved}h`,
      sub:     `${Math.round(mttrSavedMin)}min saved per incident`,
      colour:  '#3b82f6',
    },
    {
      label:   'Cost Saved This Month',
      value:   savingStr,
      sub:     `vs ${Math.round(data.baseline_mttr_minutes)}min baseline · ${data.period_months}mo window`,
      colour:  '#f59e0b',
    },
  ]

  return (
    <div className="panel animate-fade-up" style={{ padding: '20px 22px' }}>
      {/* Header */}
      <div style={{ marginBottom: 18 }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.68rem',
          letterSpacing: '0.2em', textTransform: 'uppercase',
          color: 'var(--c-signal)', marginBottom: 5,
        }}>
          Corvin ROI
        </div>
        <div style={{
          fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '1.1rem',
          color: 'var(--c-text)',
        }}>
          Business Impact This Month
        </div>
      </div>

      {/* Stat grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 2,
        borderRadius: 10,
        overflow: 'hidden',
        border: '1px solid var(--c-border)',
      }}>
        {stats.map((s, i) => (
          <div
            key={s.label}
            style={{
              padding: '16px 18px',
              background: `linear-gradient(160deg, ${TINTS[s.colour] ?? 'transparent'} 0%, var(--c-surface) 100%)`,
              borderRight: i < stats.length - 1 ? '1px solid var(--c-border)' : 'none',
              display: 'flex', flexDirection: 'column', gap: 6,
            }}
          >
            <div style={{
              fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.65rem',
              letterSpacing: '0.16em', textTransform: 'uppercase', color: s.colour, opacity: 0.9,
            }}>
              {s.label}
            </div>
            <div style={{
              fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '1.75rem',
              color: 'var(--c-text)', lineHeight: 1, letterSpacing: '-0.01em',
            }}>
              {s.value}
            </div>
            <div style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
              color: 'var(--c-text-faint)', lineHeight: 1.35,
            }}>
              {s.sub}
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div style={{
        marginTop: 12, fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
        color: 'var(--c-text-faint)', textAlign: 'right',
      }}>
        Based on {data.total_incidents} investigations · baseline {Math.round(data.baseline_mttr_minutes)}min MTTR without Corvin
      </div>
    </div>
  )
}
