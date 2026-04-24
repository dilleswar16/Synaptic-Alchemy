# Corvin Environment And Secrets Strategy

## Goal

Environment-specific differences should be handled through overlays and secret references, not source edits.

## Recommended Environment Layout

```text
config/environments/
|- local.yaml
|- personal.yaml
|- test.yaml
|- future-prod.yaml
```

## Environment File Purpose

- select active integrations,
- override endpoints,
- override workspace IDs,
- switch delivery surfaces,
- adjust feature flags.

## Secrets Rule

- Store secret references outside committed config where possible.
- Prefer environment variables, secret stores, or local secret files excluded from version control.
- Do not place API keys, tokens, or passwords directly in blueprint examples.

## V1 Auth Position

- V1 may run without auth or with a simple internal mode.
- The environment strategy should not block future auth.
- Future versions can add auth config without changing the core folder model.

## Example Overlay Pattern

```yaml
environment: personal
features:
  teams: true
  web_app: true
  execution: false
integrations:
  elastic_profile: default
  log_analytics_profile: default
```

## Rule

Operators should be able to change environment behavior by editing dedicated environment overlays, not by patching business logic.