# Managed Identity Onboarding for Azure Deployment

This document is only about managed identity onboarding when Corvin is deployed to Azure and must access onboarded connectors (Log Analytics, AKS-related evidence) that may be in the same tenant but different subscriptions.

## 1) Short answer first

Yes, this works across subscriptions in the same tenant.

Managed identity is not enough by itself. You must grant RBAC on each target resource scope where Corvin reads data.

## 2) Identity model used by Corvin

Corvin evidence adapters use Azure DefaultAzureCredential for Log Analytics and Container Insights queries.

Implication:
- In Azure hosting, DefaultAzureCredential will use the managed identity of the host when configured.
- If no managed identity is enabled, authentication will fail.
- If identity exists but RBAC is missing on a target workspace/subscription/resource group, data queries will fail.

## 3) What must be configured at deployment time

### A. Enable managed identity on hosting resource

If hosting in Azure App Service:
- Enable System Assigned Managed Identity (or attach a User Assigned identity).

If hosting in AKS:
- Use workload identity or pod-managed identity pattern and bind the app workload to the identity.

### B. Grant RBAC on every connector target

For each onboarded application connector, grant the Corvin identity access on the exact resource scope used by that connector.

Typical minimum scopes:
- Log Analytics workspace used by apim_logs connector role: workspace-level read/query permissions.
- Log Analytics workspace used by container_insights connector role: workspace-level read/query permissions.
- Any additional resource lookups used by your adapter flow: Reader at resource group or resource scope if needed.

Important:
- Different subscriptions are fine.
- The same identity can be granted RBAC in multiple subscriptions within the same tenant.

### C. User Assigned identity note

If using User Assigned identity, set AZURE_CLIENT_ID in the app settings so DefaultAzureCredential chooses that identity.

## 4) AKS caveat for live topology

Current AKS live topology adapter uses Kubernetes client config (kubeconfig or in-cluster config), not ARM token exchange for AKS API.

What this means:
- Managed identity covers Azure Monitor / Log Analytics query auth.
- For live Kubernetes API reads, you still need a valid Kubernetes auth path:
  - In-cluster config when Corvin runs inside AKS, or
  - kubeconfig available to the running service plus network access to AKS API.

If Corvin is hosted in App Service and not in AKS, plan the Kubernetes auth path explicitly.

## 5) Connector onboarding checklist (managed identity path)

1. Enable managed identity on Corvin host.
2. Grant RBAC on each target workspace/resource scope for every onboarded connector.
3. In Applications UI, create application, services, and connector records.
4. Set connector role correctly:
   - apim_logs for APIM evidence workspace
   - container_insights for AKS/container workspace
5. Run connector test from UI.
6. Validate:
   - app-scoped topology endpoints return only that app services
   - live metrics appear for registered services
   - one investigation run returns APIM and container evidence

## 6) Failure patterns and quick diagnosis

If APIM logs are empty:
- Check connector workspace id and role.
- Check identity RBAC on APIM Log Analytics workspace.

If container insights metrics are empty:
- Check connector workspace id, cluster_name, default_namespace.
- Check identity RBAC on container workspace.

If live topology pod status is unknown but logs work:
- Likely Kubernetes auth/config issue for AKS API (not Log Analytics auth issue).

## 7) Recommended standard for managed clients

Use one Corvin managed identity per environment (dev, uat, prod), and grant least-privilege RBAC per client resource scope.

Do not share broad subscription-wide Owner/Contributor permissions.

Prefer explicit workspace/resource scopes and keep connector config fully DB-driven per application.
