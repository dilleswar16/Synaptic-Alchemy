# 21 — Product research: what comparable products do, and what is worth adding to Keigan

**Date:** 2026-11-21. **Purpose:** one thorough pass, so nobody repeats this research. Part 1 is the team's own ideas, written *before* any research so the two can be compared honestly. Part 2 is the market, from each vendor's own documentation and announcements. Part 3 compares them and ranks what to build. Part 4 lists open questions and what could not be verified.

Keigan today (see `12_FEATURE_TRACKER.md`): a fixed investigation pipeline (triage → context → evidence → three hypotheses → RCA → blast radius → communications), a nine-stage alert noise pipeline, SLO monitoring with burn-rate alerts, predictive signals, a ServiceNow incident link, Teams incident chats with a bot, postmortems, runbooks, a knowledge base, an application team with invitations, and a read-only stance on customer systems (access comes from AD groups; Keigan never grants access).

---

## Part 1 — Our own ideas, before researching

Written from knowing the product and from general SRE practice. Each idea has a short reason. None of these has been checked against the market yet.

### A. Make the investigation smarter
1. **Change correlation.** "What changed just before this started?" across deployments, config changes, feature flags, infrastructure changes, certificate expiry. Most incidents are caused by a change. *(Correction after checking the code, see 3.2: Keigan already reads the Azure Activity Log as change evidence. What is missing is code, pipeline and feature-flag changes.)*
2. **Similar past incidents.** Find earlier incidents and their confirmed root causes and show them first. The RAG proposal (`08`) exists; the question is how far to take it. *(Partly exists: the last three confirmed investigations of the same application are added to the prompt.)*
3. **Suspect code.** Link a regression to the commit, pull request or release that likely introduced it.
4. **Confidence and evidence honesty.** Say how sure the analysis is, what it could not check, and what would change its mind.
5. **A feedback loop with a score.** Engineers already give a verdict on an investigation. Use it to measure accuracy over time, and as a regression test set whenever a prompt or model changes. *(Verdicts are stored and partly used; nothing measures accuracy yet.)*
6. **More signal types.** Traces, Kubernetes events, database wait statistics, cloud service-health notices, dependency provider status pages.

### B. From diagnosis to action
7. **Suggested remediation with approval.** Today Keigan suggests; it never acts. A governed path: propose an action, show the risk and blast radius (the command risk classifier exists), require approval, run through an existing pipeline or runbook automation, log everything.
8. **Rollback and mitigation suggestions** tied to the suspected change.
9. **Runbook quality.** Which runbooks helped, which are stale, which incidents had no runbook.

### C. Running the incident
10. **On-call and escalation** (who is on call, who gets paged, what happens if they do not answer). Today Keigan notifies by email and Teams.
11. **Incident roles and a live status.** Incident commander, scribe, current status, next update due.
12. **Status updates for stakeholders and a status page** (internal first).
13. **Teams actions on cards** (acknowledge, assign, ask Keigan, approve a step) so responders stay in one place.

### D. Less noise
14. **Cross-source correlation** using the topology (one database problem, forty alerts).
15. **Alert quality scoring** (which rules are noisy or never actionable) and suggested tuning.
16. **Flapping and seasonality detection.**

### E. Learning from incidents
17. **Postmortem action items tracked to done**, with owners and due dates, reminders, and a view of what repeats.
18. **Error-budget policy** that does something (freeze reminders, review triggers).
19. **Readiness reviews and game days** for an application before go-live.

### F. Service catalog and ownership
20. **Ownership health** (no lead, no on-call, stale runbook, no SLO) shown as a score per application.
21. **Dependency map from real traffic** rather than only declared dependencies.

### G. Reporting
22. **MTTD, MTTA, MTTR and incident counts** by application and period, with the AI's share of the work.
23. **A weekly executive digest.**
24. **AI cost and quality dashboard** (tokens, failures, accuracy).

### H. Platform
25. **Integrations out:** Jira or ServiceNow tasks, GitHub or Azure DevOps, Slack, PagerDuty.
26. **An API or MCP server** so other tools and agents can ask Keigan.
27. **Enterprise basics:** SSO group mapping, SCIM, audit export, data retention controls, per-application data residency.
28. **Multi-tenant or multi-business-unit** support, if more than one organisation will use it.

### I. Experience
29. **A phone-friendly on-call view.**
30. **Per-person notification preferences and quiet hours.**
31. **Saved views and a personal home.**

---

## Part 2 — What the market does

**How to read this.** Each entry says what the product is, the features worth noticing, and how much to trust the source. Source tags: **[P]** the vendor's own technical documentation, **[V]** vendor marketing or a vendor blog (treat numbers as claims), **[T]** a third party, **[?]** could not be confirmed. Every figure below is the vendor's own unless marked otherwise; no vendor has published an independently audited accuracy rate (see 2.6). URLs are in the source list at the end.

### 2.1 AI incident-investigation products ("AI SRE")

**Azure SRE Agent (Microsoft)** [P] — the closest first-party overlap with Keigan, because Keigan runs on Azure.
- Starts when an alert arrives from PagerDuty, ServiceNow or Azure Monitor. Acknowledges, queries Azure Monitor, Application Insights, Log Analytics and Kusto, checks recent deployments through GitHub or Azure DevOps, checks memory for similar past incidents, tests hypotheses, then proposes or applies a fix and writes a ticket with the full investigation summary.
- **Response plans** choose which incidents it handles. **Run modes** (Review or Autonomous) are set *per response plan and per scheduled task*, not for the whole agent. At agent level Review is the default, but the per-response-plan and per-scheduled-task defaults are Autonomous; Microsoft recommends Review for production and advises starting in Review for two to four weeks and switching only the triggers you always approve. Review mode asks approval only for Azure infrastructure write operations.
- **Tool access policies**: every tool is *allow*, *ask* or *deny*, matched by name patterns including command arguments (for example `az * delete *`). Only the global scope can deny; narrower scopes (one custom agent, one conversation) can only add allows. Order of evaluation: hooks, then policy, then connector approval, then run mode. Overrides are audit-logged.
- Five extension points: skills, custom agents, Python tools, MCP servers (Datadog, Splunk, New Relic, Dynatrace, Elastic or any custom one) and hooks. Scheduled tasks run health checks and compliance sweeps. Memory keeps root causes, resolution steps and escalation preferences across investigations. Investigation Records (preview) store the latest assessment. Network isolation by VNet, managed identity and RBAC, Bicep deployment.
- Generally available since 10 March 2026 (Microsoft Tech Community announcement); some sub-features such as Investigation Records are labelled preview.
- Billing: a fixed 4 Azure Agent Units per agent-hour plus usage-based charges while it works; no free AAUs, though the pricing page advertises a trial [P].

