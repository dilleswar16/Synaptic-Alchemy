# 31 — Weekly health review

Roadmap item **C3** (doc 21, product research, wave C "Close the loop"). Written 2026-11-23 on branch `keigan-ui-ux`, after C1 (doc 29, action items) and C2 (doc 30, error-budget policy) were built, by the lead (not an agent): the first two specs of this wave were written by agents, this one while building.

---

## 1. Purpose, status and how to use this document

**Purpose.** Give each application team one page they can open at their weekly reliability meeting: what happened this week (incidents, alert noise, SLO status), what the error budget cost, which follow-ups are done, open, overdue or have no owner, and which policy breaches wait. When the team has gone through it, an admin **marks it as reviewed** (who, when, a short note), so Keigan can say which weeks were reviewed.

**Status.** Built 2026-11-23 (section 12).

**What this is not.** Not a new report type or table of figures: the **weekly digest** (`intelligence_report`, `report_type = weekly_digest`, built every week by `send_intelligence_report`, listed on the Intelligence page, emailed to subscribers) already exists with health score, SLOs, signals, incidents and noise. The review **extends that digest** with two new sections computed from the C1 and C2 data and adds the "reviewed" record. Nothing else is duplicated.

**Glossary.**

| Term | Meaning |
|---|---|
| Weekly digest | The existing weekly `intelligence_report` of an application: seven days ending when it was built |
| Review sections | The new `budget` and `actionItems` sections inside `report_sections_json` of a weekly digest |
| Reviewed | An application admin recorded that the team went through the digest: `reviewed_at`, `reviewed_by_user_principal_name`, optional `review_note_text` |

---

## 2. Goals, non-goals, anti-goals

### 2.1 Goals
1. **G1.** The digest says what the week cost the error budgets (per incident of the week: the worst share and its state) and which policy breaches opened or are still open.
2. **G2.** The digest says where the follow-ups stand: how many are open, overdue (the list, longest overdue first, at most `WEEKLY_REVIEW_MAXIMUM_LISTED_ITEMS`), done this week, accepted this week, top-priority items with no owner.
3. **G3.** An application admin can mark a digest reviewed once, with a note; everyone with read access sees who reviewed it and when. A weekly digest that nobody reviewed says so.
4. **G4.** All figures come from code on stored rows. The model may phrase the summary (as for the digest today) but is given the figures and never computes them.

### 2.2 Non-goals
- No new schedule, report type, email template or page: the digest's schedule, email and detail view are reused.
- No meeting minutes, attendance or agenda; one note field only.
- No automatic escalation when a week is not reviewed (a later step could use "unreviewed" for a reminder).
- No review of anything but the weekly digest (proactive alerts are not reviewed).

### 2.3 Anti-goals and controls
| Anti-goal | Control | AC |
|---|---|---|
| A number from the model | The two new sections are built by code from rows; the facts given to the narration are the same figures | AC-1, AC-2 |
| Review used to hide a problem | Reviewing changes nothing but the review fields; the figures stay; the review is audited | AC-6 |
| A reader marks the review | Application admins only; a second review of the same digest is refused (one review per digest) | AC-5, AC-7 |

---

## 3. Current state (verified 2026-11-23)

| Topic | Fact | Evidence |
|---|---|---|
| Digest | `IntelligenceService._build_report` builds sections (`healthScore`, `healthComponents`, `executiveSummary`, `slos`, `recommendations`, `incidents`, `noise`, `signals`), narrates the summary, `_report_markdown` renders them, `_send_report` emails subscribers of `intelligence_report` | `backend/keigan/services/intelligence_service.py` |
| Schedule | Hourly check `enqueue_weekly_reports`: one job per application per ISO week at the configured weekday and hour (UTC) | `backend/keigan/workers/schedulers.py` |
| Screen | Intelligence page, Reports tab: list and detail of a report | `frontend/src/features/intelligence/pages/IntelligencePage.tsx` |
| Data | Action items and their dates (doc 29), budget impacts and breaches (doc 30) | `action_item`, `incident_budget_impact`, `error_budget_policy_breach` |

---

## 4. Design

### 4.1 Decisions
| # | Decision | Reason | Rejected alternative |
|---|---|---|---|
| C3-D1 | Extend the weekly digest, not a new entity | One weekly document per application already exists, is scheduled, emailed and listed | A second "review" report beside it (two weekly documents to read) |
| C3-D2 | Three nullable columns on `intelligence_report` for the review | One review per digest, no history of edits needed (audit rows keep who did what) | A `weekly_review` table (a table for three fields) |
| C3-D3 | The period is the digest's own seven days | The figures then match the rest of the digest | A calendar week |
| C3-D4 | Overdue is judged on the day the digest is built, in the application's time zone | Same rule as the reminders (doc 29) | UTC midnight |
| C3-D5 | Only application admins review | Same as other team decisions (docs 29 and 30) | Any reader |

