# Corvin Architecture

## High-Level Shape

Corvin should be a modular control plane with one main investigation engine and several explicit adapter layers around it.

```text
Azure Alerts / Manual UI / API / CLI / Teams
                |
                v
         Trigger Adapter Layer
                |
                v
          Enrichment Services
                |
                v
       Investigation Orchestrator
                |
                v
        Investigation Engine Core
                |
      +---------+---------+
      |                   |
      v                   v
  Evidence Adapters   Strategy Layer
      |                   |
      v                   v
 Elastic / Kusto /    RCA / Fix Strategy
 AKS / Change Data        |
                          v
                 Approval / Execution / Verify
                          |
                          v
                    Delivery Surfaces
```

## Main Modules

## 1. Trigger Adapter Layer

Handles all incoming trigger shapes and normalizes them into a shared internal request contract.

Examples:

- Azure alert webhook
- Teams manual request
- REST API manual request
- CLI request
- web app action

## 2. Enrichment Services

Run deterministic, high-signal evidence collection before the deep investigation engine starts.

Examples:

- fetch recent Elastic evidence,
- fetch Log Analytics context,
- fetch AKS rollout state,
- fetch recent Azure Activity Log changes,
- fetch prior incidents and learned patterns.

## 3. Investigation Orchestrator

Owns the stage transitions.

It should decide when to:

- enrich first,
- invoke the investigation engine,
- produce RCA,
- produce fix strategy,
- request approval,
- execute,
- verify,
- learn.

## 4. Investigation Engine Core

This is the main reasoning loop.

It should stay custom and controllable, with:

- structured tool or adapter calls,
- controllable step budgets,
- evidence-aware prompting,
- explicit output contracts,
- strong guardrails.

This is intentionally closer to a custom orchestration layer than to a multi-agent framework.
The default assumption is one main investigation engine with structured surrounding stages, not a planner-agent and executor-agent graph from the start.

## 5. Evidence Adapters

These are the connectors to real evidence systems.

Initial targets:

- Elastic adapter
- Log Analytics adapter
- AKS adapter
- Azure alert adapter
- change-correlation adapter

## 6. Strategy Layer

Converts investigation results into structured outputs:

- RCA
- fix strategy
- later verification recommendations

This layer should remain separate from execution.

## 7. Approval Layer

This is where human control enters.

The approval layer should:

- present the fix strategy,
- justify the strategy,
- explain risks,
- wait for explicit approval before execution-enabled versions continue.

## 8. Execution And Verification Layer

Execution should exist only in later versions and only behind policy controls.

Verification should confirm whether the approved change actually resolved the incident.

## 9. Delivery Surfaces

These are the ways results return to operators:

- web app
- REST API
- CLI
- Teams

## 10. Toolset Registry

The investigation engine drives its reasoning through registered toolsets — the callable adapters the LLM can invoke during the investigation loop.

Each toolset must provide:
- `get_tools()` — returns a list of tool definitions (name, description, parameter schema) passed to the LLM
- `execute(tool_name, params)` — runs one tool call, returns a structured `ToolOutput`
- `check_prerequisites()` — validates connectivity and config before the investigation starts

All toolsets are registered in a central registry (equivalent of Vishwakarma's `@register_toolset` decorator).

Each toolset must be explicitly enabled in config (`config/tools/<name>.yaml: enabled: true`).
Disabled toolsets are NOT passed to the LLM — it never sees tools it cannot use.

V1 toolsets:
- `elastic` — query logs and metrics from Elasticsearch
- `log_analytics` — run Kusto queries against Azure Log Analytics
- `aks` — fetch pod state, events, replica state from AKS
- `azure_activity` — fetch recent changes from Azure Activity Log
- `http` — make outbound HTTP calls to internal services
- `knowledge` — reads `knowledge/site.md` and `knowledge/learnings/` content
- `runbooks` — keyword-matches alert name against `knowledge/runbooks/catalog.json`, returns runbook content

The runbook keyword catalog lives at `knowledge/runbooks/catalog.json` (equivalent of Vishwakarma's `plugins/agents/agents.json`):
```json
[
  {
    "id": "apim-5xx",
    "description": "Investigate APIM 5xx spike",
    "keywords": ["apim", "5xx", "gateway"],
    "runbook": "runbooks/apim-5xx.md"
  }
]
```

Matched runbook content is injected into the investigation engine system prompt. The engine is instructed that the runbook takes precedence over generic investigation phases.

## 11. Scheduler (V2+)

A background scheduler runs periodic operational reports.

V2 target: **Azure Cost Management daily report**
- Fetch 30-day spend from Azure Cost Management API, grouped by resource/service
- Compute baselines, week-over-week, anomaly detection
- LLM analysis of cost drivers → Teams card + optional PDF
- Scheduled daily (configurable UTC time via `config/policies/scheduler.yaml`)
- Only posts when anomalies are detected on scheduled runs; always posts on on-demand runs
- Does NOT auto-trigger an investigation in V2 (V3 option)

Implementation: APScheduler or a simple `threading.Timer` loop in a daemon thread started alongside the FastAPI server.

## Architecture Principles

1. Keep trigger, investigation, approval, execution, and delivery separate.
2. Keep integrations behind adapters.
3. Keep changeable settings outside core code.
4. Prefer structured contracts around the LLM rather than loose free-form behavior.
5. Design for versioned growth: V1, V2, and V3 should all fit into the same module map.
6. Every tool the LLM can call must be registered, explicitly enabled in config, and have a `check_prerequisites()` guard.
7. Never pass disabled or unavailable tools to the LLM.

## Important Difference From Vishwakarma-Style Design

Corvin should inherit the strong investigation loop idea, but it should be more explicit about the later-stage flow:

- fix strategy,
- human approval,
- execution,
- verification,
- learning.

That makes the product more complete than a pure RCA engine while still staying safe.

## Framework Position

- Default direction: custom investigation engine plus product-owned orchestration.
- Model-access direction: LiteLLM or an equivalent provider abstraction.
- Future option: LangGraph only if later versions require durable workflow state, resumability, or graph-heavy stage orchestration beyond what the custom flow can manage cleanly.