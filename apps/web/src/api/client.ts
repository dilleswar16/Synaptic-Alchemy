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
    let detail = res.statusText
    try {
      const payload = await res.json() as { detail?: string; message?: string }
      detail = payload.detail || payload.message || detail
    } catch {
      // Non-JSON error payloads keep status text fallback.
    }
    throw new Error(`Corvin API error ${res.status}: ${detail}`)
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
  namespace?: string | null
  cluster_name?: string | null
}

export interface TopologyEdge {
  source: string
  target: string
  label?: string | null
}

export interface ServiceTopology {
  nodes: TopologyNode[]
  edges: TopologyEdge[]
  metadata?: {
    available_clusters?: string[]
    available_namespaces?: string[]
    cluster_namespaces?: Record<string, string[]>
    namespace_source?: string
    selected_clusters?: string[]
    selected_namespaces?: string[]
    namespace_status?: Record<string, {
      high: number
      recovering: number
      hot: number
      services: number
      status: string
    }>
    metrics_source_ok?: boolean
    pod_source_ok?: boolean
    filtered_service_count?: number
    catalog_service_count?: number
    runtime_unmapped_pods_only?: boolean
  }
}

export function fetchTopology(applicationId?: string) {
  const query = applicationId ? `?application_id=${encodeURIComponent(applicationId)}` : ''
  return apiFetch<ServiceTopology>(`/investigations/topology${query}`)
}

