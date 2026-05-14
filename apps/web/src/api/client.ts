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
    confidence_reasoning?: string
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

export async function downloadRcaPdf(id: string) {
  const res = await fetch(`${API_BASE}/investigations/${id}/rca.pdf`)
  if (!res.ok) {
    throw new Error(`Corvin API error ${res.status}: ${res.statusText}`)
  }

  const blob = await res.blob()
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `corvin-rca-${id}.pdf`
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

export function emailRcaPdf(id: string, recipients?: string[]) {
  return apiFetch<{ request_id: string; sent: boolean; message: string }>(`/investigations/${id}/rca/email`, {
    method: 'POST',
    body: JSON.stringify({ recipients: recipients ?? null }),
  })
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

// ── V3.5: Corvin Score ────────────────────────────────────────────────────

export interface ServiceScore {
  score: number                         // 0–100
  label: 'Healthy' | 'Degraded' | 'Critical' | 'No Data'
  color: 'green' | 'amber' | 'red'
  total: number                         // all-time incidents for this service
  high_conf: number                     // high-confidence RCAs count
  avg_mttr_minutes: number | null
  days_since_last: number | null
  last_incident_at: string | null
}

export function fetchServiceScore(service_name: string, environment: string) {
  const params = new URLSearchParams({ service_name, environment })
  return apiFetch<ServiceScore>(`/investigations/score?${params}`)
}

// ── V3.5: Blast Radius ────────────────────────────────────────────────────

export interface BlastRadiusEstimate {
  service_name: string
  environment: string
  affected_services: string[]
  downstream_api_count: number
  estimated_users: number
  revenue_risk_per_min: number
  currency: string
  replica_count: number
  rationale: string
}

export function fetchBlastRadius(requestId: string) {
  return apiFetch<BlastRadiusEstimate>(`/investigations/${requestId}/blast-radius`)
    .catch(() => null)   // non-fatal — returns null when evidence is absent
}

// ── V3.5: Alert Simulator ─────────────────────────────────────────────────

export interface SimulateAlertPayload {
  service_name: string
  environment: string
  scenario: string
  description?: string
}

export interface SimulateAlertResponse {
  request_id: string
  status: string
  scenario: string
  service_name: string
  environment: string
}

export function simulateAlert(payload: SimulateAlertPayload) {
  return apiFetch<SimulateAlertResponse>('/triggers/simulate', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

// ── V3.7: Intelligence Layer ──────────────────────────────────────────────

export interface PredictiveAlert {
  id: string
  service_name: string
  environment: string
  alert_type: string
  title: string
  summary: string
  severity: 'critical' | 'high' | 'medium' | 'low'
  confidence: 'high' | 'medium' | 'low'
  signal_value: number
  threshold_value: number
  estimated_breach_at: string | null
  rationale: string
  source_request_id: string | null
  status: string
  investigation_request_id: string | null
  created_at: string
}

export function fetchPredictiveAlerts(refresh = true) {
  return apiFetch<PredictiveAlert[]>(`/investigations/predictive-alerts?refresh=${refresh}`)
}

export function investigatePredictiveAlert(id: string) {
  return apiFetch<{ request_id: string; status: string; message: string }>(`/investigations/predictive-alerts/${id}/investigate`, {
    method: 'POST',
  })
}

export interface SlaCountdown {
  service_name: string
  environment: string
  sla_target_percent: number
  monthly_budget_seconds: number
  seconds_already_down_this_month: number
  current_error_rate: number
  remaining_budget_seconds: number
  estimated_breach_in_seconds: number | null
  severity: 'green' | 'amber' | 'red'
  breached: boolean
}

export function fetchSlaCountdown(requestId: string) {
  return apiFetch<SlaCountdown>(`/investigations/${requestId}/sla`).catch(() => null)
}

export interface RemediationPreviewItem {
  title: string
  action_type: string
  risk_level: string
  requires_approval: boolean
  current_state: string
  proposed_command: string
  predicted_after_state: string
  operator_notes: string[]
}

export interface RemediationPreview {
  request_id: string
  service_name: string
  environment: string
  current_replica_count: number
  cpu_throttle_events_per_min: number
  restart_count: number
  items: RemediationPreviewItem[]
}

export function fetchFixPreview(requestId: string) {
  return apiFetch<RemediationPreview>(`/investigations/${requestId}/fix-preview`)
}

export interface TopologyNode {
  id: string
  label: string
  kind: string
  status: string
}

export interface TopologyEdge {
  source: string
  target: string
  label?: string | null
}

export interface ServiceTopology {
  nodes: TopologyNode[]
  edges: TopologyEdge[]
}

export function fetchTopology() {
  return apiFetch<ServiceTopology>('/investigations/topology')
}

// ── V3.9: ROI Dashboard ───────────────────────────────────────────────────

export interface RoiStats {
  period_months: number
  total_incidents: number
  baseline_mttr_minutes: number
  corvin_mttr_minutes: number
  hours_saved: number
  cost_saved: number
  currency: string
  incidents_per_day: number
  mttr_reduction_pct: number
}

export function fetchRoi() {
  return apiFetch<RoiStats>('/investigations/roi')
}

// ── V3.9: Runbook Update ──────────────────────────────────────────────────

export interface RunbookUpdateResult {
  path: string
  service_name: string
  content: string
  message: string
}

export function updateRunbook(requestId: string) {
  return apiFetch<RunbookUpdateResult>(`/investigations/${requestId}/update-runbook`, {
    method: 'POST',
  })
}

// ── V3.9: Voice Briefing ──────────────────────────────────────────────────

export async function fetchBriefingAudio(hours = 24): Promise<Blob> {
  const res = await fetch(`${API_BASE}/investigations/briefing/audio?hours=${hours}`)
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(detail.detail ?? `TTS error ${res.status}`)
  }
  return res.blob()
}

// ── V3.9: War Room ────────────────────────────────────────────────────────

export interface WarRoomResult {
  channel_name: string
  channel_id: string
  web_url: string
  investigation_id: string
  message: string
}

export function createWarRoom(payload: {
  investigation_id: string
  service_name: string
  environment: string
  severity: string
}) {
  return apiFetch<WarRoomResult>('/teams/war-room', { method: 'POST', body: JSON.stringify(payload) })
}

