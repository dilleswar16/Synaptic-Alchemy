# Keigan: where we are and what comes next

**Last updated:** 2026-11-22. This is the one page to read first. It says what exists, what is only designed, what is parked, what to build next and when. Detail lives in the documents it points to (all in this folder; see `00_INDEX.md` for the folder map).

When this page and the code disagree, fix the page. Update it at the end of every piece of work.

---

## 1. Where we are

| Item | State |
|---|---|
| Branches | `keigan-hardening` pushed at `b2c2de3`. `keigan-ui-ux` pushed at `638bdfe`, with five local commits on top that are not pushed (folder moves, small features and fixes, Ask Keigan backend, Ask Keigan frontend, docs). Nothing is merged. Do not merge or touch production data without explicit authorisation. |
| Working tree | Clean after the docs commit. Push only when the owner says so. The middle commits are grouped by topic and are not each a tested state: shared files (settings, `main.py`, schema scripts, status values) are in the Ask Keigan backend commit, so only the tip was tested. |
| Tests | 2,630 backend tests pass (the builder's run on 2026-11-23 after Ask Keigan phase 4 part B; the lead's own re-run was stopped by low memory on the machine and was not repeated, so this count is not independently confirmed. Part B = the Teams bot on the engine and the legacy investigation chat deleted; 2,637 after phase 4 part A, the prompted-JSON protocol and the conformance suite; 2,519 after phase 3 step 2, tools 9 to 20; 2,412 after phase 3 step 1; 2,350 on 2026-11-21 by the lead). Frontend: typecheck, locale check, contrast check (222 pairs), 135 unit tests (vitest) and production build pass (run 2026-11-22 after Ask Keigan phase 3 step 3). The browser check `frontend/scripts/check-ask-keigan.mjs` (investigation panel and global chat page) passed at 1440 and 390 px, light and dark: 79 steps at 1440 px and 86 at 390 px, none failed or skipped. |
| Not verified anywhere | Any run against a real model (the mock is an oracle that knows each scenario's answer). Translations by native speakers. A real Entra tenant, Teams and ServiceNow. |
| Database | SQLite locally (`create_all`), Alembic and Azure SQL in production (head revision `b8d4f2a6c0e3`, 58 tables). Azure SQL has `demo_data/` and `migrations/` folders, regenerated on 2026-11-21. The Azure SQL scripts and the filtered unique index are checked by parser and drift tests only, never run on SQL Server. |

## 2. Built since the last status (2026-11-21, committed locally, not pushed)

| Roadmap item | What | Doc |
|---|---|---|
| A4 Reliability metrics | `/metrics` page: time to detect, first update, MTTR, time to conclusion, share correct (with sample size), AI usage and estimated cost. **MTTA is not possible**: no acknowledgement timestamp exists. | `features/reliability-metrics/24_RELIABILITY_METRICS.md` |
| B2 Operating notes | Free-text guidance per application, edited in setup, sent to investigation and chat prompts as untrusted, masked, never-cited guidance. New Alembic revision. | `features/application-operating-notes/25_APPLICATION_OPERATING_NOTES.md` |
| B3 Why were these alerts grouped | A localised sentence on alert groups, derived at read time from the real grouping reason. No schema change. | `features/alert-grouping-reason/26_ALERT_GROUPING_REASON.md` |

| **B5 Ask Keigan, phases 1 and 2 (investigation chat)** | The investigation page's chat runs on the new engine: eight read-only tools, a live tool-call trace (Running, Done, Failed, Stopped), citations `[T#] [E#] [R#]`, Stop, history, copy answer with sources, "Show tool details" switch, specific error messages. Two trace tables (revisions `a7c3e9f1b5d2`, `c5e7a9b3d1f4`). Independently reviewed twice (backend, frontend); every finding fixed except those in section 7. **Only with the mock model.** The Teams bot still uses the old engine until phase 4. | `features/ask-keigan-chat/23_ASK_KEIGAN_CHAT_SPEC.md` (sections 13 and 14) |

| **B5 Ask Keigan, phase 3 step 2 (backend tools 9 to 20)** | The global scope offers all twenty read-only tools: investigations, incidents, alert groups, the alert noise funnel, SLO history, predictive signals, the health score, the team (people aliased by role, never named) and the reliability metrics. Every tool calls its service as the asking person, records every application it read, and refuses a record outside the answer's scope. A read path that wrote a default noise policy row was found by the read-only guard and fixed. Mock planner rules for each tool, English and Japanese. The frontend shows their cards since step 3 (fields translated, series drawn as charts). **Only with the mock model.** | `features/ask-keigan-chat/23_ASK_KEIGAN_CHAT_SPEC.md` (section 13, "Phase 3 status" for step 2) |
| **B5 Ask Keigan, phase 3 step 1 (backend)** | The Keigan AI chat's backend runs on the same engine: a global scope profile (the applications the person can read, narrowed to the conversation's), the prompt `ask_keigan_global.md`, the six suggested prompts, and a global conversation answered through `POST /chat/conversations/{id}/answers`. **The access gap is closed**: each answer records the applications its tools read (new nullable column, revision `b8d4f2a6c0e3`), and a person who lost access to any of them no longer sees that answer, its trace, its step outputs or its follow-ups (a notice and the "no access" caption instead), and the model no longer gets it as history. The frontend still uses `POST /messages` until step 3; tools 9 to 19 are step 2. **Only with the mock model.** | `features/ask-keigan-chat/23_ASK_KEIGAN_CHAT_SPEC.md` (section 13, "Phase 3 status") |