**Azure Copilot Observability Agent (Microsoft)** [P] — the *Azure Monitor* side (formerly "Azure Monitor investigate"), still preview.
- Chat with logs and metrics, **deep investigations** across application, infrastructure and platform signals, saved as **Azure Monitor issues** so context survives handoff.
- **Autonomous operations (preview)**: correlates related alerts in the background into one issue *with a written explanation of why those alerts belong together*, then runs a deep investigation on it. It never restarts or changes anything. Custom instructions (up to 8,192 characters per agent resource) tell it which services are operationally distinct, which carry revenue or regulated traffic, and which alerts always deserve an issue.
- Limits worth noting: English only, a conversation cannot continue past 24 hours, no customer-managed keys, nine regions.

**AWS DevOps Agent** [P] — generally available since 31 March 2026.
- Investigates from an alert or support ticket, builds an application topology automatically, gives **mitigation plans that include how to validate success and how to revert**, analyses historical incidents to recommend preventive improvements, and reviews code changes for production risk before deployment (preview). A triage agent links duplicate tickets. Agent skills encode runbooks. Runs as a remote server others can call over MCP, ACP and A2A. Azure and Azure DevOps are supported built in, on-premises applications through MCP, and billing is per second of agent time [P].
- Claims from preview customers: up to 75% lower MTTR, 80% faster investigations, 94% root-cause accuracy [V; not independently verified].

**Google Gemini Cloud Assist investigations** [P/V] — preview in 2025. Reads logs, asset inventory, App Hub, metrics and errors in parallel, synthesises probable causes, draws on Google support knowledge and runbooks, and can open a support case with the investigation attached. By default Google does not examine investigation inputs or outputs.

**Datadog Bits AI SRE / Bits Investigation** [P] — the best-documented design.
- Hypothesis loop: propose causes, validate or invalidate each with targeted queries, branch into sub-hypotheses, prune; each investigation ends with an evidence-backed conclusion or is marked inconclusive. Shown as a live "Investigation Steps" view and a finished "Hypothesis Tree".
- Starts automatically when a monitor enters the alert state, from a Slack mention (the whole thread becomes context; default look-back four hours), from Error Tracking, or through MCP, API and CLI. Reads metrics, traces, logs, dashboards, change tracking, source code (GitHub), Watchdog, RUM, database monitoring and profiler; third-party sources in preview (Grafana, Dynatrace, Sentry, Splunk, ServiceNow, Confluence). Teams support is in preview.
- Reports tab: investigations over time by monitor, user, service and team, and **mean time to conclusion**.
- **Lessons Datadog published** [V]: an early version summarised all telemetry at once and was distracted by noisy upstream errors; investigating *per hypothesis* with only the telemetry for that causal link fixed it. Evaluation uses real incidents labelled by responders, replayed from archived telemetry, scored by an LLM judge calibrated against human judgement. Cost per investigation fell from about $25 (11 minutes, December 2025) to about $6.50 after moving from a phase-based pipeline to a ReAct loop, and to about $4 (about 2 minutes, October 2026) after model routing and running code through the MCP server to pre-process data; training a specialised model (Scout) is described as future work. Quality score +44% against the March 2026 release on Datadog's internal benchmark [V].
- Pricing: Datadog earlier priced per investigation and has moved to shared AI credits [T]; its own cost figure is about $4 of cost per investigation [V].

**Grafana Assistant Investigations** [P/V] — generally available July 2026. Background agent that finds and validates problems across metrics, logs, traces and profiles, correlated with code; started by Alerting or Cloud IRM, scheduled automations, Slack, a hosted MCP server or a CLI. Outputs reports, and GitHub issues, PRs or branches. Described as "human on the loop"; colleagues can steer a running investigation and add context. Grafana's own comparison from one incident: 8 minutes against 28 for the on-call engineer [V, single case, from a November 2025 post about its earlier assistant, not about Investigations].

**Dynatrace Davis / Dynatrace Intelligence** [P/V] — deterministic causal analysis over the Smartscape dependency graph, correlating code, deployment, configuration and policy changes, mapping impact across dependencies, and recommending actions. Agentic workflows that propose or run approved actions under policy are in preview. Architecture stance: *deterministic causal engine first, LLM agents inside its boundaries* [T, TechTarget].

**New Relic SRE Agent, now "Autopilot"** [V] — launched February 2026, renamed June 2026. Combines deterministic analysis with topology-graph causal ranking, an interactive canvas of causal chains, blast radius and evidence, duplicate-incident detection, real-time user-impact measurement, post-incident reports, and Kubernetes and Kafka specialists. Suggests rollbacks but expects engineer review.

**Splunk AI Troubleshooting Agent and ITSI** [V/T] — suspected root causes with supporting logs and exemplar traces; Event iQ alert correlation; episode summarisation; a remediation plan; an MCP server (generally available; date unconfirmed). Availability statements conflict between sources, so treat as unverified.

**Elastic Agent Builder RCA** [V] — a September 2026 build-it-yourself tutorial, not a shipped feature. Notable for *verifiability*: the report names the tool behind every number and a trace id or document id behind every claim, hypotheses carry a status (investigating, dismissed, confirmed) and the report lists gaps found.

**PagerDuty (SRE Agent "Paige", Scribe, Insights, Shift)** [V] — a virtual responder inside the escalation policy that narrates each step in the incident channel. *Deep Investigation* (preview) tests several causes at once, ranks by confidence and **shows what was ruled out and why**. Shared memory: each resolution and human correction is written back. Runs existing runbooks with approval; autonomous resolution for well-understood incidents is "coming soon". Scribe transcribes Zoom or Google Meet calls and combines them with Slack or Teams chat into summaries and status updates. Needs ownership mapping, escalation policies and runbooks to work well.

**incident.io (AI SRE / Investigations)** [V] — finds the change likely responsible (names the pull request and deploy time), links similar past incidents and what fixed them, searches public Slack threads, reads Grafana or Datadog dashboards, can open a fix PR, drafts post-mortems, works inside Slack and Microsoft Teams. Says engineers "always make the final call". It publishes how it measures accuracy (a graded scale, precision and recall, backtesting; docs.incident.io/investigations/measuring-accuracy) but no figures [P]. The "handful of customers" remark dates from July 2025.

**Rootly AI SRE** [V] — integrated with its on-call, catalog and code read access; suggests responders and roles from catalog, schedules and past involvement; drafts status updates; retrospectives with timelines and action items; Slack, Teams, mobile and IDE. Rootly's own honest assessment [V, but candid]: agents work well for summaries, related-incident retrieval, deploy correlation and retrospective drafts; they fail on novel failures and give "a plausible cause delivered with the same tone as a correct one"; roll out retrospectives first, remediation last.

