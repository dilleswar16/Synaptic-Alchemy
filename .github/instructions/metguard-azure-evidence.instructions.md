---
description: "Use when implementing Azure triggers, Azure evidence gathering, Elastic search and metrics access, Log Analytics queries, AKS context collection, APIM investigation, or Azure-specific observability integrations for Corvin."
name: "Corvin Azure Evidence"
---
# Corvin Azure Evidence Guidance

- Assume Azure as the cloud platform.
- Do not design around AWS-specific tools, alert shapes, or terminology.
- Treat Azure alerts as the primary automation trigger source.
- Treat Elastic as the primary log store and application or AKS metrics source.
- Treat Azure Log Analytics and Kusto as the primary APIM evidence source.

## Evidence Priorities

- Azure alert payload context
- Elastic logs
- Elastic-backed application and AKS metrics
- Log Analytics queries for APIM
- AKS workload state and rollout context
- Azure Activity Log and change events

## Trigger Priorities

- Azure Monitor alerts
- Action Groups
- Event Grid or webhook-driven ingestion
- Teams or API manual trigger as fallback

## Evidence Rules

- Normalize evidence into structured, comparable shapes before passing it into RCA generation.
- Keep Azure-specific query logic behind adapters.
- Always leave room for change-correlation data such as deploys, config updates, and rollouts.