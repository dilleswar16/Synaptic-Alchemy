# Corvin Integration Config Blueprint

## Goal

Every major external system should have its own dedicated configuration file so it can be replaced without touching core logic.

## Recommended Integration Files

```text
config/integrations/
|- azure-alerts.yaml
|- elastic.yaml
|- log-analytics.yaml
|- aks.yaml
|- teams.yaml
|- postgres.yaml
```

## Example Integration Shape

```yaml
enabled: true
name: elastic
endpoint: ${ELASTIC_URL}
timeout_seconds: 30
indexes:
  logs: app-logs-*
  metrics: app-metrics-*
features:
  logs: true
  metrics: true
```

## Azure Alerts File

Should contain:

- webhook bindings,
- Action Group expectations,
- payload normalization settings,
- severity mapping rules.

## Elastic File

Should contain:

- cluster endpoint,
- index patterns,
- query defaults,
- timeout and pagination defaults.

## Log Analytics File

Should contain:

- workspace identifiers,
- query defaults,
- APIM query templates if helpful,
- timeout and result-size defaults.

## Teams File

Should contain:

- bot or integration mode,
- channel or tenant references,
- messaging configuration,
- feature toggles for notifications, commands, and approval interactions.

## AKS File

Should contain:

- cluster target references,
- namespace defaults if any,
- rollout and workload query settings,
- timeout and safety defaults.

## Rule

If an integration can be removed or replaced later, its settings should be isolated in one place.