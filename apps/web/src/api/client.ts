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

export interface EvidenceBundle {
  elastic_logs: Record<string, unknown>[]
  elastic_metrics: Record<string, unknown>[]
  log_analytics_apim: Record<string, unknown>[]
  aks_context: Record<string, unknown>
  azure_activity_changes: Record<string, unknown>[]
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
  evidence: EvidenceBundle
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

// ── V3: Stats ─────────────────────────────────────────────────────────────

export interface InvestigationStats {
  total_investigations: number
  today_count: number
  confidence_distribution: { high: number; medium: number; low: number }
  approval_distribution: { pending: number; approved: number; rejected: number; executed: number }
  avg_mttr_minutes: number | null
  auto_resolved_rate: number
  recent_services: string[]
}

export function fetchInvestigationStats() {
  return apiFetch<InvestigationStats>('/investigations/stats')
}

// ── V3: Post-Mortem ───────────────────────────────────────────────────────

export interface PostMortem {
  request_id: string
  service_name: string
  environment: string
  generated_at: string
  incident_summary: string
  detection_timeline: string
  investigation_findings: string
  actions_taken: string
  prevention_recommendations: string
  approved_by: string | null
  markdown: string
}

export function generatePostMortem(id: string) {
  return apiFetch<PostMortem>(`/investigations/${id}/postmortem`, { method: 'POST' })
}

export function fetchPostMortem(id: string) {
  return apiFetch<PostMortem>(`/investigations/${id}/postmortem`)
}

// ── V3: Incident Memory ───────────────────────────────────────────────────

export interface SimilarIncident {
  request_id: string
  service_name: string
  environment: string
  completed_at: string
  rca_summary: string
  root_cause: string
  confidence: 'high' | 'medium' | 'low'
}

export function fetchSimilarIncidents(service_name: string, environment: string, n = 3) {
  const params = new URLSearchParams({ service_name, environment, n: String(n) })
  return apiFetch<SimilarIncident[]>(`/investigations/memory?${params}`)
}

// ── V3: Investigation Replay ──────────────────────────────────────────────────

export interface ReplayPayload {
  request_id: string
  trigger: {
    service_name: string
    environment: string
    trigger_source: string
    description: string
    lookback_minutes: number
    created_at: string
  }
  approval: {
    status: string | null
    approved_by: string | null
    approved_at: string | null
  }
  evidence_summary: {
    elastic_log_count: number
    elastic_metric_count: number
    log_analytics_apim_count: number
    aks_context_keys: string[]
    azure_activity_count: number
    collected_at: string
  }
  rca: {
    summary: string
    root_cause: string
    confidence: string
    contributing_factors: string[]
    evidence_references: string[]
    generated_at: string
  }
  fix_strategy: {
    summary: string
    justification: string
    action_count: number
    actions: Array<{
      title: string
      risk_level: string
      requires_approval: boolean
      estimated_impact: string
    }>
    generated_at: string
  }
  completed_at: string
}

export function fetchReplay(requestId: string) {
  return apiFetch<ReplayPayload>(`/investigations/${requestId}/replay`)
}

// ── V3: Morning Briefing ──────────────────────────────────────────────────

export interface BriefingPayload {
  generated_at: string
  period_hours: number
  total_investigations: number
  pending_approval: number
  approved: number
  executed: number
  rejected: number
  high_confidence_pending: number
  confidence_breakdown: { high: number; medium: number; low: number }
  top_services: Array<{ service: string; environment: string; count: number }>
  narrative: string
}

export function fetchBriefing(hours = 24) {
  return apiFetch<BriefingPayload>(`/investigations/briefing?hours=${hours}`)
}
