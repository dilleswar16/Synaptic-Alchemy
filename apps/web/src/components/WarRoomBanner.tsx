/**
 * WarRoomBanner — Pulsing header banner shown during active incidents
 * requiring human approval. Displayed on InvestigationDetailPage when
 * approval_status === 'pending'.
 */

export default function WarRoomBanner({ serviceName, environment }: {
  serviceName: string
  environment: string
}) {
  return (
    <div style={{
      background: 'linear-gradient(90deg, var(--c-red) 0%, var(--c-signal) 100%)',
      color: '#fff',
      padding: '10px 24px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      borderRadius: 8,
      marginBottom: 20,
      animation: 'warRoomPulse 2s ease-in-out infinite',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Animated scanner line */}
      <div style={{
        position: 'absolute',
        top: 0,
        left: '-100%',
        width: '100%',
        height: '100%',
        background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent)',
        animation: 'warRoomScan 3s linear infinite',
      }} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, zIndex: 1 }}>
        <span style={{ fontSize: '1.2rem', animation: 'warRoomBlink 1s step-end infinite' }}>🚨</span>
        <div>
          <div style={{ fontWeight: 700, fontSize: '0.88rem', letterSpacing: '0.5px' }}>
            WAR ROOM ACTIVE
          </div>
          <div style={{ fontSize: '0.72rem', opacity: 0.9 }}>
            {serviceName} / {environment} — Awaiting human approval for remediation
          </div>
        </div>
      </div>

      <div style={{
        fontSize: '0.7rem',
        fontFamily: 'var(--font-mono)',
        background: 'rgba(0,0,0,0.2)',
        padding: '3px 8px',
        borderRadius: 4,
        zIndex: 1,
      }}>
        APPROVAL REQUIRED
      </div>

      <style>{`
        @keyframes warRoomPulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.92; }
        }
        @keyframes warRoomScan {
          0% { left: -100%; }
          100% { left: 100%; }
        }
        @keyframes warRoomBlink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
      `}</style>
    </div>
  )
}
