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

- Trigger adapters (predictive, validation automation, Azure Monitor, manual)
- Enrichment services (evidence, code enrichment)
- Investigation engine
- RCA formatter
- Fix strategy generator
- AI Intelligence modules (alert correlation, capacity forecasting, runbook builder)
- Approval service (human-approval gate on ALL automated actions)
- Execution service
- Verification service
- Learning and replay service (War Games, incident replay)
- Delivery channels (Teams, webhooks, prediction notifications)
- Connectors (Azure Monitor, Elastic, Git repo, AKS, APIM)

## Version Rules

- V1: RCA plus fix strategy only. No execution, no autonomous action.
- V1.5: Real Azure cloud integration validation. No new features — only wiring real adapters and confirming smoke tests pass.
- V2: Approval center, Approve & Execute integration (ExecutionService & AKSAdapter), Two-Way ChatOps, and Streaming RCA.
- V2.5: AI Intelligence — Incident Memory, SRE Morning Briefing (Jarvis Mode), and Confidence Meter.
- V3: Premium React UI overhaul, Blameless Post-Mortem auto-generator, and Corvin Score health dashboard.
- V3.5–V3.9: Predictive Detections, SLA Countdown, Topology, Remediation Preview, ROI Dashboard, Voice TTS, 3AM Mode, Runbook Auto-Update, War Room.
- V4.5: DB-driven AKS onboarding.
- V5.0: Agentic AI — AutonomousAgent, CausalChain, NL-to-KQL, CommsDrafts.
- V5.1: Multi-Agent, Chaos Engine, IDE Integration, Voice Incident.
- V5.2: UX Maturity — Plus Jakarta Sans font, outbound connector builder.
- V5.3: AI Intelligence Suite — Alert Correlation, Capacity Forecaster, Conversational Runbook Builder, War Games, War Room Banner.

## Design Preference

- Favor deterministic pre-enrichment and structured outputs around the LLM, not opaque orchestration.
- Keep the investigation engine custom and controllable.
- Separate fix strategy generation from fix execution.