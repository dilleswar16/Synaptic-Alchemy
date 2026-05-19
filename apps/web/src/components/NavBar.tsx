import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ThemeToggle } from './ThemeToggle'
import { useThreeAmMode } from '../hooks/useThreeAmMode'

const NAV_LINKS = [
  { to: '/',               label: 'Dashboard' },
  { to: '/investigations', label: 'Investigations' },
  { to: '/corvin',         label: 'Corvin AI' },
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
      fontSize: '0.7rem',
      color: 'var(--c-text-muted)',
      letterSpacing: '0.02em',
      fontWeight: 500,
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
      borderBottom: '1px solid var(--c-border)',
      transition: 'background 0.2s ease',
    }}>
      <div style={{
        maxWidth: 1280,
        margin: '0 auto',
        padding: isMobile ? '0 12px' : '0 24px',
        height: 52,
        display: 'flex',
        alignItems: 'center',
        gap: isMobile ? 8 : 16,
      }}>
        {/* Wordmark */}
        <Link to="/" style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
          {/* Corvin logo mark */}
          <div style={{
            width: 26,
            height: 26,
            borderRadius: 7,
            background: 'var(--c-signal)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}>
            <span style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              fontSize: '0.8rem',
              color: 'white',
              lineHeight: 1,
            }}>C</span>
          </div>
          <span style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 700,
            fontSize: '0.95rem',
            color: 'var(--c-text)',
            letterSpacing: '-0.01em',
          }}>
            Corvin
          </span>
        </Link>

        {/* Separator */}
        {!isMobile && <div style={{ width: 1, height: 20, background: 'var(--c-border-hi)', flexShrink: 0 }} />}

        {/* Navigation */}
        {!isMobile && <nav style={{ display: 'flex', gap: 1 }}>
          {NAV_LINKS.map(({ to, label }) => {
            const active = to === '/' ? pathname === '/' : pathname.startsWith(to)
            return (
              <Link key={to} to={to} style={{
                textDecoration: 'none',
                padding: '6px 12px',
                borderRadius: 6,
                fontSize: '0.8125rem',
                fontWeight: 500,
                color: active ? 'var(--c-text)' : 'var(--c-text-muted)',
                background: active ? 'var(--c-surface-2)' : 'transparent',
                transition: 'color 0.15s, background 0.15s',
              }}>
                {label}
              </Link>
            )
          })}
        </nav>}

        {/* Right side */}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: isMobile ? 6 : 10 }}>
          {!isMobile && <LiveClock />}

          {/* Live indicator */}
          {!isMobile && <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 5,
            padding: '3px 8px',
            borderRadius: 6,
            background: 'var(--c-success-bg)',
            border: '1px solid var(--c-success-border)',
          }}>
            <span style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: 'var(--c-success)',
              display: 'block',
              animation: 'signal-pulse 2s ease-in-out infinite',
            }} />
            <span style={{
              fontSize: '0.6875rem',
              fontWeight: 500,
              color: 'var(--c-success)',
            }}>
              Live
            </span>
          </div>}

          {/* Theme Toggle */}
          <ThemeToggle />

          {/* 3AM Mode Toggle */}
          {!isMobile && (
            <button
              title={threeAm ? 'Exit 3AM Mode' : 'Enable 3AM Mode'}
              onClick={toggleThreeAm}
              style={{
                fontSize: '0.75rem',
                fontWeight: 500,
                padding: '5px 10px',
                borderRadius: 6,
                cursor: 'pointer',
                background: threeAm ? 'var(--c-info-bg)' : 'var(--c-surface-2)',
                color: threeAm ? 'var(--c-info)' : 'var(--c-text-muted)',
                border: threeAm ? '1px solid var(--c-info-border)' : '1px solid var(--c-border)',
                transition: 'all 0.15s',
              } as React.CSSProperties}
            >
              {threeAm ? '☽ 3AM' : '☾ 3AM'}
            </button>
          )}

          {!isMobile && (
            <Link
              to="/investigations"
              className="btn btn-primary"
              style={{ padding: '6px 12px', fontSize: '0.8125rem' }}
            >
              Open Queue
            </Link>
          )}

          {isMobile && (
            <button
              aria-label="Toggle navigation menu"
              onClick={() => setMenuOpen(v => !v)}
              style={{
                width: 34,
                height: 34,
                borderRadius: 8,
                border: '1px solid var(--c-border)',
                background: 'var(--c-surface-2)',
                color: 'var(--c-text)',
                display: 'grid',
                placeItems: 'center',
              }}
            >
              <div style={{ display: 'grid', gap: 4 }}>
                <span style={{ display: 'block', width: 14, height: 1.5, background: 'currentColor', borderRadius: 1 }} />
                <span style={{ display: 'block', width: 14, height: 1.5, background: 'currentColor', borderRadius: 1 }} />
                <span style={{ display: 'block', width: 14, height: 1.5, background: 'currentColor', borderRadius: 1 }} />
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
              background: menuOpen ? 'rgba(0, 0, 0, 0.4)' : 'transparent',
              opacity: menuOpen ? 1 : 0,
              pointerEvents: menuOpen ? 'auto' : 'none',
              transition: 'opacity 0.15s ease',
            }}
          />
          <nav
            aria-label="Mobile navigation"
            style={{
              position: 'fixed',
              top: 56,
              right: 12,
              zIndex: 59,
              minWidth: 200,
              borderRadius: 10,
              border: '1px solid var(--c-border)',
              background: 'var(--c-surface)',
              boxShadow: 'var(--shadow-lg)',
              transform: menuOpen ? 'translateY(0)' : 'translateY(-6px)',
              opacity: menuOpen ? 1 : 0,
              pointerEvents: menuOpen ? 'auto' : 'none',
              transition: 'all 0.15s ease',
              padding: 6,
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
                    borderRadius: 6,
                    padding: '8px 12px',
                    marginBottom: 2,
                    color: active ? 'var(--c-text)' : 'var(--c-text-dim)',
                    background: active ? 'var(--c-surface-2)' : 'transparent',
                    fontSize: '0.8125rem',
                    fontWeight: 500,
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


