# Corvin Surfaces: CLI, API, Web, Teams

## Purpose

Corvin should support multiple operator surfaces, each with a clear role.

## Surface Summary

| Surface | Purpose | Priority |
|---|---|---|
| CLI | direct local investigation, replay, testing, diagnostics | V1 |
| REST API | core trigger and integration surface | V1 |
| Web app | primary operator console | V1 |
| Teams | collaboration and conversational entrypoint | V1 |

## CLI

The CLI should be a first-class tool for:

- manual investigations,
- replaying historical incidents,
- testing adapters,
- validating configs,
- local developer workflows.

## REST API

The REST API should act as the canonical programmable interface.

It should support:

- manual investigation requests,
- automated Azure alert ingestion,
- progress and status retrieval,
- future approval actions,
- future execution and verification operations.

## Web App

The web app should be the main operator console.

It should eventually expose:

- investigation launch,
- incident list,
- RCA view,
- fix strategy view,
- approval center,
- verification results,
- version and progress visibility.

V1 can begin with a simpler operator UI, but the information model should leave room for those later screens.

## Teams

Teams should be treated as a delivery and conversation surface, not the only control surface.

Use Teams for:

- notifications,
- incident discussion,
- manual trigger entry,
- later approval interactions.

## Surface Alignment Rule

All surfaces should converge on the same internal contracts.

- A CLI investigation and an API investigation should normalize into the same internal request model.
- The web app and Teams should display the same RCA and fix strategy structures.
- Approval actions should map back to the same approval state model regardless of origin.

## Design Rule

Do not design the product around one chat channel. Design it around shared internal contracts plus multiple interchangeable delivery surfaces.