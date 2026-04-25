# Corvin V2.5 — Scope and Capabilities

## What Is V2.5?

V2.5 is the **AI Intelligence** release. It builds on the operational foundation of V2
and adds features that make Corvin genuinely "smart" — able to learn from history,
brief the team proactively, and communicate its own confidence levels.

---

## V2.5 Focus Areas

1. **Incident Memory & Pattern Recognition** — Corvin queries its own Postgres history to surface similar past incidents in every new RCA.
2. **SRE Morning Briefing (Jarvis Mode)** — A scheduled Teams post every morning summarising overnight incidents, cluster health, and predicted risk areas.
3. **Confidence Meter** — The `confidence` field from RCAOutput is surfaced visually in the React UI as a glowing colour-coded ring (green = high, amber = medium, red = low).

---

## V2.5 Required Capabilities

- A `MemoryService` that queries `investigations` table for semantically similar past incidents.
- A `BriefingService` that aggregates overnight data and formats a structured Teams card.
- A scheduler (APScheduler or Azure Function Timer) that triggers the briefing at 09:00 local time daily.
- Frontend confidence ring component wired to the `confidence` field in the investigation response.

---

## V2.5 Testable Slices

- Slice 1: MemoryService — query past incidents, return top-3 similar matches with similarity score
- Slice 2: "Similar Past Incidents" section injected into RCA output
- Slice 3: BriefingService — aggregate overnight data, format Teams Adaptive Card
- Slice 4: Scheduler daemon — daily trigger at 09:00, manual `corvin› brief` CLI trigger
- Slice 5: Confidence Meter ring component in React UI

---

## V2.5 Exit Criteria

- [ ] Every new RCA card includes a "Similar Past Incidents" section if ≥1 match found.
- [ ] A Morning Briefing card appears in Teams automatically each morning.
- [ ] `corvin› brief` CLI command triggers a briefing on demand.
- [ ] Confidence meter ring is visible in the React investigation detail page.
- [ ] V2 capabilities remain fully stable.

---

## V2.5 Still Excludes

- Premium UI overhaul — this is V3.
- Blameless Post-Mortem generator — this is V3.
- Corvin Score / SRE health dashboard — this is V3.
