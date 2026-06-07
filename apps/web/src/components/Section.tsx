/**
 * Section — standard panel wrapper used throughout the investigation detail page.
 * Renders a dark card with a labelled header row and padded body.
 */
import { useState, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

// ── InfoTooltip ───────────────────────────────────────────────────────────────

const TOOLTIP_WIDTH = 270

export function InfoTooltip({ text }: { text: string }) {
  const [rect, setRect] = useState<DOMRect | null>(null)
  const ref = useRef<HTMLSpanElement>(null)

  function show() {
    if (ref.current) setRect(ref.current.getBoundingClientRect())
  }
  function hide() { setRect(null) }

  // Clamp horizontally so the tooltip never overflows the viewport
  const left = rect
    ? Math.min(rect.left, window.innerWidth - TOOLTIP_WIDTH - 12)
    : 0

  return (
    <span
      ref={ref}
      style={{ display: 'inline-flex', flexShrink: 0 }}
      onMouseEnter={show}
      onMouseLeave={hide}
    >
      <span style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 15, height: 15, borderRadius: '50%',
        border: '1px solid var(--c-border-hi)',
        background: 'var(--c-surface-3)',
        color: 'var(--c-text-faint)',
        fontSize: '0.58rem', fontWeight: 700, fontFamily: 'var(--font-mono)',
        cursor: 'help', letterSpacing: 0, flexShrink: 0,
        userSelect: 'none', lineHeight: 1,
      }}>
        i
      </span>
      {rect && createPortal(
        <div style={{
          position: 'fixed',
          top: rect.bottom + 8,
          left,
          zIndex: 99999,
          width: TOOLTIP_WIDTH,
          padding: '10px 13px',
          background: 'var(--c-surface)',
          border: '1px solid var(--c-border-hi)',
          borderRadius: 8,
          boxShadow: '0 6px 24px rgba(0,0,0,0.35)',
          fontFamily: 'var(--font-body)', fontSize: '0.72rem',
          color: 'var(--c-text-dim)', lineHeight: 1.6,
          pointerEvents: 'none',
        }}>
          {text}
        </div>,
        document.body,
      )}
    </span>
  )
}

// ── Section ───────────────────────────────────────────────────────────────────

interface SectionProps {
  title: string
  children: ReactNode
  accent?: boolean
  id?: string
  /** Optional right-side header element */
  headerRight?: ReactNode
  /** Executive-safe tooltip explaining what this section contains */
  info?: string
}

export function Section({ title, children, accent, id, headerRight, info }: SectionProps) {
  return (
    <section id={id} style={{ marginTop: 24 }}>
      <div className={accent ? 'panel-signal' : 'panel'} style={{ overflow: 'hidden' }}>
        <div style={{
          padding: '12px 20px',
          borderBottom: '1px solid var(--c-border)',
          background: 'var(--c-surface-2)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span style={{
            display: 'flex', alignItems: 'center', gap: 7,
            fontWeight: 600, fontSize: '0.8125rem',
            letterSpacing: '0.02em',
            color: accent ? 'var(--c-signal)' : 'var(--c-text-dim)',
          }}>
            {title}
            {info && <InfoTooltip text={info} />}
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
        fontSize: '0.75rem', fontWeight: 500,
        letterSpacing: '0.03em', textTransform: 'uppercase',
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
      borderRadius: 8, marginBottom: 14,
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
