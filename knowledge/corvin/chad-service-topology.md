---
keywords: [chad-fundapis, chad-partnerapis, chad-fundsso, chad-fundsso-hpa, chad-fundapis-hpa, chad-partnerapis-hpa, chad-sa, chad-shared-gateway, istio, sidecar.istio.io/inject, azure.workload.identity/use, project=chad, service=fundapis, service=partnerapis, service=fundsso, ClusterIP, HPA, autoscaling/v2, acr14470aepr011, EAI14470-Prod, channels.metlife.com.au, elastic-agent-otlp, elastic-agent]
---
# CHAD Service Topology

## Kubernetes Deployment

- **Namespace:** `chad` — the Helm release namespace parameter `k8sNamespace` defaults to `chad` in `14470_CHAD_FundAPIs_Deploy.yaml`. All three services deploy to this namespace. All `kubectl` commands for incident response must include `-n chad`.
- **Production host:** `www.channels.metlife.com.au`
- **Dev host:** `dev.channels.metlife.com.au`
- **Container registry (prod):** `acr14470aepr011.azurecr.io/14470-chad/`
- **OTEL service namespace tag:** `ChAD` (all services)
- **OTEL deployment environment tag:** `EAI14470-Prod`

### Deployments

| Deployment Name | Container Name | Image Repo (Prod) | Default Port | OTEL Service Name (Prod) |
| :--- | :--- | :--- | :--- | :--- |
| `chad-fundapis` | `fundapis` | `acr14470aepr011.azurecr.io/14470-chad/fundapis:latest` | `8080` | `ChAD-Fund-APIs-PROD` |
| `chad-partnerapis` | `partnerapis` | `acr14470aepr011.azurecr.io/14470-chad/partnerapis:latest` | `8080` | `ChAD-Partner-APIs-PROD` |
| `chad-fundsso` | `fundsso` | `acr14470aepr011.azurecr.io/14470-chad/fundsso:latest` | `8080` | `ChAD-Fund-SSO-PROD` |

### Key Pod Labels

```
app: chad-fundapis | chad-partnerapis | chad-fundsso
project: chad
service: fundapis | partnerapis | fundsso
environment: prod | dev | qa
azure.workload.identity/use: "true"
```

Istio sidecar injection is enabled on all pods via annotation: `sidecar.istio.io/inject: "true"`

### Service Objects (Kubernetes)

All three services use `type: ClusterIP` — they are not directly exposed outside the cluster. External traffic enters via the Istio Ingress Gateway.

| K8s Service | Target Deployment | Port |
| :--- | :--- | :--- |
| `chad-fundapis` | `chad-fundapis` | `8080` |
| `chad-partnerapis` | `chad-partnerapis` | `8080` |
| `chad-fundsso` | `chad-fundsso` | `8080` |

### Istio Ingress Gateway

- **Gateway name:** `chad-shared-gateway`
- **HTTPS:** port `443`, TLS mode `SIMPLE`, TLS credential name `<environment>-chad-certs`
- **HTTP:** port `80`, redirects to HTTPS
- **Selector:** `istio: ingressgateway`

Traffic path: `Akamai CDN → Azure Application Gateway → APIM (EAI14470) → Istio Ingress Gateway → chad-* ClusterIP Service → pod`

---

## HPA & Scaling (Production)

| HPA Name | Target Deployment | Min Replicas | Max Replicas | Scale Metric | CPU Target |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `chad-fundapis-hpa` | `chad-fundapis` | `3` | `10` | CPU utilisation | `70%` |
| `chad-partnerapis-hpa` | `chad-partnerapis` | `2` | `8` | CPU utilisation | `70%` |
| `chad-fundsso-hpa` | `chad-fundsso` | `2` | `8` | CPU utilisation | `70%` |

- **HPA API version:** `autoscaling/v2`
- **Known constraint:** HPAs are CPU-based only. There are no custom metric HPAs. If requests queue up at Cosmos or PingFederate (slow responses, not CPU pressure), the HPA will NOT scale out. Under those conditions pods pile up in-flight requests, latency rises, and eventually return `500`.
- **Pod resource limits (prod fundapis):** CPU limit `2000m`, memory limit `2Gi`, request CPU `500m`, memory `512Mi`
- **Pod resource limits (prod partnerapis/fundsso):** CPU limit `1000m`, memory limit `1Gi`, request CPU `250m`, memory `256Mi`
- **JVM flags:** G1GC, `MaxRAMPercentage=60` (fundapis), `Xmx768m` (partnerapis/fundsso). OTEL Java agent active in prod via `-javaagent:/home/app/opentelemetry-javaagent.jar`.

---

## Pod Health Probes

All three deployments share the same probe config:

| Probe | Path | Initial Delay | Period | Failure Threshold |
| :--- | :--- | :--- | :--- | :--- |
| Startup | `GET /actuator/health` | 60s | 10s | 30 (= up to 360s total startup budget) |
| Readiness | `GET /actuator/health/readiness` | 30s | 10s | 6 |
| Liveness | `GET /actuator/health/liveness` | (set in template) | — | — |

If a pod fails its startup probe for > 360 seconds it will be killed and restarted. Common cause: Key Vault unreachable at startup (pod logs will show `com.azure.identity` or Key Vault errors).

---

## Security Context

All pods run as non-root (`runAsUser: 1000`, `runAsGroup: 1000`). `allowPrivilegeEscalation: false`. All Linux capabilities dropped. These constraints are hardened and cannot be bypassed at runtime.

---

## Supporting Infrastructure in Cluster

| Component | Namespace | Purpose |
| :--- | :--- | :--- |
| `elastic-agent-otlp` service | `elastic-agent` | In-cluster OTLP receiver; all three CHAD services push metrics, traces, and logs here on port `8200` |
| Istio sidecar (Envoy) | same namespace as CHAD pods | mTLS, traffic management, Istio `AuthorizationPolicy` enforced |
| `chad-sa` ServiceAccount | same namespace as CHAD pods | Azure Workload Identity federated credential; used by all three deployments |
