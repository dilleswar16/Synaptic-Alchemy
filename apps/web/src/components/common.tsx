import { ReactNode } from 'react'

type ButtonVariant = 'primary' | 'secondary' | 'ghost'
type ButtonSize = 'sm' | 'md' | 'lg'

interface ButtonProps {
  onClick?: () => void
  variant?: ButtonVariant
  size?: ButtonSize
  disabled?: boolean
  children: ReactNode
  title?: string
  className?: string
  type?: 'button' | 'submit' | 'reset'
  fullWidth?: boolean
  icon?: ReactNode
  iconRight?: ReactNode
}

export function Button({
  onClick,
  variant = 'primary',
  size = 'md',
  disabled = false,
  children,
  title,
  className,
  type = 'button',
  fullWidth = false,
  icon,
  iconRight,
}: ButtonProps) {
  const sizeStyles = {
    sm: { padding: '6px 12px', fontSize: '0.8rem' },
    md: { padding: '10px 20px', fontSize: '0.9rem' },
    lg: { padding: '12px 28px', fontSize: '1rem' },
  }

  const variantClass = `btn btn-${variant}`

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      type={type}
      title={title}
      className={`${variantClass} ${className || ''}`}
      style={{
        width: fullWidth ? '100%' : 'auto',
        opacity: disabled ? 0.5 : 1,
        cursor: disabled ? 'not-allowed' : 'pointer',
        ...sizeStyles[size],
      }}
    >
      {icon && <span style={{ display: 'inline-flex', alignItems: 'center' }}>{icon}</span>}
      {children}
      {iconRight && <span style={{ display: 'inline-flex', alignItems: 'center' }}>{iconRight}</span>}
    </button>
  )
}

/**
 * Card component — elevated container with consistent styling across themes
 */
interface CardProps {
  children: ReactNode
  className?: string
  style?: React.CSSProperties
  accent?: boolean
  onClick?: () => void
}

export function Card({ children, className, style, accent, onClick }: CardProps) {
  return (
    <div
      className={`${accent ? 'panel-signal' : 'panel'} ${className || ''}`}
      style={{
        cursor: onClick ? 'pointer' : 'default',
        ...style,
      }}
      onClick={onClick}
    >
      {children}
    </div>
  )
}

/**
 * Badge component — inline status indicator
 */
interface BadgeProps {
  status: 'pending' | 'approved' | 'rejected' | 'executed'
  children?: ReactNode
}

export function Badge({ status, children }: BadgeProps) {
  return (
    <span className={`badge badge-${status}`}>
      {children || status.toUpperCase()}
    </span>
  )
}

/**
 * Empty state component — show when no data is available
 */
interface EmptyStateProps {
  icon?: ReactNode
  title: string
  message?: string
  action?: { label: string; onClick: () => void }
}

export function EmptyState({ icon, title, message, action }: EmptyStateProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 16,
        padding: '64px 24px',
        textAlign: 'center',
        color: 'var(--c-text-muted)',
      }}
    >
      {icon && (
        <div style={{ fontSize: '3rem', opacity: 0.5 }}>
          {icon}
        </div>
      )}
      <div>
        <h3 style={{ margin: '0 0 8px 0', color: 'var(--c-text)', fontSize: '1.1rem', fontWeight: 600 }}>
          {title}
        </h3>
        {message && <p style={{ margin: 0, fontSize: '0.9rem' }}>{message}</p>}
      </div>
      {action && (
        <Button variant="primary" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  )
}

/**
 * Skeleton loader — placeholder for async content
 */
export function Skeleton({ width = '100%', height = '20px', style }: { width?: string; height?: string; style?: React.CSSProperties }) {
  return (
    <div
      style={{
        width,
        height,
        borderRadius: 4,
        background: 'linear-gradient(90deg, var(--c-surface-2), var(--c-surface-3), var(--c-surface-2))',
        backgroundSize: '200% 100%',
        animation: 'shimmer 2s infinite',
        ...style,
      }}
    />
  )
}

/**
 * Loading spinner component
 */
export function Spinner() {
  return (
    <div style={{
      display: 'inline-block',
      width: 20,
      height: 20,
      border: '2px solid var(--c-border)',
      borderTopColor: 'var(--c-signal)',
      borderRadius: '50%',
      animation: 'spin 0.8s linear infinite',
    }} />
  )
}
