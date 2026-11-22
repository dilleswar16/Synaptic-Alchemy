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
    │   ├── chat_controller.py             # Keigan AI chat + investigation chat; the Ask Keigan answer stream, snapshot, step output and cancel endpoints
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
    │   ├── administration_service.py      # usage, audit queries, effective settings
    │   ├── alert_group_link_service.py    # the only writer of alert group → investigation → incident links
    │   ├── ask_keigan_tools.py            # Ask Keigan tools over existing services (evidence, timeline, knowledge, safe log query, recent changes, runbooks, application map, SLO status), registered at import
    │   ├── ask_keigan_engine.py           # AskKeiganEngine: prepare() refuses a model without tools; run() answers one question and never raises for a failed answer
    │   ├── ask_keigan_loop.py             # the loop: stop check, last-turn rule (tool limit, 85 % token budget), one streamed model turn, tools run one after another
    │   ├── ask_keigan_tool_runner.py      # one tool call: fresh session + user copy without cached roles (access re-checked every call), trace, citation number, skipped requests
    │   ├── ask_keigan_prepared_run.py     # before the run exists: capability and context-window checks, rendered system prompt, tool schemas, RunSetup (versions, hashes, limits)
    │   ├── ask_keigan_scopes.py           # ScopeProfile (tools, bound arguments, context, citation kinds, limits, budget key) and the investigation profile builder
    │   ├── ask_keigan_investigation_context.py  # the untrusted investigation digest and the E#/R# sources it names
    │   ├── ask_keigan_transcript.py       # the model's input as data: context, operating notes (masked, untrusted), history, question; earlier turns and tool results
    │   ├── ask_keigan_trace.py            # TraceRecorder: runs and steps in short transactions, masked, size-capped, published as events; audit row chat.answer
    │   ├── ask_keigan_events.py           # RunEventChannel (bounded asyncio queue) and the event names/envelope of protocol version 1
    │   ├── ask_keigan_cancellation.py     # stop flag + stored cancel_requested_at; races a running step against the flag
    │   ├── ask_keigan_answer_assembler.py # final answer: citation check, follow-up split, sanitising, unverified/refusal flags
    │   ├── ask_keigan_limit_summary.py    # the deterministic answer when the model gave none at a limit
    │   ├── ask_keigan_run_state.py        # ExecutedToolCall, AnswerCitation
    │   ├── ask_keigan_service.py          # AskKeiganService: start (access, rate limit, idempotency, one run per conversation, prepare, store question, detached task), stream, snapshot, step output, cancel
    │   ├── ask_keigan_run_registry.py     # AnswerRunRegistry (singleton in application_context): the live answers of this process, one per conversation; cancel_all on shutdown
    │   ├── ask_keigan_run_snapshot.py     # AnswerRunSnapshotBuilder: the stored trace as AnswerRunView (redacts steps on applications the reader lost)
    │   ├── ask_keigan_stream.py           # events -> server-sent frames, keep-alive comments, early-close cleanup
    │   ├── ask_keigan_interruption.py     # RunInterruption: ends a run nothing works on (silent past ASK_KEIGAN_STALE_RUN_SECONDS, or cut at shutdown) as failed/answer_interrupted
    │   ├── reference_release.py           # clears or deletes the rows that still point at a deleted service, runbook or document
    │   └── service_scope.py               # checks that the service ids a user sent belong to the application
    ├── ai/
    │   ├── llm_gateway.py                 # THE only place that knows providers; structured output; retries; usage accounting; concurrency
    │   ├── prompt_library.py              # loads versioned prompts from resources/prompts
    │   ├── prompt_safety.py               # spotlighting, injection detection, output validation, command risk
    │   ├── tool_registry.py               # Ask Keigan tool declarations, per-call checks, read-only guard, masking, model view (no service imports)
    │   ├── ask_keigan_tool_models.py      # the closed input schemas of the Ask Keigan tools
    │   ├── ask_keigan_errors.py           # AskKeiganErrorCatalogue: what the person is told when part of an answer fails (EN/JA, from resources/i18n)
    │   ├── ask_keigan_answer_format.py    # transcript titles, follow-up marker, fixed answers (no access, outside scope), refusal check
    │   ├── ask_keigan_answer_stream.py    # AnswerTextStreamer: model text -> whole, sanitised, citation-checked paragraphs
    │   ├── ask_keigan_follow_ups.py       # splits the follow-up questions off an answer
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
    │   ├── linked_ids.py                  # LinkedIdsMixin: ordered id lists stored as association tables
    │   ├── status_values.py               # one StrEnum per fixed-value column; builds the CHECK constraints
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

