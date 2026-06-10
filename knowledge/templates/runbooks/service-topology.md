---
template: service-topology
version: "1"
description: AKS deployment topology for a microservices application
---

# <APPLICATION_NAME> — AKS Service Topology

## Kubernetes Namespace

| Field | Value |
|-------|-------|
| Namespace | `<namespace>` |
| Cluster | `<aks-cluster-name>` |
| Environment | `<production / staging / dev>` |

---

## Deployments

| Deployment | Image | Replicas (min/max) | HPA CPU Target | Purpose |
|------------|-------|---------------------|----------------|---------|
| `<deployment-name-1>` | `<registry>/<image>:<tag>` | `<min>`/`<max>` | `<cpu-pct>%` | `<purpose>` |
| `<deployment-name-2>` | `<registry>/<image>:<tag>` | `<min>`/`<max>` | `<cpu-pct>%` | `<purpose>` |

---

## Pod Labels

All pods in this application carry these labels:

```yaml
app: <app-label>
version: <version-label>
# Add any additional labels used for Istio routing or alerting
```

---

## Service Objects

| Service | Type | Port | Selector |
|---------|------|------|---------|
| `<svc-name-1>` | ClusterIP | `<port>` | `app: <app-label>` |
| `<svc-name-2>` | ClusterIP | `<port>` | `app: <app-label>` |

---

## Health Probes

| Deployment | Startup (initial/period/failure) | Readiness (period/failure) | Liveness (period/failure) |
|------------|----------------------------------|---------------------------|--------------------------|
| `<deployment-1>` | `<Xs delay / Xs period / N fails>` | `<Xs period / N fails>` | `<Xs period / N fails>` |

---

## HPA Configuration

| Deployment | Min Replicas | Max Replicas | CPU Target | Scale-Up Stabilisation | Scale-Down Stabilisation |
|------------|-------------|-------------|-----------|----------------------|------------------------|
| `<deployment-1>` | `<N>` | `<N>` | `<pct>%` | `<seconds>s` | `<seconds>s` |

---

## Pod Security Context

```yaml
runAsNonRoot: true
runAsUser: <uid>           # non-root UID
allowPrivilegeEscalation: false
readOnlyRootFilesystem: <true/false>
capabilities:
  drop: [ALL]
```

---

## Ingress / Gateway

| Component | Type | Host | Notes |
|-----------|------|------|-------|
| `<ingress-name>` | `<APIM / Istio Gateway / Nginx Ingress>` | `<hostname>` | `<notes>` |

---

## Service Mesh (Istio)

| Resource | Name | Purpose |
|----------|------|---------|
| `<VirtualService>` | `<name>` | `<routing rules>` |
| `<AuthorizationPolicy>` | `<name>` | `<who can call whom>` |
| `<PeerAuthentication>` | `<name>` | `<mTLS mode>` |

If not using Istio, delete this section.

---

## Observability / Telemetry

| Signal | Agent / Library | Destination |
|--------|-----------------|------------|
| Traces | `<OTEL Java Agent / OpenTelemetry SDK / Jaeger>` | `<OTLP endpoint>` |
| Metrics | `<Micrometer / Prometheus / OTEL>` | `<endpoint>` |
| Logs | `<Elastic Agent / Fluent Bit / Azure Monitor>` | `<log destination>` |

OTEL service name for this application: `<service-name>`  
Environment tag: `<prod / staging / dev>`

---

## Supporting Infrastructure in Namespace

| Pod/Deployment | Purpose |
|---------------|---------|
| `<component>` | `<purpose, e.g. Elastic Agent for log collection>` |

---

## SRE Notes

- `<Common operational observation 1, e.g.: HPA doesn't scale until CPU sustains above threshold for 3 minutes>`
- `<Common operational observation 2>`
- `<Known quirk or timing issue>`

---

## See Also

- [Service Inventory](service-inventory.md) — Maven/build metadata and inter-service dependency matrix
- [Service Dependencies](service-dependencies.md) — external dependencies (databases, auth, downstream APIs)
- [Security Context](service-security-context.md) — auth architecture, Workload Identity, secret management
