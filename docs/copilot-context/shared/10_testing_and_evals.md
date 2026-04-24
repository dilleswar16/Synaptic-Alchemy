# Corvin Testing And Evaluation Strategy

## Principle

Corvin should be built in slices that can be validated independently. Do not rely on one giant full-flow test as the main proof of correctness.

## Test Layers

## 1. Contract Tests

Use for:

- request and response schemas,
- adapter input and output contracts,
- config validation,
- structured output contracts.

## 2. Adapter Tests

Use for:

- Azure alert ingestion adapters,
- Elastic evidence adapters,
- Log Analytics adapters,
- Teams or delivery adapters,
- AKS context adapters.

## 3. Orchestration Tests

Use for:

- stage transitions,
- version gating,
- approval boundaries,
- trigger normalization,
- enrichment ordering.

## 4. Slice Integration Tests

Use for:

- one testable capability at a time,
- one adapter family at a time,
- one version-scoped feature at a time.

## 5. Replay And Evaluation Runs

Later versions should support replaying historical incidents or canned incident datasets to check:

- RCA quality,
- fix strategy quality,
- version drift,
- regression against known scenarios.

## Version Test Priorities

### V1

- trigger ingestion
- enrichment adapters
- investigation engine
- RCA output contract
- fix strategy output contract

### V2

- approval state flow
- Teams and web collaboration surfaces
- stronger correlation logic

### V3

- execution policy checks
- approval-gated execution
- verification and rollback behavior

## Evaluation Rule

Every version should define:

- what is considered done,
- what is tested directly,
- what remains intentionally deferred.

## Anti-Pattern To Avoid

Do not treat successful demo flows as sufficient validation. Corvin should prefer repeatable, slice-level evidence of correctness.