### Linking and deleting rows

Two rules keep references between rows consistent. Both are enforced by one piece of code each, so no service repeats them.

- **Alert group, investigation and incident links.** The alert group's own `investigation_id` and `incident_id` are the single record of what
  covers it and which incident it belongs to (an investigation does not store its alert group). Every write of these links goes through
  `AlertGroupLinkService.link` (`services/alert_group_link_service.py`): the alert pipeline when it creates a group for an open incident,
  `IncidentService` when an incident adopts a group or is created from one, and `InvestigationService` when it starts an investigation for a
  group. `link` checks that the rows belong to the same application and that the group and its investigation do not name different incidents,
  and raises `NotFoundException` or `ConflictException` instead of storing a disagreement.
- **Deleting a service, runbook or document.** Rows that list them (association tables such as `incident_affected_service`) or name them
  (for example `alert.service_id`) use a `NO ACTION` foreign key where SQL Server would otherwise see two cascade paths. Before the delete,
  the service calls `release_references` (`services/reference_release.py`). It walks the foreign keys in the entity metadata, so there is no
  hand-kept list of tables: a nullable referencing column is set to NULL, and a column that cannot be NULL (an association row) means the row is
  deleted. `ApplicationService.delete_application` uses it for the application's services too.

Details of the tables and keys: [03 · Database design](03_DATABASE_DESIGN.md) sections 11 to 14.

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
| AI | `LLM_PROVIDER` (gemini/azure_openai/openai_compatible/anthropic/mock), `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_API_VERSION`, `LLM_EXTRA_HEADERS_JSON`, `LLM_USE_MANAGED_IDENTITY`, `LLM_FAST_MODEL`, `LLM_DEEP_MODEL`, `LLM_VISION_MODEL`, `LLM_TEMPERATURE`, `LLM_REQUEST_TIMEOUT_SECONDS`, `LLM_MAX_CONCURRENT_REQUESTS`, `LLM_DAILY_TOKEN_BUDGET_PER_APPLICATION`, `LLM_PRICE_PER_MILLION_INPUT_TOKENS`, `LLM_PRICE_PER_MILLION_OUTPUT_TOKENS`, `LLM_MODEL_PRICES_JSON` (optional per-model prices for the reliability metrics cost estimate; empty = tokens only) |
| Investigation | `INVESTIGATION_LOOKBACK_MINUTES`, `INVESTIGATION_MAX_WINDOW_MINUTES`, `INVESTIGATION_MAX_CONCURRENT`, `INVESTIGATION_EVIDENCE_TOKEN_BUDGET`, `INVESTIGATION_KNOWLEDGE_TOKEN_BUDGET`, `AUTO_SEND_PRELIMINARY_REPORT` |
| SLO / intelligence | `SLI_COLLECTION_INTERVAL_MINUTES`, `SLO_BACKFILL_DAYS`, `PREDICTIVE_ANALYSIS_INTERVAL_MINUTES`, `INTELLIGENCE_WEEKLY_REPORT_CRON` |
| Reliability metrics | `METRICS_MINIMUM_RATING_SAMPLE` (5), `METRICS_MAXIMUM_WINDOW_DAYS` (365); prices are `LLM_MODEL_PRICES_JSON` (AI row) |
| Application content | `APPLICATION_OPERATING_NOTES_MAXIMUM_CHARACTERS` (4000; 100 to 20000), the longest operating notes an application may have |
| Ask Keigan | `ASK_KEIGAN_MAX_TOOL_CALLS_GLOBAL` (8) and `ASK_KEIGAN_MAX_TOOL_CALLS_INVESTIGATION` (6), 1 to 50: tool calls per answer, the limit on how much Keigan does for one question (there is no time limit); `ASK_KEIGAN_MAX_PARALLEL_TOOL_CALLS` (3; 1 to 5); `ASK_KEIGAN_TOOL_TIMEOUT_SECONDS` (60; 5 to 600) per tool call; `ASK_KEIGAN_STALE_RUN_SECONDS` (300; 60 to 3600) and `ASK_KEIGAN_PROGRESS_HEARTBEAT_SECONDS` (15; 5 to 300), where the stale limit must be at least 3 heartbeats or the API refuses to start; `ASK_KEIGAN_DIGEST_TIMELINE_EVENTS` (15), `ASK_KEIGAN_DIGEST_TOPOLOGY_NODES` (40) and `ASK_KEIGAN_DIGEST_EVIDENCE_SUMMARY_CHARACTERS` (300), what the investigation digest in front of the model holds; `ASK_KEIGAN_ANSWER_TOKEN_BUDGET` (80000; 5000 to 1000000); `ASK_KEIGAN_TOOL_OUTPUT_MODEL_CHARACTERS` (6000), `ASK_KEIGAN_TOOL_OUTPUT_STORED_CHARACTERS` (60000) and `ASK_KEIGAN_TOOL_OUTPUT_PREVIEW_CHARACTERS` (1500), the first and last never larger than the stored size; `ASK_KEIGAN_TOOL_LIST_ITEM_LIMIT` (20; 1 to 200); `ASK_KEIGAN_TOOL_SERIES_POINT_LIMIT` (100; 10 to 1000: points one series tool returns, the width of a point grows to keep them within it); `ASK_KEIGAN_TOOL_PASSAGE_CHARACTERS` (2400; 200 to 20000: one passage a tool returns, for example a runbook's steps); `ASK_KEIGAN_LOG_QUERY_MAX_LOOKBACK_MINUTES` (43200; 5 to 43200); `ASK_KEIGAN_KNOWLEDGE_TOKEN_BUDGET` (2500; 500 to 20000); `ASK_KEIGAN_HEARTBEAT_SECONDS` (15; 5 to 60); `ASK_KEIGAN_PROTOCOL_REPAIR_ATTEMPTS` (1; 0 to 2); `ASK_KEIGAN_FOLLOW_UP_QUESTION_LIMIT` (3; 0 to 5); `ASK_KEIGAN_SHUTDOWN_GRACE_SECONDS` (10; 1 to 120: how long a stopping process waits for its running answers before it marks their runs interrupted); `ASK_KEIGAN_TRACE_RETENTION_DAYS` (empty = keep everything; otherwise 30 to 3650); `LLM_MODEL_CAPABILITIES_JSON` (overrides of `resources/catalogs/llm_model_capabilities.yaml`, what each model can do); `LLM_MANAGED_IDENTITY_SCOPE` (token scope for managed identity) |
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
3. **Public endpoints:** only `/api/public/*`, `/api/alerts/in/{source_id}` (token or HMAC, constant-time compare; request size and rate limits are enforced by Azure APIM in front of the ingress, not by the application) and `/api/teams/messages` (Bot Framework JWT). Ingress exposes nothing else publicly.
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

**Alert → alert group → investigation → (optional) ServiceNow incident** (product spec §9). Each step that links the group to its investigation or incident calls `AlertGroupLinkService.link`.

**Ask Keigan answer (spec 23, engine part)**

```
AskKeiganEngine.prepare(profile) ─▶ refuses a model without tools / a prompt that cannot fit (before any run row exists)
TraceRecorder.begin ─▶ chat_answer_run(running)         RunEventChannel ◀─ every recorded change is published after its commit
AskKeiganEngine.run ─▶ AnswerLoop: stop check → last turn? (tool limit | 85 % of token budget) → LlmGateway.stream_agent_turn
   paragraphs ─▶ answer.text     tool requests ─▶ ToolCallRunner (own session, user copy without cached roles) ─▶ tool_registry.execute_by_name
   end ─▶ assemble_answer (citations, follow-ups, unverified) ─▶ TraceRecorder.complete_run (message + audit chat.answer) ─▶ answer.completed
   failure ─▶ AskKeiganErrorCatalogue ─▶ fail_run / cancel_run ─▶ answer.failed (question message links the run)
```

**Ask Keigan tools (spec 23, section 5; investigation scope, phase 2)** are small read-only functions in `services/ask_keigan_tools.py`, each over one existing service, called in-process with the asker's own access: `get_evidence` and `get_investigation_timeline` (`InvestigationService`), `search_knowledge` and `find_runbooks` (`KnowledgeService`), `query_logs` (`ChatDataQueryService`), `get_topology` (`TopologyService`), `get_slo_status` (`SloService.get_dashboard`, shown as the `SloHealthStatus` enum: computed from measurements and never stored, so no column, no CHECK constraint and no migration) and `list_recent_changes`. The last reads the Azure Activity Log through `EvidenceService.read_change_events`, which **raises** when the read fails (the access policy's refusal, an unreachable or refusing source); the investigation pipeline's `collect_change_evidence` calls it and turns the failure into the "could not be checked" evidence item, and the tool turns it into a failed step ("the Azure Activity Log could not be reached"), so a failed read is never reported as "no changes". The tools are registered for both scopes; the global scope profile arrives in phase 3.

