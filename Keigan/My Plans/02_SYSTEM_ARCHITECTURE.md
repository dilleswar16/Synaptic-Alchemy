# 02 — System architecture

## 1. Big picture

```
                    ┌────────────────────────── AKS ───────────────────────────┐
 Browser ──HTTPS──▶ │ ns: keigan-frontend      ns: keigan-backend               │
 (MSAL / local)     │ ┌──────────────┐  /api  ┌──────────────┐   ┌────────────┐ │
                    │ │ keigan-web   │──────▶ │ keigan-api   │   │keigan-worker│ │
                    │ │ nginx + SPA  │        │ FastAPI      │   │ jobs +      │ │
                    │ └──────────────┘        │ (stateless)  │   │ schedulers  │ │
 Azure Monitor /    │   ingress: /api/alerts/in/* only (rate limited) ─▶ api    │ │
 Elastic webhooks ─▶│                         └──────┬───────┘   └─────┬──────┘ │
 Teams (Bot Fwk) ──▶│   ingress: /api/teams/messages ─▶ api            │        │
                    └────────────────────────────────┼─────────────────┼────────┘
                                                     ▼                 ▼
                         PostgreSQL (Azure Flexible Server) ◀── shared database, job queue
                         Azure Blob Storage (uploads)   Azure Key Vault (secrets)
          Outbound (read-only): ARM · Azure Monitor metrics · Log Analytics · ServiceNow · Microsoft Graph
                                Elastic · Splunk · Datadog · SolarWinds* · IBM* · vendor APIs*   (*placeholder readers)
                                LLM endpoint (Gemini for local testing; Azure OpenAI wrapper in MetLife)
```

- **keigan-web**: React single-page app served by nginx (unprivileged). Proxies `/api` to the backend service in the backend namespace.
- **keigan-api**: FastAPI, stateless, horizontally scalable. Never runs long work in a request: it enqueues jobs.
- **keigan-worker**: same image, different entrypoint (`python -m keigan.worker_main`). Runs the job queue consumers and interval schedulers
  (ServiceNow poll, SLI collection, predictive analysis, Teams chat polling, retention cleanup). Scales independently.
- Local development runs everything in one process (`RUN_WORKERS_IN_PROCESS=true`) with SQLite and simulated integrations — zero cloud dependencies.

## 2. Technology choices

| Concern | Choice | Why |
|---|---|---|
| Backend language | Python 3.12 | Team skill, AI ecosystem |
| Web framework | FastAPI (async) + Uvicorn | Typed, OpenAPI out of the box, async I/O for LLM and HTTP calls |
| Persistence | SQLAlchemy 2.0 async ORM; SQLite (aiosqlite) locally, PostgreSQL (asyncpg) in Azure | One codebase, portable types |
| Validation / DTOs | Pydantic v2; JSON in camelCase via alias generator | Java-like DTOs; idiomatic JSON for React |
| AI orchestration | LangChain core chat models + LangGraph for the investigation workflow | Allowed frameworks; provider-neutral |
| AI providers | Gemini (local testing), Azure OpenAI, any OpenAI-compatible wrapper, mock | `LLM_PROVIDER` switch, no vendor code outside the gateway |
| Azure access | `azure-identity` (managed / workload identity, client secret locally) + REST via `httpx` | Lean: no heavy `azure-mgmt-*` packages |
| Background work | Database-backed job queue with leases + asyncio schedulers | No extra infrastructure; swap to Service Bus later behind the same interface |
| Templates | Jinja2 (emails, Adaptive Cards) | Safe autoescaping |
| Documents | `pypdf` for PDF text; vision model for images | Lean |
| Statistics | `numpy` | Robust baselines, regression |
| Frontend | React 19 + TypeScript + Vite 6 | Modern, fast |
| Styling | Tailwind CSS v4 with design tokens as CSS variables + own UI kit | Consistency across many screens and agents |
| Primitives | Radix UI (dialog, popover, tooltip, tabs, dropdown, switch, select) | Accessibility |
| Data fetching | TanStack Query v5 | Caching, polling, optimistic updates |
| Routing | React Router 7 | Standard |
| Forms | React Hook Form + Zod | Large onboarding forms |
| Charts | Recharts | SLO charts, AI chat charts, sparklines |
| Graphs | React Flow (`@xyflow/react`) | Topology and blast radius |
| Auth | `@azure/msal-browser` + `@azure/msal-react` (Entra mode) | Official |
| i18n | i18next + react-i18next, namespaced JSON | Localisation |
| Markdown | `react-markdown` + `remark-gfm` (no raw HTML) | Safe rendering of AI output |
| Icons | `lucide-react` | Clean line icons |
| Motion | `motion` (Framer Motion) used sparingly | Subtle corporate animation |

