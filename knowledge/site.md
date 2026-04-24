# Corvin Site Knowledge Base

This file is injected into the investigation engine system prompt before the
reasoning loop begins.  Keep it accurate and concise — the engine reads the
whole file as context.

Replace all placeholder values below with real infrastructure facts before
running live investigations.

---

## AKS Cluster

- Cluster name:        `your-aks-cluster`
- Resource group:      `your-resource-group`
- Region:              `eastus`
- Node pool name:      `default`
- Kubernetes version:  `1.29`
- Default namespace:   `default`

## Elastic

- Cluster endpoint:    see `config/integrations/elastic.yaml`
- Log index pattern:   `logs-*`
- Metrics index pattern: `metrics-*`
- Application logs field for service name: `service.name`
- Timestamp field:     `@timestamp`

## Azure API Management (APIM)

- APIM name:           `your-apim-instance`
- Log Analytics workspace: see `config/integrations/log_analytics.yaml`
- Primary gateway log table: `ApiManagementGatewayLogs`

## Monitored Services

List key services here so the investigation engine can recognise them:

| Service Name       | Technology    | Namespace   | AKS Deployment         |
|--------------------|---------------|-------------|------------------------|
| order-service      | Spring Boot   | default     | order-service          |
| payment-service    | Spring Boot   | default     | payment-service        |

## Alert Routing

- Azure Action Groups forward to: `POST /triggers/azure-alert`
- Manual trigger endpoint: `POST /triggers/manual`

## Known Constraints

- V1 does not execute fixes. All FixStrategyOutput actions require human review.
- Confidence threshold before surfacing RCA: `medium` (see `config/policies/investigation.yaml`)
