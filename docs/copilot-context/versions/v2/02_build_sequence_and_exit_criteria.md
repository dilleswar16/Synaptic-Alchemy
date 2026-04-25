# Corvin V2 Build Sequence And Exit Criteria

## Recommended V2 Build Sequence

1. Approval state model and Pydantic contracts
2. Approval API endpoints and Postgres migration
3. Teams Adaptive Card with Approve / Reject buttons
4. ExecutionService wired to AKSAdapter
5. ChatOps Teams bot (mention → investigate)
6. Streaming RCA endpoint (SSE) and React consumer

## Recommended Testable Slices

- Slice 1: Approval state model — `ApprovalStatus` enum + Postgres column + Pydantic contract
- Slice 2: Approval API — `POST /investigations/{id}/approve` and `POST /investigations/{id}/reject`
- Slice 3: Teams Adaptive Card — Approve / Reject buttons post back to the approval API
- Slice 4: ExecutionService — maps `FixAction.action_type` to real `AKSAdapter` call (pod restart / rollback)
- Slice 5: ChatOps bot — `botbuilder-python` webhook, listens for `@Corvin investigate <service> <env>`
- Slice 6: Streaming RCA — `GET /investigations/stream` SSE endpoint + React `EventSource` consumer

## V2 Exit Criteria

- [ ] SRE can `@Corvin investigate order-service production` in Teams and receive a real RCA Adaptive Card.
- [ ] SRE can click "Approve & Execute" in Teams and the AKS pod is actually restarted via AKSAdapter.
- [ ] No execution fires without an explicit human approval action (gate enforced at API level).
- [ ] Streaming RCA endpoint produces token-by-token output visible in the React UI (no blank screen wait).
- [ ] All approval state transitions (`pending` → `approved` → `executed`) persist to Postgres.
- [ ] V1 and V1.5 capabilities remain fully stable (155+ tests pass).

## V2 Failure Condition

V2 is not complete if:
- Approval exists only as a UI shell with no real state model or Postgres persistence.
- The ExecutionService calls are mocked — it must contact the real AKS API.
- The ChatOps bot only sends messages outbound and cannot receive mentions.
- The streaming endpoint returns the full response in one chunk (not token-by-token).