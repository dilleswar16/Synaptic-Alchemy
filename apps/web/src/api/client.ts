import { API_BASE } from './baseUrl'

/**
 * Corvin API client.
 *
 * Requests use the configured FastAPI origin when VITE_API_URL is set.
 * Otherwise they fall back to same-origin /api for local dev and SWA rewrites.
 */

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    throw new Error(`Corvin API error ${res.status}: ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export interface InvestigationSummary {
  request_id: string
  service_name: string
  environment: string
  trigger_source: string
  completed_at: string
  created_at: string
}

export interface InvestigationResult {
  request_id: string
  request: {
    id: string
    service_name: string
    environment: string
    trigger_source: string
    description: string
    created_at: string
    approval_status: string
  }
  rca: {
    summary: string
    root_cause: string
    confidence: string
    contributing_factors: string[]
    evidence_references: string[]
  } | null
  fix_strategy: {
    summary: string
    justification: string
    actions: Array<{
      title: string
      description: string
      risk_level: string
      estimated_impact: string
      requires_approval: boolean
    }>
  } | null
  completed_at: string
}

export function fetchInvestigations() {
  return apiFetch<InvestigationSummary[]>('/investigations/')
}

export function fetchInvestigation(id: string) {
  return apiFetch<InvestigationResult>(`/investigations/${id}`)
}

export function startInvestigation(payload: {
  service_name: string
  environment: string
  description?: string
}) {
  return apiFetch<{ request_id: string; status: string; message: string }>('/investigations/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export interface ApprovalResponse {
  request_id: string
  approval_status: string
  message: string
}

export function approveInvestigation(id: string) {
  return apiFetch<ApprovalResponse>(`/investigations/${id}/approve`, { method: 'POST' })
}

export function rejectInvestigation(id: string) {
  return apiFetch<ApprovalResponse>(`/investigations/${id}/reject`, { method: 'POST' })
}

export interface ExecutionOutcome {
  action_type: string
  title: string
  success: boolean
  detail: string
}

export interface ExecutionResponse {
  request_id: string
  approval_status: string
  all_succeeded: boolean
  outcomes: ExecutionOutcome[]
  message: string
}

export function executeInvestigation(id: string) {
  return apiFetch<ExecutionResponse>(`/investigations/${id}/execute`, { method: 'POST' })
}
