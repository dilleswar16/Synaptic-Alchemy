# Corvin Data And Evidence Plane

## Purpose

The evidence plane is the foundation of Corvin's investigation quality. The system should gather and normalize evidence before asking the RCA layer to decide what happened.

## Primary Evidence Sources

| Source | Role |
|---|---|
| Azure alert payloads | trigger context and severity |
| Elastic logs | application, AKS, and operational log evidence |
| Elastic metrics | application and AKS metric evidence |
| Azure Log Analytics | APIM and Azure-native operational evidence |
| AKS cluster state | workload, rollout, and pod context |
| Azure Activity Log | change correlation and deployment clues |
| Prior incidents | historical pattern comparison |
| Learned patterns | reusable knowledge and expected signatures |

## Evidence Design Goals

1. Normalize evidence into typed structures before RCA generation.
2. Keep raw evidence available for debugging and replay.
3. Correlate logs, metrics, alerts, rollout state, and change events.
4. Preserve timestamps and correlation identifiers.

## Evidence Categories

- trigger context
- log evidence
- metric evidence
- topology or component context
- change evidence
- historical comparison evidence
- validation and verification evidence

## Evidence Priority Order

The general priority order should be:

1. Alert payload and direct trigger metadata
2. High-signal metrics around the incident window
3. Log evidence around the incident window
4. Recent changes and rollout events
5. Prior incident similarity and learned patterns

## Normalized Evidence Model

Each evidence item should ideally include:

- source system
- evidence type
- timestamp or range
- service or component
- severity or confidence hint
- raw payload reference
- normalized summary

## Incident Window Rule

The system should reason around a defined incident window instead of arbitrary time ranges.

That window should be anchored by:

- the alert timestamp,
- user-specified time hints,
- or a system-defined default when neither is present.

## Change Intelligence Requirement

Corvin should not limit itself to symptoms. It should actively collect recent changes that might explain the alert.

Examples:

- AKS rollout history
- deployment markers
- Azure Activity Log entries
- APIM changes if relevant
- configuration changes if available

## Storage Direction

Corvin should persist:

- normalized incidents,
- RCA outputs,
- fix strategies,
- approval states,
- later execution results,
- verification results,
- replayable evidence snapshots when useful.

## Long-Term Goal

The evidence plane should eventually support:

- incident replay,
- evaluation against known incidents,
- learned baselines,
- cross-incident pattern detection.