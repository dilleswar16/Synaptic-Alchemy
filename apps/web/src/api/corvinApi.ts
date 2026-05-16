/**
 * Corvin Command Center — API client.
 * All calls go to the /corvin prefix registered in the FastAPI backend.
 */

import { API_BASE } from './baseUrl'

export interface CorvinSession {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface CorvinMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  thinking?: string | null
  tool_calls?: { calls: { tool_name: string; arguments: Record<string, unknown> }[] } | null
  created_at: string
}

export interface CorvinSessionDetail extends CorvinSession {
  messages: CorvinMessage[]
}

// ── Session management ────────────────────────────────────────────────────────

export async function createSession(): Promise<CorvinSession> {
  const res = await fetch(`${API_BASE}/corvin/sessions`, { method: 'POST' })
  if (!res.ok) throw new Error(`Failed to create session: ${res.statusText}`)
  return res.json()
}

export async function listSessions(): Promise<CorvinSession[]> {
  const res = await fetch(`${API_BASE}/corvin/sessions`)
  if (!res.ok) throw new Error(`Failed to list sessions: ${res.statusText}`)
  return res.json()
}

export async function getSession(sessionId: string): Promise<CorvinSessionDetail> {
  const res = await fetch(`${API_BASE}/corvin/sessions/${sessionId}`)
  if (!res.ok) throw new Error(`Failed to load session: ${res.statusText}`)
  return res.json()
}

export async function deleteSession(sessionId: string): Promise<void> {
  await fetch(`${API_BASE}/corvin/sessions/${sessionId}`, { method: 'DELETE' })
}

// ── Streaming chat ────────────────────────────────────────────────────────────

export type AgentEventType = 'thinking' | 'tool_call' | 'tool_result' | 'text' | 'error'

export interface AgentEvent {
  type: AgentEventType
  text?: string          // for 'thinking' and 'text'
  tool_name?: string     // for 'tool_call' and 'tool_result'
  arguments?: Record<string, unknown>  // for 'tool_call'
  data?: unknown         // for 'tool_result'
  message?: string       // for 'error'
}

/**
 * Send a message and return an async iterator of parsed AgentEvents.
 * Caller should iterate and handle each event type separately.
 */
export async function* streamChat(
  sessionId: string,
  message: string
): AsyncGenerator<AgentEvent> {
  const res = await fetch(`${API_BASE}/corvin/sessions/${sessionId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
  if (!res.ok) throw new Error(`Chat request failed: ${res.statusText}`)

  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const raw = line.slice(6).trim()
      if (raw === '[DONE]') return
      try {
        yield JSON.parse(raw) as AgentEvent
      } catch {
        // incomplete chunk — ignore
      }
    }
  }
}
