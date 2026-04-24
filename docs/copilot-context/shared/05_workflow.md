# Corvin Workflow

## Target Workflow

The target product workflow is:

Trigger -> Enrich -> Investigate -> RCA -> Fix Strategy -> Human Approval -> Execute Fix -> Verify -> Learn

## Stage Meaning

## 1. Trigger

An operational event or operator action enters the system.

Examples:

- Azure alert fires
- user starts an investigation from the web app
- operator runs a CLI command
- Teams user asks for an investigation

Output:

- normalized investigation request

## 2. Enrich

The system gathers deterministic, high-signal context before the main reasoning loop.

Examples:

- Elastic evidence lookups
- Log Analytics APIM queries
- AKS rollout and workload context
- Azure Activity Log and change correlation
- prior incident retrieval

Output:

- enriched investigation context

## 3. Investigate

Investigate includes research.

This stage is where the system:

- asks follow-up evidence questions,
- runs structured evidence queries,
- tests hypotheses,
- correlates signals,
- narrows the likely cause.

Output:

- structured investigation findings

## 4. RCA

The system converts investigation findings into a structured root-cause analysis.

Output:

- summary,
- confidence,
- evidence chain,
- likely blast radius,
- unresolved gaps if any.

## 5. Fix Strategy

The system proposes a justified remediation strategy based on the RCA.

This is not execution.

Output:

- proposed action,
- why it should work,
- risks,
- prerequisites,
- expected verification signals.

## 6. Human Approval

The system waits for a human to approve execution-capable actions.

Output:

- approved, rejected, deferred, or revised strategy state.

## 7. Execute Fix

This stage exists only in later versions.

If the strategy is approved, the system executes within defined policy boundaries.

Output:

- execution result and audit data.

## 8. Verify

The system checks whether the approved change actually resolved the problem.

Output:

- verified success,
- partial success,
- failed verification,
- rollback recommendation if needed.

## 9. Learn

The system stores lessons, patterns, and evidence baselines for later incidents.

Output:

- reusable context for future investigations.

## Version Constraint

- V1 ends at Fix Strategy.
- V2 strengthens approval and operator review.
- V3 adds execution and verification.

## Workflow Rule

Never collapse Fix Strategy and Execute Fix into one uncontrolled step.