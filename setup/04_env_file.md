# Setup Guide 4 — Fill in your .env and start Corvin

Once you have collected all values from guides 1–3, fill in your `.env` file
and start the application.

---

## Step 1 — Copy the example file

```powershell
Copy-Item .env.example .env
```

---

## Step 2 — Fill in every value

Open `.env` and replace every `placeholder` with the real value.
Full reference:

```env
# ── Runtime environment ──────────────────────────────────────────────────────
# Use "local" for development. Controls which config/environments/ overlay loads.
CORVIN_ENV=local

# ── Postgres ─────────────────────────────────────────────────────────────────
# Update these values to match your Azure Database for PostgreSQL Flexible Server credentials.
CORVIN_DB_HOST=<your-server>.postgres.database.azure.com
CORVIN_DB_PORT=5432
CORVIN_DB_NAME=corvin
CORVIN_DB_USER=<your-admin-user>
CORVIN_DB_PASSWORD=<your-admin-password>

# ── Azure OpenAI (from guide 01_azure_openai.md) ─────────────────────────────
AZURE_OPENAI_API_KEY=<Key 1 from Azure OpenAI resource → Keys and Endpoint>
AZURE_OPENAI_API_BASE=https://<your-resource-name>.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-01

# ── Elastic (from guide 03_elastic.md) ───────────────────────────────────────
ELASTIC_HOST=https://<your-cluster>:9243
ELASTIC_API_KEY=<encoded API key>

# ── Azure Log Analytics (from guide 02_log_analytics.md) ─────────────────────
LOG_ANALYTICS_WORKSPACE_ID=<customerId from workspace>
AZURE_CLIENT_ID=<appId of corvin-reader service principal>
AZURE_CLIENT_SECRET=<password of corvin-reader service principal>
AZURE_TENANT_ID=<your tenant ID>

# ── Azure subscription ───────────────────────────────────────────────────────
# Used by the Azure Activity Log adapter (infrastructure change detection).
AZURE_SUBSCRIPTION_ID=<your subscription ID>
```

Get your subscription ID:
```powershell
az account show --query id --output tsv
```

---

## Step 3 — Ensure Postgres is accessible

*If you are using Azure Database for PostgreSQL:*
Ensure your IP address is whitelisted in the Azure Portal (Networking -> Allow public access / add client IP). You do not need to run Docker.

*If you are using Local Postgres:*
```powershell
docker-compose up -d
```

---

## Step 4 — Run database migrations

```powershell
alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, create initial tables
```

---

## Step 5 — Start the API

```powershell
uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000
```

Check it's healthy:
```powershell
curl http://localhost:8000/health
# {"status":"ok"}
```

---

## Step 6 — Start the CLI (in a new terminal)

```powershell
.venv\Scripts\Activate.ps1
corvin
```

You should see the banner and:
```
  ✓ API is reachable — status: ok
corvin›
```

---

## Step 7 — Run your first investigation

```
corvin› investigate order-service production
```

Corvin will:
1. Query Elastic for `order-service` logs in the last 30 minutes
2. Send those logs to Azure OpenAI gpt-4o
3. Return a structured RCA with confidence level + fix strategy

---

## Troubleshooting

| Symptom | Check |
|---|---|
| `Cannot connect to Corvin API` | Is uvicorn running? Port 8000 free? |
| `API returned 500` on investigate | Check uvicorn terminal for the Python traceback |
| `AuthenticationError` from LiteLLM | `AZURE_OPENAI_API_KEY` or `AZURE_OPENAI_API_BASE` wrong |
| Empty `elastic_logs` in result | Check `ELASTIC_HOST` reachable, index pattern matches |
| `alembic upgrade head` fails | Is Postgres running? Are DB credentials correct? |
| `corvin` not recognized | Is the venv activated? Run `.venv\Scripts\Activate.ps1` first |
