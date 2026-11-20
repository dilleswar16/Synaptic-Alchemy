# 11 — Backend foundation guide (for slice agents)

The lead built these in Phase 1A. Use them; do not re-implement them. Do not edit lead-owned files (see `07` §2) —
if something is missing, add it in your own service and note it in `09_LEARNINGS_LOG.md`.

## Running locally

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -e .          # already done
# Use YOUR OWN database file and port so parallel agents don't collide (S1→8001/keigan_s1.db … S5→8005/keigan_s5.db):
$env:DATABASE_URL = "sqlite+aiosqlite:///./data/keigan_s1.db"
.\.venv\Scripts\python.exe -m keigan.seed_main
.\.venv\Scripts\python.exe -m uvicorn keigan.main:app --port 8001
```
- Test with **curl** (Git Bash) — PowerShell `Invoke-RestMethod` hangs on localhost on this machine.
- Sign in: `curl -s -X POST http://127.0.0.1:8001/api/auth/local-sign-in -H 'Content-Type: application/json' -d '{"userPrincipalName":"keigan.admin@keigan.local"}'` → `accessToken`.
- Local users: `keigan.admin@keigan.local` (KEIGAN_admin), `aiko.appadmin@keigan.local` (CLMJP_admin, CHAD_reader), `rui.reader@keigan.local` (CLMJP_reader, PAYAU_reader), `noa.noaccess@keigan.local` (none).
- `.env` defaults: `AUTH_MODE=local`, `LLM_PROVIDER=mock`, all integrations `simulated`, workers run in the API process.
- Stop servers you start before you finish.

## Seeded demo world (`keigan/seed/foundation_seed.py`)

| Code | Application | Components | Services (type) |
|---|---|---|---|
| CLMJP | Claims Processing (JP), ja, tier 1 | Azure RG `RG_21530_CLMJP_PRD01` | claims-apim (api_management), claims-api (aks, ns claims), claims-document-renderer (aks), claims-intake-func (function_app), claims-workflow (logic_app), claims-nightly-etl (data_factory), claims-sql (sql_database) |
| CHAD | Channel APIs for Digital (AU) | Azure RG `RG_14470_AUCHAD_PRD01` + Elastic connection | chad-apim, azaustaekub14470pr0101 (aks), channel-gateway-app (app_service), chad-notifications-func |
| PAYAU | Payments Platform (AU) | Azure RG + hardware (SYD DC edge) + SolarWinds (placeholder) | payment-api (aks), payment-confirmation-func, payments-apim, syd-f5-ltm-01, syd-paloalto-fw-02 (network_appliance) |
| PADMF | Policy Administration Mainframe (US) | Mainframe + Splunk | cics-policy-online (mainframe_subsystem), premium-billing-batch (batch_job_stream) |
| BENSA | Employee Benefits Portal (SaaS), ja | SaaS platform + vendor API (placeholder) | benefits-portal (saas_service, synthetic probe) |

All are `live`, have dependencies, ServiceNow groups, stakeholders and log sources. Historical scenario windows (6, 17, 13, 4, 3, 2, 9 days ago) and slow conditions
(memory leak on claims-document-renderer, error-budget burn on chad-apim, latency creep on payment-api) are stored in `platform_setting['simulation_configuration']`.
`SeedContext` gives `application_ids_by_code`, `service_ids_by_key["CODE/service-name"]`, `historical_scenarios` (each has `external_incident_number`, `application_code`, `scenario_key`, `started_at`, `ended_at`, service ids).
Add your seed step as `keigan/seed/<name>_seed.py` defining `SEED_ORDER` (knowledge 10 · alerts and SLOs 20 · investigations 30 · intelligence and notifications 40) and `async def seed(session, seed_context)`. It is discovered automatically (no shared file to edit). Make it idempotent. Run only some steps with `$env:SEED_STEPS="knowledge_seed"`. A failing step is logged and skipped, so other slices' half-finished steps never block you.

## Layer cheat-sheet

