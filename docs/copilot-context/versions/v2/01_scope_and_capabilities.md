# Corvin V2 — Scope and Capabilities

## What Is V2?

V2 is the **Human-in-the-Loop Operations** release. It takes the solid V1 engine and
wires it to the real world — giving SREs the ability to interact with Corvin conversationally
via MS Teams, and to approve and execute fixes directly from a Teams card.

V2 must feel like a complete operational tool. An SRE should be able to receive an
alert, investigate, chat with Corvin, approve a fix, and have it executed —
all without leaving Microsoft Teams.

---

## V2 Focus Areas

1. **Two-Way ChatOps** — SREs can `@mention` Corvin in Teams to trigger investigations and ask questions.
2. **Approve & Execute Loop** — Human-approved execution of AKS/Azure fix actions via Teams Adaptive Card button.
3. **Streaming RCA** — Real-time token-by-token streaming of investigation reasoning to the frontend (SSE).

---

## V2 Required Capabilities

- A working `botbuilder-python` Teams bot that listens to incoming mentions.
- An `ExecutionService` that maps `FixAction` objects to real `AKSAdapter` or Azure API calls.
- A `requires_approval` gate: no execution fires without a human clicking "Approve" in Teams.
- FastAPI `StreamingResponse` (SSE) endpoint for real-time RCA reasoning display.
- Approval state (`pending`, `approved`, `rejected`, `executed`) persisted to Postgres.

---

## V2 Testable Slices

- Slice 1: Approval state model and contracts (Pydantic + Postgres migration)
- Slice 2: Approval UI in Teams (Adaptive Card with Approve/Reject buttons)
- Slice 3: ExecutionService — map FixAction to AKSAdapter restart/rollback call
- Slice 4: ChatOps webhook — two-way Teams bot listener (mention → investigate)
- Slice 5: Streaming RCA endpoint (`/investigate/stream`) with SSE + frontend integration

---

## V2 Exit Criteria

- [ ] SRE can `@Corvin investigate order-service` in Teams and get a real RCA card.
- [ ] SRE can click "Approve & Execute" in Teams and the AKS pod is actually restarted.
- [ ] No execution fires without an explicit human approval action.
- [ ] Streaming RCA endpoint produces token-by-token output visible in the React UI.
- [ ] All approval state transitions are persisted to Postgres correctly.
- [ ] V1 and V1.5 capabilities remain fully stable (155+ tests pass).

---

## V2 Still Excludes

- AI-driven intelligence features (memory, pattern matching, morning briefing) — these are V2.5.
- Full UI overhaul — this is V3.
- Broad rollback automation without explicit human gate.