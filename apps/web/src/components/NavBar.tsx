import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ThemeToggle } from './ThemeToggle'
import { useThreeAmMode } from '../hooks/useThreeAmMode'
import { useTheme } from '../context/ThemeContext'

const NAV_LINKS = [
  { to: '/',               label: 'Dashboard',      icon: '◎' },
  { to: '/predictive-analytics', label: 'Predictive', icon: '◉' },
  { to: '/investigations', label: 'Investigations', icon: '◈' },
  { to: '/applications',   label: 'Applications',   icon: '⊞' },
  { to: '/slo',            label: 'SLO',            icon: '◐' },
  { to: '/validations',    label: 'Validations',    icon: '✓' },
  { to: '/corvin',         label: 'Corvin AI',      icon: '◆' },
  { to: '/war-games',      label: 'War Room',       icon: '⚔' },
]

export default function NavBar() {
  const { pathname } = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 960)
  const { active: threeAm, toggle: toggleThreeAm } = useThreeAmMode()
  const { theme } = useTheme()

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < 960)
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
      boxShadow: '0 1px 0 var(--c-border)',
      transition: 'background 0.3s ease',
    }}>
      <div style={{
        maxWidth: 1400,
        margin: '0 auto',
        padding: isMobile ? '0 16px' : '0 32px',
        height: 64,
        display: 'flex',
        alignItems: 'center',
        gap: 0,
      }}>

        {/* ── Logo ── */}
        <Link to="/" style={{
          textDecoration: 'none',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          flexShrink: 0,
          marginRight: 32,
        }}>
          <img
            src="/metlife-logo.svg"
            alt="MetLife"
            style={{
              height: 20,
              width: 'auto',
              display: 'block',
              filter: theme === 'dark' ? 'brightness(0) invert(1)' : 'none',
            }}
          />
          <span style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 700,
            fontSize: '1.0625rem',
            color: 'var(--c-text)',
            letterSpacing: '-0.025em',
          }}>
            Corvin
          </span>
        </Link>

        {/* ── Desktop Nav ── */}
        {!isMobile && (
          <nav style={{
            display: 'flex',
            alignItems: 'stretch',
            height: 64,
            flex: 1,
            gap: 2,
          }}>
            {NAV_LINKS.map(({ to, label }) => {
              const active = to === '/' ? pathname === '/' : pathname.startsWith(to)
              return (
                <Link key={to} to={to} style={{
                  textDecoration: 'none',
                  padding: '0 14px',
                  height: '100%',
                  display: 'inline-flex',
                  alignItems: 'center',
                  fontSize: '0.875rem',
                  fontWeight: active ? 600 : 400,
                  letterSpacing: '-0.01em',
                  color: active ? 'var(--c-signal)' : 'var(--c-text-dim)',
                  borderBottom: active ? '2px solid var(--c-signal)' : '2px solid transparent',
                  marginBottom: '-1px',
                  transition: 'color 0.15s ease, border-color 0.15s ease',
                  whiteSpace: 'nowrap',
                }}>
                  {label}
                </Link>
              )
            })}
          </nav>
        )}

        {/* ── Right side ── */}
        <div style={{
          marginLeft: 'auto',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          flexShrink: 0,
        }}>

          {/* Live dot */}
          {!isMobile && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '5px 12px',
              borderRadius: 20,
              background: 'var(--c-success-bg)',
              border: '1px solid var(--c-success-border)',
            }}>
              <span style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: 'var(--c-success)',
                display: 'block',
                flexShrink: 0,
                boxShadow: '0 0 6px rgba(52, 211, 153, 0.5)',
                animation: 'signal-pulse 2.5s ease-in-out infinite',
              }} />
              <span style={{
                fontSize: '0.8125rem',
                fontWeight: 500,
                color: 'var(--c-success)',
              }}>
                Live
              </span>
            </div>
          )}

          {/* Theme toggle */}
          <ThemeToggle />

          {/* 3AM */}
          {!isMobile && (
            <button
              title={threeAm ? 'Exit 3AM Mode' : 'Enable 3AM Mode'}
              onClick={toggleThreeAm}
              style={{
                fontSize: '0.8125rem',
                fontWeight: 500,
                padding: '5px 12px',
                borderRadius: 20,
                cursor: 'pointer',
                background: threeAm ? 'var(--c-info-bg)' : 'transparent',
                color: threeAm ? 'var(--c-info)' : 'var(--c-text-muted)',
                border: threeAm ? '1px solid var(--c-info-border)' : '1px solid var(--c-border)',
                transition: 'all 0.18s cubic-bezier(0.22, 1, 0.36, 1)',
              } as React.CSSProperties}
            >
              {threeAm ? '☽ 3AM' : '☾ 3AM'}
            </button>
          )}

          {/* Queue CTA */}
          {!isMobile && (
            <Link
              to="/investigations"
              className="btn btn-primary"
              style={{ padding: '7px 18px', fontSize: '0.875rem', borderRadius: 20 }}
            >
              Open Queue
            </Link>
          )}

          {/* Mobile hamburger */}
          {isMobile && (
            <button
              aria-label="Toggle navigation menu"
              onClick={() => setMenuOpen(v => !v)}
              style={{
                width: 38,
                height: 38,
                borderRadius: 10,
                border: '1px solid var(--c-border)',
                background: menuOpen ? 'var(--c-surface-2)' : 'transparent',
                color: 'var(--c-text)',
                display: 'grid',
                placeItems: 'center',
                transition: 'background 0.15s',
                cursor: 'pointer',
              }}
            >
              <div style={{ display: 'grid', gap: 4 }}>
                <span style={{ display: 'block', width: 16, height: 1.5, background: 'currentColor', borderRadius: 2 }} />
                <span style={{ display: 'block', width: 16, height: 1.5, background: 'currentColor', borderRadius: 2 }} />
                <span style={{ display: 'block', width: 16, height: 1.5, background: 'currentColor', borderRadius: 2 }} />
              </div>
            </button>
          )}
        </div>
      </div>

      {/* ── Mobile drawer ── */}
      {isMobile && (
        <>
          <div
            onClick={() => setMenuOpen(false)}
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: menuOpen ? 58 : -1,
              background: menuOpen ? 'rgba(0, 0, 0, 0.4)' : 'transparent',
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
              top: 68,
              right: 16,
              zIndex: 59,
              minWidth: 200,
              borderRadius: 14,
              border: '1px solid var(--c-border-hi)',
              background: 'var(--c-surface)',
              boxShadow: 'var(--shadow-lg)',
              transform: menuOpen ? 'translateY(0) scale(1)' : 'translateY(-8px) scale(0.97)',
              opacity: menuOpen ? 1 : 0,
              pointerEvents: menuOpen ? 'auto' : 'none',
              transition: 'all 0.2s cubic-bezier(0.22, 1, 0.36, 1)',
              padding: 8,
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
                    gap: 10,
                    borderRadius: 9,
                    padding: '10px 14px',
                    color: active ? 'var(--c-signal)' : 'var(--c-text-dim)',
                    background: active ? 'var(--c-signal-light)' : 'transparent',
                    fontSize: '0.9375rem',
                    fontWeight: active ? 600 : 400,
                    textDecoration: 'none',
                    transition: 'background 0.15s, color 0.15s',
                  }}
                >
                  <span style={{ fontSize: '0.75rem', opacity: 0.6 }}>{icon}</span>
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


