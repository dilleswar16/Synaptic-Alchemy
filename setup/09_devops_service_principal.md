# 09 — DevOps Request: Service Principal for Corvin (Hackathon Project)

**To:** DevOps / Azure Platform Team  
**From:** [Your Name]  
**Re:** App Registration + Role Assignments needed for Corvin hackathon project

---

## Context

I am building **Corvin**, an AKS investigation tool, as part of the MetLife hackathon.
The application is deployed in the **MetLifeSandBoxEnv** tenant (sandbox).

It needs read-only access to these resources in the **MetLife org tenant**:
- Azure Log Analytics workspace (to query container logs, AKS events, APIM logs)
- AKS cluster (to read pod status and deployment state)

No write access is required. No production changes will be made.
All actions are read-only evidence gathering for an AI-based root cause analysis tool.

---

## What I need you to do (3 steps)

---

### Step 1 — Create an App Registration in the MetLife tenant

1. Go to **Azure Portal → Entra ID → App registrations → New registration**
2. Fill in:
   - **Name:** `corvin-hackathon-sp`
   - **Supported account types:** Accounts in this organizational directory only (single tenant)
   - **Redirect URI:** leave blank
3. Click **Register**
4. On the app registration overview page, note down:
   - **Application (client) ID** — share this with me
   - **Directory (tenant) ID** — share this with me (should be `ca56a4a5-e300-406a-98ff-7e36a0baac5b`)

---

### Step 2 — Create a client secret

1. Still on the app registration → **Certificates & secrets → Client secrets → New client secret**
2. Description: `corvin-hackathon`
3. Expires: **12 months**
4. Click **Add**
5. **Copy the Value immediately** (it is only shown once) — share this with me securely

---

### Step 3 — Grant role assignments (read-only)

#### 3a — Log Analytics workspace

The workspace name is: **LogAnalytics-AUCHAD-DV01** (or whichever workspace has the `ContainerLog`, `KubePodInventory`, and `KubeEvents` tables)

1. Portal → **Log Analytics workspaces → [workspace name] → Access control (IAM)**
2. Click **Add → Add role assignment**
3. Role: **Log Analytics Reader**
4. Assign access to: **User, group, or service principal**
5. Select: search for `corvin-hackathon-sp` → select it
6. Click **Review + assign**

#### 3b — AKS cluster (two roles needed)

The cluster is: **azaustaekub14470dv0101** in resource group **RG_14470_AUCHAD_DV01**

**Role 1:**
1. Portal → **Kubernetes services → azaustaekub14470dv0101 → Access control (IAM)**
2. Click **Add → Add role assignment**
3. Role: **Azure Kubernetes Service Cluster User Role**
4. Assign to: `corvin-hackathon-sp`
5. Click **Review + assign**

**Role 2:**
1. Same IAM blade → **Add → Add role assignment**
2. Role: **Azure Kubernetes Service RBAC Reader**
3. Assign to: `corvin-hackathon-sp`
4. Click **Review + assign**

---

## What I will do with these credentials

I will add them as environment variables in my App Service (in the sandbox tenant):

| Variable | Value |
|---|---|
| `AZURE_TENANT_ID` | Directory (tenant) ID from Step 1 |
| `AZURE_CLIENT_ID` | Application (client) ID from Step 1 |
| `AZURE_CLIENT_SECRET` | Secret value from Step 2 |

These are stored as encrypted App Service Application Settings — not in code or config files.

---

## Security notes

- The service principal has **read-only** access only
- `Log Analytics Reader` — can query logs, cannot modify workspace or alerts
- `AKS Cluster User Role` — can get kubeconfig credentials, cannot modify workloads
- `AKS RBAC Reader` — can read pods/deployments/events in namespace, cannot exec, delete, or modify
- No Key Vault, Storage, or subscription-level access is requested
- The secret expires in 12 months and can be revoked at any time via the app registration

---

## Questions?

Ping me on Teams or raise a ticket. Happy to jump on a call to walk through this together.