**Cleric** [V/T] — Slack-first investigator with a system knowledge graph and operational memory. Feedback from engineers is attached to the specific investigation trace, patterns are generalised with customer details stripped, and success rate is compared before and after each new memory. Cleric notes a past production incident cannot be replayed, so it runs several strategies concurrently and compares them.

**Resolve AI** [V] — a living knowledge graph of services, pods and components that the agent walks to correlate and find causes; learns from each incident and interaction; usage is metered in credits set by contract [P]. Grafana's own test (of Grafana's graph, not Resolve's) found the agent with graph context used about half the telemetry queries; a single case; the "about half the queries" figure was not found on the cited pages when re-checked.

**Traversal** [V] — builds a "production world model" from telemetry and code and runs thousands of parallel analytical tests with causal machine learning before an LLM reasons over the survivors. Published detail is thin; one customer claim of 38% lower MTTR.

**Komodor Klaudia** [V/T] — Kubernetes-specific; root cause plus remediation, with self-healing that can run with or without a human, guardrails by pre-defined automation levels, more than 50 specialised agents, a published memory design.

**Causely** [V] — causal Bayesian reasoning from symptoms to root causes over the discovered topology; says alarm suppression is not root-cause analysis. An independent explainer notes a wrong graph produces confident wrong answers [T].

**Sentry Seer** [V] — code-level: root cause from stack trace, breadcrumbs, traces and replays, then a solution, then an optional fix PR; annotations link to the exact lines; high-confidence issues run automatically; users set how much autonomy it has.

### 2.2 Alert correlation and ITSM (AIOps)

- **BigPanda** [T]: topology-aware correlation using dependency data to group alerts; normalises events to a shared tagging scheme; an agentic first-line agent; 300+ integrations. **Moogsoft** (now Dell APEX AIOps) [T]: machine-learning clustering that works without topology; probabilistic, evidence-backed RCA. Both are described as not producing fixes or PRs.
- **ServiceNow Now Assist for ITSM and ITOM** [P] (being relabelled ServiceNow Otto from August 2026): agentic workflows for incident triage and categorisation, incident investigation and resolution (finds similar incidents and knowledge articles, writes the result to the work notes), change request planning, post-incident reports for major incidents; AIOps agents that triage alerts, assess business and technical impact and drive remediation; alerts closed autonomously are marked **"Closed by AI"** so autonomy is measurable; playbooks learned from historical incidents. Relevant because Keigan integrates with ServiceNow: the ITSM system itself is gaining the same capability, so Keigan should write into ServiceNow work notes and not compete with it.

### 2.3 The incident lifecycle around the investigation

- **incident.io** [V]: follow-ups are real tasks sent to Jira, Linear or ServiceNow, with a dashboard of outstanding items by team, completion rate, time to complete, **policy violations** (for example critical-incident follow-ups not done within N days) and reminders; MTTA, MTTR and incident frequency by service from day one; status page updated by workflow when an incident is resolved; on-call in the Basic plan.
- **FireHydrant** [V]: runbooks layered by severity, team or service; service catalog by web, API or Terraform; retrospectives; "Signals" on-call with unlimited escalation policies; AI features in the top tier only. Acquired by Freshworks in January 2026 [T].
- **Rootly** [V]: roles and responders suggested from catalog and schedules, workflow automation (channels, pages, tickets, diagnostic scripts, status drafts).
- Common to all three: a **service catalog** feeds ownership, escalation and the investigation itself. Those who skip it (or have none) say the AI is weaker. PagerDuty states the same dependency.

### 2.4 SLOs and reliability practice

- **Nobl9** [V]: composite SLOs with **weighted** component SLOs and a "component impact" view of which part burned the combined budget; SLOs as code in YAML for CI/CD; burn-rate alerts routed to PagerDuty, Jira or ServiceNow. Its best-practice guide puts drafting error budget policies in the adoption phase and says to start with SLOs as code.
- **Google SRE Workbook, example error budget policy** [P]: if one incident consumes more than 20% of the error budget over four weeks, a postmortem is required and must contain at least one top-priority action item addressing the root cause. Google's reliability-engineering posts describe reserving a share of sprint capacity for postmortem action items and shifting it toward reliability while the service is out of SLO. The policy matters only if the team agreed in advance what happens when the budget runs low.
- **Datadog** lists SLO monitors among the monitor types an investigation can start from [P]; no other vendor above was checked for this.

### 2.5 Interoperability and platform direction

- **MCP (Model Context Protocol)** is now the common plug: Azure SRE Agent consumes MCP connectors; Datadog, Grafana, Splunk (generally available; date unconfirmed) and AWS expose MCP servers; AWS DevOps Agent also speaks ACP and A2A [P].
- **Agents as callable services**: AWS, Datadog and Grafana can be started from another agent or an API, not only from their own console [P].
- **Preview is normal**: most investigation features above are preview or recently generally available, with availability statements that disagree between sources.

### 2.6 What the evidence says about effectiveness, trust, cost and governance

**Independent research is sobering** [T, academic]:
- OpenRCA (ICLR 2025): the best agent at publication reached about 11% accuracy (time, component and reason all correct). The fact-check found a later leaderboard entry at about 36% (February 2026); my fetch tool could not read the leaderboard page, so verify it at microsoft.github.io/OpenRCA. Scores are low but rising fast.
- A follow-up study ran 1,675 agent runs over five models and found the common failure types appear **regardless of model strength**, prompt engineering alone does not fix them, and the dominant ones are *hallucinated data interpretation* and *incomplete exploration*; better agent-to-agent communication cut communication failures by up to 15 points.
- ORCA-bench (2026): best frontier coding agent 25.3% on medium and 10.0% on hard tasks; the weakest model invented an implausible root cause in 40% of reports; **removing source-code access lowered accuracy and raised hallucination for every model**. The testbed is smaller than real production, so real difficulty may be higher.
- A 2026 benchmark paper (Cloud-OpsBench) reports joint accuracy up to 0.78 but finds that correct answers often lack *evidence closure*, meaning the evidence does not support the conclusion; it argues for scoring the evidence, not only the outcome.

**Vendor numbers vs this**: 94% (AWS), "up to 95%" faster resolution (Datadog), "up to 80%" (incident.io). These measure different things on private datasets. incident.io (a competitor) says Rootly publishes no production precision or recall [V].

**Trust** [V]: a CNCF member blog post by a vendor executive (StackGen), drawn from conversations at an event, argues that the gap is context, not model capability. Their requirements: evidence on messy real incidents (demos are not enough), current operational knowledge ("stale runbooks are arguably worse than none, because they invite confident, wrong action"), and **reasoning that can be reconstructed afterwards** — a decision trace recording inputs, policies, model version, rejected hypotheses, action and outcome. Practitioner reports describe agents that blame the wrong team, lock onto an unrelated critical-looking error, or get worse when given more telemetry.

