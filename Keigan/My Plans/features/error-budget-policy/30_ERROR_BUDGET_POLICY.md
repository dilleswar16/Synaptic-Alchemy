# 30 — Error-budget policy that acts

Roadmap item **C2** (doc 21, product research, section 3.5, wave C "Close the loop"). Written 2026-11-22 against branch `keigan-ui-ux`.

---

## 1. Purpose, status and how to use this document

**Purpose.** Let each application team agree, in Keigan, what happens when reliability costs too much, and have Keigan hold them to it: measure how much of each SLO's error budget an incident used; when one incident uses more than the agreed share, require a postmortem with at least one top-priority action item that prevents the root cause; when one kind of incident keeps using budget over a quarter, require a top-priority item for that kind; when a budget is used up, show the team's own agreed response everywhere the SLO appears. Keigan enforces this **inside Keigan only** (it blocks finalising a postmortem, raises an item in "Needs attention", sends a message); it never blocks a deployment or changes a customer system.

**Status.** Design, written 2026-11-22; not built.

**Part of a set of four specs with one data model** (build order C1 → C2 → C3 → C4):

| Doc | Uses from this doc | This doc needs |
|---|---|---|
| 29 Action items (C1) | | `action_item` with `action_priority = top`, `action_type = prevent`; `ActionItemService`; the finalise hook in `CommunicationService.finalize_postmortem`; the "Needs attention" list of `ActionItemOverviewService`; the postmortem prompt v2 with `priority` |
| 31 Weekly health review (C3) | budget impacts of the week; open breaches | |
| 32 Runbook health (C4) | nothing | |

**How to use it.** Owner: sections 2, 4.1 and 11. Builder: section 9 in order. References to code were checked on 2026-11-22.

**Glossary.**

| Term | Meaning |
|---|---|
| Error budget | `1 − target` of an SLO, in events over the SLO's window: 1,000,000 requests in the window at 99.9 % allow 1,000 bad requests (Google SRE Workbook) |
| Budget window | The SLO's own `rolling_window_days` (30 by default in Keigan), so a share here equals the drop in "budget remaining" on the SLO page |
| Incident budget impact | The bad events of an SLO during an incident divided by that SLO's budget in the window ending when the incident ended |
| Policy breach | A recorded fact that a policy threshold was crossed, with a requirement (`open`, `met`, `waived`, `ended`) |
| Outage class | Incidents with the same recurrence key (category and primary service; doc 29, `incident_recurrence.recurrence_key`) |

---

## 2. Goals, non-goals, anti-goals

### 2.1 Goals
1. **G1. A number per incident**: "this incident used 34 % of the Checkout availability budget", per affected SLO, provisional while the incident is open, final a day after it is resolved.
2. **G2. A policy the team writes down in advance**, per application, with Google's example as defaults: 20 % for one incident in the SLO's window; 20 % for one outage class over a quarter; the team's own words for what they do when a budget is used up.
3. **G3. The policy acts inside Keigan**: a postmortem draft is started automatically; finalising it requires an accepted top-priority `prevent` action item or a recorded waiver; open requirements appear in "Needs attention" and in the weekly review; leads are told.
4. **G4. Honest maths**: no figure when there is not enough data, every figure shows its inputs (bad events, budget events, window, coverage).

