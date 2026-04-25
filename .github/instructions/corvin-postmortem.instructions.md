---
description: "Use when designing or implementing the Blameless Post-Mortem Auto-Generator. Covers the orchestration of RCA data, execution timeline, and markdown/PDF formatting for incident resolution."
name: "Corvin Post-Mortem Generator"
---
# Corvin Post-Mortem Generator Guidance

- The Post-Mortem module must trigger automatically when an investigation/fix action transitions to the "Resolved" state.
- Do not mix the Post-Mortem generator directly into the `InvestigationEngine`. Build a separate `PostMortemService`.

## Data Composition
A complete Blameless Post-Mortem must extract and synthesize the following:
1. **Detection Timeline:** Start time (Azure Alert fired) to Triage time.
2. **Investigation Findings:** The exact `summary`, `root_cause`, and `evidence_references` from the `RCAOutput`.
3. **Execution Timeline:** The exact timestamp the human clicked "Approve & Execute" in Teams, and the completion time of the `AKSAdapter` or Azure action.
4. **Future Prevention:** LLM-generated recommendations to prevent the anomaly from recurring, based on the incident context.

## Delivery Format
- The `PostMortemService` should format the synthesized data into an Enterprise-ready Markdown document.
- Ensure the document adheres to blameless culture principles (focus on systems and processes, not the individual who approved the fix).

## Version Rules
- This feature is slated for late V2 / early V3. It depends on the Execution loops being fully operational.
