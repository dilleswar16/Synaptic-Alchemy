import { API_BASE } from './baseUrl'

/**
 * Corvin API client.
 *
 * Requests use the configured FastAPI origin when VITE_API_URL is set.
 * Otherwise they fall back to same-origin /api for local dev and SWA rewrites.
 */

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const isWrite = init?.method && init.method !== 'GET' && init.method !== 'HEAD'
  const res = await fetch(`${API_BASE}${path}`, {
    headers: isWrite ? { 'Content-Type': 'application/json', ...init?.headers } : { ...init?.headers },
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
  description: string
  approval_status: string
  incident_priority: string
  completed_at: string
  created_at: string
}

export interface EvidenceBundle {
  elastic_logs: Record<string, unknown>[]
  elastic_metrics: Record<string, unknown>[]
  log_analytics_apim: Record<string, unknown>[]
  aks_context: Record<string, unknown>
  azure_activity_changes: Record<string, unknown>[]
  container_resource_metrics: Record<string, unknown>[]
  container_inventory: Record<string, unknown>[]
  node_inventory: Record<string, unknown>[]
  network_metrics: Record<string, unknown>[]
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
    incident_priority?: string
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
      action_type?: string
      target_service?: string
      target_namespace?: string
      risk_level: string
      estimated_impact: string
      requires_approval: boolean
    }>
  } | null
  completed_at: string
  ado_work_item_id: string | null
  ado_url: string | null
  wiki_url: string | null
  sharepoint_url: string | null
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

export function acknowledgeInvestigation(id: string) {
  return apiFetch<ApprovalResponse>(`/investigations/${id}/acknowledge`, { method: 'POST' })
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

export interface SingleActionResult {
  request_id: string
  action_index: number
  action_type: string
  title: string
  success: boolean
  detail: string
  logs: string[]
}

export function executeSingleAction(id: string, actionIndex: number) {
  return apiFetch<SingleActionResult>(`/investigations/${id}/execute/${actionIndex}`, { method: 'POST' })
}

// ── Streaming execution (SSE) ─────────────────────────────────────────────

export interface ExecutionStreamEvent {
  event: 'action_start' | 'action_complete' | 'pod_logs' | 'done'
  action_index?: number
  title?: string
  action_type?: string
  total?: number
  success?: boolean
  detail?: string
  logs?: string[]
  pod_logs?: Array<{ pod: string; logs: string }>
  all_succeeded?: boolean
  error?: string
}

export function streamExecuteAll(
  id: string,
  onEvent: (event: ExecutionStreamEvent) => void,
  onError?: (err: Error) => void,
): AbortController {
  const controller = new AbortController()
  const url = `${API_BASE}/investigations/${id}/execute/stream`

  fetch(url, { signal: controller.signal })
    .then(async (res) => {
      if (!res.ok) {
        const text = await res.text()
        throw new Error(`Execution stream error ${res.status}: ${text}`)
      }
      const reader = res.body?.getReader()
      if (!reader) throw new Error('No response body')
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const parsed = JSON.parse(line.slice(6)) as ExecutionStreamEvent
              onEvent(parsed)
            } catch { /* skip malformed */ }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') onError?.(err as Error)
    })

  return controller
}

export interface PodLogsResponse {
  request_id: string
  service_name: string
  pod_logs: Array<{ pod: string; logs: string }>
}

export function fetchPodLogs(id: string, tailLines = 60, sinceSeconds = 30) {
  return apiFetch<PodLogsResponse>(
    `/investigations/${id}/logs?tail_lines=${tailLines}&since_seconds=${sinceSeconds}`
  )
}

// ── V3: Stats ─────────────────────────────────────────────────────────────

