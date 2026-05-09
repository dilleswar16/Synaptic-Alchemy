import { Link } from 'react-router-dom'
import Layout from '../components/Layout'

export default function NotFoundPage() {
  return (
    <Layout>
      <div style={{
        maxWidth: 500, margin: '80px auto', textAlign: 'center',
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 20,
      }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontWeight: 900,
          fontSize: '7rem', letterSpacing: '0.04em', lineHeight: 1,
          color: 'var(--c-signal)', opacity: 0.18,
        }}>
          404
        </div>
        <div style={{
          fontFamily: 'var(--font-display)', fontWeight: 800,
          fontSize: '1.4rem', letterSpacing: '0.06em', textTransform: 'uppercase',
          color: 'var(--c-text)',
        }}>
          Signal Not Found
        </div>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: '0.78rem',
          color: 'var(--c-text-muted)', lineHeight: 1.7,
          maxWidth: 340,
        }}>
          The investigation or route you are looking for does not exist.
          Check the URL or return to the operations dashboard.
        </div>
        <Link
          to="/"
          className="btn-primary"
          style={{ marginTop: 10, textDecoration: 'none', fontSize: '0.78rem' }}
        >
          ← Return to Dashboard
        </Link>
      </div>
    </Layout>
  )
}
