import { Link } from 'react-router-dom'

export default function Footer() {
  return (
    <footer
      style={{
        marginTop: 40,
        borderTop: '1px solid var(--c-border)',
        background: 'var(--c-surface-2)',
      }}
    >
      <div
        style={{
          maxWidth: 1280,
          margin: '0 auto',
          padding: '28px 24px',
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 20,
        }}
      >
        <div>
          <div
            style={{
              fontSize: '0.9375rem',
              fontWeight: 600,
              color: 'var(--c-text)',
              marginBottom: 8,
            }}
          >
            Corvin Operator
          </div>
          <p style={{ margin: 0, color: 'var(--c-text-muted)', fontSize: '0.86rem', lineHeight: 1.6 }}>
            Premium incident investigation UI for SRE workflows across enrichment, RCA and fix strategy.
          </p>
        </div>

        <div>
          <div className="section-label" style={{ marginBottom: 10 }}>Navigation</div>
          <div style={{ display: 'grid', gap: 8 }}>
            <Link to="/">Dashboard</Link>
            <Link to="/investigations">Investigations</Link>
          </div>
        </div>

        <div>
          <div className="section-label" style={{ marginBottom: 10 }}>Status</div>
          <div style={{ display: 'grid', gap: 8 }}>
            <span style={{ color: 'var(--c-text-muted)', fontSize: '0.84rem' }}>Theme-aware UI system</span>
            <span style={{ color: 'var(--c-text-muted)', fontSize: '0.84rem' }}>WCAG-focused contrast tokens</span>
          </div>
        </div>
      </div>
    </footer>
  )
}
