# Corvin Site Knowledge Base

This file is injected into the investigation engine system prompt before the
reasoning loop begins.  Keep it accurate and concise — the engine reads the
whole file as context.

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
- Known BackendId:     `function-app-backend`

## Monitored Services

| Service Name   | AKS Deployment    | Namespace | Normal Replicas | Notes                          |
|----------------|-------------------|-----------|-----------------|--------------------------------|
| fundapis       | chad-fundapis     | chad      | 2               | Fund APIs backend              |
| fundsso        | chad-fundsso      | chad      | 2               | Fund SSO service               |
| partnerapis    | chad-partnerapis  | chad      | 2               | Partner APIs (1/2 ready — HPA metric issue noted) |

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
