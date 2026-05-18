/**
 * Section — standard panel wrapper used throughout the investigation detail page.
 * Renders a dark card with a labelled header row and padded body.
 */
import type { ReactNode } from 'react'

interface SectionProps {
  title: string
  children: ReactNode
  accent?: boolean
  id?: string
  /** Optional right-side header element */
  headerRight?: ReactNode
}

export function Section({ title, children, accent, id, headerRight }: SectionProps) {
  return (
    <section id={id} style={{ marginTop: 24 }}>
      <div className={accent ? 'panel-signal' : 'panel'} style={{ overflow: 'hidden' }}>
        <div style={{
          padding: '12px 20px',
          borderBottom: '1px solid var(--c-border)',
          background: 'linear-gradient(90deg, rgba(249,115,22,0.03) 0%, transparent 100%), var(--c-surface-2)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span style={{
            fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.76rem',
            letterSpacing: '0.16em', textTransform: 'uppercase',
            color: accent ? 'var(--c-signal)' : 'var(--c-text-dim)',
          }}>
            {title}
          </span>
          {headerRight}
        </div>
        <div style={{ padding: '18px 20px' }}>
          {children}
        </div>
      </div>
    </section>
  )
}

/** Labelled key/value row inside a Section */
export function InfoRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', marginBottom: 10, minHeight: 20 }}>
      <span style={{
        fontFamily: 'var(--font-display)', fontSize: '0.68rem', fontWeight: 700,
        letterSpacing: '0.12em', textTransform: 'uppercase',
        color: 'var(--c-text-muted)', minWidth: 120, paddingTop: 2,
      }}>
        {label}
      </span>
      <div style={{
        fontFamily: 'var(--font-body)', fontSize: '0.85rem',
        color: 'var(--c-text-dim)', flex: 1,
      }}>
        {children}
      </div>
    </div>
  )
}

/** Inline success / error alert banner */
export function AlertBanner({
  ok, message, detail,
}: {
  ok: boolean
  message: string
  detail?: ReactNode
}) {
  return (
    <div style={{
      padding: '10px 14px',
      background: ok ? 'var(--c-green-bg)' : 'var(--c-red-bg)',
      border: `1px solid ${ok ? 'var(--c-green-border)' : 'var(--c-red-border)'}`,
      borderRadius: 3, marginBottom: 14,
    }}>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: '0.78rem',
        color: ok ? 'var(--c-green)' : 'var(--c-red)', fontWeight: 600,
      }}>
        {ok ? '✓' : '✗'} {message}
      </div>
      {detail && <div style={{ marginTop: 8 }}>{detail}</div>}
    </div>
  )
}