**Ask Keigan, around the engine (spec 23, 4.4.1 and 7.5)**

```
POST /api/chat/conversations/{id}/answers ─▶ chat_controller (Accept check) ─▶ AskKeiganService.start, in the request session:
   ChatService.open_conversation (owner + still allowed to read the investigation) ─▶ duplicate clientRequestId? ─▶ registry.register (one live run per conversation)
   ─▶ a running row of another pod? (silent ones are ended) ─▶ chat rate limit ─▶ scope profile ─▶ engine.prepare ─▶ mask the question
   ─▶ TraceRecorder.begin: the question message and the run row in ONE transaction ─▶ asyncio.create_task(engine.run(...))  [registered in AnswerRunRegistry; frees the conversation in its finally]
   (the checks above are the fast path; the database decides a race between pods: a unique clientRequestId -> 409 duplicate_request, the filtered unique index
    uq_chat_answer_run_one_running_per_conversation -> 409 answer_in_progress, each with the run id, and nothing is stored for the loser)
StreamingResponse ◀─ event_frames(channel): id/event/data frames, ": keep-alive" every ASK_KEIGAN_HEARTBEAT_SECONDS; the reader going away never stops the task
GET .../answer-runs/{id}  ─▶ ChatService.open_conversation (owner + still allowed to read) ─▶ stale check (RunInterruption) ─▶ AnswerRunSnapshotBuilder (steps on lost applications redacted); step output: same check
POST .../answer-runs/{id}/cancel ─▶ owner only (a person who lost access may still stop their own run): chat_answer_run.cancel_requested_at is stored and committed FIRST (any pod), then the registry flag (this pod);
   the engine checks both between steps and races every step against the flag
DELETE /api/chat/conversations/{id} ─▶ AskKeiganService.delete_conversation: stop the running answer of this pod and wait for it to end; a silent one is ended as interrupted; one running in another pod is asked
   to stop and the delete is refused with 409 answer_in_progress; only then the rows are removed
application lifespan (main.py) on shutdown ─▶ RunInterruption.interrupt_live_runs: cancel the answer tasks, then fail their runs as answer_interrupted
```