## 3. Backend project structure (Java-style layering)

The package mirrors a Spring Boot project: `controllers` (REST controllers) → `services` (business logic) → `repositories`
(data access) → `entities` (JPA-like models). `dtos` are request/response beans. `config/application_context.py` is the
"Spring context" holding singleton beans.

```
backend/
├── pyproject.toml                 # dependencies (pip install -e .)
├── .env.example                   # every setting documented
├── data/                          # local only: SQLite file, uploads (git-ignored)
└── keigan/
    ├── main.py                    # KeiganApplication: FastAPI factory, middleware, router registration, startup
    ├── worker_main.py             # Worker entrypoint: job consumers + schedulers
    ├── seed_main.py               # python -m keigan.seed_main → demo data
    ├── config/
    │   ├── settings.py            # Settings(BaseSettings) ≈ application.properties
    │   ├── database_config.py     # async engine, session factory, create_all
    │   ├── logging_config.py      # JSON logging + correlation id
    │   └── application_context.py # singleton beans: llm_gateway(), telemetry_gateway(), secret_store(), ...
    ├── controllers/               # one router per bounded context (thin: validate → call service → map DTO)
    │   ├── public_controller.py           # /api/public/*  (client configuration, health)
    │   ├── authentication_controller.py   # /api/auth/*    (local login, me)
    │   ├── application_controller.py      # /api/applications/*  (CRUD, readiness, access, go-live)
    │   ├── onboarding_controller.py       # components, discovery, services, log tools, integrations
    │   ├── knowledge_controller.py        # documents, topology, runbooks, capture prompt
    │   ├── incident_controller.py         # incidents, incident room
    │   ├── investigation_controller.py    # investigations, hypotheses, evidence, comms, postmortem, feedback
    │   ├── alert_controller.py            # alert sources, groups, policy, windows, mute rules, preview
    │   ├── alert_intake_controller.py     # PUBLIC webhook /api/alerts/in/{source_id}
    │   ├── slo_controller.py              # SLIs, SLOs, proposals, measurements, dashboards
    │   ├── intelligence_controller.py     # predictive signals, reports
    │   ├── chat_controller.py             # Keigan AI chat + investigation chat
    │   ├── notification_controller.py     # stakeholders, test sends, outbox
    │   ├── teams_bot_controller.py        # PUBLIC Bot Framework endpoint /api/teams/messages
    │   ├── dashboard_controller.py        # home aggregates
    │   └── administration_controller.py   # platform settings view, usage, audit
    ├── services/                  # business logic; one class per capability
    │   ├── authentication_service.py      # local users, token issue/verify, Entra token validation, group resolution
    │   ├── authorization_service.py       # RBAC: readable/editable application ids, guards
    │   ├── application_service.py         # application CRUD, AD group names, lifecycle, readiness, go-live
    │   ├── onboarding_service.py          # components, Azure verification + discovery, services, log sources, log tools, integrations, command generation
    │   ├── knowledge_service.py           # documents, extraction, digest, chunking, lexical retrieval, grounding context, topology builder, runbooks
    │   ├── incident_service.py            # ServiceNow polling, incident upsert, triage trigger, status sync, incident creation from alerts
    │   ├── investigation_service.py       # investigation lifecycle; runs the investigation graph; feedback; re-run
    │   ├── evidence_service.py            # query planning from templates, telemetry collection, PII masking, condensation, baseline comparison
    │   ├── communication_service.py       # drafts (EN/JA), approvals, postmortem generation
    │   ├── alert_service.py               # intake, canonical mapping, noise-reduction pipeline, groups, feedback, noise report, preview
    │   ├── slo_service.py                 # SLI catalogue, proposals, collection, budgets, burn-rate evaluation, dashboards
    │   ├── intelligence_service.py        # detectors, predictive signals, intelligence reports
    │   ├── chat_service.py                # investigation chat + Keigan AI chat (NL → query → answer/chart)
    │   ├── notification_service.py        # stakeholder routing, email, Teams chats, bot replies, chat polling, milestone detection, outbox
    │   ├── dashboard_service.py           # home aggregates
    │   └── administration_service.py      # usage, audit queries, effective settings
    ├── ai/
    │   ├── llm_gateway.py                 # THE only place that knows providers; structured output; retries; usage accounting; concurrency
    │   ├── prompt_library.py              # loads versioned prompts from resources/prompts
    │   ├── prompt_safety.py               # spotlighting, injection detection, output validation, command risk
    │   ├── ai_output_schemas.py           # Pydantic schemas the LLM must return
    │   └── investigation_graph.py         # LangGraph state machine for investigations
    ├── integrations/              # outbound adapters (the only code doing network I/O to external systems)
    │   ├── azure_client.py                # ARM, diagnostic settings, metric definitions, metrics, Log Analytics, activity log, alert rules
    │   ├── servicenow_client.py           # table API: query, create, update incidents; group lookup
    │   ├── microsoft_graph_client.py      # chats, chat messages, installed apps, sendMail, users, groups
    │   ├── bot_framework_client.py        # proactive messages + inbound token validation
    │   ├── log_tool_clients.py            # ElasticClient, SplunkClient, DatadogClient, placeholder readers (SolarWinds, IBM, Vendor API), SyntheticProbeClient
    │   ├── telemetry_gateway.py           # one interface: query_logs / query_metrics / test_connection, routed per log source; simulation switch
    │   ├── secret_store.py                # KeyVaultSecretStore | LocalEncryptedSecretStore
    │   ├── file_storage.py                # AzureBlobFileStorage | LocalFileStorage
    │   └── simulation/
    │       ├── telemetry_simulator.py     # realistic logs/metrics with injected fault scenarios
    │       └── servicenow_simulator.py    # fake incidents per scenario
    ├── repositories/
    │   ├── base_repository.py             # generic async CRUD: get, find, list, add, delete, count, paginate
    │   └── <domain>_repository.py         # only where custom queries are needed
    ├── entities/                  # SQLAlchemy models grouped by domain (see 03_DATABASE_DESIGN.md)
    │   ├── base_entity.py
    │   ├── platform_entities.py
    │   ├── application_entities.py
    │   ├── knowledge_entities.py
    │   ├── incident_entities.py
    │   ├── alert_entities.py
    │   ├── slo_entities.py
    │   └── notification_entities.py
    ├── dtos/                      # Pydantic request/response models per domain (camelCase JSON)
    ├── security/
    │   ├── current_user.py                # CurrentUser bean + FastAPI dependency
    │   └── security_middleware.py         # security headers, request size limit, rate limiting, correlation id
    ├── workers/
    │   ├── job_queue.py                   # enqueue / lease / complete / retry with back-off / dead-letter
    │   ├── job_handlers.py                # job type → service method registry
    │   └── schedulers.py                  # interval schedules → enqueue jobs (with dedup keys)
    ├── utils/
    │   ├── pii_masker.py                  # regex + key-based masking with stable placeholders
    │   ├── log_condenser.py               # template mining, pattern counts, baseline diff
    │   ├── query_safety.py                # KQL/ES/SPL validation for AI-generated queries
    │   ├── time_utils.py · text_utils.py · id_utils.py · crypto_utils.py · statistics_utils.py · json_path_utils.py
    ├── exceptions/
    │   └── keigan_exceptions.py           # KeiganException hierarchy + FastAPI handlers (problem+json)
    └── resources/
        ├── local_users.yaml
        ├── catalogs/ monitored_resource_types.yaml · sli_catalog.yaml · query_templates.yaml · pii_patterns.yaml · integration_field_schemas.yaml
        ├── prompts/  *.md (system prompts, versioned in front matter)
        ├── templates/email/*.html.j2 · templates/teams/*.json.j2
        └── i18n/ en.json · ja.json   (backend-generated text: emails, Teams cards)
```

