# 27 — Honest outcomes: supported, ruled out, inconclusive, and what Keigan could not check

Roadmap item **A2** (doc 21, product research, section 3.5). Written 2026-11-22 against branch `keigan-ui-ux` (head commit `556c4bf`, Alembic head `b8d4f2a6c0e3`).

---

## 1. Purpose, status and how to use this document

**Purpose.** Make every investigation say plainly how far it got. Each hypothesis ends in one of three states (supported, ruled out, inconclusive) with the reason and the evidence that decides it. Each investigation ends in one of three outcomes: *cause identified*, *inconclusive*, or *cause not visible in the data Keigan can see* (doc 21, section 3.6, the ORCA-bench lesson). Each investigation lists what Keigan could not check and why. Each evidence item says whether it was compared with a healthy baseline window, or why it could not be. The Root cause screen, the email and Teams summaries, the communication drafts and the postmortem quote the outcome, so no surface states a cause the investigation did not establish.

**Status.** Design, written 2026-11-22. **Built 2026-11-23** (steps 1 to 7 of section 9; see "Build notes" at the end). Section 3 describes the code as it was before the build. Every statement about existing code below was read in the source on 2026-11-22 and carries a `path:symbol` reference.

**How to use it.**
- Owner: read sections 2, 4.1 (decisions), 5.1 and 11.
- Builder: build in the order of section 9. Section 4 is the design, section 5 the screens, section 7 the acceptance criteria, section 8 the tests.
- Related documents: doc 06 (AI engine and prompt safety, section 3), doc 21 (sections 2.6, 3.1, 3.2, 3.6), doc 22 (evaluation harness: its `is_abstention` switches to this outcome, section 4.3.4 there), doc 23 (Ask Keigan: its investigation tools quote hypotheses), **doc 28 (decision trace, roadmap A3): built after this one; section 4.8 below is the contract between them.**

**Glossary.**

| Term | Meaning |
|---|---|
| Hypothesis state | `supported`, `ruled_out` or `inconclusive`: the end state of one perspective's hypothesis, after Keigan's rules (4.4). |
| Proposed state | What the model said before the rules. Kept beside the final state. |
| Outcome | `cause_identified`, `inconclusive` or `cause_not_visible`: the end of the whole investigation. Null when the investigation ended evidence-only (the AI was unavailable) or failed. |
| Guard | A deterministic rule in code that can **only lower** a state or an outcome (never raise it), with a code saying which rule fired. |
| Check outcome | Per evidence item: `signal` (something was found), `no_signal` (checked, healthy or nothing found: a rule-out), `not_checked` (the source could not be read; only on rows stored before this feature). |
| Decisive signal | An evidence item with check outcome `signal` **and** either a medium or high signal strength (it changed against the baseline) or no baseline exists for its kind of source (a change event, a failing probe). Only decisive signals can support a hypothesis. |
| Coverage gap | One thing Keigan meant to check and could not, or did not because of a limit. Recorded by code, never written by the model. |

---

## 2. Goals, non-goals, anti-goals

### 2.1 Goals
1. **G1. Every hypothesis ends in a state with a reason.** Supported, ruled out or inconclusive, with one or two cited sentences saying why, and a visible note when Keigan's rules changed the model's state.
2. **G2. Inconclusive is a result, not a failure** (doc 21, N2). An investigation that cannot separate the explanations says so, and one that sees nothing abnormal in any source it could read says "cause not visible in the data I can see".
3. **G3. "What I could not check", per investigation**: every source that could not be read (with the reason), every service with no telemetry, every limit that cut a check, every perspective that produced nothing.
4. **G4. Baseline comparison made visible and used.** Each evidence item says whether it was compared with the baseline window; a hypothesis is supported only by evidence that changed against the baseline (or by a source that has no baseline, such as a deployment).
5. **G5. Every surface that quotes a conclusion quotes the outcome first**: the Root cause tab, the incident list, the preliminary-report email and Teams card, the Teams fallback answer, the communication drafts and the postmortem draft.

