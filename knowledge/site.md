# Corvin Site Knowledge Base

This file is injected into the investigation engine system prompt before the
reasoning loop begins.  Keep it accurate and concise — the engine reads the
whole file as context.

---

## What is CHAD?

**CHAD = Channel Application Digital APIs & Function Hub**

CHAD is the name of the organisation's digital channel platform. It provides:
- **Fund APIs** (`fundapis`) — backend APIs for fund-related operations, exposed via APIM.
- **Partner APIs** (`partnerapis`) — APIs for partner integrations, exposed via APIM.
- **Fund SSO** (`fundsso`) — the authentication/SSO service for the channel app, called **directly** by the client app (NOT through APIM).

> ⚠️ Important: The APIM `BackendId: function-app-backend` is **not** a separate Azure Function App.
> It is simply the APIM backend reference name pointing to `fundapis` and `partnerapis` running in AKS.

---

## Traffic Flow Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   CLIENT APPLICATION                     │
│         (browser / mobile / partner system)              │
└───────────┬──────────────────────────────┬──────────────┘
            │  Fund & Partner API calls    │  SSO / Auth calls
            │  (goes through APIM)         │  (hits AKS directly — NO APIM)
            ▼                              ▼
┌─────────────────────┐        ┌──────────────────────────┐
│  Azure API Management│        │  AKS — chad namespace    │
│  (APIM DV01)        │        │  ┌────────────────────┐  │
│  - fundapis API  ───┼───────▶│  │   chad-fundsso     │  │
│  - partnerapis API──┼──┐     │  │   (SSO service)    │  │
└─────────────────────┘  │     │  └────────────────────┘  │
                          │     └──────────────────────────┘
                          │
                          ▼
           ┌──────────────────────────┐
           │  AKS — chad namespace    │
           │  ┌────────────────────┐  │
           │  │   chad-fundapis    │  │
           │  │  (Fund APIs, 2r)   │  │
           │  ├────────────────────┤  │
           │  │  chad-partnerapis  │  │
           │  │  (Partner APIs)    │  │
           │  └────────────────────┘  │
           └──────────────────────────┘
```

**Key rule:** `fundsso` is a direct AKS service — client apps call it straight without APIM in the path. `fundapis` and `partnerapis` always flow through APIM first.

---

## AKS Cluster

- Cluster name:        `azaustaekub14470dv0101`
- Resource group:      `RG_14470_AUCHAD_DV01`
- EAI code:            `14470`
- Region:              `australiaeast`
- Default namespace:   `chad`
- Container Insights:  enabled → `LogAnalytics-AUCHAD-DV01`

## Azure API Management (APIM)

- Resource group:      `RG_14359_APIM_DV01`
- EAI code:            `14359`
- Log Analytics workspace: `LogAnalytics-APIM-DV01`
- Primary gateway log table: `ApiManagementGatewayLogs`
- Known ApiId values:  `system`, `fundapis`, `partnerapis`
- Known BackendId:     `function-app-backend` ← this is the APIM name for `chad-fundapis` / `chad-partnerapis` in AKS (not a separate app)

## Monitored Services

| Service Name | AKS Deployment   | Namespace | Normal Replicas | Entry Point         | Notes                                                                                     |
|--------------|------------------|-----------|-----------------|---------------------|-------------------------------------------------------------------------------------------|
| fundapis     | chad-fundapis    | chad      | 2               | APIM → AKS          | Fund APIs backend                                                                         |
| fundsso      | chad-fundsso     | chad      | 2               | **Direct (no APIM)**| Fund SSO / auth service — depends on **PingFederate** for token validation/federation     |
| partnerapis  | chad-partnerapis | chad      | 2               | APIM → AKS          | Partner APIs (1/2 ready — HPA metric issue)                                               |

## External Dependencies

### PingFederate (Identity Provider)
- **fundsso** relies on **PingFederate** as its upstream identity provider / federation server.
- PingFederate handles SAML/OAuth token issuance and validation for the SSO flow.
- If PingFederate is unreachable or returns errors, `fundsso` authentication failures will cascade to all services that rely on the channel app SSO.
- PingFederate is **not** hosted in the CHAD AKS cluster — it is a separate on-premises or managed service.
- When investigating `fundsso` 401/403 errors or auth timeouts, always check PingFederate health as a likely upstream cause.

### Azure Cosmos DB
- CHAD applications (`fundapis`, `partnerapis`) use **Azure Cosmos DB** as their primary data store for fund and partner records.
- Cosmos DB RU (Request Unit) throttling (`429 Too Many Requests`) is a common cause of latency spikes and 5xx errors in `fundapis` and `partnerapis`.
- If APIM logs show elevated error rates with `429` or `503` backend responses, check Cosmos DB metrics (RU consumption, throttled requests) in Azure Monitor.
- The Cosmos DB account is in the same region (`australiaeast`) and resource group as the CHAD application layer.

## Log Analytics Workspaces

| Workspace                | ID                                   | Purpose                     |
|--------------------------|--------------------------------------|-----------------------------|
| LogAnalytics-APIM-DV01   | 562100ab-f3fe-46c0-8512-d4244fe33f92 | APIM gateway logs           |
| LogAnalytics-AUCHAD-DV01 | 4e6bd62b-cc6e-4538-b1fe-f28f68666d1f | AKS container logs & events |

## Evidence Sources

- APIM gateway logs → `LogAnalyticsAdapter` → `ApiManagementGatewayLogs` table
- AKS pod status → `AKSAdapter` → direct Kubernetes API
- AKS container logs → `ContainerLogsAdapter` → `ContainerLog` table (old format; ContainerLogV2 schema exists but has no data yet)
- AKS pod inventory → `ContainerLogsAdapter` → `KubePodInventory` table
- AKS warning events → `ContainerLogsAdapter` → `KubeEvents` table
- Resource changes → `AzureActivityAdapter` → `AzureActivity` table (requires Diagnostic Setting to be enabled on subscription)

## Alert Routing

- Azure Action Groups forward to: `POST /triggers/azure-alert`
- Manual trigger endpoint: `POST /triggers/manual`

## Known Issues / Constraints

- `chad-partnerapis` HPA reports `FailedComputeMetricsReplicas` — CPU metrics unavailable for pods, causing 1/2 replicas only. Investigate metrics-server or resource requests.
- Elastic (`https://c697cd417c6c4a879c778dd74ff9e641.australiaeast.azure.elastic-cloud.com`) is blocked by org SSO — use Container Insights as the log source.
- Azure Activity Log not yet flowing to APIM workspace — Diagnostic Setting needed on subscription/resource group.
- `ContainerLogV2` table schema exists in AUCHAD workspace but has no ingested data — cluster is using legacy `ContainerLog` format.
- V1 does not execute fixes. All FixStrategyOutput actions require human review.
- Confidence threshold before surfacing RCA: `medium` (see `config/policies/investigation.yaml`)
