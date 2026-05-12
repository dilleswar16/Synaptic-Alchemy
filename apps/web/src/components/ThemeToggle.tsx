import { useTheme } from '../context/ThemeContext'

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const isLight = theme === 'light'

  return (
    <button
      onClick={toggleTheme}
      aria-label={`Switch to ${isLight ? 'dark' : 'light'} mode`}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 40,
        height: 40,
        borderRadius: 10,
        background: 'var(--c-surface-2)',
        border: '1px solid var(--c-border)',
        cursor: 'pointer',
        transition: 'transform var(--motion-200) var(--ease-out), border-color var(--motion-200) var(--ease-out), background-color var(--motion-200) var(--ease-out)',
        color: 'var(--c-text)',
        position: 'relative',
        overflow: 'hidden',
      }}
      onMouseEnter={e => {
        const el = e.currentTarget as HTMLButtonElement
        el.style.backgroundColor = 'var(--c-surface-3)'
        el.style.borderColor = 'var(--c-signal)'
        el.style.transform = 'translateY(-1px)'
      }}
      onMouseLeave={e => {
        const el = e.currentTarget as HTMLButtonElement
        el.style.backgroundColor = 'var(--c-surface-2)'
        el.style.borderColor = 'var(--c-border)'
        el.style.transform = 'translateY(0)'
      }}
      onFocus={e => {
        e.currentTarget.style.boxShadow = '0 0 0 3px var(--c-signal-glow)'
      }}
      onBlur={e => {
        e.currentTarget.style.boxShadow = 'none'
      }}
    >
      <span
        style={{
          position: 'absolute',
          display: 'grid',
          placeItems: 'center',
          inset: 0,
          opacity: isLight ? 0 : 1,
          transform: `rotate(${isLight ? -90 : 0}deg) scale(${isLight ? 0.75 : 1})`,
          transition: 'opacity var(--motion-200) var(--ease-out), transform var(--motion-300) var(--ease-bounce)',
        }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="5" />
          <line x1="12" y1="1" x2="12" y2="3" />
          <line x1="12" y1="21" x2="12" y2="23" />
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
          <line x1="1" y1="12" x2="3" y2="12" />
          <line x1="21" y1="12" x2="23" y2="12" />
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
        </svg>
      </span>
      <span
        style={{
          position: 'absolute',
          display: 'grid',
          placeItems: 'center',
          inset: 0,
          opacity: isLight ? 1 : 0,
          transform: `rotate(${isLight ? 0 : 90}deg) scale(${isLight ? 1 : 0.75})`,
          transition: 'opacity var(--motion-200) var(--ease-out), transform var(--motion-300) var(--ease-bounce)',
        }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      </span>
    </button>
  )
}
