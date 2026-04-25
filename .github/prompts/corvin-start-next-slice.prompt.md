---
description: "Start the next unfinished Corvin slice using progress.md and the version docs. Use when continuing implementation after an interruption or when you want the next small testable task."
name: "Corvin: Start Next Slice"
argument-hint: "Optional focus area or current version"
agent: "agent"
---
Use the Corvin context pack to continue from the next unfinished slice.

Required inputs:

- [Pack progress](../../progress.md)
- [Shared overview](../../docs/copilot-context/shared/01_product_overview.md)
- [Shared workflow](../../docs/copilot-context/shared/05_workflow.md)
- The active version docs under `../../docs/copilot-context/versions/`

Task:

1. Read the current progress first.
2. Determine the active version and next unfinished slice.
3. Restate only the minimal slice scope.
4. Implement or plan only that slice.
5. Keep the work testable in isolation.
6. Update the progress tracker when the slice is complete.

Constraints:

- Do not jump ahead to a later version unless the current version explicitly allows it.
- Do not mix execution-stage behavior into a version that only supports RCA plus fix strategy.
- Prefer one vertical slice over broad scaffolding.