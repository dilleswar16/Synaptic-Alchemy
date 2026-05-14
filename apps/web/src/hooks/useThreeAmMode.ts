/**
 * useThreeAmMode — V3.9 focus mode hook.
 *
 * Persists to localStorage('corvin-3am-mode').
 * When active, the UI hides non-critical panels so on-call engineers
 * see only: IncidentHeroCard, SLA countdown, Approval, Execution.
 */
import { useState, useEffect, useCallback } from 'react'

const KEY = 'corvin-3am-mode'

function readStored(): boolean {
  try { return localStorage.getItem(KEY) === 'true' } catch { return false }
}

function applyToDom(active: boolean) {
  document.documentElement.setAttribute('data-3am', active ? '1' : '0')
}

export function useThreeAmMode() {
  const [active, setActive] = useState<boolean>(() => {
    const stored = readStored()
    // Apply immediately so CSS is correct on first paint, not after first effect flush
    if (typeof document !== 'undefined') applyToDom(stored)
    return stored
  })

  useEffect(() => {
    try { localStorage.setItem(KEY, String(active)) } catch { /* unavailable */ }
    applyToDom(active)
  }, [active])

  const toggle = useCallback(() => setActive(v => !v), [])

  return { active, toggle }
}