### Layering rules

1. Controllers never touch entities' sessions directly except through services; they map service results to DTOs.
2. Services own transactions (`async with session.begin()` or commit at the end of a use case). One service may call another service.
3. Only `integrations/*` performs outbound network I/O. Only `ai/llm_gateway.py` imports LLM SDKs.
4. Every long-running operation is a job (`workers/job_queue.py`), triggered by controllers or schedulers.
5. Every controller endpoint declares its authorization (`require_keigan_admin`, `require_application_reader(application_id)`, `require_application_admin(application_id)`).

### Dependency injection

FastAPI `Depends` with a generic provider:

```python
# config/application_context.py — singleton beans
@lru_cache
def llm_gateway() -> LlmGateway: ...
@lru_cache
def telemetry_gateway() -> TelemetryGateway: ...

# services take the session (and beans) in the constructor
class InvestigationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.llm_gateway = application_context.llm_gateway()

# controllers
@router.get("/{investigation_id}")
async def get_investigation(investigation_id: str,
                            current_user: CurrentUser = Depends(get_current_user),
                            investigation_service: InvestigationService = Depends(provide(InvestigationService))):
```

`provide(ServiceClass)` (in `config/database_config.py`) returns a dependency that opens a session and constructs the service.
Workers construct services with their own session the same way.

