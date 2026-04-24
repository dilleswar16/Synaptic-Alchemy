# Corvin Output Contracts

## Purpose

Corvin should prefer structured outputs over free-form prose where the system needs to chain later actions.

## Required Structured Outputs

- RCA
- fix strategy
- approval request
- execution result
- verification result

## RCA Contract

Minimum fields:

- incident summary
- affected component or service
- probable root cause
- confidence
- evidence chain
- impact summary
- unresolved questions

## Fix Strategy Contract

Minimum fields:

- proposed strategy title
- strategy summary
- why this strategy follows from the RCA
- prerequisites
- risks
- blast radius estimate
- expected success signals
- whether approval is required

## Approval Request Contract

Minimum fields:

- incident identifier
- RCA summary reference
- fix strategy reference
- human-readable justification
- risk summary
- requested action
- approval state

## Execution Result Contract

Minimum fields:

- execution identifier
- approved strategy reference
- action performed
- start time
- end time
- success or failure state
- logs or artifacts reference

## Verification Result Contract

Minimum fields:

- execution identifier
- verification checks run
- current signal status
- resolved or unresolved state
- rollback recommendation if needed

## Output Design Rules

1. Keep machine-usable fields stable.
2. Keep user-facing explanations readable.
3. Do not rely only on long-form narrative if later stages need deterministic inputs.
4. Make RCA and fix strategy separate contracts.
5. Make approval and execution auditable.