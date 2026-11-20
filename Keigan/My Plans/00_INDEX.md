# 慧眼 Keigan — Plan Index

> *The discerning eye for our systems.*
> AI SRE platform for MetLife: incident root cause analysis, alert noise reduction, SLO monitoring,
> predictive intelligence and bilingual (English / Japanese) incident communications.

This folder is the single source of truth for everyone (humans and AI agents) building Keigan.
Read the documents in order the first time. When the code and a plan disagree, fix the code or
record the decision in `09_LEARNINGS_LOG.md`, never silently diverge.

| # | Document | What it decides |
|---|---|---|
| 01 | [Product specification](01_PRODUCT_SPECIFICATION.md) | Every feature, screen and behaviour. The "what". |
| 02 | [System architecture](02_SYSTEM_ARCHITECTURE.md) | Components, Python project structure (Java-style layering), integrations, workers, configuration, capacity. |
| 03 | [Database design](03_DATABASE_DESIGN.md) | Static schema: every table and column with descriptive names. |
| 04 | [UI / UX design system](04_UI_UX_DESIGN_SYSTEM.md) | MetLife colours, fonts, type scale, spacing, components, motion, page layouts. |
| 05 | [API contract](05_API_CONTRACT.md) | REST endpoints, conventions, error format. |
| 06 | [AI engine and prompt safety](06_AI_ENGINE_AND_PROMPT_SAFETY.md) | Investigation graph, prompts, PII masking, prompt-injection defences, token strategy. |
| 07 | [Build phases and agents](07_BUILD_PHASES_AND_AGENTS.md) | Phases, ownership of files per agent, status tracker. |
| 08 | [RAG proposal](08_RAG_PROPOSAL.md) | Future retrieval-augmented knowledge base, once a vector store is provisioned. |
| 09 | [Learnings log](09_LEARNINGS_LOG.md) | Decisions, deviations and gotchas discovered while building. Append-only. |
| 10 | [Deployment on AKS](10_DEPLOYMENT_AKS.md) | Containers, namespaces, workload identity, ingress, secrets. |
| 11 | [Backend foundation guide](11_BACKEND_FOUNDATION_GUIDE.md) | How to use the shared backend code: DI, RBAC, repositories, jobs, LLM gateway, telemetry, simulation, seed. |
| 12 | [Feature tracker](12_FEATURE_TRACKER.md) | Every feature with its status (done, built, in progress, not started) and the completion rate. |
| 13 | [Sequence diagrams](13_SEQUENCE_DIAGRAMS.md) | Sign-in and access, application groups, onboarding, incident → RCA, alerts, Teams postmortem, AI chat, scheduled work. |
| 14 | [Class diagrams](14_CLASS_DIAGRAM.md) | Layers and the main classes: access, investigations, integrations, background jobs. |
| 15 | [Entity relationship diagram](15_ENTITY_RELATIONSHIP_DIAGRAM.md) | All 47 tables by domain, generated from the entities. |
| 16 | [Hardening plan](16_HARDENING_PLAN.md) | Review findings, agreed decisions (APIM, incremental schema, tests), and the status of every fix. |
| 17 | [Security and prompt review](17_SECURITY_AND_PROMPT_REVIEW.md) | Independent review: verified findings with proofs, prompt-quality notes, what was not checked. |
| 19 | [Hardening wave summary](19_HARDENING_WAVE_SUMMARY.md) | Plain tables of what waves 1 and 2 changed, the real cause of each fix, and how it was proven. |
| 20 | [Application team members: design](20_TEAM_MEMBERS_DESIGN.md) | Roles, invitations, statuses and the rules behind them, with the calls made and why. |

Database scripts for Azure SQL (run before the first deployment): [`database/azure_sql/`](../database/azure_sql/README.md).

## Ground rules for every contributor

1. **Descriptive names everywhere.** Tables, columns, variables, functions: no abbreviations
   (`incident_identifier`, not `inc_id`; `investigation_window_start`, not `win_st`). Accepted exceptions:
   industry acronyms that are clearer than their expansion: `slo`, `sli`, `kql`, `pii`, `llm`, `url`, `id`, `ai`, `api`, `aks`.
2. **Lean code.** One designated service class per business capability; shared helpers live in `utils`.
   No speculative abstractions; no copy-paste between services.
3. **Configurable.** Every endpoint, model name, interval, threshold and feature flag comes from
   environment configuration (`backend/.env`) or a catalogue file in `backend/keigan/resources`.
4. **Provider-neutral AI.** Nothing outside `keigan/ai/llm_gateway.py` may import a vendor SDK.
5. **Security first.** Secrets never in the database or the browser; PII masked before storage and before any
   AI call; every AI input from outside Keigan is treated as untrusted data; RBAC checked server-side.
6. **Keigan suggests, humans act.** Keigan never executes a fix, never edits alert rules, never changes
   customer infrastructure. It reads, reasons and recommends.
7. **Localised UI.** No user-visible string is hard-coded in a component. Every label lives in
   `frontend/src/i18n/locales/<locale>/<namespace>.json`.
8. **Tests guard every change (from 2026-11-20).** Backend changes need passing pytest tests (`backend/tests`);
   a smoke run (backend boots, frontend builds, seeded demo works, `capture-screens.mjs` clean) is still mandatory
   before a phase is called done. Frontend test suites come later. See `16_HARDENING_PLAN.md`.

## Naming

- Product name is **Keigan** (慧眼). "Corvin" in older material refers to the same product; never use it in code or UI.
- Python package: `keigan`. Frontend package: `keigan-web`.
