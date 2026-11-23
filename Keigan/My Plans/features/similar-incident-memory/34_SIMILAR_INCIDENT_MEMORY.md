# 34 — Similar-incident memory: "last time, the cause was ... and the fix was ..."

> **PHASES 1 TO 3 BUILT (2026-11-24); PHASES 4 TO 6 NOT BUILT.** The owner asked for the memory, its API and its screen (entries, matching, "Seen before"). The prompt section, the Ask Keigan tool, the measurement suites and semantic retrieval are still design only. Section 12 lists what was built and where it differs from this design.

Roadmap item **B1** (doc 21, product research, section 3.5, wave B). Written 2026-11-22 against branch `keigan-ui-ux`.

---

## 1. Purpose, status and how to use this document

**Purpose.** When a new incident looks like one Keigan has seen before, in the same application or another one the reader may see, show the responder what happened last time: the cause, the fix, how trustworthy that memory is (the engineers' verdict) and how old it is. Give the investigation's AI the same hint for the application's own past, labelled as a hint and never as evidence.

**Status.** Design, written 2026-11-22. Phases 1 to 3 built on 2026-11-24 (section 12); phases 4 to 6 not built. Every statement about existing code was checked in the source on 2026-11-22 and carries a `path:symbol` reference.

**How to use it.**
- Owner: read sections 2, 4.1 (especially M3 on semantic retrieval and M4 on access), 6 and 11.
- Implementer (when approved): build the phases of section 9 in order.
- Related documents: doc 08 (RAG proposal), doc 22 (evaluation harness; its `incident_memory` suite in section 9), doc 23 (Ask Keigan; a new tool), doc 33 (better suggested fixes; the fix plan this memory quotes), doc 06 (prompt safety and masking), doc 21 (sections 3.2, 3.5 B1, 4.4).

**Glossary.**

| Term | Meaning |
|---|---|
| Memory entry | One past incident (or standalone investigation) summarised for reuse: cause text, fix text, their sources, and its match keys. One active entry per incident. |
| Match key | A normalised, hashed fact about an entry: its service, a shared resource, an alert rule, an error signature, a change operation, a dependency target, the incident category. |
| Error signature | A log or exception template from strong evidence, normalised (numbers, ids and masking placeholders removed) and hashed. |
| Match | A past entry scored against the current investigation, with the reasons it matched. |
| Stale | An entry old enough, or whose service has gone, that the system may have changed since. Shown, never silently hidden. |

---

## 2. Goals, non-goals, anti-goals

### 2.1 Goals
1. **G1. Recall the right past incident** across applications and ticket text, ranked by how specific the shared facts are (the same error signature beats the same category).
2. **G2. Say what happened then**, in two short lines, preferring what people wrote or approved (resolution note, finalised postmortem) over what Keigan guessed.
3. **G3. Weigh by the engineers' verdicts.** A confirmed memory ranks above an unreviewed one; a memory whose analysis was marked incorrect never presents Keigan's cause as fact.
4. **G4. Keep staleness visible**: age on every match, a "may be out of date" label past a threshold, and "the service no longer exists" when it is gone.
5. **G5. Never show a person anything from an application they cannot read**, and never let one application's memory reach another application's AI output.
6. **G6. Measurable**: a no-model retrieval suite and the harness's paired suite (doc 22, section 9) say whether it helps.

### 2.2 Non-goals
- No vector store, embeddings or semantic search in the first build (decision M3; section 4.9 says when).
- No automatic action: a memory never mutes an alert, changes a priority or applies a fix.
- No cross-application memory in AI prompts (decision M4).
- No change to the recurring-incident detector (`services/intelligence_detectors.py:IntelligenceDetectors.recurring_incidents`); it counts repeats for predictive signals and stays as it is.
- No learning from free-text chat.

### 2.3 Anti-goals and controls

| Harm | Control | Checked by |
|---|---|---|
| **Stale memory invites confident, wrong action** (doc 21, 2.6: "stale runbooks are arguably worse than none") | Age on every match, stale label and reasons, prompt text says "hint, not proof, may be out of date"; the investigation's confidence rules are unchanged (only current evidence justifies confidence) | AC-9, AC-10, AC-14 |
| **Anchoring** on a past cause that only looks similar | Matched reasons are shown ("same error signature: ..."); keyword-only matches across applications are not shown; relevance feedback; the harness measures "incorrect memory used" | AC-6, AC-17 |
| **Leakage across applications** | SQL filter on the reader's readable applications before scoring; no counts of hidden matches; prompts use same-application memory only | AC-1 to AC-4 |
| **Wrong memory repeating** | An incorrect verdict demotes and relabels; an application admin can hide an entry; hidden entries leave prompts at once | AC-7, AC-12 |
| **Personal data in memory** | Built only from already-masked stored text, masked again, known person names replaced | AC-13 |

---

## 3. Current state (verified) and unknowns

### 3.1 What exists
- **The only memory today** is in `backend/keigan/ai/investigation_graph.py:InvestigationGraphRunner.context_node`: the three most recent investigations of the **same application** with `user_feedback_verdict == correct` (excluding the current one), ordered by `completed_at`, each as `- Confirmed earlier: <executive summary truncated to 300 characters>`. They go to the three hypothesis calls as the untrusted section "Recurring issues confirmed in the past" (`_hypothesis_node`), not to the synthesis. **They are the most recent, not the most similar**: nothing compares symptoms, services or errors. The limit 3 and the 300 characters are literals in code. A re-run of the same incident can receive its own earlier confirmed answer.
- **Verdicts.** `entities/incident_entities.py:Investigation.user_feedback_verdict` (`InvestigationFeedbackVerdict`: `correct`, `partially_correct`, `incorrect`), with comment and author. `services/investigation_service.py:InvestigationService.submit_feedback`: any reader may say `partially_correct` or `incorrect`; **only an application admin may say `correct`**, because "correct feeds later investigations" (V7). One verdict per investigation; a new one replaces the old. Audit event `investigation.feedback`.
- **Human-written outcomes.** `services/incident_service.py:IncidentService.resolve_incident` stores the resolution note, masked with `PiiMasker`, as an `incident_resolved` timeline event (`event_details_markdown`) and sends it to ServiceNow as close notes. Postmortems (`entities/incident_entities.py:PostmortemReport`) are drafted by AI, edited and finalised by an admin (`services/communication_service.py:CommunicationService.update_postmortem`, `finalize_postmortem`). **Edits change only `report_markdown`; `report_sections_json["root_cause"]` keeps the AI's original text**, so the approved root cause must be read from the final markdown's `## Root cause` section (heading written by `render_postmortem_markdown`).
- **Facts a match can use, already stored:** incident title and description (masked at intake, `incident_service.py`), category (`Incident.incident_category`), affected and investigated services (association tables), alerts with `rule_identifier`, `rule_name`, `alert_fingerprint` and `resource_reference` (`entities/alert_entities.py:Alert`) linked through `AlertGroup.investigation_id`, evidence rows with `condensed_patterns_json` templates and `signal_strength` (`InvestigationEvidence`; templates flagged as possible injection are replaced by a quoted marker in `services/evidence_service.py`), Azure Activity Log changes as `change` timeline events (`investigation_graph.py:evidence_node`), and each service's resource id (`MonitoredService.external_resource_identifier`) and component resource group.
- **Keyword ranking.** `services/knowledge_service.py:KnowledgeService.build_grounding_context` and `find_matching_runbooks` use `utils/text_utils.py:rank_with_bm25` over stored term frequencies; `tokenize_for_search` splits Latin words (camelCase and snake_case) and makes character bigrams for Japanese and Chinese. Everything is filtered to one `application_id`.
- **Access.** `services/authorization_service.py:AuthorizationService.readable_application_ids(current_user)`, `ensure_application_reader`, `ensure_application_admin`. Ask Keigan records the applications each answer used (`ChatAnswerRun.used_application_ids_json`) and hides answers when access is lost (doc 23).
- **Retention.** `services/incident_retention.py:purge_expired_incidents` deletes incidents and standalone investigations older than `INCIDENT_RETENTION_DAYS` (395), via `_delete_incident_batch` and `_delete_investigations`.
- **Jobs.** `workers/job_handlers.py` maps job names to `JobHandlerReference`s; `workers/job_queue.py:JobQueue.enqueue` takes a deduplication key.

### 3.2 What doc 21 and doc 08 say, checked
- Doc 21, 3.2: "the three most recent confirmed-correct investigations of the same application are added to the prompt as short summaries (300 characters each)". **Correct.** It does not say they are chosen by recency only.
- Doc 08, 3: "Index postmortems and confirmed RCAs as a separate `incident_memory` collection". Not built; doc 08 assumed vectors from the start. This design starts without them (M3).
- Doc 22, 9: an `incident_memory` suite (memory on and off, paired delta). Kept; section 4.10 adds a cheaper retrieval-only suite.

### 3.3 Unknowns
- How often real incidents repeat across MetLife applications, and whether alert rule names are shared between applications (they are when teams use the same Azure Monitor rule templates). The retrieval suite needs real labelled pairs to answer this.
- Whether ServiceNow ticket text is mostly English, Japanese or mixed per application.
- Whether some applications must never be compared even for a person who can read both (open question Q1).

---

## 4. Design

### 4.1 Decisions (made while the owner was away, revisit if wrong)

| # | Decision | Reason | Rejected alternative |
|---|---|---|---|
| M1 | **Precomputed memory entries with an inverted key table**, refreshed by jobs when an investigation completes, a verdict changes, an incident is resolved or a postmortem is finalised. | Matching needs evidence, alerts and changes from several tables; computing that per page view across all readable applications would be slow. A key table makes candidate lookup one indexed join. | Compute from source tables on every read. |
| M2 | **Structured keys first, keyword overlap second.** Score = weighted shared keys + weighted IDF keyword overlap, times a verdict multiplier. Weights live in a catalogue file. | The strongest signals of "same problem" are exact: the same error template, the same alert rule, the same shared cluster or dependency. Keyword overlap catches ticket wording. Both are explainable ("matched on ..."), which the anchoring control needs. | Keyword only (misses cross-application repeats with different ticket text); vectors only (unexplainable, needs infrastructure). |
| M3 | **No semantic retrieval in the first build.** Add it only when the measured triggers in 4.9 fire, through one retriever seam. | Doc 08's prerequisites (Azure AI Search or pgvector, an embedding deployment) are not provisioned, and nothing yet shows that vocabulary is what limits recall. | Build doc 08 first. |
| M4 | **Cross-application memory is shown to people, never given to the AI.** The investigation runs as the system and its output is read by everyone who can read *its* application; a cross-application memory in its prompt could leak into that output. Ask Keigan (which runs as the asking person and records used applications) may use cross-application memory. | Keeps G5 without a new permission model. | Give the AI cross-application memory filtered by "applications whose readers are a superset". Hard to compute and to keep true as groups change. |
| M5 | **Only admin-confirmed (`correct`) memory reaches the AI**, as today. `partially_correct` and unreviewed entries are shown to people with their label. | Keeps V7 (only an admin's verdict may feed later investigations). | Feed partially-correct entries with a lower weight. |
| M6 | **Prefer human text**: cause from a finalised postmortem's `## Root cause` section, else Keigan's analysis (labelled by verdict); fix from the resolution note, else the investigation's fix plan overview (doc 33) or the leading hypothesis's fix summary. | G2; people trust what colleagues wrote. | AI summaries only. |
| M7 | **One active entry per incident**: the latest completed investigation with a verdict, else the latest completed one; older ones are `superseded`. Standalone investigations get their own entry. | Re-runs must not crowd the list. | One entry per investigation. |
| M8 | **Never reveal that a hidden match exists** ("1 more you cannot see" is a leak). | G5. | Show a count. |
| M9 | **Weights and thresholds are a starting guess**, calibrated with the retrieval suite before release. | No labelled data exists yet. | — |

### 4.2 Data model (Alembic, when approved)

**Enumerations** (`backend/keigan/entities/status_values.py`):

| Enum | Values |
|---|---|
| `IncidentMemoryEntryStatus` | `active`, `superseded`, `hidden` |
| `IncidentMemoryKeyKind` | `service`, `shared_resource`, `alert_rule`, `error_signature`, `change_operation`, `dependency_target`, `incident_category` |
| `IncidentMemoryCauseSource` | `postmortem`, `investigation`, `none` |
| `IncidentMemoryFixSource` | `resolution_note`, `fix_plan`, `hypothesis_fix`, `none` |
| `IncidentMemoryRelevanceVerdict` | `relevant`, `not_relevant` |

**`incident_memory_entry`** (`backend/keigan/entities/incident_memory_entities.py`):

| Column | Type | Notes |
|---|---|---|
| `incident_memory_entry_id` | id (36) | primary key |
| `application_id` | FK `application`, CASCADE | |
| `investigation_id` | FK `investigation`, NO ACTION, unique | SQL Server allows one cascade path; code deletes entries before investigations (4.8) |
| `incident_id` | FK `incident`, NO ACTION, nullable, indexed | null for standalone investigations |
| `entry_status` | String(20), `values_check(IncidentMemoryEntryStatus)` | |
| `occurred_at` | UTC datetime | incident `opened_at`, else the investigation window start |
| `incident_title_text` | String(500) | masked |
| `cause_text`, `fix_text` | Text | masked, at most `INCIDENT_MEMORY_TEXT_MAXIMUM_CHARACTERS` each |
| `cause_source`, `fix_source` | String(20), checked enums | |
| `search_terms_json` | JSON | term frequencies (`term_frequencies`) of title, description, triage summary, key symptoms, cause and fix |
| `service_ids_json` | JSON | for the "service removed" stale check |
| `hidden_by_user_principal_name`, `hidden_at`, `hide_reason_text` | nullable; reason masked, at most 500 | |
| `built_at` | UTC datetime | last refresh |

Indexes: `(application_id, entry_status, occurred_at)`; unique `investigation_id`.

**`incident_memory_key`**: `incident_memory_entry_id` (FK CASCADE), `key_kind` (checked enum), `key_value_hash` String(64) (SHA-256 hex of the normalised value), `key_display_text` String(200) (masked, for "matched on ..."). Primary key (entry, kind, hash); index `(key_kind, key_value_hash)`.

**`investigation_memory_reference`** (an ordered association, like `investigation_matched_runbook`, following `OrderedLinkColumns`): `investigation_id` (FK CASCADE), `incident_memory_entry_id` (FK NO ACTION; deleting an entry deletes these rows first), `display_order`. Records which entries were given to this investigation's AI, so the page can say so and the decision trace (A3) and harness can see it.

**`incident_memory_relevance_feedback`**: `relevance_feedback_id`, `investigation_id` (FK NO ACTION), `incident_memory_entry_id` (FK CASCADE), `user_principal_name` String(320), `relevance_verdict` (checked enum), `recorded_at`. Unique `(investigation_id, incident_memory_entry_id, user_principal_name)`.

**Retention.** Entries, keys, references and feedback are deleted in `incident_retention.py:_delete_investigations` (and therefore in `_delete_incident_batch`) before the investigations they point at. No longer retention than incidents (open question Q3).

**Revision plan.** One revision `<id>_incident_memory` (down revision: head at build time) creating the four tables; Azure SQL scripts 01 to 06 regenerated, `migrations/<id>_incident_memory.sql`, demo SQL and ER diagram regenerated.

### 4.3 Match keys (`backend/keigan/services/incident_memory_keys.py`)
Built by one function `build_match_keys(facts) -> list[MatchKey]` used both for entries and for the current investigation, so the two always agree.

| Kind | Source | Normalised value | Across applications? |
|---|---|---|---|
| `service` | investigated and affected service ids | the service id | no (ids are per application) |
| `shared_resource` | `external_resource_identifier` of those services and their components' resource ids (AKS cluster, SQL server, APIM instance) | lower-case Azure resource id, trailing segments for child resources removed by a catalogue rule | **yes**: two applications on one cluster |
| `alert_rule` | the investigation's alerts (`Alert` via `AlertGroup.investigation_id`) | `rule_identifier` lower-cased, else `rule_name` normalised | yes |
| `error_signature` | condensed pattern templates of evidence rows with signal high or medium, not rule-outs, not flagged as injection | `utils/error_signature.py:normalize_error_template`: NFKC, lower-case, GUIDs and hex ids → `<id>`, numbers → `#`, masking placeholders → their category (`<email>`), whitespace collapsed, at most 300 characters | yes |
| `change_operation` | `change` timeline events within the change window | Activity Log operation name lower-cased plus the resource type | yes, low weight |
| `dependency_target` | evidence of failed dependencies (target host or name from the template) | lower-case host | yes |
| `incident_category` | `Incident.incident_category` | the category | yes, lowest weight |

Values are hashed for the index; `key_display_text` keeps a masked, shortened readable form for the "matched on" line.

### 4.4 Scoring (`backend/keigan/services/incident_memory_retriever.py`)
Catalogue `backend/keigan/resources/catalogs/incident_similarity.yaml` (starting guess, M9):
```yaml
key_weights: {error_signature: 0.35, alert_rule: 0.25, dependency_target: 0.15, shared_resource: 0.15, service: 0.15, change_operation: 0.10, incident_category: 0.05}
keyword_weight: 0.30
verdict_multipliers: {correct: 1.0, partially_correct: 0.8, none: 0.6, incorrect: 0.3}
cross_application_required_key_kinds: [error_signature, alert_rule, shared_resource, dependency_target]
```
1. **Candidates** (one query, readable applications only, status `active`, `occurred_at` before the current incident, not the same incident): entries sharing any key hash with the current keys; plus the most recent `INCIDENT_MEMORY_KEYWORD_CANDIDATE_LIMIT` active entries of the **same application** (keyword-only matches are same-application only).
2. **Structured score** = sum of the weights of the key kinds shared (each kind once), capped at 1.
3. **Keyword score** = IDF-weighted share of the current query's terms present in the entry (`Σ idf(t) over shared terms / Σ idf(t) over query terms`, IDF over the candidate set, tokens from `tokenize_for_search`). Bounded in 0 to 1 and not inflated when there is only one candidate (unlike a raw BM25 score).
4. **Raw** = min(1, structured + keyword_weight × keyword). **Final** = raw × verdict multiplier (live verdict of the entry's investigation).
5. Drop cross-application candidates that share none of `cross_application_required_key_kinds`. Drop final below `INCIDENT_MEMORY_MINIMUM_SCORE`. Sort by final, then newer first. Return the top `INCIDENT_MEMORY_MAXIMUM_SHOWN`.
6. Each match carries its reasons (kinds and display texts), its age in days, `is_stale` and stale reasons (`older_than_threshold` when age > `INCIDENT_MEMORY_STALE_AFTER_DAYS`; `service_removed` when none of `service_ids_json` still exists), whether it was given to this investigation's AI, and the reader's own relevance verdict.

### 4.5 Modules (one job each)

| Module | Job |
|---|---|
| `utils/error_signature.py` | Normalise and hash an error template |
| `services/incident_memory_keys.py` | Facts → match keys (4.3) |
| `services/incident_memory_builder.py` | Build or refresh one entry from an investigation: texts (M6), masking, keys, status (M7). Handler of the job `refresh_incident_memory_entry` (argument `investigation_id`, deduplication key `incident_memory:<investigation_id>`) |
| `services/incident_memory_retriever.py` | Candidates and scoring for a set of current keys and terms, given the allowed application ids (4.4). Behind a small `SimilarIncidentRetriever` protocol so a hybrid retriever can be added later (4.9) |
| `services/incident_memory_service.py` | Person-facing reads and writes: matches for an investigation, relevance feedback, hide and unhide; every access check |
| `ai/incident_memory_prompt.py` | Build the prompt section for the hypotheses from same-application, `correct`, non-hidden matches |
| `controllers/incident_memory_controller.py`, `dtos/incident_memory_dtos.py` | API (4.7) |
| `services/ask_keigan_memory_tools.py` | Ask Keigan tool `find_similar_incidents` (4.7) |
| `scripts/rebuild_incident_memory.py` | One-off, idempotent rebuild of all entries (first deployment, after a catalogue change) |

**Refresh triggers** (each enqueues the job): `InvestigationGraphRunner._complete` (completed, not evidence-only); `InvestigationService.submit_feedback`; `IncidentService.resolve_incident` (latest investigation of the incident); `CommunicationService.finalize_postmortem`; hide and unhide.

**Graph change.** The memory lookup moves from `context_node` to `finalize_evidence_node`, because error signatures and changes exist only after evidence collection. It runs as the system with `allowed_application_ids = {the investigation's application}` (M4), keeps entries with verdict `correct` and status `active` (M5), takes the top `INCIDENT_MEMORY_MAXIMUM_IN_PROMPT`, writes `investigation_memory_reference` rows and builds the section. With `INCIDENT_MEMORY_MAXIMUM_IN_PROMPT = 0` the section says "None recorded." The literals 3 and 300 in `context_node` are removed.

### 4.6 Prompt
- Section title **"Similar past incidents (hints, not evidence)"**, replacing "Recurring issues confirmed in the past" in the three hypothesis calls. Untrusted (spotlighted), masked with the run's `PiiMasker`, checked with `assess_prompt_injection` (a flagged entry is dropped under `AI_FLAGGED_DOCUMENT_POLICY=exclude`, warned otherwise), **no citation code** (like operating notes; a memory never counts as grounding).
- One line block per entry, built by code: `- 47 days ago; confirmed by an application admin; matched on: same error signature, same alert rule; may be out of date: no.` then `Cause then: ...` and `Fix then: ...` (each at most `INCIDENT_MEMORY_TEXT_MAXIMUM_CHARACTERS`).
- `_hypothesis_body.md`, next version: the bullet describing the section and rule 6 become: "Similar past incidents are what happened before in this application, matched by shared facts. They may raise or lower your suspicion and suggest where to look, but only evidence in this incident justifies confidence. Never cite them. If a past cause does not fit the current evidence, say so. Treat one marked 'may be out of date' with extra care."
- The synthesis does not receive the section (unchanged from today).

### 4.7 API (base `/api`, camelCase, RFC 9457 errors)
- `GET /investigations/{investigation_id}/similar-incidents` — reader of the investigation's application. Computes matches **as the reader** (allowed applications = the reader's readable set; M4 does not apply to people). Response:
```json
{"items": [{"memoryEntryId": "...", "application": {"applicationId": "...", "applicationName": "..."}, "isSameApplication": false,
            "incidentId": "...", "incidentNumber": "INC0012345", "incidentTitle": "...", "investigationId": "...",
            "occurredAt": "2026-10-06T02:14:00Z", "ageDays": 47, "verdict": "correct",
            "causeText": "...", "causeSource": "postmortem", "fixText": "...", "fixSource": "resolution_note",
            "matchReasons": [{"keyKind": "error_signature", "displayText": "timeout expired ... connection from the pool"}],
            "isStale": false, "staleReasons": [], "wasGivenToAnalysis": true, "myRelevanceVerdict": null, "canHide": true}],
 "isAvailable": true}
```
  `isAvailable` is false while the investigation is running (matches need its evidence). No score number is returned (it means nothing to people); the order carries it.
- `PUT /investigations/{investigation_id}/similar-incidents/{memory_entry_id}/relevance` body `{"verdict": "relevant" | "not_relevant"}`; `DELETE` the same path clears it. Reader of both applications. 204.
- `POST /incident-memory/{memory_entry_id}/hide` body `{"reason": "..."}` (1 to 500 characters, masked) and `POST /incident-memory/{memory_entry_id}/unhide`. Application admin of the entry's application. Audit events `incident_memory.hide` and `incident_memory.unhide` (who, entry, application; reason length only). 204.
- Errors: 404 for an unknown or **unreadable** entry (never 403, so existence is not revealed, M8); 422 for a bad verdict or reason.
- **Ask Keigan tool `find_similar_incidents`** (both scopes; doc 23's registry): input `{investigationId?: string, incidentId?: string, text?: string}` (exactly one), output items like the API's (without `canHide`), a code-written `summary`, `records` listing every application read so `used_application_ids_json` and the access-loss rules of doc 23 apply. Runs as the asking person.

### 4.8 Settings

| Name | Default | Range | Meaning |
|---|---|---|---|
| `INCIDENT_MEMORY_MAXIMUM_SHOWN` | 5 | 1 to 20 | Matches shown on the page and returned by the tool |
| `INCIDENT_MEMORY_MAXIMUM_IN_PROMPT` | 3 | 0 to 10 | Same-application confirmed matches given to the hypotheses; 0 turns prompt use off. Replaces today's literal 3 |
| `INCIDENT_MEMORY_MINIMUM_SCORE` | 0.3 (first guess 0.35; see section 12) | 0.0 to 1.0 | Matches scoring lower are not shown |
| `INCIDENT_MEMORY_STALE_AFTER_DAYS` | 180 | 7 to 395 | Older matches are labelled "may be out of date" |
| `INCIDENT_MEMORY_TEXT_MAXIMUM_CHARACTERS` | 400 | 100 to 2000 | Length of the stored cause and fix texts. Replaces today's literal 300 |
| `INCIDENT_MEMORY_KEYWORD_CANDIDATE_LIMIT` | 300 | 50 to 5000 | Recent same-application entries scored by keywords only |

Each in `settings.py`, `backend/.env.example` and Helm `backendEnvironment`, checked by a deployment-settings test.

### 4.9 Semantic retrieval: when it becomes worth it
Start with structured keys plus keyword overlap. Add semantic retrieval when **all** of these hold:
1. The retrieval suite (4.10) has at least 30 labelled pairs from real incidents (development set);
2. recall@3 is below 0.70, **and** at least half of the misses share no structured key and have keyword overlap below 0.2 (the miss is about vocabulary: synonyms, Japanese against English, paraphrase), which is the failure doc 08 section 2 predicts;
3. doc 08's prerequisites are provisioned (vector store, embedding deployment, identity).
If misses are instead about missing facts (no evidence, no alert), vectors will not help; better keys will.
**How it plugs in:** embed each entry's title, cause and fix (masked text only) into doc 08's `incident_memory` collection with `application_id` as a security filter field; a `HybridSimilarIncidentRetriever` takes the structured candidates ∪ vector top-k (filtered by the same allowed applications), fuses by reciprocal rank and keeps the explainable reasons (a vector-only match says "similar wording"). Cross-application vector-only matches stay hidden (same rule as keyword-only). The rebuild script backfills embeddings.

### 4.10 How it is measured
- **Retrieval suite (no model, cheap, every pull request once built):** a case file per labelled pair: the current investigation's facts (world seed), the expected entry id(s), and entries that must **not** be returned (another application the asking user cannot read). Metrics: recall@1, recall@3, mean reciprocal rank, `access_violation_count` (gate 0), `cross_application_keyword_only_count` (gate 0), and the miss classification of 4.9. Starts with synthetic pairs from the eight simulator scenarios (the same scenario on two applications sharing a cluster; the same scenario a month apart with different ticket wording, English and Japanese).
- **Harness `incident_memory` suite (doc 22, section 9):** paired runs with memory on and off; memory hit rate; `incorrect_or_stale_memory_used` (a planted incorrect or stale entry's cause appears in the leading hypothesis); paired delta of `grounded_correct`.
- **In the product:** share of investigations with at least one match shown; share of matches marked relevant by readers (with the sample size, as the metrics page does elsewhere); hidden entries per month. Shown on the reliability metrics page (doc 24) in phase 4.

---

## 5. User experience

### 5.1 "Seen before" card (`frontend/src/features/investigations/components/SimilarIncidentsCard.tsx`)
On the investigation page's RCA tab, after the summary card and before the three RCA cards; also a small "Seen before: 2" chip in `InvestigationHeader.tsx` that scrolls to it. Each match is a row:
- Line 1: incident number and title (a link to that incident when the reader can open it; it always can, by construction), the application name when it is another application, age ("47 days ago", `RelativeTime`), verdict badge (**Confirmed**, **Partly right**, **Not reviewed**, **Marked incorrect**).
- "Last time, the cause was: ..." with its source label ("from the approved postmortem", "Keigan's analysis, confirmed by an admin", "Keigan's analysis, not reviewed"). For **Marked incorrect**, the cause line reads "Keigan's analysis was marked incorrect" and the AI cause is not shown.
- "Fixed by: ..." with its source label ("resolution note", "Keigan's suggested plan").
- "Matched on: same error signature (…), same alert rule (…)".
- Stale: an amber "May be out of date" label with the reasons ("older than 180 days", "service no longer exists").
- "Given to Keigan's analysis" chip when it was in the prompt.
- Actions: **Relevant** / **Not relevant** toggle buttons (`aria-pressed`); for admins of that entry's application, "Hide from memory" (opens `ConfirmDialog` with a reason field).
- The card's description says: "Past incidents that share facts with this one. They are hints: check them against the current evidence."

### 5.2 States
Running investigation: the card shows "Available when the investigation finishes". No matches: the card is not shown (no empty card on every page), except a one-line note in the hypotheses tab intro when memory was given to the AI. Error: the card shows the shared `ErrorState` with retry; the rest of the page is unaffected. Loading: `Skeleton` rows.

### 5.3 Keyboard, screen readers, phone
A list (`<ul>`) of articles with headings; the verdict and stale labels are text; toggles are buttons with `aria-pressed`; the hide dialog traps focus. At 390 px each row stacks, actions wrap below, buttons are 44 px high.

### 5.4 Locales (en, es, es-MX falls back to es, fr, ja, nl, zh-CN)
`investigations.similarIncidents.*`: title, description, verdict labels, cause and fix source labels, match key kinds, stale reasons, relevance, hide dialog, states. Ask Keigan tool card field labels in the chat namespace, like tools 9 to 20.

---

## 6. Safety, access and privacy
- **Reading:** a person sees a match only when they can read its application (`readable_application_ids`, applied in the SQL candidate query, before scoring and limiting). Unreadable entries are indistinguishable from absent ones (404, no counts).
- **AI:** investigations use same-application, admin-confirmed memory only (M4, M5). Ask Keigan uses the asking person's readable set and records every application read.
- **Writing:** relevance feedback by any reader of both applications (it never changes what the AI receives; it is measurement); hide and unhide by admins of the entry's application, audited.
- **Masking:** entry texts are built only from stored text that was already masked (incident text at intake, resolution note, postmortem, AI output), passed through `PiiMasker` again, and through `ai/author_labels.py:mask_known_names` with the timeline's actor names (resolution notes are free text and may name people; doc 23 decision D2 keeps people out of AI output). Error signatures are normalised so masking placeholders become categories. Hide reasons are masked.
- **Stored:** summaries and hashes, no raw telemetry. Kept as long as the incident (395 days by default), deleted with it.
- **Prompt injection:** memory texts come from tickets, notes and AI output, so they are untrusted sections; templates already flagged as injection never become keys.

---

## 7. Acceptance criteria

| # | Criterion | Test type |
|---|---|---|
| AC-1 | A reader of application A only, viewing an A investigation, never receives a match from application B, even when B shares an error signature | integration (service) |
| AC-2 | A reader of A and B receives the B match with `isSameApplication = false` and its reasons | integration |
| AC-3 | `GET` and relevance `PUT` for an entry of an unreadable application return 404 | integration (controller) |
| AC-4 | The investigation prompt contains only same-application entries, even when a cross-application entry scores higher | integration (graph, scripted gateway) |
| AC-5 | Only `correct`, `active` entries reach the prompt; `partially_correct`, unreviewed and hidden do not | integration (graph) |
| AC-6 | A cross-application candidate matched only by keywords or category is not returned | unit (retriever) |
| AC-7 | A `correct` entry ranks above an otherwise identical unreviewed one; an `incorrect` entry's API item has no AI cause text | unit + integration |
| AC-8 | Re-running an incident supersedes the earlier entry; one active entry per incident | integration (builder) |
| AC-9 | An entry older than `INCIDENT_MEMORY_STALE_AFTER_DAYS` is returned with `isStale` and `older_than_threshold`; one whose services are all deleted has `service_removed` | unit |
| AC-10 | The prompt line of a stale entry says "may be out of date: yes" | unit (`incident_memory_prompt.py`) |
| AC-11 | Cause text comes from the final postmortem's edited `## Root cause` section, not from `report_sections_json`, when the postmortem is final | integration (builder) |
| AC-12 | Hiding removes the entry from the page and from the next investigation's prompt and writes one audit row; unhide restores it | integration |
| AC-13 | A resolution note "Taro Yamada restarted the pod, mail taro@example.com" is stored with the name replaced and the email masked | unit (builder) |
| AC-14 | The section has no citation code: an AI output citing anything for it keeps only valid codes | unit |
| AC-15 | `normalize_error_template` maps two templates differing only in numbers, GUIDs and placeholders to the same hash | unit |
| AC-16 | Every refresh trigger enqueues exactly one deduplicated job | integration (each service) |
| AC-17 | The Ask Keigan tool returns only readable applications and adds them to `used_application_ids_json`; losing access to one hides the answer (doc 23 rules) | integration |
| AC-18 | Retention deletes entries, keys, references and feedback with their investigations, with no foreign-key error on SQLite and in the Azure SQL script order | integration (retention) |
| AC-19 | The six settings exist with ranges, in `.env.example` and Helm, defaults equal; the literals 3 and 300 are gone from `investigation_graph.py` | unit (config, source scan) |
| AC-20 | New keys exist in the six locales; the card renders at 390 px without horizontal scroll | script + browser check |

---

## 8. Test plan (mirrors the source tree)
- `backend/tests/unit/utils/test_error_signature.py` (AC-15)
- `backend/tests/unit/services/test_incident_memory_keys.py`
- `backend/tests/unit/services/test_incident_memory_retriever.py` (AC-6, AC-7, AC-9)
- `backend/tests/unit/ai/test_incident_memory_prompt.py` (AC-10, AC-14)
- `backend/tests/integration/services/test_incident_memory_builder.py` (AC-8, AC-11, AC-13, AC-16)
- `backend/tests/integration/services/test_incident_memory_service.py` (AC-1, AC-2, AC-7, AC-12)
- `backend/tests/integration/controllers/test_incident_memory_controller.py` (AC-3)
- `backend/tests/integration/ai/test_investigation_memory.py` (AC-4, AC-5)
- `backend/tests/integration/services/test_ask_keigan_memory_tools.py` (AC-17)
- `backend/tests/integration/services/test_incident_retention.py` (extended, AC-18)
- `backend/tests/integration/migrations/test_incident_memory_migration.py`
- `backend/tests/unit/config/test_incident_memory_settings.py` (AC-19)
- Frontend: `SimilarIncidentsCard.test.tsx` (labels per verdict, no AI cause for incorrect, toggles), locale and contrast checks; browser check added to `capture-screens.mjs` (RCA tab with two matches, one stale and one from another application, 1440 and 390 px, light and dark).
- Retrieval suite (4.10) when the harness exists.

---

## 9. Phased build plan (for when the owner approves; not scheduled)

| Phase | Tasks | Size | Depends on | Demonstrable |
|---|---|---|---|---|
| 1. Entries | Enums, entities, Alembic and Azure SQL; `error_signature.py`; keys; builder and job; triggers; retention; rebuild script; demo seed builds entries | M | — | Entries with readable "matched on" keys for every seeded investigation |
| 2. Matching and API | Retriever, catalogue, service, controller, DTOs, settings; access tests | M | 1 | `GET /similar-incidents` returns matches across two demo applications that share a cluster |
| 3. Screens | `SimilarIncidentsCard`, header chip, relevance and hide, locales ×6, browser check | S to M | 2 | The RCA tab shows "Seen before" with verdict, age and stale labels |
| 4. AI and chat | Prompt section, graph move to `finalize_evidence_node`, `investigation_memory_reference`, Ask Keigan tool, metrics on the metrics page | S to M | 2; doc 23 registry | The hypotheses receive confirmed same-application memory; Ask Keigan answers "have we seen this before?" |
| 5. Measure | Retrieval suite; harness `incident_memory` suite; calibrate weights (M9) | S to M | A1 for the paired suite | Recall@3 and the paired delta in the report |
| 6. Semantic (conditional) | Section 4.9 | M | Triggers in 4.9 and doc 08 prerequisites | Hybrid retrieval with the same reasons and access rules |

Overall M (doc 21 estimate), plus phase 6 only if triggered.

---

## 10. Docs, migration and demo-data impact
- `ai-engine/06_AI_ENGINE_AND_PROMPT_SAFETY.md`: section 3.2 (memory moves to after evidence), 3.4 (the section), 5.1 and 5.2 item 13 (memory as untrusted, uncited), 7.7 (feedback loop now similarity-based).
- `architecture/03_DATABASE_DESIGN.md`, `15_ENTITY_RELATIONSHIP_DIAGRAM.md` (regenerated), `05_API_CONTRACT.md`, `13_SEQUENCE_DIAGRAMS.md` (incident to RCA: the memory lookup), `02_SYSTEM_ARCHITECTURE.md` (the job).
- `features/semantic-retrieval/08_RAG_PROPOSAL.md`: the `incident_memory` collection row points here and to the triggers of 4.9.
- `features/ai-evaluation-harness/22_...`: the retrieval suite beside `incident_memory`.
- `features/ask-keigan-chat/23_...`: tool 21 `find_similar_incidents`.
- Azure SQL: scripts 01 to 06, `migrations/<id>_incident_memory.sql`, demo data regenerated.
- Demo seed (`seed/investigation_seed.py`, `seed/foundation_seed.py`): two applications that share an AKS cluster (the seed already has `azaustaekub14470pr0101` for Channel APIs for Digital; add the same resource id to one service of a second application), one past incident per scenario dated 40 and 220 days back (one stale), one with a resolution note, one with a final postmortem, one marked incorrect; then the builder runs.

---

## 11. Risks and mitigations; open questions for the owner

| Risk | Mitigation |
|---|---|
| Starting weights are wrong | M9: calibrate with the retrieval suite before release; weights are in a catalogue |
| Generic keys (a common timeout template, a shared "High CPU" rule) match everything | IDF-like down-weighting of very common key hashes (a key present in more than a catalogue share of entries counts half); measured by precision from relevance feedback |
| Memory reinforces a wrong diagnosis | Only admin-confirmed memory reaches the AI; incorrect memory is relabelled; hide; the harness gates `incorrect_or_stale_memory_used` |
| People over-trust "Confirmed" | The label is about the past incident; the card says "hints: check against the current evidence" |
| Load from cross-application candidate queries | Indexed key lookup; candidate limits; matches computed per page view only for finished investigations |

**Open questions for the owner**
1. **Q1. Segregation:** are there applications whose incidents must never be compared, even for people who can read both (regulatory or business separation)? If yes, add a per-application "share memory across applications" switch.
2. **Q2. Partly-correct memory in prompts:** keep it out (M5), or let it in at a lower weight once accuracy is measured?
3. **Q3. Longer memory:** should summaries outlive the 395-day incident retention (they are small and masked)? A compliance question.
4. **Q4. Resolution notes in AI prompts:** they are human free text; names are replaced by known-name masking, but other personal details are only pattern-masked. Acceptable?
5. **Q5. When to build:** the status page says "when the harness or users show repeat incidents are missed"; this design does not change that.

---

## 12. Build notes (2026-11-24): phases 1 to 3 built

Built on branch `keigan-ui-ux` at the owner's request (the owner then said B1 was wanted). Phases 4 to 6 (prompt section, Ask Keigan tool, measurement, semantic retrieval) are **not built**.

**What exists.**
- Enums in `status_values.py` (`IncidentMemoryEntryStatus`, `IncidentMemoryKeyKind`, `IncidentMemoryCauseSource`, `IncidentMemoryFixSource`, `IncidentMemoryRelevanceVerdict`); entities `IncidentMemoryEntry`, `IncidentMemoryKey`, `IncidentMemoryRelevanceFeedback` in `entities/incident_memory_entities.py`; revision `e6b2d8f4a0c3` (64 to 67 tables); Azure SQL scripts, migration script, ER diagram and demo data regenerated.
- `utils/error_signature.py`, `services/incident_memory_keys.py`, `incident_memory_scoring.py` (pure), `incident_memory_builder.py` (the job `refresh_incident_memory_entry`), `incident_memory_retriever.py` (`SimilarIncidentRetriever` protocol and `StructuredKeywordRetriever`), `incident_memory_service.py`, `incident_memory_retention.py`; `controllers/incident_memory_controller.py`; `dtos/incident_memory_dtos.py`; catalogue `resources/catalogs/incident_similarity.yaml`.
- Five settings (`INCIDENT_MEMORY_MAXIMUM_SHOWN`, `_MINIMUM_SCORE`, `_STALE_AFTER_DAYS`, `_TEXT_MAXIMUM_CHARACTERS`, `_KEYWORD_CANDIDATE_LIMIT`) in `settings.py`, `.env.example` and Helm, with a test that checks all three.
- Refresh triggers: an investigation completing (not evidence-only), `submit_feedback`, `resolve_incident`, `finalize_postmortem`. Retention: incident retention and application deletion remove entries, keys and answers before the investigations. `scripts/rebuild_incident_memory.py` builds what is missing and is safe to repeat. The demo seed builds an entry for every seeded completed investigation.
- Screen: `SimilarIncidentsCard.tsx` on the RCA tab (shown only when there is a match), a "Seen before: N" chip in the investigation header, relevance buttons, and a hide dialog for application admins; `investigations.similarIncidents.*` in the six languages; `api/incidentMemoryApi.ts`.

**Deviations from the design above (all deliberate).**
1. **All seven key kinds are produced** (the last three were added the same day): `alert_rule` from the rules of the alerts grouped into the investigation (the rule's own identifier, else its name folded to lower case); `change_operation` from the Activity Log operation name of the change evidence (stored as `operationName` in each change pattern from now on; an older pattern's operation is read from its sample line); `dependency_target` from the host in a failed-dependency message (port removed, lower case). A change pattern is never also an error signature. Note the weights: one alert rule alone is 0.25 and one dependency 0.15, so neither alone reaches the minimum score of 0.35; it takes two shared facts (or one plus the confirmed verdict and words).
2. **No down-weighting of very common keys** (the first risk in section 11). The shared words use IDF over the candidate set; the keys do not. Revisit when real data shows a key that matches everything.
3. **`investigation_memory_reference` and `INCIDENT_MEMORY_MAXIMUM_IN_PROMPT` belong to phase 4** and were not added; the API therefore has no `wasGivenToAnalysis` field yet.
4. **A past incident marked incorrect is listed apart, labelled "Marked incorrect before".** With the first weights its multiplier (0.3) kept it below the minimum score, so it could never appear. Now it has no multiplier: it is judged on its raw score against the same minimum, shown after the others in its own section, at most `INCIDENT_MEMORY_MAXIMUM_REJECTED_SHOWN` (default 2; 0 hides them), and its cause text is never repeated. It is never given to the AI (phase 4 uses confirmed ones only).
5. **Hide and unhide do not queue a refresh.** They set the status directly, and unhide re-settles the incident's live entry in the same request.
6. **Search words come from the title, the incident description, the triage summary and key symptoms, and the stored cause and fix.** Error templates are keys, not words.
7. **Links in the card go to the past investigation** (always readable by construction), not to the incident.

**Phase 5, the retrieval suite (built 2026-11-24, no model needed).** `backend/tests/support/incident_retrieval_cases.yaml` holds 12 labelled synthetic cases (the same error a month apart with different wording, English against Japanese, two applications on one cluster, a reader who may read only one of them, wording alone across applications, confirmed against unreviewed, marked incorrect, hidden, a later incident, the same category only, an alert rule plus a failing dependency, and a documented miss). `tests/support/incident_retrieval_suite.py` builds each case's past incidents in the database, asks the **real** retriever as a reader with the case's readable applications, removes them again and computes recall@1, recall@3, mean reciprocal rank, `access_violation_count` and `cross_application_keyword_only_count` (both gates, both 0), and classifies each miss as vocabulary (no shared key, under 0.2 word overlap) or missing facts. `tests/integration/services/test_incident_retrieval_suite.py` runs it with the gates and floors (recall@1, recall@3 and MRR all at least 0.85). Run `pytest tests/integration/services/test_incident_retrieval_suite.py -s` to print the report. There are 12 cases, not the 30 real pairs section 4.9 asks for before deciding about semantic retrieval, so the numbers say the rules behave as designed, not how well they find real incidents.

**What the suite found, and the change it caused.** An incident nobody has reviewed scores 0.6 times its facts; the same error and the same service give 0.50 and so 0.30, which the first minimum of 0.35 dropped. Unreviewed is the usual state, so the default `INCIDENT_MEMORY_MINIMUM_SCORE` is now **0.30**. One miss remains, on purpose: the same words and no shared fact inside one application score at most 0.30 times the verdict and are not shown. The suite classifies it as a weights question (the words overlap strongly), not a vocabulary one, so it does not argue for vectors.

**Phase 4a, the hint for the hypotheses (built 2026-11-24).** The old "Recurring issues confirmed in the past" text (the last three correct investigations' executive summaries, a literal 3 and a literal 300) is gone. After the evidence is stored (`finalize_evidence_node`, because error signatures and changes exist only then) the graph asks the real retriever **as the system with only this application allowed** (M4), keeps entries an admin confirmed (M5; marked-incorrect ones never), takes the top `INCIDENT_MEMORY_MAXIMUM_IN_PROMPT` (default 3; 0 gives none), writes `investigation_memory_reference` rows (revision `f7c3e9a1b5d2`) and passes one section, **"Similar past incidents (hints, not evidence)"**, built by `ai/incident_memory_prompt.py` from stored fields: untrusted, masked, checked with `assess_prompt_injection` (dropped under `AI_FLAGGED_DOCUMENT_POLICY=exclude`, flagged otherwise), with no citation code. A failure to look up never stops an investigation. The shared hypothesis body's description and rule 6 are rewritten per 4.6 and the three hypothesis prompts are version 7. The API's `wasGivenToAnalysis` and a "Shown to the analysis" chip on the card say which suggestions the AI saw. Two limits: the lookup takes the retriever's top results first (the `INCIDENT_MEMORY_MAXIMUM_SHOWN`) and then keeps the confirmed ones, so a confirmed incident ranked below the shown ones is not given; and what the AI does with the hint can only be judged with a real model (part of `37_REAL_MODEL_TEST_PLAN.md`, not run).

**Phase 4b, the Ask Keigan tool (built 2026-11-24).** `find_similar_incidents` (`services/ask_keigan_memory_tools.py`, registered by importing `ask_keigan_tools`), in both scopes, takes exactly one of `investigation_id` (bound in an investigation conversation), `incident_id` (its latest finished investigation) or `text` with `application_code`. It runs `IncidentMemoryService` as the asking person, searches only the applications the conversation covers, re-checks each application that contributed (access removed during an answer refuses it) and lists them as read. The output has a code-written summary, the cause and fix with their sources, `reviewed_as`, `matched_on`, staleness and `was_marked_incorrect`, and no score. The offline planner plans it from "have we seen this before?" and "similar incidents". The investigation scope now offers nine tools, not eight.

**One scoring change for it.** An incident with no facts at all (a description typed in words, or an investigation with nothing to key on) is compared on its words, which then carry the whole score instead of the 0.30 they are worth next to shared facts. Otherwise a text question could never reach the minimum score. Words still never cross applications. The suite's former known miss is now found, and a new case checks that the same words do not bring back an incident whose facts disagree.

**Checked, not assumed.** Access: a reader never receives an entry of an application they cannot read, and an unreadable or unknown entry answers 404 for relevance, hide and unhide (tests in `tests/integration/controllers/test_incident_memory_controller.py` and `tests/integration/services/test_incident_memory.py`). **Not checked:** the screen in a browser, real incident wording, and the quality of the weights; the retrieval suite of phase 5 does not exist yet.
