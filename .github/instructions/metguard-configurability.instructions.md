---
description: "Use when creating config files, tool definitions, integration folders, URL settings, model settings, policy files, or environment overrides for Corvin. Covers the replaceable folder-based configuration model."
name: "Corvin Configurability"
---
# Corvin Configurability Guidance

- Corvin must keep mutable settings outside core logic.
- Any URL, endpoint, model choice, tool endpoint, integration credential reference, or policy that may change later should live in a dedicated configuration area.
- Prefer folders by concern over one giant config file.

## Required Config Separation

- `config/models/`
- `config/integrations/`
- `config/tools/`
- `config/policies/`
- `config/environments/`

## Rules

- Keep one file per major integration where practical.
- Keep one file per major tool family where practical.
- Prefer environment overlays instead of duplicating entire configs.
- Use placeholders or secret references, not inline secrets.
- Avoid requiring users to hunt through code to replace a URL or switch an integration.

## Implementation Preference

- Load config through typed models.
- Validate config at startup.
- Support feature toggles for channels, integrations, execution modes, and delivery surfaces.