# 29 — Action items: post-incident follow-ups tracked to done

Roadmap item **C1** (doc 21, product research, section 3.5, wave C "Close the loop"). Written 2026-11-22 against branch `keigan-ui-ux`.

---

## 1. Purpose, status and how to use this document

**Purpose.** Turn the action items a postmortem lists into tracked tasks: each has an owner, a due date, a priority and a status; owners get reminders through the existing notification outbox; the team sees what is overdue, what is missing (major incidents without a finished postmortem), and which incidents came back while their follow-ups were still open or after they were done. The design leaves a seam for a ServiceNow sync (roadmap D1) without building it.

**Status.** Design, written 2026-11-22; not built.

**This is the first of four specs that share one data model.** Build them in this order; each later one needs the earlier:

| Doc | Roadmap | What it adds to the shared model | Needs from earlier |
|---|---|---|---|
| **29 (this)** | C1 Action items | `action_item` table, the action-item service, reminders, the Action items page | nothing (A4 metrics exist) |
| 30 | C2 Error-budget policy | per-incident budget impact, policy breaches; requires a top-priority `prevent` action item before a postmortem is finalised | `action_item` with `action_priority = top` and `action_type = prevent`; the finalise hook added here; the "Needs attention" view |
| 31 | C3 Weekly health review | the weekly review page and digest, "mark as reviewed" | open, overdue and completed action items (section 4.4 overview service); breaches from doc 30 |
| 32 | C4 Runbook health | runbook match records and feedback | `action_item` source `runbook_review`; the weekly review section from doc 31 |

**How to use it.** Owner: read sections 2, 4.1 and 11. Builder: follow section 9 in order; every acceptance criterion in section 7 has a test in section 8. Every claim about existing code below was checked in the source on 2026-11-22 and carries a `path:symbol` reference.

**Glossary.**

| Term | Meaning |
|---|---|
| Action item | One follow-up task after an incident (or from a policy, a weekly review or a runbook review): title, type, priority, owner, due date, status |
| Proposed item | An item the AI suggested in a postmortem draft that no person has accepted yet. It is not tracked, reminded or counted |
| Owner | One team member (a `stakeholder` row of type `person`) chosen by a person. The AI only suggests an owner *role* in words |
| Overdue | Not `done` or `wont_do`, and the due date has passed in the application's own time zone |
| Repeat | A later incident with the same recurrence key (category and primary service) as an earlier one in the repeat window |

---

## 2. Goals, non-goals, anti-goals

### 2.1 Goals
1. **G1. Follow-ups are records, not text.** Each action item in a postmortem is a row with an owner, due date, priority, type and status, editable after the postmortem is final.
2. **G2. People accept what the AI proposes.** AI suggestions arrive as *proposed* items; a person accepts, edits or discards each before the postmortem can be finalised.
3. **G3. Nothing rots silently.** Owners get a reminder before the due date and while overdue; unowned and long-overdue items reach the team leads.
4. **G4. One view of what needs attention**: overdue items, top-priority items with no owner, major incidents with no final postmortem after the grace period (and, from doc 30, policy breaches).
5. **G5. Learn what repeats.** For incidents that recur, show whether the earlier incidents' `prevent` items were still open (follow-through problem) or already done (the fix may not have worked).
6. **G6. Numbers that prove the loop works**: completion rate, median time to complete, share done on time, per application.

