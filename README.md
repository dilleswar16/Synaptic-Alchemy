# Corvin Copilot Pack  

This folder is an exportable VS Code Copilot context pack for building Corvin from scratch.

Corvin is defined here as an Azure-native investigation platform for personal use, built with:

- Python control plane
- React plus Vite web app
- Postgres persistence
- Azure alert ingestion
- Elastic for logs and application or AKS metrics
- Azure Log Analytics for APIM evidence
- CLI, REST API, web app, and Teams delivery surfaces
- Structured RCA and structured fix strategy output
- Human approval before any future remediation execution

This pack is intentionally separate from the Vishwakarma implementation. It is meant to be copied into the root of a fresh repository so VS Code Copilot can use the context while you build the product.

## What This Pack Contains

- `.github/copilot-instructions.md`
  - Small always-on workspace rules.
- `.github/instructions/`
  - Scoped instructions for architecture, Azure evidence, configurability, UI/API work, and phased delivery.
- `.github/prompts/`
  - Reusable prompts for implementing Corvin in versioned, testable slices.
- `docs/copilot-context/shared/`
  - Full product context, architecture, workflow, stack, modularity, outputs, testing, and target repo structure.
- `docs/copilot-context/versions/`
  - Versioned product plans for V1, V2, and V3.
- `docs/copilot-context/config-blueprints/`
  - Blueprint docs for configuration layout, integration folders, tool folders, environments, and policies.
- `progress.md`
  - The resumable pack-building tracker.

## Intended Workflow

1. Copy this folder's contents into the root of a new Corvin repository.
2. Keep `.github/` at the repo root so VS Code Copilot loads the instructions and prompts.
3. Use `progress.md` to resume documentation or implementation sessions.
4. Build version by version instead of trying to implement the full product in one flow.

## Product Workflow Encoded In This Pack

The target product flow is:

Trigger -> Enrich -> Investigate -> RCA -> Fix Strategy -> Human Approval -> Execute Fix -> Verify -> Learn

For V1, the product stops at RCA plus Fix Strategy. Execution is intentionally deferred to later versions.

## Reading Order

1. `progress.md`
2. `docs/copilot-context/shared/01_product_overview.md`
3. `docs/copilot-context/shared/03_architecture.md`
4. `docs/copilot-context/shared/05_workflow.md`
5. `docs/copilot-context/shared/06_modularity_and_configurability.md`
6. `docs/copilot-context/versions/v1/01_scope_and_capabilities.md`

## Notes

- This pack avoids putting all context into one giant always-on instruction file.
- The small workspace instruction file sets the rules.
- The deeper docs hold the full A-to-Z product plan so Copilot can reference them without being overloaded on every request.
