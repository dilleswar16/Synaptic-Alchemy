---
description: "Write tests or evaluation checks for one Corvin slice. Use when validating a trigger adapter, evidence adapter, RCA formatter, fix strategy generator, approval step, or verification step."
name: "Corvin: Write Slice Tests"
argument-hint: "Slice or module to validate"
agent: "agent"
---
Write tests and validation checks for one Corvin slice.

Read first:

- [Testing and eval strategy](../../docs/copilot-context/shared/10_testing_and_evals.md)
- [Pack progress](../../progress.md)
- The relevant version docs under `../../docs/copilot-context/versions/`

Task:

1. Identify the exact slice under test.
2. Define the smallest set of valuable tests.
3. Cover happy path, failure path, and configuration edge cases.
4. Prefer isolated tests over giant end-to-end flows.
5. State what remains intentionally untested if full integration is out of scope.

Output:

- test plan
- created or updated tests
- residual risk