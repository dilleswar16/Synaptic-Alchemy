# 08 — Azure Deployment Guide (App Service + Static Web Apps)

This guide deploys Corvin to Azure using the Azure Portal only — no Docker, no CLI required.
You need your Azure Repo already connected to your Azure DevOps project.

---

## What you will deploy

| Component | Azure Resource | Tier |
|---|---|---|
| Python API (FastAPI) | App Service (Linux, Python 3.13) | B1 or higher |
| React UI (Vite) | Static Web Apps | Free |

---

## Part 1 — Deploy the Python API to App Service

### Step 1 — Create the App Service

1. Portal → **Create a resource** → search **Web App**
2. Fill the form:
   - **Subscription**: your subscription
   - **Resource Group**: `corvin-rg` (or your existing RG)
   - **Name**: `corvin-api` (must be globally unique — becomes `corvin-api.azurewebsites.net`)
   - **Publish**: `Code`
   - **Runtime stack**: `Python 3.13`
   - **OS**: `Linux`
   - **Region**: same as your other resources (e.g. `Australia East`)
   - **Pricing plan**: B1 (Basic) minimum — Free tier does not support always-on or custom startup commands
3. Click **Review + create → Create**

### Step 2 — Set the startup command

1. App Service → **Configuration → General settings**
2. In **Startup Command** enter: `startup.sh`
3. Click **Save**

### Step 3 — Add environment variables

1. App Service → **Configuration → Application settings → + New application setting**
2. Add every variable from your `.env` file — one by one:

| Key | Value |
|---|---|
| `LITELLM_ENDPOINT` | your Azure OpenAI endpoint |
| `LITELLM_API_KEY` | your Azure OpenAI key |
| `AZURE_API_VERSION` | `2025-01-01-preview` |
| `CORVIN_DB_HOST` | your Postgres host |
| `CORVIN_DB_USER` | your Postgres user |
| `CORVIN_DB_PASSWORD` | your Postgres password |
| `CORVIN_DB_NAME` | `corvin` |
| `AZURE_CLIENT_ID` | service principal client ID |
| `AZURE_CLIENT_SECRET` | service principal secret |
| `AZURE_TENANT_ID` | your tenant ID |
| `LOG_ANALYTICS_WORKSPACE_ID` | your Log Analytics workspace ID |
| `AKS_RESOURCE_GROUP` | your AKS resource group |
| `AKS_CLUSTER_NAME` | your AKS cluster name |
| `TEAMS_APP_ID` | (set after bot registration) |
| `TEAMS_APP_PASSWORD` | (set after bot registration) |

3. Click **Save → Continue**

### Step 4 — Connect to Azure Repo and deploy

1. App Service → **Deployment Center**
2. **Source**: `Azure Repos`
3. **Organization**: your Azure DevOps org
4. **Project**: your project
5. **Repository**: `MetGuard` (or your repo name)
6. **Branch**: `main`
7. **Build provider**: `App Service Build Service` (Oryx — detects Python automatically)
8. Click **Save**

App Service will pull the code, install `requirements.txt`, and run `startup.sh` automatically.

### Step 5 — Verify the API is live

Open: `https://corvin-api.azurewebsites.net/docs`

You should see the FastAPI Swagger UI. If you see a 500, check:
- App Service → **Log stream** for startup errors
- All environment variables are set correctly

---

## Part 2 — Deploy the React UI to Static Web Apps

### Step 1 — Create the Static Web App

1. Portal → **Create a resource** → search **Static Web App**
2. Fill the form:
   - **Resource Group**: `corvin-rg`
   - **Name**: `corvin-ui`
   - **Hosting plan**: Free
   - **Region**: `East Asia` or `East US 2` (closest with free tier)
   - **Source**: `Azure DevOps`
   - **Organization / Project / Repository / Branch**: same as above
   - **Build presets**: `React`
   - **App location**: `apps/web`
   - **Output location**: `dist`
3. Click **Review + create → Create**

Static Web Apps automatically sets up a build pipeline in Azure DevOps and deploys on every push to `main`.

### Step 2 — Point the UI at the real API

1. Open `apps/web/staticwebapp.config.json`
2. Replace both `<CORVIN_API_URL>` placeholders with your actual App Service URL:
   ```
   https://corvin-api.azurewebsites.net
   ```
3. Commit and push — Static Web Apps redeploys automatically.

### Step 3 — Verify the UI is live

Open the URL shown on the Static Web App resource overview page (e.g. `https://corvin-ui.azurestaticapps.net`).

---

## Part 3 — Azure Bot + Web Chat (replaces Teams for orgs with custom app restrictions)

### Step 1 — Create the Azure Bot

1. Portal → **Create a resource** → search **Azure Bot**
2. Fill the form:
   - **Bot handle**: `corvin-bot`
   - **Resource Group**: `corvin-rg`
   - **Pricing tier**: F0 (free)
   - **Microsoft App ID**: `Create new Microsoft App ID`
3. Click **Review + create → Create**

### Step 2 — Get App ID and create a secret

1. Bot resource → **Configuration** → copy **Microsoft App ID** — this is `TEAMS_APP_ID`
2. Click the App ID link → opens Entra ID App Registration
3. **Certificates & secrets → New client secret** → 24 months → **Add**
4. Copy the **Value** immediately — this is `TEAMS_APP_PASSWORD`
5. Go back to App Service → Configuration → add both values → Save

### Step 3 — Set the messaging endpoint

1. Bot resource → **Configuration**
2. Set **Messaging endpoint**: `https://corvin-api.azurewebsites.net/teams/messages`
3. Click **Apply**

### Step 4 — Enable the bot in Corvin config

Open `config/integrations/teams.yaml` and set:
```yaml
bot_enabled: true
```

Commit and push — App Service redeploys and the bot is live.

### Step 5 — Test via Web Chat (no Teams required)

1. Bot resource → **Test in Web Chat** (left sidebar)
2. Type: `investigate fundsso dev`
3. Expected: Corvin replies with an RCA Adaptive Card

This works entirely inside the Azure Portal — no Teams channel, no org app policy needed.

### Step 6 — Enable Teams channel (optional, when org allows)

1. Bot resource → **Channels → Microsoft Teams → Apply**
2. In Teams: search for `corvin-bot` → **Add to a team** → pick your channel
3. Type: `@Corvin investigate fundsso dev`

---

## Troubleshooting

| Symptom | Check |
|---|---|
| App Service 500 on startup | Log stream → missing env var or alembic migration failed |
| Bot returns "Bot is not reachable" | Messaging endpoint URL wrong or App Service not running |
| Static Web App 404 on refresh | `staticwebapp.config.json` navigationFallback not committed |
| Bot messages not arriving | `TEAMS_APP_ID` / `TEAMS_APP_PASSWORD` mismatch |
| `bot_enabled: false` returns 501 | Flip to `true` in config and redeploy |
