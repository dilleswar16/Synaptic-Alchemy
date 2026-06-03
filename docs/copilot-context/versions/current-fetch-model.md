# Current Fetch Model

Date: 2026-06-03

## 1) AKS Pod/Context Fetch
File: `corvin/evidence/aks_adapter.py`

- Uses Kubernetes Python client.
- Supports two runtime auth modes:
  - Local kubeconfig (`kube_config_path`)
  - In-cluster auth (`in_cluster=true`)
- Includes best-effort `kubectl` fallback for some local/dev discovery paths.
- Runtime config is DB-first via connector resolution.

## 2) Container Logs and Metrics (Container Insights)
File: `corvin/evidence/container_logs_adapter.py`

- Uses Azure Monitor Logs API via `LogsQueryClient`.
- Auth uses `DefaultAzureCredential`.
- Workspace is resolved from DB connector with role `container_insights`.

## 3) APIM Analytics
File: `corvin/evidence/apim_analytics_adapter.py`

- Uses Azure Monitor Logs API via `LogsQueryClient`.
- Auth uses `DefaultAzureCredential`.
- Workspace/table are resolved from DB connector role `apim_logs`.
- No hardcoded workspace IDs in runtime query path.

## 4) DB-Driven Connector Resolution
File: `corvin/connectors/config_resolver.py`

- DB-first connector lookup by service/application and role.
- Falls back to provided config only when no matching connector exists.
- Primary roles used:
  - `apim_logs`
  - `container_insights`
  - `azure_activity`

## 5) Onboarding API Surface
File: `apps/api/routes/applications.py`

- Connector create/update APIs validate `connector_role` and required fields.
- `azure_monitor` connectors require `workspace_id`.
- APIM role defaults table to `ApiManagementGatewayLogs` unless overridden.

## 6) Is It Using az login Directly?

- Not directly in code.
- Code uses `DefaultAzureCredential`.
- If running locally, `DefaultAzureCredential` can use `AzureCliCredential` under the hood, which relies on `az login` token.
- In deployed environments, it should use Managed Identity/Workload Identity (preferred), not interactive `az login`.

## 7) For Sellable/Customer-Friendly Deployment (Recommended Target)

1. Use Managed Identity (or Workload Identity) for API service.
2. Grant that identity Log Analytics read rights for customer workspaces.
3. Keep connector metadata in DB (`workspace_id`, role, table, cluster settings) via onboarding UI/API.
4. For AKS access:
- Best for production: in-cluster service account RBAC if Corvin runs in same cluster.
- Multi-cluster SaaS: avoid filesystem kubeconfig dependency; use a standardized identity/RBAC approach per client cluster.
5. Keep all secrets/refs external (Key Vault/env refs), not embedded.

## 8) Short Answer to the Concern

- Yes, APIM/Container logs are API-based via Azure SDK and DB-driven connector config.
- AKS is currently kubeconfig/in-cluster based (with fallback behavior), not hardcoded.
- This is already close to productizable onboarding, and moving AKS auth to strict managed identity patterns is the main enterprise-hardening step.

## 9) Current Status

- APIM analytics runtime path is now DB-driven and generic.
- Error handling distinguishes real query/config/auth failures from true empty datasets.
- Existing intelligence slice tests remain passing after changes.

## 10) Managed Identity Impact: Do We Need Code Changes?

Short answer: for Log Analytics paths, usually no major code changes; for AKS, it depends on deployment topology.

### 10.1 Container Insights + APIM Analytics

- Current implementation already uses Azure SDK clients and `DefaultAzureCredential`:
  - `corvin/evidence/container_logs_adapter.py`
  - `corvin/evidence/log_analytics_adapter.py`
  - `corvin/evidence/apim_analytics_adapter.py`
- In cloud, `DefaultAzureCredential` will automatically use Managed Identity/Workload Identity when configured.
- Result: usually configuration + RBAC work, not application code changes.

### 10.2 AKS Context Access

- Current implementation in `corvin/evidence/aks_adapter.py` is kubeconfig / in-cluster based.
- If Corvin runs in the same cluster as target workloads, in-cluster RBAC can be sufficient with minimal code changes.
- For multi-cluster SaaS onboarding, avoid filesystem kubeconfig dependency and move toward standardized identity+RBAC federation patterns; this may require targeted AKS auth enhancements.

## 11) Deployment Checklist (No-Code-Change Path)

1. Enable Managed Identity (or Workload Identity) on the Corvin API host.
2. Grant Log Analytics read permissions for each customer workspace to that identity.
3. Ensure connector onboarding stores DB metadata correctly (`workspace_id`, `connector_role`, table names, cluster settings).
4. Keep secrets and references external (Key Vault / environment references), never embedded in source.
5. Validate with onboarding smoke tests:
   - APIM analytics query returns rows or explicit diagnostics.
   - Container Insights metrics query resolves workspace from DB connector.
   - AKS health path works for selected deployment mode.

## 12) Enterprise Hardening Backlog (Recommended)

- Add strict application-scoped connector resolution for all tool invocations to avoid cross-tenant ambiguity.
- Add AKS multi-cluster identity model (no kubeconfig file assumptions).
- Add connector onboarding validation endpoint for identity/RBAC preflight checks.
