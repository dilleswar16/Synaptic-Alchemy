# Corvin V3 Build Sequence And Exit Criteria

## Recommended V3 Build Sequence

1. Execution policy model
2. Approval-gated execution interface
3. Verification checks and verification contract
4. Rollback recommendation model
5. Audit trail and review visibility

## Recommended Testable Slices

- Slice 1: policy validation blocks disallowed execution
- Slice 2: approved low-risk execution path
- Slice 3: verification after a simulated change
- Slice 4: failed verification produces rollback recommendation
- Slice 5: audit trail capture for approval and execution

## V3 Exit Criteria

- Execution only occurs after explicit approval.
- Execution behavior is governed by policy files, not loose prompt behavior.
- Verification is mandatory after execution.
- The system can clearly report success, failure, or rollback recommendation.
- Auditability exists across approval, execution, and verification.

## V3 Failure Condition

V3 is not complete if it can change systems but cannot prove what it changed, why it changed it, or whether the change actually worked.