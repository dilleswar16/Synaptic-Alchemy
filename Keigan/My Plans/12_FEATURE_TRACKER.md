# 12 — Feature tracker

Every feature from `01_PRODUCT_SPECIFICATION.md`, with its real status. Updated by the lead after each build agent reports and after each integration test.
**Last updated:** 2026-11-20 — Azure SQL scripts, identity auto-discovery, "Check in Entra" for access groups, sequence / class / ER diagrams.

## Summary

| | Count | Share |
|---|---|---|
| ✅ Done and verified | 92 | 88 % |
| 🟡 Built; needs your environment to verify (tenant, keys, live systems) | 9 | 9 % |
| 🧩 Placeholder by design (configuration saved, reader later) | 2 | 2 % |
| 🔄 Being built right now | 0 | 0 % |
| ⬜ Not started | 2 | 2 % |
| **Total features** | **105** | **98 % built · 88 % verified** |

**Legend**
- ✅ **Done and verified** in the local simulated environment: API tested end to end, and the screen loads in a real browser (headless Edge) with live data and no console or API errors. Mock AI unless stated.
- 🟡 **Built; needs your environment:** code complete, but verifying it needs something this machine doesn't have — a real Entra tenant, a Gemini/OpenAI key, live Azure / ServiceNow / Teams / log tools, Docker or Helm.
- 🧩 **Placeholder by design:** what the spec asked for — configuration captured, reader shown honestly as "in development".
- 🔄 **In progress:** an agent is working on it now.
- ⬜ **Not started.**

**How verification was done:** `frontend/scripts/capture-screens.mjs` signs in, opens all 22 screens in headless Edge and fails on any console error, page error or failed API call (22/22 clean). Home, investigation, onboarding, alerts, SLO and intelligence screens were also reviewed visually. The end-to-end flow was run through the API (see §O).

---

## A. Platform foundation

| # | Feature | Status | Notes |
|---|---|---|---|
| A1 | Plans and design documents (`My Plans/`) | ✅ | 13 documents + agent briefs |
| A2 | Static database schema (40+ tables, descriptive names) | ✅ | |
| A3 | Configuration from `.env` | ✅ | |
| A4 | Local sign-in with dummy users | ✅ | |
| A5 | Microsoft Entra sign-in (MSAL, token validation, group overage) | 🟡 | Needs a real tenant |
| A6 | RBAC: Keigan admin / `<APP>_admin` / `<APP>_reader` | ✅ | Readers get 403 on writes; no-access users see nothing |
| A7 | Provider-neutral AI (Gemini, Azure OpenAI, OpenAI-compatible, mock) | 🟡 | Mock verified everywhere; needs your Gemini key for a real run |
| A8 | Prompt-injection defences | ✅ | The seeded ticket contains an injection attempt; it is flagged |
| A9 | PII and secret masking | ✅ | |
| A10 | Validation of AI-generated KQL / Elastic / SPL | ✅ | |
| A11 | Background jobs, retries, schedulers | ✅ | 35 jobs in the demo run, 0 dead-lettered |
| A12 | Simulated world (8 scenarios, telemetry, ServiceNow) | ✅ | Low-volume realism fixed in integration |
| A13 | Token budgets and usage accounting | ✅ | |
| A14 | Audit trail | ✅ | |

## B. Frontend foundation and design

| # | Feature | Status | Notes |
|---|---|---|---|
| B1 | MetLife colours, fonts, type scale, light and dark themes | ✅ | Dark pass: 22/22 screens clean |
| B2 | UI component kit (≈ 50 components) | ✅ | |
| B3 | App shell: sidebar, top bar, scope switcher, ⌘K palette | ✅ | |
| B4 | Charts and topology graph | ✅ | SLO heatmap now judged against each SLO's own target |
| B5 | Sign-in page and "no access" state | 🟡 | Sign-in is bypassed by the screenshot script; check by hand |
| B6 | Design-system showcase page | ✅ | |

## C. Home — SRE command centre

| # | Feature | Status | Notes |
|---|---|---|---|
| C1 | Greeting and KPI tiles | ✅ | Reviewed visually |
| C2 | Application health grid | ✅ | |
| C3 | Live incidents and intelligence feed | ✅ | |
| C4 | Ask Keigan card | ✅ | Submits into Keigan AI chat |

## D. Applications and onboarding

