# EV1 — Acceptance Criteria

## EV1 Is Complete When

- connector config is persisted in the database
- the UI can create, edit, and test connectors
- the registry can resolve connector credentials at runtime
- same-tenant Azure deployments have a clear managed identity path
- local development still works without customer infrastructure
- cross-tenant onboarding is documented as an explicit path
- the system no longer depends on env files as the primary customer setup model

## Manual Verification Checklist

- create an application in the UI
- create a service under that application
- add at least one connector
- choose a credential mode
- test the connector
- confirm the config is stored in the DB
- confirm the runtime uses the selected connector flow

## Evidence To Capture

- screenshots of the UI onboarding flow
- sample DB rows for connector storage
- a runtime trace of connector resolution
- a note describing which credential mode was used
- a note describing whether the path was local, same-tenant Azure, or cross-tenant
