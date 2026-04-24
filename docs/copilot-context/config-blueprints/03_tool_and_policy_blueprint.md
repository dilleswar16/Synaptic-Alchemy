# Corvin Tool And Policy Blueprint

## Goal

Tools and execution policy should be configurable and version-aware.

## Recommended Layout

```text
config/tools/
|- investigation-tools.yaml
|- enrichment-tools.yaml
|- delivery-tools.yaml

config/policies/
|- approval-policy.yaml
|- execution-policy.yaml
|- verification-policy.yaml
```

## Tool Config Should Control

- whether a tool family is enabled,
- default timeouts,
- adapter binding,
- default query behavior,
- feature flags for version-specific behavior.

## Policy Config Should Control

- whether execution is enabled at all,
- what categories always require approval,
- what actions are disallowed,
- what verification is mandatory,
- what rollback hints or safeguards apply.

## Example Approval Policy Shape

```yaml
execution_enabled: false
require_human_approval: true
risk_levels:
  low:
    approval_required: true
  medium:
    approval_required: true
  high:
    approval_required: true
disallowed_actions:
  - destructive-delete
  - irreversible-config-change
```

## Rule

The model should not be the only guardrail. Policy files must enforce execution boundaries explicitly.