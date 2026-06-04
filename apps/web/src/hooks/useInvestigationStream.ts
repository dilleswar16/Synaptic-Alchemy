/**
 * useInvestigationStream — React hook for the Corvin SSE streaming endpoint.
 *
 * Opens an EventSource to the configured investigations stream endpoint and
 * emits stage events as they arrive from the FastAPI backend.
 *
 * Usage
 * -----
 *   const { stages, isStreaming, isComplete, error, start, reset } =
 *     useInvestigationStream()
 *
 *   // Kick off a stream:
 *   start({ service_name: 'order-service', environment: 'production' })
 *
 * Stage event shape (matches backend InvestigationStreamer output):
 *   { stage: string, status: 'started' | 'complete' | 'error', message: string, ...extra }
 */

import { useCallback, useRef, useState } from 'react'

import { API_BASE } from '../api/baseUrl'

export type StageStatus = 'started' | 'fetching' | 'token' | 'complete' | 'error'

export interface StageEvent {
  stage: string
  status: StageStatus
  message: string
  /** Extra fields emitted by the backend (summary, request_id, etc.) */
  [key: string]: unknown
}

export interface StreamParams {
  service_name: string
  environment?: string
  description?: string
}

export interface UseInvestigationStreamResult {
  /** All stage events received so far, in order (excludes token and fetching events). */
  stages: StageEvent[]
  /** Accumulated raw LLM token text per stage name, built as tokens arrive. */
  streamText: Record<string, string>
  /** Live evidence-collection sub-events: one per source, running then done. */
  fetchingEvents: StageEvent[]
  /** Live delivery sub-events: one per delivery target (db, ado, email, wiki). */
  deliveryEvents: StageEvent[]
  /** True while the EventSource connection is open. */
  isStreaming: boolean
  /** True once a 'complete' or 'error' stage event is received. */
  isComplete: boolean
  /** Non-null if the stream ended with an error stage event. */
  error: string | null
  /** request_id from the 'complete' event — available to navigate to the result. */
  requestId: string | null
  /** Azure Boards work item ID created after investigation, if any. */
  adoWorkItemId: string | null
  /** Full URL to the Azure Boards work item, if created. */
  adoUrl: string | null
  /** Whether the RCA email was sent automatically. */
  emailSent: boolean
  /** Open the stream with the given params. Resets state first. */
  start: (params: StreamParams) => void
  /** Close the stream and clear all state. */
  reset: () => void
}

export function useInvestigationStream(): UseInvestigationStreamResult {
  const [stages, setStages] = useState<StageEvent[]>([])
  const [streamText, setStreamText] = useState<Record<string, string>>({})
  const [fetchingEvents, setFetchingEvents] = useState<StageEvent[]>([])
  const [deliveryEvents, setDeliveryEvents] = useState<StageEvent[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [isComplete, setIsComplete] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [requestId, setRequestId] = useState<string | null>(null)
  const [adoWorkItemId, setAdoWorkItemId] = useState<string | null>(null)
  const [adoUrl, setAdoUrl] = useState<string | null>(null)
  const [emailSent, setEmailSent] = useState(false)

  const esRef = useRef<EventSource | null>(null)

  const reset = useCallback(() => {
    if (esRef.current) {
      esRef.current.close()
      esRef.current = null
    }
    setStages([])
    setStreamText({})
    setFetchingEvents([])
    setDeliveryEvents([])
    setIsStreaming(false)
    setIsComplete(false)
    setError(null)
    setRequestId(null)
    setAdoWorkItemId(null)
    setAdoUrl(null)
    setEmailSent(false)
  }, [])

  const start = useCallback(
    ({ service_name, environment, description = '' }: StreamParams) => {
      // Close any existing stream before starting a new one.
      reset()

      const params = new URLSearchParams({
        service_name,
        environment,
        ...(description ? { description } : {}),
      })

      const url = `${API_BASE}/investigations/stream?${params.toString()}`
      const es = new EventSource(url)
      esRef.current = es
      setIsStreaming(true)

      es.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data) as StageEvent

          // Token events are accumulated separately — not stored in stages array
          if (data.status === 'token') {
            setStreamText((prev) => ({
              ...prev,
              [data.stage]: (prev[data.stage] ?? '') + data.message,
            }))
            return
          }

          // Evidence and delivery sub-events: accumulate in separate arrays
          // so the UI can show live per-source progress rows (running → done)
          if (data.status === 'fetching') {
            const setter = data.stage === 'delivery' ? setDeliveryEvents : setFetchingEvents
            setter((prev) => {
              // Replace the existing entry for this source (running → done)
              const idx = prev.findIndex((e) => e.source === data.source)
              if (idx >= 0) {
                const next = [...prev]
                next[idx] = data
                return next
              }
              return [...prev, data]
            })
            return
          }

          setStages((prev) => [...prev, data])

          if (data.stage === 'complete') {
            setRequestId((data.request_id as string) ?? null)
            setAdoWorkItemId((data.ado_work_item_id as string | null) ?? null)
            setAdoUrl((data.ado_url as string | null) ?? null)
            setEmailSent((data.email_sent as boolean) ?? false)
            setIsComplete(true)
            setIsStreaming(false)
            es.close()
          } else if (data.stage === 'error') {
            setError(data.message)
            setIsComplete(true)
            setIsStreaming(false)
            es.close()
          }
        } catch {
          // Malformed JSON — log and continue
          console.warn('useInvestigationStream: malformed SSE event', event.data)
        }
      }

      es.onerror = () => {
        setError('Lost connection to the investigation stream.')
        setIsStreaming(false)
        setIsComplete(true)
        es.close()
      }
    },
    [reset],
  )

  return { stages, streamText, fetchingEvents, deliveryEvents, isStreaming, isComplete, error, requestId, adoWorkItemId, adoUrl, emailSent, start, reset }
}
