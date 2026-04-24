# Corvin Workspace Instructions

This workspace defines Corvin, an Azure-native investigation platform for a personal project. Treat this as a fresh product build, not a direct fork of Vishwakarma.

## Product Direction

- Build the control plane in Python.
- Build the web app in React with Vite.
- Use Postgres for persistence.
- Target Azure alerts, AKS, Elastic, Azure Log Analytics, REST API, CLI, web app, and Teams.
- The monitored applications may be Java Spring Boot, but the investigation platform itself is Python.

## Workflow Contract

The target workflow is:

Trigger -> Enrich -> Investigate -> RCA -> Fix Strategy -> Human Approval -> Execute Fix -> Verify -> Learn

For V1, stop at RCA plus Fix Strategy. Do not implement autonomous execution in V1.

## Delivery Rules

- Work version by version: V1 first, then V2, then V3.
- Within each version, build testable slices instead of one large end-to-end flow.
- Keep `progress.md` updated whenever a major doc set, prompt, or implementation slice is completed.

## Architecture Rules

- Keep triggers, evidence sources, investigation engine, approval flow, execution flow, and delivery surfaces as separate modules.
- Use adapter-style boundaries for integrations.
- Keep configuration externalized and replaceable.
- Do not hardcode environment URLs, tool endpoints, or secrets inside core logic.

## Configuration Rules

- Place replaceable settings in dedicated folders and files by concern.
- Separate model config, integration config, tool config, policy config, and environment overrides.
- Prefer references and placeholders for secrets.

## Context Usage

- Use `progress.md` as the first resumption file.
- Use `docs/copilot-context/shared/` for A-to-Z product context.
- Use `docs/copilot-context/versions/` for version scope and sequencing.
- Use `docs/copilot-context/config-blueprints/` for configuration layout decisions.

## Technology Constraints

- Azure, not AWS.
- Elastic is the primary store for logs and application or AKS metrics.
- Log Analytics is the primary source for APIM evidence.
- Azure alerts are the primary automation trigger source.
- No authentication is required for V1, but the system should leave room for future auth.