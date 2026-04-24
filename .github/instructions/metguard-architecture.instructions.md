---
description: "Use when designing Corvin architecture, module boundaries, workflow stages, service decomposition, adapters, orchestration, approval flow, or execution flow. Covers the Azure-native control-plane design and versioned product structure."
name: "Corvin Architecture"
---
# Corvin Architecture Guidance

- Treat Corvin as a product with clear layers: triggers, enrichment, investigation, RCA, fix strategy, approval, execution, verification, and learning.
- Keep one main investigation engine. Do not force a multi-agent design unless a later version proves it is necessary.
- Model the system as a configurable control plane that observes Java Spring Boot workloads running elsewhere.
- Keep inbound triggers, evidence adapters, decision logic, and delivery channels separate.
- Prefer explicit module boundaries over large orchestrator files.

## Core Boundaries

- Trigger adapters
- Enrichment services
- Investigation engine
- RCA formatter
- Fix strategy generator
- Approval service
- Execution service
- Verification service
- Learning and replay service
- Delivery channels

## Version Rules

- V1: RCA plus fix strategy only.
- V2: approval center, stronger collaboration surfaces, better correlation.
- V3: approval-gated execution, verification, rollback, and audit.

## Design Preference

- Favor deterministic pre-enrichment and structured outputs around the LLM, not opaque orchestration.
- Keep the investigation engine custom and controllable.
- Separate fix strategy generation from fix execution.