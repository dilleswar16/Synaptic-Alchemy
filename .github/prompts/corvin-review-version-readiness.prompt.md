---
description: "Review Corvin progress against the current version plan. Use when checking if the implementation is aligned with the version scope, exit criteria, and missing slices."
name: "Corvin: Review Version Readiness"
argument-hint: "Version or area to review"
agent: "agent"
---
Review the current Corvin implementation against the target version plan.

Use these references:

- [Pack progress](../../progress.md)
- Shared docs in `../../docs/copilot-context/shared/`
- Version docs under `../../docs/copilot-context/versions/`

Review for:

- scope drift,
- missing slices,
- missing tests,
- misplaced later-version features,
- broken configurability assumptions,
- missing approval or verification boundaries.

Output format:

1. Findings first, ordered by severity.
2. Missing slices.
3. Version readiness summary.
4. Recommended next slice.