## 4. Configuration (`backend/.env`)

All settings live in `keigan/config/settings.py` as one typed `Settings` class grouped by prefix. Highlights:

| Group | Keys |
|---|---|
| Runtime | `ENVIRONMENT` (local/dev/test/prod), `LOG_LEVEL`, `RUN_WORKERS_IN_PROCESS`, `PUBLIC_BASE_URL`, `FRONTEND_BASE_URL`, `CORS_ALLOWED_ORIGINS` |
| Database | `DATABASE_URL` (`sqlite+aiosqlite:///./data/keigan.db` or `postgresql+asyncpg://…`), `DATABASE_POOL_SIZE` |
| Auth | `AUTH_MODE` (local/entra), `LOCAL_TOKEN_SIGNING_SECRET`, `ENTRA_TENANT_ID`, `ENTRA_API_CLIENT_ID`, `ENTRA_API_AUDIENCE`, `ENTRA_SPA_CLIENT_ID`, `ENTRA_API_SCOPE`, `KEIGAN_ADMIN_GROUP_NAME`, `KEIGAN_ADMIN_GROUP_OBJECT_ID`, `APPLICATION_ADMIN_GROUP_PATTERN`, `APPLICATION_READER_GROUP_PATTERN` |
| Keigan identity | `AZURE_IDENTITY_MODE` (managed_identity/workload_identity/client_secret/none), `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `KEIGAN_MANAGED_IDENTITY_OBJECT_ID`, `KEIGAN_MANAGED_IDENTITY_DISPLAY_NAME`, `KEIGAN_MULTI_TENANT_APP_CLIENT_ID` |
| Integrations mode | `TELEMETRY_MODE` (live/simulated), `SERVICENOW_MODE` (live/simulated/disabled), `TEAMS_MODE` (live/simulated/disabled), `EMAIL_MODE` (graph/smtp/simulated/disabled) |
| ServiceNow | `SERVICENOW_INSTANCE_URL`, `SERVICENOW_AUTH_METHOD` (oauth/basic), `SERVICENOW_CLIENT_ID`, `SERVICENOW_CREDENTIAL_SECRET_NAME`, `SERVICENOW_POLL_INTERVAL_SECONDS` |
| Graph / Teams / Email | `GRAPH_SENDER_MAILBOX`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD_SECRET_NAME`, `TEAMS_BOT_APP_ID`, `TEAMS_BOT_APP_SECRET_NAME`, `TEAMS_APP_CATALOG_ID`, `TEAMS_CHAT_POLL_INTERVAL_MINUTES`, `TEAMS_MILESTONE_PHRASES` |
| AI | `LLM_PROVIDER` (gemini/azure_openai/openai_compatible/anthropic/mock), `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_API_VERSION`, `LLM_EXTRA_HEADERS_JSON`, `LLM_USE_MANAGED_IDENTITY`, `LLM_FAST_MODEL`, `LLM_DEEP_MODEL`, `LLM_VISION_MODEL`, `LLM_TEMPERATURE`, `LLM_REQUEST_TIMEOUT_SECONDS`, `LLM_MAX_CONCURRENT_REQUESTS`, `LLM_DAILY_TOKEN_BUDGET_PER_APPLICATION`, `LLM_PRICE_PER_MILLION_INPUT_TOKENS`, `LLM_PRICE_PER_MILLION_OUTPUT_TOKENS` |
| Investigation | `INVESTIGATION_LOOKBACK_MINUTES`, `INVESTIGATION_MAX_WINDOW_MINUTES`, `INVESTIGATION_MAX_CONCURRENT`, `INVESTIGATION_EVIDENCE_TOKEN_BUDGET`, `INVESTIGATION_KNOWLEDGE_TOKEN_BUDGET`, `AUTO_SEND_PRELIMINARY_REPORT` |
| SLO / intelligence | `SLI_COLLECTION_INTERVAL_MINUTES`, `SLO_BACKFILL_DAYS`, `PREDICTIVE_ANALYSIS_INTERVAL_MINUTES`, `INTELLIGENCE_WEEKLY_REPORT_CRON` |
| Storage / secrets | `FILE_STORAGE_MODE` (local/azure_blob), `AZURE_BLOB_ACCOUNT_URL`, `AZURE_BLOB_CONTAINER`, `SECRET_STORE_MODE` (local_encrypted/key_vault), `AZURE_KEY_VAULT_URL`, `LOCAL_SECRET_ENCRYPTION_KEY`, `MAX_UPLOAD_BYTES` |
| Security | `PII_MASKING_ENABLED` (always true outside local), `PII_MASK_IP_ADDRESSES` (none/partial/full), `ALERT_INTAKE_MAX_PAYLOAD_BYTES`, `ALERT_INTAKE_RATE_LIMIT_PER_MINUTE`, `CHAT_RATE_LIMIT_PER_MINUTE` |
| Retention | `RAW_ALERT_RETENTION_DAYS` (30), `INCIDENT_RETENTION_DAYS` (395), `SLI_RAW_RETENTION_DAYS` (90) |

