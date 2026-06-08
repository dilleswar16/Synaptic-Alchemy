# Corvin — Global SRE Expert Evaluation Response
### Against: Tool Evaluation Checklist + NPI Advisory Checklist
> Baseline: Corvin post all improvements (4-week plan + RAEL backdoor + multi-model routing)
> Rating: ✅ Yes  |  🟡 Partial  |  ❌ No  |  🔮 Roadmap (post 4 weeks)

---

## SECTION 1 — MUST-PASS CRITERIA (8 Items)

| # | Must-Pass Criterion | Corvin | Evidence / Honest Note |
|---|---|---|---|
| 1 | Production references at comparable scale | ❌ | Competition winner, no enterprise production deployments yet. Honest answer: none. Counter: POC-first engagement with MetLife IS the reference. |
| 2 | Dedicated AI research organization | ❌ | Single cross-functional team. No dedicated AI research org. However: RAGAS eval pipeline + OTel tracing + continuous improvement infrastructure substitutes for formal research org function. |
| 3 | Observability stack coverage in GA | 🟡 | Azure Monitor (deep, GA), Elastic (GA), Splunk (planned). Missing: Datadog, New Relic, Prometheus native, Dynatrace. Azure-native stack is fully covered in GA. |
| 4 | Infrastructure coverage including non-Kubernetes | 🟡 | AKS/Kubernetes: deep. Azure VMs: via Azure Monitor Metrics API + AMA agent. Bare metal / non-Azure: not directly covered — requires Elastic or Azure Arc. Non-K8s workloads on Azure are reachable via Azure Monitor. |
| 5 | Cross-tool correlation demonstrated | ✅ | APIM gateway logs + AKS Container Insights + Azure Activity Log (change correlation) + Elastic app logs — all correlated within a single investigation. Activity Log surfaces the deployment that preceded the incident. Demonstrable in live POC. |
| 6 | Raw telemetry stays in your environment | ✅ | Fully self-hosted in customer Azure tenant. Corvin does not have a SaaS backend. Logs, RCAs, embeddings, session data never leave customer VNet. Azure OpenAI is in customer's Azure subscription. |
| 7 | SOC 2 Type II current report available | ❌ | Not a formal compliance-certified product. Self-hosted architecture means customer controls the compliance boundary — no vendor cloud, no vendor data handling. GDPR posture is strong (PII redaction, data never leaves tenant) but SOC 2 audit has not been conducted. |
| 8 | Hypothesis revision when the first hypothesis is wrong | ✅ | F8 Hypothesis Service generates 3 competing hypotheses (infrastructure / code-change / dependency angles). Low-confidence retry loop (Feature 6) automatically retries with broadened evidence when first RCA is weak. Critic pass (Feature 5) independently flags unsupported claims. Three-layer revision mechanism. |

**Must-Pass Score: 3 full pass, 3 partial, 2 fail**

