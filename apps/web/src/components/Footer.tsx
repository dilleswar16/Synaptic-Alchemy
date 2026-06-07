import { Link } from 'react-router-dom'

export default function Footer() {
  return (
    <footer
      style={{
        marginTop: 48,
        borderTop: '2px solid #0090DA',
        background: '#002A5C',
      }}
    >
      <div
        style={{
          maxWidth: 1280,
          margin: '0 auto',
          padding: '32px 24px',
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 24,
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <svg width={20} height={20} viewBox="0 0 32 32" fill="none" style={{ flexShrink: 0 }}>
              <defs>
                <linearGradient id="ft-bg" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#007ABC"/><stop offset="1" stopColor="#0090DA"/>
                </linearGradient>
              </defs>
              <rect width="32" height="32" rx="7.5" fill="url(#ft-bg)"/>
              <path d="M21.5 9A9 9 0 1 0 21.5 23" stroke="white" strokeWidth="2.8" fill="none" strokeLinecap="round"/>
              <path d="M16 12L20 16L16 20L12 16Z" fill="white"/>
            </svg>
            <span style={{
              fontFamily: 'var(--font-display)',
              fontSize: '0.875rem',
              fontWeight: 700,
              color: '#ffffff',
              letterSpacing: '-0.01em',
            }}>
              Corvin Operator
            </span>
          </div>
          <p style={{ margin: 0, color: 'rgba(255,255,255,0.65)', fontSize: '0.84rem', lineHeight: 1.65 }}>
            AI-powered incident investigation platform for SRE teams.
          </p>
        </div>

        <div>
          <div style={{
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            fontSize: '0.65rem',
            fontWeight: 600,
            color: 'rgba(255,255,255,0.45)',
            marginBottom: 12,
          }}>Navigate</div>
          <div style={{ display: 'grid', gap: 8 }}>
            <Link to="/" style={{ fontSize: '0.84rem', color: 'rgba(255,255,255,0.75)', textDecoration: 'none' }}>Dashboard</Link>
            <Link to="/investigations" style={{ fontSize: '0.84rem', color: 'rgba(255,255,255,0.75)', textDecoration: 'none' }}>Investigations</Link>
            <Link to="/corvin" style={{ fontSize: '0.84rem', color: 'rgba(255,255,255,0.75)', textDecoration: 'none' }}>Corvin AI</Link>
          </div>
        </div>

        <div>
          <div style={{
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            fontSize: '0.65rem',
            fontWeight: 600,
            color: 'rgba(255,255,255,0.45)',
            marginBottom: 12,
          }}>Platform</div>
          <div style={{ display: 'grid', gap: 8 }}>
            <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.8rem', fontFamily: 'var(--font-mono)' }}>v3.9 — Enterprise</span>
            <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.8rem' }}>WCAG AA compliant</span>
          </div>
        </div>
      </div>

      {/* Bottom bar */}
      <div style={{
        maxWidth: 1280,
        margin: '0 auto',
        padding: '12px 24px',
        borderTop: '1px solid rgba(255,255,255,0.10)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span style={{ color: 'rgba(255,255,255,0.40)', fontSize: '0.75rem' }}>
          © {new Date().getFullYear()} MetLife. Internal use only.
        </span>
        <span style={{ color: 'rgba(255,255,255,0.40)', fontSize: '0.75rem', fontFamily: 'var(--font-mono)' }}>
          ◈ Operator UI
        </span>
      </div>
    </footer>
  )
}