export interface InvestigationStats {
  total_investigations: number
  today_count: number
  confidence_distribution: { high: number; medium: number; low: number }
  approval_distribution: { pending: number; approved: number; rejected: number; acknowledged: number; executed: number }
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
  acknowledged: number
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
  confidence_pct: number
  signal_value: number
  threshold_value: number
  estimated_breach_at: string | null
  rationale: string
  source_request_id: string | null
  status: string
  investigation_request_id: string | null
  created_at: string
  change_correlation: string | null
  related_count: number
  blast_radius_users: number
  blast_radius_requests: number
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
  target_service?: string
  target_namespace?: string
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
  cpu_mcores?: number | null
  cpu_request_mcores?: number | null
  cpu_limit_mcores?: number | null
  cpu_utilization_pct?: number | null
  memory_mib?: number | null
  memory_request_mib?: number | null
  memory_limit_mib?: number | null
  memory_utilization_pct?: number | null
  phase?: string | null
  ready_containers?: number | null
  total_containers?: number | null
  restart_count?: number | null
  unhealthy_containers?: number | null
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

export function fetchTopologyLive() {
  return apiFetch<ServiceTopology>('/investigations/topology/live')
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

// ── DORA Metrics ──────────────────────────────────────────────────────────

export interface DoraMetrics {
  period_days: number
  total_investigations: number
  high_confidence_count: number
  deployment_frequency: number
  lead_time_minutes: number
  mttr_minutes: number
  mttr_prior_minutes: number
  mttr_trend: 'improving' | 'stable' | 'degrading'
  change_failure_rate_pct: number
}

export function fetchDora(days = 30) {
  return apiFetch<DoraMetrics>(`/investigations/dora?days=${days}`)
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

// ── V3.99: Chaos & Sync ──────────────────────────────────────────────────

export interface SyncResponse {
  ticket_id: string
  url?: string
  message: string
}

export function syncAzureBoards(requestId: string) {
  return apiFetch<SyncResponse>(`/investigations/${requestId}/sync/azure-boards`, { method: 'POST' })
}

export function syncServiceNow(requestId: string) {
  return apiFetch<SyncResponse>(`/investigations/${requestId}/sync/servicenow`, { method: 'POST' })
}

// ── Application Panel ─────────────────────────────────────────────────────

export interface ApplicationService {
  id: number
  application_id: string
  service_name: string
  display_name: string
  namespace: string | null
  tier: string
  dependencies: string[]
  metadata_json: Record<string, unknown>
  k8s_app_label: string | null
}

export interface LogSource {
  id: string
  application_id: string
  source_type: 'azure_monitor' | 'elastic' | 'byoa' | 'aks'
  display_name: string
  config_json: Record<string, unknown>
  credential_type: 'db_encrypted' | 'kv_reference' | 'env_var'
  credential_ref: string | null
  is_active: boolean
  last_tested_at: string | null
  test_status: 'ok' | 'error' | null
  test_message: string | null
  created_at: string
}

export interface SloConfig {
  id: number
  application_id: string
  service_name: string
  sli_type: 'availability' | 'latency'
  target_pct: number
  time_window_days: number
  latency_threshold_ms: number | null
  enabled: boolean
  created_at: string
}

export interface Application {
  id: string
  name: string
  description: string
  team_name: string
  environment_default: string
  topology_json: Record<string, unknown>
  created_at: string
  updated_at: string
  services?: ApplicationService[]
  log_sources?: LogSource[]
  slo_configs?: SloConfig[]
}

export function listApplications() {
  return apiFetch<Application[]>('/applications/')
}

export function getApplication(id: string) {
  return apiFetch<Application>(`/applications/${id}`)
}

export function createApplication(payload: Partial<Application>) {
  return apiFetch<Application>('/applications/', { method: 'POST', body: JSON.stringify(payload) })
}

export function updateApplication(id: string, payload: Partial<Application>) {
  return apiFetch<Application>(`/applications/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
}

export function deleteApplication(id: string) {
  return apiFetch<void>(`/applications/${id}`, { method: 'DELETE' })
}

export function addService(appId: string, payload: Partial<ApplicationService>) {
  return apiFetch<ApplicationService>(`/applications/${appId}/services`, { method: 'POST', body: JSON.stringify(payload) })
}

export function updateService(appId: string, svcId: number, payload: Partial<ApplicationService>) {
  return apiFetch<ApplicationService>(`/applications/${appId}/services/${svcId}`, { method: 'PUT', body: JSON.stringify(payload) })
}

export function deleteService(appId: string, svcId: number) {
  return apiFetch<void>(`/applications/${appId}/services/${svcId}`, { method: 'DELETE' })
}

export function listConnectors(appId: string) {
  return apiFetch<LogSource[]>(`/applications/${appId}/connectors`)
}

export function addConnector(appId: string, payload: Partial<LogSource> & { credential_value?: string }) {
  return apiFetch<LogSource>(`/applications/${appId}/connectors`, { method: 'POST', body: JSON.stringify(payload) })
}

export function deleteConnector(appId: string, srcId: string) {
  return apiFetch<void>(`/applications/${appId}/connectors/${srcId}`, { method: 'DELETE' })
}

export interface ConnectorTestResult {
  ok: boolean
  message: string
  latency_ms: number | null
}

export function testConnector(appId: string, srcId: string) {
  return apiFetch<ConnectorTestResult>(`/applications/${appId}/connectors/${srcId}/test`, { method: 'POST' })
}

export function addSloConfig(appId: string, payload: Partial<SloConfig>) {
  return apiFetch<SloConfig>(`/applications/${appId}/slo-configs`, { method: 'POST', body: JSON.stringify(payload) })
}

export function updateSloConfig(appId: string, cfgId: number, payload: Partial<SloConfig>) {
  return apiFetch<SloConfig>(`/applications/${appId}/slo-configs/${cfgId}`, { method: 'PUT', body: JSON.stringify(payload) })
}

export function deleteSloConfig(appId: string, cfgId: number) {
  return apiFetch<void>(`/applications/${appId}/slo-configs/${cfgId}`, { method: 'DELETE' })
}

export function migrateFromYaml() {
  return apiFetch<Record<string, unknown>>('/applications/migrate-from-yaml', { method: 'POST' })
}

// ── SLO Monitoring ────────────────────────────────────────────────────────────

export interface SloSnapshot {
  id: number
  slo_config_id: number
  application_id: string
  service_name: string
  sli_type: 'availability' | 'latency'
  target_pct: number
  measured_pct: number | null
  error_budget_pct: number | null
  burn_rate: number | null
  is_compliant: boolean | null
  data_source: 'simulated' | 'connector'
  sampled_at: string
}

export interface SloStatusEntry {
  id: number
  application_id: string
  service_name: string
  sli_type: 'availability' | 'latency'
  target_pct: number
  time_window_days: number
  latency_threshold_ms: number | null
  enabled: boolean
  latest_snapshot: SloSnapshot | null
}

export interface SloSummary {
  total: number
  compliant: number
  at_risk: number
  breached: number
  no_data: number
}

export function listSloStatus(appId?: string) {
  const qs = appId ? `?app_id=${encodeURIComponent(appId)}` : ''
  return apiFetch<SloStatusEntry[]>(`/slo/${qs}`)
}

export function getSloSummary() {
  return apiFetch<SloSummary>('/slo/summary')
}

export function getSloHistory(sloId: number, limit = 30) {
  return apiFetch<{ config: SloStatusEntry; history: SloSnapshot[] }>(
    `/slo/${sloId}/history?limit=${limit}`
  )
}

export function refreshSloSnapshots(appId?: string) {
  const qs = appId ? `?app_id=${encodeURIComponent(appId)}` : ''
  return apiFetch<{ snapshots_written: number }>(`/slo/refresh${qs}`, { method: 'POST' })
}

// ── Validations ───────────────────────────────────────────────────────────────

export interface ValidationRun {
  id: string
  definition_id: string
  status: 'running' | 'pass' | 'fail' | 'error'
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  result_json: { steps: ValidationStepResult[]; passed: boolean }
  triggered_by: string | null
}

export interface ValidationStepResult {
  ok: boolean
  step_index: number
  step_name: string
  status_code?: number
  expected_status?: number
  duration_ms?: number
  error?: string | null
  note?: string
}

export interface ValidationDefinition {
  id: string
  application_id: string | null
  name: string
  description: string | null
  validation_type: 'health_check' | 'endpoint' | 'synthetic' | 'user_journey' | 'slo_gate' | 'chaos'
  config_json: Record<string, unknown>
  enabled: boolean
  last_run_at: string | null
  last_run_status: 'pass' | 'fail' | 'error' | 'running' | null
  created_at: string
  last_run: ValidationRun | null
}

export function listValidations(appId?: string) {
  const qs = appId ? `?app_id=${encodeURIComponent(appId)}` : ''
  return apiFetch<ValidationDefinition[]>(`/validations/${qs}`)
}

export function getValidation(id: string) {
  return apiFetch<ValidationDefinition>(`/validations/${id}`)
}

export function createValidation(payload: Partial<ValidationDefinition> & { name: string }) {
  return apiFetch<ValidationDefinition>('/validations/', { method: 'POST', body: JSON.stringify(payload) })
}

export function updateValidation(id: string, payload: Partial<ValidationDefinition>) {
  return apiFetch<ValidationDefinition>(`/validations/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })
}

export function deleteValidation(id: string) {
  return apiFetch<void>(`/validations/${id}`, { method: 'DELETE' })
}

export function triggerValidationRun(id: string) {
  return apiFetch<ValidationRun>(`/validations/${id}/run`, { method: 'POST' })
}

export function getValidationHistory(id: string, limit = 20) {
  return apiFetch<ValidationRun[]>(`/validations/${id}/history?limit=${limit}`)
}

