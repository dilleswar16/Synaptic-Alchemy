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

- V1: RCA plus fix strategy only. No execution, no autonomous action.
- V1.5: Real Azure cloud integration validation. No new features — only wiring real adapters and confirming smoke tests pass.
- V2: Approval center, Approve & Execute integration (ExecutionService & AKSAdapter), Two-Way ChatOps, and Streaming RCA.
- V2.5: AI Intelligence — Incident Memory, SRE Morning Briefing (Jarvis Mode), and Confidence Meter.
- V3: Premium React UI overhaul, Blameless Post-Mortem auto-generator, and Corvin Score health dashboard.

## Design Preference

- Favor deterministic pre-enrichment and structured outputs around the LLM, not opaque orchestration.
- Keep the investigation engine custom and controllable.
- Separate fix strategy generation from fix execution.