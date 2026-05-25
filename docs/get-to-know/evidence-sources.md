# Corvin Evidence Sources — Quick Reference

Every investigation Corvin runs collects evidence from multiple sources before sending it to the LLM for Root Cause Analysis. This doc explains **what each source is**, **what it tells us**, and **what it fetches** from Azure.

---

## At a Glance

| # | UI Label | Source Key | Azure Table | Adapter |
|---|----------|------------|-------------|---------|
| 1 | Application Logs | `container_logs` | ContainerLog | ContainerLogsAdapter |
| 2 | Application Logs (Elastic) | `elastic_logs` | Elastic index | ElasticAdapter |
| 3 | API Gateway | `apim_logs` | ApiManagementGatewayLogs | LogAnalyticsAdapter |
| 4 | K8s Cluster Health | `aks_context` | Kubernetes API (live) | AKSAdapter |
| 5 | K8s Resource Usage | `resource_metrics` | Perf (K8SContainer) | ContainerLogsAdapter |
| 6 | Container Images | `container_inventory` | ContainerInventory | ContainerLogsAdapter |
| 7 | K8s Node Health | `node_inventory` | KubeNodeInventory | ContainerLogsAdapter |
| 8 | Network Traffic | `network_metrics` | InsightsMetrics | ContainerLogsAdapter |
| 9 | K8s Pod Restarts | `pod_restarts` | KubePodInventory | ContainerLogsAdapter |
| 10 | K8s OOM Kill Events | `oom_kill_events` | KubeEvents | ContainerLogsAdapter |
| 11 | K8s Autoscaler Events | `autoscaler_events` | KubeEvents | ContainerLogsAdapter |
| 12 | K8s Health Probes | `health_probe_failures` | KubeEvents | ContainerLogsAdapter |

---

## 1. Application Logs (`container_logs`)

**What it is:** stdout/stderr logs from containers running on AKS, collected via Container Insights.

**What it tells us:** Application errors, exceptions, stack traces, slow queries, connection failures — the raw output your Java/Python app writes to console.

**What it fetches:**
- **Table:** `ContainerLog` joined with `KubePodInventory` (to scope by namespace + service name)
- **Fields:** `TimeGenerated`, `Name`, `LogEntry`, `LogEntrySource`, `ContainerID`
- **Join strategy:** Gets `ContainerID` from `KubePodInventory` → filters `ContainerLog` by those IDs
- **Default window:** 60 minutes, max 200 rows

---

## 2. Application Logs — Elastic (`elastic_logs`)

**What it is:** Application logs stored in Elasticsearch (alternative to Container Insights logs).

**What it tells us:** Same as above — application-level errors and traces — but from Elastic's index instead of Azure.

**What it fetches:**
- **Index:** Configurable per `config/integrations/elastic.yaml`
- **Query:** Filters by `service_name` and time range
- **Note:** Optional source. Elastic may be org-SSO-blocked. Corvin works fine without it.

---

## 3. API Gateway (`apim_logs`)

**What it is:** Azure API Management gateway request/response logs.

**What it tells us:** API call failures, HTTP 4xx/5xx responses, latency spikes, backend timeouts, request throttling — everything that flows through APIM.

**What it fetches:**
- **Table:** `ApiManagementGatewayLogs` in Log Analytics
- **Fields:** Timestamp, operation, response code, duration, backend response code, errors
- **Adapter:** `LogAnalyticsAdapter`

---

## 4. K8s Cluster Health (`aks_context`)

**What it is:** Live Kubernetes API state for pods, deployments, and recent events.

**What it tells us:** Current pod status (Running/CrashLoopBackOff/Pending), deployment replica counts, recent warning events — the real-time view of what's happening in the cluster right now.

**What it fetches:**
- **Source:** Kubernetes API (via `kubernetes` Python client, not KQL)
- **Data:** Pod list with container statuses, restart counts, deployment spec vs actual replicas, recent events
- **Auth:** Kubeconfig (local dev) or in-cluster credentials (production)
- **Note:** This is a live API call, not a historical log query

---

## 5. K8s Resource Usage (`resource_metrics`)

**What it is:** CPU and memory usage, limits, and requests for containers — the numbers behind `kubectl top`.

**What it tells us:** Whether containers are CPU-throttled, approaching memory limits, or have misconfigured resource requests. Shows usage vs. limit ratios over time.

**What it fetches:**
- **Table:** `Perf` (Container Insights standard table, `ObjectName == 'K8SContainer'`)
- **Counters (7 total):**
  - `cpuUsageNanoCores` — actual CPU consumed
  - `cpuLimitNanoCores` — CPU limit set on the container
  - `cpuRequestNanoCores` — CPU request (guaranteed minimum)
  - `memoryWorkingSetBytes` — actual memory in use
  - `memoryRssBytes` — resident set size (physical memory)
  - `memoryLimitBytes` — memory limit set on the container
  - `memoryRequestBytes` — memory request (guaranteed minimum)
- **Join strategy:** Gets `PodUid` from `KubePodInventory` → filters `Perf.InstanceName` via `has_any` (InstanceName embeds PodUid)
- **Aggregation:** 5-minute bins, avg + max per counter per container
- **Why limits matter:** Without limits, you can't tell if 500MB usage is fine (limit=2GB) or critical (limit=512MB)

---

## 6. Container Images (`container_inventory`)

**What it is:** Image metadata for every container running the service.

**What it tells us:** Which image version is deployed, when it was created/started, container state, exit codes. Critical for detecting bad deployments or rollback scenarios.

**What it fetches:**
- **Table:** `ContainerInventory` joined with `KubePodInventory`
- **Fields:** `Name`, `Image`, `ImageTag`, `ContainerState`, `CreatedTime`, `StartedTime`, `FinishedTime`, `ExitCode`
- **Example:** Image `14470-chad/fundapis:20260521.4`, State `Running`, Started `2026-05-21T18:52:49`

