/**
 * Demo-mode predictive alerts for the Predictive Analytics page.
 *
 * Service names are injected at runtime from the list of onboarded
 * services so that the demo works for any customer's application.
 * Toggle on via the "Demo Mode" button; real alerts continue underneath.
 */
import type { PredictiveAlert } from '../api/client'

const now = Date.now()
const mins = (m: number) => new Date(now + m * 60_000).toISOString()
const ago = (m: number) => new Date(now - m * 60_000).toISOString()

/**
 * Generate a realistic set of demo predictive alerts using the provided
 * service names. Falls back to generic names if fewer than 3 are supplied.
 */
export function buildDemoAlerts(serviceNames: string[]): PredictiveAlert[] {
  const s0 = serviceNames[0] ?? 'service-a'
  const s1 = serviceNames[1] ?? 'service-b'
  const s2 = serviceNames[2] ?? 'service-c'

  return [
    {
      id: 'demo-1',
      service_name: s0,
      environment: 'production',
      alert_type: 'cpu_pressure',
      title: 'CPU spike detected — pods throttling under load',
      summary:
        `CPU utilisation has surged to 92.3% across ${s0} pods, breaching the 80% threshold. ` +
        'If the trend continues, full saturation is projected in 11 minutes. Auto-scaler is at max replicas.',
      rationale:
        `(live) Avg CPU usage across 6 pods is 92.3%. Limit per pod is 500m (0.5 vCPU). ` +
        '4 of 6 pods show >90% utilisation. HPA maxReplicas (6) reached — no further scale-out possible.',
      severity: 'critical',
      confidence: 'high',
      signal_value: 92.3,
      threshold_value: 80.0,
      estimated_breach_at: mins(11),
      source_request_id: null,
      investigation_request_id: null,
      status: 'active',
      created_at: ago(4),
      confidence_pct: 94.2,
      related_count: 4,
      blast_radius_users: 12_400,
      blast_radius_requests: 38_600,
      change_correlation: `Deployment ${s0}:v2.14.3 rolled out 22min ago — new connection pool config`,
    },
    {
      id: 'demo-2',
      service_name: s1,
      environment: 'production',
      alert_type: 'error_rate',
      title: 'Authentication error rate spiking — 5xx responses climbing',
      summary:
        `Error rate has jumped to 8.7% against the 5% SLA threshold on ${s1}. ` +
        'Token validation failures are cascading. Breach projected in 26 minutes if trend holds.',
      rationale:
        '(live) 5xx error rate over last 5 min window: 8.7%. Baseline (24h avg): 0.4%. ' +
        '87% of errors are 503 from /oauth2/token endpoint.',
      severity: 'high',
      confidence: 'high',
      signal_value: 8.7,
      threshold_value: 5.0,
      estimated_breach_at: mins(26),
      source_request_id: null,
      investigation_request_id: null,
      status: 'active',
      created_at: ago(7),
      confidence_pct: 88.1,
      related_count: 3,
      blast_radius_users: 5_200,
      blast_radius_requests: 14_800,
      change_correlation: null,
    },
    {
      id: 'demo-3',
      service_name: s2,
      environment: 'production',
      alert_type: 'memory_pressure',
      title: 'Memory working set approaching OOM threshold',
      summary:
        `Memory utilisation at 78.4% of limit on ${s2}. Two pods showing >85%. ` +
        'GC pause times increasing. OOMKill risk within 45 minutes if leak continues.',
      rationale:
        '(live) Avg memory working set: 802 MiB across 4 pods (limit 1024 MiB). ' +
        'Heap growth rate: +18 MiB/min over last 15 min. Possible memory leak in DB connection handler.',
      severity: 'high',
      confidence: 'medium',
      signal_value: 78.4,
      threshold_value: 85.0,
      estimated_breach_at: mins(45),
      source_request_id: null,
      investigation_request_id: null,
      status: 'active',
      created_at: ago(12),
      confidence_pct: 72.5,
      related_count: 2,
      blast_radius_users: 3_100,
      blast_radius_requests: 9_400,
      change_correlation: null,
    },
    {
      id: 'demo-4',
      service_name: s0,
      environment: 'production',
      alert_type: 'latency_degradation',
      title: 'P99 latency exceeding SLA — response times 3× baseline',
      summary:
        `P99 latency has risen to 2,840 ms against the 1,000 ms SLA target on ${s0}. ` +
        'Database connection pool exhaustion detected. 14% of requests timing out.',
      rationale:
        '(live) P99 latency (5 min window): 2,840 ms. SLA target: 1,000 ms. ' +
        'Connection pool utilisation: 97/100 active. Wait queue depth: 34.',
      severity: 'critical',
      confidence: 'high',
      signal_value: 284.0,
      threshold_value: 100.0,
      estimated_breach_at: mins(5),
      source_request_id: null,
      investigation_request_id: null,
      status: 'active',
      created_at: ago(2),
      confidence_pct: 96.8,
      related_count: 4,
      blast_radius_users: 12_400,
      blast_radius_requests: 38_600,
      change_correlation: `Deployment ${s0}:v2.14.3 — new connection pool config`,
    },
    {
      id: 'demo-5',
      service_name: s1,
      environment: 'staging',
      alert_type: 'disk_pressure',
      title: 'Persistent volume 87% full — log rotation stalled',
      summary:
        `Log volume on ${s1} staging is filling at 2.1 GB/hour. Current usage 87%. ` +
        'If log rotation does not recover, volume will be full in ~90 minutes.',
      rationale:
        '(live) PVC logs: 43.5 GiB used of 50 GiB (87%). Growth rate: 2.1 GiB/h. ' +
        'Log rotation cron last succeeded 6 hours ago — appears stuck.',
      severity: 'medium',
      confidence: 'medium',
      signal_value: 87.0,
      threshold_value: 90.0,
      estimated_breach_at: mins(90),
      source_request_id: null,
      investigation_request_id: null,
      status: 'active',
      created_at: ago(20),
      confidence_pct: 61.3,
      related_count: 1,
      blast_radius_users: 0,
      blast_radius_requests: 0,
      change_correlation: null,
    },
    {
      id: 'demo-6',
      service_name: s2,
      environment: 'production',
      alert_type: 'error_rate',
      title: 'DB request charge exceeding provisioned throughput budget',
      summary:
        `${s2} DB consumption at 84% of provisioned throughput. 429 throttling responses starting. ` +
        'Cross-partition queries detected.',
      rationale:
        '(live) Current RU/s: 4,200 (84% of 5,000 limit). 429 responses: 12 in last 5 min. ' +
        'Top query consuming 380 RU per execution — cross-partition scan.',
      severity: 'medium',
      confidence: 'high',
      signal_value: 84.0,
      threshold_value: 95.0,
      estimated_breach_at: mins(68),
      source_request_id: null,
      investigation_request_id: null,
      status: 'active',
      created_at: ago(15),
      confidence_pct: 79.4,
      related_count: 2,
      blast_radius_users: 1_800,
      blast_radius_requests: 6_200,
      change_correlation: 'New batch sync job deployed 40min ago — runs cross-partition queries',
    },
  ]
}

/** @deprecated Use buildDemoAlerts(serviceNames) instead. */
export const DEMO_ALERTS = buildDemoAlerts([])
