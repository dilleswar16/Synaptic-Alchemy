---
description: "Build one capability for the active Corvin version. Use when implementing a version-scoped feature such as enrichment, RCA output, fix strategy generation, approval workflow, or verification logic."
name: "Corvin: Build Version Capability"
argument-hint: "Capability name"
agent: "agent"
---
Build one Corvin capability for the active version only.

Read first:

- [Pack progress](../../progress.md)
- Shared docs in `../../docs/copilot-context/shared/`
- The active version docs under `../../docs/copilot-context/versions/`

Task:

1. Confirm whether the capability belongs in V1, V2, or V3.
2. If it belongs to a later version, state that clearly before making changes.
3. Implement the capability in a testable slice.
4. Respect current-version constraints.
5. Add or update tests, checks, or validation notes for the slice.

Do not:

- pull execution into V1,
- skip the approval stage when execution is in scope,
- or blur fix strategy and actual fix execution.