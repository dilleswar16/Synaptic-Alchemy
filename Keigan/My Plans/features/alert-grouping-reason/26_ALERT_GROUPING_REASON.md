# 26 — Why these alerts were grouped

Written 2026-11-21. Roadmap item B3 in `product/21_PRODUCT_RESEARCH.md` (section 3.5): say, in one plain sentence on each alert group, why its alerts belong together. Status: built, verified by tests and screenshots, not yet committed.

## What it does

Each alert group now carries a structured reason: a code plus the names and numbers a sentence needs. The screen turns it into a localised sentence, for example "Grouped because 3 alerts fired on claims-sql within 10 minutes of each other."

It is shown under the group title in the alerts list (not for `single_alert`, where there is nothing to explain) and as a line at the top of the group drawer.

## How the reason is chosen

The reason is **derived when a group is read**, from the group's alerts, the application's service dependencies and its group window. Nothing is stored: no schema change, no CHECK constraint, no change to the demo data. The alert pipeline's group stage (`AlertPipelineService._select_group`) already joins an alert by the same checks, in the same order; the derivation replays those checks over the group's alerts, oldest first (the first alert starts the group and has no reason of its own).

| Code | Meaning | Parameters |
|---|---|---|
| `same_service` | a later alert was on a service an earlier alert of the group was on | `serviceName`, `alertCount` (alerts of the group on that service), `windowMinutes` |
| `dependency` | a later alert was on a service that depends on, or is depended on by, a service already in the group | `serviceName`, `relatedServiceName`, `windowMinutes` |
| `same_rule` | a later alert had the same rule identifier as an earlier one | `ruleName`, `alertCount`, `windowMinutes` |
| `attached_to_incident` | none of the above explains the group, but it is attached to an incident | `incidentName` (the external incident number, else the title), `windowMinutes` |
| `single_alert` | the group has one alert | none |
| `not_recorded` | no alerts, or the rules above cannot explain the group | none |

A group usually joined by several of these. The **strongest wins**, in the order `same_service`, `dependency`, `same_rule`, then `attached_to_incident`; `single_alert` applies when the group has exactly one alert, and `not_recorded` is the fallback. Where a reason has more than one possible example (several related services), the parameters use the first one in alphabetical order, so the sentence does not change between reads.

`windowMinutes` is the application's group window from its noise-reduction policy, or the default (`group_window_minutes`, 10 in `alert_rules.py`) when the application has no stored policy. It is the window **now**: if the policy was changed after the group formed, the sentence shows the current value, not the one in force then.

## Response shape

`AlertGroupSummaryResponse.groupingReason` (in `GET /api/alert-groups` and `GET /api/alert-groups/{id}`) is `{ "code": "<code>", "parameters": { ... } }`. It is always present. It replaces the former nullable string of the same name; the stored `alert_group.grouping_reason` text column still exists and is still written by the pipeline, but the alert-group endpoints no longer return it. Parameter keys are camelCase as listed above.

## Where the code is

| Part | Path |
|---|---|
| Derivation (pure functions, no database) | `backend/keigan/services/alert_grouping_reason.py` (`derive_grouping_reason`) |
| Code names | `AlertGroupingReason` in `backend/keigan/entities/status_values.py` |
| Response shape | `GroupingReasonResponse` in `backend/keigan/dtos/alert_dtos.py` |
| Read-time derivation | `AlertService.grouping_reasons` in `backend/keigan/services/alert_service.py` (the Alerts page and the investigation payload both call it) |
| Shared neighbour helper | `service_neighbours` in `backend/keigan/services/alert_rules.py` (the pipeline and the derivation both use it, so "depends on" means the same in both) |
| Screen | `frontend/src/features/alerts/components/GroupingReasonText.tsx`, used by `pages/AlertsPage.tsx`, `components/AlertGroupDrawer.tsx` and the investigation page's `AlertsSection.tsx` |
| Types | `AlertGroupingReason` in `frontend/src/api/alertsApi.ts` |
| Text | `groupingReason.<code>` in the `alerts` namespace of each locale |
| Tests | `backend/tests/unit/services/test_alert_grouping_reason.py`, `tests/integration/services/test_alert_service.py`, `tests/unit/services/test_alert_rules.py`, `tests/unit/test_frontend_contract.py` |

A code the screen does not know reads as "not recorded", so a future code cannot break the page.

## Settings

None. The window comes from the existing noise-reduction policy.

## What is not verified

- `attached_to_incident` has unit tests only; no integration test or screen run produced it.
- The translations (en, es, fr, ja, nl, zh-CN) were not read by native speakers. `es-MX` was not touched and falls back to `es`.

## Known leftovers

- None open. Two leftovers were closed on 2026-11-21: the investigation page (`GET /api/investigations/{id}`, `alertGroup.groupingReason`) now returns the same `{ code, parameters }` and shows the same sentence; and the stored `group_summary` fallback no longer states an alert count (it said "1 alert on claims-sql" for a group of 2 because it is written once, when the group is created, and the count grows afterwards). The fallback now reads "Started with an alert on <service>."

## Deliberately left out

- Multi-hop grouping (dependencies of dependencies). The pipeline groups across one declared hop only; the sentence says only what the pipeline does.
- Storing the reason at the moment of grouping. Deriving it avoids a column and a backfill, at the cost of the window caveat above.
- A reason for each individual alert. The sentence explains the group.