Startup validation fails fast with a clear message for impossible combinations (for example `AUTH_MODE=local` in production, `LLM_PROVIDER=gemini` without key).

## 5. Integrations

### 5.1 Azure (read-only)

All calls via `AzureClient` with a token from `azure-identity` (`ManagedIdentityCredential` / `WorkloadIdentityCredential` in AKS; `ClientSecretCredential` or `AzureCliCredential` locally).

| Purpose | REST call |
|---|---|
| List resources in a resource group | `GET /subscriptions/{s}/resourceGroups/{rg}/resources?api-version=2021-04-01` |
| Diagnostic settings | `GET {resourceId}/providers/Microsoft.Insights/diagnosticSettings?api-version=2021-05-01-preview` |
| Metric definitions | `GET {resourceId}/providers/Microsoft.Insights/metricDefinitions?api-version=2023-10-01` |
| Metrics | `GET {resourceId}/providers/Microsoft.Insights/metrics?metricnames=…&timespan=…&interval=PT5M&aggregation=…&api-version=2023-10-01` |
| Log query | `POST https://api.loganalytics.io/v1/workspaces/{workspaceCustomerId}/query` (`timespan`, `query`) |
| Activity log (changes) | `GET /subscriptions/{s}/providers/Microsoft.Insights/eventtypes/management/values?$filter=…&api-version=2015-04-01` |
| Alert rules | `GET /subscriptions/{s}/resourceGroups/{rg}/providers/Microsoft.Insights/metricAlerts` · `scheduledQueryRules` · `activityLogAlerts` · `actionGroups` |
| Role verification | Attempt each read; map 403 to the missing role |

