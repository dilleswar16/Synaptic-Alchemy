# 39 — Later to-dos

**Date:** 2026-11-24. **Purpose:** one list of things that are worth doing later but are not being built now, so nobody has to rediscover them. Each item says what it is, why it was not built, how big it is, what it needs and when to look at it again. Nothing here is a promise; the owner picks.

Sources: `21_PRODUCT_RESEARCH.md` (the first market study), `38_COMPETITOR_AND_GAP_RESEARCH.md` (the second one, with 25 capability and 16 frontend gaps), and the checks made on 2026-11-24 against the code.

Sizes: **S** days, **M** one to two weeks, **L** several weeks. "Needs" says what blocks it: nothing (can be built and tested on this machine), a real model, a person, or an integration.

---

## 1. Notification preferences, including personal ones

**What exists (checked in the code, 2026-11-24).** Each stakeholder on an application's notification list (a person or a Teams channel) has: the channels to use (email, Teams), a minimum priority, the notification types, the subscribed services and a language. `notification_service.py` and `stakeholder_service.py` use them.

**What is missing.**
- **Quiet hours.** The `quiet_hours_json` column exists on the stakeholder row, but nothing reads or writes it. Setting it does nothing.
- **Personal settings.** The preferences belong to the application's contact list, set by an application admin. A person cannot set their own ("tell me by Teams, not email, never between 22:00 and 07:00 unless it is a P1").
- **A digest instead of single messages** (one summary per hour or per day for low priorities).

**What a proper version needs.** Read the quiet hours when a message is sent; let P1 (and P2 if the person chooses) override them; hold the other messages and send them when the quiet hours end; a "My notifications" screen; the same settings in the application's notification step for admins; tests with a fixed clock and time zones.

**Size:** S to M. **Needs:** nothing. **Look again when:** responders say they get messages at the wrong time. Note: Keigan does not page (decision of 2026-11-21), so quiet hours matter only for email and Teams.

## 2. Acknowledge and approve actions on Teams cards

**What exists.** The preliminary-report card posted to an incident's Teams chat has three buttons that rate the analysis (D2, built 2026-11-24).

**What is missing.** "Acknowledge" (a person says they are looking at it), "Assign to me", "Ask Keigan about this", and "Approve this step" for a suggested fix. Because Keigan does not execute fixes (E2 is parked), an approve button would only record that a person agreed; it must not look like it ran anything.

**A link to a bigger gain.** An acknowledgement timestamp is also what Keigan needs to compute time to acknowledge (MTTA), which the metrics page cannot show today because no timestamp exists. The second research document ranks this high (its item C-10). Build the timestamp and the buttons together, and add the same action as a web button.

**Size:** M. **Needs:** nothing to build and test with the simulated Teams; a real Teams tenant to confirm the cards render. **Look again when:** the metrics page is used and MTTA is asked for.

## 3. Multi-hop alert grouping

**What exists.** Alerts are grouped when their services are directly connected (one hop in the declared dependencies), and each group says why.

**What is missing.** Grouping an alert on service A with one on service C when A depends on B and B on C. A database fault often shows up two or three services away.

**Risk.** More hops means more chances to join unrelated alerts. It needs a hop limit as a setting, a time window, and a way to see and undo a grouping.

**Size:** S to M. **Needs:** nothing. **Look again when:** the real alert flow shows groups that should have been one.

## 4. Composite SLOs and SLOs as code

- **Composite SLO.** One figure for a user journey that depends on several services (for example "log in" depends on three services). Needs a rule for combining the parts (the weakest, a weighted mix) and a way to show which part is hurting.
- **SLOs as code.** Define SLOs in a file kept in git and apply them, instead of only in the screens. Needs a file format, validation and a safe way to apply it (preview, then apply, with an audit row).

**Size:** M each. **Needs:** nothing. **Look again when:** a team asks for a journey-level figure, or wants SLOs reviewed in pull requests.

## 5. Alert quality scoring (only if it proves worth it)

**What it is.** A score for each alert rule that says whether the rule is useful: how often it fires, how often it is grouped away or muted, how often anyone acts on it, how often it flaps. It would list "rules needing tuning" with a suggested change (a higher threshold, a longer window).

**Why later, and "only if worth it".** It was never built (checked: nothing in the code). All the facts it needs are already stored by the nine-stage noise pipeline, so it is a new calculation, an API and one list, with no new data collection. But its value depends on how noisy the real alert flow is, which only real traffic shows. Build it when the noise report shows that a few rules produce most of the noise.

**Size:** S to M. **Needs:** nothing to build; real alert history to judge whether it is worth it. **Look again when:** the weekly noise report keeps showing the same noisy rules.

---

## 6. Other items still open from the market studies

| Item | Why it waits | Size | Needs |
|---|---|---|---|
| Evaluation harness (A1) | Needs a real model; the plan is `37_REAL_MODEL_TEST_PLAN.md` | M | A real model, another machine |
| Fix scoring (E1 phase 5) | Waits for the harness | S to M | The harness |
| Semantic retrieval for similar incidents (B1 phase 6) | Only if real labelled pairs show misses from different wording | M | 30 real labelled pairs |
| Code and pipeline changes (GitHub, Azure DevOps) | Parked by decision of 2026-11-21: no access yet | L | Read access |
| Executing fixes (E2) | Parked by decision: Keigan only suggests | L | Compliance decision, measured accuracy |
| Browser verification and component tests | Deferred to spec 35 | M | A browser, memory |
| Evidence re-run button | Owner decision | S | Decision |
| MCP server (D3) | Not needed: the team is the only consumer | M to L | A consumer |
| On-call, paging, status page | Not now (decision of 2026-11-21) | L | A request, then integrate first |

The new gaps found on 2026-11-24 are in `38_COMPETITOR_AND_GAP_RESEARCH.md`, with the research agent's own ranking. Its first ten are not repeated here; the owner decides which become specs.