| Need | Use |
|---|---|
| Settings | `from keigan.config.settings import get_settings` |
| Singleton beans | `from keigan.config import application_context` → `.llm_gateway()`, `.telemetry_gateway()`, `.azure_client()`, `.secret_store()`, `.file_storage()`, `.prompt_library()`, `.telemetry_simulator()`, `.log_tool_client_factory()` |
| Session per request | services take `session: AsyncSession` in `__init__`; controllers use `Depends(provide(MyService))` from `keigan.config.database_config` |
| Session in jobs/scripts | `async with open_session() as session:` (commits on success) |
| Current user | `Depends(get_current_user)`, `Depends(require_keigan_admin)`, and for routes with an `{application_id}` path parameter `Depends(require_application_reader)` / `Depends(require_application_admin)` — all in `keigan.security.current_user` |
| RBAC inside services | `AuthorizationService(session)`: `readable_application_ids(user)`, `editable_application_ids(user)`, `scoped_application_ids(user, requested_ids)`, `ensure_application_reader/admin(user, application_id)`. For routes keyed by another id (incident, investigation…) load the entity and call `ensure_application_reader(user, entity.application_id)`. |
| CRUD | `BaseRepository(session, EntityClass)`: `get_by_id`, `get_required`, `find_all(*conditions, order_by=, limit=)`, `find_one`, `count`, `exists`, `paginate(...) -> (items, total)`, `add`, `add_all`, `delete`, `delete_where` |
| DTOs | subclass `ApiModel` (`keigan.dtos.common_dtos`) → camelCase JSON automatically; `PagedResult[T]`, `JobAcceptedResponse`, `MessageResponse` |
| Errors | raise `NotFoundException`, `ForbiddenException`, `BusinessValidationException(detail, field_errors=[...])`, `ConflictException`, `IntegrationException`, `ReaderNotAvailableException` (`keigan.exceptions.keigan_exceptions`) → problem+json |
| Background work | `await JobQueue(session).enqueue(job_type, payload, deduplication_key=…)`; job types and their handler methods are fixed in `workers/job_handlers.py` (implement the method with those kwargs). Return a small dict (stored as result summary). |
| Audit | `await AuditService(session).record(current_user, "area.verb", target_entity_type=…, target_entity_id=…, application_id=…, action_details={...})` on every write |
| Rate limit | `rate_limiter.check(key, per_minute)` from `keigan.security.security_middleware` |
| Router | your controller file already has `router = APIRouter(prefix="/api", tags=[…])`; write full paths (`@router.get("/applications/{application_id}/runbooks")`). It is already registered in `main.py`. |

## AI

```python
from keigan.ai.llm_gateway import LlmUsageContext, ModelTier, PromptSection, register_mock_response
gateway = application_context.llm_gateway()
system_prompt = application_context.prompt_library().render("incident_triage", application_name=..., service_catalogue=...)  # trusted values only
result = await gateway.generate_structured(
    feature_name="triage", model_tier=ModelTier.FAST, system_prompt=system_prompt,
    prompt_sections=[
        PromptSection("Application knowledge", grounding.knowledge_markdown),                         # trusted (built by Keigan)
        PromptSection("Incident from ServiceNow", masked_text, is_untrusted=True, source_label="servicenow:INC0012345"),
        PromptSection("Task", "Classify the incident …"),
    ],
    output_schema=TriageResult,   # your Pydantic model (ai/ai_output_schemas.py or your slice's schemas module)
    usage_context=LlmUsageContext(application_id=..., investigation_id=..., requested_by_user_principal_name=...),
)
```
- `generate_text(...) -> LlmCallResult(text, input_token_count, output_token_count, model_name)`; `describe_image(image_bytes=, content_type=, instruction=, usage_context=)`.
- `gateway.chat_model(ModelTier.DEEP)` returns a LangChain chat model for LangGraph tool-calling agents; **not available when `gateway.is_mock`** — fall back to `generate_text`/`generate_structured`. Account tokens with `gateway.record_external_usage(...)`.
- Installed: `langchain-core 1.8`, `langchain-openai 1.8`, `langchain-google-genai 4.5`, `langgraph 1.2` (`from langgraph.graph import StateGraph, START, END`; prebuilt ReAct agent: `from langgraph.prebuilt import create_react_agent`).
- **Mock provider:** without a registered mock, schema fields get "Simulated … (LLM_PROVIDER=mock)" placeholders. Register realistic offline responses per feature with `register_mock_response(feature_name, factory)` (factory receives `(output_schema, prompt_sections)` and returns an instance) — do this for every feature whose UI must look right in local demos (the scenario catalogue `SCENARIO_CATALOG` has `root_cause_summary` / `recommended_fix_summary` you can use).
- Prompts: one Markdown file per prompt in `keigan/resources/prompts/<prompt_key>.md` with front matter (`prompt_key`, `version`, `model_tier`). Never interpolate untrusted text into templates.
- `UNTRUSTED_DATA_POLICY` is appended to every system prompt automatically.
- `keigan.ai.prompt_safety`: `spotlight`, `assess_prompt_injection(text).is_suspicious`, `classify_command_risk(command) -> low|medium|high`, `find_citation_codes`, `remove_invalid_citations(text, valid_codes)`, `neutralize_untrusted_links(text, DEFAULT_ALLOWED_LINK_HOSTS)`.
- Token budget: `TokenBudgetExceededException` / `LlmUnavailableException` — catch them to fall back to evidence-only / deterministic output.
- Estimate tokens: `estimate_token_count(text)`.

