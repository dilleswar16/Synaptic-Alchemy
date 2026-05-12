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
    <div className="corvin-modal-overlay" onClick={onClose}>
      <div className="corvin-modal-card" onClick={e => e.stopPropagation()}>
        <button 
          onClick={onClose}
          className="corvin-modal-close"
        >
          ✕
        </button>
        {children}
      </div>
    </div>
  )

  return createPortal(content, document.body)
}
