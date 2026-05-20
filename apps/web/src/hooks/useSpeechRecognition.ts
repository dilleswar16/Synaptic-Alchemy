/**
 * Browser-native Speech-to-Text hook using the Web Speech API.
 * Works in Chrome and Edge (Edge uses Azure Speech under the hood).
 */
import { useState, useRef, useCallback } from 'react'

interface SpeechRecognitionHook {
  /** Whether the mic is actively listening */
  listening: boolean
  /** Interim (unfinished) transcript while speaking */
  interim: string
  /** Whether the browser supports SpeechRecognition */
  supported: boolean
  /** Start listening */
  start: () => void
  /** Stop listening and return final transcript */
  stop: () => void
}

// Browser types — prefixed in some browsers
type SpeechRecognitionType = typeof window extends { SpeechRecognition: infer T } ? T : any

function getRecognitionClass(): SpeechRecognitionType | null {
  if (typeof window === 'undefined') return null
  return (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition ?? null
}

export function useSpeechRecognition(
  onResult: (transcript: string) => void,
  lang = 'en-US',
): SpeechRecognitionHook {
  const [listening, setListening] = useState(false)
  const [interim, setInterim] = useState('')
  const recognitionRef = useRef<any>(null)

  const supported = getRecognitionClass() !== null

  const start = useCallback(() => {
    const SpeechRecognition = getRecognitionClass()
    if (!SpeechRecognition) return

    const recognition = new SpeechRecognition()
    recognition.lang = lang
    recognition.interimResults = true
    recognition.continuous = false
    recognition.maxAlternatives = 1

    recognition.onresult = (event: any) => {
      let interimText = ''
      let finalText = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript
        if (event.results[i].isFinal) {
          finalText += transcript
        } else {
          interimText += transcript
        }
      }
      setInterim(interimText)
      if (finalText) {
        onResult(finalText)
        setInterim('')
      }
    }

    recognition.onerror = () => {
      setListening(false)
      setInterim('')
    }

    recognition.onend = () => {
      setListening(false)
      setInterim('')
    }

    recognitionRef.current = recognition
    recognition.start()
    setListening(true)
  }, [lang, onResult])

  const stop = useCallback(() => {
    recognitionRef.current?.stop()
    setListening(false)
  }, [])

  return { listening, interim, supported, start, stop }
}
