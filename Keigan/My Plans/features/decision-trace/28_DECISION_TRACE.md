# 28 — Decision trace: one screen that replays how an investigation reached its outcome

Roadmap item **A3** (doc 21, product research, section 3.5). Written 2026-11-22 against branch `keigan-ui-ux` (head commit `556c4bf`, Alembic head `b8d4f2a6c0e3`).

---

## 1. Purpose, status and how to use this document

**Purpose.** For every investigation, record and show in order what Keigan did and why: the inputs it started from (incident, windows, services, settings), the evidence it collected and the sources it could not read, every AI call (which prompt and version, the prompt hashes, provider, model, tokens per attempt, what went in by section, the raw answer and what Keigan's checks changed in it), the deterministic decisions (services chosen, priority, planner, evidence kept, fallbacks), the hypotheses that were rejected and why, and the outcome. A person reviewing an incident, an auditor, or the evaluation harness (doc 22) can then reconstruct the reasoning instead of trusting a summary (doc 21, 2.6: "reasoning that can be reconstructed afterwards").

**Status.** Design, written 2026-11-22; not built. Every statement about existing code was read in the source on 2026-11-22 and carries a `path:symbol` reference.

**How to use it.**
- Owner: read sections 2, 4.1 (decisions, especially D-A3-1 and D-A3-4), 5 and 11.
- Builder: **build doc 27 (A2, honest outcomes) first**; this spec shows A2's states and guards (section 4.9). Then follow section 9.
- Related documents: doc 06 (AI engine), doc 21 (2.6, 3.1 point 5), doc 22 (evaluation harness: seams S1 and S2 in its section 6 are built here and reused there), doc 23 (Ask Keigan: sections 6 and 9.6, the trace model this one borrows from), doc 24 (reliability metrics: the price table), doc 27 (A2).

**Glossary.**

| Term | Meaning |
|---|---|
| Trace step | One ordered row of an investigation's decision trace: inputs, an AI call, the evidence summary, a deterministic decision, or the outcome. |
| AI call | One `InvestigationAiCaller.ask` (triage, planner, one hypothesis, synthesis, blast radius narrative, communications drafts). May have several attempts (the gateway's repair retry). |
| Attempt | One model request, as recorded today in `llm_usage_record` (outcome `succeeded`, `failed` or `validation_retry`). |
| Input manifest | Per AI call, one entry per prompt section: title, source, sizes, whether it was cut, the SHA-256 of what was sent, the citation codes it contained. Not the text (D-A3-2). |
| Raw output | The model's validated structured answer **before** Keigan's cleaning (citation removal, path restriction, risk raising, A2's guards), masked and size-limited. |
| Adjustment | One thing Keigan's code changed in a raw output, with a code and small parameters (for example "citation E14 removed: it does not exist"). |

---

## 2. Goals, non-goals, anti-goals

### 2.1 Goals
1. **G1. One screen replays an investigation** (doc 21, A3 "done when"): a new "Decision trace" tab on the investigation page, steps in order, each expandable.
2. **G2. Reproducibility facts per AI call**: prompt key and version, a hash of the prompt template **including its fragments** (catches an edited prompt whose version was not bumped), a hash of the exact system message, provider, model, tier, tokens per attempt, latency, failures.
3. **G3. Inputs by reference, verifiable by hash**: evidence by id and code, knowledge and runbooks by code, every section by size and SHA-256.
4. **G4. The model and the rules kept apart**: the raw answer beside the list of adjustments and A2's guard decisions, so a reader can see what the AI said and what Keigan changed.
5. **G5. Rejected hypotheses and the outcome** with reasons (from A2).
6. **G6. A durable summary** that outlives the investigation: one `audit_event` per finished or failed run.
7. **G7. Reuse, not a second system**: the same conventions and helpers as the Ask Keigan trace (doc 23, section 6), the existing `llm_usage_record` rows for tokens, and the evaluation harness's planned seams (doc 22, S1 and S2).

### 2.2 Non-goals
- No re-execution ("run it again with another model") from the screen. Re-running exists (`POST /investigations/{id}/rerun`); counterfactual replay is the harness's job (doc 22).
- No storage of full prompt text (D-A3-2; open question 1).
- No export to OpenTelemetry or Application Insights in v1; the mapping is written down (4.10) so it is a later exporter.
- No trace of Ask Keigan answers inside this screen: those are personal and owner-only (doc 23, D3).
- No cross-investigation trace search or admin browser.
- No change to how investigations run, other than recording.

### 2.3 Anti-goals

| Anti-goal | Control | AC |
|---|---|---|
| A trace that shows something other than what the model saw | Section hashes are computed from the exact content the gateway sends (after its truncation, before the random spotlight boundary); the system-message hash uses the same function the gateway uses to build the message | AC-3, AC-4 |
| A trace that leaks data the investigation page does not | Only masked, size-limited data is stored; the trace is read with the investigation's own access check; the raw output is limited to admins (D-A3-4) | AC-10, AC-11 |
| Unchecked model commands copied from the raw output | Raw output is admin-only, shown as escaped JSON with a warning, never with copy buttons or command formatting | AC-11, AC-17 |
| Recording slows or breaks an investigation | Rows are added to the session the runner already commits per stage; a recorder error is logged and never fails the run | AC-8 |
| Token totals that silently miss calls | Tokens are read from `llm_usage_record` at view time; the run's own totals are computed after the gateway's pending usage rows are flushed (seam S2) | AC-6, AC-7 |

---

## 3. Current state (verified 2026-11-22)

| Topic | Fact | Evidence |
|---|---|---|
| Investigation run | One `background_job` of type `run_investigation` (deduplication key `run_investigation:{id}`) calls `InvestigationService.run_investigation` → `InvestigationGraphRunner.run`. There is **no step table**: progress is the English list `investigation.stage_messages_json` and the current stage and percent. A failure rolls back and stores a generic `failure_reason` with the correlation id. | `backend/keigan/services/investigation_service.py:InvestigationService.start_investigation`, `_run`; `backend/keigan/workers/job_handlers.py`; `backend/keigan/ai/investigation_graph.py:_update_progress` |
| AI calls | Every investigation AI call goes through `InvestigationAiCaller.ask`: it renders the prompt, calls `LlmGateway.generate_structured` (or an offline factory), counts estimated tokens only for mock and offline runs, and keeps the set of model names. Communications drafted inside the run use the same `ask`. | `backend/keigan/ai/investigation_ai_caller.py:InvestigationAiCaller.ask`; `investigation_graph.py:communications_node`; `backend/keigan/services/communication_service.py:draft_investigation_communications` |
| What is stored per run | Total input and output tokens and `model_names_json` on `investigation`; evidence rows with query text, time range, counts; hypothesis rows; triage JSON; knowledge references. **No prompt key, version or hash anywhere; the synthesis's leading-perspective reason is dropped (fixed by doc 27).** | `backend/keigan/entities/incident_entities.py:Investigation`, `InvestigationEvidence`, `InvestigationHypothesis`; `investigation_graph.py:_complete` |
| Prompt versions | Hand-written `version:` in each prompt's front matter; `PromptLibrary.version_of`. Fragments (`_hypothesis_body.md`) are included with Jinja `{% include %}`, so editing a fragment changes three prompts without changing any version. | `backend/keigan/ai/prompt_library.py:PromptLibrary.load_template`, `version_of`; `resources/prompts/hypothesis_*.md` |
| Prompt hashes | Only logged, at DEBUG level, as the SHA-256 of all message text (including the random spotlight boundary, so it never repeats). | `backend/keigan/ai/llm_gateway.py:LlmGateway._log_prompt` |
| Usage rows | `llm_usage_record`: application, investigation and conversation ids (no foreign keys), feature name, provider, model, tier, input, output and cached tokens, latency, outcome (`succeeded`, `failed`, `validation_retry`), error message, requester, time. One row **per attempt**. Written by a background task after a 2-second delay (`USAGE_FLUSH_DELAY_SECONDS`), so a caller that reads them right away can miss the latest. The mock provider writes none. No index on `investigation_id`. | `backend/keigan/entities/platform_entities.py:LlmUsageRecord`; `llm_gateway.py:_record_usage`, `_flush_usage_records`, `generate_structured` |
| **Likely bug** | `_complete` sums usage rows by investigation id immediately after the communications call, before the background flush has written the last attempts, so `total_input_token_count` and `total_output_token_count` probably understate real runs. Not proven by a test (no real provider is run here); seam S2 (4.3) fixes it either way. | `investigation_graph.py:_complete`; `llm_gateway.py:USAGE_FLUSH_DELAY_SECONDS` |
| Ask Keigan trace | Two tables, `chat_answer_run` and `chat_run_step`, with prompt key and version, `system_prompt_sha256`, provider, model, tier, tool-calling mode, limits, token totals, per-step masked model view and its SHA-256, outcome codes. A run requires a conversation and a user message (non-null foreign keys), has one-running-per-conversation and stale-run logic, and is readable by the conversation owner only (doc 23, D3). An `audit_event` `chat.answer` summarises each run. | `incident_entities.py:ChatAnswerRun`, `ChatRunStep`; `backend/keigan/services/ask_keigan_trace.py`; `ask_keigan_answer_access.py:AnswerAccess` |
| Access | Investigation reads check read access to the application on every call; re-run and the "correct" verdict need application admin. Keigan admins read every application. | `investigation_service.py:load_readable_investigation`, `rerun`, `submit_feedback`; `backend/keigan/services/authorization_service.py` |
| Retention | Investigations and everything keyed to them are deleted with expired incidents (`INCIDENT_RETENTION_DAYS`, 395) or, standalone, after the same age. Audit and usage rows are kept 400 days. | `backend/keigan/services/incident_retention.py:_delete_investigations`; `administration_service.py:run_retention_cleanup` |
| Harness seams (designed, not built) | Doc 22 plans S1, a call observer on `InvestigationAiCaller` passed through `InvestigationGraphRunner(ai_call_observer=...)`, and S2, `LlmGateway.flush_pending_usage_records()`, plus prompt hashing including fragments for its pins. | doc 22, section 6 (table of seams) and AC-13 |
| Hard-coded threshold seen | The planner runs when fewer than **2** strong signals were found (`strong_count < 2` literal). Recorded by this trace; making it a setting is left to the owner (11.2). | `investigation_graph.py:evidence_node` |

**What the research doc says that is not quite right.** Doc 21, 3.2 says "Per-call usage rows are linked to the investigation, so cost per investigation can be computed today." True, with the flush caveat above; and the rows cannot be tied to a stage or a prompt version, which is what a trace needs.

**Unknowns.** (1) Real providers' token reporting per attempt (only mock and scripted gateways run here). (2) Whether LangGraph's three parallel hypothesis nodes ever interleave `session.add` with an `await` in a way that matters; today they already share the session, and adds are synchronous. (3) The size of real raw outputs (the setting in 4.6 bounds it).

---

## 4. Design

### 4.1 Decisions

**D-A3-1. Investigations get their own step table; the conventions and helpers are shared.** *Decision (made while the owner was away, revisit if wrong).*

| Option | Verdict | Why |
|---|---|---|
| Reuse `chat_answer_run` / `chat_run_step` | Rejected | A run requires a conversation, a user message and a client request id (non-null keys); one-running-per-conversation, stale-run sweeps, cancellation and `AnswerAccess` are chat semantics. Making them optional would weaken every chat guarantee to fit a pipeline that has none of them. |
| A new shared "AI run" model and migrating the chat tables into it | Rejected | Rewrites two built, reviewed tables and their code for no user-visible gain; risky migration. |
| **New `investigation_trace_step`, keyed to `investigation`** | **Chosen** | The investigation row already is the run (status, times, windows, tokens, models). One step table adds what is missing. It reuses: the column names and meanings of `chat_answer_run` (`prompt_key`, `prompt_version`, `system_prompt_sha256`, `provider_name`, `model_name`, `model_tier`, `started_at`, `completed_at`, `duration_milliseconds`), the "recorded fact, no foreign key" rule, the truncated-output format (`ask_keigan_trace.py:TRUNCATED_OUTPUT_KEY`), the per-attempt `llm_usage_record` rows, and one prompt-hash helper used by both traces and the harness. |

**D-A3-2. Inputs are recorded by manifest and hash, not by text.** Each AI call stores, per section, its size, cut flag, SHA-256 and citation codes; the content itself already lives in evidence rows, knowledge references, runbooks and the incident. *Why:* the evidence index alone can be 60,000 characters and is sent to five calls; copying it per call multiplies stored customer telemetry with no new information, and the hash still proves whether a rebuilt input matches. *Rejected:* storing the masked section text like Ask Keigan's `model_view_text` (that is per tool call and small). *Consequence, said plainly:* the knowledge section is built from documents that can change later, so a faithful byte-for-byte replay of it is possible only while the documents are unchanged; the hash tells which. Open question 1.

**D-A3-3. Tokens come from `llm_usage_record`, linked by a step id.** `LlmUsageContext` gains `trace_step_id`; the gateway writes it into a new nullable `llm_usage_record.investigation_trace_step_id`. The trace sums attempts per step at read time. Mock and offline runs (no usage rows) store the caller's estimates on the step, flagged as estimates. *Rejected:* copying token counts onto the step (the gateway does not return them to the caller, and attempts would be lost).

**D-A3-4. Access: readers of the application see the trace; raw outputs need admin.** *Decision (made while the owner was away, revisit if wrong).* The trace is part of the investigation, which the application's team shares: anyone who can read the investigation (`load_readable_investigation`) can read its trace, because the people who must trust a conclusion are the responders, not only its requester. The **raw output** of an AI call is readable only by an application admin of that application or a Keigan admin. *Why the split:* the raw output is the uncleaned answer, which can contain commands before risk classification, invented file paths or citations Keigan removed; it is for review and audit, not for action. *Rejected:* owner-only as in doc 23 D3 (an automatic investigation's requester is the system; chat traces are personal, investigations are not); Keigan-admin-only (application admins own their operating notes, runbooks and the "correct" verdict, so they are the right reviewers); everything for every reader (copyable unchecked commands).

**D-A3-5. Recording rides on the runner's own session and commits.** The runner already commits after every stage (`_update_progress`); trace rows are added to the same session and commit with the stage, so the trace and the visible progress never disagree. A recorder exception is caught, logged with the investigation id, and recording stops for that run (the run continues; the trace shows "incomplete"). *Rejected:* separate short sessions per write as in Ask Keigan (needed there for streaming; here nothing streams, and per-stage commits already exist).

**D-A3-6. One durable audit row per run.** `audit_event` `investigation.concluded` (or `investigation.failed`) with codes and counts only. Audit rows are kept 400 days, incidents 395, so the summary outlives the trace.

### 4.2 Data model

New enums in `backend/keigan/entities/status_values.py`:

| Enum | Values |
|---|---|
| `InvestigationTraceStepKind` | `inputs`, `ai_call`, `evidence`, `decision`, `outcome` |
| `InvestigationTraceStepStatus` | `succeeded`, `failed`, `skipped` |
| `InvestigationDecisionKind` | `services_selected`, `priority_set`, `planner_requested`, `evidence_only_mode`, `synthesis_fallback` |
| `InvestigationAiCallFailure` | `token_budget_exceeded`, `ai_unavailable`, `ai_rate_limited`, `ai_output_invalid`, `failed` |
| `InvestigationTraceAdjustment` (values inside JSON, no column, no CHECK, like `AlertGroupingReason`) | `invalid_citations_removed`, `evidence_codes_dropped`, `file_path_replaced`, `command_risk_raised`, `candidate_services_dropped`, `runbook_code_dropped`, `confidence_capped`, `hypothesis_state_guarded`, `outcome_guarded` |

**New table `investigation_trace_step`** (entity `InvestigationTraceStep` in `incident_entities.py`, beside `InvestigationHypothesis`).

| Column | Type | Notes |
|---|---|---|
| `trace_step_id` | String(36) PK | allocated by the recorder **before** an AI call, so usage rows can carry it |
| `investigation_id` | FK `investigation` ON DELETE CASCADE | unique with `sequence_number` |
| `sequence_number` | Integer | order of completion, 1, 2, 3… |
| `stage_name` | String(30), CHECK `InvestigationStage` | the blast radius belongs to `synthesis`, as in today's progress |
| `step_kind` | String(20), CHECK | |
| `step_status` | String(20), CHECK | |
| `decision_kind` | String(40), CHECK, nullable | decision steps only |
| `started_at`, `completed_at`, `duration_milliseconds` | DateTime, DateTime, Integer | |
| `feature_name` | String(80), nullable | AI calls: the prompt key the caller used (open, like `llm_usage_record.feature_name`) |
| `prompt_key`, `prompt_version` | String(80), String(20), nullable | `PromptLibrary.version_of` |
| `prompt_template_sha256` | String(64), nullable | `PromptLibrary.template_sha256` (4.3): the file plus its included fragments |
| `system_prompt_sha256` | String(64), nullable | of the exact system message text sent (`LlmGateway.system_message_text`) |
| `provider_name`, `model_name`, `model_tier` | String(40), String(120), String(20), nullable | `offline` / `offline-factory` for seeded runs, `mock` for the mock provider |
| `input_manifest_json` | JSON, nullable | list of `{title, sourceLabel, isUntrusted, isFlagged, characterCount, sentCharacterCount, isTruncated, sha256, citationCodes}` |
| `estimated_input_token_count`, `estimated_output_token_count` | Integer, nullable | only when the call wrote no usage rows (mock, offline) |
| `raw_output_json` | JSON, nullable | the validated answer before cleaning, masked with the run's masker; cut to `INVESTIGATION_TRACE_RAW_OUTPUT_STORED_CHARACTERS` in the Ask Keigan format `{"truncated_output_text": "…"}` |
| `raw_output_character_count`, `raw_output_is_truncated`, `raw_output_sha256` | Integer, Boolean, String(64), nullable | SHA-256 of the masked JSON text before cutting |
| `adjustments_json` | JSON, nullable | `[{"code": "invalid_citations_removed", "parameters": {"codes": ["E14"]}}, …]` |
| `failure_code` | String(40), CHECK `InvestigationAiCallFailure`, nullable | |
| `hypothesis_id` | String(36), nullable, no FK | the hypothesis row a hypothesis call produced (set after the synthesis flush); a recorded fact, no second cascade path |
| `details_json` | JSON, nullable | inputs, evidence, decision and outcome steps (4.4); ids, codes, numbers and catalogue names only |

Indexes: `uq_investigation_trace_step_investigation_id_sequence_number` (unique; also serves reads by investigation).

**Changed table `llm_usage_record`:** new nullable `investigation_trace_step_id` String(36) (no FK, like its other ids); new index `ix_llm_usage_record_investigation_id` (the trace and `_complete` read by it; today it is a scan).

**Size per investigation:** about 15 steps (1 inputs, 1 evidence, up to 5 decisions, up to 8 AI calls: triage, planner, three hypotheses, synthesis, blast radius, communications; 1 outcome). Raw outputs are the large part: at most 8 × the setting (default 20,000 characters).

**Alembic revision** (on top of doc 27's revision; file `<date>_<rev>_investigation_decision_trace.py`): `create_table investigation_trace_step` with CHECKs rendered from entity metadata, FK and unique index; `add_column llm_usage_record.investigation_trace_step_id`; `create_index ix_llm_usage_record_investigation_id`. No backfill (D-A3-8 below). Downgrade drops them. SQL Server: the four JSON columns are `NVARCHAR(max)`; the single cascade path is investigation → step. Regenerate Azure SQL `02`–`05`, the delta `database/azure_sql/migrations/<rev>_investigation_decision_trace.sql`, demo SQL, ER diagram (doc 15), README counts (tables +1, CHECKs +4, indexes +2). `test_schema_drift.py` must pass.

**D-A3-7. Retention follows the investigation.** `incident_retention.py:_delete_investigations` deletes trace steps before investigations (count key `investigationTraceSteps`). Usage rows keep their step id after the step is gone (kept 400 days for cost reporting, as today). No separate trace retention setting: the investigation's own retention already applies (consistent with doc 23 D4's "nothing extra expires").

**D-A3-8. Investigations before this feature show what can be rebuilt.** No backfill. The trace endpoint returns `isRecorded: false`, the models from `model_names_json`, and the usage rows of the investigation grouped by feature name (tokens, attempts, failures). The screen says "This investigation ran before Keigan kept decision traces; only its AI usage is shown."

### 4.3 Services and modules (one job each)

| Module | Job | Shared with |
|---|---|---|
| `backend/keigan/ai/prompt_library.py` (changed) | `PromptLibrary.template_sha256(prompt_key) -> str`: SHA-256 over the prompt file's bytes, then each template it includes (found with `jinja2.meta.find_referenced_templates` on the parsed source, recursively, de-duplicated, in sorted order), each prefixed by its file name. Cached like `load_template`. | doc 22 pins (its AC-13); doc 23 could record it later |
| `backend/keigan/ai/llm_gateway.py` (changed) | (1) `LlmUsageContext.trace_step_id: str \| None = None`, written by `_record_usage` as `investigation_trace_step_id`. (2) `system_message_text(system_prompt) -> str` (the text `_build_messages` already builds, now one function both use). (3) `sent_section_content(section) -> str`: the content as sent before spotlighting (`sanitize_untrusted_text(content, maximum_characters)` for untrusted sections, the content for trusted ones), used by `_render_prompt_sections` and the manifest, so they cannot disagree. (4) **Seam S2** `flush_pending_usage_records()`: awaits the pending flush task and writes what is queued now. | doc 22 S2 |
| `backend/keigan/ai/investigation_ai_caller.py` (changed) | **Seam S1** as doc 22 defines it, extended: `InvestigationAiCaller(..., call_observer=None)`. `ask` allocates a `trace_step_id` (uuid4) before the call, passes it in `LlmUsageContext`, times the call, and calls the observer **after success and after failure** with `InvestigationAiCall(trace_step_id, feature_name, prompt_key, prompt_version, prompt_template_sha256, system_prompt_sha256, provider_name, model_name, model_tier, prompt_sections, raw_output: dict \| None, failure: Exception \| None, started_at, duration_milliseconds, estimated_input_tokens, estimated_output_tokens)`, then returns or re-raises. Doc 22's recorder ignores failures. An observer exception is logged and swallowed. | doc 22 S1 (superset; doc 22 updated, 10.1) |
| `backend/keigan/services/investigation_trace_recorder.py` (new) | `InvestigationTraceRecorder(session, investigation, masker, settings)`: keeps the sequence counter in memory; `record_inputs(...)`, `record_ai_call(call)` (builds the manifest with `sent_section_content`, masks and cuts the raw output, maps the failure to `InvestigationAiCallFailure`), `add_adjustments(feature_name, adjustments)`, `record_decision(kind, details)`, `record_evidence(evidence_rows, gaps, kept, left_out)`, `link_hypotheses(rows_by_perspective)`, `record_outcome(...)`, `record_failure(stage, correlation_id)`. Rows are `session.add`-ed; the runner's stage commit writes them. Every public method is wrapped: on an exception it logs and sets `is_recording=False` (D-A3-5). | — |
| `backend/keigan/ai/investigation_graph.py` (changed) | Creates the recorder and passes `recorder.record_ai_call` as the caller's observer (chained with an outer `ai_call_observer` keyword, doc 22's). Records: inputs after `_load_inputs`; `services_selected` and `priority_set` in `triage_node`; `planner_requested` in `evidence_node` (strong count, threshold, queries planned and run); the evidence step in `finalize_evidence_node` (counts by A2 check outcome, evidence ids, gap ids, kept and left out, token budget); `evidence_only_mode` when it switches (with the reason); adjustments from `_validated_hypothesis`, the triage filter and `synthesis_node` (removed citation codes are the difference between `find_citation_codes` of the raw and cleaned text; A2's `StateDecision` and `OutcomeDecision`; the confidence cap from and to); `synthesis_fallback`; hypothesis links after the synthesis flush; the outcome step and the audit row in `_complete` **after `flush_pending_usage_records()`**, which also fixes the token totals (section 3). | |
| `backend/keigan/services/investigation_service.py` (changed) | `_run`'s failure branch calls `record_failure` after the rollback (the AI calls of the stage that failed were rolled back with it; their usage rows remain and appear as calls without a step, 4.5) and writes the `investigation.failed` audit row. | |
| `backend/keigan/services/investigation_trace_service.py` (new) | Read model. `get_trace(current_user, investigation_id) -> InvestigationTraceView` (reader check, steps, usage rows by investigation grouped by step id, A2 fields, cost); `get_raw_output(current_user, investigation_id, trace_step_id)` (admin check). Cost uses the metrics page's price table and function (`backend/keigan/services/reliability_metrics.py:summarize_ai_usage`, prices from `LLM_MODEL_PRICES_JSON`): same rule, an unpriced model gives no cost and is named. | doc 24 |
| `backend/keigan/dtos/investigation_trace_dtos.py` (new), `controllers/investigation_controller.py` (changed) | DTOs and the two endpoints (4.5). | |
| `backend/keigan/services/incident_retention.py` (changed) | D-A3-7. | |
| `backend/keigan/seed/investigation_seed.py` (changed) | Shifts the seeded steps' times by the same offset it applies to the investigation's times (it rewrites `created_at`, `started_at`, `completed_at` today). | |

### 4.4 What each step records (`details_json`, ids and codes only)

| Step | Details |
|---|---|
| `inputs` (stage `triage`) | `pipelineVersion` (new constant `INVESTIGATION_PIPELINE_VERSION` in `investigation_graph.py`, bumped when the graph's order or rules change), `trigger`, `incidentId`, `incidentNumber`, `alertGroupId`, `window` and `baselineWindow` (start, end), `windowWasShortened` (the maximum-window rule in `_load_inputs`), `requestedServiceIds`, `provider` (`name`, `isMock`, `offlineAi`), configured `models` (fast, deep), `settings` (lookback, maximum window, maximum services, maximum checks per service, evidence and knowledge token budgets, A2's two thresholds, temperature, structured-output method), `operatingNotes` (`present`, `sha256` of the masked notes), `knowledgeReferenceCount` |
| `decision / services_selected` | ids by origin: `fromRequest`, `fromIncident`, `fromTriage` (catalogue names), `fromDependencies`, `fallbackByCriticality`, `selected`, `cut` (beyond the limit), `limit` |
| `decision / priority_set` | `suggested`, `mappedFromServiceNow`, `guardrail` (and the burn-rate rule that produced it), `final` |
| `decision / planner_requested` | `strongSignalCount`, `threshold`, `queriesPlanned`, `queriesRun`, `queriesRejected`, `queriesFailed` |
| `evidence` (stage `evidence`) | `evidenceIds` with codes, counts by `checkOutcome` and `baselineComparison` (doc 27), `coverageGapIds`, `kept`, `leftOut`, `tokenBudget` |
| `decision / evidence_only_mode` | `reason`: `ai_unavailable`, `token_budget_exceeded`, `no_hypothesis_produced`; `stage` |
| `decision / synthesis_fallback` | `failureCode`, `strongestPerspective` |
| `outcome` (stage `completed`) | `status`, `outcome`, `proposedOutcome`, `outcomeGuard` (doc 27), `leadingHypothesisId`, per hypothesis `{hypothesisId, perspective, state, proposedState, stateGuard, confidence}`, `overallConfidence`, `communicationIds` drafted, `durationMilliseconds`; on failure `failedAfterStage`, `correlationId` |

### 4.5 API (base `/api`, camelCase, RFC 9457 errors, doc 05 conventions)

| Method | Path | Access | Response |
|---|---|---|---|
| GET | `/investigations/{id}/trace` | application reader (`load_readable_investigation`) | `InvestigationTraceView` |
| GET | `/investigations/{id}/trace/steps/{stepId}/raw-output` | application admin of the investigation's application, or Keigan admin | `{ "rawOutput": <JSON>, "characterCount": 1234, "isTruncated": false, "sha256": "…" }` |

Errors: `404` investigation or step not found (or the step is not an AI call, or has no raw output); `403` no read access, or not an admin for the raw output (message names the role needed). No write endpoints.

```jsonc
// InvestigationTraceView (also the TypeScript type in frontend/src/api/investigationsApi.ts)
{
  "investigationId": "…", "isRecorded": true, "isComplete": true,      // isComplete false while running or when recording stopped
  "pipelineVersion": "1", "status": "completed",
  "outcome": { /* doc 27 shape */ },
  "totals": { "inputTokenCount": 51234, "outputTokenCount": 6120, "tokenCountsEstimated": false,
              "aiCallCount": 8, "attemptCount": 9, "failedAttemptCount": 1, "durationMilliseconds": 182000,
              "estimatedCost": 0.42, "unpricedModels": [] },                // estimatedCost null when no price is configured
  "models":  [ { "providerName": "azure_openai", "modelName": "…", "modelTier": "deep", "callCount": 6 } ],
  "prompts": [ { "promptKey": "rca_synthesis", "promptVersion": "4", "promptTemplateSha256": "…" } ],
  "steps": [ {
      "traceStepId": "…", "sequenceNumber": 4, "stageName": "hypotheses", "stepKind": "ai_call", "stepStatus": "succeeded",
      "decisionKind": null, "startedAt": "…", "completedAt": "…", "durationMilliseconds": 2100,
      "aiCall": { "featureName": "hypothesis_dependencies", "promptKey": "hypothesis_dependencies", "promptVersion": "4",
                  "promptTemplateSha256": "…", "systemPromptSha256": "…", "providerName": "…", "modelName": "…", "modelTier": "deep",
                  "inputTokenCount": 9100, "outputTokenCount": 880, "tokenCountsEstimated": false,
                  "attempts": [ { "outcomeStatus": "validation_retry", "latencyMilliseconds": 900, "inputTokenCount": 4500, "outputTokenCount": 400 }, … ],
                  "inputSections": [ { "title": "Evidence index", "sourceLabel": "telemetry evidence", "isUntrusted": true, "isFlagged": false,
                                       "characterCount": 18210, "sentCharacterCount": 18210, "isTruncated": false, "sha256": "…", "citationCodes": ["E1","E2"] } ],
                  "adjustments": [ { "code": "hypothesis_state_guarded", "parameters": { "proposed": "supported", "final": "inconclusive", "guard": "support_not_in_evidence" } } ],
                  "hasRawOutput": true, "rawOutputCharacterCount": 3400, "rawOutputIsTruncated": false, "failureCode": null, "hypothesisId": "…" },
      "details": null } ],
  "hypotheses": [ { "hypothesisId": "…", "perspective": "dependencies", "title": "…", "state": "ruled_out", "proposedState": "ruled_out",
                    "stateGuardCode": null, "stateReasonMarkdown": "…", "confidence": 0.1, "isLeading": false,
                    "supportingEvidenceCodes": [], "contradictingEvidenceCodes": ["E4"] } ],
  "evidence": [ { "evidenceId": "…", "evidenceCode": "E4", "title": "…", "checkOutcome": "no_signal", "baselineComparison": "compared", "signalStrength": "low" } ],
  "coverageGaps": [ /* doc 27 shape */ ],
  "callsWithoutStep": [ { "featureName": "incident_communications", "modelName": "…", "createdAt": "…", "inputTokenCount": 1200, "outputTokenCount": 640, "outcomeStatus": "succeeded" } ]
}
```

`callsWithoutStep` lists this investigation's usage rows whose step id is null or names no stored step: later drafts and the postmortem (run after the investigation), Teams digests, or the calls of a stage that failed and was rolled back. Each is labelled by feature.

### 4.6 Settings

| Setting | Default | Range | Meaning |
|---|---|---|---|
| `INVESTIGATION_TRACE_RAW_OUTPUT_STORED_CHARACTERS` | `20000` | 1000 to 200000 | Characters of one AI call's raw output kept in the trace; longer ones are cut and marked |

In `backend/keigan/config/settings.py`, `backend/.env.example` and the Helm `backendEnvironment`, one comment line each. No other limit is needed: the number of steps is bounded by the pipeline.

### 4.7 AI prompts
None. The trace records prompts; it adds none and changes none.

### 4.8 Audit
- `investigation.concluded` written in `_complete`: actor `requested_by_user_principal_name` or `system:worker`, target `investigation`, `application_id`, `action_details`: `status`, `outcome`, `proposedOutcome`, `outcomeGuard`, `hypothesisStates` (perspective → state), `modelNames`, `promptVersions` (key → version), `traceStepCount`, `inputTokenCount`, `outputTokenCount`, `coverageGapCount`. Masked by `AuditService.record` as every audit row.
- `investigation.failed` in `_run`'s failure branch: the same keys known at that point plus `failedAfterStage`.
- Reading a trace writes no audit row (reading an investigation writes none today); open question 3.

### 4.9 Dependency on doc 27 (A2), both ways
- **A3 needs from A2:** the proposed and final states and outcome with guard codes; the `StateDecision` and `OutcomeDecision` objects in memory at the stage commit (recorded as `hypothesis_state_guarded` and `outcome_guarded` adjustments); coverage gap rows with ids written in `finalize_evidence_node`; `check_outcome` and `baseline_comparison` on evidence; ruled-out and inconclusive hypotheses stored as rows. Built before A2, this screen would show "not recorded" in the hypotheses, gaps and outcome panels.
- **A2 needs from A3:** nothing. A2 is complete alone.
- Shared: A3's inputs step snapshots A2's two threshold settings, so a later change of thresholds is visible per investigation.

### 4.10 Replay and mapping to other systems
- **Reading replay (this screen):** steps in order with their inputs by reference and hash, the raw answer, the adjustments and the result.
- **Faithful replay (doc 22, not built here):** rebuild each AI call's sections from stored rows (evidence via `render_evidence_markdown`, runbooks, incident text), compare each section's SHA-256 with the manifest, and re-ask with the same prompt version or a new one. Sections whose hash no longer matches (typically knowledge after a document changed) are reported as "input changed since the run".
- **OpenTelemetry GenAI mapping (later exporter):** investigation ↔ an `invoke_agent` span (`gen_ai.agent.name = keigan.investigation`); an `ai_call` step ↔ an inference span (`gen_ai.operation.name = chat`, `gen_ai.request.model`, `gen_ai.usage.input_tokens` and `output_tokens` from the attempts, `error.type = failure_code`); `decision`, `evidence` and `outcome` steps ↔ internal spans with their codes as attributes. Keigan's names stay its own.

---

## 5. User experience

### 5.1 Where
A new tab **"Decision trace"** on the investigation page (`InvestigationPage.tsx` `tabKeys`: `trace` after `postmortem`, before `teams`), component `features/investigations/components/DecisionTraceSection.tsx`. Loaded only when the tab opens (`useInvestigationTrace(investigationId, enabled)`), refetched when the progress query's stage or percent changes while the investigation runs.

### 5.2 Layout (top to bottom)
1. **Summary strip** (`TraceSummary.tsx`): outcome badge (doc 27's `OutcomeBadge`), models used, duration, tokens in and out (with "estimated" when so), attempts and failed attempts, estimated cost or "No price configured for {{model}}", and a "Download trace (JSON)" button that saves the view as shown (never the raw outputs).
2. **Prompts used**: a compact table of prompt key, version and template hash (first 12 characters, a copy button for the full value). A warning chip "Edited without a version change" when the same key and version appear with two different template hashes **across this application's last 50 investigations** (one query on the trace table, by application through investigation; cheap and catches the forgotten version bump).
3. **Steps** (`TraceStepList.tsx`): an ordered list. Each step is a disclosure row with stage, kind icon, plain-words title (for example "Analyst: dependencies (AI)", "Services chosen", "Evidence collected", "Outcome"), status, duration and a one-line result ("Ruled out, 10%", "14 evidence items, 2 sources not read"). Expanded:
   - **AI call** (`TraceAiCall.tsx`): prompt key, version and both hashes (copyable); provider, model, tier; attempts table (outcome, latency, tokens); **Inputs** table (section, source, trusted or untrusted, characters sent, cut, hash, the citation codes as chips linking to evidence, runbooks and knowledge on their tabs); **What Keigan changed** (adjustments as translated sentences, for example "Removed citation E14: no such evidence", "State changed from Supported to Inconclusive: none of the cited evidence changed from the baseline"); **Result** link (the hypothesis card, the RCA); **Raw answer** button for admins (`RawOutputDialog.tsx`), hidden for readers with the caption "Raw AI answers are visible to application admins."
   - **Decision**: its details as a definition list with translated labels; service ids shown as names (current names, with "removed service" for missing ones).
   - **Evidence**: counts by check outcome and baseline, the coverage gaps (doc 27's sentences), links to the Evidence tab.
   - **Outcome**: final and proposed outcome, the hypotheses table (perspective, state, proposed state, guard, confidence, leading), "Rejected hypotheses" first-class: ruled-out ones with their reason.
4. **Calls without a step**: a small table, with the explanation from 4.5.

### 5.3 States
- **Loading:** skeleton rows. **Error:** the shared `ErrorState` with retry; a `403` on the raw output shows "Only application admins can see raw AI answers."
- **Running:** steps recorded so far, a "Still running" row at the end.
- **Not recorded (before this feature):** the caption from D-A3-8, the usage table grouped by feature, model names.
- **Incomplete** (recording stopped, `isComplete: false` after completion): a warning banner "Part of this trace could not be recorded. The investigation itself is not affected. Reference {{correlationId}}."
- **Failed run:** the steps up to the failure, the outcome step with "Failed after {{stage}}", calls without a step labelled "did not finish".
- **Evidence-only:** the `evidence_only_mode` decision with its reason; no hypothesis or synthesis steps.

### 5.4 Keyboard, screen reader, phone
- The steps are an `<ol>`; each row is a button with `aria-expanded` and `aria-controls`; "Expand all" and "Collapse all" buttons; Enter and Space toggle. Each row's accessible name reads like "Step 4 of 15. Analyst, dependencies. AI call. Succeeded. 2.1 seconds. Ruled out." Hashes have `aria-label` "SHA-256 {{first 12 characters}}, copy full value". Copy confirmations use the existing polite live region.
- The raw output dialog is the shared dialog (focus trapped, Escape closes), content in a `<pre>` of escaped JSON with a warning header "Before Keigan's checks. Do not run commands from here; use the checked fix on the Root cause tab." No copy buttons, no markdown rendering, no links.
- Phone (390 px): the summary strip wraps into two columns; tables become stacked definition lists; hashes show 8 characters; buttons 44 px.

### 5.5 Locale key groups (six locales; es-MX falls back to es)
`investigations.json`: `tabs.trace`; `trace.summary.*` (models, duration, tokens, estimated, attempts, failedAttempts, cost, noPrice, download); `trace.prompts.*` (title, key, version, templateHash, editedWithoutVersion); `trace.step.kind.<kind>`, `trace.step.status.<status>`, `trace.step.title.<feature or decision>`, `trace.step.ofTotal`; `trace.decision.<decisionKind>.*` (labels of each details field); `trace.aiCall.*` (attempts, inputs, trusted, untrusted, cut, changed, result, rawAnswer, rawAnswerAdminsOnly, rawWarning); `trace.adjustment.<code>`; `trace.failure.<failureCode>`; `trace.outcome.*` (rejected, failedAfter); `trace.callsWithoutStep.*`; `trace.state.notRecorded|running|incomplete`; `trace.expandAll|collapseAll|copyHash`. `npm run check:locales` must pass.

---

## 6. Safety, access and privacy
- **Access** (D-A3-4): trace for readers of the investigation's application (checked on every request, so a person who lost access is refused, as for the investigation itself); raw outputs for that application's admins and Keigan admins. Keigan admins read every application (existing rule). Tested per role (AC-10, AC-11).
- **What is stored:** masked, cleaned facts only. Inputs: sizes, hashes, codes; never section text, the spotlight boundary, credentials or provider request bodies. Raw output: masked with the run's masker (one `PiiMasker`, so placeholders match the evidence), cut to the setting. Details: ids, codes, numbers and catalogue names; never exception text (failures are codes; the correlation id points to the log).
- **Display safety:** raw output is escaped text (no `MarkdownView`, no `CommandBlock`); adjustments and decisions are rendered from codes by the screen's own translations; nothing from the trace is sent to a model.
- **Audit:** 4.8. The trace is the detailed record; `audit_event` is the durable summary (as doc 23, 9.6).
- **Retention:** D-A3-7; usage rows and audit rows keep their 400 days.
- **Hash disclosure:** SHA-256 of masked prompt sections reveals nothing practical about their content to a reader who could already read the investigation.

---

## 7. Acceptance criteria

| # | Criterion | Test type |
|---|---|---|
| AC-1 | `template_sha256` changes when the prompt file or any included fragment changes by one byte, and is stable otherwise; `_hypothesis_body.md` changes all three hypothesis hashes | unit (`test_prompt_library.py`) |
| AC-2 | Seam S1: the observer receives one call per `ask`, on success and on failure, with the step id that the usage context carried; with no observer, behaviour is unchanged; an observer exception does not fail `ask` | unit (`tests/unit/ai/test_investigation_ai_caller.py`, new) |
| AC-3 | `system_message_text` is the exact text `_build_messages` sends, and the stored `system_prompt_sha256` equals the SHA-256 of it | unit (`test_llm_gateway.py`) |
| AC-4 | Each manifest entry's `sha256` equals the SHA-256 of `sent_section_content`, which is what `_render_prompt_sections` wraps; truncated untrusted sections are flagged | unit |
| AC-5 | Usage rows written for an AI call carry its `investigation_trace_step_id`; a validation retry produces two attempts under one step | integration (`test_llm_gateway.py` with a scripted model) |
| AC-6 | Seam S2: after `flush_pending_usage_records()` every queued row is in the database | integration |
| AC-7 | `_complete`'s token totals equal the sum of the run's usage rows (scripted gateway with the real flush delay) | integration (`tests/integration/ai/test_investigation_decision_trace.py`, new) |
| AC-8 | A recorder that raises on every call leaves the investigation `completed` with the same RCA, and the trace reports `isComplete: false` | integration |
| AC-9 | An offline run records: one `inputs` step, `services_selected`, `priority_set`, one `evidence` step, three hypothesis calls linked to their hypothesis rows, synthesis, blast radius, communications, one `outcome` step; sequence numbers are 1..n without gaps | integration |
| AC-10 | `GET /trace`: reader `200`; person without access `403`; unknown id `404`; a person whose access was removed `403` | integration (`tests/integration/controllers/test_investigation_controller.py`, new) |
| AC-11 | `GET /raw-output`: application admin and Keigan admin `200`; reader `403`; a non-AI step `404` | integration |
| AC-12 | Adjustments: a scripted hypothesis citing a non-existent code, an unknown file path and a high-risk command records `invalid_citations_removed`, `file_path_replaced` and `command_risk_raised`; a guarded state records `hypothesis_state_guarded` with doc 27's codes; the overall cap records `confidence_capped` with from and to | integration |
| AC-13 | A failed run (exception in synthesis) has the steps of the committed stages, a failed `outcome` step with `failedAfterStage`, an `investigation.failed` audit row, and the rolled-back calls under `callsWithoutStep` | integration |
| AC-14 | `investigation.concluded` audit row has the listed keys and no free text; it remains after incident retention deletes the investigation | integration (`test_incident_retention.py`) |
| AC-15 | An investigation stored before the migration returns `isRecorded: false` with usage grouped by feature | integration |
| AC-16 | Raw output is masked (an e-mail address in a scripted answer is stored as a placeholder) and cut at the setting with the truncated format | integration |
| AC-17 | Frontend: the raw dialog renders escaped text (a scripted `<a href>` shows as text), and has no copy button | browser script |
| AC-18 | Migration creates the table, column and index; downgrade removes them; schema drift passes | integration (`tests/integration/migrations/test_decision_trace_migration.py`, `test_schema_drift.py`) |
| AC-19 | Setting default, range, `.env.example`, Helm | unit (`tests/unit/config/test_settings.py`) |
| AC-20 | Types match the DTOs; locales complete; typecheck and build pass | `test_frontend_contract.py`, `npm run typecheck`, `check:locales`, `build` |
| AC-21 | Browser check at 1440 and 390 px, light and dark: trace tab of a seeded investigation expands a hypothesis call and shows prompt hash, inputs, adjustments and the rejected hypothesis; reader sees no raw-answer button, admin does | script (`frontend/scripts/capture-screens.mjs`) |

---

## 8. Test plan (files mirror `backend/keigan/`)

| File | Covers |
|---|---|
| `backend/tests/unit/ai/test_prompt_library.py` (extend) | AC-1 |
| `backend/tests/unit/ai/test_investigation_ai_caller.py` (new; doc 22 lists the same file for S1) | AC-2 |
| `backend/tests/integration/ai/test_llm_gateway.py` (extend) | AC-3 to AC-6 |
| `backend/tests/unit/services/test_investigation_trace_recorder.py` (new) | manifest building, masking and cutting of raw output, failure mapping, sequence numbers, stop-on-error |
| `backend/tests/integration/ai/test_investigation_decision_trace.py` (new) | AC-7 to AC-9, AC-12, AC-13, AC-16 through the real graph (offline factories and a scripted gateway) |
| `backend/tests/integration/services/test_investigation_trace_service.py` (new) | view assembly, cost with and without prices, `callsWithoutStep`, AC-15 |
| `backend/tests/integration/controllers/test_investigation_controller.py` (new) | AC-10, AC-11 |
| `backend/tests/integration/services/test_incident_retention.py` (extend) | trace steps deleted; AC-14 |
| `backend/tests/integration/migrations/test_decision_trace_migration.py` (new), `test_schema_drift.py` | AC-18 |
| `backend/tests/unit/config/test_settings.py` (extend) | AC-19 |
| `backend/tests/unit/test_frontend_contract.py` (extend) | AC-20 |
| `frontend/scripts/capture-screens.mjs` (add the trace tab as reader and as admin) | AC-17, AC-21 |

---

## 9. Phased build plan (after doc 27 is built)

| # | Task | Size | Depends on | Demonstrable at the end |
|---|---|---|---|---|
| 1 | Enums, `InvestigationTraceStep`, `llm_usage_record` column and index, Alembic revision, Azure SQL scripts and delta, ER diagram, README counts | S | doc 27 merged | Migration up and down on a copy of the demo database |
| 2 | Gateway: `trace_step_id` in the usage context, `system_message_text`, `sent_section_content`, seam S2; `PromptLibrary.template_sha256` | S | 1 | AC-1, AC-3 to AC-6 |
| 3 | Seam S1 in `InvestigationAiCaller` | S | 2 | AC-2 |
| 4 | `InvestigationTraceRecorder` and its wiring in the graph and `_run` (all steps, adjustments, A2 decisions, outcome, audit rows, the token-total fix); seed time shift; retention | M | 3 | AC-7 to AC-9, AC-12 to AC-14, AC-16; seeded investigations have traces |
| 5 | `InvestigationTraceService`, DTOs, endpoints | S | 4 | AC-10, AC-11, AC-15 via HTTP |
| 6 | Frontend tab, components, six locales, capture script | M | 5 | AC-17, AC-20, AC-21 at both widths |
| 7 | Demo SQL regenerated, docs (10.1), smoke run | S | 6 | Smoke run clean |

Build order 1 → 2 → 3 → 4 → 5 → 6 → 7. Total about M.

---

## 10. Docs, migration and demo-data impact

### 10.1 Documents (updated by the lead after the build)
- Doc 03 (the table, the usage column and index), doc 15 (regenerated), doc 05 (two endpoints and the view), doc 06 (section 1: usage context and seams; section 3: recording per stage; prompt hashes), doc 13 (incident to RCA: recorder writes per stage), doc 14 (class diagram: recorder, trace service), doc 01 (the investigation page's new tab), doc 12 and the status page.
- Doc 22: seams S1 (now built, a superset that also reports failures) and S2, and the shared `template_sha256`, are done; its build tasks 1.3 and the S2 part shrink.
- Doc 23: section 6.7 may point to `template_sha256` if the chat trace later records it (not required).
- Doc 09 (learnings): the token totals read before the usage flush.

### 10.2 Azure SQL
Baseline scripts regenerated, delta `<rev>_investigation_decision_trace.sql`, README counts, demo data regenerated. Checked by parser and drift tests only, as today.

### 10.3 Demo data
The seeded offline investigations (eight scenarios plus doc 27's `cause_not_visible` one) produce traces through the real recorder with provider `offline` and model `offline-factory`, estimated tokens flagged, and step times shifted to their historical times. No usage rows are seeded (unchanged decision), so the demo shows estimated tokens and "No price configured". No hand-written trace rows.

---

## 11. Risks, mitigations, open questions

### 11.1 Risks

| Risk | Mitigation |
|---|---|
| Raw outputs grow the database | Bounded by the setting and by about eight calls per investigation; deleted with the investigation |
| Parallel hypothesis calls finish in a different order each run, so sequence numbers differ between runs | The screen shows the stage and perspective, not the number alone; comparisons use feature names |
| A recorder bug hides part of the trace | Stop-on-error with a visible "incomplete" banner; the investigation is unaffected (AC-8) |
| Template hash differs between machines because of line endings | Hash the bytes as stored in git with `.gitattributes` text normalisation; the test runs on the repository's files (AC-1); the builder checks `.gitattributes` covers `*.md` under `resources/prompts` |
| Readers infer cost data the owner considers internal | Cost is already visible to readers on the metrics page (doc 24, scoped to readable applications); same rule here |

### 11.2 Open questions for the owner
1. **Store the masked text of each prompt section?** It would make a faithful replay possible after knowledge documents change, at the cost of several copies of telemetry per investigation (about 100 to 300 KB each). *Recommendation:* no for now; revisit when the harness (doc 22) needs replays of real incidents.
2. **Raw outputs for readers?** Decided admin-only (D-A3-4). Confirm, or open them to readers if your teams prefer full transparency over the copy risk.
3. **Audit trace reads?** Reading an investigation is not audited today, so reading its trace is not either. If compliance wants a record of who looked at raw AI answers, add `investigation.trace.raw_output_view` (one line). *Recommendation:* add it only if compliance asks.
4. **Make the planner threshold a setting?** The planner runs below 2 strong signals (`investigation_graph.py:evidence_node`, a literal). The trace now records it; turning it into `INVESTIGATION_PLANNER_STRONG_SIGNAL_THRESHOLD` is a one-line change. *Recommendation:* yes, in the same build (it is a hard-coded threshold, against the standing rules), unless you want it unchanged.
