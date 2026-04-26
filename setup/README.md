# Corvin Setup Guides

Work through these in order. Each guide tells you exactly what to create in Azure,
what values to copy, and where to put them.

| # | Guide | What it covers |
|---|-------|----------------|
| 1 | [01_azure_openai.md](01_azure_openai.md) | Azure AI Foundry setup, deploy gpt-4.1, get API key |
| 2 | [02_log_analytics.md](02_log_analytics.md) | Create Log Analytics workspace, create service principal, grant access |
| 3 | [03_elastic.md](03_elastic.md) | Point Corvin at your existing Elastic cluster (Elastic Cloud or self-hosted) |
| 4 | [04_env_file.md](04_env_file.md) | Fill in your `.env` file with all collected values and start the app |
| 5 | [05_aks.md](05_aks.md) | Connect Corvin to your AKS cluster, verify kubeconfig, update site.md |
| 6 | [06_database_migrations.md](06_database_migrations.md) | How to use Alembic to update Postgres schemas |

## Prerequisites

- Azure CLI installed: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli
- Docker Desktop running (for local Postgres)
- Python venv activated: `.venv\Scripts\Activate.ps1`

## Quick check — are you logged in to Azure?

```powershell
az login
az account show
```

If the wrong subscription is shown:
```powershell
az account set --subscription "Your Subscription Name"
```
