# Corvin V2 Build Sequence And Exit Criteria

## Recommended V2 Build Sequence

1. Approval state model and contracts
2. Web approval center and Teams approval surfaces
3. Change-intelligence enrichment adapters
4. Incident replay and evaluation harness
5. Cross-incident comparison or learned-pattern support
6. Azure Cost Management scheduler and daily report

## Recommended Testable Slices

- Slice 1: approval request lifecycle
- Slice 2: approval UI and Teams approval interaction
- Slice 3: Execution Service (mapping FixAction to AKSAdapter execution)
- Slice 4: ChatOps webhook for two-way Teams messaging
- Slice 5: Premium Dashboard UI Styling (Tailwind/Vanilla Custom CSS)
- Slice 6: Post-Mortem Generator (Auto-publish RCA & execution timeline to Markdown)
- Slice 7: change-correlation enrichment
- Slice 8: replay a historical incident through the RCA and fix strategy path
- Slice 9: compare current incident with prior stored incidents
- Slice 10: Azure Cost Management adapter — fetch and format 30-day spend data

## V2 Exit Criteria

- Approval objects and review flows exist and are usable.
- The product can show and manage approval state consistently across API, web app, and Teams.
- Change intelligence contributes to enrichment.
- Replay and evaluation runs are possible for at least a small historical dataset.
- Daily Azure cost report runs on schedule, detects anomalies, posts to Teams.
- V1 capabilities remain stable.

## V2 Failure Condition

V2 is not complete if approval exists only as a UI shell with no meaningful state model or justification contract behind it.