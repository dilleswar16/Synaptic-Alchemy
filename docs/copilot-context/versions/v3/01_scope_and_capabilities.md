# Corvin V3 Scope And Capabilities

## V3 Goal

V3 introduces approval-gated remediation, verification, and rollback-aware execution under strong policy control.

## V3 Focus Areas

1. Execute only after explicit approval.
2. Verify whether the approved action solved the incident.
3. Keep auditability and policy boundaries explicit.
4. Introduce rollback-aware behavior where needed.

## V3 Required Capabilities

- policy-controlled execution pathways
- execution request and execution result contracts
- verification stage with clear success signals
- rollback recommendation or rollback flow support
- stronger audit trail for approval and execution decisions

## V3 Safety Rule

Execution must never bypass:

- policy checks,
- explicit approval,
- post-action verification.

## V3 Product Standard

V3 should be impressive because it closes the loop safely, not because it executes aggressively.