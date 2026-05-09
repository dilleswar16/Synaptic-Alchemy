/**
 * useTypewriter — animates text character-by-character.
 * speed: ms per character.
 */
import { useEffect, useState } from 'react'

export function useTypewriter(text: string, speed = 15): { displayed: string; done: boolean } {
  const [displayed, setDisplayed] = useState('')

  useEffect(() => {
    if (!text) { setDisplayed(''); return }
    setDisplayed('')
    let i = 0
    const timer = setInterval(() => {
      i++
      setDisplayed(text.slice(0, i))
      if (i >= text.length) clearInterval(timer)
    }, speed)
    return () => clearInterval(timer)
  }, [text, speed])

  return { displayed, done: displayed.length >= text.length }
}
