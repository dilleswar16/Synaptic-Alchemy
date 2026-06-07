---
description: "Use when designing or implementing the Corvin web app, REST API, CLI, Teams surface, operator workflow UI, approval UI, or output contracts between frontend and backend."
name: "Corvin UI and API"
---
# Corvin UI and API Guidance

- The V1 surfaces are web app, REST API, CLI, Teams, and Azure alert ingestion.
- Teams is part of the target product and should be designed early even if implemented later in the version plan.
- The web app uses React with Vite.
- The backend control plane uses Python.

## UI Rules

- The web app should expose investigation status, RCA, fix strategy, progress, and versioned product state clearly.
- Plan for a future approval center in the UI.
- V1 may run without auth, but do not hardwire the architecture against future auth.

## ApplicationsPage Conventions (V5.2+)

The `ApplicationsPage` renders 4 tabs: **Services | Connectors | Notifications | SLO**.

### Outbound Connector Modal Pattern

The `AddOutboundModal` uses **5 sections in a scrollable modal** (`maxHeight: 72vh`):
1. **Type + Name** — 2-column grid; type selector drives all section defaults
2. **Endpoint** — label/placeholder adapts per type; special fields per type:
   - Email: host + port grid
   - ServiceNow: base URL + `table` field
   - Generic HTTP: URL + HTTP method pill selector
3. **Authentication** — pill button picker (`None | Bearer Token | API Key | OAuth 2.0 | Basic Auth`) + conditional fields
4. **Variables** — add/remove rows of `key → default_value`; `{{var}}` interpolation in default values
5. **Payload Template** — JSON textarea with `{{key}}` placeholders; "Reset to default" button

**Module-level constants pattern** (before `ConnectorsTab` component):
```typescript
const CONNECTOR_DEFAULT_ENDPOINTS: Record<ConnectorType, string> = { ... }
const CONNECTOR_DEFAULT_AUTH: Record<ConnectorType, ConnectorAuthType> = { ... }
const CONNECTOR_DEFAULT_VARS: Record<ConnectorType, ConnectorVariable[]> = { ... }
const CONNECTOR_DEFAULT_PAYLOADS: Record<ConnectorType, string> = { ... }
const AUTH_TYPE_OPTS: { key: ConnectorAuthType; label: string }[] = [ ... ]
```

On type change: auto-populate endpoint, auth type, variables, and payload template from these constants.

### `ConnectorConfig` TypeScript Interface
```typescript
export interface ConnectorVariable { key: string; default_value: string }
export interface ConnectorAuth {
  type: 'none' | 'bearer' | 'api_key' | 'basic' | 'oauth2'
  bearer_token?: string
  api_key?: string; api_key_header?: string
  username?: string; password?: string
  token_url?: string; client_id?: string; client_secret?: string; scopes?: string
}
export interface ConnectorConfig {
  endpoint?: string
  endpoint_fields?: Record<string, string>   // table, port, from, http_method
  auth?: ConnectorAuth
  variables?: ConnectorVariable[]
  payload_template?: string
  webhook_url?: string   // legacy compat only
}
```

Built-in interpolation vars: `{{service_name}}` `{{rca_summary}}` `{{confidence}}` `{{environment}}` `{{request_id}}`

### Connector Card Display
Each outbound connector card must show:
- Connector type icon + name
- **Auth type badge** (e.g. `OAuth 2.0`, `Bearer`, `None`)
- **Variable count** (e.g. `3 variables`)
- **Endpoint URL** (truncated, `overflow: hidden; textOverflow: ellipsis`)

## Delivery Surface Rule

- Treat CLI, REST API, web app, and Teams as first-class surfaces in the target product.
- If implementation sequencing defers part of Teams behavior, keep the contracts ready for it from V1.

## War Games Page Conventions (V5.3+)

The `WarGamesPage` renders 4 tabs: **Chaos Experiments | Alert Correlation | Capacity Forecast | Incident Replay**.
- Each tab renders a dedicated panel component (SimulateAlertPanel, AlertCorrelationPanel, CapacityForecastPanel)
- Tab switching uses a `Tab` type union and `TABS` array pattern
- All actions require human approval before execution

## InvestigationDetailPage Conventions (V5.3+)

- **WarRoomBanner** renders at top when `approval_status === 'pending'` — pulsing animated gradient banner
- **RunbookBuilderChat** renders post-execution (when `approval_status === 'executed'`) below RunbookUpdatePrompt
- Props for RunbookBuilderChat: `{ requestId, serviceName, environment }` from investigation data

## AI Features API Pattern (V5.3+)

All AI feature routes live under `/ai` prefix in `apps/api/routes/ai_features.py`:
- Analysis endpoints: `POST /ai/correlate-alerts`, `POST /ai/capacity-forecast`, etc.
- Approval endpoints: `POST /ai/.../approve` — human-approval gates
- Session endpoints: `POST /ai/runbook-session/start|message|approve|save` — multi-turn

Frontend client pattern: `apiFetch<T>(path, init?)` with typed interfaces in `client.ts`.

## API Rules

- Prefer explicit request and response schemas.
- Use structured outputs for RCA, fix strategy, approval requests, execution results, and verification results.
- Keep manual and automated triggers aligned through shared internal contracts.

## CLI Rules

- The CLI should support direct manual investigation, local testing, replay, and diagnostics.
- The CLI should remain a first-class operator surface, not just a debug afterthought.