Multi-tenant: each component stores `azure_tenant_id`; the credential is requested per tenant (multi-tenant app registration or Lighthouse delegation). Rate limiting: concurrency 5 per scope; respect `Retry-After`.

### 5.2 ServiceNow

Table API: `GET /api/now/table/incident?sysparm_query=assignment_group.nameIN{groups}^sys_updated_on>{watermark}&sysparm_fields=…&sysparm_limit=200`;
create: `POST /api/now/table/incident`; work notes on update (optional, off by default). OAuth client credentials preferred; basic auth supported. Watermark per application stored in `platform_setting` (`servicenow_watermark:{application_id}`).

### 5.3 Microsoft Graph and Teams

- Create group chat: `POST /chats` (`chatType: group`, members, topic) with application permission `Chat.Create`.
- Install Keigan bot in chat: `POST /chats/{id}/installedApps` (`TeamsAppInstallation.ReadWriteForChat.All`).
- Post messages and cards: Bot Framework proactive messaging to the chat conversation (bot service URL + conversation ID captured on install event).
- Read messages for polling: `GET /chats/{id}/messages` (RSC permission `ChatMessage.Read.Chat` granted through the Teams app manifest, or `Chat.Read.All`).
- Inbound bot activities (mentions): `POST /api/teams/messages`, JWT validated against Bot Framework OpenID metadata.
- Email: `POST /users/{GRAPH_SENDER_MAILBOX}/sendMail` (`Mail.Send` restricted by application access policy to the Keigan mailbox) or SMTP.
- Simulated mode: chats live in Keigan's database and are shown in the investigation page "Teams room" panel so the whole flow is testable locally; emails go to the outbox.

### 5.4 Log tools

`ElasticClient` (`POST /{index}/_search` with bounded time range + filters; ES|QL optional), `SplunkClient` (`POST /services/search/jobs/export` with `earliest_time`/`latest_time`), `DatadogClient` (`POST /api/v2/logs/events/search`, metrics `GET /api/v1/query`).
Placeholder readers (`SolarWindsReader`, `IbmZLogReader`, `VendorApiReader`) implement the same interface and return `ReaderNotAvailable` with a clear message; their configuration is still stored.
`SyntheticProbeClient` performs HTTP GET probes for SaaS components (timeout, status, latency) — used by SLI collection.

### 5.5 Telemetry gateway (one interface for everything)

```python
class TelemetryGateway:
    async def query_logs(self, log_source: ServiceLogSource, query: TelemetryQuery) -> LogQueryResult
    async def query_metrics(self, service: MonitoredService, metric_names: list[str], time_range, interval) -> MetricQueryResult
    async def query_activity_changes(self, component, time_range) -> list[ChangeEvent]
    async def test_connection(self, connection) -> ConnectionTestResult
```

`TelemetryQuery` carries the language (`kql`, `elastic_dsl`, `esql`, `spl`, `datadog`), the query text, time range and row limit.
With `TELEMETRY_MODE=simulated` the gateway delegates to `TelemetrySimulator`, which produces realistic, scenario-driven logs and metrics
(e.g. *database connection pool exhaustion*, *bad deployment*, *downstream API timeout*, *node memory pressure*, *certificate expiry*, *batch ABEND*, *SaaS vendor outage*).