export function fetchTopologyLive(params?: {
  applicationId?: string
  clusters?: string[]
  namespaces?: string[]
}) {
  const qp = new URLSearchParams()
  if (params?.applicationId) qp.set('application_id', params.applicationId)
  if (params?.clusters?.length) qp.set('clusters', params.clusters.join(','))
  if (params?.namespaces?.length) qp.set('namespaces', params.namespaces.join(','))
  const query = qp.toString() ? `?${qp.toString()}` : ''
  return apiFetch<ServiceTopology>(`/investigations/topology/live${query}`)
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

export function updateInvestigationRunbook(requestId: string) {
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

// ── V5.0: Agentic AI Features ─────────────────────────────────────────────

export interface CausalChainNode {
  id: string
  label: string
  category: 'trigger' | 'failure' | 'cascade' | 'impact'
}

export interface CausalChainEdge {
  from_id: string
  to_id: string
  label?: string
}

export interface CausalChain {
  nodes: CausalChainNode[]
  edges: CausalChainEdge[]
  summary?: string
}

export function fetchCausalChain(requestId: string) {
  return apiFetch<CausalChain>(`/investigations/${requestId}/causal-chain`)
}

export interface CommsDraft {
  audience: 'executive' | 'internal' | 'public'
  draft: string
  service_name: string
  environment: string
  generated_from: string
  fallback?: boolean
}

export function fetchCommsDraft(requestId: string, audience: 'executive' | 'internal' | 'public' = 'internal') {
  return apiFetch<CommsDraft>(`/investigations/${requestId}/comms-draft`, {
    method: 'POST',
    body: JSON.stringify({ audience }),
  })
}

export function fetchAllCommsDrafts(requestId: string) {
  return apiFetch<CommsDraft[]>(`/investigations/${requestId}/comms-draft/all`)
}

export interface NLToKQLResult {
  query: string | null
  explanation: string
  safe: boolean
  original_question: string
}

export function translateNLToKQL(question: string, timeRange?: string) {
  return apiFetch<NLToKQLResult>('/investigations/kql/translate', {
    method: 'POST',
    body: JSON.stringify({ question, time_range: timeRange ?? null }),
  })
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
  git_provider: string | null
  git_repo_url: string | null
  git_branch: string | null
  has_git_token: boolean
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

export interface NotificationContact {
  id: number
  application_id: string
  contact_name: string
  method: 'email' | 'phone' | 'teams'
  value: string
  priority_filter: 'all' | 'p1_only' | 'p1_p2'
  is_active: boolean
  created_at: string
}

export interface ConnectorVariable {
  key: string
  default_value: string
}

export interface ConnectorAuth {
  type: 'none' | 'bearer' | 'api_key' | 'basic' | 'oauth2'
  bearer_token?: string
  bearer_token_ref?: string
  api_key?: string
  api_key_ref?: string
  api_key_header?: string
  username?: string
  password?: string
  password_ref?: string
  token_url?: string
  client_id?: string
  client_secret?: string
  client_secret_ref?: string
  scopes?: string
}

export interface ConnectorConfig {
  endpoint?: string
  endpoint_fields?: Record<string, string>
  auth?: ConnectorAuth
  variables?: ConnectorVariable[]
  payload_template?: string
  // legacy field from before structured config
  webhook_url?: string
}

export interface OutboundConnector {
  id: string
  application_id: string
  connector_type:
    | 'teams_webhook'
    | 'servicenow'
    | 'email'
    | 'pagerduty'
    | 'generic_http'
    | 'azure_devops_boards'
    | 'azure_devops_wiki'
    | 'sharepoint'
  display_name: string
  config_json: ConnectorConfig
  is_active: boolean
  last_tested_at: string | null
  test_status: string | null
  test_message: string | null
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
  notification_contacts?: NotificationContact[]
  outbound_connectors?: OutboundConnector[]
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

export function updateConnector(appId: string, srcId: string, payload: Partial<LogSource> & { credential_value?: string }) {
  return apiFetch<LogSource>(`/applications/${appId}/connectors/${srcId}`, { method: 'PUT', body: JSON.stringify(payload) })
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

// ── V5.1: F9-F12 Agentic AI Features ─────────────────────────────────────────

// ── F9: Multi-Agent Investigation ──

export interface MultiAgentTurn {
  turn: number
  agent: string
  elapsed_ms: number
  status: string
  error?: string
}

export interface MultiAgentTrace {
  request_id: string
  turns: MultiAgentTurn[]
  started_at: string
  completed_at: string | null
  terminal_signal: string | null
  total_elapsed_ms: number
  turn_count: number
}

export interface MultiAgentResult {
  request_id: string
  status: string
  mode: string
  trace: MultiAgentTrace
  confidence: string
  root_cause: string
}

export function startMultiAgentInvestigation(params: {
  service_name: string
  environment?: string
  description: string
  priority?: string
}) {
  return apiFetch<MultiAgentResult>('/investigations/multi-agent', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

export function fetchMultiAgentTrace(requestId: string) {
  return apiFetch<MultiAgentTrace>(`/investigations/${requestId}/multi-agent/trace`)
}

// ── F10: Chaos Experiment Generator ──

export interface ChaosExperiment {
  id: string
  name: string
  experiment_type: 'pod-kill' | 'network-delay' | 'resource-exhaust' | 'dependency-failure' | 'dns-failure'
  target_service: string
  target_namespace: string
  description: string
  hypothesis: string
  steady_state: string
  blast_radius: 'limited' | 'moderate' | 'wide'
  duration_seconds: number
  parameters: Record<string, unknown>
  rollback_steps: string[]
  prerequisites: string[]
  generated_at: string
}

export interface ChaosExperimentPlan {
  request_id: string
  service_name: string
  experiments: ChaosExperiment[]
  rationale: string
  risk_assessment: string
  generated_at: string
  experiment_count: number
}

export function fetchChaosExperiments(requestId: string) {
  return apiFetch<ChaosExperimentPlan>(`/investigations/${requestId}/chaos-experiments`)
}

// ── F11: IDE Integration Context ──

export interface IDEContext {
  service_name: string
  active_investigations: Array<{
    id: string
    status: string
    alert_summary: string
    started_at: string
    confidence: string
  }>
  recent_incidents: Array<{
    id: string
    root_cause: string
    completed_at: string
    confidence: string
  }>
  deployment_safety: DeploySafetySignal
  knowledge_snippets: Array<{ title: string; content: string }>
  generated_at: string
}

export interface DeploySafetySignal {
  safe_to_deploy: boolean
  service_name: string
  active_incident_count: number
  recent_failure_count: number
  warnings: string[]
  blockers: string[]
}

export interface IDEFixSuggestion {
  file_path: string
  service_name: string
  suggestion: string
  rationale: string
  related_investigation_id: string | null
  confidence: string
  code_snippet: string | null
}

export function fetchIDEContext(serviceName: string) {
  return apiFetch<IDEContext>(`/investigations/ide/context/${serviceName}`)
}

export function fetchIDEFixSuggestion(params: {
  service_name: string
  file_path: string
  error_context: string
}) {
  return apiFetch<IDEFixSuggestion>('/investigations/ide/fix-suggestion', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

export function fetchDeploySafety(serviceName: string) {
  return apiFetch<DeploySafetySignal>(`/investigations/ide/deploy-safety/${serviceName}`)
}

// ── F12: Voice Incident Reporter ──

export interface TranscriptionResult {
  text: string
  confidence: number
  duration_seconds: number
  language: string
}

export interface VoiceIncidentReport {
  transcription: TranscriptionResult
  extracted_request: Record<string, unknown> | null
  extraction_confidence: string
  raw_extraction: Record<string, unknown>
}

export async function submitVoiceReport(audioBlob: Blob): Promise<VoiceIncidentReport> {
  const buffer = await audioBlob.arrayBuffer()
  const res = await fetch(`${API_BASE}/investigations/voice/transcribe-and-report`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: buffer,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(detail.detail ?? `Voice report error ${res.status}`)
  }
  return res.json()
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

// ── Notification Contacts ─────────────────────────────────────────────────────

export function addNotificationContact(appId: string, payload: Partial<NotificationContact>) {
  return apiFetch<NotificationContact>(`/applications/${appId}/notification-contacts`, { method: 'POST', body: JSON.stringify(payload) })
}

export function updateNotificationContact(appId: string, contactId: number, payload: Partial<NotificationContact>) {
  return apiFetch<NotificationContact>(`/applications/${appId}/notification-contacts/${contactId}`, { method: 'PUT', body: JSON.stringify(payload) })
}

export function deleteNotificationContact(appId: string, contactId: number) {
  return apiFetch<void>(`/applications/${appId}/notification-contacts/${contactId}`, { method: 'DELETE' })
}

// ── Outbound Connectors ───────────────────────────────────────────────────────

export function addOutboundConnector(appId: string, payload: Partial<OutboundConnector>) {
  return apiFetch<OutboundConnector>(`/applications/${appId}/outbound-connectors`, { method: 'POST', body: JSON.stringify(payload) })
}

export function updateOutboundConnector(appId: string, connId: string, payload: Partial<OutboundConnector>) {
  return apiFetch<OutboundConnector>(`/applications/${appId}/outbound-connectors/${connId}`, { method: 'PUT', body: JSON.stringify(payload) })
}

export function testOutboundConnector(appId: string, connId: string) {
  return apiFetch<ConnectorTestResult>(`/applications/${appId}/outbound-connectors/${connId}/test`, { method: 'POST' })
}

export function deleteOutboundConnector(appId: string, connId: string) {
  return apiFetch<void>(`/applications/${appId}/outbound-connectors/${connId}`, { method: 'DELETE' })
}

export function bootstrapOutboundConnectors(appId: string) {
  return apiFetch<{ status: string; application_id: string; inserted: number; updated: number }>(
    `/applications/${appId}/outbound-connectors/bootstrap`,
    { method: 'POST' },
  )
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
  breach_reason: string | null
  recommended_action: string | null
  breach_severity: 'critical' | 'warning' | 'minor' | null
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
  skipped?: boolean
  assertions?: { type: string; passed: boolean; detail: string }[]
  extracted_vars?: Record<string, string>
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

// Journey Builder types
export interface JourneyAuthConfig {
  type: 'none' | 'bearer' | 'api_key' | 'oauth2_client_credentials' | 'custom_header'
  token?: string
  header_name?: string
  key?: string
  header_value?: string
  token_url?: string
  client_id?: string
  client_secret?: string
  scope?: string
}

export interface JourneyStepAssertion {
  type: 'body_contains' | 'json_path_equals' | 'max_latency_ms' | 'json_path_exists'
  value?: string
  path?: string
}

export interface JourneyStepExtraction {
  variable: string
  source: 'json_path' | 'header'
  path?: string
  header?: string
}

export interface JourneyStep {
  name: string
  type: 'http' | 'wait'
  method?: string
  url?: string
  headers?: Record<string, string>
  body?: unknown
  expected_status?: number
  timeout_s?: number
  assertions?: JourneyStepAssertion[]
  extract?: JourneyStepExtraction[]
  duration_ms?: number // for wait type
}

export interface JourneyConfig {
  base_url: string
  auth?: JourneyAuthConfig
  abort_on_failure?: boolean
  steps: JourneyStep[]
}

export interface DryRunResult {
  passed: boolean
  duration_ms: number
  steps: ValidationStepResult[]
}

export interface PlaywrightResult {
  script: string
  filename: string
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

export function dryRunValidation(config: JourneyConfig, validationType = 'user_journey') {
  return apiFetch<DryRunResult>('/validations/dry-run', {
    method: 'POST',
    body: JSON.stringify({ config_json: config, validation_type: validationType }),
  })
}

export function generatePlaywrightScript(config: JourneyConfig, name: string) {
  return apiFetch<PlaywrightResult>('/validations/generate-playwright', {
    method: 'POST',
    body: JSON.stringify({ config_json: config, name }),
  })
}

// ── Alert Correlation ─────────────────────────────────────────────────────────

export interface CorrelatedAlert {
  alert_id: string
  service_name: string
  environment: string
  title: string
  severity: string
  created_at: string
  similarity_score: number
}

export interface CorrelationGroup {
  group_id: string
  primary_alert_id: string
  service_name: string
  environment: string
  correlation_reason: string
  unified_summary: string
  severity: string
  alerts: CorrelatedAlert[]
  alert_count: number
  suppression_recommended: boolean
  approval_status: string
  approved_by: string | null
  created_at: string
}

export interface CorrelatedAlertsResponse {
  total_alerts: number
  correlation_groups: CorrelationGroup[]
  ungrouped_count: number
  suppression_candidates: number
}

export function fetchCorrelatedAlerts(environment?: string) {
  const params = environment ? `?environment=${encodeURIComponent(environment)}` : ''
  return apiFetch<CorrelatedAlertsResponse>(`/ai/alerts/correlated${params}`)
}

export function approveCorrelationAction(groupId: string, action: 'approve' | 'reject', approvedBy = 'operator') {
  return apiFetch<{ group_id: string; status: string; message: string }>('/ai/alerts/correlated/approve', {
    method: 'POST',
    body: JSON.stringify({ group_id: groupId, action, approved_by: approvedBy }),
  })
}

// ── Capacity Forecast ─────────────────────────────────────────────────────────

export interface ResourceForecast {
  resource_type: string
  current_usage_pct: number
  trend_direction: string
  trend_slope_per_hour: number
  predicted_exhaustion_at: string | null
  hours_until_exhaustion: number | null
  confidence: string
  data_points_analyzed: number
  recommendation: string
}

export interface ScalingRecommendation {
  action_type: string
  target_service: string
  target_namespace: string
  current_replicas: number
  recommended_replicas: number | null
  current_resource_limit: string | null
  recommended_resource_limit: string | null
  reason: string
  estimated_monthly_cost_delta: number
  priority: string
  requires_approval: boolean
}

export interface CapacityForecastReport {
  service_name: string
  environment: string
  namespace: string
  forecasts: ResourceForecast[]
  scaling_recommendations: ScalingRecommendation[]
  overall_risk: string
  ai_narrative: string
  analyzed_window_hours: number
  generated_at: string
}

export function fetchCapacityForecast(serviceName: string, environment = 'dev', namespace = 'default') {
  return apiFetch<CapacityForecastReport>(
    `/ai/capacity-forecast/${encodeURIComponent(serviceName)}?environment=${encodeURIComponent(environment)}&namespace=${encodeURIComponent(namespace)}`
  )
}

export function approveScalingAction(serviceName: string, actionType: string, approvedBy = 'operator') {
  return apiFetch<{ status: string; message: string }>('/ai/capacity-forecast/approve-scaling', {
    method: 'POST',
    body: JSON.stringify({ service_name: serviceName, action_type: actionType, approved_by: approvedBy }),
  })
}

// ── Conversational Runbook Builder ────────────────────────────────────────────

export interface RunbookDraft {
  content: string
  version: number
  generated_at: string
}

export interface RunbookSessionResponse {
  session_id: string
  status: string
  initial_response?: string
  draft?: RunbookDraft | null
}

export interface RunbookChatResponse {
  session_id: string
  response: string
  draft: RunbookDraft | null
  message_count: number
}

export interface RunbookChatStreamEvent {
  type: 'token' | 'done' | 'error'
  text?: string
  error?: string
  session_id?: string
  response?: string
  draft?: RunbookDraft | null
  message_count?: number
}

export function startRunbookSession(requestId: string, serviceName: string, environment: string) {
  return apiFetch<RunbookSessionResponse>('/ai/runbooks/start-session', {
    method: 'POST',
    body: JSON.stringify({ request_id: requestId, service_name: serviceName, environment }),
  })
}

export function sendRunbookMessage(sessionId: string, message: string) {
  return apiFetch<RunbookChatResponse>('/ai/runbooks/chat', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, message }),
  })
}

export function streamRunbookMessage(
  sessionId: string,
  message: string,
  onEvent: (event: RunbookChatStreamEvent) => void,
  onError?: (err: Error) => void,
): AbortController {
  const controller = new AbortController()
  const url = `${API_BASE}/ai/runbooks/chat/stream`

  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        let detail = res.statusText
        try {
          const payload = await res.json() as { detail?: string; message?: string }
          detail = payload.detail || payload.message || detail
        } catch {
          // keep status text fallback
        }
        throw new Error(`Corvin API error ${res.status}: ${detail}`)
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
          if (!line.startsWith('data: ')) continue
          try {
            const payload = JSON.parse(line.slice(6)) as RunbookChatStreamEvent
            onEvent(payload)
          } catch {
            // Ignore malformed events.
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') onError?.(err as Error)
    })

  return controller
}

export function approveRunbookDraft(sessionId: string, approvedBy = 'operator') {
  return apiFetch<{ session_id: string; status: string; draft: RunbookDraft }>('/ai/runbooks/approve', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, approved_by: approvedBy }),
  })
}

export function saveRunbook(sessionId: string) {
  return apiFetch<{ session_id: string; status: string; path: string; content: string; message: string }>('/ai/runbooks/save', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId }),
  })
}

// ── War Games ─────────────────────────────────────────────────────────────────

export interface WarGamesScenario {
  id: string
  name: string
  type: 'chaos' | 'replay' | 'tabletop'
  description: string
  target_service: string
  environment: string
  difficulty: 'easy' | 'medium' | 'hard'
  estimated_duration_min: number
}

export function fetchWarGamesScenarios() {
  return apiFetch<WarGamesScenario[]>('/ai/war-games/scenarios')
}

// ── Simulator Presets (per-application, DB-driven) ───────────────────────────

export interface SimulatorPreset {
  id: string
  application_id: string
  scenario_id: string
  label: string
  service_name: string
  environment: string
  description: string
  icon_key: string | null
  accent_color: string | null
  is_active: boolean
  display_order: number
  created_at: string
  updated_at: string
}

export function listSimulatorPresets(appId: string) {
  return apiFetch<SimulatorPreset[]>(`/applications/${appId}/simulator-presets`)
}

export function createSimulatorPreset(appId: string, payload: Partial<SimulatorPreset>) {
  return apiFetch<SimulatorPreset>(`/applications/${appId}/simulator-presets`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateSimulatorPreset(appId: string, presetId: string, payload: Partial<SimulatorPreset>) {
  return apiFetch<SimulatorPreset>(`/applications/${appId}/simulator-presets/${presetId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteSimulatorPreset(appId: string, presetId: string) {
  return apiFetch<void>(`/applications/${appId}/simulator-presets/${presetId}`, { method: 'DELETE' })
}

// ── Convenience: list all services across all onboarded applications ──────────

export async function listAllServices(): Promise<Array<ApplicationService & { application_name: string; application_id: string }>> {
  const apps = await listApplications()
  const results: Array<ApplicationService & { application_name: string; application_id: string }> = []
  for (const app of apps) {
    const svcs = await apiFetch<ApplicationService[]>(`/applications/${app.id}/services`)
    for (const svc of svcs) {
      results.push({ ...svc, application_name: app.name, application_id: app.id })
    }
  }
  return results
}

// ── Application Environments ─────────────────────────────────────────────────

export interface ApplicationEnvironment {
  id: number
  application_id: string
  name: string
  display_name: string
  priority_tier: 'P1' | 'P2' | 'P3'
  lookback_minutes: number
  is_default: boolean
  display_order: number
  created_at: string
  updated_at: string
}

export function listEnvironments(appId: string) {
  return apiFetch<ApplicationEnvironment[]>(`/applications/${appId}/environments`)
}

export function createEnvironment(appId: string, payload: Partial<ApplicationEnvironment>) {
  return apiFetch<ApplicationEnvironment>(`/applications/${appId}/environments`, {
    method: 'POST', body: JSON.stringify(payload),
  })
}

export function updateEnvironment(appId: string, envId: number, payload: Partial<ApplicationEnvironment>) {
  return apiFetch<ApplicationEnvironment>(`/applications/${appId}/environments/${envId}`, {
    method: 'PUT', body: JSON.stringify(payload),
  })
}

export function deleteEnvironment(appId: string, envId: number) {
  return apiFetch<void>(`/applications/${appId}/environments/${envId}`, { method: 'DELETE' })
}

// ── Knowledge Base ───────────────────────────────────────────────────────────

export interface KnowledgeEntry {
  id: string
  application_id: string
  title: string
  content: string
  is_active: boolean
  display_order: number
  created_at: string
  updated_at: string
}

export function listKnowledge(appId: string) {
  return apiFetch<KnowledgeEntry[]>(`/applications/${appId}/knowledge`)
}

export function createKnowledge(appId: string, payload: Partial<KnowledgeEntry>) {
  return apiFetch<KnowledgeEntry>(`/applications/${appId}/knowledge`, {
    method: 'POST', body: JSON.stringify(payload),
  })
}

export function updateKnowledge(appId: string, kbId: string, payload: Partial<KnowledgeEntry>) {
  return apiFetch<KnowledgeEntry>(`/applications/${appId}/knowledge/${kbId}`, {
    method: 'PUT', body: JSON.stringify(payload),
  })
}

export function deleteKnowledge(appId: string, kbId: string) {
  return apiFetch<void>(`/applications/${appId}/knowledge/${kbId}`, { method: 'DELETE' })
}

// ── Runbook Library ──────────────────────────────────────────────────────────

export interface RunbookEntry {
  id: string
  application_id: string
  service_name: string | null
  title: string
  keywords: string[]
  content: string
  is_active: boolean
  display_order: number
  created_at: string
  updated_at: string
}

export function listRunbooks(appId: string) {
  return apiFetch<RunbookEntry[]>(`/applications/${appId}/runbooks`)
}

export function createRunbook(appId: string, payload: Partial<RunbookEntry>) {
  return apiFetch<RunbookEntry>(`/applications/${appId}/runbooks`, {
    method: 'POST', body: JSON.stringify(payload),
  })
}

export function updateRunbook(appId: string, rbId: string, payload: Partial<RunbookEntry>) {
  return apiFetch<RunbookEntry>(`/applications/${appId}/runbooks/${rbId}`, {
    method: 'PUT', body: JSON.stringify(payload),
  })
}

export function deleteRunbook(appId: string, rbId: string) {
  return apiFetch<void>(`/applications/${appId}/runbooks/${rbId}`, { method: 'DELETE' })
}

export async function listAllPresetsAcrossApplications(): Promise<Array<SimulatorPreset & { application_name: string }>> {
  const apps = await listApplications()
  const results: Array<SimulatorPreset & { application_name: string }> = []
  for (const app of apps) {
    const presets = await apiFetch<SimulatorPreset[]>(`/applications/${app.id}/simulator-presets`)
    for (const p of presets) {
      if (p.is_active) results.push({ ...p, application_name: app.name })
    }
  }
  return results
}


// ── Feature 8: Root Cause Debate Mode ─────────────────────────────────────────

export interface RCAHypothesis {
  /** Positional identifier: "h1" | "h2" | "h3" */
  id: string
  /** Short label ≤60 chars */
  title: string
  /** Full technical explanation of this hypothesis */
  root_cause: string
  /** Evidence source keys that support this hypothesis */
  evidence_ids: string[]
  /** LLM-assigned confidence score 0.0–1.0 */
  confidence_score: number
  /** Evidence strength 0–100 for UI progress bar */
  evidence_strength_pct: number
  /** Bullet list of key signals that support this hypothesis */
  supporting_signals: string[]
  /** Signals that argue against this hypothesis */
  refuting_signals: string[]
  /** Traceability map for supporting signals */
  supporting_evidence?: Array<{ source_id: string; summary: string }>
  /** Traceability map for refuting signals */
  refuting_evidence?: Array<{ source_id: string; summary: string }>
}

export interface DebatePairwiseInsight {
  left_id: string
  right_id: string
  winner_id: string
  score_gap: number
  reason: string
}

export interface DebateMeta {
  leader_id: string | null
  leader_score: number
  runner_up_id: string | null
  runner_up_score: number | null
  score_gap: number
  is_ambiguous: boolean
  recommendation: string
  pairwise: DebatePairwiseInsight[]
  selected_id: string | null
}

export interface HypothesesResponse {
  request_id: string
  hypotheses: RCAHypothesis[]
  /** "h1" | "h2" | "h3" | null — set when SRE selects a winner */
  selected_hypothesis_id: string | null
  debate_meta?: DebateMeta
}

/** Generate competing hypotheses for an investigation (triggers LLM call). */
export function generateHypotheses(investigationId: string): Promise<HypothesesResponse> {
  return apiFetch<HypothesesResponse>(`/investigations/${investigationId}/hypotheses`, {
    method: 'POST',
  })
}

/** Fetch already-generated hypotheses for an investigation (no LLM call). */
export function fetchHypotheses(investigationId: string): Promise<HypothesesResponse> {
  return apiFetch<HypothesesResponse>(`/investigations/${investigationId}/hypotheses`)
}

/** Select a winning hypothesis and re-run fix strategy generation. */
export function selectHypothesis(
  investigationId: string,
  hypothesisId: string,
): Promise<InvestigationResult & HypothesesResponse> {
  return apiFetch<InvestigationResult & HypothesesResponse>(
    `/investigations/${investigationId}/select-hypothesis`,
    {
      method: 'POST',
      body: JSON.stringify({ hypothesis_id: hypothesisId }),
    },
  )
}


// ── Feature 9: Incident Heatmap Calendar ──────────────────────────────────────

export interface HeatmapDay {
  /** ISO date string e.g. "2026-03-01" */
  date: string
  /** Number of investigations on this day */
  count: number
  /** Severity bucket based on investigation.yaml thresholds */
  severity: 'none' | 'low' | 'medium' | 'high' | 'critical'
}

export interface HeatmapSeverityThresholds {
  low: number
  medium: number
  high: number
  critical: number
}

export interface HeatmapResponse {
  /** Fully populated day-by-day list including zero-count days */
  days: HeatmapDay[]
  /** Highest single-day count in the window */
  max_count: number
  /** Total incidents across the entire window */
  total_incidents: number
  date_range: { start: string; end: string }
  /** Thresholds from investigation.yaml — use for color legend */
  severity_thresholds: HeatmapSeverityThresholds
}

export function fetchHeatmap(
  days?: number,
  serviceFilter?: string,
  environmentFilter?: string,
): Promise<HeatmapResponse> {
  const params = new URLSearchParams()
  if (days !== undefined) params.set('days', String(days))
  if (serviceFilter) params.set('service_name', serviceFilter)
  if (environmentFilter) params.set('environment', environmentFilter)
  const query = params.toString() ? `?${params.toString()}` : ''
  return apiFetch<HeatmapResponse>(`/investigations/heatmap${query}`)
}


// ── Feature 10: Compliance Evidence Pack ──────────────────────────────────────

/**
 * Download a compliance evidence pack for the given investigation.
 * Triggers a browser file download and returns the raw Blob.
 */
export async function downloadCompliancePack(
  investigationId: string,
  format: 'pdf' | 'zip',
): Promise<Blob> {
  const res = await fetch(
    `${API_BASE}/investigations/${investigationId}/compliance-pack?format=${format}`,
  )
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(detail?.detail ?? `Compliance pack error ${res.status}`)
  }
  const blob = await res.blob()

  // Trigger browser download automatically
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `corvin-evidence-pack-${investigationId}.${format}`
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)

  return blob
}


// ── Feature 7: pgvector Semantic RAG ──────────────────────────────────────────

export interface SemanticSimilarIncident {
  request_id: string
  service_name: string
  environment: string
  completed_at: string
  rca_summary: string
  root_cause: string
  confidence: 'high' | 'medium' | 'low'
  /** Cosine similarity score 0.0–1.0 (pgvector) or null (keyword fallback) */
  similarity_score: number | null
  /** "pgvector" | "keyword" — which backend served this result */
  search_backend: 'pgvector' | 'keyword'
}

export interface SemanticSearchResponse {
  results: SemanticSimilarIncident[]
  query: string
  backend: 'pgvector' | 'keyword'
  k: number
}

export function fetchSemanticSimilar(
  query: string,
  k?: number,
  serviceFilter?: string,
  environmentFilter?: string,
): Promise<SemanticSearchResponse> {
  const params = new URLSearchParams({ q: query })
  if (k !== undefined) params.set('k', String(k))
  if (serviceFilter) params.set('service_name', serviceFilter)
  if (environmentFilter) params.set('environment', environmentFilter)
  return apiFetch<SemanticSearchResponse>(`/investigations/similar?${params.toString()}`)
}