| **B5 Ask Keigan, phase 3 step 3 (frontend: the global chat page)** | The Keigan AI chat page runs on the new engine (`AskKeiganConversation`, global scope): the live tool-call trace, citations, Stop, copy with sources and "Show tool details" as on the investigation page; a conversation is created with its first question; the six suggested prompts; the number and chart of a log query and charts for series tools; fields of tools 9 to 20 translated in six languages; an answer hidden after access was lost shows one calm caption and is not asked for again; phone layout (the list in a drawer, 44 px buttons). The old send path and the clarification buttons are removed from the screen; `POST /messages` is still in the backend until step 4. **Found: new conversations keep the title "New conversation"** (the answer endpoint does not set it; a small backend fix). Only with the mock model. | `features/ask-keigan-chat/23_ASK_KEIGAN_CHAT_SPEC.md` (section 13, "Phase 3 frontend status") |

| **B5 Ask Keigan, phase 3 step 4 (backend: the old router removed)** | The old global router in `ChatService` is gone: the intent, knowledge and data answers, the clarification options, the three prompts `ai_chat_intent`, `ai_chat_answer` and `ai_chat_knowledge_answer` with their mock factories, and the global path of `POST /chat/conversations/{id}/messages` with `clarificationResponse`. That endpoint now refuses a Keigan AI chat with `422` and names the answers endpoint; the investigation path stays for the Teams bot's contract until phase 4. The hard-coded global limits are gone, and a unit test fails if one comes back (AC-20). No schema change. **Only with the mock model.** | `features/ask-keigan-chat/23_ASK_KEIGAN_CHAT_SPEC.md` (section 13, "Phase 3 status (step 4)") |
| **B5 Ask Keigan, phase 4 part A (backend: the prompted-JSON protocol and the conformance suite)** | A model whose capability says `tool_calling: prompted_json` now works: the gateway asks it for one JSON object (tool requests or an answer), parses it strictly into the same requests a native call gives, sends a reply outside the format back with the specific problem (`ASK_KEIGAN_PROTOCOL_REPAIR_ATTEMPTS`) and then fails the run with `ai_tool_protocol_failed` instead of guessing. The registry still validates every argument for both modes. Scenarios C1 to C14 (`resources/evaluation/ask_keigan_conformance.yaml`) run offline through the real engine in three modes (mock planner, scripted model with native tool calls, the same script as prompted JSON), and a live script (`backend/scripts/run_ask_keigan_conformance.py --provider-from-env`) runs them against the configured model and writes a JSON report with the capabilities it saw. No schema change, no new setting. **The live script has never run against a real model** (no key here; it ran with `LLM_PROVIDER=mock`). The Teams bot is on the engine since part B (next row). | `features/ask-keigan-chat/23_ASK_KEIGAN_CHAT_SPEC.md` (section 13, "Phase 4 status, part A"); `ai-engine/06_AI_ENGINE_AND_PROMPT_SAFETY.md` (section 4) |
| **B5 Ask Keigan, phase 4 part B (backend: the Teams bot on the engine)** | Questions to Keigan in an incident's Teams chat are answered by the same engine and service as the web, with the investigation profile and **as the person who asked** (the Teams sender resolved by `TeamsSenderAuthorizer`; a sender that cannot be resolved gets no answer, never Keigan's own access). `query_logs` is withheld unless the author is an application admin. Each answer leaves a run and steps in a Teams conversation of the author's own (scope `teams_incident_chat`, apart from the room's messages and from their web chat), the room gets the answer with a Sources line and the "unverified" caution, and when the engine refuses or fails it gets the investigation's findings with the catalogue code logged. The old investigation chat is deleted: `InvestigationChatService`, `investigation_chat.md`, `answer_investigation_question`, `POST /chat/conversations/{id}/messages` and its DTO; no module outside `keigan/ai/` imports `langchain_*` or `langgraph` any more, with no exception. No schema change, no new setting. Nothing ran against a real Teams tenant or a real model. | `features/ask-keigan-chat/23_ASK_KEIGAN_CHAT_SPEC.md` (section 13, "Phase 4 status, part B") |
| **B5 Ask Keigan, phase 4 row 4.5 (administration page)** | The settings page shows each configured AI model's resolved capabilities and a summary of the last conformance report (read only; no report yet is shown calmly). New setting `ASK_KEIGAN_CONFORMANCE_REPORT_PATH`. Typecheck and locale check pass; not seen in a browser (low memory on the machine). | `features/ask-keigan-chat/23_ASK_KEIGAN_CHAT_SPEC.md` (section 13) |