Critical gap: Production references (#1) and SOC 2 (#7) are the two hard blockers for formal enterprise procurement. Both are process/time gated, not engineering gated. Self-hosted architecture partially addresses #7 (customer owns the compliance boundary) — this framing is defensible.

---

## SECTION 2 — USE CASES

### On-Call and Alerts

| Feature | Corvin | Evidence / Notes |
|---|---|---|
| **Autonomous alert triage** — Every alert assessed 24/7, severity read, recommended path | 🟡 | F1 Autonomous Agent fires on Azure Monitor webhook alerts, runs full investigation, sends Teams notification with severity and proposed action. Covers: escalate and investigate. Missing: silence, snooze, route-only (without investigation). |
| **Triage Mode** — Fast first-responder pass under 5 min, stops once basic questions answered | 🟡 | No dedicated triage-only mode. Full investigation (Enrich→RCA→Fix) takes 3–8 min depending on evidence volume. Parallel evidence collection (Feature 3) helps. A triage-only fast-path could be added as a pipeline variant — not yet built. |
| **Adaptive Mode** — Agent evaluates findings, decides to stop or auto-escalate | 🟡 | Confidence gate: if RCA confidence is LOW after 2 retries → escalation node fires and skips fix strategy. Agent-decides-depth pattern is partially implemented. Not full adaptive depth selection (no "just triage, not full RCA" decision branch yet). |
| **Runbook-guided triage** — Encodes on-call checks as structured runbook steps | ✅ | `strategy/runbook_builder.py` auto-generates runbooks from investigation patterns. Runbook toolset in `toolsets/runbooks.py`. Knowledge loader (`core/knowledge_loader.py`) injects runbook content into RCA context. On-call checks are encoded in prompt templates. |
| **Configurable escalation policy** — Teams define high-impact criteria, always/never escalate | 🟡 | Confidence-based escalation is config-driven (`policies/investigation.yaml`). Per-team escalation policies (which alerts always escalate, custom impact thresholds) are not yet implemented — currently global policy only. |
| **Alert enrichment** — Alert arrives with context before engineer is paged | ✅ | F1 Autonomous Agent investigates before paging. Teams notification includes: RCA summary, causal chain, proposed fix actions, evidence sources queried, confidence score. Engineer starts with a full investigation result, not a raw alert. |
| **Signal-to-noise consolidation** — Cascading alerts collapse into one incident story | 🟡 | `strategy/alert_correlation.py` exists. Groups related alerts. Does not yet produce a causal-ordered "primary cause + downstream symptoms" narrative automatically — outputs correlated alert groups, not a unified incident story. |
| **Noise detection and tuning** — Flags noisy alerts, surfaces common root cause behind repeat classes | 🟡 | `triggers/predictive.py` detects repeat patterns. `triggers/prediction_penalty.py` tracks penalty signals. Does not yet surface explicit "this alert class fires 40 times/month — here is the fix" tuning recommendation to operators. |

---

### Incidents

| Feature | Corvin | Evidence / Notes |
|---|---|---|
| **Swarm of specialized agents** — Domain agents investigate in parallel from different hypotheses | 🟡 | F9 has 3 specialist agents (Evidence Collector, RCA Analyst, Fix Strategist). F8 generates 3 competing hypotheses (infrastructure/code/dependency). Agents are sequential today — LangGraph migration (Feature 11) enables parallel node execution. True parallelism is post-4-weeks. |
| **Specialized agents per domain** — Distinct agents tuned per investigation domain | 🟡 | 3 agents with different system prompts and scopes. Multi-model routing (Feature 10) assigns high-reasoning model to causal tasks, fast model to tool calls — functional specialization exists. Not domain-tuned on incident data (no fine-tuning). |
| **Independent verification** — Verifier validates findings against production evidence | ✅ | Critic/Reflection Pass (Feature 5): independent LLM pass reviews every RCA claim against the evidence bundle. Unsupported claims are flagged. Confidence score is adjusted. This is structurally identical to independent verification. |
| **Dynamic tool calls** — Agent decides which tool and query to use, reformulates on bad results | ✅ | ReAct loop: agent selects tools dynamically from 15+ tool schemas based on investigation context. Tool results are appended to the message thread — agent sees results and can reformulate follow-up queries. Low-quality results trigger retry or different tool selection. |
| **Hypothesis revision** — When evidence contradicts current path, branches to alternatives | ✅ | Three mechanisms: (1) F8 generates 3 competing hypotheses upfront; (2) Critic flags unsupported claims and surfaces alternatives; (3) Low-confidence retry re-runs RCA with broadened evidence and alternative angle emphasis. |
| **Root cause with cited evidence** — Every claim linked to log line, metric, trace, or code diff | ✅ | Evidence Audit Panel (Feature 9): every RCA claim is linked to the specific log line, metric value, or event that supports it. SRE can search raw evidence and verify each claim. Critic flags claims with no evidence link. |
| **First-team-right routing** — Routes to correct owner when root cause is outside paged team | ❌ | No service ownership model or team routing logic implemented. Corvin produces the RCA and fix recommendation — manual routing to the correct team. Would require a CMDB/service catalog integration with ownership metadata. |
| **Incident channel context capture** — Ingests Slack/Teams channel messages as investigation context | 🟡 | Teams integration delivers findings to channels. Does NOT yet ingest channel messages as investigation context (read from Teams). One-directional: Corvin → Teams. Bidirectional (Teams → Corvin context) is not implemented. |
| **Proactive evidence-backed posting** — Posts new findings to channel without being mentioned | ❌ | Corvin posts investigation results when triggered. Does not monitor channels and post proactively as new evidence emerges. |
| **Catch-up summaries for new joiners** | ❌ | Not implemented. Postmortem is the closest artifact but it is not a real-time "here is what has happened so far" summary delivered privately. |
| **Postmortem generation** | ✅ | `strategy/postmortem_service.py`: blameless postmortem document generated from investigation data. Timeline, impact, RCA, prevention recommendations. Caches in Postgres. Delivered to ADO Wiki and SharePoint. Solid implementation. |

---

### Production Tasks

| Feature | Corvin | Evidence / Notes |
|---|---|---|
| **Deployment monitoring** — Watches every rollout for anomalies, investigates before alerts | 🟡 | Azure Activity Log adapter correlates recent deployments with incidents. `triggers/predictive.py` monitors for anomalies. Does not yet continuously watch rollouts in real-time — triggers post-alert, not pre-alert. |
| **Scheduled and triggered workflows** — Agents run on cadence or production triggers | 🟡 | `triggers/predictive.py` runs on schedule. `triggers/azure_alert.py` fires on webhook. No configurable workflow scheduler or template library yet. |
| **Operational reporting** — SLO reports, on-call handovers, change-risk briefs on schedule | ✅ | `strategy/roi.py` (ROI reports), `strategy/sla.py` (SLA tracking), `strategy/compliance_pack.py` (compliance evidence), `delivery/rca_notification.py`, `delivery/rca_pdf.py`. Scheduled report delivery via existing delivery adapters. Solid. |
| **Regression and anomaly lead time** — Catches regressions before they page | 🟡 | `triggers/predictive.py` with heuristic thresholds gives advance warning. Not ML-trained — rule-based. Improves only when rules are manually updated, not through automatic pattern learning. |
| **Template library** — Pre-built workflow templates | ❌ | No template library. Runbook builder generates runbooks from incidents but there is no library of pre-built investigation workflow templates to start from. |

---

### Conversational Production Queries

| Feature | Corvin | Evidence / Notes |
|---|---|---|
| **Natural language production access** — Any engineer queries production in plain English | ✅ | `strategy/agent_service.py` + `strategy/nl_to_kql.py`: natural language → KQL query → Azure Monitor / Elastic results. ReAct chat agent handles multi-turn queries. Any engineer (not just on-call) can use the chat interface. |
| **On-call prep and handoff summaries** — Shift brief with current telemetry and investigation state | 🟡 | `strategy/chat_service.py` supports multi-turn investigation context. No dedicated "shift brief" feature — engineer would manually query for this. Producing a shift brief via a prompt template is straightforward to add. |
| **Internal terminology mapping** — Maps team's service names and jargon to correct services | 🟡 | `investigation/prompt_builder.py` injects service context (name, environment, namespace) into every prompt. Connector registry maps service names to data sources. Explicit "PartnerAPI = payments-service-v2" jargon mapping is not a formalized feature — would require a terminology config file. |

---

## SECTION 3 — PLATFORM

### Models

| Feature | Corvin | Evidence / Notes |
|---|---|---|
| **Domain-specialized post-trained models** — Models trained on production incident data | ❌ | Uses Azure OpenAI foundation models (GPT-4o, GPT-4.1, GPT-4.1-mini). No fine-tuning on incident data. Compensates with: evidence-grounded prompts, hypothesis angle forcing, critic pass, RAGAS evals. Foundation models are highly capable for this domain with good prompting. |
| **Managed frontier models** — Frontier models managed and paired with specialized models | ✅ | GPT-4o (reasoning), GPT-4.1 (RCA generation, critic), GPT-4.1-mini (tool calls, summarization) via Azure OpenAI. LiteLLM manages model routing and version abstraction. |
| **Per-task model selection** — Best model for each specific task | ✅ | Feature 10 (Multi-Model Routing): `core/model_router.py` routes each task type to the appropriate model tier. P1 incidents → high-reasoning path. Tool calls → fast/cheap path. Causal reasoning always → highest-tier model. |
| **Orchestration across model releases** — Platform absorbs model churn | ✅ | LiteLLM + `litellm.drop_params = True` + `litellm.reasoning_auto_summary = True`: model-agnostic call layer. When Azure OpenAI releases a new model version, only the config value in `config/models/llm.yaml` needs updating. No code changes. |

---

### Context

| Feature | Corvin | Evidence / Notes |
|---|---|---|
| **Persistent knowledge graph** — Services, dependencies, deploy history, runbooks, incident timelines | 🟡 | Components exist but not assembled into a unified knowledge graph: pgvector on past RCAs (semantic memory), Activity Log for deploy history, knowledge_loader for runbooks/wikis, topology.py for service dependencies. No single queryable graph — these are separate stores. |
| **Real-time updates** — Topology and production state updates continuously | 🟡 | Evidence is collected fresh per investigation (not from a cached graph). Azure Monitor queries are always real-time. Topology is resolved per investigation via AKS API. No continuous background topology monitoring between investigations. |
| **Knowledge graph auditability** — Teams can inspect what the system believes and correct it | 🟡 | Investigation history, RCAs, and evidence bundles are fully queryable in Postgres. RAG retrieved incidents are visible in investigation context. No dedicated "knowledge graph inspection UI" — data is in Postgres, not a graph visualisation. |
| **Implicit learning** — Improves from engineer corrections without retraining | 🟡 | RAG on past incidents with HyDE (Feature 8) improves retrieval as more investigations are indexed. Engineer hypothesis selection (F8) feeds back into which incident patterns are associated with which root causes. No formal "correction feedback loop" — engineer selects the winning hypothesis, that selection is stored, future retrieval weighs confirmed patterns. |

---

### Actions

| Feature | Corvin | Evidence / Notes |
|---|---|---|
| **Alert actions** — Silences/snoozes alerts, executes predefined actions, routes | ❌ | No alert management actions implemented. Corvin is an investigation platform, not an alert manager. Would require Azure Monitor alert management API integration. |
| **Remediation actions** — Reverts commits, opens PRs, executes GitHub Actions, runs config changes | 🟡 | AKS actions: restart pods, rollback deployment, scale deployment (via AKS adapter, HITL gated). Azure DevOps integration exists for ADO wiki/work items. GitHub/PR-opening is not implemented. Config change execution is not implemented. |
| **Read and write across the stack** — Read logs/traces/metrics, write rollbacks/configs when approved | ✅ | Read: Azure Monitor (KQL), AKS K8s API, Elastic, Azure Activity. Write: AKS deployments (restart/rollback/scale) with HITL approval. Playwright validation post-action. Read is comprehensive; write is K8s-scoped. |
| **Guardrailed execution** — Every action within defined boundaries | ✅ | Hard HITL gate in `execution/execution_service.py`: `approval_status != APPROVED` blocks all execution absolutely. Confidence gate adds a soft guardrail before fix strategy generation. No approval = no action, always. |
| **Approval workflows** — Write actions require approval, full capture of request/execution/impact | ✅ | Teams notification with approval buttons. `approved_by` and `approved_at` fields in DB. Execution blocked until explicit approval. Post-execution Playwright validation captures impact. Complete audit trail. |
| **Outcome verification** — After executing, verifies intended effect | ✅ | `validations/playwright_runner.py` + `validations/runner.py`: automated validation after fix execution verifies service health. Not just assumes success. |
| **Full action audit trail** — Every action and reasoning logged per investigation | ✅ | Every tool call, RCA, fix action, approval event, execution result, and validation outcome stored in Postgres per `request_id`. Full investigation audit trail queryable. |

---

### Scalability

| Feature | Corvin | Evidence / Notes |
|---|---|---|
| **Concurrent investigation handling** — Handles many parallel investigations and high volumes | 🟡 | FastAPI async architecture supports concurrent requests. Each investigation is independent. No explicit load testing done. Rate limiting on Azure OpenAI is the practical bottleneck — TPM limits. Deployable on AKS with horizontal scaling. |
| **Schema-change adaptation** — Adapts to log/telemetry schema changes without retraining | ✅ | LLM-based tool call generation dynamically formulates queries. KQL templates use parameterized patterns. Schema changes in Container Insights or APIM tables require at most a KQL template update — no retraining or parser rebuilding. |
| **Rapid team and service onboarding** — New team/service added without vendor PS, in one day | ✅ | Connector registry: per-service `source_type` config + namespace + workspace ID. No vendor professional services required. Single config entry per service. Self-service. |

---

## SECTION 4 — UI

### Collaborative Investigation IDE

| Feature | Corvin | Evidence / Notes |
|---|---|---|
| **Shared investigation surface** — Engineers and agents investigate on same evidence surface | 🟡 | SSE streaming delivers real-time investigation events to the frontend. Evidence Audit Panel (Feature 9) shows all evidence. Multi-user simultaneous viewing is not implemented — investigation is single-user initiated, viewable by others via shared URL. |
| **Real-time visibility** — Live view into hypotheses being pursued, evidence gathered | ✅ | SSE stream with typed events: `thinking`, `tool_call`, `tool_result`, `text`. Frontend sees every tool the agent selects and every result it receives as they happen. Causal chain rendered as Mermaid flowchart. |
| **Per-agent work review** — Engineers see each agent's specific work and evidence | ✅ | Full audit trail stored per agent: Evidence Collector output, RCA Analyst output, Fix Strategist output all separately queryable. Investigation audit trail endpoint. Evidence Audit Panel links evidence to claims per agent contribution. |
| **Evidence and hypothesis exploration** — Explore evidence/hypotheses without losing context | ✅ | F8 hypothesis panel: 3 competing hypotheses with evidence support, selectable. Evidence Audit Panel: searchable raw evidence linked to claims. Investigation continues while SRE reviews evidence. |
| **Private parallel investigations** — Run private investigation thread alongside main | ❌ | Not implemented. Single investigation thread per request. |
| **Investigation steering** — Redirect mid-flight, agent preserves context and cites pivot reason | 🟡 | Hypothesis selection effectively steers the investigation (selecting h2 over h1 causes fix strategy to regenerate from h2's root cause). Mid-flight tool call steering via chat is partially implemented. Formal "pivot with reason preserved" is not a dedicated feature. |
| **Teammate tag-in** — Tag teammates with shared investigation state | ❌ | Not implemented. Teams notification is sent to a configured channel — not a per-teammate tag-in with state handoff. |

---

### Chat Surfaces

| Feature | Corvin | Evidence / Notes |
|---|---|---|
| **Slack-native workflow** — Findings posted to incident channels, investigation redirectable from Slack | ❌ | Teams only. No Slack integration. This is a significant gap for organizations using Slack as primary incident channel. |
| **MS Teams** — Available in Teams for context capture and in-channel answers | ✅ | `delivery/teams_adapter.py`: full Teams integration. Sends investigation results, approval buttons, RCA summaries, causal chain. Bidirectional approval flow from Teams. |
| **CLI and web** | 🟡 | Web interface exists (FastAPI frontend). CLI for migrations (`cli/migrate_config.py`). No dedicated investigation CLI (e.g., `corvin investigate --service payments-api --alert "high error rate"`). |
| **Natural language from any surface** | 🟡 | Web + Teams surfaces. API for programmatic access. Slack is missing. Context maintained across turns in `strategy/chat_service.py`. |

---

## SECTION 5 — EXTENSIBILITY

| Feature | Corvin | Evidence / Notes |
|---|---|---|
| **MCP server** — Available as MCP server for external agents | ❌ | No MCP (Model Context Protocol) implementation. Tools are OpenAI-format schemas, internal only. Adding MCP is a medium-effort addition — tool schemas already exist, wrapping them as MCP server endpoints is feasible. |
| **Public API** — Programmatic access to capabilities | ✅ | FastAPI REST API: investigations, hypotheses, approvals, execution, evidence, postmortems, chat. All core capabilities accessible programmatically. |
| **Your skills in Resolve** — Codify expertise as composable Skills | 🟡 | Tools in `strategy/agent_tools.py` are the analog of Skills. Adding a new tool requires: adding a schema to TOOL_SCHEMAS and an executor function. Not a formalized "Skills" abstraction with metadata and lifecycle — it's direct code extension. |
| **Build custom agents** | 🟡 | The codebase is open Python — custom agents can be built by extending the multi_agent.py framework or adding LangGraph nodes (Feature 11). No no-code agent builder or visual workflow designer. Engineering capability to build custom agents: yes. Product-level self-service for non-engineers: no. |

---

## SECTION 6 — INTEGRATION COVERAGE

| Feature | Corvin | Evidence / Notes |
|---|---|---|
| **Observability stack coverage** — Connects to observability tools in GA, correlates metrics/logs/traces | 🟡 | **GA**: Azure Monitor (deep — Container Insights, Log Analytics, Metrics API), Elastic/OpenSearch. **Partial**: Splunk (planned). **Missing**: Datadog, New Relic, Prometheus (native scrape), Dynatrace, AppDynamics. For Azure-native stacks: full coverage. For mixed stacks: gaps. |
| **Infrastructure coverage** — Kubernetes, VMs, bare metal, cloud-native, non-containerized | 🟡 | **Full**: AKS/Kubernetes. **Good**: Azure VMs (Azure Monitor AMA), Azure Functions, Event Hub, APIM. **Limited**: Bare metal (only if Azure Arc or Elastic agent installed). **Missing**: Non-Azure cloud-native services as first-class. |
| **Code and repository coverage** — Source, diffs, deployment history for investigation reasoning | 🟡 | `connectors/git_repo.py`: git repository connector. `investigation/code_enrichment.py`: enriches investigation with code context. Azure DevOps integration for deploy history. GitHub support is partial — no native GitHub Actions or PR integration. |
| **CI/CD and deployment coverage** — Correlates deploy events to anomalies | 🟡 | Azure Activity Log captures Azure DevOps deployments. Activity Log adapter correlates "what changed recently" with the incident. GitHub Actions and other CI/CD tools not directly integrated. |
| **Incident management coverage** — Connects to paging and incident tooling | 🟡 | **Yes**: Teams (notification + approval). **Missing**: PagerDuty, OpsGenie, ServiceNow, Jira Service Management. These are common paging tools in enterprise — their absence means Corvin cannot start an investigation automatically when a PagerDuty alert fires (only Azure Monitor webhook). |
| **Knowledge and documentation coverage** — Runbooks, wikis, repos accessible to investigations | ✅ | `core/knowledge_loader.py`: loads internal knowledge into context. ADO Wiki adapter reads and writes. SharePoint integration for documentation. Runbook builder generates runbooks. Knowledge is injected into every investigation prompt via `investigation/prompt_builder.py`. |
| **Cross-tool correlation** — Traces symptom in one tool to root cause in another | ✅ | Demonstrated: APIM 5xx (ApiManagementGatewayLogs) → pod crash (KubePodInventory + KubeEvents) → deployment (AzureActivity) — traced in a single investigation across three tools. This is the core differentiator and it works. |
| **Breadth of pre-built integrations** — 60+ pre-built integrations | 🟡 | ~15–20 deep Azure integrations. Well below 60+. Depth vs breadth trade-off: Corvin has deeper Azure tooling than any competitor, but narrower total integration count. |
| **Heterogeneous-environment handling** — Non-standard stacks without vendor PS | 🟡 | Azure-native heterogeneous (AKS + APIM + Functions + Event Hub + VMs): handled. Non-Azure heterogeneous (on-prem VMs, non-Azure K8s, Graphite, custom tooling): requires adapter development. The connector framework makes adding new sources straightforward — but it's engineering work. |

---

## SECTION 7 — ONBOARDING & TIME TO VALUE

| Feature | Corvin | Evidence / Notes |
|---|---|---|
| **Plug-and-play start** — Delivers value without lengthy services-led implementation | 🟡 | For Azure-native stacks: connector registry + config YAML → working in 1–2 days. For non-Azure stacks: adapter development needed. Not a 5-minute SaaS onboarding, but a self-service connector model with reasonable setup time. |
| **Continuous learning built in** | ✅ | RAG with HyDE (Feature 8): every completed investigation is indexed as an embedding. Future investigations retrieve semantically similar past incidents automatically. Learning is fully automatic — no manual curation required. |
| **No per-team professional services** | ✅ | Connector registry is self-service. New team = new connector config entry. No Corvin vendor involvement needed after initial deployment. |
| **Self-service onboarding** | 🟡 | Self-service for Azure-native services. Non-Azure sources require an engineer to write a new adapter (Python class implementing the adapter interface). Not a no-code onboarding experience for custom sources. |
| **Forward-deployed engineers (FDEs)** | ❌ | Corvin is self-hosted software. No FDE delivery model. The team that owns the deployment IS the forward-deployed engineer. For MetLife: this means internal SRE team owns the deployment — which is exactly what MetLife wants (data sovereignty). |
| **AI engagement managers** | ❌ | Not a SaaS product with customer success function. Internal team drives adoption. |

---

## SECTION 8 — SECURITY & COMPLIANCE

| Feature | Corvin | Evidence / Notes |
|---|---|---|
| **Raw telemetry residency** — Logs, metrics, traces stay in your environment | ✅ | Fully self-hosted in customer Azure tenant. No Corvin backend, no external API calls with customer data. Azure OpenAI is in customer's own subscription — tokens do not leave the Azure tenant. |
| **In-VPC component** — Integrations operate within private network | ✅ | Deployed on customer AKS. All adapter calls go within Azure VNet (Azure Monitor private link compatible, Elastic within VNet, K8s API is internal). No public internet data path. |
| **Data egress scope documentation** | 🟡 | Corvin does not send data outside the customer VNet. Documentation of what data flows where (which service calls which API, what token content) can be produced — not pre-built but derivable from the codebase. A data flow diagram can be created for the POC. |
| **Cloud egress cost transparency** | 🟡 | Azure Monitor API calls are within-tenant (no egress). LLM token costs (Azure OpenAI) are within-tenant. No cross-region or cross-tenant data transfer unless Azure OpenAI model is deployed in a different region — configurable to avoid. |
| **Data redaction** — Sensitive data redacted before reaching vendor environment | ✅ | Feature 2 (PII Redaction): PII detected and redacted before LLM injection. Redaction map stored per investigation for SRE recovery. Configurable redaction rules in policy config. No "vendor environment" — data never leaves customer tenant. |
| **Tenant isolation** | ✅ | Single-tenant by architecture. One Corvin deployment = one customer. No shared infrastructure. Cryptographic isolation is the entire Azure tenant boundary. |
| **Deployment options** — SaaS, BYOC, self-hosted | ✅ | Self-hosted on customer AKS (primary). Azure Container Apps option. BYOC via managed deployment in customer's Azure subscription. True SaaS (Corvin-hosted) not currently offered — but this is a feature, not a gap, for regulated enterprises. |
| **SOC 2 Type II** | ❌ | No audit conducted. Self-hosted architecture significantly reduces scope — there is no Corvin cloud processing customer data, so the SOC 2 risk surface is the deployment process, not data handling. Frame: "Customer controls the SOC 2 boundary — there is no vendor cloud." |
| **GDPR / HIPAA / PCI-DSS** | 🟡 | GDPR: strong posture — data stays in EU Azure region, PII redacted before LLM injection, no cross-border transfer. HIPAA/PCI: self-hosted means customer PHI/PCI data never leaves their environment. No formal certifications. Compliance posture is strong by architecture; certifications require audit. |
| **RBAC and access control** | 🟡 | Approval gate is role-based (approver vs. viewer). Investigation initiation is controlled. Full RBAC (team-scoped permissions, read vs. write roles, investigation visibility scoping) is not fully implemented. Azure AD integration for identity exists via Azure default credentials. |
| **Audit trails** | ✅ | Full investigation audit trail: every tool call, every LLM response, every hypothesis, every approval action, every execution, every validation — stored per `request_id` in Postgres. OTel tracing (Feature 13) adds span-level trace to Azure Monitor. |
| **Hierarchical guardrails** — Org/team/personal guardrail levels | ❌ | Single-level confidence and approval guardrails. No org→team→personal hierarchy. The approval gate is binary (approved/not). Configurable confidence thresholds per environment but not per team. |

---

## SECTION 9 — COMPANY & VENDOR VIABILITY

| Feature | Corvin | Evidence / Notes |
|---|---|---|
| **Production references at scale** | ❌ | Competition winner, no enterprise production deployments. For the review: position as "first enterprise POC = MetLife" and frame the lack of existing customers as an opportunity, not a gap. |
| **Customer expansion evidence** | ❌ | No existing customers to expand. N/A at this stage. |
| **Dedicated AI research organization** | ❌ | Single team. Compensate with: documented RAGAS eval infrastructure, continuous improvement pipeline, public architecture transparency — which commercial vendors don't offer. |
| **Post-trained models on production incident data** | ❌ | Foundation models only. Counter argument: foundation models (GPT-4o, Claude) are state-of-the-art reasoning systems. Fine-tuning is a performance optimization on specific tasks, not a correctness requirement. Corvin's evidence-grounded architecture + critic pass compensates architecturally. |
| **Continuous evaluation infrastructure** | ✅ | RAGAS eval pipeline (Feature 14): automated evaluation across 10+ incident types. Runs on-demand or scheduled. Catches silent regression when LLM models update. Eval cases are versioned JSONL. This is more rigorous than most commercial vendors disclose. |
| **Model migration absorption** | ✅ | LiteLLM + config-driven model selection: when Azure OpenAI releases a new model, one config value changes. `litellm.drop_params = True` handles parameter compatibility. No customer-visible disruption. |
| **Funding and team depth** | 🟡 | Competition winner with demonstrated product quality. Not externally funded. Self-hosted model reduces burn rate significantly (no cloud infrastructure to maintain). Team depth: needs honest disclosure. For a regulated enterprise: this is a risk factor. |
| **Roadmap commitments** | ✅ | 4-week improvement plan with specific feature delivery dates is documented. Post-4-week roadmap includes: LangGraph pipeline, MCP server, PagerDuty integration, Slack integration, CMDB-based routing, fine-tuning on accumulated incident data. Committed, specific, time-bounded. |

---

## SECTION 10 — NPI ADVISORY CHECKLIST RESPONSE

This checklist is strategic/procurement guidance for the buyer (MetLife). Corvin's response to each advisory:

| NPI Area | Advisory | Corvin's Position |
|---|---|---|
| **RFP Structure** | Split evaluation: AIOps (event pipeline) vs AI SRE (investigation) | Corvin is AI SRE, not AIOps. Do not compete against BigPanda on alert correlation. Compete on: investigation depth, Azure-native tooling, data sovereignty. Run Corvin in the AI SRE track only. |
| **Vendor Comparison** | Map vendors to specific use cases | Corvin's use case: "Deep RCA investigation for Azure APIM + AKS workloads with full data sovereignty." This is a narrower claim than NeuBird's ("universal production operations") but more honest and more defensible in POC. |
| **Capability Focus** | Prioritize based on primary pain point | If MetLife's primary pain is manual RCA time, Corvin is directly on point. If primary pain is alert noise volume, BigPanda is the right tool and Corvin is complementary. |
| **POC Approach** | Use real historical incidents with known outcomes | Corvin is designed for this. Real Azure Monitor / Elastic logs, real past incidents, verifiable root causes. Corvin's RAGAS eval pipeline is built for exactly this validation. Propose a 30-day POC with 10 real historical incidents and known root causes. |
| **POC Validation Metrics** | Measure accuracy, false positives, RCA quality | Corvin produces: RAGAS Faithfulness, Answer Relevance, Context Precision scores per investigation. Define success as: composite RAGAS ≥ 0.75 on 80% of POC cases. This is quantifiable upfront. |
| **Integration Evaluation** | Assess depth of integration (ServiceNow, Elastic, etc.) | Corvin's Azure Monitor + Elastic depth is demonstrable in POC. ServiceNow and PagerDuty integrations are gaps — acknowledge them and provide a timeline (post-4-week roadmap). |
| **Data Readiness** | Validate CMDB, logs, and alert quality before POC | Corvin requires: Azure Monitor Container Insights enabled, APIM diagnostics configured, Elastic deployed (or fall back to Container Logs). Data readiness assessment can be run in 1 day against MetLife's environment. |
| **Scalability Testing** | Test at enterprise-scale volumes | Include in POC: 1,000 investigations/month simulation. Azure Container Apps auto-scaling. Load test Azure OpenAI TPM limits. This is a real test, not a demo. |
| **Vendor Maturity** | Include vendor viability scoring | Be transparent: early-stage, self-hosted, competition-proven but no enterprise production deployments. The risk mitigation is: self-hosted (no vendor lock-in), open architecture (no black box), POC-tied contract (no risk until value proven). |
| **Pricing Transparency** | Request normalized pricing scenarios | Corvin pricing is fully transparent and deterministic: infrastructure cost (published Azure pricing) + Azure OpenAI consumption ($0.16/investigation). No surprise costs. Contrast this with NeuBird ($15/credit) or BigPanda ($230K+/year). |
| **Cost Risk** | Usage-based models create cost volatility | Corvin cost is bounded: Azure OpenAI TPM limits cap LLM spend. Infrastructure is fixed. No per-investigation billing from Corvin. Cost is entirely within customer's Azure subscription — customer has full control. |
| **Discounting Reality** | Focus on unit economics, not discount % | Corvin has no vendor discount to negotiate — it's self-hosted infrastructure + Azure consumption. Unit economics: ~$0.16/investigation vs NeuBird's $15/investigation. 94x lower per-investigation cost at equivalent scale. |
| **Commercial Leverage** | Push for aggressive pricing and favorable terms | Corvin is self-hosted software. No ongoing vendor commercial relationship to negotiate. License fee or support contract is the commercial structure — MetLife has full leverage since there's no dependency on Corvin infrastructure. |
| **Contract Protections** | Secure exit terms, data portability, rate protections | Not applicable in the traditional sense — Corvin runs in MetLife's Azure. All data, models, embeddings, investigation history stay in MetLife's environment. Exit = remove the deployment. No lock-in by architecture. |
| **Consumption Control** | Define limits on usage-based pricing | MetLife controls Azure OpenAI TPM via Azure portal. Investigation concurrency is controllable via AKS deployment settings. No external vendor can cause unexpected consumption spikes. |
| **Rate Stability** | Lock pricing for multi-year deals | Azure OpenAI pricing is independent of Corvin. Corvin's license/support fee (if any) is the only Corvin-specific cost — fully negotiable. |
| **POC-Based Contracting** | Tie agreements to POC success | Corvin supports this directly: propose a no-cost 30-day POC (MetLife pays only their own Azure OpenAI consumption) with clearly defined RAGAS success criteria. License/support fees only commence if POC passes. |
| **Security & Governance** | No data training, strong access control, auditability | No data training: Azure OpenAI does not train on customer data by default. Access control: Azure AD + HITL approval gate. Auditability: full investigation audit trail per request_id. |
| **Exit Strategy** | Data export and transition support | All data in MetLife's Postgres database. Full export via standard SQL. Embeddings in pgvector — exportable. No proprietary format. Running the Corvin codebase is not required to export historical data. |
| **Vendor Strategy** | Include incumbents (ServiceNow, Splunk) as benchmarks | Corvin is not positioning against ServiceNow (ITSM) or Splunk (log management) — these are complementary. Splunk integration is on the roadmap. Frame Corvin as the AI investigation layer that works alongside existing tools. |

---

## SUMMARY SCORECARD

### By Section (post all improvements)

| Section | Score | Key Strength | Key Gap |
|---|---|---|---|
| Must-Pass (8 items) | 3✅ 3🟡 2❌ | Cross-tool correlation, telemetry residency, hypothesis revision | Production references, SOC 2 |
| Use Cases — Alerts | 4✅ 4🟡 0❌ | Alert enrichment, runbook-guided triage | Triage-only mode, noise tuning |
| Use Cases — Incidents | 5✅ 3🟡 3❌ | Evidence audit panel, critic verification, dynamic tools | Team routing, channel monitoring, catch-up summaries |
| Use Cases — Production | 2✅ 2🟡 1❌ | Operational reporting, scheduled triggers | Template library |
| Use Cases — Conversational | 2✅ 1🟡 0❌ | Natural language queries, multi-turn context | Shift brief, terminology mapping |
| Platform — Models | 3✅ 0🟡 1❌ | Per-task routing, model migration absorption | No fine-tuned models |
| Platform — Context | 0✅ 4🟡 0❌ | Fresh real-time evidence | No unified knowledge graph |
| Platform — Actions | 5✅ 1🟡 1❌ | HITL gate, outcome verification, audit trail | Alert actions (silence/snooze) |
| Platform — Scalability | 2✅ 1🟡 0❌ | Schema adaptation, rapid onboarding | Load testing not done |
| UI | 3✅ 3🟡 2❌ | Real-time SSE, per-agent review, hypothesis exploration | Slack, private threads, teammate tag-in |
| Extensibility | 2✅ 2🟡 1❌ | Public API, custom tools | No MCP server |
| Integration Coverage | 3✅ 6🟡 0❌ | Cross-tool correlation, knowledge/docs, code | 15 integrations vs 60+ expected |
| Onboarding | 3✅ 2🟡 2❌ | Continuous learning, no-PS onboarding | No FDE/CSM model |
| Security & Compliance | 6✅ 4🟡 2❌ | Data sovereignty, PII redaction, audit trails | SOC 2, hierarchical guardrails |
| Vendor Viability | 3✅ 1🟡 4❌ | RAGAS evals, model migration, roadmap | No production refs, no funding |

---

### Top 5 Strengths to Lead With in the Review

1. **Azure-native depth that no competitor matches**: 20+ APIM KQL templates, 12 Container Insights queries, Activity Log change correlation — all purpose-built for Azure stacks. Cross-tool correlation is demonstrable in POC.

2. **Full data sovereignty by architecture**: Nothing leaves the customer Azure tenant. No vendor cloud, no shared infrastructure, no data training risk. SOC 2 scope is entirely within MetLife's compliance boundary.

3. **Transparent trust model**: Evidence Audit Panel links every RCA claim to specific evidence. SRE verifies, not trusts. More honest and auditable than black-box vendor verification claims.

4. **Cost model is structurally superior**: ~$0.16/investigation all-in. No per-credit pricing, no usage spikes, no vendor lock-in. MetLife controls all cost levers through their own Azure subscription.

5. **POC-ready with measurable success criteria**: RAGAS eval pipeline produces objective accuracy scores. Propose: 30 real historical incidents, RAGAS ≥ 0.75 composite on 80% = success. Quantifiable, not demo theatre.

---

### Top 5 Gaps to Acknowledge Proactively

1. **No production references** — Be first, with a no-risk POC structure.
2. **No SOC 2** — Frame: self-hosted means MetLife owns the compliance boundary. Offer a data flow diagram.
3. **Integration breadth** — 15 deep vs 60+ broad. Offer: Azure stack is complete; non-Azure integrations have a published roadmap.
4. **No Slack** — Teams-only today. Slack is on the post-4-week roadmap.
5. **No PagerDuty / ServiceNow** — Investigation triggers only from Azure Monitor webhooks today. PagerDuty and ServiceNow webhook integration is feasible and on roadmap.