**One end per run.** The run row can be ended by the engine (completed, failed, cancelled), by a stop request, by the stale-run sweep of another pod and by a shutdown. Every end is a single conditional `UPDATE chat_answer_run ... WHERE run_status = 'running'` that is the first statement of its transaction (`TraceRecorder._claim_run_end`); the party that gets rowcount 0 lost the race, writes nothing else (no assistant message, no audit row, no final event), logs at info and, in the engine, returns an outcome with `was_ended_elsewhere`. While a model turn or tool call is in flight, `RunHeartbeat` refreshes `last_progress_at` every `ASK_KEIGAN_PROGRESS_HEARTBEAT_SECONDS` (also a conditional UPDATE, so an ended run is never touched), so the longest silence of a live run is one beat whatever the provider timeouts and retries add up to (`LLM_REQUEST_TIMEOUT_SECONDS` x retries can be several minutes). The settings validator keeps `ASK_KEIGAN_STALE_RUN_SECONDS` at least `STALE_RUN_MINIMUM_HEARTBEATS` (3) heartbeats, so a run is called interrupted only after three missed beats, which only a dead process produces. The sweep itself re-checks the stored progress in its UPDATE (`last_progress_at <= now - stale limit`), so a run that beat after it was judged silent is left alone.

The answer task holds no request-scoped session; every write is a short `open_session()` transaction (SQLite-safe). A pod that dies leaves a `running` row; the next read of that run (snapshot, stop, or a new question in the conversation) ends it as interrupted once `last_progress_at` is older than `ASK_KEIGAN_STALE_RUN_SECONDS` and nothing in the reading process works on it. The registry knows only its own process, so one answer per conversation is enforced by the registry (this pod), a database check for a `running` row (other pods, the fast path) and, for the race between two pods, the filtered unique index on `chat_answer_run(conversation_id) WHERE run_status = 'running'`.