| # | Feature | Status | Notes |
|---|---|---|---|
| D1 | Applications page; onboard or request onboarding | ✅ | |
| D2 | Readiness checklist and go-live | ✅ | |
| D3 | Azure resource group: role commands, verify, discover | ✅ | Simulated Azure; live Azure is a config switch. Keigan's tenant / client / object ID are read from its own token in AKS (no manual IDs); warning banner if any is missing |
| D4 | Hardware, mainframe and SaaS components | ✅ | |
| D5 | Services table, log sources, dependencies | ✅ | |
| D6 | Resource explorer drawer | 🟡 | Page verified; drawer not opened in the walkthrough |
| D7 | Elastic, Splunk, Datadog connections and test | 🟡 | Needs live endpoints |
| D8 | SolarWinds, IBM Z, vendor API readers | 🧩 | Spec: placeholders |
| D9 | Knowledge upload, AI digest, chunking | ✅ | |
| D10 | Copilot knowledge-capture prompt | ✅ | |
| D11 | CMDB and EI portal integrations | 🧩 | Spec: placeholders |
| D12 | AI-built topology and stakeholder review | ✅ | |
| D13 | Runbooks | ✅ | |
| D14 | ServiceNow assignment groups | ✅ | |
| D15 | Alert sources and noise policy step | ✅ | HTML nesting bug fixed |
| D16 | SLO proposals step | ✅ | |
| D17 | Notifications step (stakeholders, service checkboxes) | ✅ | |
| D18 | Access step (AD group names for SailPoint) | ✅ | "Check in Entra" confirms both groups, shows member counts, saves object IDs. Verified with local users; Entra path needs `GroupMember.Read.All` on Keigan's identity |

## E. Incidents and investigations (RCA)

| # | Feature | Status | Notes |
|---|---|---|---|
| E1 | ServiceNow polling | ✅ | Simulated ServiceNow |
| E2 | Priority triage P1–P4 | ✅ | |
| E3 | Evidence collection | ✅ | 27 evidence items, 12 strong, on the demo incident |
| E4 | Three hypotheses with fixes | ✅ | |
| E5 | RCA: what / why / how, with citations | ✅ | Reviewed visually |
| E6 | Runbook matching | ✅ | Re-ranked on error signatures (integration fix) |
| E7 | Blast radius | ✅ | |
| E8 | Evidence-only mode | ✅ | |
| E9 | Incident room | ✅ | |
| E10 | Investigation page with live progress | ✅ | Header layout and code-block copy button fixed |
| E11 | Manual investigation, re-run, feedback | ✅ | |
| E12 | Investigation chat | ✅ | "What changed?" now answers from the activity log |

## F. Communications and postmortems

| # | Feature | Status | Notes |
|---|---|---|---|
| F1 | English and Japanese drafts | ✅ | |
| F2 | Edit and approve | ✅ | |
| F3 | Send by email / Teams | ✅ | Simulated email (outbox) |
| F4 | Blameless postmortem generation | ✅ | |
| F5 | Postmortem emailed to stakeholders | ✅ | Simulated email |
| F6 | Branded email templates (EN / JA) | ✅ | |

## G. Microsoft Teams

| # | Feature | Status | Notes |
|---|---|---|---|
| G1 | Incident group chat with subscribed stakeholders | ✅ | Simulated Teams; Japanese welcome for the JP app |
| G2 | Keigan bot answers questions | ✅ | |
| G3 | Chat read on a schedule; facts added to the timeline | ✅ | |
| G4 | "Keigan, this is finished" → postmortem | ✅ | |
| G5 | Teams room panel (simulated mirror) | ✅ | Duplicate report post fixed |
| G6 | Teams app manifest | 🟡 | Needs upload in your Teams admin center |

## H. Alerts and noise reduction

| # | Feature | Status | Notes |
|---|---|---|---|
| H1 | Webhook intake | ✅ | |
| H2 | Azure Monitor, Elastic, generic mapping | ✅ | |
| H3 | 9-stage pipeline with reasons | ✅ | Group resolution bug fixed |
| H4 | Observe and Active modes | ✅ | |
| H5 | Maintenance windows and mute rules | ✅ | |
| H6 | Policy preview funnel | ✅ | |
| H7 | Alert group → investigation → ServiceNow incident | ✅ | Alerts-before-ticket race fixed |
| H8 | Alerts page | ✅ | 134 alerts → 6 groups in the demo; funnel consistency fixed |
| H9 | Weekly noise report | ✅ | API only |

## I. SLO monitoring

