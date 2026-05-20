/**
 * Browser-native Text-to-Speech hook using the SpeechSynthesis API.
 * Provides speak/stop with a speaking state indicator.
 */
import { useState, useRef, useCallback, useEffect } from 'react'

interface SpeechSynthesisHook {
  /** Whether audio is currently playing */
  speaking: boolean
  /** Whether the browser supports TTS */
  supported: boolean
  /** Speak the given text. Stops any current utterance first. */
  speak: (text: string) => void
  /** Stop any current speech */
  stop: () => void
}

/**
 * Strip markdown syntax so the TTS reads clean prose.
 */
function stripMarkdown(md: string): string {
  return md
    .replace(/```[\s\S]*?```/g, '')           // code blocks
    .replace(/`([^`]+)`/g, '$1')              // inline code
    .replace(/#{1,6}\s+/g, '')                // headings
    .replace(/\*\*([^*]+)\*\*/g, '$1')        // bold
    .replace(/\*([^*]+)\*/g, '$1')            // italic
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')  // links
    .replace(/[>\-|]/g, '')                   // blockquotes, list markers, table pipes
    .replace(/\n{2,}/g, '. ')                 // paragraph breaks → pause
    .replace(/\n/g, ' ')
    .trim()
}

export function useSpeechSynthesis(voiceLang = 'en-US'): SpeechSynthesisHook {
  const [speaking, setSpeaking] = useState(false)
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null)

  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window

  // Clean up on unmount
  useEffect(() => {
    return () => { window.speechSynthesis?.cancel() }
  }, [])

  const speak = useCallback((text: string) => {
    if (!supported) return
    window.speechSynthesis.cancel()

    const clean = stripMarkdown(text)
    if (!clean) return

    const utterance = new SpeechSynthesisUtterance(clean)
    utterance.lang = voiceLang
    utterance.rate = 1.05
    utterance.pitch = 1.0

    // Try to pick a natural-sounding voice
    const voices = window.speechSynthesis.getVoices()
    const preferred = voices.find(v => v.lang.startsWith('en') && v.name.toLowerCase().includes('natural'))
      ?? voices.find(v => v.lang.startsWith('en') && v.name.toLowerCase().includes('neural'))
      ?? voices.find(v => v.lang.startsWith('en'))
    if (preferred) utterance.voice = preferred

    utterance.onstart = () => setSpeaking(true)
    utterance.onend = () => setSpeaking(false)
    utterance.onerror = () => setSpeaking(false)

    utteranceRef.current = utterance
    window.speechSynthesis.speak(utterance)
  }, [supported, voiceLang])

  const stop = useCallback(() => {
    window.speechSynthesis?.cancel()
    setSpeaking(false)
  }, [])

  return { speaking, supported, speak, stop }
}
