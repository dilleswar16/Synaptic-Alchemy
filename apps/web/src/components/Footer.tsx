import { Link } from 'react-router-dom'

export default function Footer() {
  return (
    <footer
      style={{
        marginTop: 48,
        borderTop: '1px solid var(--c-border)',
        background: 'var(--c-surface)',
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
            <div style={{
              width: 20,
              height: 20,
              borderRadius: 5,
              background: 'var(--c-signal)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              <span style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.6rem', color: '#fff' }}>C</span>
            </div>
            <span style={{
              fontFamily: 'var(--font-display)',
              fontSize: '0.875rem',
              fontWeight: 700,
              color: 'var(--c-text)',
              letterSpacing: '-0.01em',
            }}>
              Corvin Operator
            </span>
          </div>
          <p style={{ margin: 0, color: 'var(--c-text-muted)', fontSize: '0.84rem', lineHeight: 1.65 }}>
            AI-powered incident investigation platform for SRE teams.
          </p>
        </div>

        <div>
          <div className="section-label" style={{ marginBottom: 12 }}>Navigate</div>
          <div style={{ display: 'grid', gap: 8 }}>
            <Link to="/" style={{ fontSize: '0.84rem', color: 'var(--c-text-dim)' }}>Dashboard</Link>
            <Link to="/investigations" style={{ fontSize: '0.84rem', color: 'var(--c-text-dim)' }}>Investigations</Link>
            <Link to="/corvin" style={{ fontSize: '0.84rem', color: 'var(--c-text-dim)' }}>Corvin AI</Link>
          </div>
        </div>

        <div>
          <div className="section-label" style={{ marginBottom: 12 }}>Platform</div>
          <div style={{ display: 'grid', gap: 8 }}>
            <span style={{ color: 'var(--c-text-faint)', fontSize: '0.8rem', fontFamily: 'var(--font-mono)' }}>v3.9 — Enterprise</span>
            <span style={{ color: 'var(--c-text-faint)', fontSize: '0.8rem' }}>WCAG AA compliant</span>
          </div>
        </div>
      </div>

      {/* Bottom bar */}
      <div style={{
        maxWidth: 1280,
        margin: '0 auto',
        padding: '12px 24px',
        borderTop: '1px solid var(--c-border)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span style={{ color: 'var(--c-text-faint)', fontSize: '0.75rem' }}>
          © {new Date().getFullYear()} Corvin Intelligence
        </span>
        <span style={{ color: 'var(--c-text-faint)', fontSize: '0.75rem', fontFamily: 'var(--font-mono)' }}>
          ◈ Operator UI
        </span>
      </div>
    </footer>
  )
}
