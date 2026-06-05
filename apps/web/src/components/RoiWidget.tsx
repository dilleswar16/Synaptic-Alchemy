/**
 * RoiWidget — V3.9 ROI Dashboard panel.
 *
 * Shows the business case in big numbers: incidents handled, MTTR saved,
 * hours saved, cost saved. Answers "what's the business case?" before judges ask.
 */
import { useQuery } from '@tanstack/react-query'
import { fetchRoi } from '../api/client'

/** Per-colour tinted backgrounds using token vars. */
const TINTS: Record<string, string> = {
  'var(--c-signal)': 'var(--c-signal-light)',
  'var(--c-green)': 'var(--c-success-bg)',
  'var(--c-info)': 'var(--c-info-bg)',
  'var(--c-warning)': 'var(--c-warning-bg)',
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
        display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)',
        gap: 2, marginTop: 18, borderRadius: 10, overflow: 'hidden',
        border: '1px solid var(--c-border)',
      }}>
        {[0, 1].map(i => (
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

  const stats = [
    {
      label:   'Incidents Handled',
      value:   String(data.total_incidents),
      sub:     `${data.incidents_per_day.toFixed(1)}/day avg`,
      colour:  'var(--c-signal)',
    },
    {
      label:   'MTTR Reduction',
      value:   `${data.mttr_reduction_pct}%`,
      sub:     `${Math.round(data.corvin_mttr_minutes)}min vs ${Math.round(data.baseline_mttr_minutes)}min baseline`,
      colour:  'var(--c-green)',
    },
  ]

  return (
    <div className="panel animate-fade-up" style={{ padding: '20px 22px' }}>
      {/* Header */}
      <div style={{ marginBottom: 18 }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '0.75rem',
          letterSpacing: '0.2em', textTransform: 'uppercase',
          color: 'var(--c-signal)', marginBottom: 5,
        }}>
          Corvin ROI
        </div>
        <div style={{
          fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '1.125rem',
          color: 'var(--c-text)',
        }}>
          Business Impact This Month
        </div>
      </div>

      {/* Stat grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(2, 1fr)',
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
              fontWeight: 600, fontSize: '0.75rem',
              letterSpacing: '0.03em', textTransform: 'uppercase', color: s.colour, opacity: 0.9,
            }}>
              {s.label}
            </div>
            <div style={{
              fontWeight: 700, fontSize: '1.5rem',
              color: 'var(--c-text)', lineHeight: 1, letterSpacing: '-0.02em',
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