## 6. Workers and scheduling

**Job queue** (`background_job` table): `enqueue(job_type, payload, deduplication_key, available_at, priority)`; workers lease with `UPDATE … WHERE job_status='queued' AND available_at<=now … RETURNING` (PostgreSQL uses `FOR UPDATE SKIP LOCKED`); lease 5 minutes, heartbeat for long jobs;
retries with exponential back-off (max attempts per type); dead-letter status visible to admins. Idempotent handlers.

| Job type | Trigger | Handler |
|---|---|---|
| `poll_servicenow` | every `SERVICENOW_POLL_INTERVAL_SECONDS` per live application | `IncidentService.poll_servicenow_for_application` |
| `run_investigation` | new incident / alert group / manual / re-run | `InvestigationService.run_investigation` |
| `process_alert_event` | webhook intake | `AlertService.process_alert_event` |
| `settle_alert` | delayed by settle delay | `AlertService.complete_settle_stage` |
| `discover_component` | verify / refresh | `OnboardingService.discover_component` |
| `verify_component_access` | add / retry | `OnboardingService.verify_component_access` |
| `digest_knowledge_document` | upload | `KnowledgeService.digest_document` |
| `build_topology` | button / after digests | `KnowledgeService.build_topology` |
| `measure_sli_proposals` | SLO step open | `SloService.measure_proposals` |
| `backfill_sli` | SLO saved | `SloService.backfill_sli` |
| `collect_sli_measurements` | every 5 min | `SloService.collect_all_due_measurements` |
| `evaluate_burn_rates` | after collection | `SloService.evaluate_burn_rates` |
| `run_predictive_analysis` | every `PREDICTIVE_ANALYSIS_INTERVAL_MINUTES` | `IntelligenceService.run_detectors_for_application` |
| `send_intelligence_report` | weekly + on high-confidence signal | `IntelligenceService.send_report` |
| `deliver_notification` | any send | `NotificationService.deliver` |
| `create_incident_chat` | incident detected | `NotificationService.create_incident_chat` |
| `poll_incident_chats` | every `TEAMS_CHAT_POLL_INTERVAL_MINUTES` | `NotificationService.poll_active_incident_chats` |
| `generate_postmortem` | milestone phrase / button | `CommunicationService.generate_postmortem` |
| `weekly_noise_report` | weekly | `AlertService.build_noise_report` |
| `retention_cleanup` | daily | per-domain purge |

## 7. Security architecture

1. **Authentication:** Entra access tokens (RS256 via JWKS, issuer, audience, `exp`, `nbf`, tenant) or local HS256 tokens (local mode only). Tokens are kept in memory by MSAL (session storage cache), never in local storage.
2. **Authorization:** `AuthorizationService` computes `readable_application_ids` and `editable_application_ids` from groups once per request (cached by token hash for 5 min).
   Every query filters by these ids. Keigan admin bypass is explicit.
