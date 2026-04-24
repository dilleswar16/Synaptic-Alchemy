---
description: "Use when designing or implementing the Corvin web app, REST API, CLI, Teams surface, operator workflow UI, approval UI, or output contracts between frontend and backend."
name: "Corvin UI and API"
---
# Corvin UI and API Guidance

- The V1 surfaces are web app, REST API, CLI, Teams, and Azure alert ingestion.
- Teams is part of the target product and should be designed early even if implemented later in the version plan.
- The web app uses React with Vite.
- The backend control plane uses Python.

## UI Rules

- The web app should expose investigation status, RCA, fix strategy, progress, and versioned product state clearly.
- Plan for a future approval center in the UI.
- V1 may run without auth, but do not hardwire the architecture against future auth.

## Delivery Surface Rule

- Treat CLI, REST API, web app, and Teams as first-class surfaces in the target product.
- If implementation sequencing defers part of Teams behavior, keep the contracts ready for it from V1.

## API Rules

- Prefer explicit request and response schemas.
- Use structured outputs for RCA, fix strategy, approval requests, execution results, and verification results.
- Keep manual and automated triggers aligned through shared internal contracts.

## CLI Rules

- The CLI should support direct manual investigation, local testing, replay, and diagnostics.
- The CLI should remain a first-class operator surface, not just a debug afterthought.