### 4.2 Data model
Alembic revision on top of `f4a8c2e6b0d7`: `intelligence_report.reviewed_at` (DateTime, null), `reviewed_by_user_principal_name` (String 320, null), `review_note_text` (String 2000, null). No backfill (earlier digests read as not reviewed).

### 4.3 The new sections (`services/weekly_review_facts.py`, one function `weekly_review_sections(session, application, period_start, period_end, now, maximum_listed_items)`)

`budget`: `policyIsEnabled`; `incidents` (incidents opened in the period that have at least one stated share: incident number, title, worst share, SLO name, state); `breachesOpenedCount`; `openBreaches` (open breaches of the application: kind, share, incident number, SLO name). Shares are as stored (doc 30); an incident with no stated share is counted in `incidentsWithoutFigureCount`.

`actionItems`: `openCount` (open, in progress, blocked), `overdueCount`, `overdue` (title, owner name or null, priority, days overdue, incident number; longest overdue first, at most the maximum), `doneThisWeekCount`, `acceptedThisWeekCount`, `topPriorityWithoutOwner` (titles, at most the maximum), `suggestedWaitingCount` (proposed items of postmortems).

Both go into `report_sections_json`, into the facts text given to the narration (one line each), and into the Markdown (headings "Error budget" and "Follow-ups").

### 4.4 API
`POST /api/intelligence-reports/{reportId}/review` (application admin): `{noteText?}` (at most 2000 characters, masked and sanitised) → the report response. 422 for a report that is not a weekly digest or is already reviewed. Audit `intelligence_report.review`. The report summary gains `reviewedAt`, `reviewedBy` and `reviewNote`.

### 4.5 Settings
`WEEKLY_REVIEW_MAXIMUM_LISTED_ITEMS` (default 10, 1 to 50): the most overdue items and unowned items listed. In `.env`, `.env.example` and Helm.

---

## 5. User experience
- Intelligence page, Reports tab: a weekly digest shows two new cards, "Error budget" and "Follow-ups", above the existing sections; the list shows a "Reviewed" chip, or "Not reviewed" for digests older than a day.
- "Mark as reviewed" (admins) opens a dialog with an optional note; afterwards the card header reads "Reviewed by <name> on <date>" with the note.
- Six locales (es-MX falls back to es); new strings in the `intelligence` namespace.

---

## 6. Safety, access and privacy
Read: application readers (as the digest). Review: application admins. Names shown are team members' display names already visible on the Action items page. The note is masked with `PiiMasker` and sanitised.

---

## 7. Acceptance criteria
| # | Criterion | Test |
|---|---|---|
| AC-1 | The `budget` section lists the week's incidents with their worst stated share, counts incidents without a figure, and lists open breaches | integration |
| AC-2 | The `actionItems` section counts open, overdue, done and accepted items for the period and lists overdue items longest first up to the maximum | integration |
| AC-3 | Overdue follows the application's time zone | unit/integration |
| AC-4 | The facts text and the Markdown carry both sections; the narration receives the figures | integration |
| AC-5 | Only an application admin can review; a reader gets 403 | integration (controller) |
| AC-6 | Review records who, when and the sanitised note, writes an audit row and changes nothing else | integration |
| AC-7 | A second review, or a review of a proactive alert, is refused with 422 | integration |
| AC-8 | The setting is validated and documented in `.env.example` and Helm | unit |
| AC-9 | Schema drift and status tests pass with the new columns | integration |

---

## 8. Phased build
1. Migration and setting; `weekly_review_facts.py` with tests.
2. Digest integration (sections, facts, Markdown), the review endpoint and DTO fields with tests.
3. Screens, locales, docs.

---

## 9. Docs impact
03 (columns), 05 (endpoint), 12 (tracker), 00 (status), Azure SQL scripts regenerated.

---

## 10. Risks and open questions
| Risk | Mitigation |
|---|---|
| A long list makes the digest unreadable | Lists are capped by the setting and the page links to the Action items page |
| Digests built before this change lack the sections | The screen shows the new cards only when the sections exist |

Open: **Should an unreviewed digest remind the admins after a few days?** Not built; the data to do it exists (`reviewed_at` is null).

---

## 12. Build notes (2026-11-23)

Built in two steps on `keigan-ui-ux` (migration, setting, facts module with tests; digest integration, endpoint, screen, locales).

Differences from this design:
- The route is `POST /api/intelligence-reports/{reportId}/review` (the existing report routes use that prefix). Revision `a1d5c9e3f7b2`.
- The two sections reach the screen through the digest's Markdown (headings "Error budget" and "Follow-ups"); the spec's two separate cards were not built. The structured sections are stored in `reportSections` for a later screen.
- The list shows a "Reviewed" chip; the "Not reviewed" chip for digests older than a day was not built (the detail says so).
- The narration receives the figures as fact lines; it was only run on the offline model.
- Not seen in a browser; no reminder for unreviewed digests (open question 1).

