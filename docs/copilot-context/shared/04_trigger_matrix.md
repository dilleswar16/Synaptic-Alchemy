# Corvin Trigger Matrix

## Purpose

This document defines how Corvin should be triggered across versions and surfaces.

## Trigger Categories

- automatic operational triggers,
- manual operator triggers,
- scheduled validation or review triggers,
- approval and verification triggers.

## Core Trigger Matrix

| Trigger | Type | Source | Version Priority | Expected Output |
|---|---|---|---|---|
| Azure Monitor alert webhook | Automatic | Azure alerts | V1 | investigation request |
| Azure Action Group delivery | Automatic | Azure alerts | V1 | investigation request |
| REST API request | Manual or automated | API clients | V1 | investigation request |
| CLI request | Manual | local operator | V1 | investigation request |
| Web app investigation start | Manual | UI operator | V1 | investigation request |
| Teams message or command | Manual | Teams user | V1 | investigation request |
| Change event trigger | Automatic | deploy or config system | V2 target | enrichment-only or investigation request |
| Approval action | Human decision | web app or Teams | V2 target | approval state change |
| Execution request | Controlled | approval flow | V3 target | execution job |
| Verification trigger | Automatic | post-fix workflow | V3 target | verification request |
| Replay or eval run | Scheduled or manual | CLI or scheduler | V2 or V3 | evaluation result |

## V1 Required Triggers

- Azure alert ingestion
- REST API manual trigger
- CLI manual trigger
- web app manual trigger
- Teams manual trigger

## V2 Expansion Triggers

- Teams manual trigger
- change-correlation triggers
- approval triggers

## V3 Expansion Triggers

- controlled execution triggers
- verification triggers
- rollback triggers if needed

## Trigger Contract Requirements

Every trigger should normalize into a shared internal request model that contains:

- trigger type,
- source,
- time,
- severity,
- affected service or component,
- raw context,
- normalized investigation question or objective,
- correlation identifiers.

## Design Rules

- Keep trigger adapters thin.
- Normalize early.
- Do not force downstream layers to understand vendor-specific payloads.
- Preserve the raw source payload for debugging and replay.