| # | Feature | Status | Notes |
|---|---|---|---|
| I1 | SLI catalogue | ✅ | |
| I2 | Proposals with measured targets | ✅ | |
| I3 | Backfill and 5-minute collection | ✅ | |
| I4 | Multi-window burn-rate alerts | ✅ | |
| I5 | SLO dashboard and detail charts | ✅ | Reviewed visually |
| I6 | Ecosystem heatmap | ✅ | |

## J. Predictive intelligence

| # | Feature | Status | Notes |
|---|---|---|---|
| J1 | Detectors | ✅ | Memory leak, latency creep, budget burn, recurring incidents found |
| J2 | Signals feed with actions | ✅ | Reviewed visually |
| J3 | Keigan Intelligence Report | ✅ | |
| J4 | Health score trend | ✅ | |

## K. Keigan AI chat

| # | Feature | Status | Notes |
|---|---|---|---|
| K1 | Knowledge questions with citations | ✅ | |
| K2 | Question → query → number | ✅ | |
| K3 | Pattern → chart, with clarification | ✅ | |
| K4 | Conversation history | ✅ | |

## L. Administration

| # | Feature | Status | Notes |
|---|---|---|---|
| L1 | Platform settings, identity, connection tests | ✅ | |
| L2 | Usage, audit log, job queue | ✅ | |
| L3 | Outbox | ✅ | |
| L4 | Simulation controls | ✅ | |

## M. Localisation

| # | Feature | Status | Notes |
|---|---|---|---|
| M1 | English | ✅ | |
| M2 | Japanese, Chinese, Spanish (+ Mexico), Dutch, French | ✅ | 15 namespaces × 5 languages, zero missing keys; es-MX falls back to es. Native-speaker review suggested for a few terms (see learnings log) |
| M3 | Bilingual emails and Teams cards (EN / JA) | ✅ | |

## N. Deployment and hardening

| # | Feature | Status | Notes |
|---|---|---|---|
| N1 | Dockerfiles and nginx with strict security headers | 🟡 | Docker not installed here |
| N2 | Helm chart | 🟡 | Helm not installed here |
| N3 | Database migrations (Alembic) | ✅ | 47 tables, no drift; schema-aware (`keigan`); Helm pre-upgrade job (can be switched off). Upgrade/downgrade verified on SQLite; SQL Server output rendered offline |
| N8 | Azure SQL DDL scripts (`database/azure_sql/`) | 🟡 | Generated from the entities: schema, 47 tables, 32 foreign keys, 62 indexes, migration baseline, managed-identity grants. All batches pass a T-SQL parser and fit SQL Server key limits; needs a real Azure SQL database to run |
| N9 | Sequence, class and ER diagrams | ✅ | `13_SEQUENCE_DIAGRAMS.md`, `14_CLASS_DIAGRAM.md`, `15_ENTITY_RELATIONSHIP_DIAGRAM.md` (generated); all 21 diagrams render with Mermaid 11 |
| N4 | Automated test suites | ⬜ | Deferred, as you asked |
| N5 | RAG proposal | ✅ | `08_RAG_PROPOSAL.md` |
| N6 | End-to-end run with a real Gemini key | ⬜ | Needs your key |
| N7 | Browser walkthrough of every screen | ✅ | 22/22 screens, light and dark |

## O. End-to-end demo (verified 2026-11-20)

Simulated "SQL connection pool exhaustion" on Claims Processing (JP):
alerts fire 12 min before the ticket → noise reduction groups them → investigation starts from the alert group → ServiceNow ticket arrives and adopts that investigation →
Teams room opens with a Japanese welcome and the RCA → "Keigan, what changed in the last hour?" → Keigan names the `BATCH_IMPORT_PARALLELISM` 4 → 16 change [E7] →
"Keigan, this is finished" → blameless postmortem drafted → emails and chat posts in the outbox.

## What's next

1. Done today: UI polish (card padding on 11 screens, Applications cards redesigned, incident table fits, Ask Keigan contrast, translated component labels on Home).
2. You: put a Gemini key in `backend/.env` (`LLM_PROVIDER=gemini`, `LLM_API_KEY=…`) and run the demo for real AI analysis (N6).
3. Before Azure: follow `10_DEPLOYMENT_AKS.md` §8 — managed identity + `GroupMember.Read.All`, run `database/azure_sql/run_all.sql` (N8), Docker/Helm build on a machine that has them (N1, N2), Entra app registrations (A5), Teams app upload (G6).