Earlier and already pushed: team members with invitations and roles (doc 20), the hardening waves (docs 16, 17, 19), the demo seed for every team status, and Azure SQL demo data.

## 3. Designed, not built

| What | Doc | State |
|---|---|---|
| **Ask Keigan phase 4 row 4.4 and phase 5**: the trace retention purge (parked) and later sources. Row 4.5 (administration page for model capabilities and the last conformance report) is built, see section 2 | `features/ask-keigan-chat/23_ASK_KEIGAN_CHAT_SPEC.md` section 13 | Spec approved by the owner on 2026-11-21 (decisions D1 to D6 in it). Phases 1 to 3 and phase 4 rows 4.1 to 4.3 are built (the Teams bot is on the engine, the old router and the investigation chat service are removed), see section 2. |
| **AI evaluation harness**: score real-model investigations against known scenarios | `features/ai-evaluation-harness/22_AI_EVALUATION_HARNESS_SPEC.md` | **Design only, by decision.** The owner is prioritising features. Six open questions are in the doc; the first two (real models, budget) are needed only before the first real-model run. |
| Semantic retrieval for knowledge | `features/semantic-retrieval/08_RAG_PROPOSAL.md` | Future; today retrieval is keyword ranking. Revisit when the harness shows misses caused by synonyms or mixed Japanese and English. |

## 4. What to build next, in order, and when

| Order | Item | Size | Build when | Depends on |
|---|---|---|---|---|
| 0 | ~~Commit~~ **Committed locally 2026-11-22** (five commits). Push the branch | S | When the owner says | Nothing |
| 1 | ~~Fix the investigation-chat access gap~~ **Done 2026-11-21**: current read access is now checked on every read and send of an investigation chat (4 tests). Committed on keigan-ui-ux | S | Done | Nothing |
| 2 | **B5 Ask Keigan** (doc 23): phases 1 and 2 **done 2026-11-21**; phase 3 step 1 (backend, access gap) **done 2026-11-22**; phase 3 step 2 (backend tools 9 to 20) **done 2026-11-22**; phase 3 step 3 (the page on the engine, frontend) **done 2026-11-22**; phase 3 step 4 (removing the old router) **done 2026-11-22**; phase 4 part A (the prompted-JSON protocol and the conformance suite, backend) **done 2026-11-22**; phase 4 part B (Teams on the engine) **done 2026-11-23**; next phase 4 rows 4.4 and 4.5 (trace retention purge, parked; administration page) | M to L | Phase 4 next, when the owner says | Phases 1 and 2 |
| 3 | **A2 Honest outcomes** (per-hypothesis state, "what I could not check") and **A3 Decision trace** per investigation | S to M each | After B5 phase 1, because the trace model is shared | B5 trace tables |
| 4 | **C1 Action items** as tracked tasks, **C2 error-budget policy that acts**, **C3 weekly health review**, **C4 runbook health** | S to M each | When the owner wants the "close the loop" wave | A4 metrics (numbers to act on) |
| 5 | **B1 Similar-incident memory** | M | When the harness or users show repeat incidents are missed | Semantic retrieval is optional |
| 6 | **E1 Better suggested fixes** (exact copyable commands, validate and revert steps) | S to M | Any time; most useful once A1 can score them | A1 helps |
| 7 | **D1 ServiceNow write-back**, **D2 Teams card actions**, **D3 read-only MCP server** | S to L | When a team asks; the Ask Keigan tool set is what D3 would expose | B5 |
| 8 | **A1 Evaluation harness** | M | **Before a real model is used on real incidents**, and before any prompt or model change goes live. The owner decides when to start | Real model access and a budget (spec open questions 1 and 2) |

The wave letters and numbers (A1 to E2) are the roadmap in `product/21_PRODUCT_RESEARCH.md`; they are not the feature numbers in `product/12_FEATURE_TRACKER.md`.

## 5. Parked on purpose (decisions of 2026-11-21)

