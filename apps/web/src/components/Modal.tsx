import { useEffect, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

interface ModalProps {
  isOpen: boolean
  onClose: () => void
  children: ReactNode
}

export function Modal({ isOpen, onClose, children }: ModalProps) {
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    if (isOpen) {
      window.addEventListener('keydown', handleEsc)
      document.body.style.overflow = 'hidden' // prevent background scrolling
    }
    return () => {
      window.removeEventListener('keydown', handleEsc)
      document.body.style.overflow = 'auto'
    }
  }, [isOpen, onClose])

  if (!isOpen) return null

  const content = (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 99999,
      background: 'rgba(11, 15, 26, 0.85)',
      backdropFilter: 'blur(12px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: '40px',
    }} onClick={onClose}>
      <div style={{
        background: '#0B0F19',
        border: '1px solid var(--c-border-glow)',
        boxShadow: '0 8px 32px var(--c-signal-glow)',
        borderRadius: 8,
        width: '100%', maxWidth: 860, maxHeight: '90vh',
        overflowY: 'auto',
        padding: '40px',
        position: 'relative',
      }} onClick={e => e.stopPropagation()}>
        <button 
          onClick={onClose}
          style={{
            position: 'absolute', top: 20, right: 20,
            background: 'var(--c-surface-2)', border: '1px solid var(--c-border-hi)',
            color: 'var(--c-text-muted)', width: 32, height: 32, borderRadius: 16,
            display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer',
          }}
        >
          ✕
        </button>
        {children}
      </div>
    </div>
  )

  return createPortal(content, document.body)
}
