import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ThemeToggle } from './ThemeToggle'
import { useThreeAmMode } from '../hooks/useThreeAmMode'
import { useTheme } from '../context/ThemeContext'

const NAV_LINKS = [
  { to: '/',               label: 'Dashboard',      icon: '◎' },
  { to: '/predictive-analytics', label: 'Predictive', icon: '◉' },
  { to: '/investigations', label: 'Investigations', icon: '◈' },
  { to: '/corvin',         label: 'Corvin AI',      icon: '◆' },
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
      fontSize: '0.6875rem',
      color: 'var(--c-text-faint)',
      letterSpacing: '0.04em',
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
  const { theme } = useTheme()
  const isLight = theme === 'light'

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
      background: isLight ? 'rgba(248, 248, 252, 0.85)' : 'rgba(14, 14, 20, 0.8)',
      backdropFilter: 'blur(12px)',
      WebkitBackdropFilter: 'blur(12px)',
      borderBottom: '1px solid var(--c-border)',
      transition: 'background 0.3s ease',
    }}>
      <div style={{
        maxWidth: 1280,
        margin: '0 auto',
        padding: isMobile ? '0 12px' : '0 24px',
        height: 56,
        display: 'flex',
        alignItems: 'center',
        gap: isMobile ? 8 : 16,
      }}>
        {/* Logo */}
        <Link to="/" style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
          {/* Corvin sigil mark */}
          <svg width={28} height={28} viewBox="0 0 32 32" fill="none" style={{ flexShrink: 0 }}>
            <defs>
              <linearGradient id="nav-bg" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
                <stop stopColor="#0f766e"/><stop offset="1" stopColor="#14b8a6"/>
              </linearGradient>
            </defs>
            <rect width="32" height="32" rx="7.5" fill="url(#nav-bg)"/>
            <path d="M21.5 9A9 9 0 1 0 21.5 23" stroke="white" strokeWidth="2.8" fill="none" strokeLinecap="round"/>
            <path d="M16 12L20 16L16 20L12 16Z" fill="white"/>
          </svg>
          <span style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 800,
            fontSize: '1rem',
            color: 'var(--c-text)',
            letterSpacing: '-0.02em',
          }}>
            Corvin
          </span>
        </Link>

        {/* Separator */}
        {!isMobile && <div style={{ width: 1, height: 22, background: 'var(--c-border-hi)', flexShrink: 0, opacity: 0.6 }} />}

        {/* Navigation pills */}
        {!isMobile && <nav style={{
          display: 'flex',
          gap: 2,
          padding: '3px',
          borderRadius: 10,
          background: 'var(--c-surface)',
          border: '1px solid var(--c-border)',
        }}>
          {NAV_LINKS.map(({ to, label, icon }) => {
            const active = to === '/' ? pathname === '/' : pathname.startsWith(to)
            return (
              <Link key={to} to={to} style={{
                textDecoration: 'none',
                padding: '5px 14px',
                borderRadius: 7,
                fontSize: '0.8125rem',
                fontWeight: active ? 600 : 500,
                color: active ? 'var(--c-text)' : 'var(--c-text-muted)',
                background: active ? 'var(--c-surface-2)' : 'transparent',
                transition: 'all 0.18s cubic-bezier(0.22, 1, 0.36, 1)',
                display: 'flex',
                alignItems: 'center',
                gap: 5,
                boxShadow: active ? 'var(--shadow-sm)' : 'none',
              }}>
                <span style={{ fontSize: '0.65rem', opacity: active ? 0.9 : 0.4 }}>{icon}</span>
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
            padding: '4px 10px',
            borderRadius: 8,
            background: 'var(--c-success-bg)',
            border: '1px solid var(--c-success-border)',
          }}>
            <span style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: 'var(--c-success)',
              display: 'block',
              boxShadow: '0 0 6px rgba(52, 211, 153, 0.4)',
              animation: 'signal-pulse 2.5s ease-in-out infinite',
            }} />
            <span style={{
              fontSize: '0.6875rem',
              fontWeight: 600,
              color: 'var(--c-success)',
              letterSpacing: '0.03em',
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
                fontWeight: 600,
                padding: '5px 10px',
                borderRadius: 8,
                cursor: 'pointer',
                background: threeAm ? 'var(--c-info-bg)' : 'var(--c-surface-2)',
                color: threeAm ? 'var(--c-info)' : 'var(--c-text-muted)',
                border: threeAm ? '1px solid var(--c-info-border)' : '1px solid var(--c-border)',
                transition: 'all 0.18s cubic-bezier(0.22, 1, 0.36, 1)',
              } as React.CSSProperties}
            >
              {threeAm ? '☽ 3AM' : '☾ 3AM'}
            </button>
          )}

          {!isMobile && (
            <Link
              to="/investigations"
              className="btn btn-primary"
              style={{ padding: '7px 16px', fontSize: '0.8125rem', borderRadius: 9 }}
            >
              Open Queue
            </Link>
          )}

          {isMobile && (
            <button
              aria-label="Toggle navigation menu"
              onClick={() => setMenuOpen(v => !v)}
              style={{
                width: 36,
                height: 36,
                borderRadius: 9,
                border: '1px solid var(--c-border)',
                background: 'var(--c-surface-2)',
                color: 'var(--c-text)',
                display: 'grid',
                placeItems: 'center',
                transition: 'background 0.15s',
              }}
            >
              <div style={{ display: 'grid', gap: 4 }}>
                <span style={{ display: 'block', width: 14, height: 1.5, background: 'currentColor', borderRadius: 2 }} />
                <span style={{ display: 'block', width: 14, height: 1.5, background: 'currentColor', borderRadius: 2 }} />
                <span style={{ display: 'block', width: 14, height: 1.5, background: 'currentColor', borderRadius: 2 }} />
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
              background: menuOpen ? 'rgba(6, 6, 10, 0.6)' : 'transparent',
              backdropFilter: menuOpen ? 'blur(4px)' : 'none',
              opacity: menuOpen ? 1 : 0,
              pointerEvents: menuOpen ? 'auto' : 'none',
              transition: 'opacity 0.2s ease',
            }}
          />
          <nav
            aria-label="Mobile navigation"
            style={{
              position: 'fixed',
              top: 60,
              right: 12,
              zIndex: 59,
              minWidth: 220,
              borderRadius: 12,
              border: '1px solid var(--c-border-hi)',
              background: 'var(--c-surface)',
              boxShadow: 'var(--shadow-lg)',
              transform: menuOpen ? 'translateY(0) scale(1)' : 'translateY(-8px) scale(0.97)',
              opacity: menuOpen ? 1 : 0,
              pointerEvents: menuOpen ? 'auto' : 'none',
              transition: 'all 0.2s cubic-bezier(0.22, 1, 0.36, 1)',
              padding: 6,
            }}
          >
            {NAV_LINKS.map(({ to, label, icon }) => {
              const active = to === '/' ? pathname === '/' : pathname.startsWith(to)
              return (
                <Link
                  key={to}
                  to={to}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    borderRadius: 8,
                    padding: '10px 14px',
                    marginBottom: 2,
                    color: active ? 'var(--c-text)' : 'var(--c-text-dim)',
                    background: active ? 'var(--c-surface-2)' : 'transparent',
                    fontSize: '0.8125rem',
                    fontWeight: active ? 600 : 500,
                    textDecoration: 'none',
                    transition: 'background 0.15s',
                  }}
                >
                  <span style={{ fontSize: '0.7rem', opacity: 0.5 }}>{icon}</span>
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