## Telemetry

```python
from keigan.integrations.telemetry_gateway import TelemetryQuery, TelemetryTarget
target = TelemetryTarget.from_entities(service, log_source, component, log_tool_connection)
result = await application_context.telemetry_gateway().query_logs(target, TelemetryQuery(
    query_language="kql", query_text=kql, time_range_start=start, time_range_end=end,
    query_purpose="aks_container_errors", purpose_parameters={"signal_kind": "error_logs"}))
# result.columns, result.rows (list of dicts), result.row_count, result.is_simulated, result.executed_query_text
metrics = await gateway.query_metrics(target, ["node_cpu_usage_percentage"], start, end, interval_minutes=5)
changes = await gateway.query_activity_changes(application_id, tenant, subscription, resource_group, start, end, use_simulation=...)
probe = await gateway.probe_endpoint(url, application_id=..., use_simulation=...)
await gateway.test_log_source(target) / gateway.test_log_tool_connection(connection)  # → ConnectionTestResult
```
`signal_kind` values understood by the simulator: `error_logs`, `exceptions`, `failed_requests`, `slow_requests`, `failed_dependencies`, `kube_events`, `pod_restarts`, `batch_failures`,
`sli_counts` (params `sli_kind`, `interval_minutes`, `latency_threshold_milliseconds` → rows `{window_start, good, total}` or `{window_start, value}`), `count`, `time_series`, `generic` (inferred from query text).
Rows may carry `count_` (aggregated). Live Azure: `AzureClient` (`list_resource_group_resources`, `get_diagnostic_settings`, `get_metric_definitions`, `query_metrics`, `query_log_analytics`,
`get_workspace_customer_id`, `list_activity_changes`, `list_alert_rules`, `verify_read_access`). Log tools: `ElasticClient`, `SplunkClient`, `DatadogClient`, `PlaceholderReader` via `LogToolClientFactory.client_for(connection)`.

## Safety utilities

- `PiiMasker(MaskingContext())` → `mask_text`, `mask_value` (recursive, JSON-key aware), `mask_rows`, `.masked_value_count`. Share one `MaskingContext` per investigation for stable placeholders.
- `condense_log_records(rows, baseline_rows)` → `CondensedLogs(patterns: [LogPattern], total_record_count, baseline_record_count, strongest_signal)`; `LogPattern.to_dictionary()` matches `condensed_patterns_json`.
- `validate_generated_query(language, text, start, end)` → `HardenedQuery(query_language, query_text, applied_hardening)` or raises `QueryRejectedError`.
- `keigan.utils.text_utils`: `tokenize_for_search`, `term_frequencies`, `rank_with_bm25(query, {key: term_frequencies})`, `chunk_markdown`, `extract_markdown_headings`, `truncate_text`.
- `keigan.utils.statistics_utils`: `robust_baseline`, `linear_trend`, `burn_rate`, `error_budget_minutes`, `propose_availability_target`, `propose_latency_threshold_milliseconds`.
- `keigan.utils.time_utils`: `utc_now`, `parse_iso_duration`, `floor_to_interval`, `iterate_windows`, `hour_of_week`.
- `keigan.utils.json_path_utils`: `read_json_path`, `list_json_paths`.

## Simulation

- `SimulationService(session).trigger_scenario(application_id, scenario_key)` (local/dev/test only) → starts failing telemetry, creates a simulated ServiceNow incident in the app's first assignment group, enqueues `simulate_alerts_for_scenario`.
- `ServiceNowSimulator().list_incidents(group_names, updated_since)` / `create_incident(fields)` / `update_incident(sys_id, fields)` — ServiceNow field names (`number`, `sys_id`, `short_description`, `description`, `priority`, `impact`, `urgency`, `state`, `assignment_group.display_value`, `cmdb_ci.display_value`, `opened_at`, `sys_updated_on` as `YYYY-MM-DD HH:MM:SS` UTC).
- Scenario catalogue: `keigan.integrations.simulation.simulation_scenarios.SCENARIO_CATALOG` (8 scenarios with titles, root causes, fixes, alert rule names, change events).

## How to

Run these from `backend/` (`.\.venv\Scripts\python.exe -m alembic ...`). The database design is described in `03_DATABASE_DESIGN.md` sections 11 to 14.

### Add or change an enum column (a column with a fixed set of values)

1. Add a `StrEnum` to `keigan/entities/status_values.py` (to change a column, add or rename a member of its existing enum). The enum is the one definition of the values.
2. In the entity, add `values_check("column_name", YourEnum)` to `__table_args__` (import it from `status_values`). It builds `CHECK (column_name IN (...))` named
   `ck_<table>_<column>_values`. In code, write the value as an enum member, not a typed string.
