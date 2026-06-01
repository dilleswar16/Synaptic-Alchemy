# EV1 — Connector And Identity Architecture

## Architecture Summary

EV1 should establish a single flow for connector onboarding and runtime resolution.

The intended path is:

1. The user configures an application in the Application Panel.
2. The user adds services under that application.
3. The user attaches one or more connectors.
4. The system stores connector metadata in Postgres.
5. The connector registry resolves the stored configuration into a live client at runtime.
6. Azure identity or secret resolution happens only inside the registry.
7. Evidence and operational flows consume the resolved connector.

## Layer Boundaries

### UI layer

The UI should:
- collect connector details
- collect credential mode
- collect application/service scope
- trigger a connection test
- show active/inactive and last-test status

The UI should not:
- know how a connector authenticates internally
- create Azure SDK clients directly
- read secrets from env files as the primary onboarding path

### API layer

The API should:
- validate connector payloads
- persist connector metadata
- test a connector on demand
- expose application/service/connector relationships
- hand the stored config to the registry when needed

The API should not:
- embed auth strategy in random route handlers
- duplicate connector-specific instantiation logic

### Registry layer

The registry should:
- map connector type to connector class
- resolve credential mode
- fetch a secret from env, Key Vault, or encrypted DB value
- instantiate the client
- return a connector or a controlled failure

The registry should be the only place that converts configuration into a live connector instance.

### Identity layer

The identity model should be:
- local dev first: flexible and easy to bootstrap
- Azure production: managed identity or workload identity by default
- cross-tenant: explicit and documented
- least privilege: separate read-only and write capabilities when possible

## Configuration Model

Recommended precedence:

1. Application/service/connector data stored in Postgres
2. Credential reference resolved by the registry
3. Env vars used for bootstrap, local dev, and fallback
4. Managed identity used when running in Azure and available
5. Key Vault used when configured as the credential source

The product should also expose an explicit auth-mode decision rather than relying on guesswork.

Recommended auth-mode behavior:
- local bootstrap can use Azure CLI or env fallback
- Azure-hosted Corvin should prefer managed identity or workload identity
- service principal should be an explicit override path, not the silent default
- the runtime should make the selected path visible for debugging and support

## Storage Model

Connector rows should store:
- source type
- display name
- active state
- test status
- last test time
- config JSON
- credential type
- credential reference

This keeps secret handling out of the UI and allows onboarding to be repeatable.

## Deployment Modes

### Local developer mode

- can use env-based auth
- can use Azure CLI login through `DefaultAzureCredential`
- should not require production secrets to boot

### Same-tenant Azure deployment

- should prefer managed identity or workload identity
- should avoid long-lived client secrets if possible
- should read connector config from DB

### Cross-tenant deployment

- should be treated as an exception path
- should require explicit onboarding and consent
- should not be the default path

## Success Signal

If a customer can configure a connector in the UI, store it in the DB, test it, and have the runtime use it without editing env files, EV1 is doing its job.
