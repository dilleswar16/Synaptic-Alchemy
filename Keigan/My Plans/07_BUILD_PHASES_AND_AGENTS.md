# 07 — Build phases and agent plan

Work is split into **vertical slices** (backend + frontend for one capability) so each agent can ship a working feature
without waiting on others. Shared foundations are built first by the lead and are owned by the lead afterwards.

## 1. Phases

| Phase | Scope | Owner | Exit criteria |
|---|---|---|---|
| **0. Plans** | This folder | Lead | Documents 00–10 written |
| **1A. Backend foundation** | settings, database, **all entities**, base repository, DTO base, security (auth modes, RBAC), exceptions, middleware, LLM gateway, prompt safety, PII masker, log condenser, query safety, telemetry gateway + simulator, secret store, file storage, job queue + worker + schedulers, service class skeletons with method signatures, controller router registration, seed data skeleton | Lead | `uvicorn keigan.main:app` boots, `/api/public/health` ok, local sign-in works, tables created |
| **1B. Frontend foundation** | Vite + TS + Tailwind v4 project, tokens (light/dark), fonts, UI kit (§04-5), app shell (sidebar, top bar, scope switcher, language switcher, theme toggle), Keigan logo, auth (local + MSAL behind runtime flag), API client, TanStack Query setup, i18n setup with namespaces, routing with page stubs, formatters | Agent **F0** | `npm run build` passes; sign-in → shell → stub pages in light and dark; language switch works |
| **2. Vertical slices** (parallel) | see §2 | Agents **S1–S5** | Each slice: endpoints implemented, UI complete with real data from seeded/simulated environment, i18n keys in `en` |
| **3. Integration** | Home dashboard wiring, cross-slice links, seed scenarios end to end, boot + build + smoke run, bug fixes | Lead | Seeded demo: incident → investigation (mock or Gemini) → Teams room (simulated) → postmortem; alerts → groups; SLO dashboard; intelligence; AI chat |
| **4. Localisation** | Translate all namespaces to `ja`, `zh-CN`, `es`, `es-MX`, `nl`, `fr`; backend email/Teams strings `ja` | Agent **L1** | No missing keys (script check) |
| **5. Deployment** | Dockerfiles, nginx config, Helm chart (frontend/backend namespaces, workload identity, ingress, network policies), Teams app manifest, README run books | Agent **D1** | `helm template` renders; docker builds (when Docker available) |
| **6. Hardening (later)** | Alembic migrations, test suites, load test of intake, pen-test fixes, RAG (doc 08) | Later | — |

## 2. Vertical slices and file ownership

Shared files owned by the lead (agents must **not** edit; ask the lead via the learnings log or keep changes minimal and additive where explicitly allowed):
`backend/keigan/main.py`, `config/*`, `entities/base_entity.py`, `ai/llm_gateway.py`, `ai/prompt_safety.py`, `integrations/telemetry_gateway.py`, `workers/job_queue.py`, `security/*`,
`frontend/src/components/ui/*`, `frontend/src/components/layout/*`, `frontend/src/api/httpClient.ts`, `frontend/src/auth/*`, `frontend/src/i18n/index.ts`, `frontend/src/styles/*`, `frontend/src/app/routes.tsx`.

Allowed additive edits to shared files: registering a job handler in `workers/job_handlers.py` (one line per job type, in your section), adding columns to entities **of your own domain** (record in `03_DATABASE_DESIGN.md` change log), adding UI kit components if missing (new file only; announce in learnings log).

