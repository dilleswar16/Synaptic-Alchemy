# Corvin Modularity And Configurability

## Goal

Corvin should be easy to reconfigure without digging through core source code. Any part likely to change later should live behind a replaceable module or config layer.

## Modularity Principles

1. One responsibility per module.
2. One integration per adapter family.
3. One surface per delivery module.
4. One policy layer for approvals and execution.
5. One configuration area per concern.

## Modules That Must Stay Separate

- trigger adapters
- enrichment services
- investigation engine
- RCA formatter
- fix strategy generator
- approval service
- execution service
- verification service
- learning service
- delivery channel adapters
- config loader and validation

## Configurability Principles

- URLs, workspace IDs, index names, model IDs, and feature flags should not be buried in code.
- Integrations should be switchable through config.
- Tools should be enableable or disableable through config.
- Execution capability should be policy-driven.

## Configuration Areas

The target repo should use dedicated folders such as:

- `config/models/`
- `config/integrations/`
- `config/tools/`
- `config/policies/`
- `config/environments/`

Examples:

- Elastic URL and index patterns in one integration file.
- Log Analytics workspace and query settings in another.
- Teams delivery config in another.
- execution permissions in policy files.

## Replaceability Requirement

If a user wants to replace:

- an endpoint,
- a workspace binding,
- an index pattern,
- a tool behavior,
- a model,
- or an approval policy,

they should be able to do it in a dedicated folder or file without searching through core logic.

## Target Behavior

Corvin should feel configurable at the edges and stable at the core.

- Core logic should operate on typed contracts.
- Edge adapters should map configuration into those contracts.
- Policy files should govern behavior changes, not hardcoded `if` branches scattered across the codebase.