**Rollout order recommended by vendors who sell this** [V]: retrospective drafting, then summaries, then candidate causes treated as leads, with remediation last and gated. incident.io's rule: "AI proposes, human approves, AI executes."

**Cost** [V/T]: Datadog's own figure is about $4 of cost per investigation [V]; it earlier priced per investigation and now uses shared credits [T]; Resolve meters credits [P]; Cleric uses credits per investigation [T]; Azure SRE Agent charges a fixed hourly amount plus usage [P]. Gartner names uncapped usage pricing as a risk (cost overruns for over half of buyers through 2027) [T, press coverage]. The market is converging on **usage-based pricing tied to investigations**, which makes a cost-per-investigation figure a first-class product metric.

**Analysts and governance** [T]: Gartner's 2026 prediction report urges setting governance, guardrails and performance SLAs for production AI agents and forecasts large growth in autonomous reliability practices (the figures, 70% by 2030 or 2029, are quoted secondhand and differ between sources). For regulated financial firms, commentary stresses meaningful (not nominal) human oversight, agents as identities with their own access controls, machine-readable rules for when an agent may act alone, and a traceable evidence bundle per action. The NIST AI RMF organises this as govern, map, measure, manage. Several of these are secondary writeups; the primary texts (EU AI Act, NIST, US Treasury financial-sector framework) were not read.

---

## Part 3 — What it means for Keigan

### 3.1 Patterns that hold across the whole market

