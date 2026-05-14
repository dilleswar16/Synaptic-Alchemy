import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ThemeToggle } from './ThemeToggle'
import { useThreeAmMode } from '../hooks/useThreeAmMode'

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
  const [menuOpen, setMenuOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 900)
  const { active: threeAm, toggle: toggleThreeAm } = useThreeAmMode()

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < 900)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  useEffect(() => {
    setMenuOpen(false)
  }, [pathname])

  return (
    <header className="three-am-exclude" style={{
      position: 'sticky',
      top: 0,
      zIndex: 60,
      background: 'var(--c-surface)',
      backdropFilter: 'blur(var(--glass-blur))',
      WebkitBackdropFilter: 'blur(var(--glass-blur))',
      borderBottom: '1px solid var(--c-border)',
      transition: 'all var(--motion-300) var(--ease-out)',
    }}>
      {/* Amber top accent line */}
      <div style={{ height: 2, background: 'linear-gradient(90deg, var(--c-signal) 0%, transparent 55%)' }} />

      <div style={{
        maxWidth: 1320,
        margin: '0 auto',
        padding: isMobile ? '0 12px' : '0 24px',
        height: 62,
        display: 'flex',
        alignItems: 'center',
        gap: isMobile ? 10 : 20,
      }}>
        {/* Wordmark */}
        <Link to="/" style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
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
              fontSize: isMobile ? '1rem' : '1.1rem',
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
              display: isMobile ? 'none' : 'inline',
            }}>
              SRE CO-PILOT
            </span>
          </div>
        </Link>

        {/* Separator */}
        {!isMobile && <div style={{ width: 1, height: 24, background: 'var(--c-border-hi)' }} />}

        {/* Navigation */}
        {!isMobile && <nav style={{ display: 'flex', gap: 2 }}>
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
                    bottom: -5,
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
        </nav>}

        {/* Right side */}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: isMobile ? 8 : 14 }}>
          {!isMobile && <LiveClock />}

          {/* Live indicator */}
          {!isMobile && <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
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
          </div>}

          {/* Version */}
          {!isMobile && <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.62rem',
            color: 'var(--c-text-faint)',
            letterSpacing: '0.06em',
          }}>
            V3
          </span>}

          {/* Theme Toggle */}
          <ThemeToggle />

          {/* 3AM Mode Toggle */}
          {!isMobile && (
            <button
              title={threeAm ? 'Exit 3AM Mode — restore full dashboard' : 'Enable 3AM Mode — focus view for on-call'}
              onClick={toggleThreeAm}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.68rem',
                fontWeight: 700, letterSpacing: '0.04em',
                padding: '6px 12px', borderRadius: 8, border: 'none', cursor: 'pointer',
                background: threeAm ? 'rgba(59,130,246,0.18)' : 'var(--c-surface-2)',
                color: threeAm ? '#60a5fa' : 'var(--c-text-dim)',
                border: threeAm ? '1px solid rgba(59,130,246,0.35)' : '1px solid var(--c-border)',
                transition: 'all 0.2s',
              } as React.CSSProperties}
            >
              {threeAm ? '☽ 3AM' : '☾ 3AM'}
            </button>
          )}

          {!isMobile && (
            <Link
              to="/investigations"
              className="btn btn-primary"
              style={{ padding: '8px 14px', fontSize: '0.78rem' }}
            >
              Open Queue
            </Link>
          )}

          {isMobile && (
            <button
              aria-label="Toggle navigation menu"
              onClick={() => setMenuOpen(v => !v)}
              style={{
                width: 38,
                height: 38,
                borderRadius: 10,
                border: '1px solid var(--c-border)',
                background: 'var(--c-surface-2)',
                color: 'var(--c-text)',
                display: 'grid',
                placeItems: 'center',
              }}
            >
              <div style={{ display: 'grid', gap: 4 }}>
                <span style={{ display: 'block', width: 16, height: 2, background: 'currentColor' }} />
                <span style={{ display: 'block', width: 16, height: 2, background: 'currentColor' }} />
                <span style={{ display: 'block', width: 16, height: 2, background: 'currentColor' }} />
              </div>
            </button>
          )}
        </div>
      </div>

      {isMobile && (
        <>
          <div
            onClick={() => setMenuOpen(false)}
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: menuOpen ? 58 : -1,
              background: menuOpen ? 'rgba(2, 6, 23, 0.45)' : 'transparent',
              opacity: menuOpen ? 1 : 0,
              pointerEvents: menuOpen ? 'auto' : 'none',
              transition: 'opacity var(--motion-200) var(--ease-out)',
            }}
          />
          <nav
            aria-label="Mobile navigation"
            style={{
              position: 'fixed',
              top: 64,
              right: 12,
              zIndex: 59,
              minWidth: 220,
              borderRadius: 14,
              border: '1px solid var(--c-border)',
              background: 'var(--c-surface-2)',
              boxShadow: 'var(--shadow-lg)',
              transform: menuOpen ? 'translateY(0)' : 'translateY(-8px)',
              opacity: menuOpen ? 1 : 0,
              pointerEvents: menuOpen ? 'auto' : 'none',
              transition: 'all var(--motion-200) var(--ease-out)',
              padding: 8,
            }}
          >
            {NAV_LINKS.map(({ to, label }) => {
              const active = to === '/' ? pathname === '/' : pathname.startsWith(to)
              return (
                <Link
                  key={to}
                  to={to}
                  style={{
                    display: 'block',
                    borderRadius: 10,
                    padding: '10px 12px',
                    marginBottom: 4,
                    color: active ? 'var(--c-signal)' : 'var(--c-text)',
                    background: active ? 'var(--c-signal-glow)' : 'transparent',
                    fontFamily: 'var(--font-display)',
                    fontSize: '0.86rem',
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    textDecoration: 'none',
                  }}
                >
                  {label}
                </Link>
              )
            })}
          </nav>
        </>
      )}
    </header>
  )
}

function _utcString() {
  return new Date().toISOString().replace('T', ' ').substring(0, 19) + ' UTC'
}