### 2.2 Non-goals
- **No release freeze enforcement.** Google's example halts changes when the budget is exhausted. Keigan has no deployment pipeline access (B4 parked) and must not act on customer systems (execution parked, E2). It shows the team's agreed response; people apply it.
- No composite or weighted SLOs, no SLOs as code (roadmap ideas, not C2).
- No per-SLO policy or per-tier defaults in v1 (one policy per application; open question 3).
- No change to burn-rate alerting (see 3.2: its thresholds are hard-coded and the stored per-SLO policy is ignored; that is a separate fix).
- No CTO escalation workflow (Google's escalation clause); a waiver with a reason is the release valve.

### 2.3 Anti-goals and controls
| Anti-goal | Control | AC |
|---|---|---|
| A wrong number blocks people (bad data makes a small incident look huge) | Shares are computed only with enough coverage and events; the gate blocks only on a **final** impact; every block can be waived with a reason; the inputs are shown | AC-4, AC-5, AC-12 |
| Keigan "acting" on a customer system | Every action is inside Keigan (a draft, a requirement, a message). No new integration writes | AC-15 |
| A policy nobody agreed to | The policy is **off** until an application admin turns it on; impacts are shown either way as information | AC-1 |
| Gaming the requirement with an empty item | The qualifying item must be accepted (not proposed), `top`, `prevent`, not `wont_do`; turning it to `wont_do` later reopens the requirement | AC-9, AC-10 |
| Double counting overlapping incidents as "budget spent" | Shares are per incident and are not added; the screen says so; the quarter rule counts bad events once per SLO measurement window | AC-7 |

---

## 3. Current state (verified) and unknowns

### 3.1 What exists

| Topic | Fact | Evidence |
|---|---|---|
| SLI data | Good and total event counts per SLI every 5 minutes (`sli_measurement`), unique per window; collection every `SLI_COLLECTION_INTERVAL_MINUTES`, catching up at most 24 h back. Raw rows kept `SLI_RAW_RETENTION_DAYS` (90). | `backend/keigan/entities/slo_entities.py:SliMeasurement`; `backend/keigan/services/slo_service.py:SloService.collect_due_measurements`; `administration_service.py:run_retention_cleanup` |
| SLO | `target_percentage`, `rolling_window_days` (default 30), `burn_rate_policy_json`. | `slo_entities.py:ServiceLevelObjective` |
| Budget maths | `burn_rate(good, total, target)`, `error_budget_minutes(target, days)`. The dashboard computes `errorBudgetRemainingPercentage = (1 − (bad/total)/(1 − target)) × 100` over the SLO window and the status `breached` when compliance is below target, `at_risk` when remaining < 30 % or the 6 h burn > 2 (literals). | `backend/keigan/utils/statistics_utils.py`; `slo_service.py:SloService._summaries`; `status_values.py:SloHealthStatus` |
| Burn alerts | Multi-window page (1 h and 5 min above 14.4×) and ticket (6 h and 30 min above 6×) alerts stored in `slo_burn_alert`, routed as internal alerts and emailed to `slo_burn_alert` subscribers. Supporting-signal SLIs excluded. | `slo_service.py:evaluate_burn_rates`, `PAGE_BURN_RATE`, `TICKET_BURN_RATE`; `notification_service.py:notify_slo_burn_alert` |
| Signals | `error_budget_exhaustion` detector forecasts exhaustion and says "already exhausted" when remaining ≤ 0. | `backend/keigan/services/intelligence_detectors.py:PredictiveDetectors.error_budget_forecasts` |
| Incidents | `opened_at`, `detected_by_keigan_at`, `resolved_at`, `keigan_priority`, `incident_category`, affected services (first = primary). Linked alert groups give the earliest alert (`reliability_metrics_service.py:_incidents`). | `backend/keigan/entities/incident_entities.py:Incident`; `backend/keigan/services/reliability_metrics_service.py` |
| Resolution paths | `IncidentService.resolve_incident` (Keigan button) and `_synchronize_existing_incident` (ServiceNow state resolved or closed). | `backend/keigan/services/incident_service.py` |
| Postmortem | Generated by job `generate_postmortem` with a free-text `generation_trigger`; finalised by `finalize_postmortem` (doc 29 adds the action-item gate there). The postmortem prompt already asks for "SLO or error budget when known" in the impact, but no budget figure is given to it. | `communication_service.py`; `resources/prompts/postmortem_report.md` |

### 3.2 Found while checking (not fixed here)
- `ServiceLevelObjective.burn_rate_policy_json` is written at SLI proposal acceptance (`sli_proposal_service.py`, 14.4 and 6 with windows) and returned by the API, but `evaluate_burn_rates` ignores it and uses the module constants. A team that "changes" its burn policy changes nothing. Separate fix; noted for doc 09.
- The SLO status thresholds (30 % remaining, burn 2) and `MINIMUM_EVENTS_IN_LONG_WINDOW = 50` are literals. This spec does not reuse them; its own thresholds are settings.
- Doc 21 says "Error-budget policy that triggers actions ⬜": correct; nothing exists.

### 3.3 Unknowns
1. Whether the demo's simulated SLI data makes any seeded incident cross 20 % (section 10 says how the seed handles both outcomes without faking numbers).
2. How late SLI data arrives in production for log-query SLIs; the default "final after 24 h" assumes collection catches up within a day (it catches up at most 24 h back, 3.1).

---

## 4. Design

### 4.1 Decisions (made while the owner was away, revisit if wrong)

| # | Decision | Reason | Rejected alternative |
|---|---|---|---|
| C2-D1 | **Budget window = the SLO's own window** (not a fixed four weeks) | The share then equals the fall in "budget remaining" the team sees on the SLO page; Google uses four weeks because their SLO window is four weeks | A fixed 28-day window (two different budgets for one SLO) |
| C2-D2 | **Event-based budget**: `budget events = (1 − target/100) × total events in the window ending at the incident's end` | Google's own definition; matches Keigan's stored counts | Minutes of downtime (Keigan's SLIs are ratios, not uptime) |
| C2-D3 | **Impact window** = from the earliest of `opened_at`, `detected_by_keigan_at` and the first linked alert's `first_seen_at`, to `resolved_at` (or now while open) | Bad events before the ticket was opened belong to the incident; the first alert is the best start Keigan has | Only `opened_at` (understates incidents with slow detection, which are the ones that matter) |
| C2-D4 | **Which SLOs**: enabled SLIs with an SLO, excluding `supporting_signal`, whose service is one of the incident's affected services; SLIs with no service count for every incident of the application; an incident with no affected services counts against every SLO of the application | Same exclusion as burn alerts; application-level SLIs are affected by any incident | Primary service only (misses multi-service incidents) |
| C2-D5 | **Provisional, then final**: impacts recompute hourly while the incident is open and until `ERROR_BUDGET_POLICY_FINAL_AFTER_HOURS` after resolution; then frozen | Late SLI data; a frozen number can be cited in a postmortem | Compute once at resolution |
| C2-D6 | **Stored impacts**, one row per incident and SLO | Raw SLI rows expire after 90 days; the history and the quarter rule need the numbers | Compute on read |
| C2-D7 | **Policy is off by default** per application; impacts are always computed and shown | Google: the policy matters only if the team agreed in advance (doc 21, 2.4) | On for every application |
| C2-D8 | **"Requires a postmortem"** means: a draft is started automatically (`generation_trigger = "error_budget_policy"`) and finalising it needs an accepted `top` `prevent` item or a waiver | A requirement Keigan can check; the draft makes it cheap to comply | Only a notification (nothing holds) |
| C2-D9 | **The gate blocks only on a final impact**; a provisional breach shows a warning | Do not block on numbers that may still change | Block on provisional |
| C2-D10 | **Waivers by application admins with a written reason** (minimum length), audited, shown on the postmortem and in the weekly review | A release valve for wrong data or accepted risk; visibility discourages abuse | Keigan-admin-only waivers (central bottleneck; open question 2) |
| C2-D11 | **Budget exhausted** = the SLO's status is `breached` (compliance below target over its window); ends when compliance is back at or above target | Google: "until the service is back within its SLO"; reuses the existing status | Remaining ≤ 0 with a recovery margin (another threshold to tune) |
| C2-D12 | **Quarter rule uses raw SLI rows**, so its window must not exceed `SLI_RAW_RETENTION_DAYS` (validated) | Exact budget for the quarter; 90 days fits today's retention | Approximating from stored four-week impacts |

### 4.2 Data model

**New enums** (`status_values.py`):

```python
class IncidentBudgetImpactState(StrEnum):
    PROVISIONAL = "provisional"        # the incident is open or resolved less than FINAL_AFTER_HOURS ago
    FINAL = "final"
    INSUFFICIENT_DATA = "insufficient_data"   # coverage or volume below the minimums; no share is stated

class ErrorBudgetBreachKind(StrEnum):
    SINGLE_INCIDENT = "single_incident"
    OUTAGE_CLASS = "outage_class"
    BUDGET_EXHAUSTED = "budget_exhausted"

class ErrorBudgetRequirementStatus(StrEnum):
    OPEN = "open"
    MET = "met"
    WAIVED = "waived"
    ENDED = "ended"        # budget_exhausted only: the SLO is back within target
```

`ActionItemSource` (doc 29) gains `ERROR_BUDGET_POLICY = "error_budget_policy"` (items created from a breach card for the outage-class rule); this revision replaces `ck_action_item_source_kind_values`.

**Table `error_budget_policy`** (entity `ErrorBudgetPolicy` in a new module `backend/keigan/entities/error_budget_entities.py`; `AuditColumnsMixin`). One row per application, created on the first save only (a read never writes; a missing row means "off, defaults"):

| Column | Type | Rule |
|---|---|---|
| `error_budget_policy_id` | String(36) PK | |
| `application_id` | FK `application` CASCADE, unique | `uq_error_budget_policy_application_id` |
| `is_enabled` | Boolean, default false | |
| `single_incident_threshold_percent` | Float, nullable | null = setting default; 1–100 |
| `outage_class_threshold_percent` | Float, nullable | null = default; 1–100 |
| `outage_class_window_days` | Integer, nullable | null = default; 7 to `SLI_RAW_RETENTION_DAYS` |
| `exhausted_budget_guidance_text` | Text, nullable | the team's agreed response, at most `ERROR_BUDGET_POLICY_GUIDANCE_MAXIMUM_CHARACTERS`; masked and sanitised; never sent to a model |

**Table `incident_budget_impact`** (entity `IncidentBudgetImpact`):

| Column | Type | Rule |
|---|---|---|
| `incident_budget_impact_id` | String(36) PK | |
| `incident_id` | FK `incident` CASCADE, not null | the one cascade path |
| `application_id` | String(36), not null, index | recorded fact without FK (one cascade path rule), like `chat_run_step.application_id` |
| `slo_id` | FK `service_level_objective` NO ACTION, nullable | released to null when the SLO is deleted; the snapshot columns keep the meaning |
| `sli_name_text` | String(200) | snapshot |
| `target_percentage` | Float | snapshot at evaluation |
| `budget_window_days` | Integer | the SLO window used |
| `impact_window_start`, `impact_window_end` | DateTime | 4.3 |
| `budget_window_start`, `budget_window_end` | DateTime | `end = impact_window_end`, `start = end − budget_window_days` |
| `bad_event_count` | BigInteger | `Σ (total − good)` inside the impact window |
| `impact_total_event_count` | BigInteger | `Σ total` inside the impact window |
| `window_total_event_count` | BigInteger | `Σ total` inside the budget window |
| `data_coverage_percent` | Float | measured 5-minute windows with events ÷ windows in the budget window × 100 |
| `budget_event_count` | Float, nullable | null when insufficient |
| `budget_share_percent` | Float, nullable | null when insufficient |
| `is_service_matched` | Boolean | true when matched by an affected service; false when matched as an application-level SLI or because the incident names no service |
| `impact_state` | String(20), `values_check(IncidentBudgetImpactState)` | |
| `evaluated_at` | DateTime | |

Unique `uq_incident_budget_impact_incident_id_slo_id`. Index `ix_incident_budget_impact_application_id_evaluated_at`.

**Table `error_budget_policy_breach`** (entity `ErrorBudgetPolicyBreach`; `AuditColumnsMixin`):

| Column | Type | Rule |
|---|---|---|
| `error_budget_policy_breach_id` | String(36) PK | |
| `application_id` | FK `application` CASCADE, not null, index | |
| `breach_kind` | String(30), `values_check(ErrorBudgetBreachKind)` | |
| `incident_id` | FK `incident` NO ACTION, nullable, index | single_incident only |
| `incident_reference_text` | String(60), nullable | snapshot of the number |
| `slo_id` | FK `service_level_objective` NO ACTION, nullable | the SLO with the largest share (single), the SLO concerned (class, exhausted) |
| `sli_name_text` | String(200) | snapshot |
| `recurrence_category` | String(40), nullable | outage_class only |
| `recurrence_service_id` | String(36), nullable | outage_class only; recorded fact without FK |
| `recurrence_service_name_text` | String(200), nullable | snapshot |
| `measured_share_percent` | Float, nullable | null for budget_exhausted |
| `threshold_percent` | Float, nullable | the threshold in force at detection |
| `window_days` | Integer | SLO window (single, exhausted) or the class window |
| `detected_at` | DateTime | |
| `requirement_status` | String(20), `values_check(ErrorBudgetRequirementStatus)` | |
| `requirement_changed_at` | DateTime | |
| `qualifying_action_item_id` | FK `action_item` NO ACTION, nullable | the item that met the requirement (released to null if ever deleted; tracked items are never deleted, doc 29) |
| `waived_by_user_principal_name` | String(320), nullable | |
| `waiver_reason_text` | String(1000), nullable | masked |
| `notified_at` | DateTime, nullable | |
| `is_provisional` | Boolean | single_incident only: the impact behind it is not final yet |

Filtered unique indexes (portable like `uq_incident_external_number`):
- `uq_error_budget_policy_breach_single_incident` on (`incident_id`) where `breach_kind = 'single_incident'`.
- `uq_error_budget_policy_breach_open_outage_class` on (`application_id`, `recurrence_category`, `recurrence_service_id`) where `breach_kind = 'outage_class' AND requirement_status = 'open'`.
- `uq_error_budget_policy_breach_open_exhausted` on (`slo_id`) where `breach_kind = 'budget_exhausted' AND requirement_status = 'open'`.

**Reference release.** New NO ACTION keys on `service_level_objective` and `incident` and `action_item`. `SloService.delete_slo` and `delete_sli` call `release_references(self.session, ServiceLevelObjective.slo_id, ids)` before deleting (nullable columns become null, rows stay). Incident retention clears `error_budget_policy_breach.incident_id` (keeps the snapshot) in the same statement block doc 29 adds; `incident_budget_impact` cascades with the incident (impacts of expired incidents are no longer needed; the breach keeps the share). The application delete path releases SLO ids as it releases service ids.

**Alembic revision** `<new id>_error_budget_policy`: three tables, the filtered indexes, and the replaced `ck_action_item_source_kind_values`. Tables 59 → 62. Azure SQL regenerated (section 10).

**Retention.** Policies live with the application. Impacts live with the incident. Breaches: `ended`, `met` and `waived` breaches older than `ERROR_BUDGET_POLICY_BREACH_RETENTION_DAYS` are deleted by `run_retention_cleanup`.

### 4.3 The maths (pure module `backend/keigan/services/error_budget_math.py`, unit-tested)

```python
@dataclass(frozen=True)
class MeasurementTotals:
    good: int
    total: int
    measured_window_count: int   # 5-minute windows with total > 0

def impact_window(opened_at, detected_at, first_alert_at, resolved_at, now) -> tuple[datetime, datetime]
    # start = min of the known moments; end = resolved_at or now; both floored to the 5-minute grid (SAMPLE_INTERVAL_MINUTES)

def budget_share(impact: MeasurementTotals, window: MeasurementTotals, target_percentage: float, window_days: int,
                 minimum_coverage_percent: float, minimum_window_events: int) -> BudgetShare
    # allowed_ratio = 1 - target/100 (<= 0 -> insufficient: a 100 % target has no budget)
    # coverage = window.measured_window_count / (window_days * 288) * 100
    # insufficient when coverage < minimum_coverage_percent or window.total < minimum_window_events
    # scaled_window_total = window.total * 100 / coverage   (extrapolates a partly measured window to the full window)
    # budget_events = allowed_ratio * scaled_window_total
    # share = (impact.total - impact.good) / budget_events * 100, rounded to 1 decimal
```

- With full coverage the share equals the fall in "budget remaining" the dashboard computes from the same rows (AC-6 checks it on the same data).
- Bad events counted once per 5-minute measurement window. Two overlapping incidents each count the overlap (shares are per incident and are not summed; the UI says "Overlapping incidents each count the shared minutes").
- The quarter rule (`class_share`): for one SLO, the **union** of the impact windows of the class's incidents in the class window (no window counted twice), bad events in that union, divided by the budget over the class window computed as above with `window_days = class window`. A class breaches when any one SLO's share exceeds the class threshold.

### 4.4 Services and modules

| Module | Job |
|---|---|
| `entities/error_budget_entities.py` | the three entities |
| `services/error_budget_math.py` | pure maths above |
| `services/incident_budget_impact_service.py` (`IncidentBudgetImpactService`) | reads SLIs, SLOs and measurements; writes impact rows for one incident; `impacts_for_incident(current_user, incident_id)` for the API |
| `services/error_budget_policy_service.py` (`ErrorBudgetPolicyService`) | the policy (get effective, save); `evaluate_application(application_id)` job handler; breach creation, requirement checks, waivers; `finalize_requirement(postmortem)` called by the finalise hook |
| `services/error_budget_policy_notifier.py` | builds and queues the breach messages |
| `dtos/error_budget_dtos.py`, `controllers/error_budget_controller.py` | API |

**Evaluation flow** (`ErrorBudgetPolicyService.evaluate_application(application_id)`):
1. Incidents to evaluate: open incidents of the application, plus incidents resolved within the last `ERROR_BUDGET_POLICY_FINAL_AFTER_HOURS` whose impacts are not all final. For each, `IncidentBudgetImpactService.evaluate(incident)` upserts one row per matched SLO and sets `impact_state` (`provisional` until `resolved_at + FINAL_AFTER_HOURS` has passed, then `final`; `insufficient_data` when the maths says so).
2. If the policy row is missing or disabled: stop (impacts are information only).
3. **Single incident**: for each evaluated incident whose largest `budget_share_percent` exceeds the threshold: create the breach if none exists (`is_provisional` true while any impact is provisional), or update its share, SLO and provisional flag. A breach whose final share falls back below the threshold is deleted (with an audit row `error_budget_breach.withdrawn` by `system:keigan`) only while it is still provisional; a final breach is never withdrawn.
   - On first creation for a **resolved** incident, or when an open incident's breach becomes final after resolution: if `ERROR_BUDGET_POLICY_AUTO_DRAFT_POSTMORTEM` and no postmortem exists, enqueue `generate_postmortem` with `generation_trigger = "error_budget_policy"` and `requested_by_user_principal_name = "system:keigan"` (dedup key `postmortem:{incident_id}`, as the existing callers use); notify (4.6) once (`notified_at`).
   - Requirement check (`_requirement_met(breach)`): a final postmortem exists for the incident **and** an action item of that incident with `action_priority = top`, `action_type = prevent`, status in (`open`, `in_progress`, `blocked`, `done`) exists → `met` with `qualifying_action_item_id`. Otherwise `open` (unless `waived`).
4. **Outage class** (once per local day per application, tracked by the job's dedup key): for each recurrence key with two or more incidents in the class window, compute `class_share` per SLO; above the threshold → open breach if none is open for that key. Met when any action item linked to an incident of the class, created in the class window, has `action_priority = top` and status not `wont_do`/`proposed`. Breaches of a key whose share falls below the threshold stay until met or waived (the rule is about the quarter that already happened).
5. **Budget exhausted**: from `SloService.summarize_slos([application_id])`, each SLO with status `breached` and no open exhausted breach → open one and notify; each open exhausted breach whose SLO is no longer `breached` → `ended`.

**Triggers.**
- New schedule `IntervalSchedule("error_budget_policy", settings.error_budget_policy_evaluation_interval_minutes * 60, enqueue_error_budget_policy)` for live applications with SLOs, dedup key `error_budget_policy:{application_id}`; job type `evaluate_error_budget_policy` → `ErrorBudgetPolicyService.evaluate_application`.
- After an incident becomes resolved (`IncidentService.resolve_incident`, and `_synchronize_existing_incident` when the state moves to resolved or closed): enqueue the same job for its application (same dedup key, so it merges with a queued run).
- After any action-item change on an incident with a breach, and after a postmortem is finalised: `ErrorBudgetPolicyService.refresh_requirement(incident_id)` runs in the same transaction (doc 29's `ActionItemService` calls it through one hook function `on_action_items_changed(incident_id)`), so turning the qualifying item to `wont_do` reopens the requirement at once.

**Finalise gate** (added to doc 29's hook in `CommunicationService.finalize_postmortem`, after its proposed-items check): when the incident has a `single_incident` breach that is not provisional and is `open`, and the accepted items include no `top` `prevent` item, refuse with `422`, field `actionItems`, message "The error budget policy needs at least one accepted top-priority 'prevent' action item (this incident used 34 % of the Checkout availability budget). Add one, or waive the requirement with a reason." A provisional breach does not block; the panel shows a warning.

**Postmortem prompt** (`postmortem_report.md` becomes **version 3**): when the incident has impacts, a trusted section "Error budget impact" lists per SLO `name, share %, window days` (numbers from code); when a breach exists, a trusted section "Error budget policy" says "The team's policy requires at least one action item with priority top and type prevent that addresses the root cause." The system prompt adds: "If an 'Error budget policy' section is present, include at least one prevent item with priority top that addresses the root cause." These sections are Keigan-computed facts, not untrusted text. The model's item is still only proposed (doc 29): a person accepts it.

### 4.5 AI
No new prompt. One prompt version bump (4.4). The policy's guidance text is never sent to a model.

### 4.6 Notifications
- New notification type `error_budget_policy`, added to `NOTIFICATION_TYPE_VALUES` **and** to the stakeholder subscription list (`frontend/src/api/notificationsApi.ts:notificationTypes` and its translations), because it is a broadcast. Recipients: active members subscribed to it by email, plus active `person` members whose role is in `ERROR_BUDGET_POLICY_NOTIFICATION_ROLES` (default `lead`), deduplicated by address.
- Messages (backend strings `types.error_budget_policy_single.*`, `..._class.*`, `..._exhausted.*` in `en.json` and `ja.json`): facts (SLO, share, threshold, window, incident number) and the link (`/incidents/{id}` for single, `/action-items?tab=attention` for class, `/slo` for exhausted). For exhausted budgets the email quotes the team's guidance text (sanitised).
- The incident's Teams chat, when still active, gets the single-incident message as a card through `post_card_if_chat_exists` (reuse of `postmortem_ready` card layout with its own heading key).

### 4.7 API (base `/api`)

| Method | Path | Who | Request | Response |
|---|---|---|---|---|
| GET | `/applications/{applicationId}/error-budget-policy` | reader | | `ErrorBudgetPolicyResponse` |
| PUT | `/applications/{applicationId}/error-budget-policy` | admin | `ErrorBudgetPolicyRequest` | `ErrorBudgetPolicyResponse` |
| GET | `/incidents/{incidentId}/budget-impact` | reader | | `IncidentBudgetImpactResponse` |
| GET | `/error-budget-breaches` | reader (scoped) | `applicationIds`, `statuses` (default `open`), `kinds` | `list[ErrorBudgetBreachDto]` |
| POST | `/error-budget-breaches/{breachId}/waive` | admin | `{reasonText}` | `ErrorBudgetBreachDto` |
| POST | `/error-budget-breaches/{breachId}/action-items` | admin (outage class only) | doc 29 `ActionItemCreateRequest` (priority forced `top`) | `201 ActionItemDto` with `sourceKind = error_budget_policy`, `sourceRecordId = breachId` |

`ErrorBudgetPolicyResponse`: `applicationId, isEnabled, singleIncidentThresholdPercent, outageClassThresholdPercent, outageClassWindowDays` (effective values), `usesDefault {singleIncidentThreshold, outageClassThreshold, outageClassWindow}`, `defaults {...}`, `maximumOutageClassWindowDays` (= `SLI_RAW_RETENTION_DAYS`), `exhaustedBudgetGuidanceText, updatedAt, updatedBy`.
`ErrorBudgetPolicyRequest` (`extra="forbid"`): `isEnabled`, the three numbers (null = default), `exhaustedBudgetGuidanceText`.
`IncidentBudgetImpactResponse`: `incidentId, policy {isEnabled, singleIncidentThresholdPercent}, impacts [{sloId, sliName, targetPercentage, budgetWindowDays, impactWindowStart, impactWindowEnd, badEventCount, budgetEventCount, budgetSharePercent, dataCoveragePercent, isServiceMatched, impactState, evaluatedAt}], breach: ErrorBudgetBreachDto | null`.
`ErrorBudgetBreachDto`: `breachId, applicationId, applicationName, breachKind, incidentId, incidentReference, sloId, sliName, recurrenceCategory, recurrenceServiceName, measuredSharePercent, thresholdPercent, windowDays, detectedAt, requirementStatus, isProvisional, qualifyingActionItemId, waivedBy, waiverReasonText, guidanceText` (exhausted only).

Errors: `404`; `403`; `422` for out-of-range numbers, a class window above SLI retention, guidance too long, a waiver reason below `ERROR_BUDGET_POLICY_WAIVER_MINIMUM_CHARACTERS`, waiving a breach that is not `open`, creating an item for a non-class breach.

Audit: `error_budget_policy.update` (changed fields), `error_budget_breach.waive`, `error_budget_breach.withdrawn` (system).

### 4.8 Settings

| Name | Default | Range | Meaning |
|---|---|---|---|
| `ERROR_BUDGET_POLICY_SINGLE_INCIDENT_THRESHOLD_PERCENT` | 20 | 1–100 | Google's example: one incident using more than this share of an SLO's budget needs a postmortem with a top-priority item |
| `ERROR_BUDGET_POLICY_OUTAGE_CLASS_THRESHOLD_PERCENT` | 20 | 1–100 | Google's example for one class of outage over the class window |
| `ERROR_BUDGET_POLICY_OUTAGE_CLASS_WINDOW_DAYS` | 90 | 7 to `SLI_RAW_RETENTION_DAYS` | "A quarter" |
| `ERROR_BUDGET_POLICY_EVALUATION_INTERVAL_MINUTES` | 60 | 5–1440 | How often impacts and breaches are re-evaluated |
| `ERROR_BUDGET_POLICY_FINAL_AFTER_HOURS` | 24 | 1–168 | Hours after resolution when an impact becomes final |
| `ERROR_BUDGET_POLICY_MINIMUM_DATA_COVERAGE_PERCENT` | 50 | 10–100 | Least share of the budget window that must have measurements |
| `ERROR_BUDGET_POLICY_MINIMUM_WINDOW_EVENTS` | 1000 | 0–1,000,000,000 | Fewest events in the budget window for a share to be stated |
| `ERROR_BUDGET_POLICY_AUTO_DRAFT_POSTMORTEM` | true | | Start a draft when a breach is found on a resolved incident |
| `ERROR_BUDGET_POLICY_WAIVER_MINIMUM_CHARACTERS` | 20 | 5–500 | Shortest waiver reason |
| `ERROR_BUDGET_POLICY_GUIDANCE_MAXIMUM_CHARACTERS` | 2000 | 100–10000 | Longest guidance text |
| `ERROR_BUDGET_POLICY_NOTIFICATION_ROLES` | `lead` | `StakeholderRole` values | Roles told about breaches in addition to subscribers |
| `ERROR_BUDGET_POLICY_BREACH_RETENTION_DAYS` | 730 | 90–3650 | Closed breaches older than this are deleted |

A model validator refuses `OUTAGE_CLASS_WINDOW_DAYS > SLI_RAW_RETENTION_DAYS`; the policy save refuses the same per application. All in `backend/.env.example` and Helm values.

---

## 5. User experience

### 5.1 Policy editor (application workspace, SLO step: `ErrorBudgetPolicySection.tsx` below the SLO list)
- A card "Error budget policy" with a switch "Keigan holds this application to the policy" (admins), the two thresholds as percentage inputs showing "Default 20 %", the class window in days ("at most 90, the SLI history Keigan keeps"), and a textarea "What we do when an SLO's budget is used up" with a placeholder from Google's example ("Pause feature releases except urgent and security fixes until the SLO is met again").
- A live sentence under the form, built from the values: "If one incident uses more than 20 % of an SLO's budget in its 30-day window, Keigan drafts a postmortem and needs a top-priority action item that prevents the cause before the postmortem can be finalised." (per SLO window shown when SLOs differ).
- Readers see the same card read-only. Off state: "Off. Keigan shows budget impact on incidents but holds nobody to it."

### 5.2 Budget impact on the incident (investigation page, Postmortem tab and incident room: `BudgetImpactCard.tsx`)
- One row per SLO: name, a horizontal meter of the share with a marker at the threshold, the figure ("34 % of the 30-day budget"), state chip (Provisional, Final, Not enough data), and an expandable "How this was worked out" with bad events, budget events, window dates, coverage, "Matched by service" or "Application-wide SLO".
- Empty: "No SLO covers the services of this incident." Insufficient: "Not enough measurements in the window (31 % measured, at least 50 % needed)."

### 5.3 Postmortem requirement banner (in `PostmortemSection`)
- Open, final breach: warning banner "Error budget policy: this incident used 34 % of the Checkout availability budget (limit 20 %). Finalising needs at least one accepted top-priority 'prevent' action item." with buttons **Add top-priority item** (opens doc 29's drawer preset: `top`, `prevent`) and **Waive** (admin; dialog with reason, shows the minimum length).
- Provisional: info banner "Provisional: … The figure becomes final 24 hours after resolution."
- Met: success line "Policy met by: <item title>". Waived: neutral line "Waived by <name>: <reason>".

### 5.4 Elsewhere
- SLO monitoring page: an SLO card with an open `budget_exhausted` breach shows a banner "Budget used up. Your team agreed: <guidance>" (or "No agreed response written yet" with a link to the policy for admins).
- Action items page, Needs attention (doc 29): kind `policy_breach_open` cards per open breach, with "Add top-priority item" for class breaches.
- Weekly review (doc 31): breaches section.

### 5.5 States, keyboard, phone, locales
- Loading skeletons; `ErrorState` with retry; errors from the API shown with their `detail`.
- The meter has `role="meter"` with `aria-valuenow`, `aria-valuemax` and a text label; the threshold is stated in text, not only by the marker.
- Phone: the impact table becomes stacked rows; banners wrap; buttons 44 px.
- New namespace `errorBudgetPolicy` in the six locales (es-MX falls back): groups `policy`, `impact`, `state.*`, `breach.kind.*`, `breach.status.*`, `banner`, `waive`, `errors`. Additions in `notifications.json` (the new subscription type and its help) and `actionItems.json` (`attention.policy_breach_open`).

---

## 6. Safety, access and privacy
- Read policy, impacts and breaches: application readers. Change policy, waive, create class items: application admins. Lists are scoped with `scoped_application_ids`.
- No customer-system action exists in this feature (anti-goal table). The only automatic actions are a postmortem draft job, notification rows and breach rows.
- Stored: counts and percentages, snapshots of names, the guidance and waiver texts (masked with `PiiMasker`, sanitised with `sanitize_ai_markdown`/`sanitize_ai_line`). No telemetry content.
- Audit rows for every policy change and waiver. Retention per 4.2.

---

## 7. Acceptance criteria

| # | Criterion | Test type |
|---|---|---|
| AC-1 | With no policy row, impacts are computed and no breach, draft or message is created; reading the policy writes no row | integration |
| AC-2 | `budget_share` on constructed totals gives the expected share; a 100 % target and zero events give insufficient data | unit |
| AC-3 | The impact window starts at the earliest of opened, detected and first linked alert, ends at resolution or now, on the 5-minute grid | unit |
| AC-4 | Coverage below the minimum or fewer events than the minimum gives `insufficient_data` and no breach | unit and integration |
| AC-5 | An impact is provisional while open and until the configured hours after resolution, then final and no longer recomputed | integration (frozen clock) |
| AC-6 | With full coverage, the share equals the fall in `errorBudgetRemainingPercentage` from `SloService._summaries` over the same window | integration |
| AC-7 | The quarter rule counts overlapping impact windows once | unit |
| AC-8 | SLO matching follows C2-D4 (affected service, application-level SLI, incident without services; supporting signals excluded) | integration |
| AC-9 | A breach on a resolved incident drafts a postmortem with trigger `error_budget_policy` once, and notifies once | integration |
| AC-10 | Finalising is refused while a final open breach has no accepted `top` `prevent` item; a proposed or `wont_do` item does not count; after accepting one, finalising succeeds and the breach is `met` | integration (controller) |
| AC-11 | Turning the qualifying item to `wont_do` reopens the requirement immediately | integration |
| AC-12 | A provisional breach does not block finalising; the banner says provisional | integration and browser |
| AC-13 | A waiver needs an admin and a reason of minimum length, sets `waived`, writes an audit row, and the gate lets finalising pass | integration |
| AC-14 | A class over the class threshold opens one breach per key; it is met by a `top` item on any incident of the class created in the window | integration |
| AC-15 | `budget_exhausted` opens when the SLO is `breached` and ends when it is not; no other system is called (the test runs with every integration in a mode that fails on any outbound call) | integration |
| AC-16 | Deleting an SLO keeps impacts and breaches with null `slo_id` and their snapshots | integration |
| AC-17 | Every endpoint refuses a reader for changes (403) and hides other applications | integration (controller) |
| AC-18 | Settings validated (class window ≤ SLI retention) and documented in `.env.example` and Helm | unit |
| AC-19 | Schema drift and status-value tests pass with the new tables, filtered indexes and the replaced action-item source constraint | integration |
| AC-20 | The postmortem prompt v3 receives the impact and policy sections only when they apply; the mock factory then proposes a `top` `prevent` item | integration (mock gateway) |
| AC-21 | Policy editor, impact card, banners and waiver work at 1440 and 390 px, light and dark, keyboard only | browser script |

---

## 8. Test plan
- `backend/tests/unit/services/test_error_budget_math.py` (AC-2, 3, 4, 7).
- `backend/tests/integration/services/test_incident_budget_impact_service.py` (AC-5, 6, 8, 16).
- `backend/tests/integration/services/test_error_budget_policy_service.py` (AC-1, 9, 11, 13, 14, 15).
- `backend/tests/integration/services/test_communication_service.py` additions (AC-10, 12, 20).
- `backend/tests/integration/controllers/test_error_budget_controller.py` (AC-10, 13, 17).
- `backend/tests/unit/config/test_error_budget_settings.py` and the deployment settings test (AC-18).
- Schema drift, status values and constraint tests (AC-19); SLI measurements built with the existing test helpers in `backend/tests/support/`.
- Frontend: `frontend/src/features/slo/budgetImpactPresentation.test.ts` (share text, state text); typecheck, locales, contrast, build.
- Browser script `frontend/scripts/check-error-budget-policy.mjs`: enable the policy on the demo application, open the seeded breached incident, see the banner, try to finalise (refused), add a top prevent item, finalise; waive on another; 390 px; light and dark (AC-21).

---

## 9. Phased build plan

| Step | Task | Size | Depends on | Demonstrable |
|---|---|---|---|---|
| 1 | Enums, entities, Alembic revision (incl. replaced source constraint), Azure SQL, settings; `error_budget_math.py` with unit tests | M | doc 29 step 1 | drift green; maths tested |
| 2 | `IncidentBudgetImpactService`, schedule and resolve triggers, `GET /incidents/{id}/budget-impact`, `BudgetImpactCard` | M | 1 | impact visible on demo incidents (information only) |
| 3 | Policy row, editor, breaches (single, class, exhausted), notifier, auto-draft | M | 2, doc 29 step 2 | turning the policy on raises breaches and drafts |
| 4 | Finalise gate, requirement refresh hook, waiver, banners, prompt v3 | S | 3, doc 29 step 3 | the full loop in the browser |
| 5 | Needs-attention kind, SLO page banner, class-breach item creation, demo seed, browser script, docs | S | 4, doc 29 step 5 | demo shows a met, an open and a waived breach |

Build after doc 29 steps 1–3 and 5. Doc 31 reads impacts and breaches after step 3.

---

## 10. Docs, migration and demo-data impact
- Docs: 03 (three tables, enums), 15 (regenerate), 05 (endpoints), 01 (policy, impact, gate), 12 (row), 13 (sequence: resolve → evaluate → breach → draft → finalise gate), 06 (postmortem prompt v3), 02 (schedule), 09 (the ignored `burn_rate_policy_json`, the literals in `_summaries`).
- Azure SQL: regenerate the four DDL files and the delta `<revision>_error_budget_policy.sql`; README counts (62 tables) and check query.
- Demo seed (after the SLO and investigation seeds): enable the policy for Claims (CLMJP) with default thresholds and a guidance text; run `IncidentBudgetImpactService.evaluate` for every seeded incident (no hand-written numbers). The seed test asserts the impacts exist. If at least one seeded incident crosses 20 %, its breach is left open on the most recent incident, met on another (accept its `top` prevent item from doc 29's seed) and waived on a third if there is one. **If no seeded incident crosses 20 %** with the simulated data, the builder must not lower thresholds or invent counts: instead, make one historical simulation scenario's error burst large enough (in `integrations/simulation/simulation_scenarios.py`, as realistic data) and record the change in doc 09. Add the three tables to `demo_data_plan.py` and regenerate `database/azure_sql/demo_data/`.

---

## 11. Risks, mitigations and open questions

### 11.1 Risks
| Risk | Mitigation |
|---|---|
| SLIs that do not reflect user pain make shares meaningless | Policy off by default; shares shown with inputs; waivers |
| Slow detection hides budget use before the first alert | Documented: Keigan counts from the first signal it has; earlier bad events are still in the SLO page's remaining budget |
| Incidents without affected services blame every SLO | `is_service_matched = false` shown as "Application-wide"; the gate uses the largest share, which the team can waive |
| Teams disable the policy when it bites | Policy changes are audited and shown in the weekly review (doc 31) |

### 11.2 Open questions for the owner
1. **Default off**: decided off per application (the team must agree first). Should Tier 1 applications start with it on?
2. **Who may waive**: decided application admins. Should waivers on Tier 1 applications need a Keigan admin (closer to Google's escalation to the CTO)?
3. **Per-tier or per-SLO thresholds**: v1 has one policy per application. Needed?
4. **Release freeze**: Keigan only shows the agreed response. Should a later wave tell ServiceNow change management (D1) when a budget is exhausted?
