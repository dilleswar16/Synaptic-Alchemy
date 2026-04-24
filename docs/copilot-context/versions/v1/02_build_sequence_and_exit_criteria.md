# Corvin V1 Build Sequence And Exit Criteria

## Recommended V1 Build Sequence

1. Core contracts and config loader
2. Trigger normalization layer
3. Evidence adapters: Elastic, Log Analytics, AKS, and Azure Activity Log (change correlation)
4. Knowledge layer: `knowledge/site.md`, `runbooks/` stubs, `data/learnings/`, `config/tools/knowledge.yaml`
5. Investigation engine with knowledge injection (site facts + matched runbook + learnings in system prompt)
6. RCA and fix strategy output contracts
7. Postgres persistence layer (init Alembic, create `corvin/storage/` module, initial migration)
8. REST API and CLI
9. Web app operator views (investigation list + detail + fix strategy pages)
10. Teams delivery and manual trigger path

## Recommended Testable Slices

- Slice 1: Azure alert to normalized request ✅ (9 tests pass)
- Slice 2: Enrichment service graceful degradation ✅ (3 tests pass)
- Slice 2b: Elastic evidence adapter (wire elasticsearch-py)
- Slice 3: Log Analytics APIM adapter
- Slice 4: AKS context adapter
- Slice 4b: Azure Activity Log adapter (change correlation)
- Slice 5: Knowledge layer injection — site.md, runbook matching, learnings loading
- Slice 6: Investigation engine with LiteLLM + structured evidence + knowledge context
- Slice 7: RCA contract generation
- Slice 8: Fix strategy contract generation
- Slice 9: Postgres persistence (storage module + Alembic migration)
- Slice 10: CLI and REST API flows
- Slice 11: Web app — list, detail, fix strategy pages
- Slice 12: Teams delivery path

## V1 Exit Criteria

- A user can start an investigation manually through CLI, API, web app, and Teams.
- Azure alerts can trigger the investigation flow automatically.
- The system enriches incidents using the planned V1 evidence adapters.
- The investigation engine produces a structured RCA.
- The system produces a structured fix strategy with justification.
- Results are stored in Postgres.
- The key slices have isolated tests or validation checks.

## V1 Failure Condition

V1 is not complete if it still depends on one giant end-to-end flow that cannot be tested slice by slice.