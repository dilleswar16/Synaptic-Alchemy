# Corvin Configuration Layout

## Goal

Corvin configuration should be replaceable from dedicated folders instead of being scattered through application code.

## Target Layout

```text
config/
|- models/
|- integrations/
|- tools/
|- policies/
|- environments/
```

## Folder Purpose

| Folder | Purpose |
|---|---|
| `models/` | LLM provider, model IDs, fallback chains, output modes |
| `integrations/` | Elastic, Log Analytics, Azure alerts, Teams, AKS, and future integrations |
| `tools/` | tool catalogs, enablement, timeouts, query defaults |
| `policies/` | approval rules, execution rules, safety levels, risk categories |
| `environments/` | local, dev, test, or personal environment overlays |

## Load Order Recommendation

1. base config by concern
2. environment overlay
3. secret references or environment-variable binding
4. runtime feature flags if needed

## Design Rules

- Do not create one giant `config.yaml` that contains everything forever.
- Keep each major integration in its own file.
- Keep execution policy separate from integration definitions.
- Keep model settings separate from tool settings.
- Validate the merged configuration at startup.