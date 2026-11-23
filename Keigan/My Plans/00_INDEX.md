# 慧眼 Keigan — Plan Index

> *The discerning eye for our systems.*
> AI SRE platform for MetLife: incident root cause analysis, alert noise reduction, SLO monitoring,
> predictive intelligence and bilingual (English / Japanese) incident communications.

This folder is the single source of truth for everyone (humans and AI agents) building Keigan.
Read the status page first, then the documents you need. When the code and a plan disagree, fix the code or
record the decision in `build-history/09_LEARNINGS_LOG.md`, never silently diverge.

**Start with [`00_STATUS_AND_ROADMAP.md`](00_STATUS_AND_ROADMAP.md):** where we are, what is built, designed, parked, and what to build next and when.

Documents keep their numbers, so "doc 06" always means the same file. They are grouped in folders by area, and every feature has its own folder under `features/`.

### product/: what we build and why
| # | Document | What it decides |
|---|---|---|
| 01 | [Product specification](product/01_PRODUCT_SPECIFICATION.md) | Every feature, screen and behaviour. The "what". |
| 12 | [Feature tracker](product/12_FEATURE_TRACKER.md) | Every feature with its status (done, built, in progress, not started) and the completion rate. |
| 21 | [Product research](product/21_PRODUCT_RESEARCH.md) | Our own ideas, then a sourced market study (AI SRE and incident tools, SLO practice, evidence on accuracy and trust) and the ranked roadmap (waves A to E). Redo around May 2027. |

### architecture/: how it is built and run
| # | Document | What it decides |
|---|---|---|
| 02 | [System architecture](architecture/02_SYSTEM_ARCHITECTURE.md) | Components, Python project structure (Java-style layering), integrations, workers, configuration, capacity. |
| 03 | [Database design](architecture/03_DATABASE_DESIGN.md) | Static schema: every table and column with descriptive names. |
| 05 | [API contract](architecture/05_API_CONTRACT.md) | REST endpoints, conventions, error format. |
| 10 | [Deployment on AKS](architecture/10_DEPLOYMENT_AKS.md) | Containers, namespaces, workload identity, ingress, secrets. |
| 11 | [Backend foundation guide](architecture/11_BACKEND_FOUNDATION_GUIDE.md) | How to use the shared backend code: DI, RBAC, repositories, jobs, LLM gateway, telemetry, simulation, seed. |
| 13 | [Sequence diagrams](architecture/13_SEQUENCE_DIAGRAMS.md) | Sign-in and access, application groups, onboarding, incident to RCA, alerts, Teams postmortem, AI chat, scheduled work. |
| 14 | [Class diagrams](architecture/14_CLASS_DIAGRAM.md) | Layers and the main classes: access, investigations, integrations, background jobs. |
| 15 | [Entity relationship diagram](architecture/15_ENTITY_RELATIONSHIP_DIAGRAM.md) | All tables by domain, generated from the entities (`backend/scripts/generate_entity_relationship_diagram.py`). |

### ui-ux/ and ai-engine/
| # | Document | What it decides |
|---|---|---|
| 04 | [UI / UX design system](ui-ux/04_UI_UX_DESIGN_SYSTEM.md) | MetLife colours, fonts, type scale, spacing, components, motion, page layouts. |
| 06 | [AI engine and prompt safety](ai-engine/06_AI_ENGINE_AND_PROMPT_SAFETY.md) | Investigation graph, prompts, PII masking, prompt-injection defences, token strategy. |

### features/: one folder per feature
| # | Document | State |
|---|---|---|
| 20 | [Application team members](features/team-members/20_TEAM_MEMBERS_DESIGN.md) | Built. Roles, invitations, statuses and the rules behind them. |
| 24 | [Reliability metrics](features/reliability-metrics/24_RELIABILITY_METRICS.md) | Built (roadmap A4). Definitions, settings, what is not available. |
| 25 | [Application operating notes](features/application-operating-notes/25_APPLICATION_OPERATING_NOTES.md) | Built (roadmap B2). Guidance per application for the AI, never evidence. |
| 26 | [Alert grouping reason](features/alert-grouping-reason/26_ALERT_GROUPING_REASON.md) | Built (roadmap B3). The "why were these alerts grouped" sentence. |
| 23 | [Ask Keigan chat: design and spec](features/ask-keigan-chat/23_ASK_KEIGAN_CHAT_SPEC.md) | Designed, not built (roadmap B5). One chat with every read-only tool and a visible tool-call view; owner decisions D1 to D6 recorded. |
| 22 | [AI evaluation harness: design and spec](features/ai-evaluation-harness/22_AI_EVALUATION_HARNESS_SPEC.md) | Designed, deferred by decision (roadmap A1). |
| 37 | [Real-model test plan](features/ai-evaluation-harness/37_REAL_MODEL_TEST_PLAN.md) | Written, not run. A self-contained checklist with acceptance criteria and the agent prompt, for the first real-model results on another machine. |
| 08 | [RAG proposal](features/semantic-retrieval/08_RAG_PROPOSAL.md) | Future retrieval-augmented knowledge base, once a vector store is provisioned. |

### quality-and-security/
| # | Document | What it decides |
|---|---|---|
| 16 | [Hardening plan](quality-and-security/16_HARDENING_PLAN.md) | Review findings, agreed decisions (APIM, incremental schema, tests), and the status of every fix. |
| 17 | [Security and prompt review](quality-and-security/17_SECURITY_AND_PROMPT_REVIEW.md) | Independent review: verified findings with proofs, prompt-quality notes, what was not checked. |
| 19 | [Hardening wave summary](quality-and-security/19_HARDENING_WAVE_SUMMARY.md) | Plain tables of what waves 1 and 2 changed, the real cause of each fix, and how it was proven. |

### build-history/
| # | Document | What it decides |
|---|---|---|
| 07 | [Build phases and agents](build-history/07_BUILD_PHASES_AND_AGENTS.md) | Phases, ownership of files per agent, status tracker. Agent briefs are in `build-history/agent-briefs/`. |
| 09 | [Learnings log](build-history/09_LEARNINGS_LOG.md) | Decisions, deviations and gotchas discovered while building. Append-only. |

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
6. **Keigan suggests, humans act.** Keigan does not execute a fix, edit alert rules or change customer
   infrastructure. It reads, reasons and recommends. Execution is parked, not removed (roadmap E2); it needs an explicit decision first.
7. **Localised UI.** No user-visible string is hard-coded in a component. Every label lives in
   `frontend/src/i18n/locales/<locale>/<namespace>.json`.
8. **Tests guard every change (from 2026-11-20).** Backend changes need passing pytest tests (`backend/tests`);
   a smoke run (backend boots, frontend builds, seeded demo works, `capture-screens.mjs` clean) is still mandatory
   before a phase is called done. Frontend test suites come later. See `quality-and-security/16_HARDENING_PLAN.md`.

## Naming

- Product name is **Keigan** (慧眼). "Corvin" in older material refers to the same product; never use it in code or UI.
- Python package: `keigan`. Frontend package: `keigan-web`.
