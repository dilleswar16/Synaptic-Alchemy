# EV1 — Acceptance Criteria

## EV1 Is Complete When

- connector config is persisted in the database
- the UI can create, edit, and test connectors
- the registry can resolve connector credentials at runtime
- same-tenant Azure deployments have a clear managed identity path
- cross-tenant onboarding is documented as an explicit path
- env files are no longer the primary customer setup path
- the system has one obvious connector onboarding flow
- the connector families already present in the workspace are covered by the EV1 foundation
- local bootstrap remains simple and does not require customer secrets

## Manual Verification Checklist

- create an application in the UI
- create a service under that application
- add at least one connector
- choose a credential mode
- test the connector
- confirm the config is stored in the DB
- confirm the runtime uses the selected connector flow
- confirm the auth mode is visible and understandable to an operator

## Evidence To Capture

- screenshots of the UI onboarding flow
- sample DB rows for connector storage
- a runtime trace of connector resolution
- a note describing which credential mode was used
- a note describing whether the path was local, same-tenant Azure, or cross-tenant
- a note showing that existing connector families were included in the model