3. **Public endpoints:** only `/api/public/*`, `/api/alerts/in/{source_id}` (token or HMAC, constant-time compare, 256 KB, rate limit) and `/api/teams/messages` (Bot Framework JWT). Ingress exposes nothing else publicly.
4. **Secrets:** Key Vault in Azure (`SecretStore` interface), Fernet-encrypted local store for development. Database stores secret *names* only. API never returns secret values.
5. **PII:** `PiiMasker` on every telemetry result, alert payload summary, ServiceNow description and chat input before persistence (evidence) and before every LLM call. Stable placeholders (`<EMAIL_3>`) keep correlation.
6. **Prompt injection:** see `06_AI_ENGINE_AND_PROMPT_SAFETY.md`. Untrusted content is spotlighted, tools are read-only and allowlisted, outputs are schema-validated and citation-checked.
7. **Uploads:** extension + MIME + magic-byte check, size limit, filename sanitised, stored outside web root under random names, never executed; SVG sanitised or rendered as image only.
8. **Transport and headers:** HTTPS only; HSTS; CSP (`default-src 'self'`; connect-src self + login.microsoftonline.com); `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, frame-ancestors none.
9. **Audit:** every write and every AI tool execution (query text, application, user) is written to `audit_event`.
10. **Least privilege:** Keigan's Azure identity holds only reader roles; Graph permissions limited to chat creation, chat read (RSC), mail send for one mailbox, group read.
11. **Supply chain:** pinned dependency ranges, `pip-audit` / `npm audit` in CI, distroless or slim non-root images.

## 8. Data flows (key sequences)

**Incident → investigation → communication**

```
Scheduler ─▶ poll_servicenow ─▶ IncidentService.upsert(incident) ─(new)▶ enqueue run_investigation
Worker ─▶ InvestigationService.run_investigation ─▶ InvestigationGraph
     triage → context → evidence (TelemetryGateway, PiiMasker, LogCondenser) → 3 hypotheses ∥ → synthesis → communications
     ─▶ persist RCA, hypotheses, evidence, timeline ─▶ NotificationService.on_investigation_completed
          ├─ email preliminary report (stakeholders by service + priority)
          └─ Teams: create chat (if not exists) + post Adaptive Card
Scheduler ─▶ poll_incident_chats ─▶ new messages → facts into timeline; answer mentions; milestone? → generate_postmortem → email + chat
```

**Alert → alert group → investigation → (optional) ServiceNow incident** — see product spec §9.

**AI chat data question**

```
User question → ChatService: intent (fast model) → service + source resolution (topology + catalogue)
→ query generation (deep model, few-shot by language) → QuerySafety.validate → TelemetryGateway.query_logs
→ PiiMasker → answer + ChartSpecification (fast model) → persisted message with payload → UI renders chart
```

## 9. Capacity, cost and token strategy

**Per-investigation budget (typical):**

| Step | Model tier | Input tokens | Output tokens |
|---|---|---|---|
| Triage | fast | 3 000 | 600 |
| Hypotheses × 3 (parallel) | deep | 3 × 14 000 | 3 × 1 800 |
| Synthesis | deep | 16 000 | 3 000 |
| Communications (EN + JA) | fast | 6 000 | 2 000 |
| **Total** | | **≈ 67 000** | **≈ 11 000** |

100 investigations/day ≈ 6.7 M input + 1.1 M output tokens. Postmortems and chat are extra and metered.

**Controls:**
1. **Evidence condensation** (largest saving): raw logs are never sent; log lines are templated and counted (`LogCondenser`), only top patterns with masked samples are sent, capped by `INVESTIGATION_EVIDENCE_TOKEN_BUDGET` (default 8 000).
2. **Knowledge budgeting:** grounding context is assembled from digests + retrieved chunks up to `INVESTIGATION_KNOWLEDGE_TOKEN_BUDGET` (default 6 000).
3. **Model tiering:** fast model for triage, intent, titles, comms, narratives; deep model only for hypotheses, synthesis, query generation, topology.
4. **Prompt caching friendliness:** static system prompt and application knowledge first, incident-specific content last, so provider-side prefix caching applies.
5. **Deduplicated work:** noise reduction ensures one investigation per alert group; re-runs reuse collected evidence when the window is unchanged.
6. **Limits:** `LLM_MAX_CONCURRENT_REQUESTS` (global semaphore), `INVESTIGATION_MAX_CONCURRENT` (worker), `max_investigations_per_hour` (per application policy), `LLM_DAILY_TOKEN_BUDGET_PER_APPLICATION`
   (at 80 % notify admins; at 100 % new investigations run in *evidence-only* mode: deterministic evidence and blast radius without AI narrative, clearly labelled).
7. **Accounting:** every call writes `llm_usage_record`; the usage page shows tokens and estimated cost per application, feature and day.

Accuracy over thrift: the deep model is always used for hypotheses and synthesis; budgets cut breadth (fewer, better evidence items), never the reasoning step.
