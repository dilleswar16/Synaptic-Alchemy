---
description: "Implement a Corvin adapter for a trigger, evidence source, or delivery channel. Use when adding Azure alert ingestion, Elastic adapters, Log Analytics adapters, Teams delivery, or any configurable integration."
name: "Corvin: Implement Adapter"
argument-hint: "Adapter type and target integration"
agent: "agent"
---
Implement one Corvin adapter in a modular, configurable way.

Use these references first:

- [Architecture guidance](../../docs/copilot-context/shared/03_architecture.md)
- [Trigger matrix](../../docs/copilot-context/shared/04_trigger_matrix.md)
- [Evidence plane](../../docs/copilot-context/shared/07_data_and_evidence_plane.md)
- [Configurability model](../../docs/copilot-context/shared/06_modularity_and_configurability.md)
- Config blueprint docs in `../../docs/copilot-context/config-blueprints/`

Task:

1. Define the adapter's role.
2. Define the input and output contract.
3. Place all changeable URLs and settings in the correct config area.
4. Keep the adapter replaceable behind a stable interface.
5. Add only the minimal tests or validation hooks needed for this slice.

Output:

- Files added or updated
- Contract summary
- Config files required
- How to test this adapter in isolation