1. **Alert in, investigation out, no human trigger.** Every product starts an investigation from an alert or ticket automatically, and also lets a person start one from chat.
2. **Hypotheses, tested one at a time, each with an honest outcome.** Datadog (validate or invalidate; a whole investigation can end inconclusive), PagerDuty (ranked by confidence, shows what was ruled out) and Azure (hypothesis testing) all show the rejected leads. Skipping this is where wrong answers hide.
3. **Change correlation is the most-cited cause finder.** Recent deploys, config and code changes appear in every product's example. Source-code access measurably improves accuracy (ORCA-bench).
4. **Memory of past incidents**, from "similar incidents" lists (incident.io, ServiceNow) to feedback-driven learned memory (Cleric, PagerDuty, Azure, AWS "learned skills").
5. **Evidence you can follow.** Citations to the exact pull request, trace id or log line (incident.io, Elastic, Seer); a replayable decision trace is what senior SREs ask for.
6. **Humans approve writes, mostly.** Review is the recommended mode for production, but defaults differ (Azure's per-plan default is Autonomous; Grafana describes "human on the loop"; Komodor self-heals). Autonomy is granted *per trigger* after a trial period. Azure's Review mode gates only Azure infrastructure writes, and an allow rule, including a one-conversation allow that any user can add, skips approval, so a finer policy layer (allow, ask, deny by tool and arguments) exists for the rest.
7. **Lives in the chat tool.** Slack and Microsoft Teams are first-class; answers and approvals happen where responders already are.
8. **Reports prove the value.** Investigation counts, mean time to conclusion, MTTR, follow-up completion.
9. **Open plumbing.** MCP in and out, and an API so another agent can ask.
10. **Cost is measured per investigation** and is falling fast (Datadog $25 to about $4).

### 3.2 Keigan against that list

Status: ✅ have · 🟡 partial · ⬜ missing · ➖ deliberately not built. "Code-checked" means I confirmed it in the source on 2026-11-21; the rest is from `12_FEATURE_TRACKER.md` (2026-11-20) and may be slightly out of date.

| Capability the market has | Keigan today | Notes |
|---|---|---|
| Automatic investigation from an alert group | ✅ | Alert group to investigation to ServiceNow incident (tracker H7) |
| Hypotheses with confidence | ✅ code-checked | Three fixed perspectives (application, dependencies, infrastructure) with a confidence score each and an overall score |
| Show rejected or inconclusive hypotheses | 🟡 (corrected after fact-check) | Evidence-level rule-outs and "cannot check this source" notes exist (`evidence_service.py`), and contradicting evidence is shown per hypothesis (`HypothesesSection.tsx`). Missing: a hypothesis-level ruled-out or inconclusive state and an investigation-level "inconclusive" outcome |
| Evidence with citations | ✅ | Citation codes checked and invalid ones removed |
| Healthy-window baseline comparison | ✅ mostly (corrected after fact-check) | A baseline window is passed to all telemetry evidence collection (`investigation_graph.py`, evidence stage); events, latency and metrics are compared with it (`evidence_service.py`). Synthetic probes and activity-log changes are not |
| Change correlation from the cloud | ✅ code-checked | Azure Activity Log is read as evidence ("Recent deployments and configuration changes") |
| Change correlation from code and pipelines (GitHub, Azure DevOps) | ⬜ code-checked | No repository or CI/CD integration |
| Similar past incidents | 🟡 code-checked | The three most recent *confirmed-correct* investigations of the same application are added to the prompt as short summaries (300 characters each); a recurring-incident detector exists; the RAG proposal (`08`) is not built across applications |
| Learning from feedback | 🟡 | Verdicts are stored and the "correct" ones feed the prompt as above; no accuracy measurement, no negative learning |
| Evaluation of the AI itself | ⬜ | No measured accuracy; a labelled simulator exists (8 scenarios) that could seed one |
| Decision trace / replay | 🟡 (corrected after fact-check) | Prompt hashes are written only to a DEBUG log (`llm_gateway.py`), not stored. Per-call usage rows are linked to the investigation (`LlmUsageRecord`), so cost per investigation can be computed today. No assembled per-investigation trace |
| Post-incident draft | ✅ | Blameless postmortem, edit and approve |
| Post-incident action items tracked to done | 🟡 (corrected after fact-check) | Postmortems list action items with owner role, due date and type (`PostmortemActionItem`); they are not tracked as tasks, reminded or synced to ServiceNow |
| Alert correlation with reasons | ✅ | Nine-stage pipeline records why each alert was kept, grouped or dropped |
| Written "why these alerts belong together" on the group | 🟡 (corrected after fact-check) | Grouping across declared one-hop dependencies exists (`alert_pipeline_service.py`) and the group stores a `grouping_reason` text (`alert_entities.py`). A structured, localised sentence was built on 2026-11-21 (B3, see `features/alert-grouping-reason/26_ALERT_GROUPING_REASON.md`); multi-hop grouping is not built |
| SLOs and burn-rate alerts | ✅ | Multi-window; heatmap |
| Error-budget policy that triggers actions | ⬜ | |
| Composite or weighted SLOs, SLOs as code | ⬜ | |
| Predictive signals | ✅ | Memory leak, latency creep, budget burn, recurring incidents |
| Chat in Teams | ✅ | Incident chat and bot; "this is finished" starts the postmortem |
| One chat that can use every read-only tool (SLOs, alerts, incidents, signals, topology, runbooks, changes, logs) | 🟡 code-checked | Three chats exist. The global Keigan chat routes a question to *knowledge*, *a count from logs*, *a pattern chart* or *out of scope*; it does not query incidents, alerts, SLOs or signals. The investigation chat is a tool-using agent but only for one investigation (evidence lookup, knowledge search, safe log query, at most six tool calls) |
| Actions on Teams cards (acknowledge, approve) | ⬜ | Not confirmed |
| Per-application operating instructions for the AI | 🟡 | Knowledge documents and runbooks, but no short, durable, audited instruction set |
| MCP server or client | ⬜ code-checked | No MCP anywhere |
| Reports: MTTD, MTTA, MTTR, time to conclusion, AI cost per investigation | 🟡 | Usage and token accounting exist; the incident metrics are not in the tracker |
| Remediation proposals with validate and revert steps | ✅ code-checked (corrected after fact-check) | Every hypothesis fix carries steps, a command risk rating, verification steps and rollback steps, and the investigation screen shows them (`ProposedFix` in `ai/investigation_ai_schemas.py`; `HypothesesSection.tsx`). What remains is raising their quality and scoring them in the harness |
| Executing remediation | ➖ | By design: Keigan never changes customer systems |
| On-call schedules, paging, escalation | ➖ | Notifications by email and Teams; ServiceNow owns assignment |
| Status page | ⬜ | |
| Multilingual output | ✅ | Seven interface languages; Japanese incident communications. Azure's observability agent is English only |
| Prompt-injection defences, PII masking, output sanitising | ✅ | Rarely stated by competitors |

### 3.3 Where Keigan is different, and the question that follows

What nobody else bundles: **noise policy, SLOs, predictive signals, investigation, communications, postmortem and a stakeholder team in one governed flow**, ServiceNow-centred, multilingual, with hard rules about what the AI may read and say.

What the hyperscalers now offer: Azure SRE Agent (generally announced) and the Azure Copilot Observability Agent cover alert-to-investigation-to-ticket on Azure and ServiceNow, and AWS DevOps Agent investigates Azure (built in) and on-premises applications (through MCP). They will keep improving faster than a single team can. Racing them on raw telemetry reasoning is the weakest position.

**My view, to be confirmed by you:** Keigan should be the *organisation-owned reliability workflow*, and treat the investigation engine as replaceable. Concretely: keep investing in what the platform vendors will not build for one company (policy, knowledge, ServiceNow flow, languages, SLO governance, the learning loop, evaluation), and make Keigan able to *consume* an external agent's findings as one more evidence source. That decision is Part 4, question 1. **Decided 2026-11-21 (see 4.0):** Keigan builds its own investigation agents, grounded in each application's knowledge and runbooks; external agents stay an optional evidence source for later.

### 3.4 Our own ideas, re-scored against the evidence

Numbers refer to Part 1. Verdicts: **Build** (recommended, see 3.5), **Later**, **Integrate** (use an existing system rather than build), **Skip**.

| # | Idea | Verdict | Why |
|---|---|---|---|
| 1 | Change correlation | **Build the second half** | Azure Activity Log is done (code-checked). Missing: code, pipelines, feature flags. Correction to my Part 1, which said there was no change feed |
| 2 | Similar past incidents | **Build** | Table stakes; today only one application's last three confirmed summaries |
| 3 | Suspect code | **Later, depends on access** | A promising accuracy lever (one benchmark), but needs repository access decisions |
| 4 | Confidence and honesty | **Build** | Confidence scores exist; add ruled-out, inconclusive and "could not check" |
| 5 | Feedback loop with a score | **Build, first** | Verdicts exist (partly used); the missing piece is measurement. Without it no other AI change can be judged |
| 6 | More signal types | **Later** | Add per demand; MCP makes it cheaper |
| 7 | Suggested remediation with approval | **Exists as suggest-only; improve quality** | Fixes already carry verification and rollback steps (corrected after fact-check); execution is parked (E2) |
| 8 | Rollback suggestions | **Exists; tie to the suspect change later** | Rollback steps are already produced per fix |
| 9 | Runbook quality | **Build, cheap** | The research says stale runbooks are dangerous; track which helped and which are old |
| 10 | On-call and escalation | **Integrate** | ServiceNow, PagerDuty and Azure Monitor own this; every AI product integrates rather than replaces |
| 11 | Roles and live status | **Later** | Team roles now exist; a status model can follow |
| 12 | Status page | **Skip for now** | Ask whether anyone needs it |
| 13 | Teams card actions | **Build** | Matches the market pattern of staying in chat |
| 14 | Cross-source correlation | **Partly exists; B3 built** | One-hop declared-dependency grouping and a written, localised reason exist; remaining: multi-hop grouping |
| 15 | Alert quality scoring | **Build** | Cheap from data already held (noisy, never actioned) |
| 16 | Flapping and seasonality | **Later** | The predictive detectors already use seasonality |
| 17 | Action items tracked to done | **Build** | Clear competitor feature, strong fit with postmortems and ServiceNow |
| 18 | Error-budget policy that acts | **Build** | Google's own policy is concrete; fits Keigan's SLO strength |
| 19 | Readiness reviews, game days | **Later** | |
| 20 | Ownership health score | **Later** | Every vendor says the AI needs ownership data; a score would show gaps |
| 21 | Dependency map from real traffic | **Later** | Declared topology plus AI-built topology exist |
| 22 | MTTD, MTTA, MTTR | **Build** | Cheap and proves value |
| 23 | Weekly executive digest | **Build, cheap** | Intelligence report exists |
| 24 | AI cost and quality dashboard | **Build with 22** | Cost per investigation is now a market metric |
| 25 | Outbound integrations | **Build ServiceNow write-back first** | Matches Now Assist; others on demand |
| 26 | API or MCP server | **Build read-only** | Every serious competitor has it |
| 27 | Enterprise basics | **Ongoing** | Mostly present (RBAC, audit); SCIM only if asked |
| 28 | Multi-tenant | **Skip until asked** | |
| 29 | Phone on-call view | **Later** | Responsive design is done; no on-call engine here |
| 30 | Notification preferences | **Build, small** | Team feature just added; quiet hours and per-type are natural next |
| 31 | Saved views | **Skip** | Low value |

New ideas the research added that were not in Part 1:
- **N1. Per-application operating instructions** (Azure's "custom instructions": which services are revenue-critical, which alerts must never be merged, which are regulated).
- **N2. Inconclusive is a result, not a failure**, and is reported (Datadog marks a whole investigation inconclusive when it is; some vendors' older plans did not bill inconclusive runs [T]).
- **N3. Per-trigger autonomy with a trial period** (Azure run modes), as the design for any future action.
- **N4. "Closed by AI" style attribution** to measure what the AI actually handled (ServiceNow).
- **N5. Scheduled health reviews** per application (Azure scheduled tasks, Grafana automations).
- **N6. Investigation per hypothesis, not bulk summary**, and evidence pre-processed in code before the model sees it (Datadog). Applies to our existing pipeline.
- **N7. Healthy-window baseline** for every claim of "changed" (Elastic).

### 3.5 Recommended order

Sizes are relative: **S** days, **M** one to two weeks, **L** several weeks. The order matters: trust first, because every later feature inherits it.

**Wave A — Prove it works** (nothing in B to E should ship before A1)
| | What | Size | Why now | Done when |
|---|---|---|---|---|
| A1 | **Evaluation harness**: run the eight simulated scenarios through the real pipeline with the real model, score root cause, citation validity, hallucination, inconclusive rate, cost and time; run on every prompt or model change; add real labelled incidents as they are confirmed | M | Independent research shows low accuracy and 7 to 40% hallucination; Datadog calls evaluation "fundamental"; we already own labelled scenarios | A prompt change shows a before and after score in CI **Spec written: doc 22, AI evaluation harness spec (draft, awaiting owner approval). DEFERRED by the owner (2026-11-21): design only for now, to be built later; feature work comes first. Note that without it, accuracy of every AI feature stays unmeasured.** |
| A2 | **Honest outcomes (BUILT 2026-11-23, see `features/honest-outcomes/27_HONEST_OUTCOMES.md`)**: per-hypothesis state (supported, ruled out, inconclusive), "what I could not check", baseline comparison | S to M | PagerDuty, Datadog and Elastic all show rejected leads | Every investigation lists what was ruled out and why |
| A3 | **Decision trace (BUILT 2026-11-23, see `features/decision-trace/28_DECISION_TRACE.md`)** per investigation (inputs, evidence ids, prompt hashes, model, rejected hypotheses, outcome) | S to M | a vendor executive's CNCF post calls it "non-negotiable"; audit needs it | One screen replays an investigation |
| A4 | **Metrics and cost**: MTTD, MTTA, MTTR, time to conclusion, accuracy from verdicts, cost per investigation | S to M | Proves value; every vendor reports it | Dashboard and weekly digest. **Built 2026-11-21 as the `/metrics` page (MTTA not possible: no acknowledgement timestamp exists); no weekly digest.** See `features/reliability-metrics/24_RELIABILITY_METRICS.md` |

**Wave B — Smarter**
| | What | Size | Notes |
|---|---|---|---|
| B1 | **Similar-incident memory** across applications and ticket text; show "last time: cause, fix" | M | Weight by feedback; keep the stale-memory risk visible |
| B2 | **Operating instructions per application** | S | Length-limited, audited, editable by the application admin. **Built 2026-11-21.** See `features/application-operating-notes/25_APPLICATION_OPERATING_NOTES.md` |
| B3 | **Why-grouped sentence** per alert group, topology-aware grouping | S to M | **Built 2026-11-21** (the sentence; multi-hop grouping was not built). See `features/alert-grouping-reason/26_ALERT_GROUPING_REASON.md` |
| B4 | **Code and pipeline changes** (Azure DevOps, GitHub read-only) | L | **Parked by decision (2026-11-21):** access is not available yet; see the parking lot in 4.4 |
| B5 | **One chat that can use every read-only tool**: a tool-using agent over Keigan's own data (incidents, alerts, SLOs, signals, investigations, topology, runbooks, team, changes) plus the existing safe log query. Every tool enforces the asking person's application access; answers cite the record they came from | M | Added 2026-11-21 after the user asked for it; today's global chat covers only knowledge, log counts and patterns. The same tool set is what a read-only MCP server (D3) would expose |

**Wave C — Close the loop**
| | What | Size | Notes |
|---|---|---|---|
| C1 | **Post-incident action items** as tracked tasks with owners, due dates, reminders, ServiceNow sync and a policy-violation view | M | Competitor standard; strong fit |
| C2 | **Error-budget policy that acts** (for example one incident burning more than a set share in a window requires a postmortem with a top-priority action) | M | Thresholds configurable, defaults from Google's example |
| C3 | **Scheduled weekly health review** per application | S | |
| C4 | **Runbook health**: used, helped, stale | S | |

**Wave D — Open up**
| | What | Size | Notes |
|---|---|---|---|
| D1 | **ServiceNow write-back** (work notes, tasks) | S to M | Meets Now Assist where the user already is |
| D2 | **Teams card actions** (acknowledge, ask, approve a proposed step) | M | |
| D3 | **Read-only MCP server**, then MCP client for third-party observability | M to L | Standard plug everywhere |

**Wave E — Suggest better now; execution is parked (decided 2026-11-21)**
| | What | Size | Notes |
|---|---|---|---|
| E1 | **Better suggested fixes** (the structure exists: steps, risk rating, verification and rollback steps are already produced and shown; corrected after fact-check): make each step an exact copyable command or change (kubectl, a system command, a configuration edit), improve their quality and score them in the harness | S to M | Humans run it, in their own tools and under their own access |
| E2 | **Governed execution** (PARKED) | L | **Not now; it may come later (decided 2026-11-21).** Today Keigan never executes. If it ever returns: allow, ask and deny rules by tool and arguments, Review by default per trigger, a per-conversation override, full audit, non-production first (Azure's layering is the model). It needs a compliance decision and measured accuracy (A1) first |

### 3.6 Lessons for what already exists

- **Datadog**: the distraction came from an early summarise-everything agent and was fixed by investigating per hypothesis with only that link's telemetry; separately, moving from phases to a ReAct loop cut cost. The fact-check found that every Keigan perspective receives the full evidence index (`investigation_graph.py`), so test whether per-hypothesis evidence helps; the harness (A1) can measure it.
- **Elastic**: every number names its tool and every claim names a record id. Check that Keigan's citations point to ids a person can open.
- **ORCA-bench**: weaker models invent causes when the real cause is outside the data. Keigan's "evidence-only" mode and "no data" wording are the right instinct; add an explicit "cause not visible in the data I can see" outcome.
- **CNCF**: stale runbooks are worse than none. Runbook health (C4) addresses it.
- **Rootly's own advice**: introduce summaries and retrospectives before remediation. Keigan already does; keep remediation propose-only.

### 3.7 Not recommended now

- Building **our own on-call scheduling and paging**: every AI product integrates with the incumbent.
- Building **our own observability data store**: Keigan reads Azure and log tools; storing telemetry competes with them.
- **Any execution of changes**, autonomous or approved: **not now** by decision (2026-11-21); Keigan suggests and recommends only. It may be revisited later, so it is parked as E2, not deleted.
- **Training a specialised model** (Datadog's route): needs an in-house reinforcement-learning stack.
- A **public status page**, **multi-tenant**, **SCIM**: wait for a real request.

---

## Part 4 — Decisions, open questions, limits and when to redo this

### 4.0 Decisions made on 2026-11-21

| Question | Decision | Consequence |
|---|---|---|
| Complement or compete with Azure's and AWS's agents? | Keigan builds **its own investigation agents**. Their edge over a generic agent is the application's own knowledge and runbooks, retrieved and sent with every investigation. | Keep investing in retrieval quality, citations and the evaluation harness (A1). Taking an external agent's findings as an evidence source stays possible later but is not a goal |
| Will Keigan ever change customer systems? | **Not now; it may happen later.** Today it only suggests and recommends: a kubectl command, a system command or any other fix, shown for a person to run. | E2 (governed execution) is parked, not removed. Keep Keigan's own access read-only while that holds. Suggestions carry validate and revert steps (E1) |
| Read access to Azure DevOps or GitHub? | **Yes, but not today.** Keep it in the architecture for later. | Parked item B4; see 4.4 |
| On-call and status pages? | **Not now.** Teams chat and email are the channels for now; maybe later. | Nothing built. Integrate with ServiceNow or PagerDuty first if it comes back |

### 4.1 Questions still open (1 to 4 of the original six were answered, see 4.0)
1. *(Answered, see 4.0.)* **Complement or compete?** Should Keigan stay the organisation's own reliability workflow and accept external agents (Azure SRE Agent, AWS DevOps Agent) as evidence sources, or aim to replace them for investigation?
2. *(Answered, see 4.0.)* **Will Keigan ever change customer systems?** Today it never does. Wave E changes that stance and needs a policy and compliance decision first.
3. *(Answered, see 4.0.)* **Repository access.** Can Keigan get read access to Azure DevOps or GitHub, and to deployment pipelines? It is the biggest single accuracy lever.
4. *(Answered, see 4.0.)* **Who needs on-call and status pages?** If ServiceNow or PagerDuty already cover them, we integrate and skip.
5. **How will you judge success?** MTTR, hours saved, fewer pages, accuracy? It decides what A4 measures.
6. **Regulatory scope.** Is Keigan used for incidents affecting regulated customer data or processes, so the governance material in 2.6 applies in full?

### 4.2 What this research could not confirm
- **No independent accuracy figure** exists for any commercial product. All percentages are vendor claims.
- **Availability and dates** of many features differ between sources (PagerDuty, Splunk, Google). Check live documentation before relying on any.
- **Pricing** is quoted secondhand (Better Stack, incident.io blogs) and changes often.
- **Gartner**: the fact-check found a press release of 26 October 2026 (top AI trends in infrastructure and operations for 2027) and a July 2026 Hype Cycle for AI in IT Operations. The Gartner pages themselves returned 403, so these figures come from press coverage (CXOToday, The Register) and were not re-read: minimal-human IT operations for half of organisations by 2030; uncapped usage pricing causing cost overruns through 2027. One prediction (40% of agents decommissioned by 2027) could not be traced to Gartner and was left out.
- **Regulatory texts** (EU AI Act, NIST AI RMF, US Treasury framework) were summarised by commentators; the primary texts were not read.
- **Not researched** (the OpenTelemetry GenAI conventions and ISO/IEC 42001 were added as gaps by the fact-check): Honeycomb, Lightstep, Opsgenie replacement paths, Jeli, Squadcast, Zenduty, OpenSLO specification, Microsoft's Responsible AI transparency notes in detail, and non-English-language market (Japan) vendors.
- **Several fetches were limited** by the fetching tool's summarisation: where a page said "not covered", that is recorded as not found, not as absent from the product.
- Some Keigan "have" statements are from the feature tracker and not re-verified in code (see 3.2).

### 4.2a Independent fact-check (2026-11-21)

A second model (Opus 5.5, high effort) re-checked this document against primary sources and the code and reported 28 findings. I spot-checked the high-severity ones (the code claims, the AWS GA date) and applied the corrections above; items marked "corrected after fact-check" are those.
- **Biggest corrections:** my Keigan status table understated what exists in four places (fixes already carry verification and rollback steps; a baseline window already feeds evidence; dependency-based alert grouping already exists; postmortems already list action items). Azure's run-mode defaults are not "Review everywhere". OpenRCA's best score has risen to about 36%. Several dates, labels and the Datadog and pricing details were wrong or invented and are fixed.
- **Verified correct** by the fact-check: Datadog cost, time and quality figures; Azure run modes, policies, pricing structure and Observability Agent limits; AWS mitigation plans and protocols; the benchmark papers' figures; Google's 20% and four weeks; the code facts marked code-checked.
- **Still unverified** (not re-fetched): Dynatrace agentic workflows (preview), Traversal's 38%, Cleric's memory design, Causely, Sentry's autonomy settings, BigPanda and Moogsoft details, the governance and regulatory secondary sources. Two details in the Nobl9 and Komodor entries (component-impact view, 50 agents and memory design) came from search summaries and were not found on the cited pages.
- **Gaps the fact-check added** (not yet read in full): OpenTelemetry GenAI semantic conventions including MCP, a candidate standard for the decision trace (A3) and metrics (A4); ISO/IEC 42001, the AI management-system standard, relevant to governance.

### 4.3 When to redo this
Re-check in **about six months (May 2027)**, or sooner if Microsoft changes Azure SRE Agent's scope, an independent benchmark of a commercial product appears, or Keigan's scope changes. Update only the vendor entries that changed, not the whole document.

### 4.4 Architecture parking lot (decided later, designed now so it is a contained change)

**Code and pipeline evidence (Azure DevOps, GitHub).** Parked until read access exists.
- It should arrive as *one more evidence source* beside the Azure Activity Log, not as a new pipeline stage: the investigation already collects evidence drafts from sources, ranks them and cites them.
- Needs, when it is time: a read-only identity per organisation or per repository (a GitHub App or an Azure DevOps service principal, never a person's token), its secret in the existing secret store, a repository mapping per application or component, recent commits, pull requests, releases and pipeline runs in the incident window, and a size and time limit per read.
- Repository content is **untrusted text** (comments and commit messages can carry instructions), so it goes into the model as an untrusted section like logs, with masking, exactly as today.
- In one independent benchmark (ORCA-bench) removing source-code access hurt every model, so it is a promising lever, though not a proven largest one; it is worth doing first when access arrives.
- **Revisit when:** read access to at least one repository host is granted.

**Execution of changes (E2).** Not built and not planned now. **Revisit when** the evaluation harness (A1) shows measured accuracy, a compliance decision allows it, and a team asks for it. Start in non-production with approval for every action.

**On-call, paging, status page.** Not built. Teams chat and email are the channels. **Revisit when** responders ask for paging or escalation, and then integrate with ServiceNow or PagerDuty before building anything.

**Semantic retrieval for knowledge and past incidents.** Today retrieval is keyword ranking (BM25), see `08_RAG_PROPOSAL.md`. **Revisit when** the evaluation harness (A1) shows misses caused by synonyms, mixed Japanese and English, or when similar-incident search across applications (B1) needs it.

---

## Sources

Tags as in Part 2. Fetched in full on 2026-11-21 unless marked *(search result only)*.

**Microsoft**
- [P] Azure SRE Agent overview: https://learn.microsoft.com/en-us/azure/sre-agent/overview
- [P] Run modes: https://learn.microsoft.com/en-us/azure/sre-agent/run-modes
- [P] Tool access policies: https://learn.microsoft.com/en-us/azure/sre-agent/tool-access-policies
- [P] Incident response: https://sre.azure.com/docs/capabilities/incident-response
- [P] Azure Copilot Observability Agent: https://learn.microsoft.com/en-us/azure/azure-monitor/aiops/observability-agent-overview
- [P] Autonomous operations: https://learn.microsoft.com/en-us/azure/azure-monitor/aiops/observability-agent-autonomous-operations
- [P] SRE Agent pricing *(search result only)*: https://azure.microsoft.com/en-us/pricing/details/sre-agent/
- [V] GA announcement *(title only)*: https://techcommunity.microsoft.com/blog/AppsonAzureBlog/announcing-general-availability-for-the-azure-sre-agent/4500682

**AWS, Google**
- [P] AWS DevOps Agent guide: https://docs.aws.amazon.com/devopsagent/latest/userguide/about-aws-devops-agent.html
- [T] AWS GA (InfoQ) *(search result only)*: https://infoq.com/news/2026/04/aws-devops-agent-ga
- [P] Gemini Cloud Assist investigations *(search result only)*: https://docs.cloud.google.com/cloud-assist/investigations

**Observability vendors**
- [V] Datadog, building Bits AI SRE: https://www.datadoghq.com/blog/building-bits-ai-sre.md
- [P] Datadog, investigate alerts: https://docs.datadoghq.com/bits_ai/bits_ai_sre/investigate_alerts
- [V] Datadog, cost, speed, accuracy: https://www.datadoghq.com/blog/bits-investigations-cost-speed-accuracy.md
- [V] Grafana Assistant Investigations: https://grafana.com/blog/automatically-discover-and-remediate-root-causes-with-grafana-assistant-investigations
- [P/V] Dynatrace Davis AI: https://docs.dynatrace.com/docs/observe-and-explore/davis-ai
- [T] Dynatrace causal AI (TechTarget) *(search result only)*: https://www.techtarget.com/searchapparchitecture/tip/Dynatrace-bets-on-causal-intelligence-for-AI-observability
- [V] New Relic SRE Agent: https://newrelic.com/press-release/20260224 *(search result only)*
- [V] Splunk AI troubleshooting agent *(search result only)*: https://www.splunk.com/en_us/blog/observability/ai-troubleshooting-agent-in-splunk-observability-cloud
- [P/V] Elastic RCA with Agent Builder *(search result only)*: https://www.elastic.co/observability-labs/blog/ai-root-cause-analysis-agent-builder
- [V] Sentry Seer *(search result only)*: https://docs.sentry.io/product/ai-in-sentry/seer/

**Incident-management and AI SRE vendors**
- [V] PagerDuty, Paige: https://www.pagerduty.com/blog/ai/meet-paige-sre-agent/
- [V] incident.io, AI SRE: https://incident.io/blog/introducing-ai-sre
- [V] incident.io, AI SRE explained: https://incident.io/blog/what-is-ai-sre-complete-guide-2026
- [V] incident.io, timeline to automated response (April 2025, historical): https://incident.io/blog/the-timeline-to-fully-automated-incident-response
- [V] incident.io, follow-ups and insights *(search result only)*: https://incident.io/blog/best-postmortem-software-for-on-call-engineers-2026-guide
- [V] Rootly, do AI SRE agents work: https://rootly.com/blog/do-ai-sre-agents-actually-work
- [V] Rootly AI SRE *(search result only)*: https://rootly.com/product/ai
- [V] FireHydrant *(search result only)*: https://firehydrant.com/platform/
- [V/T] Cleric with LangSmith: https://www.langchain.com/blog/customers-cleric
- [V] Resolve AI knowledge graph *(search result only)*: https://resolve.ai/blog/knowledge-graph-agentic-ai-incident-response
- [V] Traversal *(search result only)*: https://www.traversal.com/blog/introducing-causal-search-engine-from-correlated-alerts-to-causally-consistent-diagnoses
- [V] Komodor Klaudia *(search result only)*: https://www.helpnetsecurity.com/2025/11/05/komodor-platform-self-healing-and-cost-optimization-capabilities/
- [V] Causely *(search result only)*: https://dev.to/causely/alarm-suppression-is-not-root-cause-analysis-3o5o
- [T] BigPanda and Moogsoft comparison *(search result only)*: https://coralogix.com/ai-blog/aiops-tools/
- [P] ServiceNow Now Assist for ITSM and ITOM *(search result only)*: https://www.servicenow.com/docs/r/Sx3eYflWQ2rS18vmPDBm0Q/9QWq2IH_qKXYxV7RXwkHeQ
- [V] Nobl9 composite SLOs *(search result only)*: https://www.nobl9.com/features/composite-service-level-objectives

**Practice, research, governance**
- [P] Google SRE Workbook, example error budget policy *(search result only)*: https://sre.google/workbook/error-budget-policy/
- [T] OpenRCA, ICLR 2025 *(search result only)*: https://iclr.cc/virtual/2025/poster/32093
- [T] LLM RCA agent pitfalls on OpenRCA: https://arxiv.org/abs/2602.09937
- [T] ORCA-bench: https://arxiv.org/abs/2607.28545
- [T] Cloud-OpsBench critique of live benchmarks *(search result only)*: https://arxiv.org/abs/2603.00468
- [T] CNCF, trust gap and the 4-body problem: https://www.cncf.io/blog/2026/07/06/the-4-body-problem-of-sre-why-autonomous-operations-depend-on-context/
- [T] Practitioner reports and failure modes *(search result only)*: https://www.infoworld.com/article/4195114/how-to-teach-sre-ai-agents-to-fail-safely-and-earn-your-teams-trust.html
- [T] AI SRE pricing comparisons *(search result only)*: https://betterstack.com/community/comparisons/bits-ai-sre-alternatives/
- [T] Gartner predictions summary (via PagerDuty) *(search result only)*: https://www.pagerduty.com/resources/itops/analyst-report/gartner-predicts-report-2026-ai-agents-transform-it-infrastructure-operations/
- [T] Agentic AI governance in financial services *(search result only)*: https://www.jitterbit.com/blog/5-best-practices-for-agentic-ai-governance-in-financial-services/
