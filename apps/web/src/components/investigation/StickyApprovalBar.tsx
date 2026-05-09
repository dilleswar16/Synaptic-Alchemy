/**
 * StickyApprovalBar — fixed floating bar shown when an investigation is pending
 * approval and the inline approval section is not in the viewport.
 */

interface StickyApprovalBarProps {
  serviceName: string
  environment: string
  confidence: string | null
  onApprove: () => void
  onReject: () => void
}

export function StickyApprovalBar({
  serviceName, environment, confidence, onApprove, onReject,
}: StickyApprovalBarProps) {
  const confColor = confidence === 'high' ? 'var(--c-green)'
    : confidence === 'low' ? 'var(--c-red)' : 'var(--c-yellow)'

  return (
    <div
      className="sticky-bar-enter"
      style={{
        position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)',
        zIndex: 1000, display: 'flex', alignItems: 'center', gap: 16,
        padding: '12px 18px',
        background: 'rgba(4,7,10,0.97)',
        backdropFilter: 'blur(20px)',
        border: '1px solid rgba(249,115,22,0.35)',
        borderRadius: 8,
        boxShadow: '0 12px 48px rgba(0,0,0,0.8), 0 0 0 1px rgba(249,115,22,0.08), inset 0 1px 0 rgba(255,255,255,0.04)',
        width: 'max-content',
      }}
    >
      {/* Pulsing amber dot */}
      <div style={{ position: 'relative', width: 10, height: 10, flexShrink: 0 }}>
        <div style={{
          position: 'absolute', inset: 0, borderRadius: '50%',
          background: 'var(--c-signal)', boxShadow: '0 0 8px var(--c-signal)',
          animation: 'signal-pulse 1.6s ease-in-out infinite',
        }} />
        <div style={{
          position: 'absolute', inset: -3, borderRadius: '50%',
          border: '1.5px solid var(--c-signal)',
          animation: 'ring-ripple 1.6s ease-out infinite', opacity: 0,
        }} />
      </div>

      <div style={{ minWidth: 0 }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 800,
          letterSpacing: '0.16em', textTransform: 'uppercase',
          color: 'var(--c-signal)', marginBottom: 3,
        }}>
          Approval Required
        </div>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: '0.66rem',
          color: 'var(--c-text-muted)', whiteSpace: 'nowrap',
        }}>
          {serviceName} / {environment}
          {confidence && (
            <span style={{ color: confColor, marginLeft: 8 }}>· {confidence} confidence</span>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, flexShrink: 0, alignItems: 'center' }}>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: '0.56rem',
          color: 'var(--c-text-faint)', letterSpacing: '0.06em',
          whiteSpace: 'nowrap', marginRight: 4,
        }}>
          A · R
        </span>
        <button
          onClick={onReject}
          className="btn-ghost"
          style={{ fontSize: '0.7rem', padding: '7px 14px', color: 'var(--c-red)', borderColor: 'rgba(239,68,68,0.3)' }}
        >
          ✗ Reject
        </button>
        <button
          onClick={onApprove}
          className="btn-primary"
          style={{ fontSize: '0.7rem', padding: '7px 14px' }}
        >
          ✓ Approve
        </button>
      </div>
    </div>
  )
}