3. Write a new Alembic revision (`alembic revision -m "short description"`). For a new column, add the column and create the constraint; for a changed value set, drop
   `ck_<table>_<column>_values` and create it again with the new list. Model it on `d2a6b0c5e8f9`: it takes the condition from the entity, checks the existing rows first and stops
   with a message naming the column if one holds another value, and it does nothing on SQLite (see below). Give the revision a `downgrade`.
4. Tests: add the column to the typed list in `tests/integration/entities/test_status_values.py` (it tries every member and one outside value against a fresh database, and scans the
   code for literals written to constrained columns). `tests/integration/migrations/test_schema_drift.py` compares the CHECK columns that revision `d2a6b0c5e8f9` lists with the ones
   the entities declare, so a new CHECK fails it until the test also reads your revision.
5. Regenerate the Azure SQL files: `scripts\generate_azure_sql_ddl.py` and `scripts\generate_azure_sql_migration_scripts.py` (the drift test compares them with what the entities and Alembic produce).
   Update the value list in `03_DATABASE_DESIGN.md` and its change log.

If the column must stay open (values come from a catalog, an Azure resource type or free input), do not add a CHECK; the open columns are listed in the docstring of `status_values.py`.

### Add a list of ids of other rows (an association list)

Never add a `*_ids_json` column for ids of Keigan rows. Use an association table so the database checks every id.

1. Write the association entity next to its owner. It extends `OrderedLinkColumns` (which supplies `position`) and `EntityBase`, sets `__tablename__` and `linked_id_attribute`, and has the owner id
   column and the linked id column as the two primary-key columns. The owner key is `ForeignKey(..., ondelete="CASCADE")`. The linked key is `NO ACTION` (no `ondelete`) and indexed, because
   the owner and the linked row both cascade from the application and SQL Server allows one cascade path; the exception is a linked row outside the application's cascade tree
   (`conversation_application`). Copy `IncidentAffectedService` in `incident_entities.py`.
2. On the owner: put `LinkedIdsMixin` first in the bases, set `link_relationship_names = ("affected_service_links",)`, declare
   `affected_service_links = ordered_links_relationship("IncidentAffectedService")` and `affected_service_ids = linked_ids_property("affected_service_links")`
   (all from `keigan/entities/linked_ids.py`).
3. Read with the property (`incident.affected_service_ids`). Write only with `incident.replace_linked_ids("affected_service_links", ids)`: it drops duplicates and empty values, keeps
   the order and sets `position`. Do not edit the link rows or assign the property. When a user sends the ids, check them first with `unknown_service_ids(session, application_id, ids)`
   from `keigan/services/service_scope.py`.
4. When a service, runbook or document can be deleted, call `await release_references(session, Model.primary_key_attribute, [ids])` from `keigan/services/reference_release.py` before the delete.
   It finds the `NO ACTION` keys from the entity metadata, so there is no table list to update.
5. Write the revision (model: `a3f5c0d1e2b4`): create the table and its index, copy any existing list into it in order (skipping ids of rows that do not exist), then drop the old column. Regenerate the Azure SQL files as above.

### Why a new CHECK or foreign key needs its own revision

- A database that is already at an older revision never re-runs it, and the DBA scripts in `database/azure_sql/migrations` are one file per revision, each run once. Editing an old revision changes nothing for them.
- Existing rows may break the new rule. A revision checks them first (the CHECK revision stops with a message; the foreign key revision `c9e4f1b8d3a7` repairs orphans before it adds the key: delete the row
  that belongs to the missing parent, or set an optional reference to NULL).
- A foreign key must use `NO ACTION` unless the table has exactly one cascade path from the application (`tests/integration/entities/test_foreign_keys.py` checks this and that every reference column has a key).
- SQLite cannot add a key or a CHECK to an existing table without rebuilding it, and a rebuild with foreign keys on cascade-deletes child rows. So the revision repairs data but skips the key or constraint on
  SQLite and logs a warning; local SQLite demo databases are recreated, and fresh databases and Azure SQL have everything. Never use Alembic batch mode on SQLite for this.
- Alembic's comparison does not see CHECK constraints, so only the tests above notice a forgotten revision for them.

## Conventions reminder

- Descriptive names (no abbreviations), lean code, one service class per capability, all strings user-facing in the UI go through i18n.
- New columns only in your own domain's entity file, recorded in `03_DATABASE_DESIGN.md` change log.
- Every endpoint: DTOs, RBAC, audit on writes, problem+json errors.