---

## 7. K8s Node Health (`node_inventory`)

**What it is:** Status of the AKS nodes (VMs) hosting the service's pods.

**What it tells us:** Whether nodes are `Ready` or under pressure (MemoryPressure, DiskPressure, PIDPressure). Node-level issues cause pod evictions and scheduling failures that look like app problems.

**What it fetches:**
- **Table:** `KubeNodeInventory` scoped to nodes running the service's pods
- **Fields:** `Computer` (node name), `Status`, `KubeletVersion`, `KubeProxyVersion`, `OperatingSystem`
- **Join strategy:** Gets `Computer` from `KubePodInventory` (the node each pod is scheduled on) → filters `KubeNodeInventory`

---

## 8. Network Traffic (`network_metrics`)

**What it is:** Network bytes sent/received per node, from Container Insights.

**What it tells us:** Network saturation, connection storms, unusual traffic spikes. If a service is slow but CPU/memory are fine, network might be the bottleneck.

**What it fetches:**
- **Table:** `InsightsMetrics` (`Name in ('bytes_sent', 'bytes_recv')`)
- **Fields:** `HostName`, `Name` (metric), `AvgValue`, `MaxValue`
- **Join strategy:** Gets `Computer` (node names) from `KubePodInventory` → matches `InsightsMetrics.Tags.hostName`
- **Aggregation:** 5-minute bins, avg + max

---

## 9. K8s Pod Restarts (`pod_restarts`)

**What it is:** Restart count trends for each pod over the lookback window.

**What it tells us:** Crash-looping pods, intermittent OOM kills, or containers that keep restarting. A pod with 0 restarts is healthy; 5+ restarts in an hour is a red flag.

**What it fetches:**
- **Table:** `KubePodInventory`
- **Fields:** `Name`, `PodStatus`, `ContainerStatus`, `ContainerStatusReason`, `ContainerRestartCount`, `PodRestartCount`
- **Aggregation:** Latest state per pod (`arg_max` by `TimeGenerated`), sorted by restart count descending

---

## 10. K8s OOM Kill Events (`oom_kill_events`)

**What it is:** Out-of-memory kill events from the Kubernetes event stream.

**What it tells us:** The kernel killed a container because it exceeded its memory limit. This is the smoking gun for memory leaks or undersized memory limits.

**What it fetches:**
- **Table:** `KubeEvents`
- **Filter:** `Reason in ('OOMKilling', 'OOMKilled', 'Killing')` OR `Message contains 'OOM'` OR `Message contains 'out of memory'`
- **Fields:** `TimeGenerated`, `Name`, `Reason`, `Message`, `Count`
- **Note:** Empty results on a healthy cluster is expected — these only appear during actual OOM incidents

---

## 11. K8s Autoscaler Events (`autoscaler_events`)

**What it is:** Horizontal Pod Autoscaler (HPA) events — scale-up, scale-down, and failures.

**What it tells us:** Whether the autoscaler is thrashing (rapid scale up/down), failing to compute metrics, or hitting scaling limits. An HPA failure during a traffic spike means the app can't scale to meet demand.

**What it fetches:**
- **Table:** `KubeEvents`
- **Filter:** `Reason in ('FailedComputeMetricsReplicas', 'FailedGetScale', 'FailedRescale', 'SuccessfulRescale', 'ScalingLimited', 'FailedGetResourceMetric', 'FailedGetExternalMetric')` OR `ObjectKind == 'HorizontalPodAutoscaler'`
- **Fields:** `TimeGenerated`, `Name`, `Reason`, `Message`, `Count`, `ObjectKind`

---

## 12. K8s Health Probes (`health_probe_failures`)

**What it is:** Kubernetes liveness and readiness probe failure events.

**What it tells us:** Pods failing health checks get removed from service (readiness) or restarted (liveness). This causes intermittent 503s and connection drops even when the app "looks" healthy in logs.

**What it fetches:**
- **Table:** `KubeEvents`
- **Filter:** `Reason in ('Unhealthy', 'FailedLiveness', 'FailedReadiness', 'ProbeError', 'ContainerUnhealthy')`
- **Fields:** `TimeGenerated`, `Name`, `Reason`, `Message`, `Count`

---

## How Evidence Flows Through Corvin

```
Alert / Manual Trigger
        │
        ▼
  EnrichmentService.enrich()
        │
        ├── ContainerLogsAdapter  ──▶  sources 1, 5, 6, 7, 8, 9, 10, 11, 12
        ├── ElasticAdapter        ──▶  source 2
        ├── LogAnalyticsAdapter   ──▶  source 3
        └── AKSAdapter            ──▶  source 4
        │
        ▼
  EvidenceBundle (Pydantic model)
        │
        ▼
  RCAGenerator  ──▶  LLM prompt with all evidence
        │
        ▼
  Root Cause Analysis + Fix Strategy
```

## Common Patterns to Look For

| Symptom | Key Sources | What to check |
|---------|-------------|---------------|
| App returning 500s | Application Logs, API Gateway | Stack traces, backend timeouts |
| Pods restarting | Pod Restarts, OOM Kill Events | Restart count > 0, OOMKilled reason |
| Slow responses | Resource Usage, Network Traffic | CPU near limit, memory pressure, network saturation |
| Deployment broke things | Container Images | Image tag changed recently, exit code != 0 |
| Scaling failures | Autoscaler Events | FailedRescale, ScalingLimited reasons |
| Intermittent 503s | Health Probes, K8s Cluster Health | FailedReadiness, pods not Ready |
| Node-level issues | Node Health | Status != Ready, MemoryPressure/DiskPressure |
