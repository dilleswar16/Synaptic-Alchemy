import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'

const NAV_LINKS = [
  { to: '/',               label: 'Dashboard' },
  { to: '/investigations', label: 'Investigations' },
]

function LiveClock() {
  const [time, setTime] = useState(() => _utcString())
  useEffect(() => {
    const id = setInterval(() => setTime(_utcString()), 1000)
    return () => clearInterval(id)
  }, [])
  return (
    <span style={{
      fontFamily: 'var(--font-mono)',
      fontSize: '0.72rem',
      color: 'var(--c-text-muted)',
      letterSpacing: '0.04em',
    }}>
      {time}
    </span>
  )
}

export default function NavBar() {
  const { pathname } = useLocation()

  return (
    <header style={{
      position: 'sticky',
      top: 0,
      zIndex: 50,
      background: 'rgba(3,5,7,0.96)',
      backdropFilter: 'blur(12px)',
      WebkitBackdropFilter: 'blur(12px)',
      borderBottom: '1px solid var(--c-border-hi)',
    }}>
      {/* Amber top accent line */}
      <div style={{ height: 2, background: 'linear-gradient(90deg, var(--c-signal) 0%, transparent 60%)' }} />

      <div style={{
        maxWidth: 1320,
        margin: '0 auto',
        padding: '0 24px',
        height: 52,
        display: 'flex',
        alignItems: 'center',
        gap: 32,
      }}>
        {/* Wordmark */}
        <Link to="/" style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 10 }}>
          {/* Signal bars icon */}
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 16 }}>
            {[6, 10, 14, 18].map((h, i) => (
              <div key={i} style={{
                width: 3,
                height: h,
                borderRadius: 1,
                background: i < 3 ? 'var(--c-signal)' : 'var(--c-border-hi)',
              }} />
            ))}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1 }}>
            <span style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 900,
              fontSize: '1.1rem',
              letterSpacing: '0.12em',
              color: 'var(--c-text)',
            }}>
              CORVIN
            </span>
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.55rem',
              color: 'var(--c-signal)',
              letterSpacing: '0.16em',
            }}>
              SRE CO-PILOT
            </span>
          </div>
        </Link>

        {/* Separator */}
        <div style={{ width: 1, height: 24, background: 'var(--c-border-hi)' }} />

        {/* Navigation */}
        <nav style={{ display: 'flex', gap: 2 }}>
          {NAV_LINKS.map(({ to, label }) => {
            const active = to === '/' ? pathname === '/' : pathname.startsWith(to)
            return (
              <Link key={to} to={to} style={{ textDecoration: 'none', position: 'relative', padding: '4px 14px' }}>
                <span style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: '0.82rem',
                  fontWeight: 700,
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  color: active ? 'var(--c-signal)' : 'var(--c-text-dim)',
                  transition: 'color 0.15s',
                }}>
                  {label}
                </span>
                {/* Active underline */}
                {active && (
                  <div style={{
                    position: 'absolute',
                    bottom: -1,
                    left: 14,
                    right: 14,
                    height: 2,
                    background: 'var(--c-signal)',
                    borderRadius: 1,
                  }} />
                )}
              </Link>
            )
          })}
        </nav>

        {/* Right side */}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 20 }}>
          <LiveClock />

          {/* Live indicator */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span
              className="animate-pulse-glow"
              style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--c-signal)', display: 'block' }}
            />
            <span style={{
              fontFamily: 'var(--font-display)',
              fontSize: '0.7rem',
              fontWeight: 700,
              letterSpacing: '0.12em',
              color: 'var(--c-signal)',
            }}>
              LIVE
            </span>
          </div>

          {/* Version */}
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.62rem',
            color: 'var(--c-text-faint)',
            letterSpacing: '0.06em',
          }}>
            V3
          </span>
        </div>
      </div>
    </header>
  )
}

function _utcString() {
  return new Date().toISOString().replace('T', '  ').substring(0, 21) + ' UTC'
}