### 2.2 Non-goals
- No new evidence sources. Code and pipeline evidence stays parked (doc 21, 4.4); the screen states the standing gap in one line instead (5.1).
- No per-hypothesis evidence collection (doc 21, N6, Datadog's lesson). Every perspective still reads the whole evidence index; A1 (doc 22) can measure whether splitting helps.
- No hypothesis tree, sub-hypotheses or extra analyst rounds. Three perspectives stay.
- No change to how signal strength is scored (`evidence_service.py:EvidenceService._signal_strength`, `_fill_metric_evidence`).
- No new outcome on the reliability metrics page (doc 24). A later small change can count outcomes; listed in 11.2.
- No baseline for synthetic probes or Activity Log changes: a probe cannot be sent into the past, and the change read already covers the 24 hours before the window. They are marked `no_baseline_for_source` instead.
- No re-scoring of investigations stored before this feature. Their states stay "not recorded".

### 2.3 Anti-goals (what would make this harmful, and the control)

| Anti-goal | Control | AC |
|---|---|---|
| A failed read presented as a healthy result ("ruled out") | Sources that could not be read become coverage gaps, never evidence; legacy `not_checked` rows are never rendered as rule-outs; a hypothesis is ruled out only by evidence that was actually read | AC-3, AC-4, AC-8 |
| A confident cause announced with nothing changed in the data (ORCA-bench's invented causes) | The outcome guard forces `cause_not_visible` when no evidence item is a decisive signal; `cause_identified` needs a supported leading hypothesis | AC-10, AC-11 |
| "Supported" resting on a pattern that was just as common in the healthy hour before | Support guard: at least one cited supporting item must be a decisive signal | AC-7 |
| The model's own words hidden behind code changes (users cannot tell the AI from the rules) | Proposed state and outcome are stored beside the final ones with the guard code; the screen says when a rule changed them | AC-9, AC-14 |
| Stakeholder emails stating a cause the investigation did not confirm | Email, card, fallback answer and drafts take the outcome from code; "Likely cause" and "Suggested fix" appear only for `cause_identified` | AC-16 to AC-19 |
| "Inconclusive" used as a safe default to avoid all risk | Measured by doc 22 (`over_abstention_rate`); the guards only fire on stated rules, and the model is told when each state is right (4.5) | AC-12 (mock scenarios end `cause_identified`) |

---

## 3. Current state (verified 2026-11-22)

### 3.1 What exists

| Topic | Fact | Evidence |
|---|---|---|
| Pipeline | triage → context → evidence → (planner once) → finalize evidence → three hypothesis nodes in parallel → synthesis → blast radius → communications. Progress is committed after every stage. | `backend/keigan/ai/investigation_graph.py:InvestigationGraphRunner.build_graph`, `_update_progress` |
| Baseline window | Set to the same length just before the investigation window. Log, latency and metric templates query both windows; patterns are diffed (`isNewPattern`, `changeRatio`); metrics use a robust z-score against the baseline. Probes and Activity Log changes are not compared with a baseline. | `investigation_graph.py:_load_inputs`; `backend/keigan/services/evidence_service.py:_fill_log_evidence`, `_summarize_slow_requests`, `_fill_metric_evidence`, `_fill_probe_evidence`, `collect_change_evidence` |
| Rule-outs and "could not check" at draft level | `EvidenceDraft.is_rule_out` is set for empty or healthy results, and a failed read writes the summary "Not available: <reason>. Keigan cannot rule this source in or out." with `is_rule_out=True`. A failed Activity Log read writes "Recent changes: could not be checked" (fixed 2026-11-21). | `evidence_service.py:EvidenceDraft`, `_run_template`, `describe_query_failure`, `collect_change_evidence` |
| Hypothesis output | `HypothesisResult`: title, statement, reasoning, confidence, supporting and contradicting evidence codes, proposed fix, risk, matched runbook. **No state.** | `backend/keigan/ai/investigation_ai_schemas.py:HypothesisResult` |
| Synthesis output | `RcaSynthesisResult`: leading perspective and **its reason**, overall confidence, summary, three markdown sections, open questions, applied runbooks. **No outcome.** | `investigation_ai_schemas.py:RcaSynthesisResult` |
| Confidence | Overall confidence is capped at the best hypothesis + 0.05. A hypothesis's confidence is clamped to 0..1. | `investigation_graph.py:synthesis_node`, `_validated_hypothesis` |
| Storage | `investigation_hypothesis` has no state columns; `investigation` has no outcome columns; `investigation_evidence` has no rule-out or check-outcome column. | `backend/keigan/entities/incident_entities.py:InvestigationHypothesis`, `Investigation`, `InvestigationEvidence` |
| Screens | Root cause tab: executive summary, leading perspective, overall confidence meter, three cards, open questions, matched runbooks. Hypotheses tab: three cards with confidence, statement, reasoning, supporting and contradicting evidence chips, the fix. Evidence tab: strength badge "Strong / Medium / Weak or none". | `frontend/src/features/investigations/components/RcaSection.tsx`, `HypothesesSection.tsx`, `EvidenceSection.tsx` |
| Email and Teams | Preliminary report email body: executive summary, "**What went wrong**", "**Likely cause**", "**Suggested fix**" (fix only for technical roles); facts include "Confidence N%". The Teams card shows the executive summary and "Confidence N%". The Teams fallback answer quotes the executive summary and the fix. | `backend/keigan/services/notification_service.py:NotificationService.investigation_email_body`, `on_investigation_completed`; `backend/keigan/services/teams_chat_service.py:TeamsChatService._fallback_answer`, the card in chat creation |
| Communication drafts | The writer gets "Executive summary, What went wrong, Why it happened, Confidence". The prompt says "use 'most likely' below 0.8". | `backend/keigan/services/communication_service.py:CommunicationService.draft_investigation_communications`; `resources/prompts/incident_communications.md` (v2) |
| Postmortem | Gets the investigation's summary, why and fix as one untrusted section. | `communication_service.py` (postmortem sections); `resources/prompts/postmortem_report.md` (v1) |
| Chat consumers | Ask Keigan's `get_investigation` tool and the investigation context digest list hypotheses with confidence and evidence codes, no state. | `backend/keigan/services/ask_keigan_investigation_tools.py:HypothesisItem`, `GetInvestigationOutput`; `ask_keigan_investigation_context.py`; `investigation_chat_service.py:_load_context` (old engine, still used by the Teams bot until doc 23 phase 4) |
| Mock and seed | Eight scenario scripts give each perspective a fixed confidence; a generic script for unknown windows already says "cause cannot be confirmed". The seed runs one offline investigation per historical scenario. | `backend/keigan/ai/investigation_mock_responses.py:build_hypothesis`, `build_synthesis`, `_generic_script`; `backend/keigan/seed/investigation_seed.py:seed` |

### 3.2 Problems found while reading (each is fixed by this spec)

1. **A failed read reaches the model as a rule-out.** The persisted row loses `is_rule_out`; `EvidenceService.render_evidence_markdown` marks a row "rule-out" when `matched_record_count == 0`. A failed query has 0 matches, so the hypothesis prompt sees `| rule-out` next to "Not available ... cannot rule this source in or out", while `_hypothesis_body.md` says "Items marked rule-out show a healthy result and are useful to exclude causes". The signals contradict each other.
2. **The rule-out marker is also wrong the other way.** Healthy metrics (`matched_record_count = len(series) > 0`), healthy latency (sum of request counts > 0) and all-successful probes (count 5) are rule-outs at draft level but are rendered without the marker.
3. **Not-checked items look like weak evidence on screen.** The evidence tab shows a failed read as a normal evidence card with the "Weak or none" badge; only the English summary text says it was not read.
4. **Gaps disappear silently.** `rank_and_trim` drops low-strength drafts over the token budget, including "Not available" ones; `_select_templates` keeps only `MAXIMUM_TEMPLATES_PER_SERVICE` (a hard-coded module constant, 7); `_resolve_candidate_services` cuts to `investigation_max_services`; a service with no log source produces no draft at all; `run_planned_queries` skips rejected and failed planner queries with only a log line; a hypothesis node that fails validation returns `{}`. None of these reaches the person.
5. **The leading-perspective reason is discarded.** `RcaSynthesisResult.leading_perspective_reason` is produced and then dropped (only the mock context keeps it).
6. **English text in Japanese messages.** `investigation_email_body` writes the headings "What went wrong", "Likely cause", "Suggested fix" in English for every recipient; `on_investigation_completed` builds the Teams card with `"en"` and the literal fact labels "Incident", "Priority", "Confidence".

### 3.3 What the research doc says that is not quite right
- Doc 21, 3.2 says rule-outs and "cannot check this source" notes exist in `evidence_service.py`. True for drafts; **lost on persistence and mis-rendered to the model** (3.2, items 1 and 2).
- Doc 21, 3.2 rates the baseline comparison "✅ mostly". The comparison happens, but nothing downstream uses it as a gate: a hypothesis can be "supported" by a pattern that was equally common in the baseline. A2 adds the gate (4.4).

### 3.4 Unknowns
1. How a real model distributes the three states and outcomes. Only the mock was run. The harness (doc 22) measures it.
2. Whether any demo service has no log source (needed to show `service_without_telemetry` in the demo). The builder checks `service_log_source` in the seed; if none, section 10.3 says what to seed.
3. Native-speaker review of the new Japanese strings (email, card, screen).

---

## 4. Design

### 4.1 Decisions

**D-A2-1. The model proposes, code decides downward.** *Decision (made while the owner was away, revisit if wrong).* The model proposes each state and the outcome with its reason; deterministic guards (4.4) can only lower them (supported → inconclusive, ruled out → inconclusive, cause identified → inconclusive or not visible). Both values are stored. *Why:* the model reads the evidence and judges meaning; code checks the rules a person can verify (is the cited evidence real, did it change against the baseline). Raising is never automatic because a confident wrong answer is the most harmful outcome (doc 22, `confident_unsupported_rate`). *Rejected:* states computed by code only from confidence bands (cannot tell "contradicted" from "no data"); states from the model only (repeats ORCA-bench's failure mode).

**D-A2-2. Sources that could not be read are coverage gaps, not evidence.** *Decision (made while the owner was away, revisit if wrong).* A draft whose read failed is no longer persisted as an `investigation_evidence` row with an E code. It becomes an `investigation_coverage_gap` row and the model receives it in a separate trusted section "What Keigan could not check". *Why:* an E code invites citation as support or as a rule-out; a failed read is neither. *Rejected:* keep the row and add a flag (keeps the citation trap and the "Weak or none" card; still needed for rows stored before, see 4.2).

**D-A2-3. "Cause not visible" is forced by code when nothing changed.** When no evidence item is a decisive signal, the outcome is `cause_not_visible` whatever the model proposed. The model may also choose it when signals exist but only show symptoms. *Why:* this is exactly the case where weak models invent causes (doc 21, 2.6). *Rejected:* model-only choice.

**D-A2-4. Confidence keeps its meaning; outcome comes first everywhere.** `overall_confidence_score` stays "confidence in the leading or strongest lead", computed and capped as today. Surfaces show the outcome first; for an outcome other than `cause_identified`, the screen labels the meter "Confidence in the strongest lead", and emails and cards replace the "Confidence" fact with "Outcome". *Rejected:* forcing the number under a threshold (needs an arbitrary margin and breaks doc 22's calibration score); nulling it (loses information).

**D-A2-5. `cause_not_visible` has no leading hypothesis.** `leading_hypothesis_id` is null and no hypothesis is flagged leading. For `inconclusive` the synthesis lead is kept and shown as "Strongest lead, not confirmed". *Why:* a "Leading" ribbon on an explanation the data does not show is the confident tone the research warns about.

**D-A2-6. Gaps are a table, not JSON.** *Decision (made while the owner was away, revisit if wrong).* `investigation_coverage_gap` with enum CHECK constraints. *Why:* countable per application and source ("this Log Analytics workspace refused access in 9 investigations this week") for a later telemetry-health view, and enforced values. *Rejected:* `coverage_gaps_json` on `investigation` (no CHECK, not countable portably on SQLite and Azure SQL; the codebase moved away from id lists in JSON, revision `a3f5c0d1e2b4`).

**D-A2-7. The standing "no code or pipeline access" gap is a fixed sentence, not a row.** Every investigation would get the same row. The screen shows one footnote and the hypothesis prompt states it (4.5). It disappears when B4 lands.

**D-A2-8. Old investigations are not re-scored.** New columns are nullable; old rows show "not recorded". Evidence rows get a check outcome by backfill (4.3) because their text was written by Keigan's own code in a fixed form.

### 4.2 Data model

New enums in `backend/keigan/entities/status_values.py` (each builds its CHECK constraint with `values_check`):

| Enum | Values | Column |
|---|---|---|
| `HypothesisState` | `supported`, `ruled_out`, `inconclusive` | `investigation_hypothesis.hypothesis_state`, `.proposed_hypothesis_state` |
| `HypothesisStateGuard` | `support_not_in_evidence`, `confidence_below_supported_minimum`, `rule_out_not_in_evidence`, `confidence_above_ruled_out_maximum` | `investigation_hypothesis.state_guard_code` |
| `InvestigationOutcome` | `cause_identified`, `inconclusive`, `cause_not_visible` | `investigation.investigation_outcome`, `.proposed_investigation_outcome` |
| `InvestigationOutcomeGuard` | `nothing_changed_in_checked_sources`, `leading_hypothesis_not_supported`, `synthesis_unavailable` | `investigation.outcome_guard_code` |
| `EvidenceCheckOutcome` | `signal`, `no_signal`, `not_checked` | `investigation_evidence.check_outcome` |
| `BaselineComparison` | `compared`, `no_baseline_for_source` | `investigation_evidence.baseline_comparison` |
| `CoverageGapKind` | `source_not_readable`, `changes_not_readable`, `service_without_telemetry`, `services_beyond_limit`, `checks_beyond_limit`, `planned_query_rejected`, `planned_query_failed`, `results_left_out`, `perspective_not_analysed` | `investigation_coverage_gap.gap_kind` |
| `CoverageGapReason` | `access_refused`, `throttled`, `source_not_found`, `source_error`, `timed_out`, `not_approved`, `query_rejected`, `reader_not_available`, `ai_unavailable`, `ai_output_invalid`, `unknown` | `investigation_coverage_gap.reason_code` |

**New columns** (all nullable: rows stored before this feature have none).

| Table | Column | Type | Meaning |
|---|---|---|---|
| `investigation_hypothesis` | `hypothesis_state` | String(20), CHECK | final state |
| | `proposed_hypothesis_state` | String(20), CHECK | the model's state |
| | `state_guard_code` | String(40), CHECK | the guard that lowered it, null when none |
| | `state_reason_markdown` | Text | the model's reason, cleaned like other AI text (`_clean_ai_text`) |
| `investigation` | `investigation_outcome` | String(30), CHECK | final outcome; null for evidence-only, failed, queued, running |
| | `proposed_investigation_outcome` | String(30), CHECK | the model's outcome |
| | `outcome_guard_code` | String(40), CHECK | |
| | `outcome_reason_markdown` | Text | cleaned with `_clean_synthesis_text` |
| | `leading_perspective_reason_markdown` | Text | today's discarded `leading_perspective_reason`, cleaned |
| `investigation_evidence` | `check_outcome` | String(20), CHECK | |
| | `baseline_comparison` | String(30), CHECK | |

**New table `investigation_coverage_gap`** (entity `InvestigationCoverageGap` in `incident_entities.py`, beside `InvestigationEvidence`).

| Column | Type | Notes |
|---|---|---|
| `coverage_gap_id` | String(36) PK | `identifier_column()` |
| `investigation_id` | FK `investigation` ON DELETE CASCADE, index | one cascade path, like `investigation_evidence` |
| `display_order` | Integer | the order the gaps were found |
| `gap_kind` | String(40), CHECK `CoverageGapKind` | |
| `reason_code` | String(40), CHECK `CoverageGapReason`, nullable | |
| `service_id` | String(36), nullable, no FK | a recorded fact (like `chat_run_step.application_id`): the gap outlives a deleted service |
| `service_name` | String(200), nullable | the name at the time, for the same reason |
| `source_kind` | String(40), nullable | open column, same values as `investigation_evidence.evidence_source_kind` (`log_analytics`, `application_insights`, `log_tool`, `activity_log`, ...) |
| `parameters_json` | JSON, nullable | small, code-built values only: `{"limit": 6, "count": 3, "serviceNames": [...], "perspective": "dependencies", "templateTitles": [...]}` |
| `recorded_at` | DateTime | |

Index: `ix_investigation_coverage_gap_investigation_id`. Retention: deleted with its investigation (4.7). No text from outside Keigan is stored in a gap: names come from the service catalogue, reasons are codes.

**Alembic revision plan** (one revision on top of the head at build time; today `b8d4f2a6c0e3`; file `backend/migrations/versions/<date>_<rev>_honest_outcomes.py`, docstring in the style of `20261122_b8d4f2a6c0e3_answer_run_used_applications.py`):
1. `add_column` for the eleven columns with their named CHECK constraints rendered from entity metadata (as `d2a6b0c5e8f9_status_check_constraints` does).
2. `create_table investigation_coverage_gap` with its CHECKs, FK and index.
3. Backfill `investigation_evidence` (one `UPDATE` each, portable SQL):
   - `check_outcome = 'not_checked'` where `evidence_summary LIKE 'Not available:%'`;
   - `check_outcome = 'no_signal'` where still null and (`evidence_summary LIKE 'Rule-out:%'` or `matched_record_count = 0`);
   - `check_outcome = 'signal'` for the rest;
   - `baseline_comparison = 'no_baseline_for_source'` where `evidence_category IN ('change_event', 'synthetic_probe')`, else `'compared'`.
   The prefixes are the exact strings `evidence_service.py` writes; the docstring says so and that rows written by other code (none today) would land in `signal`.
4. `downgrade()` drops the table and columns.
5. Regenerate `database/azure_sql/02_create_tables.sql` to `05_reference_data.sql` (`backend/scripts/generate_azure_sql_ddl.py`), the delta `database/azure_sql/migrations/<rev>_honest_outcomes.sql` (`generate_azure_sql_migration_scripts.py`, including the backfill), the demo SQL (`generate_demo_data_sql.py`), the ER diagram (`generate_entity_relationship_diagram.py` → doc 15) and the counts in `database/azure_sql/README.md` (tables +1, CHECK constraints +12, indexes +1). `tests/integration/migrations/test_schema_drift.py` must pass.

### 4.3 Services and modules (one job each)

| Module | Job | Notes |
|---|---|---|
| `backend/keigan/ai/investigation_outcome_rules.py` (new, pure, no database) | The guards. `decide_hypothesis_state(proposed, confidence, supporting_rows, contradicting_rows, thresholds) -> StateDecision`; `decide_outcome(proposed, final_states, leading_perspective, evidence_rows, synthesis_was_available) -> OutcomeDecision`; `is_decisive_signal(row)`; `check_outcome_of(draft)`; `baseline_comparison_of(category)`. `StateDecision` and `OutcomeDecision` are frozen dataclasses: final value, proposed value, guard code or None, the decisive evidence codes. Doc 28 records these objects (4.8). | Thresholds come from settings (4.6) |
| `backend/keigan/services/investigation_coverage.py` (new) | `CoverageGapCollector`: collects gaps during one run in memory (`add(kind, reason, service, source_kind, parameters)`), persists them in `finalize_evidence_node`, and renders the trusted prompt section "What Keigan could not check" (`render_for_prompt()`). `classify_query_failure(error) -> CoverageGapReason` maps the same cases as today's `describe_query_failure`. | `describe_query_failure` stays for the English sentence the model and the log get; both read one table of cases so they cannot disagree |
| `backend/keigan/services/evidence_service.py` (changed) | Drafts gain `check_outcome` and `baseline_comparison` (set in each `_fill_*`, `_run_template`, `collect_change_evidence`). A failed read sets `check_outcome=not_checked` and a `failure_reason` code. `persist_evidence` writes both new columns and **skips `not_checked` drafts**. `render_evidence_markdown` and `render_draft_markdown` mark from `check_outcome`, not from `matched_record_count`. `rank_and_trim` returns `(kept, left_out_count)`. `run_planned_queries` reports rejected and failed queries through the collector instead of only logging. `_select_templates` reads the new setting `INVESTIGATION_MAX_CHECKS_PER_SERVICE` instead of `MAXIMUM_TEMPLATES_PER_SERVICE` and reports the cut. | `EvidenceService` takes an optional `CoverageGapCollector` |
| `backend/keigan/ai/investigation_graph.py` (changed) | Owns one collector per run. `_resolve_candidate_services` reports `services_beyond_limit`; `evidence_node` reports services with no log source (`service_without_telemetry`); hypothesis nodes report `perspective_not_analysed` (`ai_output_invalid` on `KeiganException`, `ai_unavailable` on budget or availability errors); `_validated_hypothesis` calls `decide_hypothesis_state`; `synthesis_node` calls `decide_outcome`, stores the outcome columns and `leading_perspective_reason_markdown`, sets `leading_hypothesis_id` per D-A2-5 (null for `cause_not_visible`; the existing `next(...)` must not raise), and on the synthesis fallback path uses guard `synthesis_unavailable` (outcome `cause_identified` only when the best hypothesis is supported, else `inconclusive`). `_complete` leaves the outcome null for evidence-only runs. The timeline event `rca_completed` names the outcome. | |
| `backend/keigan/ai/investigation_ai_schemas.py` (changed) | Schema fields in 4.5. | |
| `backend/keigan/ai/investigation_mock_responses.py` (changed) | `build_hypothesis` proposes `supported` for the lead perspective when its script confidence ≥ the supported minimum, `ruled_out` when confidence ≤ the ruled-out maximum and it has contradicting codes, else `inconclusive`, each with a filled reason sentence. `build_synthesis` proposes `cause_identified` for scenario scripts and `cause_not_visible` for the generic script (a window the simulator has no scenario for: by construction nothing caused it), with `leading_perspective` null; the generic hypotheses propose `inconclusive`. | The eight scenarios must end `cause_identified` (AC-12); the generic path is deterministic whatever background noise the simulator produces, because guards never raise |
| `backend/keigan/services/investigation_service.py` (changed) | Detail and summary DTOs gain the fields in 4.7; `get_investigation_detail` loads gaps and adds legacy `not_checked` evidence rows to the gap list (kind `source_not_readable`, reason `unknown`, the row's code kept for the link). | |
| `backend/keigan/services/notification_service.py`, `teams_chat_service.py`, `communication_service.py`, `ask_keigan_investigation_tools.py`, `ask_keigan_investigation_context.py`, `investigation_chat_service.py` (changed) | Quote the outcome (4.7, 5.3). | |
| `backend/keigan/services/incident_retention.py` (changed) | Deletes coverage gaps in `_delete_investigations` before the investigation (count key `coverageGaps`). | |

### 4.4 The guards (exact rules, `investigation_outcome_rules.py`)

Inputs per hypothesis: proposed state, clamped confidence `c`, the **valid** supporting and contradicting codes (after `remove_invalid_citations`), the evidence rows by code. Thresholds `S = INVESTIGATION_SUPPORTED_MINIMUM_CONFIDENCE`, `R = INVESTIGATION_RULED_OUT_MAXIMUM_CONFIDENCE`.

| Proposed | Rule, checked in this order | Final | Guard code |
|---|---|---|---|
| `supported` | no valid supporting code is a decisive signal | `inconclusive` | `support_not_in_evidence` |
| `supported` | `c < S` | `inconclusive` | `confidence_below_supported_minimum` |
| `ruled_out` | no valid contradicting code (only read evidence has codes, D-A2-2; a legacy `not_checked` row never counts) | `inconclusive` | `rule_out_not_in_evidence` |
| `ruled_out` | `c > R` | `inconclusive` | `confidence_above_ruled_out_maximum` |
| any | none of the above | proposed | null |

Outcome, after the states are final (`L` = the synthesis's leading perspective, or the highest-confidence hypothesis when the synthesis named none or was unavailable):

| Rule, in order | Final outcome | Guard code |
|---|---|---|
| no persisted evidence row is a decisive signal | `cause_not_visible` | `nothing_changed_in_checked_sources` (null if the model proposed the same) |
| synthesis unavailable (fallback path) | `cause_identified` if `L` is `supported`, else `inconclusive` | `synthesis_unavailable` |
| proposed `cause_identified` and `L`'s final state is not `supported` | `inconclusive` | `leading_hypothesis_not_supported` |
| otherwise | proposed | null |

The guards never raise a state or an outcome; a model that proposes `inconclusive` or `cause_not_visible` is believed.

### 4.5 AI prompts and schemas

Schemas (`investigation_ai_schemas.py`):

```python
HypothesisStateName = Literal["supported", "ruled_out", "inconclusive"]
InvestigationOutcomeName = Literal["cause_identified", "inconclusive", "cause_not_visible"]

class HypothesisResult(BaseModel):          # existing fields unchanged, plus:
    assessment: HypothesisStateName = Field(description="supported, ruled_out or inconclusive; see the rules")
    assessment_reason_markdown: str = Field(description="One or two sentences: why this state, citing the evidence codes that decide it")

class RcaSynthesisResult(BaseModel):        # existing fields, with these changes:
    leading_perspective: AnalysisPerspectiveName | None   # null only with cause_not_visible
    investigation_outcome: InvestigationOutcomeName
    outcome_reason_markdown: str = Field(description="Two or three sentences: why this outcome, citing evidence; for cause_not_visible, which sources were normal or unreadable")
```

No defaults on the new fields: a reply without them fails validation, gets the gateway's one repair retry (`llm_gateway.py:LlmGateway.generate_structured`) and then the perspective is recorded as `perspective_not_analysed / ai_output_invalid`. A silent default would recreate the problem this spec removes.

Prompt changes (versions bump; the trusted template variables `supported_minimum_confidence` and `ruled_out_maximum_confidence` are rendered from settings so the prompt and the guard read the same numbers):

| Prompt | Version | Change |
|---|---|---|
| `_hypothesis_body.md` (fragment) → `hypothesis_application.md`, `hypothesis_dependencies.md`, `hypothesis_infrastructure.md` | 3 → 4 each | (1) Replace "Items marked rule-out show a healthy result" with: "Each item says `checked: signal` or `checked: no signal (rule-out)` and `baseline: compared` or `baseline: none for this source`. Sources Keigan could not read are not evidence: they are listed in 'What Keigan could not check'. Never treat an unread source as healthy." (2) New section description for "What Keigan could not check" (trusted, written by Keigan). (3) The state rules: *supported* only when a cited item changed against the baseline (or is a change event or failing probe) and its timing fits the onset, confidence at least {{ supported_minimum_confidence }}; *ruled_out* only when a source that was read shows the lens is healthy (cite it as contradicting), confidence at most {{ ruled_out_maximum_confidence }}; *inconclusive* when the deciding source was not read, or the evidence fits more than one explanation. "Inconclusive is an honest result; do not stretch the evidence to avoid it." (4) "Keigan cannot read code repositories, pull requests or deployment pipelines. A code defect can be supported only by what telemetry shows (new exception types, a deployment event), never assumed." |
| `rca_synthesis.md` | 3 → 4 | Decide `investigation_outcome`: *cause_identified* only when the leading hypothesis is supported; *inconclusive* when signals exist but do not establish one cause; *cause_not_visible* when no checked source changed against the baseline, or the signals show only the symptom and the sources that could show a cause were normal or not readable. For anything but cause_identified: `executive_summary` says the cause is not confirmed (no "most likely" cause sentence), `why_it_happened_markdown` says what is known and what is not, `how_to_fix_markdown` lists safe next checks and symptom mitigation, not a fix for an unproven cause, and `open_questions` name the checks that would settle it, starting with the coverage gaps. `leading_perspective` is null for cause_not_visible. It also receives "What Keigan could not check" and each hypothesis's final state and guard (the analyst hypotheses section). |
| `incident_communications.md` | 2 → 3 | The findings now include `Outcome:` and `Outcome reason:`. Rule: "When the outcome is not cause_identified, never state or imply a cause. Say the cause is being investigated (inconclusive) or is not visible in the monitoring data Keigan can read (cause_not_visible), and what the team is checking next." |
| `postmortem_report.md` | 1 → 2 | The investigation section includes the outcome. Rule: "If the investigation outcome is not cause_identified, root_cause comes only from the responders' timeline and chat facts and says so; if they do not establish it, write that the root cause was not established and list what would establish it." |

Injection handling is unchanged: the gap section is trusted because code writes it from catalogue names and fixed reason codes (the same trust as "Service catalogue"); everything else stays spotlighted. The new reason fields go through `remove_invalid_citations` and `sanitize_ai_markdown` like every other AI text (`_clean_ai_text`).

### 4.6 Settings (validated; `backend/keigan/config/settings.py`, `backend/.env.example`, Helm `backendEnvironment`)

| Setting | Default | Range | Meaning |
|---|---|---|---|
| `INVESTIGATION_SUPPORTED_MINIMUM_CONFIDENCE` | `0.5` | 0.0 to 1.0 | Lowest confidence a supported hypothesis may have (the rubric's "strongly suggests" band in `_hypothesis_body.md`) |
| `INVESTIGATION_RULED_OUT_MAXIMUM_CONFIDENCE` | `0.2` | 0.0 to 1.0 | Highest confidence a ruled-out hypothesis may have (the rubric's "unlikely" band) |
| `INVESTIGATION_MAX_CHECKS_PER_SERVICE` | `7` | 1 to 30 | Replaces the module constant `MAXIMUM_TEMPLATES_PER_SERVICE`; same value, now visible and reported as a gap when it cuts |

Validator: `INVESTIGATION_RULED_OUT_MAXIMUM_CONFIDENCE < INVESTIGATION_SUPPORTED_MINIMUM_CONFIDENCE`, with a message naming both.

### 4.7 API (base `/api`, camelCase, doc 05 conventions; no new endpoint)

`GET /api/investigations/{id}` (`InvestigationDetailDto`) gains:

```jsonc
"outcome": {                       // null when evidence-only, failed, queued or running
  "code": "inconclusive",          // InvestigationOutcome, or "not_recorded" for investigations before this feature
  "proposedCode": "cause_identified",
  "guardCode": "leading_hypothesis_not_supported",   // or null
  "reasonMarkdown": "…[E3] …"
},
"leadingPerspectiveReasonMarkdown": "…",
"coverageGaps": [ { "coverageGapId": "…", "gapKind": "source_not_readable", "reasonCode": "access_refused",
                    "serviceId": "…", "serviceName": "claims-api", "sourceKind": "application_insights",
                    "parameters": {}, "legacyEvidenceCode": null } ]
```

`HypothesisDto` gains `state`, `proposedState`, `stateGuardCode`, `stateReasonMarkdown` (null on old rows). `EvidenceDto` gains `checkOutcome`, `baselineComparison`. `InvestigationSummaryDto` (lists) and `incident_dtos.py:InvestigationBrief` gain `investigationOutcome` (code or null). The TypeScript types in `frontend/src/api/investigationsApi.ts` follow; `tests/unit/test_frontend_contract.py` checks the names. Errors: none new.

Ask Keigan `get_investigation` (`ask_keigan_investigation_tools.py`): `HypothesisItem.state`, `GetInvestigationOutput.outcome` and `coverage_gap_count`; the tool's registry `version` increments (doc 23, 4.5.1). The investigation context digest and the old `investigation_chat_service._load_context` digest print each hypothesis's state and the outcome.

### 4.8 Contract with doc 28 (decision trace, A3): A2 is built first

**What A3 needs from A2** (A2 must deliver these, even though A2's own screen uses only some):
1. `proposed_hypothesis_state`, `state_guard_code`, `proposed_investigation_outcome` and `outcome_guard_code` stored, so the trace can show "the model said X; Keigan's rule changed it to Y because Z".
2. `decide_hypothesis_state` and `decide_outcome` return `StateDecision` and `OutcomeDecision` objects (with the decisive codes) that the graph keeps in memory until the stage commits; A3's recorder attaches them to the matching AI-call step without recomputing.
3. Coverage gap rows with stable ids, written in `finalize_evidence_node` before the hypothesis stage, so A3's evidence step can list them by id.
4. `check_outcome` and `baseline_comparison` on evidence, so A3 can count "signals, rule-outs, compared with baseline".
5. Ruled-out and inconclusive hypotheses are stored as rows (they already are; this must not change). A3's "rejected hypotheses" panel is these rows.

**What A2 needs from A3:** nothing. A2 ships and is useful alone. A3 built without A2 would show "state not recorded" for every hypothesis; that is why the order is A2, then A3.

---

## 5. User experience

### 5.1 Root cause tab (`RcaSection.tsx`)
- **Outcome line first**, inside the summary card above the executive summary: an `OutcomeBadge` (new, `components/ui/OutcomeBadge.tsx`) and one sentence:
  - `cause_identified` (tone success): "Cause identified" / "The evidence supports one explanation."
  - `inconclusive` (tone warning): "Inconclusive" / "The evidence does not settle between the explanations. The strongest lead is shown, not confirmed."
  - `cause_not_visible` (tone neutral-info, not danger: it is a result): "Cause not visible in the data Keigan can see" / "Nothing Keigan could read changed against the hour before. The cause is likely in a system or change Keigan cannot see."
  - `not_recorded`: no badge; caption "This investigation ran before Keigan recorded outcomes."
  - The `outcomeReasonMarkdown` follows, with citation chips (existing `CitationRow`).
  - When `guardCode` is set: a small note "Keigan's rules changed the AI's conclusion from {{proposed}} to {{final}}: {{guard sentence}}."
- Leading line: `cause_identified` keeps "Leading: {{perspective}}" plus the `leadingPerspectiveReasonMarkdown` in a disclosure "Why this lead"; `inconclusive` says "Strongest lead (not confirmed): …"; `cause_not_visible` shows none.
- Confidence meter label: "Overall confidence" for `cause_identified`, "Confidence in the strongest lead" otherwise; hidden for `cause_not_visible`.
- **"Ruled out" card** (new, beside open questions): each ruled-out hypothesis's perspective, title and reason, linking to the Hypotheses tab. Empty: not shown.
- **"What Keigan could not check" card** (new, `CoverageGapsCard.tsx`): one row per gap, as a sentence built from translated parts, for example "claims-api · Application Insights: Keigan's identity was refused access (a read role is missing)". Grouped: sources not read; services with no telemetry; limits; perspectives not analysed. Always ends with the footnote "Keigan does not read code repositories or deployment pipelines." Empty state: "Keigan read every source it planned to." (still with the footnote). A legacy `not_checked` evidence row appears here with its E code as a link.

### 5.2 Hypotheses and Evidence tabs
- Each hypothesis card header gets a `HypothesisStateBadge` (Supported: success; Ruled out: neutral with a strike icon; Inconclusive: warning). Below the confidence meter: "Why: {{stateReasonMarkdown}}". When `stateGuardCode` is set: "The AI said {{proposed}}; Keigan's rule changed it: {{guard sentence}}". The "Leading" badge follows D-A2-5. Order stays by perspective.
- Each evidence card gets two small badges: check outcome ("Signal", "Healthy or nothing found", legacy "Could not be read") and baseline ("Compared with {{baselineWindow}}" or "No baseline for this kind of source"). The existing strength badge stays. The intro sentence gains "Sources Keigan could not read are listed on the Root cause tab."

### 5.3 Other surfaces
- **Incident list and board** (`IncidentTable.tsx`, `IncidentBoard.tsx`): where confidence is shown, show a compact outcome chip first; confidence only for `cause_identified`.
- **Preliminary-report email** (`investigation_email_body`, now with a `language_code` parameter): first a translated outcome sentence (backend string table, en and ja: `outcome.<code>.sentence`); headings translated (`email.what_went_wrong`, `email.likely_cause`, `email.known_so_far`, `email.suggested_fix`, `email.next_checks`); "Likely cause" and "Suggested fix" only for `cause_identified`; otherwise "What is known so far" and, for technical roles, "Suggested next checks". Technical roles also get "Keigan could not check {{count}} source(s); see the investigation." when gaps exist. Facts: "Outcome" replaces "Confidence" unless `cause_identified`.
- **Teams card** (`on_investigation_completed` and chat creation in `teams_chat_service.py`): same facts rule, labels from `translate(language, "labels.…")` in the application's primary locale (fixes 3.2, item 6). **Teams fallback answer** (`_fallback_answer`): starts with the outcome sentence; "Suggested fix" only for `cause_identified`.
- Backend notification languages are en and ja only (`utils/string_table.py:SUPPORTED_LANGUAGE_CODES`); new keys go into `resources/i18n/en.json` and `ja.json`.

### 5.4 States, keyboard, screen readers, phone
- Loading and error: unchanged (the detail query). Running: no outcome yet; the progress view is unchanged. Evidence-only: the existing banner; the gaps card still shows. Failed: the existing banner; gaps recorded before the failure are not shown (they are written with the evidence stage; a failure after it keeps them and they show).
- Badges carry text, never colour alone; the guard note is plain text; the gaps card is a `<section>` with a heading and a `<ul>`; citation chips keep their accessible names. No new motion.
- Phone (390 px): the outcome badge and sentence stack above the summary; the two new cards stack in one column; gap rows wrap.

### 5.5 Locale key groups (frontend, six locales: en, es, fr, ja, nl, zh-CN; es-MX falls back to es)
`investigations.json`: `outcome.<code>.title|description` (codes plus `not_recorded`), `outcome.guard.<guardCode>`, `outcome.guardNote`, `outcome.whyThisLead`, `outcome.strongestLead`, `outcome.confidenceStrongestLead`; `hypotheses.state.<state>`, `hypotheses.stateGuard.<guardCode>`, `hypotheses.stateGuardNote`, `hypotheses.why`; `ruledOut.title|description`; `coverage.title|description|empty|footnoteCodeAccess`, `coverage.group.<group>`, `coverage.kind.<gapKind>`, `coverage.reason.<reasonCode>`; `evidence.checkOutcome.<value>`, `evidence.baseline.<value>`, `evidence.introUnreadSources`. `common.json`: `investigationOutcome.<code>` (short chip labels for the incident list). `npm run check:locales` must pass.

---

## 6. Safety, access and privacy
- **Who sees what:** unchanged. Everything here is part of the investigation detail, readable by readers of the application (`InvestigationService.load_readable_investigation`); nothing new is writable by a person.
- **Masking:** reason texts are model output from masked input and are cleaned like the other AI fields (`_clean_ai_text`: invalid citations removed, links and HTML neutralised). Gap rows hold catalogue names and codes only; the English failure sentence for the model is built from fixed strings (the integration's own text is never copied, as today: `QUERY_FAILURE_REASON_BY_ERROR_CODE`).
- **Prompt safety:** the gap section is trusted only because code writes it from catalogue values; service names are already rendered in the trusted catalogue section. A test fails if any gap field holds text from an exception message (AC-5).
- **Audit:** no new audit rows (no new write action). The outcome is part of the durable `investigation.concluded` audit row that doc 28 adds.
- **Retention:** gaps and the new columns follow their investigation (`INCIDENT_RETENTION_DAYS`, 395 by default).
- **Stakeholder messages:** the anti-goal controls in 2.3; business roles never receive fix steps or next-check commands (existing audience rule kept).

---

## 7. Acceptance criteria

| # | Criterion | Test type |
|---|---|---|
| AC-1 | `HypothesisResult` and `RcaSynthesisResult` reject a reply without the new fields; `leading_perspective` accepts null | unit |
| AC-2 | Each draft kind gets the right `check_outcome` and `baseline_comparison`: logs with and without matches, slow requests healthy and slow, metrics healthy and abnormal, probes passing and failing, changes found, none and read failure | integration (`test_evidence_service.py`) |
| AC-3 | A failed read (each `CoverageGapReason` that `classify_query_failure` returns) is persisted as a gap, never as an evidence row, and consumes no E code | integration |
| AC-4 | `render_evidence_markdown` marks rule-outs from `check_outcome` (healthy metrics, latency and probes are marked; nothing unread is marked) | unit |
| AC-5 | Every gap kind is produced by its trigger (service limit, checks limit, no log source, planner rejected, planner failed, results left out by the token budget, perspective validation failure, perspective budget failure), and no gap field contains exception text | integration (`test_investigation_graph` with the mock gateway) |
| AC-6 | `classify_query_failure` and `describe_query_failure` cover the same cases (table-driven) | unit |
| AC-7 | Support guard: a `supported` proposal citing only low-strength compared items, or only rule-outs, becomes `inconclusive / support_not_in_evidence`; citing a change event (no baseline) stays supported | unit (`test_investigation_outcome_rules.py`) |
| AC-8 | Rule-out guard: `ruled_out` with no valid contradicting code becomes `inconclusive / rule_out_not_in_evidence`; a legacy `not_checked` row never counts | unit |
| AC-9 | Confidence guards at the exact thresholds (equal to `S` stays supported; equal to `R` stays ruled out) | unit |
| AC-10 | Outcome guard: with no decisive signal in the evidence the outcome is `cause_not_visible` and `leading_hypothesis_id` is null, whatever the model proposed | unit + integration |
| AC-11 | `cause_identified` with a non-supported lead becomes `inconclusive / leading_hypothesis_not_supported`; the synthesis fallback records `synthesis_unavailable` | unit + integration |
| AC-12 | Offline, each of the eight seeded scenarios ends `cause_identified` with the lead supported and at least one other perspective `ruled_out` or `inconclusive`; a run on a window with no scenario ends `cause_not_visible` with no leading hypothesis | integration (`test_investigation_service.py`) |
| AC-13 | Guards never raise: a proposal of `inconclusive` or `cause_not_visible` is kept in every combination (property-style table test) | unit |
| AC-14 | The detail API returns outcome, proposed values, guard codes, gaps, check outcome and baseline fields; an investigation stored before the migration returns `not_recorded` and null states | integration |
| AC-15 | The migration backfills the three check outcomes and the two baseline values from representative rows; downgrade removes everything | integration (`tests/integration/migrations/test_honest_outcomes_migration.py`) |
| AC-16 | Email body: for each outcome and for technical and business roles, the right headings in en and ja, no "Likely cause" or "Suggested fix" unless `cause_identified`, "Outcome" replaces "Confidence" | integration (`test_notification_service.py`) |
| AC-17 | Teams card facts are translated and follow the same rule; the fallback answer starts with the outcome sentence | integration (`test_teams_chat_service.py`) |
| AC-18 | The communication and postmortem prompts receive the outcome; the mock drafts for `inconclusive` contain no cause sentence | integration (`test_communication_service.py`) |
| AC-19 | Prompts `hypothesis_*` v4, `rca_synthesis` v4, `incident_communications` v3, `postmortem_report` v2 render the two thresholds from settings (changing a setting changes the rendered text) | unit (`test_prompt_library.py`) |
| AC-20 | Settings: defaults, ranges, the ordering validator; present in `.env.example` and Helm values | unit (`tests/unit/config/test_settings.py`) |
| AC-21 | Retention removes gaps with their investigation | integration (`test_incident_retention.py`) |
| AC-22 | Ask Keigan `get_investigation` returns states, outcome and gap count; tool version incremented | integration (`test_ask_keigan_investigation_tools.py`) |
| AC-23 | Frontend: types match the DTOs; locales complete; typecheck and build pass | unit (`test_frontend_contract.py`), `npm run typecheck`, `check:locales`, `build` |
| AC-24 | Browser check at 1440 and 390 px, light and dark: outcome badge, ruled-out card, gaps card and state badges visible on a seeded `cause_identified` and on the seeded `cause_not_visible` investigation | script (`frontend/scripts/capture-screens.mjs` routes added) |

---

## 8. Test plan (files mirror `backend/keigan/`)

| File | Covers |
|---|---|
| `backend/tests/unit/ai/test_investigation_outcome_rules.py` (new) | AC-7 to AC-11, AC-13 |
| `backend/tests/unit/ai/test_investigation_ai_schemas.py` (new) | AC-1 |
| `backend/tests/unit/ai/test_investigation_graph.py` (extend) | leading id null for `cause_not_visible`; reason columns cleaned |
| `backend/tests/unit/ai/test_prompt_library.py` (extend) | AC-19 |
| `backend/tests/unit/services/test_investigation_coverage.py` (new) | collector order, rendering for the prompt, AC-6 |
| `backend/tests/integration/services/test_evidence_service.py` (extend) | AC-2, AC-3, AC-4 |
| `backend/tests/integration/ai/test_investigation_honest_outcomes.py` (new) | AC-5, AC-10, AC-11 through the real graph with the mock gateway and scripted factories |
| `backend/tests/integration/services/test_investigation_service.py` (extend) | AC-12, AC-14 |
| `backend/tests/integration/services/test_notification_service.py`, `test_teams_chat_service.py`, `test_communication_service.py` (extend) | AC-16 to AC-18 |
| `backend/tests/integration/services/test_ask_keigan_investigation_tools.py` (extend) | AC-22 |
| `backend/tests/integration/services/test_incident_retention.py` (extend) | AC-21 |
| `backend/tests/integration/migrations/test_honest_outcomes_migration.py` (new), `test_schema_drift.py` | AC-15 |
| `backend/tests/unit/config/test_settings.py` (extend) | AC-20 |
| `backend/tests/unit/test_frontend_contract.py` (extend) | AC-23 |
| Browser: `frontend/scripts/capture-screens.mjs` (add the two investigations' Root cause and Hypotheses tabs) | AC-24 |

Smoke run as for every phase: backend boots, demo seed completes, frontend builds, capture clean.

---

## 9. Phased build plan

| # | Task | Size | Depends on | Demonstrable at the end |
|---|---|---|---|---|
| 1 | Enums, entity columns, `InvestigationCoverageGap`, Alembic revision with backfill, Azure SQL scripts and delta, ER diagram, README counts | M | — | `alembic upgrade` on a copy of the demo database shows backfilled check outcomes |
| 2 | `investigation_outcome_rules.py` with its unit tests; the three settings | S | 1 | AC-7 to AC-13, AC-20 green |
| 3 | `investigation_coverage.py`; evidence service changes (check outcome, gaps instead of rows, marker fix, setting for checks per service, planner reporting) | M | 1 | AC-2 to AC-6 green |
| 4 | Schemas, prompts v4/v4/v3/v2, mock factories, graph wiring (gaps, states, outcome, leading rule, fallback) | M | 2, 3 | Offline seed: eight scenarios `cause_identified`, ruled-out and inconclusive hypotheses visible in the API |
| 5 | DTOs, detail and summary API, Ask Keigan tool and digests | S | 4 | AC-14, AC-22 |
| 6 | Email body, Teams card and fallback, communication and postmortem inputs, backend en/ja strings | S | 4 | AC-16 to AC-18 |
| 7 | Frontend: `OutcomeBadge`, `HypothesisStateBadge`, `CoverageGapsCard`, ruled-out card, evidence badges, incident list chip, six locales | M | 5 | Screens at both widths |
| 8 | Demo seed additions (10.3), demo SQL regenerated, capture script routes, docs listed in 10.1 | S | 7 | AC-24, smoke run |

Build order: 1 → 2 and 3 (parallel) → 4 → 5 and 6 (parallel) → 7 → 8. Total about M (one to two weeks).

---

## 10. Docs, migration and demo-data impact

### 10.1 Documents to update (by the lead after the build)
- Doc 03 (database design): the new table and columns. Doc 15: regenerated ER diagram.
- Doc 05 (API contract): the new detail, summary and evidence fields.
- Doc 06 (AI engine): section 3.3 (check outcome, gaps, marker fix), 3.4 (states, guards, thresholds), 3.5 (outcome), 3.8 (evidence-only has no outcome), the prompt versions.
- Doc 13 (sequence diagrams): incident to RCA, the guard step after hypotheses and synthesis.
- Doc 01 (product specification): the investigation page and the preliminary report.
- Doc 12 (feature tracker), doc 21 (3.2 rows "Show rejected or inconclusive hypotheses" and "Healthy-window baseline comparison"), doc 00 status page.
- Doc 22: `is_abstention(trial)` becomes `outcome in ("inconclusive", "cause_not_visible")` (its section 4.3.4 already plans this).
- Doc 09 (learnings): the rule-out marker bug (3.2, items 1 and 2).

### 10.2 Azure SQL
Baseline scripts `02` to `05` regenerated; delta `database/azure_sql/migrations/<rev>_honest_outcomes.sql` with the backfill `UPDATE`s; README counts; demo data regenerated (10.3). The scripts are checked by the parser and drift tests only, as today (status page section 1).

### 10.3 Demo data
- The eight historical incidents get states and outcomes from the offline factories (no manual rows): lead `supported`, the low-confidence perspectives `ruled_out` where the script has contradicting codes, others `inconclusive`.
- **One new seeded manual investigation** (in `investigation_seed.py`): application PAYAU (or any seeded application with no historical scenario in the chosen window), a 60-minute window that overlaps no scenario, trigger `manual`, requested by `keigan.admin@keigan.local`. The generic script and the outcome guard make it `cause_not_visible`. If the chosen application has a service with no `service_log_source`, it is in scope and yields `service_without_telemetry`; if no seeded service lacks a source, add one inactive-telemetry service (for example a `mainframe` component service with no source) to that application in the application seed so the gaps card shows data.
- No AI usage rows are seeded (unchanged decision, status page section 7).

---

## 11. Risks, mitigations, open questions

### 11.1 Risks

| Risk | Mitigation |
|---|---|
| A real model over-uses "inconclusive" | Prompt says inconclusive needs a reason; doc 22 measures `over_abstention_rate`; guards never push toward it except by stated rules |
| A real model fills the new fields badly (for example "supported" with no codes) | The guards catch the measurable cases; the repair retry catches missing fields; the state reason is visible next to the evidence |
| The support guard is too strict for legitimate low-strength evidence (a rare but decisive error) | The hypothesis is then inconclusive, not lost; its reason and evidence remain visible; revisit the definition of "decisive" with harness data |
| Fewer E codes after D-A2-2 changes code numbering compared with older investigations | Codes are per investigation; nothing compares codes across investigations |
| Thresholds changed without re-reading the rubric | The prompt renders the same settings (AC-19) |
| Japanese wording of "cause not visible" sounds like a failure to stakeholders | Native-speaker review (status page, needs the owner item 4) |

### 11.2 Open questions for the owner
1. **Stakeholder wording for `cause_not_visible`.** Proposed English for emails: "Keigan could not see the cause in the monitoring data it can read. The team is investigating." Is that acceptable to send to business stakeholders automatically (`AUTO_SEND_PRELIMINARY_REPORT=true`), or should a `cause_not_visible` preliminary report wait for approval? *Recommendation:* send it; silence is worse, and the wording makes no claim.
2. **Count outcomes on the metrics page (doc 24)?** "Share inconclusive" and "share not visible" per week are cheap after this. *Recommendation:* yes, as a small follow-up once a real model has run.
3. **Naming.** "Cause not visible in the data Keigan can see" is long for a badge; the badge says "Cause not visible" and the sentence says the rest. Confirm.

---

## Build notes (2026-11-23)

Built in the order of section 9, one commit per step. Differences from the design:

- **Gap reporting lives in the evidence service**, not in the graph: `EvidenceService` takes the `CoverageGapCollector` and reports services without telemetry, checks beyond the limit, refused or failed planner queries and results cut by the token budget (`set_aside_unread` and `select_for_investigation`). The graph reports only what it owns: services beyond the limit and perspectives that produced nothing. Gaps are stored with `persist_new` (a watermark), so the evidence stage stores its own before the hypotheses start and later stages add theirs.
- **AC-13 has one exception by design (D-A2-3):** an `inconclusive` proposal is lowered to `cause_not_visible` when no evidence item is a decisive signal. Every other proposal of `inconclusive` or `cause_not_visible` is kept.
- **`failure_reason` and two properties replace a stored flag on the draft:** `check_outcome` and `baseline_comparison` are computed from the draft, so they cannot disagree with `is_rule_out`.
- **AC-12 holds for seven of the eight scenarios.** In the vendor-outage scenario the offline probe reads the present rather than the historical window, so the evidence has no signal and the rules correctly turn the model's cause into "cause not visible" (status page, known issues).
- **Not done:** the incident list and board chip (5.3), a seeded investigation with gaps (10.3), the Teams card in the application's language (no application language exists), the browser check (AC-24; the machine was short of memory), the `docs/01`, `13` and `22` updates in 10.1.
- **Tests:** `tests/unit/ai/test_investigation_outcome_rules.py`, `tests/unit/services/test_investigation_coverage.py`, `tests/integration/services/test_evidence_honest_outcomes.py`, `tests/integration/ai/test_investigation_honest_outcomes.py`, `tests/integration/migrations/test_honest_outcomes_migration.py`, and additions to the investigation, notification, communication, Teams, retention and prompt-library tests.
