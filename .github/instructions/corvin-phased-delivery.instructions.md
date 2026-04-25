---
description: "Use when planning or implementing Corvin in phases, versions, slices, milestones, or testable increments. Covers how to work version-by-version and validate one slice at a time."
name: "Corvin Phased Delivery"
---
# Corvin Phased Delivery Guidance

- Do not attempt to build the full platform in one end-to-end pass.
- Work from V1 → V1.5 → V2 → V2.5 → V3.
- Do NOT start a new version until the previous version's exit criteria are fully met.
- Within each version, implement small slices that can be tested independently.

## Slice Rules

- Each slice should have a clear scope.
- Each slice should define what is testable immediately.
- Each slice should update `progress.md` once complete.
- Each slice should avoid leaking future-version behavior into the current version unless it is a deliberate extension point.

## Preferred Build Order

- Contracts and config first
- Trigger and evidence adapters second
- Investigation engine third
- Output contracts fourth
- UI and delivery surfaces next
- Approval and execution later

## Version Safety

- V1: RCA and Fix Strategy only. No execution, no autonomous action.
- V1.5: Real cloud integration validation. No new features — only wiring real adapters and confirming smoke tests pass.
- V2: Human-in-the-Loop Execution (Approve & Execute), Two-Way ChatOps, and Streaming RCA via SSE.
- V2.5: AI Intelligence — Incident Memory, SRE Morning Briefing, and Confidence Meter.
- V3: Premium UI overhaul, Blameless Post-Mortem auto-generator, and Corvin Score health dashboard.