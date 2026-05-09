import { useState } from 'react'

/** Renders a truncated request ID that copies to clipboard on click. */
export function CopyableId({ requestId }: { requestId: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(requestId).catch(() => {})
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button
      onClick={copy}
      title={`Copy ID: ${requestId}`}
      style={{
        fontFamily: 'var(--font-mono)', fontSize: '0.62rem',
        color: copied ? 'var(--c-green)' : 'var(--c-text-faint)',
        letterSpacing: '0.04em', background: 'none', border: 'none',
        cursor: 'pointer', padding: '1px 4px', borderRadius: 2,
        transition: 'color 0.2s',
      }}
    >
      {copied ? '✓ copied' : `#${requestId.substring(0, 8)}…`}
    </button>
  )
}