**Read-only guard (spec 23, 9.1).** `read_only_session_guard` wraps the session of one tool call in three layers: `before_flush` (ORM changes; adding an `AuditEvent` row is the only permitted change, never changing or deleting one), `do_orm_execute` (ORM write statements) and `before_cursor_execute` on the session's connection, which lets through only a `SELECT` and the `INSERT INTO audit_event` statement, so `session.execute(text("UPDATE ..."))`, `(await session.connection()).execute(...)` and an ORM `delete(AuditEvent)` raise `ReadOnlyViolation` before they reach the database.

**Language of a tool's messages.** `ToolContext.language_code` (the person's `preferred_locale`) is passed to every message the registry words (refusals, failures, timeouts, the internal-error step, the tool label, the name of a source or record kind): all come from the string tables (`ask_keigan_errors`, `ask_keigan_tools` and `ask_keigan_answers` in `resources/i18n/en.json` and `ja.json`; any other language falls back to English). The code-written `summary` of a tool output is English and is not localised: it is what the model reads and cites, it is the one-line fact of the card (spec 5.2 shows it in English), and the card's label, status and fields around it are localised by the browser.

**Telemetry mode and the Activity Log.** `TelemetryGateway.activity_is_simulated` is the one rule: simulated mode, or a component marked `simulated`. In live mode an application with no Azure subscription has no Activity Log to read: `query_activity_changes` raises `ReaderNotAvailableException` (the tool answers `query_not_answerable` with that sentence) instead of silently answering from the simulator, and every `list_recent_changes` output carries `is_simulated`.

**Managed identity for the model.** `LlmGateway` holds one `azure.identity.aio.ManagedIdentityCredential` (with azure-core's `AsyncioRequestsTransport`, because the default asynchronous transport needs `aiohttp`, which Keigan does not ship) behind one asynchronous token provider used by both `AzureChatOpenAI` (`azure_ad_async_token_provider`) and `ChatOpenAI` (`api_key` as an async callable), so a token refresh never blocks the event loop; `LlmGateway.aclose()` closes the credential.

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
6. **Limits:** `LLM_MAX_CONCURRENT_REQUESTS` (global semaphore), `INVESTIGATION_MAX_CONCURRENT` (all worker pods together: the job lease counts running investigations in the database, so more wait in the queue; must be at least 1; the limit is soft by at most the number of pods minus one, because two pods can claim at the same instant; a job running longer than `JOB_MAXIMUM_RUNTIME_SECONDS` is stopped so it cannot hold a slot), `max_investigations_per_hour` (per application policy), `LLM_DAILY_TOKEN_BUDGET_PER_APPLICATION`
   (at 80 % notify admins; at 100 % new investigations run in *evidence-only* mode: deterministic evidence and blast radius without AI narrative, clearly labelled).
7. **Accounting:** every call writes `llm_usage_record`; the usage page shows tokens and estimated cost per application, feature and day.

Accuracy over thrift: the deep model is always used for hypotheses and synthesis; budgets cut breadth (fewer, better evidence items), never the reasoning step.
