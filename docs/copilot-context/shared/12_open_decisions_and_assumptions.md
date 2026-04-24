# Corvin Open Decisions And Assumptions

## Confirmed Assumptions

- Corvin is a personal project.
- Azure is the cloud platform.
- Elastic stores logs and application or AKS metrics.
- Log Analytics is used for APIM evidence.
- The monitored workloads include Java Spring Boot services.
- The control plane should be Python.
- The orchestration default is a custom controllable investigation engine, not a multi-agent framework.
- LiteLLM or an equivalent model-abstraction layer is the preferred model runtime direction.
- The web app should use React with Vite.
- Postgres is the persistence target.
- V1 may run with no auth or simple internal mode.
- Human approval is required before any future fix execution.

## Open Decisions

- Exact Teams implementation path: bot, app, webhook, or hybrid.
- Exact background job model for long-running investigations and later execution flows.
- Whether later-version orchestration complexity is high enough to justify LangGraph.
- Exact persistence model for historical incident replay and learned patterns.
- Exact verification policy for when a fix is considered successful.
- Exact rollback model in V3.
- Whether change correlation is built through Azure-native events only or also through deployment-system adapters.

## Assumptions To Keep Stable Unless Revisited

- V1 stops at fix strategy.
- V2 strengthens review and collaboration rather than jumping to execution too early.
- V3 is the first version where approval-gated execution is allowed.
- Config should remain folder-based and replaceable.

## Decision Hygiene Rule

When one of the open decisions becomes final, update this document and the related version docs instead of scattering the decision across multiple unrelated files.