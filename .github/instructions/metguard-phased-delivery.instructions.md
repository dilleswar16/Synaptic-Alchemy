---
description: "Use when planning or implementing Corvin in phases, versions, slices, milestones, or testable increments. Covers how to work version-by-version and validate one slice at a time."
name: "Corvin Phased Delivery"
---
# Corvin Phased Delivery Guidance

- Do not attempt to build the full platform in one end-to-end pass.
- Work from V1 to V3.
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

- V1 should not silently include autonomous remediation.
- V2 should strengthen review, correlation, and operator control.
- V3 is where approval-gated execution and verification belong.