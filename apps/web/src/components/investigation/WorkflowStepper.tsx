/**
 * WorkflowStepper — 5-stage horizontal progress indicator for investigations.
 * Triggered → Evidence → RCA → Approval/Rejected → Executed
 */

interface WorkflowStepperProps {
  approvalStatus: string
  hasEvidence: boolean
  hasRca: boolean
}

export function WorkflowStepper({ approvalStatus, hasEvidence, hasRca }: WorkflowStepperProps) {
  const isRejected = approvalStatus === 'rejected'
  const stages: { key: string; label: string; done: boolean; rejected: boolean }[] = [
    { key: 'triggered', label: 'Triggered',
      done: true, rejected: false },
    { key: 'evidence',  label: 'Evidence',
      done: hasEvidence, rejected: false },
    { key: 'rca',       label: 'RCA',
      done: hasRca, rejected: false },
    { key: 'approval',
      label: isRejected ? 'Rejected' : 'Approval',
      done: ['approved', 'rejected', 'executed'].includes(approvalStatus),
      rejected: isRejected },
    { key: 'executed',  label: 'Executed',
      done: approvalStatus === 'executed', rejected: false },
  ]
  const currentIdx = stages.reduce<number>((acc, s, i) => s.done ? i : acc, -1)

  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', paddingBottom: 10, overflow: 'visible' }}>
      {stages.map((stage, i) => {
        const isActive  = i === currentIdx
        const isBefore  = i < currentIdx
        const isAfter   = i > currentIdx
        const dotSize   = isActive ? 12 : 8
        const dotBg     = stage.rejected ? 'var(--c-red)'
          : isAfter ? 'transparent' : 'var(--c-signal)'
        const dotBorder = isAfter ? '1.5px solid rgba(255,255,255,0.15)' : 'none'
        const dotGlow   = isActive && !stage.rejected
          ? '0 0 0 3px rgba(249,115,22,0.2), 0 0 10px rgba(249,115,22,0.6)' : 'none'
        const labelColor = stage.rejected ? 'var(--c-red)'
          : isActive ? 'var(--c-signal)'
          : isBefore ? 'var(--c-text-dim)' : 'var(--c-text-faint)'
        const lineColor  = isBefore ? 'rgba(249,115,22,0.4)' : 'var(--c-border)'

        return (
          <div
            key={stage.key}
            style={{
              display: 'flex', alignItems: 'flex-start',
              flex: i < stages.length - 1 ? 1 : 0,
              minWidth: i === stages.length - 1 ? 42 : 0,
            }}
          >
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              minWidth: i === stages.length - 1 ? 42 : 'auto',
            }}>
              <div style={{
                width: dotSize, height: dotSize, borderRadius: '50%',
                background: dotBg, border: dotBorder, boxShadow: dotGlow,
                flexShrink: 0, transition: 'all 0.25s', boxSizing: 'border-box',
              }} />
              <span style={{
                fontFamily: 'var(--font-display)', fontWeight: 700,
                fontSize: '0.5rem', letterSpacing: '0.1em', textTransform: 'uppercase',
                color: labelColor, textAlign: 'center', marginTop: 5,
                transition: 'color 0.25s', maxWidth: 48,
              }}>
                {stage.label}
              </span>
            </div>
            {i < stages.length - 1 && (
              <div style={{
                flex: 1, height: 1, background: lineColor,
                marginTop: dotSize / 2, marginLeft: 6, marginRight: 6,
                minWidth: 12, transition: 'background 0.3s',
              }} />
            )}
          </div>
        )
      })}
    </div>
  )
}