| Item | Why parked | Revisit when |
|---|---|---|
| **E2 Governed execution** (Keigan changes a customer system) | Keigan only suggests and recommends. Execution would need a compliance decision and measured accuracy. Parked, not removed. | The harness shows measured accuracy, a compliance decision allows it and a team asks. Start in non-production with approval for every action. |
| **B4 Code and pipeline evidence** (Azure DevOps, GitHub, read-only) | No read access yet. Kept in the architecture as one more evidence source. | Read access to a repository host is granted. It is the biggest accuracy lever in the independent research. |
| On-call, paging, status page | Teams chat and email are the channels for now. | Responders ask for paging. Integrate with ServiceNow or PagerDuty before building. |

## 6. Needs the owner

1. Approve `features/ask-keigan-chat/23_ASK_KEIGAN_CHAT_SPEC.md` (decisions D1 to D6 are written in; one point to confirm: answers name no people in v1).
2. Say when to commit and push this working tree.
3. When the harness starts: answer its first two open questions (which real models, what budget).
4. Have someone who reads the languages review the new translations (metrics, operating notes, grouping sentence), including `ja`.

## 7. Known issues and gaps found, not yet fixed

| Issue | Where | Note |
|---|---|---|
| Tool-card **summaries** (the one-line result under each tool call, for example "E1: High error rate (strong signal, 3 matching records)") are English for every language. They are built by code from the record, not written by the AI; the model reads and cites the same line. Refusals and errors are localised | `ask_keigan_tools.py` | Decision needed in phase 3: localise the person-facing summary separately from the model's |
| Stale-run marking works by silence (heartbeat plus a conditional update), but was tested only with scripted gateways in one process | `ask_keigan_heartbeat.py`, `ask_keigan_interruption.py` | Test with two real API processes before running more than one pod |
| The filtered unique index (one running answer per conversation) and the read-only guard's statement check were never run on SQL Server | Alembic `c5e7a9b3d1f4`, `tool_registry.py` | Run on a real Azure SQL database before production |
| No screen-reader (NVDA) pass on the chat panel; no run with a real model; Stop is verified in the browser only through an intercepted stream | Ask Keigan UI | Needs a person with a screen reader and a model key |
| The Helm values with the new Ask Keigan settings were checked by a test that reads the YAML, but never rendered with `helm template` (Helm is not installed here) | `deploy/helm/keigan/values.yaml` | Run `helm template` once on a machine with Helm |
| The OpenRCA "about 36%" figure in doc 21 | `product/21_PRODUCT_RESEARCH.md` | Verify at the leaderboard; the page could not be read when checked |
| The metrics seed has no AI-usage rows and no linked alerts | demo seed | On purpose for usage rows (they would distort reporting); the page shows "no data" |

## 8. Standing rules (short)

Proper fixes only, no workarounds, no hard-coded values. Backend tests mirror the source tree. Schema changes only through Alembic, then regenerate the Azure SQL scripts and the migration delta. Update these documents with every change. Keigan only reads and suggests. Never merge or modify production data without explicit authorisation, and push only when the owner asks.

## 9. Fixed on 2026-11-21 and 2026-11-22 (after the three builds)

| Fix | Test |
|---|---|
| Investigation chat re-checks application access on every read and send | `tests/integration/services/test_chat_service.py` (4 tests) |
| Keigan AI chat (global scope): an answer that used an application the reader has since lost is hidden (snapshot, step output and conversation read), also when only one of several applications was lost, and is not sent to the model as history | `test_ask_keigan_answer_access.py`, `test_ask_keigan_service.py`, `test_chat_service.py`, `test_chat_controller.py` |
| A failed Azure Activity Log read says "could not be checked", not "no changes found" | `tests/integration/services/test_evidence_service.py` |
| `openai_compatible` with managed identity now gets an Entra token provider | `tests/integration/ai/test_llm_gateway.py` |
| Investigation page shows the same translated grouping sentence as the Alerts page | `tests/integration/services/test_investigation_service.py` |
| Fallback group summary no longer states a stale alert count (demo SQL regenerated) | `tests/unit/ai/test_alert_ai_schemas.py` |
| The two SLO window tests no longer clear the settings cache | `tests/integration/services/test_slo_service.py` |
| A new Keigan AI chat is titled by its first question (it stayed "New conversation" on the new engine) | `tests/integration/services/test_ask_keigan_service.py`, `tests/unit/services/test_conversation_titles.py` |
| `ensure_utc` has typed overloads (a real date gives a real date), so the type checker no longer flags its callers | `mypy keigan/utils/time_utils.py` clean |
| The administration page shows a number or a flag even when its name contains "token" (token budgets); real secrets stay masked | `tests/unit/config/test_settings.py` |
| Every Ask Keigan setting (24 incl. the model-capability overrides) is in `backend/.env`, `backend/.env.example` and the Helm `backendEnvironment`, one comment line each, defaults equal to `settings.py` (2026-11-22) | `tests/unit/config/test_ask_keigan_deployment_settings.py` (49 tests) |