### 2.2 Non-goals (v1)
- **No ServiceNow write.** The seam is designed (section 4.7); writing tasks to ServiceNow is roadmap D1. v1 only stores a ServiceNow task number a person types in.
- No Jira, Azure Boards or Linear integration.
- No sub-tasks, comments thread, attachments or watchers. One completion note and one reason field.
- No Teams reminders. Reminders are email (the incident's Teams chat is closed by then, and a Teams channel is the wrong place for a personal reminder).
- No per-person notification preferences or quiet hours (the `quiet_hours_json` column exists on `stakeholder` but nothing reads it; using it is roadmap idea 30, not this).
- No automatic closing of items from telemetry ("the error rate is fine now, so the item is done").

### 2.3 Anti-goals (what would make this harmful) and their controls
| Anti-goal | Control | AC |
|---|---|---|
| The AI assigns blame or names a person | The AI fills only `suggested_owner_role_text` (words like "Claims platform team"); only a person sets `owner_stakeholder_id`. The postmortem document shows the owner's *role*, never the person (blameless), while the tracker shows the person (accountable) | AC-3, AC-12 |
| AI suggestions become commitments nobody agreed to | Proposed items are not tracked, reminded or counted; finalising is refused while any remain | AC-2, AC-4 |
| Reminder spam | One email per owner per application per day, listing all their due items; a reminder per item at most every `ACTION_ITEMS_OVERDUE_REMINDER_INTERVAL_DAYS`; a job deduplication key per application and local day | AC-14, AC-15 |
| Work quietly dropped | Tracked items are never deleted, only closed as `wont_do` with a reason by an application admin; due-date moves are counted and shown | AC-7, AC-9, AC-10 |
| A dashboard that shames people | The overview shows counts per application and per role, not a ranking of people; overdue lists show the owner because the owner needs to act, not as a league table | AC-19 |

---

## 3. Current state (verified) and unknowns

### 3.1 What exists

| Topic | Fact | Evidence |
|---|---|---|
| Action items in postmortems | The postmortem model returns `action_items: list[PostmortemActionItem]` with `description`, `owner_role` (free text), `due_in_days` (default 14) and `action_type` (`prevent`, `detect`, `mitigate`). **There is no entity**: `PostmortemActionItem` is a pydantic output schema only. | `backend/keigan/ai/investigation_ai_schemas.py:PostmortemActionItem`, `PostmortemResult` |
| Where they are kept | Only inside `postmortem_report.report_sections_json` (the whole model output) and as a Markdown table in `report_markdown`, rendered once with the due date `resolved_at + due_in_days`. | `backend/keigan/services/communication_service.py:CommunicationService._write_postmortem`, `render_postmortem_markdown` |
| Editing | `update_postmortem` edits only `report_title` and `report_markdown` (masked, sanitised). After an edit `report_sections_json.action_items` no longer matches what the document says. | `communication_service.py:CommunicationService.update_postmortem` |
| Lifecycle | `generating → draft → final` (or `failed`); only an application admin generates, edits, finalises and sends; a final postmortem can no longer be regenerated or edited. | `communication_service.py:start_postmortem`, `finalize_postmortem`, `send_postmortem`; `backend/keigan/entities/status_values.py:PostmortemStatus` |
| Triggers | The "Resolve" dialog (`ResolveIncidentRequest.generate_postmortem`), the postmortem tab's button, and "Keigan, this is finished" in the incident's Teams chat (`generation_trigger = "teams_phrase"`). | `backend/keigan/services/incident_service.py:IncidentService.resolve_incident`; `teams_chat_service.py` (enqueue of `generate_postmortem`) |
| Prompt | `postmortem_report.md` v1 asks for specific, verifiable items "owned by a role or team", at most **eight** (a number written in the prompt, not a setting). | `backend/keigan/resources/prompts/postmortem_report.md` |
| Blameless masking | Person names from the Teams chat and timeline are replaced with placeholders before the model sees them (V12). | `communication_service.py:_write_postmortem` (`mask_known_names`) |
| Screen | `PostmortemSection` shows the Markdown with edit, regenerate, finalise, send, download and print. No structured action items. | `frontend/src/features/investigations/components/PostmortemSection.tsx` |
| Team | `stakeholder` rows: `recipient_type` (`person`, `teams_channel`, `distribution_list`), `stakeholder_role` (ten roles incl. `lead`, `manager`), `email_address`, `user_principal_name`, `preferred_language_code`, `is_active`. | `backend/keigan/entities/notification_entities.py:Stakeholder`; `status_values.py:StakeholderRole` |
| Outbox | `NotificationService.queue_email` adds a `notification_delivery` row and a `deliver_notification` job; deduplication exists only per incident. Email bodies are rendered from `resources/i18n/{en,ja}.json` (**only English and Japanese**; other languages fall back to English). | `backend/keigan/services/notification_service.py:queue_email`, `deliver`; `backend/keigan/utils/string_table.py:SUPPORTED_LANGUAGE_CODES` |
| Personal vs subscribed mail | Broadcast types are opt-in per stakeholder (`subscribed_notification_types_json`); the allowed list is `NOTIFICATION_TYPE_VALUES`. | `backend/keigan/dtos/notification_dtos.py:NOTIFICATION_TYPE_VALUES`; `notification_service.py:matching_stakeholders` |
| Scheduling | An in-process scheduler enqueues jobs on intervals; the weekly report checks weekday and hour in **UTC**. Job types map to service methods. | `backend/keigan/workers/schedulers.py:build_schedules`, `enqueue_weekly_reports`; `backend/keigan/workers/job_handlers.py:JOB_HANDLER_REFERENCES` |
| Repeats today | The `recurring_incident` detector groups incidents of the last **30 days** (a literal) by `(incident_category, first affected service)` and raises a predictive signal at two or more. Nothing links repeats to follow-ups. | `backend/keigan/services/intelligence_detectors.py:PredictiveDetectors.recurring_incidents` |
| Retention | Finished incidents older than `INCIDENT_RETENTION_DAYS` (395) are deleted with their postmortems by bulk statements. | `backend/keigan/services/incident_retention.py:_delete_incident_batch` |
| ServiceNow | The client can list, create and update **incidents** only (Table API or the simulator). | `backend/keigan/integrations/servicenow_client.py:ServiceNowClient` |
| Access | Readers read; application admins change. `ensure_application_reader`, `ensure_application_admin`. | `backend/keigan/services/authorization_service.py` |
| Application time zone | `application.time_zone_name` (default `UTC`). | `backend/keigan/entities/application_entities.py:Application` |

### 3.2 What the research document got wrong or left out
- Doc 21 section 3.2 says "Postmortems list action items with owner role, due date and type (`PostmortemActionItem`)". The name is a pydantic schema, not a table: nothing can be tracked, queried or reminded today, and the stored JSON goes stale when the Markdown is edited.
- Doc 21 lists "ServiceNow sync" in C1. Writing to ServiceNow is D1; this spec stores a typed-in reference only and designs the seam.

### 3.3 Unknowns
1. Which ServiceNow table the organisation uses for post-incident tasks (`problem_task` under a Problem, a Post-Incident Review task, or a custom table). Needed for D1, not for v1 (open question 2).
2. Whether team members reliably have `user_principal_name` set (needed so an owner who is only a reader can update their own item). Members added before doc 20 may have an email only; the match uses both (section 6.1).

---

## 4. Design

### 4.1 Decisions (made while the owner was away, revisit if wrong)

| # | Decision | Reason | Rejected alternative |
|---|---|---|---|
| C1-D1 | **Rows, created as `proposed` when a draft is written**; a person accepts, edits or discards each; finalising is refused while any are proposed | People own the commitment; the AI draft still saves typing | Creating items only at finalisation (the person would edit a table in Markdown first, then again as rows) |
| C1-D2 | **The rows are the truth; the Markdown table is rendered from them** when a draft is written and again at finalisation | Ends the "edited Markdown, stale JSON" split found in 3.1 | Parsing the edited Markdown table back into rows (fragile, lossy) |
| C1-D3 | **Owner is a team member (`stakeholder` person), set by a person**; the AI's owner text stays as a suggestion | Decision D2 of doc 23 (no people named by AI); blameless postmortem, accountable tracker | Free-text owner (cannot be reminded); owner by email address (duplicates the team list) |
| C1-D4 | **Every tracked item has a due date** | Items without dates are where follow-ups rot (incident.io's policy views are built on due dates) | Optional due dates |
| C1-D5 | **Tracked items are never deleted**; they close as `done` or `wont_do` (reason required, admin only). Only `proposed` items can be discarded (deleted) | Audit and honest completion rates | Delete with audit row only |
| C1-D6 | **The owner may update their own item** (status among open, in progress, blocked, done; notes) with reader access; reassigning, re-dating, re-prioritising and `wont_do` need an application admin | The person doing the work closes it; dropping or moving work is a team decision | Admin-only changes (owners would have to ask an admin to tick a box) |
| C1-D7 | **Priority words, not P-numbers**: `top`, `high`, `normal`, `low` | Incident priorities are already `P1`–`P4`; "P0" for tasks next to "P1" incidents confuses. `top` is Google's P0 ("drop everything") and what doc 30 requires | `p0`–`p3` |
| C1-D8 | **Reminders are personal email, sent regardless of subscriptions**, one digest per owner per application per local day; escalation to leads and managers | You were assigned the work; opt-in would mean nobody gets reminders (no existing stakeholder subscribes to a new type) | A new opt-in notification type |
| C1-D9 | **Due dates and "overdue" use the application's time zone** | A Tokyo team's "due 1 December" ends at midnight Tokyo time | UTC dates |
| C1-D10 | **Repeats reuse the detector's recurrence key**, extracted into one function both use; the window is a setting (default 90 days) | One definition of "the same kind of incident"; follow-ups take longer than the detector's 30 days | A new similarity measure (that is B1, similar-incident memory) |
| C1-D11 | **ServiceNow: a typed-in reference in v1, a port for D1** | Teams already track in ServiceNow; a link is useful today; writing needs D1's access decision | Building a one-way sync now |
| C1-D12 | **Action items outlive their incident**: incident retention clears the incident and postmortem links but keeps the item and a snapshot of the incident number; closed items are purged after `ACTION_ITEMS_CLOSED_RETENTION_DAYS` | An open follow-up must not vanish because the incident aged out | Cascade delete with the incident |

### 4.2 Data model

**New enums** in `backend/keigan/entities/status_values.py` (each builds its CHECK constraint through `values_check`):

```python
class ActionItemStatus(StrEnum):
    PROPOSED = "proposed"      # suggested by the AI in a draft; not tracked until accepted
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    WONT_DO = "wont_do"

class ActionItemType(StrEnum):      # same three words as PostmortemActionItem.action_type
    PREVENT = "prevent"
    DETECT = "detect"
    MITIGATE = "mitigate"

class ActionItemPriority(StrEnum):
    TOP = "top"                # Google's P0: "drop everything"; required by doc 30
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"

class ActionItemSource(StrEnum):    # docs 30, 31 and 32 each add one value with their own revision
    POSTMORTEM = "postmortem"
    MANUAL = "manual"
```

`ActionItemSource` lists only what C1's code writes (rule at the top of `status_values.py`). Doc 30 adds `error_budget_policy`, doc 31 `weekly_review`, doc 32 `runbook_review`, each in its own revision that replaces the constraint.

**New table `action_item`** (entity `ActionItem` in a new module `backend/keigan/entities/action_item_entities.py`, registered in `entities/all_entities.py`; `AuditColumnsMixin` gives `created_at`, `updated_at`, `created_by_user_principal_name`, `updated_by_user_principal_name`):

| Column | Type | Rule |
|---|---|---|
| `action_item_id` | String(36) PK | `identifier_column()` |
| `application_id` | FK `application` ON DELETE CASCADE, not null | the one cascade path |
| `incident_id` | FK `incident` NO ACTION, nullable | SQL Server allows one cascade path; released by incident retention (4.6) |
| `postmortem_id` | FK `postmortem_report` NO ACTION, nullable | same |
| `incident_reference_text` | String(60), nullable | snapshot of the incident number (or the first 8 characters of its id) when linked; shown after the incident expires |
| `source_kind` | String(30), `values_check(ActionItemSource)`, not null | |
| `source_record_id` | String(36), nullable | the record the item came from when that is not the incident (a breach, a weekly review, a runbook). A recorded fact without FK, like `audit_event.target_entity_id` |
| `item_title` | String(300), not null | masked, `sanitize_ai_line` |
| `item_details_markdown` | Text, nullable | masked, `sanitize_ai_markdown`; at most `ACTION_ITEMS_DETAILS_MAXIMUM_CHARACTERS` |
| `action_type` | String(10), `values_check(ActionItemType)`, not null | |
| `action_priority` | String(10), `values_check(ActionItemPriority)`, not null, default `normal` | |
| `item_status` | String(20), `values_check(ActionItemStatus)`, not null | |
| `suggested_owner_role_text` | String(200), nullable | the AI's owner words; never a person; sanitised |
| `owner_stakeholder_id` | FK `stakeholder` NO ACTION, nullable | must be an active `person` of the same application |
| `due_on` | Date, nullable for `proposed`, required otherwise (service rule) | a calendar date in the application's time zone |
| `original_due_on` | Date, nullable | the due date when the item was accepted or created; never changed afterwards |
| `due_on_change_count` | Integer, default 0 | incremented by every due-date change after acceptance |
| `status_reason_text` | String(1000), nullable | required for `blocked` and `wont_do`; masked |
| `completion_note_text` | String(2000), nullable | optional for `done`; masked |
| `completed_at` | DateTime, nullable | set on `done` and `wont_do`, cleared on reopen |
| `completed_by_user_principal_name` | String(320), nullable | |
| `accepted_at` | DateTime, nullable | when the item stopped being `proposed` (or was created as tracked) |
| `accepted_by_user_principal_name` | String(320), nullable | |
| `external_reference_text` | String(60), nullable | a ServiceNow task number typed by a person; pattern `ACTION_ITEMS_EXTERNAL_REFERENCE_PATTERN` |
| `last_reminded_at` | DateTime, nullable | |
| `reminder_count` | Integer, default 0 | |
| `display_order` | Integer, default 0 | order inside one postmortem |

Constraints and indexes:
- `ck_action_item_item_status_values`, `ck_action_item_action_type_values`, `ck_action_item_action_priority_values`, `ck_action_item_source_kind_values` (from `values_check`).
- `ix_action_item_application_id_item_status_due_on` (application_id, item_status, due_on): the overview and reminder queries.
- `ix_action_item_owner_stakeholder_id`, `ix_action_item_incident_id`, `ix_action_item_postmortem_id`.
- No unique constraint on title: two items may read the same.

Reference release: `owner_stakeholder_id` is a new NO ACTION key on `stakeholder`. `StakeholderService.delete_stakeholder` (`backend/keigan/services/stakeholder_service.py`) must call `release_references(self.session, Stakeholder.stakeholder_id, [stakeholder_id])` before deleting (the column is nullable, so the item stays, unassigned). The application delete path in `application_service.py` (which already releases service references) must also release the application's stakeholder ids. `release_references` walks the metadata, so no list needs maintaining.

**Pydantic schema change** (`backend/keigan/ai/investigation_ai_schemas.py:PostmortemActionItem`): add `priority: Literal["top", "high", "normal", "low"] = "normal"` and a description on `owner_role` ("a role or team, never a person's name"). The mock factory in `investigation_mock_responses.py` gives one item per scenario `priority="top"` and type `prevent`, so the demo and doc 30 have a qualifying item.

**Alembic revision** `<new id>_action_items` on top of the head at build time (today `b8d4f2a6c0e3`): `create_table("action_item")` with the constraints rendered from the entity metadata (as `20261120_d2a6b0c5e8f9_status_check_constraints.py` does). No data backfill: existing postmortems' `report_sections_json.action_items` are not converted (they were never agreed by anyone; section 10 says how the demo gets rows). Then regenerate the Azure SQL scripts (section 10). Tables 58 → 59.

**Retention.** Open items never expire. Items `done` or `wont_do` whose `completed_at` is older than `ACTION_ITEMS_CLOSED_RETENTION_DAYS` are deleted by `AdministrationService.run_retention_cleanup` (`removed["actionItems"]`). Audit rows (`audit_event`) keep their own 400 days.

### 4.3 Rules (pure, unit-tested)

Module `backend/keigan/services/action_item_rules.py` (no database):

**Status transitions** (`ALLOWED_TRANSITIONS`, `can_transition(actor, from, to)`):

| From → To | Admin | Owner |
|---|---|---|
| `proposed` → `open` (accept) | yes | no |
| `proposed` → deleted (discard) | yes | no |
| `open` ↔ `in_progress`, `open`/`in_progress` → `blocked`, `blocked` → `open`/`in_progress` | yes | yes |
| `open`/`in_progress`/`blocked` → `done` | yes | yes |
| `open`/`in_progress`/`blocked` → `wont_do` | yes | no |
| `done`/`wont_do` → `open` (reopen) | yes | no |

`blocked` and `wont_do` need `status_reason_text` (at least `ACTION_ITEMS_REASON_MINIMUM_CHARACTERS`). `done` and `wont_do` set `completed_at` and `completed_by_user_principal_name`; reopen clears both.

**Dates.**
- `local_today(time_zone_name, now)`: today's date in the application's zone (`zoneinfo.ZoneInfo`; an unknown zone name falls back to UTC and logs once).
- `is_overdue(item, today)`: status in (`open`, `in_progress`, `blocked`) and `due_on < today`.
- `days_overdue(item, today)`.
- `proposed_due_on(base_moment, due_in_days, time_zone_name)`: the local date of `base_moment + clamp(due_in_days, 1, ACTION_ITEMS_MAXIMUM_DUE_DAYS)`; `base_moment` is the incident's `resolved_at` or now.
- On create, accept or change, `due_on` must be on or after `local_today` and at most `ACTION_ITEMS_MAXIMUM_DUE_DAYS` ahead; accepting a proposed item whose AI date is already past is refused with a message asking for a new date.

**Reminders** (`reminder_kind(item, today, last_reminded_on)` returns `None`, `due_soon`, `overdue` or `escalate`):
- `due_soon` when `due_on - today == ACTION_ITEMS_REMINDER_DAYS_BEFORE_DUE` and not yet reminded today.
- `overdue` on the first overdue day, then again when `today - last_reminded_on >= ACTION_ITEMS_OVERDUE_REMINDER_INTERVAL_DAYS`.
- `escalate` instead of `overdue` when `days_overdue >= ACTION_ITEMS_ESCALATE_AFTER_OVERDUE_DAYS` and priority is `top` or `high`.
- Only `open`, `in_progress` and `blocked` items; never `proposed`.

**Completion figures** (`completion_summary(items, window, today)`): items accepted in the window; `done_count`, `wont_do_count`, `open_count`, `overdue_count`, `completion_rate = done / (accepted − wont_do)` (null when the denominator is 0), median days from `accepted_at` to `completed_at` (reuse `reliability_metrics.summarize_durations`), `on_time_share` = done with `completed_at` local date ≤ `original_due_on` over done. Every figure carries its sample size, as on the metrics page.

### 4.4 Services and modules (one job each)

| Module | Job |
|---|---|
| `entities/action_item_entities.py` | `ActionItem` |
| `services/action_item_rules.py` | pure rules above |
| `services/action_item_service.py` (`ActionItemService`) | create, read, update, accept, discard, change status; access checks; audit rows; called by the postmortem code |
| `services/postmortem_action_items.py` | `replace_proposed_items(postmortem, incident, result_items)`; `render_action_items_table(rows, language)`; `replace_action_items_section(markdown, table)` (replaces the text between `## Action items` and the next `## ` heading, or appends the section) |
| `services/action_item_reminders.py` (`ActionItemReminderService`) | job handler `send_due_reminders(application_id)` |
| `services/action_item_overview_service.py` (`ActionItemOverviewService`) | the overview: completion figures, "needs attention" list, repeats; used by the page and by doc 31 |
| `services/incident_recurrence.py` | `recurrence_key(incident) -> tuple[str, str]` = (`incident_category` or `"unclassified"`, first affected service id or `""`). `PredictiveDetectors.recurring_incidents` is changed to call it (same behaviour, its 30-day window untouched) |
| `dtos/action_item_dtos.py` | request and response shapes |
| `controllers/action_item_controller.py` | endpoints (4.5) |

**Postmortem integration** (changes in `communication_service.py`):
1. `_write_postmortem`, after a successful model call: `PostmortemActionItems.replace_proposed_items` deletes the postmortem's existing `proposed` rows (accepted ones stay), inserts one `proposed` row per model item (at most `ACTION_ITEMS_MAXIMUM_PER_POSTMORTEM`, in model order), with `source_kind = postmortem`, `incident_id`, `postmortem_id`, `incident_reference_text`, `item_title = sanitize_ai_line(description, 300)`, `suggested_owner_role_text = sanitize_ai_line(owner_role, 200)`, `action_type`, `action_priority`, `due_on = proposed_due_on(...)`. `render_postmortem_markdown` takes the rows (accepted and proposed) for its table instead of `result.action_items`.
2. `finalize_postmortem`: refuse with `BusinessValidationException` (`422`, field `actionItems`, message "Accept or discard the 3 suggested action items before finalising.") while the postmortem has `proposed` items. Then replace the Markdown's action-items section with the table rendered from the accepted rows (columns Action, Owner role, Due, Type, Priority; the owner column shows the owner's team role label, or the suggested role text when nobody is assigned; never the person's name). Doc 30 adds its policy check at this same point.
3. `prompt_library`: `postmortem_report.md` becomes **version 2**: the maximum ("at most eight") becomes the variable `{{ maximum_action_items }}` filled from `ACTION_ITEMS_MAXIMUM_PER_POSTMORTEM`; adds "give each item a priority: top only for an item that must be done before anything else because it addresses the root cause of a serious incident; most items are normal"; adds "owner_role is a role or team, never a person's name". Inputs, masking and the untrusted sections are unchanged. Prompt safety: the output is already passed through `sanitize_ai_model`; titles additionally go through `sanitize_ai_line`.

**Reminder job.** New schedule in `workers/schedulers.py`: `IntervalSchedule("action_item_reminders", 3600, enqueue_action_item_reminders)`. For each live application whose local hour equals `ACTION_ITEMS_REMINDER_HOUR_LOCAL`, enqueue `send_action_item_reminders` with deduplication key `action_item_reminders:{application_id}:{local date}` (a second worker or a second check in the same hour does nothing). Register `"send_action_item_reminders": JobHandlerReference("keigan.services.action_item_reminders", "ActionItemReminderService", "send_due_reminders")` in `job_handlers.py`.

`send_due_reminders(application_id)`:
1. Skip when `ACTION_ITEMS_REMINDERS_ENABLED` is false.
2. Load tracked items of the application; compute `reminder_kind` for each.
3. Group `due_soon` and `overdue` items by owner. Owner must be an active `person` with an email address or user principal name; otherwise the item joins the "unowned" group.
4. One email per owner: notification type `action_item_reminder`, language from the owner's `preferred_language_code`, body = a list built by code (title, incident reference, due date, days overdue, link `/action-items?owner=me`). Rendered with `NotificationRenderer.render_email`; queued with `queue_email(application_id, "action_item_reminder", address, rendered)`.
5. Unowned items and `escalate` items: one email per recipient to active `person` members whose role is in `ACTION_ITEMS_ESCALATION_ROLES` (default `lead,manager`), notification type `action_item_escalation`, listing those items.
6. Set `last_reminded_at = now`, `reminder_count += 1` on every item included. Return `{"owners": n, "escalations": m, "items": k}`.

Both types are added to `NOTIFICATION_TYPE_VALUES` (so the outbox and administration pages label them) but are **not** used for subscription routing (C1-D8); the stakeholder form does not offer them (the frontend `notificationTypes` list in `frontend/src/api/notificationsApi.ts` stays as it is). Backend strings `types.action_item_reminder.*`, `types.action_item_escalation.*`, `labels.due`, `labels.days_overdue`, `labels.owner_role` go into `resources/i18n/en.json` and `ja.json`.

**Overview** (`ActionItemOverviewService.overview(current_user, application_ids, days)`):
- `completion`: `completion_summary` over items accepted in the last `days` (default 90, at most `ACTION_ITEMS_OVERVIEW_MAXIMUM_DAYS`).
- `needs_attention`: a list of typed entries, each `{kind, applicationId, recordKind, recordId, title, parameters}`:
  - `overdue_item` (parameters: daysOverdue, priority);
  - `top_priority_unowned`;
  - `postmortem_missing`: an incident whose `keigan_priority` is in `ACTION_ITEMS_POSTMORTEM_REQUIRED_PRIORITIES`, resolved more than `ACTION_ITEMS_POSTMORTEM_GRACE_DAYS` ago, within the overview window, with no `final` postmortem;
  - `proposed_waiting`: a draft postmortem with proposed items older than the grace days;
  - (doc 30 adds `policy_breach_open`).
  Sorted: overdue top first, then by days overdue.
- `repeats`: for readable incidents opened in the last `ACTION_ITEMS_REPEAT_WINDOW_DAYS`, grouped by `recurrence_key`, groups of two or more, the key's service id not empty. For each incident after the first, an outcome computed from the action items of the earlier incidents in the group, as they stood at the later incident's `opened_at`:
  - `no_postmortem`: none of the earlier incidents has a final postmortem;
  - `no_prevent_item`: earlier postmortems exist but have no tracked `prevent` item;
  - `repeated_while_open`: at least one earlier `prevent` item was not done at that moment (it was accepted before and `completed_at` is null or later);
  - `repeated_after_done`: every earlier `prevent` item was done before the repeat ("the fix may not have worked").
  Each repeat lists the earlier incidents and their prevent items with status at that moment. Items closed `wont_do` count as not done.

### 4.5 API (base `/api`, camelCase JSON, RFC 9457 errors as in doc 05)

| Method | Path | Who | Request | Response |
|---|---|---|---|---|
| GET | `/action-items` | reader (filtered to readable applications) | query: `applicationIds`, `statuses` (default all tracked: open, in_progress, blocked), `priorities`, `sourceKinds`, `owner` (`me`, `unassigned` or a stakeholder id), `overdueOnly`, `incidentId`, `page`, `pageSize` (≤ 200) | `PagedResult[ActionItemDto]` |
| GET | `/action-items/{actionItemId}` | reader | | `ActionItemDto` |
| POST | `/applications/{applicationId}/action-items` | admin | `ActionItemCreateRequest` | `201 ActionItemDto` (`source_kind = manual` unless a later doc's endpoint creates it) |
| PATCH | `/action-items/{actionItemId}` | admin (owner: `itemDetailsMarkdown` only) | `ActionItemUpdateRequest` | `ActionItemDto` |
| POST | `/action-items/{actionItemId}/status` | admin or owner (4.3 table) | `{status, reasonText?, completionNoteText?}` | `ActionItemDto` |
| POST | `/action-items/{actionItemId}/accept` | admin | optional `ActionItemUpdateRequest` fields applied first | `ActionItemDto` |
| DELETE | `/action-items/{actionItemId}` | admin, `proposed` only | | `204` |
| GET | `/postmortems/{postmortemId}/action-items` | reader | | `list[ActionItemDto]` in `display_order` |
| GET | `/action-items/overview` | reader | `applicationIds`, `days` | `ActionItemOverviewResponse` |

`ActionItemDto`: `actionItemId, applicationId, applicationName, incidentId, incidentReference, postmortemId, sourceKind, sourceRecordId, itemTitle, itemDetailsMarkdown, actionType, actionPriority, itemStatus, suggestedOwnerRoleText, owner {stakeholderId, displayName, role} | null, dueOn, originalDueOn, dueOnChangeCount, isOverdue, daysOverdue, statusReasonText, completionNoteText, completedAt, completedBy, acceptedAt, externalReferenceText, externalReferenceUrl, lastRemindedAt, canEdit, canChangeStatus, allowedStatuses, createdAt, updatedAt`. `canEdit`/`canChangeStatus`/`allowedStatuses` are worked out for the caller so the screen never offers a refused action. `externalReferenceUrl` is built from `SERVICENOW_INSTANCE_URL` with the configured task path (`ACTION_ITEMS_EXTERNAL_REFERENCE_URL_TEMPLATE`, empty = no link).

`ActionItemCreateRequest`: `itemTitle` (2–300), `itemDetailsMarkdown?`, `actionType`, `actionPriority`, `ownerStakeholderId?`, `dueOn` (required), `incidentId?` (must belong to the application), `postmortemId?` (must belong to that incident), `externalReferenceText?`. `ActionItemUpdateRequest`: the same fields, all optional; `ownerStakeholderId: null` unassigns. `extra="forbid"` on all.

`ActionItemOverviewResponse`: `periodStart, periodEnd, completion {acceptedCount, doneCount, wontDoCount, openCount, overdueCount, completionRate, completionRateSampleCount, medianDaysToComplete, medianSampleCount, onTimeShare}, byApplication [...same per application], needsAttention [...], repeats [{recurrenceCategory, serviceId, serviceName, incidents [{incidentId, incidentReference, openedAt, outcome, earlierPreventItems [{actionItemId, itemTitle, statusAtRepeat}]}]}]`.

Errors: `404` unknown item, incident or postmortem; `403` no read or no change right (message says which); `422` invalid transition, missing reason, due date out of range, owner not an active person of the application, external reference not matching the pattern, finalising with proposed items; `409` when the item changed since it was read is **not** used (last write wins, every change audited; the screen refetches after each mutation).

Audit actions (`AuditService.record`): `action_item.create`, `action_item.accept`, `action_item.discard`, `action_item.update` (changed field names, old and new due date), `action_item.status` (from, to), all with `application_id` and the item id.

### 4.6 Retention and incident deletion
- `incident_retention.py:_delete_incident_batch` and `_delete_investigations`: before deleting postmortems and incidents, `update(ActionItem).where(ActionItem.incident_id.in_(ids)).values(incident_id=None, postmortem_id=None)` (and by `postmortem_id` for the investigation path). `removed["actionItemsUnlinked"]` counts them. `incident_reference_text` keeps the number.
- `run_retention_cleanup`: delete closed items past `ACTION_ITEMS_CLOSED_RETENTION_DAYS` (counted as `actionItems`).

### 4.7 The ServiceNow seam (designed, not built; D1 builds it)
- Port `backend/keigan/integrations/action_item_tracker.py` (D1 creates it): `class ExternalTaskTracker(Protocol)`: `system_name: str`; `async def create_task(item: ActionItemSnapshot) -> ExternalTaskReference`; `async def read_task_states(references: list[str]) -> dict[str, ExternalTaskState]`. `ActionItemSnapshot` carries only title, details, type, priority, due date, incident number and the owner's ServiceNow user id when known; never the postmortem text.
- Columns D1 adds by its own revision: `external_system` (open column, like `record_system`), `external_record_identifier` (sys_id), `external_status_text`, `external_synced_at`, `external_sync_status` (enum `not_linked`, `pending`, `linked`, `failed`). `external_reference_text` (v1) becomes the displayed number.
- Rule for D1, decided now so v1 does nothing that conflicts: **once an item is linked, ServiceNow owns its status**; Keigan reads it back on the existing poll schedule, stops its own reminders for that item, and shows "Tracked in ServiceNow". Keigan never closes a ServiceNow task.
- Priority mapping (D1): `top` → 1, `high` → 2, `normal` → 3, `low` → 4 (ServiceNow priority), configurable then.

### 4.8 Settings (all in `backend/keigan/config/settings.py` with `Field` bounds, in `backend/.env.example` and the Helm `backendEnvironment`, one comment line each)

| Name | Default | Range | Meaning |
|---|---|---|---|
| `ACTION_ITEMS_MAXIMUM_PER_POSTMORTEM` | 8 | 1–20 | Most items the AI may propose for one postmortem (also told to the model) |
| `ACTION_ITEMS_MAXIMUM_DUE_DAYS` | 180 | 7–730 | Latest due date, in days from today (and the clamp on the AI's `due_in_days`) |
| `ACTION_ITEMS_DETAILS_MAXIMUM_CHARACTERS` | 4000 | 200–20000 | Longest details text |
| `ACTION_ITEMS_REASON_MINIMUM_CHARACTERS` | 10 | 1–200 | Shortest reason for `blocked` and `wont_do` |
| `ACTION_ITEMS_REMINDERS_ENABLED` | true | | Master switch for reminder and escalation emails |
| `ACTION_ITEMS_REMINDER_HOUR_LOCAL` | 9 | 0–23 | Hour, in the application's time zone, at which the daily reminder job runs |
| `ACTION_ITEMS_REMINDER_DAYS_BEFORE_DUE` | 2 | 0–14 | Days before the due date of the "due soon" reminder (0 = none) |
| `ACTION_ITEMS_OVERDUE_REMINDER_INTERVAL_DAYS` | 7 | 1–30 | Days between reminders for one overdue item |
| `ACTION_ITEMS_ESCALATE_AFTER_OVERDUE_DAYS` | 14 | 1–90 | Days overdue after which top and high items go to the escalation roles |
| `ACTION_ITEMS_ESCALATION_ROLES` | `lead,manager` | values of `StakeholderRole` | Who receives escalations and unowned items |
| `ACTION_ITEMS_POSTMORTEM_REQUIRED_PRIORITIES` | `P1,P2` | values of `Priority` | Incidents that should have a final postmortem |
| `ACTION_ITEMS_POSTMORTEM_GRACE_DAYS` | 5 | 1–60 | Days after resolution before a missing postmortem is listed |
| `ACTION_ITEMS_REPEAT_WINDOW_DAYS` | 90 | 7–365, ≤ `INCIDENT_RETENTION_DAYS` | Look-back of the repeats view |
| `ACTION_ITEMS_OVERVIEW_MAXIMUM_DAYS` | 365 | 7–730 | Longest overview period |
| `ACTION_ITEMS_CLOSED_RETENTION_DAYS` | 730 | 90–3650 | Closed items older than this are deleted |
| `ACTION_ITEMS_EXTERNAL_REFERENCE_PATTERN` | `^[A-Z]{2,10}[0-9]{4,12}$` | a valid regex | Accepted shape of a typed ServiceNow number |
| `ACTION_ITEMS_EXTERNAL_REFERENCE_URL_TEMPLATE` | empty | must contain `{number}` when set | Link for the typed number, for example `https://<instance>/nav_to.do?uri=task.do?sysparm_query=number={number}` |

Validators: list settings are parsed and checked against their enums at startup (invalid stops Keigan, as `LLM_MODEL_PRICES_JSON` does); `ACTION_ITEMS_REPEAT_WINDOW_DAYS <= INCIDENT_RETENTION_DAYS`.

---

## 5. User experience

### 5.1 Postmortem tab: "Action items" panel (`PostmortemActionItems.tsx`, inside `PostmortemSection`)
- Below the report card, a card "Action items" with two groups: **Suggested by Keigan** (proposed; `AiGeneratedChip`) and **Tracked**.
- A suggested row shows title, type, priority, suggested owner role, due date, and three controls for admins: **Accept**, **Edit and accept** (opens the drawer prefilled; owner picker is the team list filtered to active people), **Discard**. "Accept all" accepts every suggested item that has a valid date.
- A tracked row shows owner (name and role), due date (with "Overdue by 3 days" text and a warning chip), priority, status chip and a "More" menu (change status, edit).
- **Add action item** (admin) opens the drawer with the incident and postmortem preset.
- While suggestions remain, the **Finalise** button is disabled with the visible reason "Accept or discard 3 suggested action items first" (also the API refuses).
- After finalisation the panel stays editable (statuses and owners change after the document is frozen) and says "The finalised document shows the list as it was when it was finalised."

### 5.2 Action items page (`/action-items`, sidebar Reliability section, icon `ListChecks`, label "Action items")
- Header: application scope from the existing switcher, period select (30, 90, 365 days), four stat tiles: open, overdue, completion rate (with "n = 24"), median days to complete.
- Tabs:
  1. **Items**: filter bar (status, priority, owner: me, unassigned, anyone; source; overdue only) and a `DataTable`: title, application, incident (link), owner, due (date; overdue in text and chip), priority, status. Row opens `ActionItemDrawer`.
  2. **Needs attention**: grouped cards per kind (overdue, top priority without owner, postmortem missing, suggestions waiting; doc 30 adds policy breaches), each linking to the record.
  3. **Repeats**: one card per recurrence group (category and service), a vertical list of incidents in time order; each later incident has an outcome chip ("Came back while 2 follow-ups were open", "Came back after all follow-ups were done", "No follow-ups were tracked", "No postmortem") and expands to the earlier prevent items with their status at that moment.
- `ActionItemDrawer`: fields (title, details, type, priority, owner, due date, ServiceNow number), status actions as buttons limited to `allowedStatuses`, reason field when needed, history line "Due date moved twice (first due 1 Dec)", audit-free (no people's history list).
- Email links: reminders link to `/action-items?owner=me`; escalations to `/action-items?tab=attention&applicationIds=<id>`.

### 5.3 States
- Empty (no items): "No action items yet. They appear when a postmortem is drafted, or add one by hand." with "Open incidents" link.
- Loading: skeleton table and tiles. Error: `ErrorState` with retry; mutations show a toast with the server's `detail`.
- Partial: completion figures below 5 samples show "Not enough completed items yet" (reuse `METRICS_MINIMUM_RATING_SAMPLE` for the threshold, so the two pages agree).
- An owner who was removed from the team: "Unassigned (was Jane Doe)" is not shown; the item simply reads "Unassigned" (the stakeholder row is gone).

### 5.4 Keyboard and screen readers
- Every control reachable by Tab; drawer traps focus (`useFocusTrap`) and returns focus to the row; Escape closes.
- Status changes announce through the existing toast live region ("Marked as done").
- Overdue is conveyed in text ("Overdue by 3 days"), never by colour alone; the due-date input has a visible label and the accepted range in its helper text.
- The table has a caption; the repeats list uses `<ol>` with time order.

### 5.5 Phone layout (390 px)
- The table turns into stacked cards (title, owner, due, status). Filters collapse into a "Filters" button opening a drawer. The drawer is full screen. All buttons at least 44 px tall. Stat tiles wrap two by two.

### 5.6 Locales
New namespace `actionItems` in `frontend/src/i18n/locales/{en,es,fr,ja,nl,zh-CN}/actionItems.json` (`es-MX` gets an empty file and falls back to `es`, as for `metrics`). Key groups: `page`, `tabs`, `stats`, `filters`, `table`, `status.*`, `type.*`, `priority.*`, `source.*`, `drawer`, `errors`, `attention.*` (one per kind), `repeats.outcome.*`, `postmortemPanel`, `empty`. Additions to `investigations.json` (`postmortem.finalizeBlocked`) and `navigation.json` (`items.actionItems`). `npm run check:locales` must pass.

---

## 6. Safety, access and privacy

### 6.1 Who may see and change what
- Read: anyone who can read the application (`ensure_application_reader`); lists are filtered with `scoped_application_ids`.
- Change: application admins (`ensure_application_admin`), except the owner rights in 4.3.
- **Owner match**: the caller is the owner when the owner stakeholder is active and its `user_principal_name` or `email_address` equals the caller's user principal name or email, case-insensitive. The caller must still read the application; being named owner grants no read access (Keigan does not grant access, doc 20).
- Owner must be an active `person` stakeholder of the same application (not a channel or a list).

### 6.2 AI output
- The AI writes `item_title` and `suggested_owner_role_text` only, through `sanitize_ai_model` and `sanitize_ai_line`; the inputs are already masked (names replaced, V12). The prompt says roles, never names. No new AI call is added.
- Human text (titles, details, reasons, notes) is masked with `PiiMasker` and sanitised before storage, as postmortem edits are.

### 6.3 Audit and storage
- Audit rows per change (4.5). Reminder emails are outbox rows (`notification_delivery`) like every other message.
- Stored: the item text (masked), owner reference, dates. Not stored: email content beyond the outbox row.
- Retention: 4.2 and 4.6.

---

## 7. Acceptance criteria

| # | Criterion | Test type |
|---|---|---|
| AC-1 | Writing a postmortem draft creates one `proposed` row per model item (up to the setting), with due date in the application's zone, and keeps accepted rows | integration (service) |
| AC-2 | Regenerating a draft replaces proposed rows only | integration |
| AC-3 | No AI path writes `owner_stakeholder_id`; the postmortem Markdown shows the role, not the person, for an assigned item | integration |
| AC-4 | Finalising with proposed items returns 422 naming `actionItems`; after accepting or discarding all, it succeeds and the Markdown's action table equals the accepted rows | integration (controller) |
| AC-5 | Accepting an item whose date is in the past is refused with a message asking for a new date | unit (rules) and integration |
| AC-6 | Every transition in the 4.3 table is allowed or refused for admin and owner exactly as listed | unit |
| AC-7 | `blocked` and `wont_do` without a reason of minimum length are refused | unit |
| AC-8 | An owner who is only a reader can mark their item done; cannot reassign, re-date or set `wont_do` | integration (controller) |
| AC-9 | A tracked item cannot be deleted (422); a proposed one can (204) | integration |
| AC-10 | Changing the due date increments `due_on_change_count` and keeps `original_due_on` | integration |
| AC-11 | A person without read access gets 403 on read and change, and list endpoints omit the application | integration |
| AC-12 | The owner must be an active person of the same application; a channel or another application's member is refused | integration |
| AC-13 | Overdue uses the application's time zone: an item due "today" in Tokyo is not overdue at 23:00 Tokyo time and is at 00:01 | unit |
| AC-14 | The reminder job sends one email per owner listing all their due items, and none on a second run the same local day | integration (job) |
| AC-15 | Overdue reminders repeat no sooner than the interval; escalations go to the configured roles for top and high items only; unowned items go to the escalation roles | unit and integration |
| AC-16 | Reminders are not sent when the switch is off, for `proposed`, `done` or `wont_do` items, or to inactive members | integration |
| AC-17 | Completion rate excludes `wont_do` from the denominator, carries its sample size, and is null with no data | unit |
| AC-18 | The repeats view gives each of the four outcomes on constructed data, using the status at the moment of the repeat | integration |
| AC-19 | The overview returns per-application figures and never a per-person ranking | integration (shape test) |
| AC-20 | Incident retention keeps open items, clears their incident and postmortem links and keeps `incident_reference_text`; closed items past retention are deleted | integration |
| AC-21 | Deleting a stakeholder unassigns their items; deleting an application works on SQLite with the new keys (and the release covers the new NO ACTION key by metadata) | integration |
| AC-22 | `recurring_incidents` produces the same signals as before after using `recurrence_key` | unit (existing detector tests unchanged and passing) |
| AC-23 | Every new setting is validated, documented in `backend/.env.example` and the Helm values with the same default | unit (`test_settings.py` pattern, deployment settings test) |
| AC-24 | Schema drift test passes: entity, Alembic revision and Azure SQL scripts agree | integration (`test_schema_drift.py`) |
| AC-25 | No status literal for the new columns outside `status_values.py` (the AST guard test) | unit (existing guard) |
| AC-26 | The page, panel and drawer work at 1440 and 390 px, light and dark, keyboard only | browser script |

---

## 8. Test plan

Backend (mirrors `backend/keigan/`):
- `backend/tests/unit/services/test_action_item_rules.py`: transitions, reasons, dates and time zones, reminder kinds, completion figures (AC-5, 6, 7, 13, 15, 17).
- `backend/tests/unit/services/test_postmortem_action_items.py`: table rendering, section replacement (heading present, absent, last section) (AC-4).
- `backend/tests/unit/services/test_incident_recurrence.py` (AC-22).
- `backend/tests/integration/services/test_action_item_service.py` (AC-1, 2, 3, 8–12, 21).
- `backend/tests/integration/services/test_action_item_reminders.py` (AC-14, 15, 16), with the outbox in simulated mode and a frozen clock.
- `backend/tests/integration/services/test_action_item_overview_service.py` (AC-18, 19).
- `backend/tests/integration/services/test_communication_service.py`: draft creates proposed rows; finalise gate (AC-1, 2, 4).
- `backend/tests/integration/services/test_incident_retention.py` and `test_administration_service.py` additions (AC-20).
- `backend/tests/integration/controllers/test_action_item_controller.py`: every endpoint, status codes, camelCase shapes (AC-4, 8, 9, 11).
- `backend/tests/unit/ai/test_investigation_ai_schemas.py` (or the existing schema test file): `priority` default and validation; prompt renders `maximum_action_items`.
- `backend/tests/unit/config/test_action_item_settings.py` and the deployment settings test (AC-23).
- Existing `test_schema_drift.py`, `test_status_values.py` (add the new columns), status-literal guard (AC-24, 25).

Frontend:
- `frontend/src/features/action-items/actionItemPresentation.test.ts` (vitest): due-date text, overdue text, allowed actions from the DTO.
- `npm run typecheck`, `check:locales`, `check:contrast`, build.
- Browser script `frontend/scripts/check-action-items.mjs` (same style as `check-ask-keigan.mjs`, demo seed, mock model): open an investigation with a draft postmortem, accept one, discard one, try to finalise (blocked), accept the rest, finalise; open `/action-items`, filter overdue, mark one done, open Repeats; repeat at 390 px; light and dark (AC-26).

---

## 9. Phased build plan

| Step | Task | Size | Depends on | Demonstrable at the end |
|---|---|---|---|---|
| 1 | Enums, entity, Alembic revision, Azure SQL regeneration, ER diagram, settings, `action_item_rules.py` with unit tests | M | nothing | drift test green; rules tested |
| 2 | `ActionItemService`, `postmortem_action_items.py`, postmortem integration (draft rows, finalise gate, Markdown table), prompt v2, mock factory priority, stakeholder and retention release | M | 1 | a seeded draft shows proposed rows via the API; finalise refuses until decided |
| 3 | Controller and DTOs; `actionItemsApi.ts`; postmortem panel and drawer; locales | M | 2 | accept, edit, discard and finalise in the browser |
| 4 | Reminder job, schedule, email strings (en, ja), outbox types | S | 2 | reminders visible in the Outbox page (simulated mail) |
| 5 | Overview service (completion, needs attention, repeats) and `incident_recurrence.py`; the Action items page | M | 2, 3 | `/action-items` with three tabs on demo data |
| 6 | Demo seed rows, demo SQL regeneration, browser script, docs | S | 3–5 | demo shows overdue, done, blocked, unowned and a repeat |
| 7 (optional, after B5 phase 4) | Ask Keigan tool `list_action_items` (global scope; owners aliased by role, never named, per D2), one registry entry | S | 5 | "Which follow-ups from last month are overdue?" answered with a cited tool call |

Build order for wave C: **this whole spec first**, then doc 30 (needs steps 1–3 and the "Needs attention" list of step 5), doc 31 (needs step 5's overview), doc 32 (needs step 1's table for runbook review items).

---

## 10. Docs, migration and demo-data impact

- `My Plans` docs (the lead updates the status page and index; the builder updates the rest): doc 03 (new table, columns, enums), doc 15 (regenerate with `backend/scripts/generate_entity_relationship_diagram.py`), doc 05 (endpoints), doc 01 (postmortem section, new page), doc 12 (feature row), doc 13 (sequence: draft → proposed items → accept → finalise; daily reminders), doc 06 (postmortem prompt v2), doc 02 (new schedule and job), doc 09 (learnings).
- Azure SQL: regenerate `database/azure_sql/02_create_tables.sql`, `03_create_foreign_keys.sql`, `04_create_indexes.sql`, `05_reference_data.sql` with `generate_azure_sql_ddl.py`; add `database/azure_sql/migrations/<revision>_action_items.sql` with `generate_azure_sql_migration_scripts.py`; update table, key and index counts and the check query in `database/azure_sql/README.md`.
- Demo seed (`backend/keigan/seed/investigation_seed.py`, after `write_postmortem_offline`): for each postmortem the seed finalises, accept every proposed item through `ActionItemService` (seed actor) and then set, deterministically by scenario: Claims (CLMJP) one `top` prevent item done on time, one overdue `high` item owned by the seeded developer, one `blocked` item with a reason, one `top` item unassigned; Chad (CHAD) one done late and one open; the recent (draft) postmortem keeps its proposed items. If two seeded incidents share a recurrence key, the repeats view shows them; otherwise the seed adds no fake incident and the Repeats tab shows its empty state (stated in the seed docstring). Add `action_item` to the incident group in `backend/scripts/demo_data_sql/demo_data_plan.py` and regenerate `database/azure_sql/demo_data/` with `generate_demo_data_sql.py`.

---

## 11. Risks, mitigations and open questions

### 11.1 Risks
| Risk | Mitigation |
|---|---|
| Teams already track follow-ups in ServiceNow and see Keigan as a second list | Typed ServiceNow reference now; D1 makes ServiceNow the owner of linked items (4.7) |
| Owners are not set (the team list lacks people) | "Top priority without owner" in Needs attention and escalation to leads |
| AI dates are unrealistic | Clamp, then a person accepts or edits every date; due-date moves are visible |
| Reminder emails in English for Spanish, French, Dutch and Chinese readers (backend tables are en and ja only) | Known platform limit (3.1); listed as open question 4 |
| Time-zone names that `zoneinfo` does not know | Fallback to UTC with one log line; the application form should validate the zone (separate fix) |

### 11.2 Open questions for the owner
1. **Who may close an item as `wont_do`?** Decided: application admins only. Should a lead (team role) also be able to, even without the admin group?
2. **ServiceNow table for D1**: `problem_task`, a Post-Incident Review task, or another? Needed before D1, not before C1.
3. **Retention of closed items**: two years by default. Does compliance need longer for P1 follow-ups?
4. **Backend email languages**: reminders inherit the en/ja-only string tables. Extend them to all six languages as a separate small task?
