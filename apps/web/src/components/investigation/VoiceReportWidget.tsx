import { useState, useRef } from 'react'
import { submitVoiceReport, type VoiceIncidentReport } from '../../api/client'

type RecordingState = 'idle' | 'recording' | 'processing'

export function VoiceReportWidget() {
  const [state, setState] = useState<RecordingState>('idle')
  const [report, setReport] = useState<VoiceIncidentReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const startRecording = async () => {
    setError(null)
    setReport(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
      chunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        setState('processing')
        try {
          const result = await submitVoiceReport(blob)
          setReport(result)
        } catch (err: unknown) {
          setError(err instanceof Error ? err.message : 'Voice report failed')
        } finally {
          setState('idle')
        }
      }

      recorder.start()
      mediaRecorderRef.current = recorder
      setState('recording')
    } catch {
      setError('Microphone access denied')
    }
  }

  const stopRecording = () => {
    mediaRecorderRef.current?.stop()
  }

  return (
    <section style={{ marginTop: '1.5rem' }}>
      <h3 style={{ margin: '0 0 0.75rem', fontSize: '1rem', fontWeight: 600 }}>Voice Incident Report</h3>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        {state === 'idle' && (
          <button
            onClick={startRecording}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: '20px',
              border: 'none',
              background: '#ef4444',
              color: '#fff',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
            }}
          >
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#fff' }} />
            Record
          </button>
        )}

        {state === 'recording' && (
          <button
            onClick={stopRecording}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: '20px',
              border: '2px solid #ef4444',
              background: '#fff',
              color: '#ef4444',
              cursor: 'pointer',
              animation: 'pulse 1.5s infinite',
            }}
          >
            ■ Stop
          </button>
        )}

        {state === 'processing' && (
          <span style={{ fontSize: '0.8rem', color: '#6366f1' }}>Transcribing & extracting…</span>
        )}
      </div>

      {error && <p style={{ color: '#dc2626', fontSize: '0.8rem', marginTop: '0.5rem' }}>{error}</p>}

      {report && (
        <div style={{
          marginTop: '1rem',
          background: '#f8fafc',
          borderRadius: '8px',
          padding: '1rem',
          border: '1px solid #e2e8f0',
        }}>
          <div style={{ marginBottom: '0.5rem' }}>
            <strong style={{ fontSize: '0.75rem', color: '#64748b' }}>Transcription</strong>
            <span style={{
              marginLeft: '0.5rem',
              fontSize: '0.65rem',
              color: '#10b981',
            }}>
              {(report.transcription.confidence * 100).toFixed(0)}% confidence
            </span>
          </div>
          <p style={{ fontSize: '0.85rem', color: '#1e293b', margin: '0 0 0.75rem', fontStyle: 'italic' }}>
            "{report.transcription.text}"
          </p>

          {report.extracted_request && (
            <div>
              <strong style={{ fontSize: '0.75rem', color: '#64748b' }}>Extracted Incident Fields</strong>
              <pre style={{
                fontSize: '0.75rem',
                background: '#f1f5f9',
                padding: '0.5rem',
                borderRadius: '4px',
                overflow: 'auto',
                marginTop: '0.25rem',
              }}>
                {JSON.stringify(report.extracted_request, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
