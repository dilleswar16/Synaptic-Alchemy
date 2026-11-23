# 32 — Runbook health

Roadmap item **C4** (doc 21, product research, wave C "Close the loop"). Written 2026-11-23 on branch `keigan-ui-ux` by the lead while building, after C1 to C3.

---

## 1. Purpose, status and how to use this document

**Purpose.** Runbooks are only useful while they are findable and right. Keigan already matches runbooks to incidents and counts how often each was used. This feature tells each team which of its runbooks need attention: never used, not updated for a long time, often judged wrong, or unable to match anything (no symptoms) or to help (no steps). It reads what Keigan already stores; it never edits a runbook.

**Status.** Built 2026-11-23 (section 12).

**Glossary.**

| Term | Meaning |
|---|---|
| Runbook | A team's known-issue write-up: title, trigger symptoms, steps, the services it applies to (`runbook`) |
| Referenced | An investigation matched the runbook and used it (`times_referenced_count`, `last_referenced_at`) |
| Rated | An investigation that matched the runbook and received a verdict from a person (`correct`, `partially_correct`, `incorrect`) |
| Finding | One reason a runbook needs attention, with the figures behind it |

---

## 2. Goals, non-goals, anti-goals
### 2.1 Goals
1. **G1.** A per-application list of runbook findings, each with its figures, computed on read from stored rows (no new table, no model).
2. **G2.** Five finding kinds with thresholds in settings: `never_used`, `not_updated`, `often_wrong`, `no_trigger_symptoms`, `no_steps`.
3. **G3.** The weekly digest (doc 31) counts the runbooks with findings and names a few.

### 2.2 Non-goals
- No automatic edit, deletion or rewrite of a runbook, and no AI-written suggestions (a later step could draft an update from the investigations that used it).
- No new table or schema change; no new action item source.
- No scoring or ranking of runbooks beyond the findings.

### 2.3 Anti-goals and controls
| Anti-goal | Control | AC |
|---|---|---|
| Blaming a runbook on too little evidence | `often_wrong` needs at least `RUNBOOK_HEALTH_MINIMUM_RATED_INVESTIGATIONS` rated investigations; the figures are shown | AC-3 |
| Nagging about new runbooks | `never_used` and `not_updated` only apply once the runbook is older than the threshold | AC-2 |
| A model's opinion presented as fact | Nothing here uses a model | AC-1 |

---

## 3. Current state (verified 2026-11-23)
| Topic | Fact | Evidence |
|---|---|---|
| Runbooks | Entity with title, symptoms, steps, services, `times_referenced_count`, `last_referenced_at`, `created_at`, `updated_at` | `backend/keigan/entities/knowledge_entities.py:Runbook` |
| Matching | An investigation stores the runbooks it matched (`investigation_matched_runbook`); using one increments the counters | `incident_entities.py`, `knowledge_service.py` |
| Ratings | `investigation.user_feedback_verdict` | `incident_entities.py` |

---

## 4. Design
### 4.1 Decisions
| # | Decision | Reason | Rejected |
|---|---|---|---|
| C4-D1 | Compute on read | The inputs are small and already stored | A findings table (state to keep in sync) |
| C4-D2 | "Wrong" means the matching investigations were rated `incorrect` | It is the only judgement people already give; it judges the investigation, not only the runbook, so the figure is shown with its sample size and the wording is "often rated incorrect" | Inferring from outcomes (not recorded for runbooks) |
| C4-D3 | Ages are counted from `created_at` for never-used and from `updated_at` for not-updated | A runbook that was just edited is not stale | `last_referenced_at` for staleness |

### 4.2 Rules (`services/runbook_health_rules.py`, pure)
`findings_for(facts, today, thresholds)` returns findings in this order:
- `no_trigger_symptoms`: symptoms text empty (such a runbook cannot be matched to an incident).
- `no_steps`: steps text empty.
- `never_used`: referenced zero times and created at least `RUNBOOK_HEALTH_UNUSED_AFTER_DAYS` ago.
- `not_updated`: last updated at least `RUNBOOK_HEALTH_STALE_AFTER_DAYS` ago.
- `often_wrong`: rated investigations at least the minimum, and the share rated `incorrect` at least `RUNBOOK_HEALTH_WRONG_SHARE_PERCENT`.

### 4.3 API
`GET /api/applications/{applicationId}/runbook-health` (reader) → `{runbooks: [{runbookId, runbookTitle, timesReferencedCount, lastReferencedAt, createdAt, updatedAt, matchedInvestigationCount, ratedInvestigationCount, incorrectRatedCount, findings: [{kind, parameters}]}], runbookCount, withFindingsCount}`; runbooks with findings first, then the rest by title.

### 4.4 Settings
`RUNBOOK_HEALTH_UNUSED_AFTER_DAYS` (60, 7 to 730), `RUNBOOK_HEALTH_STALE_AFTER_DAYS` (180, 30 to 1095), `RUNBOOK_HEALTH_MINIMUM_RATED_INVESTIGATIONS` (3, 1 to 50), `RUNBOOK_HEALTH_WRONG_SHARE_PERCENT` (50, 10 to 100). In `.env`, `.env.example` and Helm.

### 4.5 Weekly digest
`weekly_review_sections` gains `runbooks`: `withFindingsCount` and up to the listed-items maximum of `{title, findingKinds}`; one fact line and one Markdown block "Runbooks".

---

## 5. User experience
The Runbooks step (and page) shows a "Runbook health" card above the list: the count, then each runbook with findings as a row with chips (one per finding) and the figures in words ("Used 0 times in 74 days", "Last updated 212 days ago", "3 of 5 rated investigations were rated incorrect"). Readers see it; nothing in it edits. Six locales (es-MX falls back); strings in the `knowledge` namespace.

---

## 6. Safety, access and privacy
Readers of the application. No personal data: titles, counts and dates only.

---

## 7. Acceptance criteria
| # | Criterion | Test |
|---|---|---|
| AC-1 | Findings are computed by the pure rules from the stored fields | unit |
| AC-2 | A runbook younger than the threshold is neither never-used nor stale | unit |
| AC-3 | `often_wrong` needs the minimum sample and the share; below either no finding | unit |
| AC-4 | The service counts matched and rated investigations of one runbook and no other | integration |
| AC-5 | The endpoint is reader-scoped (403 elsewhere) and orders runbooks with findings first | integration (controller) |
| AC-6 | The weekly digest section counts runbooks with findings | integration |
| AC-7 | Settings validated and documented in `.env.example` and Helm | unit |

---

## 8. Phased build
1. Rules, settings, tests. 2. Service, endpoint, digest section. 3. Card, locales, docs.

## 9. Docs impact
05 (endpoint), 12 (tracker), 00 (status), the weekly review spec (section 4.5 here).

## 10. Risks
| Risk | Mitigation |
|---|---|
| A good runbook flagged "never used" because incidents have not happened | Wording says only what is true ("used 0 times in N days"); thresholds are settings |
| Ratings blame the runbook for a bad investigation | Figures with sample size shown; minimum sample |

---

## 12. Build notes (2026-11-23)

Built in three steps on `keigan-ui-ux`: rules and settings with tests; service, endpoint and the digest section; the card and locales.

Differences from this design:
- The weekly digest's Markdown carries a "Runbooks" block and the structured `runbooks` section (spec 31 now lists four sections).
- The card is shown on the Runbooks step only; it hides itself when the application has no runbooks.
- No action item is created from a finding (it would need a new source value and a revision); the Action items page's "New action item" is the way.
- Not seen in a browser.

