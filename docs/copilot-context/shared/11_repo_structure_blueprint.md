# Corvin Repo Structure Blueprint

## Goal

This is the target repository shape for the future Corvin codebase.

```text
corvin/
|- .github/
|  |- copilot-instructions.md
|  |- instructions/
|  |- prompts/
|- apps/
|  |- api/
|  |- web/
|  |- cli/
|- corvin/
|  |- core/
|  |- triggers/
|  |- enrich/
|  |- evidence/
|  |- strategy/
|  |- storage/
|  |- delivery/
|  |- toolsets/              ← registered investigation tools (LLM-callable)
|- config/
|  |- models/
|  |- integrations/
|  |  |- elastic.yaml
|  |  |- aks.yaml
|  |  |- azure_alerts.yaml
|  |  |- azure_activity.yaml    ← change correlation source
|  |  |- teams.yaml
|  |  |- postgres.yaml
|  |- tools/
|  |  |- query_defaults.yaml
|  |  |- knowledge.yaml         ← paths to knowledge/ and runbooks/
|  |- policies/
|  |- environments/
|- knowledge/
|  |- site.md                   ← static infra facts injected into every investigation prompt
|  |- runbooks/
|  |  |- catalog.json           ← keyword → runbook registry (like Vishwakarma agents.json)
|  |  |- README.md              ← runbook format + keyword registration
|  |  |- apim-5xx.md
|  |  |- aks-crashloop.md
|  |- learnings/
|  |  |- general.md             ← patterns discovered from real incidents
|- alembic/                     ← DB migrations
|  |- versions/
|  |- env.py
|- docs/
|  |- copilot-context/
|- tests/
|  |- contracts/
|  |- adapters/
|  |- orchestration/
|  |- slices/
```

## Structure Notes

- `apps/` holds the operator-facing surfaces.
- `platform/` holds the reusable product logic.
- `config/` holds externalized settings and policy files.
- `docs/copilot-context/` holds the product blueprint for Copilot and future sessions.
- `tests/` mirrors the slice-based testing strategy.

## Module Intent

- `triggers/`: ingest and normalize source events.
- `enrich/`: deterministic pre-investigation context gathering.
- `evidence/`: Elastic, Log Analytics, AKS, Azure Activity, and related adapters.
- `strategy/`: RCA and fix strategy generation.
- `storage/`: SQLAlchemy ORM models, Alembic migrations, session factory.
- `delivery/`: Teams adapter and other notification surfaces.
- `toolsets/`: all LLM-callable investigation tool adapters. Each toolset implements `get_tools()`, `execute()`, `check_prerequisites()`. Registered centrally; only enabled toolsets are passed to the LLM.
- `knowledge/site.md`: static infra facts—AKS cluster name, Elastic index patterns, APIM name, Log Analytics workspace ID. Never hardcode these in core code; always read from this file.
- `knowledge/runbooks/catalog.json`: keyword-to-runbook registry. Alert name is matched against `keywords[]`; matched runbook is injected into the investigation engine system prompt.
- `knowledge/runbooks/`: per-alert-type investigation workflows matched by keyword and injected into the investigation engine system prompt.
- `knowledge/learnings/`: incident patterns and gotchas discovered over time, read by the engine as additional context.

## Rule

Any folder that contains changeable integration details should remain cleanly separated from core orchestration logic.