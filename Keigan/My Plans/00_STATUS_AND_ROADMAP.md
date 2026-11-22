# Keigan: where we are and what comes next

**Last updated:** 2026-11-22. This is the one page to read first. It says what exists, what is only designed, what is parked, what to build next and when. Detail lives in the documents it points to (all in this folder; see `00_INDEX.md` for the folder map).

When this page and the code disagree, fix the page. Update it at the end of every piece of work.

---

## 1. Where we are

| Item | State |
|---|---|
| Branches | `keigan-hardening` pushed at `b2c2de3`. `keigan-ui-ux` pushed at `638bdfe`, with five local commits on top that are not pushed (folder moves, small features and fixes, Ask Keigan backend, Ask Keigan frontend, docs). Nothing is merged. Do not merge or touch production data without explicit authorisation. |
| Working tree | Clean after the docs commit. Push only when the owner says so. The middle commits are grouped by topic and are not each a tested state: shared files (settings, `main.py`, schema scripts, status values) are in the Ask Keigan backend commit, so only the tip was tested. |
| Tests (run 2026-11-21, by the lead) | 2,350 backend tests pass. Frontend: typecheck, locale check, contrast check (222 pairs), 108 unit tests (vitest) and production build pass. The browser check `frontend/scripts/check-ask-keigan.mjs` passed at four sizes when the frontend builder ran it (45, 45, 48 and 48 steps, none failed or skipped); I did not rerun it. |
| Not verified anywhere | Any run against a real model (the mock is an oracle that knows each scenario's answer). Translations by native speakers. A real Entra tenant, Teams and ServiceNow. |
| Database | SQLite locally (`create_all`), Alembic and Azure SQL in production (head revision `c5e7a9b3d1f4`, 58 tables). Azure SQL has `demo_data/` and `migrations/` folders, regenerated on 2026-11-21. The Azure SQL scripts and the filtered unique index are checked by parser and drift tests only, never run on SQL Server. |

## 2. Built since the last status (2026-11-21, committed locally, not pushed)

| Roadmap item | What | Doc |
|---|---|---|
| A4 Reliability metrics | `/metrics` page: time to detect, first update, MTTR, time to conclusion, share correct (with sample size), AI usage and estimated cost. **MTTA is not possible**: no acknowledgement timestamp exists. | `features/reliability-metrics/24_RELIABILITY_METRICS.md` |
| B2 Operating notes | Free-text guidance per application, edited in setup, sent to investigation and chat prompts as untrusted, masked, never-cited guidance. New Alembic revision. | `features/application-operating-notes/25_APPLICATION_OPERATING_NOTES.md` |
| B3 Why were these alerts grouped | A localised sentence on alert groups, derived at read time from the real grouping reason. No schema change. | `features/alert-grouping-reason/26_ALERT_GROUPING_REASON.md` |

| **B5 Ask Keigan, phases 1 and 2 (investigation chat)** | The investigation page's chat runs on the new engine: eight read-only tools, a live tool-call trace (Running, Done, Failed, Stopped), citations `[T#] [E#] [R#]`, Stop, history, copy answer with sources, "Show tool details" switch, specific error messages. Two trace tables (revisions `a7c3e9f1b5d2`, `c5e7a9b3d1f4`). Independently reviewed twice (backend, frontend); every finding fixed except those in section 7. **Only with the mock model.** The Teams bot and the old global chat still use the old engine until phases 4 and 3. | `features/ask-keigan-chat/23_ASK_KEIGAN_CHAT_SPEC.md` (sections 13 and 14) |

Earlier and already pushed: team members with invitations and roles (doc 20), the hardening waves (docs 16, 17, 19), the demo seed for every team status, and Azure SQL demo data.

## 3. Designed, not built

| What | Doc | State |
|---|---|---|
| **Ask Keigan phases 3 to 5**: the global chat on the same engine (tools 9 to 19, charts, old router removed), the prompted-JSON fallback and conformance suite, the Teams bot on the new engine, later sources | `features/ask-keigan-chat/23_ASK_KEIGAN_CHAT_SPEC.md` section 13 | Spec approved by the owner on 2026-11-21 (decisions D1 to D6 in it). Phases 1 and 2 are built (section 2). |
| **AI evaluation harness**: score real-model investigations against known scenarios | `features/ai-evaluation-harness/22_AI_EVALUATION_HARNESS_SPEC.md` | **Design only, by decision.** The owner is prioritising features. Six open questions are in the doc; the first two (real models, budget) are needed only before the first real-model run. |
| Semantic retrieval for knowledge | `features/semantic-retrieval/08_RAG_PROPOSAL.md` | Future; today retrieval is keyword ranking. Revisit when the harness shows misses caused by synonyms or mixed Japanese and English. |

## 4. What to build next, in order, and when

| Order | Item | Size | Build when | Depends on |
|---|---|---|---|---|
| 0 | ~~Commit~~ **Committed locally 2026-11-22** (five commits). Push the branch | S | When the owner says | Nothing |
| 1 | ~~Fix the investigation-chat access gap~~ **Done 2026-11-21**: current read access is now checked on every read and send of an investigation chat (4 tests). Committed on keigan-ui-ux | S | Done | Nothing |
| 2 | **B5 Ask Keigan** (doc 23): phases 1 and 2 **done 2026-11-21**; next phase 3 (global chat), then 4 (providers, Teams) | M to L | Phase 3 next, when the owner says | Phases 1 and 2 |
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
| Keigan AI chat (global scope): a person who lost access to an application can still re-read earlier answers that used its data | `chat_service.py` `get_conversation` | Found 2026-11-21 while fixing the investigation chat. New questions are already limited to readable applications. Fix inside B5: store which applications each answer used and hide an answer when the reader has lost access to any of them |
| Hard-coded limits remain in the legacy global chat path (`chat_service.py`: lookback and similar) | `chat_service.py` | The investigation chat limits are settings now. The global ones go away with the old router in Ask Keigan phase 3 |
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
| A failed Azure Activity Log read says "could not be checked", not "no changes found" | `tests/integration/services/test_evidence_service.py` |
| `openai_compatible` with managed identity now gets an Entra token provider | `tests/integration/ai/test_llm_gateway.py` |
| Investigation page shows the same translated grouping sentence as the Alerts page | `tests/integration/services/test_investigation_service.py` |
| Fallback group summary no longer states a stale alert count (demo SQL regenerated) | `tests/unit/ai/test_alert_ai_schemas.py` |
| The two SLO window tests no longer clear the settings cache | `tests/integration/services/test_slo_service.py` |
| `ensure_utc` has typed overloads (a real date gives a real date), so the type checker no longer flags its callers | `mypy keigan/utils/time_utils.py` clean |
| The administration page shows a number or a flag even when its name contains "token" (token budgets); real secrets stay masked | `tests/unit/config/test_settings.py` |
| Every Ask Keigan setting (24 incl. the model-capability overrides) is in `backend/.env`, `backend/.env.example` and the Helm `backendEnvironment`, one comment line each, defaults equal to `settings.py` (2026-11-22) | `tests/unit/config/test_ask_keigan_deployment_settings.py` (49 tests) |
