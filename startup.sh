#!/bin/bash
# Azure App Service startup script for Corvin API

pip install -r requirements.txt --quiet

# Fetch AKS kubeconfig using managed identity (requires AZURE_SUBSCRIPTION_ID,
# AKS_RESOURCE_GROUP, AKS_CLUSTER_NAME in App Service Application Settings)
if [ -n "$AKS_CLUSTER_NAME" ] && [ -n "$AKS_RESOURCE_GROUP" ]; then
    az aks get-credentials \
        --resource-group "$AKS_RESOURCE_GROUP" \
        --name "$AKS_CLUSTER_NAME" \
        --overwrite-existing 2>/dev/null || echo "Warning: could not fetch AKS kubeconfig"
fi

# Run Alembic migrations on every startup so schema is always current
# (skip for SQLite — the app uses create_all() instead)
if [ "${DB_BACKEND:-postgres}" != "sqlite" ]; then
    python -m alembic upgrade head
fi

# Start the API
exec uvicorn apps.api.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 2