| Slice | Agent | Backend files | Frontend files |
|---|---|---|---|
| **S1 Applications, onboarding, knowledge** | S1 | `controllers/application_controller.py`, `onboarding_controller.py`, `knowledge_controller.py`; `services/application_service.py`, `onboarding_service.py`, `knowledge_service.py`; `integrations/azure_client.py` (discovery/verification parts), `integrations/log_tool_clients.py` (test connection); `dtos/application_dtos.py`, `onboarding_dtos.py`, `knowledge_dtos.py`; prompts `knowledge_*`, `topology_builder`, `knowledge_capture_prompt`; catalogs `monitored_resource_types.yaml`, `integration_field_schemas.yaml` | `features/applications/**`, `api/applicationsApi.ts`, `api/knowledgeApi.ts`, `i18n/locales/en/applications.json`, `onboarding.json`, `knowledge.json` |
| **S2 Incidents and investigations** | S2 | `controllers/incident_controller.py`, `investigation_controller.py`; `services/incident_service.py`, `investigation_service.py`, `evidence_service.py`, `communication_service.py`; `ai/investigation_graph.py`, `ai/ai_output_schemas.py` (investigation section); `integrations/servicenow_client.py`; catalogs `query_templates.yaml`; prompts `incident_triage`, `evidence_query_planner`, `hypothesis_*`, `rca_synthesis`, `blast_radius_narrative`, `incident_communications`, `postmortem_report`; `dtos/incident_dtos.py`, `investigation_dtos.py` | `features/incidents/**`, `features/investigations/**` (incl. investigation chat panel UI), `api/incidentsApi.ts`, `api/investigationsApi.ts`, locales `incidents.json`, `investigations.json` |
| **S3 Alerts and SLOs** | S3 | `controllers/alert_controller.py`, `alert_intake_controller.py`, `slo_controller.py`; `services/alert_service.py`, `slo_service.py`; catalogs `sli_catalog.yaml`; prompt `alert_group_title`; `dtos/alert_dtos.py`, `slo_dtos.py` | `features/alerts/**`, `features/slo/**`, onboarding step components for alerts/noise/SLO in `features/applications/steps/{IncidentsAndAlertsStep,SloStep}.tsx` (S1 leaves these as stubs), `api/alertsApi.ts`, `api/sloApi.ts`, locales `alerts.json`, `slo.json` |
| **S4 Notifications, Teams, intelligence** | S4 | `controllers/notification_controller.py`, `teams_bot_controller.py`, `intelligence_controller.py`; `services/notification_service.py`, `intelligence_service.py`; `integrations/microsoft_graph_client.py`, `bot_framework_client.py`; templates `email/*`, `teams/*`; prompts `teams_chat_digest`, `intelligence_*`; `dtos/notification_dtos.py`, `intelligence_dtos.py` | `features/intelligence/**`, notifications step `features/applications/steps/NotificationsStep.tsx` (S1 leaves stub), Teams room panel `features/investigations/components/TeamsRoomPanel.tsx` (S2 leaves stub), `api/notificationsApi.ts`, `api/intelligenceApi.ts`, locales `notifications.json`, `intelligence.json` |
| **S5 AI chat, home, administration** | S5 | `controllers/chat_controller.py`, `dashboard_controller.py`, `administration_controller.py`; `services/chat_service.py`, `dashboard_service.py`, `administration_service.py`; prompts `investigation_chat`, `ai_chat_*`; `dtos/chat_dtos.py`, `dashboard_dtos.py`, `administration_dtos.py` | `features/chat/**`, `features/home/**`, `features/administration/**`, shared `components/chat/ChatMessageView.tsx` + `ChartMessage.tsx` (used by S2's panel), `api/chatApi.ts`, `api/dashboardApi.ts`, `api/administrationApi.ts`, locales `chat.json`, `home.json`, `administration.json` |

**Ownership clarifications (lead, 2026-11-19):**
- `GET/PUT /applications/{id}/servicenow-groups` and `GET /servicenow/groups/search` → **S1** (onboarding data, in `onboarding_controller.py`). S2 only reads the table.
- `GET /incidents/{id}/teams-chat`, `POST /incidents/{id}/teams-chat/messages` → **S4** (in `notification_controller.py`).
- `/administration/simulation/*` (list and trigger scenarios via `SimulationService`) → **S5**.
- Onboarding step UI files under `frontend/src/features/applications/steps/`: S1 creates every step; `IncidentsAndAlertsStep.tsx` and `SloStep.tsx` are left as stubs for **S3**, `NotificationsStep.tsx` as a stub for **S4**. Every step component has props `{ applicationId: string; mode: "wizard" | "page"; canEdit: boolean; onStatusChange?: () => void }` (call `onStatusChange` after saves so the workspace refetches readiness).
- Shared chat UI `frontend/src/components/chat/` (ChatMessageView, ChartMessage, ChatComposer) → **S5**; S2's investigation chat panel uses them when present, otherwise `MarkdownView`.
- `frontend/src/features/investigations/components/TeamsRoomPanel.tsx` (props `{ incidentId: string }`) → stub by **S2**, implemented by **S4**.
- Local dev servers: S1 port 8001 + `data/keigan_s1.db`, S2 8002/`keigan_s2.db`, S3 8003, S4 8004, S5 8005 (set `DATABASE_URL`). Frontend dev servers: 5174–5178 with `VITE_API_PROXY_TARGET` if supported by F0's config, otherwise build-only checks.

Cross-slice calls go through the service **method signatures created by the lead in Phase 1A** (skeleton classes with docstrings). If a slice needs a method from another slice's service
that does not exist yet, implement a minimal version in your own service and log it in `09_LEARNINGS_LOG.md` for the lead to reconcile.

## 3. Definition of done (per slice)

1. Every endpoint in `05_API_CONTRACT.md` for the slice exists, has RBAC, and uses DTOs.
2. Works fully in local mode: SQLite, `TELEMETRY_MODE=simulated`, `SERVICENOW_MODE=simulated`, `TEAMS_MODE=simulated`, `EMAIL_MODE=simulated`, `LLM_PROVIDER=mock` **and** with a real Gemini key.
3. UI follows `04_UI_UX_DESIGN_SYSTEM.md`, uses the UI kit, all strings via i18n, light and dark themes correct, loading / empty / error states present.
4. Python imports clean (`python -c "import keigan.main"`), `npm run build` (type check) passes.
5. Learnings appended to `09_LEARNINGS_LOG.md`.

## 4. Status tracker

| Item | Status | Notes |
|---|---|---|
| Phase 0 Plans | ✅ Done | 2026-11-19 |
| Phase 1A Backend foundation | ✅ Done | Lead — see `11_BACKEND_FOUNDATION_GUIDE.md`; boots, seeds, local sign-in + RBAC verified |
| Phase 1B Frontend foundation | ⏳ Wave 1 (relaunched on Sonnet) | F0 — writes `frontend/FOUNDATION_READY.md` when done |
| S1 Applications / onboarding / knowledge | ⏳ Wave 1 (relaunched on Sonnet) | backend first, frontend after F0 |
| S2 Incidents / investigations | ⏳ Wave 1 (relaunched on Sonnet) | backend first, frontend after F0 |
| S3 Alerts / SLOs | ⏳ Wave 2 | starts when a wave-1 agent finishes |
| S4 Notifications / Teams / intelligence | ⏳ Wave 2 | |
| S5 AI chat / home / admin | ⏳ Wave 2 | |

**2026-11-19 — usage limit:** the first run of six Opus agents in parallel hit the 5-hour limit before slices wrote code (F0 reached ≈ half). Relaunch policy: agent instructions live in `My Plans/agent-briefs/` (a relaunch is a one-line prompt), Sonnet for build agents, at most three at a time.
| Phase 3 Integration | ⏳ Pending | |
| Phase 4 Localisation | ⏳ Pending | |
| Phase 5 Deployment | ⏳ Pending | |
