# Setup Guide 2 — Azure Log Analytics

Corvin queries Log Analytics for APIM gateway evidence (5xx errors, latency,
throttling) using a service principal with read-only access.

The four values you need at the end:
- `LOG_ANALYTICS_WORKSPACE_ID`
- `AZURE_CLIENT_ID`
- `AZURE_CLIENT_SECRET`
- `AZURE_TENANT_ID`

---

## Step 1 — Find or create a Log Analytics workspace

### If you already have one
```powershell
# List all workspaces in your subscription
az monitor log-analytics workspace list --output table
```
Note the **customerId** column — that is your `LOG_ANALYTICS_WORKSPACE_ID`.

### If you need to create one
```powershell
az monitor log-analytics workspace create `
  --resource-group rg-corvin `
  --workspace-name corvin-logs `
  --location eastus
```

Then get the workspace ID:
```powershell
az monitor log-analytics workspace show `
  --resource-group rg-corvin `
  --workspace-name corvin-logs `
  --query customerId `
  --output tsv
```
Copy this value → `LOG_ANALYTICS_WORKSPACE_ID`

---

## Step 2 — Get your Tenant ID

```powershell
az account show --query tenantId --output tsv
```
Copy this value → `AZURE_TENANT_ID`

---

## Step 3 — Create a service principal

Corvin needs a service principal (app registration) to authenticate against
the Log Analytics API. It only needs read access — never write.

```powershell
az ad sp create-for-rbac `
  --name corvin-reader `
  --role "Log Analytics Reader" `
  --scopes /subscriptions/<your-subscription-id>/resourceGroups/<your-rg>
```

The output looks like:
```json
{
  "appId":       "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "displayName": "corvin-reader",
  "password":    "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "tenant":      "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

- `appId`    → `AZURE_CLIENT_ID`
- `password` → `AZURE_CLIENT_SECRET`  ← save this now, it is shown only once
- `tenant`   → `AZURE_TENANT_ID` (same as Step 2)

---

## Step 4 — Grant the service principal access to the workspace

The role assignment in Step 3 covers the resource group, but you also need to
explicitly grant access to the workspace itself for query API calls:

```powershell
# Get the workspace resource ID
$workspaceId = az monitor log-analytics workspace show `
  --resource-group rg-corvin `
  --workspace-name corvin-logs `
  --query id --output tsv

# Assign Log Analytics Reader to the service principal on the workspace
az role assignment create `
  --assignee <appId from Step 3> `
  --role "Log Analytics Reader" `
  --scope $workspaceId
```

---

## Step 5 — Connect your Java app to Log Analytics (if not already done)

For Corvin to query your Java app logs, those logs must flow into Log Analytics.
The standard path is:

```
Java app (Spring Boot)
    → Logback / Log4j2 appender
    → Azure Monitor OpenTelemetry exporter  (or Filebeat → Elastic — see guide 3)
    → Log Analytics workspace
```

Easiest option — add the Azure Monitor agent to your AKS node pool:
```powershell
az aks enable-addons `
  --resource-group <your-aks-rg> `
  --name <your-aks-cluster> `
  --addons monitoring `
  --workspace-resource-id $workspaceId
```

This automatically collects stdout/stderr from all containers (including your
Java apps) into the `ContainerLog` table in Log Analytics.

---

## Step 6 — Verify queries work

In the Azure Portal → your Log Analytics workspace → **Logs**, run:

```kql
ContainerLog
| where TimeGenerated > ago(1h)
| where LogEntry contains "ERROR"
| project TimeGenerated, ContainerName, LogEntry
| limit 20
```

If you see your Java app errors here, Corvin can query them.

---

## Values to add to `.env`

```env
LOG_ANALYTICS_WORKSPACE_ID=<customerId from Step 1>
AZURE_CLIENT_ID=<appId from Step 3>
AZURE_CLIENT_SECRET=<password from Step 3>
AZURE_TENANT_ID=<tenant from Step 2>
```

See [04_env_file.md](04_env_file.md) for the complete `.env` template.
