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
For V1.5, wire all adapters to real Azure cloud services and validate end-to-end with no mocks.
For V2, implement Two-Way ChatOps targeting Teams, Human-in-the-Loop Execution (Approve & Execute via AKSAdapter), and Streaming RCA via SSE.
For V2.5, implement AI intelligence features: Incident Memory, Morning Briefing (Jarvis Mode), and Confidence Meter.
For V3, implement the Premium React UI overhaul, Blameless Post-Mortem auto-generator, and Corvin Score health dashboard.
For V3.5, implement the hackathon demo core: Alert Simulator, Teams Adaptive Cards with inline approve, Blast Radius Estimator, Corvin Score Gauge.
For V3.7, implement intelligence layer: Predictive Detection, SLA Countdown, Cross-Service Dependency Visualizer, Remediation Preview.
For V3.9, implement enterprise polish: Voice Morning Briefing, ROI Dashboard, 3AM Mode, Runbook Auto-Update, War Room Channel, Confidence Routing.
For V4, implement Semantic Search / Vector RAG using pgvector on Azure Postgres.

## Delivery Rules

- Work version by version: V1 → V1.5 → V2 → V2.5 → V3 → V3.5 → V3.7 → V3.9 → V4.
- Do NOT start a new version until the previous version's exit criteria are fully met.
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