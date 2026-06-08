# Corvin — Platform Architecture, Current State & Improvement Roadmap

> **Purpose**: Authoritative internal reference for the Global SRE Expert review.  
> Covers what Corvin does today (honest, with gaps named), and the post-improvement
> target state with implementation-ready prompts for each feature.

---

## PART 1 — CORVIN TODAY (Current State)

---

### 1.1 What Corvin Is

Corvin is a self-hosted, Azure-native AI SRE Copilot that autonomously investigates
production incidents, generates root-cause analysis, proposes fix strategies, and
optionally executes approved remediations. It runs entirely inside the customer's Azure
tenant — logs, embeddings, RCAs, and session data never leave the customer's environment.

It is not a monitoring tool. It does not ingest metrics or generate alerts. It receives
alerts (via webhook or manual trigger), investigates them by querying existing data
sources, and returns structured findings to SRE teams.

**Positioning**: Self-hosted, Azure-sovereign alternative to NeuBird / Flip.AI for
organizations where data residency is non-negotiable.

---

### 1.2 Architecture Overview

```
Trigger Layer          Evidence Layer             Intelligence Layer        Delivery Layer
─────────────          ──────────────             ──────────────────        ──────────────
Azure Monitor    ──►   Container Insights   ──►   Investigation Engine ──►  Teams
Webhook               APIM Log Analytics          RCA Generator             Email
Manual trigger         AKS Kubernetes API          Fix Strategy Generator    SharePoint
Predictive alerts      Azure Activity Log          Hypothesis Service        ADO Wiki
                       Elastic (optional)          Causal Chain              PDF Export
                       Splunk (optional)           Post-Mortem Generator
                                                   Autonomous Agent
                                                   Multi-Agent Orchestrator
                                                   ReAct Chat Agent
```

**Storage**: PostgreSQL (SQLAlchemy ORM) — investigation_requests, rca_outputs,
fix_strategy_outputs, evidence_bundles, post_mortems, chat_messages, hypotheses.
pgvector extension installed, schema stub present, no embeddings written yet.

**LLM**: Azure OpenAI via LiteLLM. Config-driven model selection. `litellm.drop_params = True`
for cross-model compatibility. `litellm.reasoning_auto_summary = True` for Responses API.

**Deployment**: Python/FastAPI. Runs on AKS, Azure Container Apps, or any Python environment.
Kubeconfig or in-cluster service account for K8s access.

---

### 1.3 Feature Inventory — Current State

#### 1.3.1 Investigation Engine (`corvin/investigation/engine.py`)

**Status**: ✅ Solid — production-ready pipeline

The `InvestigationEngine` owns the 4-stage V1 pipeline:

```
InvestigationRequest
  → EnrichmentService.enrich()        → EvidenceBundle
  → RCAGenerator.generate()           → RCAOutput
  → FixStrategyGenerator.generate()   → FixStrategyOutput
  → InvestigationResult
```

- Confidence gate: if RCA confidence is below configured threshold (`min_confidence_to_suggest_action`), fix strategy is skipped and a warning is surfaced. Does NOT retry — the gap.
- Code enrichment: `code_enrichment.py` optionally enriches with git context before RCA.
- Topology resolution: `topology.py` resolves service dependencies.
- Sequential execution: all stages run in series, no parallelism.

#### 1.3.2 RCA Generator (`corvin/strategy/rca_generator.py`)

**Status**: ✅ Solid with one critical gap

- LiteLLM structured output call with `response_format=json_object`.
- Pydantic validation of output against `RCAOutput` contract.
- Streaming via `generate_stream()` with non-streaming fallback on failure.
- `last_stream_status` tracks degraded states: `ok`, `insufficient_evidence`,
  `degraded_non_streaming`, `degraded_unparseable`, `degraded_failed`.
- Evidence-gate: rejects investigation if evidence bundle is empty.
- **Gap**: Self-reports its own confidence score. No external verification pass.
  Low confidence → warning logged, pipeline continues. No retry, no critique.

#### 1.3.3 Fix Strategy Generator (`corvin/strategy/fix_strategy_generator.py`)

**Status**: ✅ Solid

- Structured fix actions with risk level, rollback steps, rationale.
- Gated: only runs if RCA confidence meets threshold.
- Output tied to the winning hypothesis when debate mode is active.

#### 1.3.4 F1 — Autonomous Agent (`corvin/strategy/autonomous_agent.py`)

**Status**: ✅ Solid — the "3AM investigation" feature

The flagship autonomous capability. Fires on webhook alert, runs the full
investigation pipeline without human initiation, emits structured events, sends
Teams notification with proposed fix and approval buttons, then waits.

Event stages emitted: `investigation_started` → `evidence_collected` →
`rca_generated` → `fix_proposed` → `awaiting_approval`.

Depends on `InvestigationEngine` + `CausalChainGenerator` + `CommsDraftGenerator`
+ `TeamsAdapter`.

**Gap**: No OTel tracing. Events are emitted to a custom lightweight emitter,
not to Azure Monitor or any structured trace backend.

#### 1.3.5 F4 — Causal Chain Generator (`corvin/strategy/causal_chain.py`)

**Status**: ✅ Solid

Produces a directed cause-effect DAG from a completed `InvestigationResult`.
LLM outputs structured JSON: nodes (trigger/failure/cascade/impact categories)
and edges with causal link labels. Designed for Mermaid flowchart rendering
on the frontend. 4–8 nodes, evidence-referenced where possible.

#### 1.3.6 F8 — Hypothesis Service / Root Cause Debate (`corvin/strategy/hypothesis_service.py`)

**Status**: ✅ Novel — architecturally distinctive

Generates N competing root-cause hypotheses from a single LLM call with
forced angle diversity:
- h1: infrastructure angle (CPU/memory/OOM/node)
- h2: code/config change angle (deployment/env var/schema)
- h3: upstream dependency angle (external service/DNS/network)

SRE selects the winning hypothesis via `POST /investigations/{id}/select-hypothesis`.
The winner's root cause drives a fresh fix strategy generation.

**Honest assessment**: This is "multi-hypothesis generation from one LLM call",
not adversarial debate between agents. Valuable and novel — but architecturally
weaker than true debate. Named correctly in hypothesis_service.py docstring.

#### 1.3.7 F9 — Multi-Agent Orchestrator (`corvin/strategy/multi_agent.py`)

**Status**: 🟡 Partial — sequential pipeline disguised as multi-agent

Models the SelectorGroupChat pattern (AutoGen 0.4 style) with three specialist agents:
- `EvidenceCollectorAgent` — wraps EnrichmentService
- `RCAAnalystAgent` — wraps RCAGenerator  
- `FixStrategyAgent` — wraps FixStrategyGenerator

The `_select_next_agent()` fast-path is a hardcoded linear sequence:
`ORCHESTRATOR → EVIDENCE_COLLECTOR → RCA_ANALYST → FIX_STRATEGIST → done`

The LLM-based selector only fires when the simple role-based if/else fails,
meaning under normal conditions the LLM selector never runs. Max 12 turns.
Termination signal: `FIX_STRATEGY_COMPLETE` string in message content.

**Honest gap**: Agents do not communicate — outputs are passed as function
arguments, not as messages on a shared thread. RCA Analyst cannot ask
Evidence Collector for more data. No genuine multi-agent collaboration.

#### 1.3.8 ReAct Chat Agent (`corvin/strategy/agent_service.py` + `agent_tools.py`)

**Status**: ✅ Solid at ~75%

6-round tool-call loop with 15+ live tools. Correct OpenAI tool-call message
threading (tool calls and results appended to messages array). SSE streaming
with typed events: `thinking`, `tool_call`, `tool_result`, `text`.

**Gap**: No token budget check before appending tool results. A KQL returning
500 log lines silently fills the context window.

**Tool registry** (`agent_tools.py`): Static `TOOL_SCHEMAS` list — hardcoded at
startup. No per-service tool availability, no runtime tool registration.

Available tools include: `run_kql`, `query_apim_analytics`, `get_aks_health`,
`get_container_resource_metrics`, and ~11 more covering APIM, AKS, Container
Insights, Azure Activity, Elastic, knowledge base, runbooks, code analysis.

#### 1.3.9 Enrichment Service (`corvin/enrich/enrichment_service.py`)

**Status**: 🟡 Works but sequential

13 adapter calls run in series with `try/except` graceful skip on each:
Elastic logs → Elastic metrics → Container logs (fallback) → APIM logs →
Pod context → Resource metrics → Container inventory → Node inventory →
Network metrics → Pod restarts → OOM kill events → HPA events → Probe failures.

**Gap**: Sequential execution. At P1 incident response, total evidence collection
time = sum of all 13 adapter latencies. Should be `asyncio.gather()`.

#### 1.3.10 Evidence Adapters

| Adapter | File | Status | What It Queries |
|---|---|---|---|
| ContainerLogsAdapter | `evidence/container_logs_adapter.py` | ✅ | 12 Container Insights KQL queries (ContainerLogV2, KubePodInventory, KubeEvents, Perf, InsightsMetrics, KubeNodeInventory) |
| AKSAdapter | `evidence/aks_adapter.py` | ✅ read / ⚠️ write optional | K8s Python client — pod context, deployment state, pod logs. Write methods (restart/rollback/scale) require K8s write access |
| LogAnalyticsAdapter | `evidence/log_analytics_adapter.py` | ✅ | APIM gateway logs — ApiManagementGatewayLogs table |
| APIMAnalyticsAdapter | `evidence/apim_analytics_adapter.py` | ✅ | 20+ KQL templates: traffic, latency percentiles, error origin, top callers, URL segment analysis, TLS distribution |
| AzureActivityAdapter | `evidence/azure_activity_adapter.py` | ✅ | AzureActivity table — change correlation, recent deployments, config changes |
| ElasticAdapter | `evidence/elastic_adapter.py` | ✅ optional | Application logs (logs-*) and metrics (metrics-*) via Elasticsearch Query DSL |

All Azure Monitor adapters: `DefaultAzureCredential` → `LogsQueryClient` → KQL → `query_workspace()`.
No `MetricsQueryClient` — numerical platform metrics (AKS node CPU, APIM request counts) are
queried via KQL against LA Perf/InsightsMetrics tables instead of the free Metrics Store.

#### 1.3.11 Predictive Detection (`corvin/triggers/predictive.py`)

**Status**: 🟡 Heuristic-based, not ML

Rule-based heuristics comparing current metrics to thresholds derived from
recent investigation history. Emits `PredictiveAlert` with fields including
`estimated_breach_at`, `change_correlation`, `confidence_pct`.

Not a trained model. Patterns are hand-coded thresholds, not learned from data.
Sufficient for MVP demonstration but will not improve with deployment time unless
actively extended.

#### 1.3.12 Post-Mortem Generator (`corvin/strategy/postmortem_service.py`)

**Status**: ✅ Solid

Blameless post-mortem document generation. Deterministically assembles timeline,
impact, and RCA sections from persisted data. LLM called once for the
"Prevention & Future Actions" section only — reproducible even if model changes.
Cached in `post_mortems` table.

#### 1.3.13 Additional Strategy Services

| Service | File | Status | Function |
|---|---|---|---|
| Causal Chain | `strategy/causal_chain.py` | ✅ | Directed DAG from root cause to business impact |
| Comms Draft | `strategy/comms_draft.py` | ✅ | Auto-draft stakeholder communication |
| NL-to-KQL | `strategy/nl_to_kql.py` | ✅ | Natural language → KQL query translation |
| Runbook Builder | `strategy/runbook_builder.py` | ✅ | Auto-generate runbooks from investigation patterns |
| Blast Radius | `strategy/blast_radius.py` | ✅ | Estimate affected services/users |
| Alert Correlation | `strategy/alert_correlation.py` | ✅ | Correlate related alerts into incidents |
| Compliance Pack | `strategy/compliance_pack.py` | ✅ | Generate compliance evidence packs |
| ROI Calculator | `strategy/roi.py` | ✅ | Calculate time/cost savings per investigation |
| Capacity Forecaster | `strategy/capacity_forecaster.py` | ✅ | Resource capacity trend forecasting |
| SLA Tracker | `strategy/sla.py` | ✅ | SLA/SLO tracking against investigations |
| Similarity Network | `strategy/similarity_network.py` | ✅ | Service dependency similarity graph |
| Chaos Engine | `strategy/chaos_engine.py` | ✅ | Chaos scenario generation |
| Voice Incident | `strategy/voice_incident.py` | ✅ | Voice-based incident reporting |

#### 1.3.14 Delivery Layer (`corvin/delivery/`)

| Adapter | Status | Delivers |
|---|---|---|
| TeamsAdapter | ✅ | Incident notifications, approval buttons, RCA summaries |
| EmailAdapter | ✅ | RCA/postmortem email delivery |
| SharePointAdapter | ✅ | RCA documents to SharePoint |
| ADOWikiAdapter | ✅ | Post-mortems to Azure DevOps Wiki |
| AzureDevOpsAdapter | ✅ | Work items, PR linking |
| RCAPdfAdapter | ✅ | PDF export of RCA |

#### 1.3.15 Execution Layer (`corvin/execution/`)

- `execution_service.py`: Hard approval gate. `approval_status != APPROVED` blocks all execution.
- `chaos_executor.py`: kubectl-based chaos execution (pod delete, scale, rollout).
- `preview.py`: Dry-run preview of fix actions before approval.

#### 1.3.16 Validation Layer (`corvin/validations/`)

- `runner.py` + `playwright_runner.py`: Automated validation using Playwright after
  fix execution — verifies service health post-remediation.

---

### 1.4 What Corvin Gets Right

1. **Evidence-grounded generation** — RCA generator is explicitly told what was queried
   and what it found. Hallucinated tool suggestions are blocked by design.
2. **HITL gate is hard** — no execution without `approval_status == APPROVED`. Correct.
3. **Azure-native depth** — 20+ APIM KQL templates, 12 Container Insights queries, 
   Activity Log correlation. No competitor matches this for Azure/APIM-heavy stacks.
4. **Hypothesis diversity** — forced angle diversity (infrastructure/code/dependency)
   prevents single-hypothesis tunnel vision.
5. **Full audit trail** — every tool call, result, RCA, and fix action persisted.
6. **Delivery breadth** — Teams, email, SharePoint, ADO, PDF. Meets enterprise delivery requirements.
7. **Structured degradation** — RCA generator tracks its own failure modes and falls back gracefully.

---

### 1.5 What Corvin Gets Wrong (Honest Gap Analysis)

| Gap | Severity | File | Impact |
|---|---|---|---|
| No PII detection before LLM injection | **P0** | `enrich/enrichment_service.py` | GDPR — Elastic logs hit LLM raw |
| No context window budget | **P0** | `strategy/agent_service.py`, `strategy/rca_generator.py` | Silent context overflow → wrong RCAs at scale |
| Sequential evidence collection | **P1** | `enrich/enrichment_service.py` | P1 response time = sum of 13 adapter latencies |
| No reflection/critic pass on RCA | **P1** | `strategy/rca_generator.py` | Self-reported confidence, unchallenged claims |
| No retry on low confidence | **P1** | `investigation/engine.py` | Low confidence → warning + continue, not retry |
| No RAG — pgvector schema exists, no embeddings | **P1** | `storage/models.py` | No semantic memory over past incidents |
| No Azure Monitor Metrics API | **P2** | New adapter needed | Pays LA ingestion cost for free platform metrics |
| Multi-agent is sequential pipeline | **P2** | `strategy/multi_agent.py` | Agents can't communicate, no loop-back possible |
| No OpenTelemetry tracing | **P2** | All LLM + tool call sites | Production debugging is blind |
| No RAGAS or eval harness | **P2** | Not implemented | Can't prove RCA accuracy with numbers |
| Predictive detection is heuristic | **P3** | `triggers/predictive.py` | Won't improve without explicit model work |
| Static tool registry | **P3** | `strategy/agent_tools.py` | No per-service tool availability, no runtime registration |
| No MCP / A2A compatibility | **P3** | — | Not composable with external agents |

---

### 1.6 Agentic Maturity Scorecard

```
Level 1:  LLM Call                     ✅ Done
Level 2:  Prompt Engineering            ✅ Done  (layered prompts, evidence grounding, angle-forced hypotheses)
Level 3:  Tool Use / Function Calling   ✅ Done  (15+ tools, ReAct loop, schema-driven)
Level 4:  Structured Output             ✅ Done  (Pydantic + json_object, streaming with fallback)
Level 5:  Memory & Persistence          🟡 Partial (message history + evidence bundles; no semantic RAG)
Level 6:  Multi-Agent Coordination      🟡 Partial (F9 pipeline masquerading as agents)
Level 7:  Reflection / Self-Critique    ❌ Missing
Level 8:  Planning                      ❌ Missing (no plan-and-execute, no LangGraph)
Level 9:  Autonomous Recovery           ❌ Missing (no retry on low confidence)
Level 10: Observability & Evals         ❌ Missing (no OTel, no RAGAS)

Overall AI Maturity: ~28%
Agentic Patterns:    ~42%
RAG:                 ~14%
```

---

---

## PART 2 — POST-IMPROVEMENTS: TARGET STATE

### Guiding Principles

Three architectural themes drive all improvements:

1. **4-Week Execution Plan** — Close P0/P1 gaps: safety, quality, RAG, observability.
2. **RAEL Backdoor** — Compete with NeuBird's verifiable investigation programs through
   *transparency + auditability* rather than proprietary language. Every RCA claim is
   linked to specific evidence. SRE becomes the verifier. A second model independently
   critiques each claim.
3. **Multi-Model Agentic Pattern** — Route investigation steps to the right model by
   complexity. High-reasoning model for causal analysis and critique; standard model for
   tool calls, summarization, and structured generation. LangGraph as the pipeline spine.

---

### Post-Improvement Maturity Target

```
Level 1-4:  ✅ Already done
Level 5:    ✅ Semantic RAG with HyDE (Feature 7+8)
Level 6:    ✅ LangGraph pipeline + multi-model routing (Feature 10+11)
Level 7:    ✅ Critic/reflection pass (Feature 5)
Level 8:    ✅ LangGraph conditional edges = plan-and-execute (Feature 11)
Level 9:    ✅ Low-confidence retry loop (Feature 6)
Level 10:   ✅ OTel + RAGAS (Feature 12+13)

Overall AI Maturity: ~65–70%
```

---

### Feature 1 — Context Window Budget Management

**What**: Before appending any tool result to the LLM messages array, count the
current token total using `tiktoken`. If adding the result would exceed 80% of
the model's context limit, truncate the result (keep head + tail) or summarize it
before appending. Applies to both the ReAct agent loop and the RCA generator.

**Why**: Today, a KQL returning 500 log lines is appended raw. At high investigation
volume or when many tools fire in one session, the context window silently fills.
The model truncates from the end — which is where the most recent (most relevant)
tool results sit. This produces wrong RCAs with no warning. `tiktoken` is already a
project dependency and is unused.

**Affected files**: `corvin/strategy/agent_service.py`, `corvin/strategy/rca_generator.py`

---

#### Implementation Prompt — Feature 1

```
You are implementing context window budget management in Corvin, a Python FastAPI
AI SRE Copilot. The codebase uses LiteLLM for all LLM calls and stores conversation
state as a list of OpenAI-format message dicts.

PROBLEM: The ReAct agent loop in corvin/strategy/agent_service.py appends tool results
directly to the messages list without checking token count. When many tools fire or
when a KQL returns 500 log lines, the context window silently overflows. tiktoken
is already installed but unused.

TASK: Create a utility module at corvin/core/token_budget.py with the following:

1. A function `count_tokens(messages: list[dict], model: str) -> int` that uses
   tiktoken to count the total token usage of a messages array. Use `tiktoken.encoding_for_model()`
   with a fallback to `cl100k_base` for unknown model names. Handle the OpenAI
   message format: each message has role + content (str or list of content parts).

2. A function `budget_tool_result(
       messages: list[dict],
       new_result: str,
       model: str,
       max_fraction: float = 0.80,
       head_lines: int = 50,
       tail_lines: int = 50
   ) -> str` that:
   - Counts current token usage
   - Estimates tokens in new_result
   - If adding new_result would exceed max_fraction of the model's context limit,
     truncates new_result to head_lines from the start + tail_lines from the end
     with a middle marker: "... [truncated {N} lines — context budget] ..."
   - Returns the (possibly truncated) result string

   Model context limits to hardcode: gpt-4o=128000, gpt-4.1=1047576, gpt-4.1-mini=1047576,
   gpt-4-turbo=128000, gpt-4=8192, claude-3-5-sonnet=200000, claude-opus-4=200000,
   default=128000. Accept model names with "azure/" prefix — strip it before lookup.

3. In corvin/strategy/agent_service.py, find where tool results are appended to the
   messages list (look for messages.append with role="tool" or similar). Import
   budget_tool_result and wrap each tool result before appending.

4. In corvin/strategy/rca_generator.py, find where the evidence bundle is serialized
   and added to the prompt. Apply the same token check — if the serialized evidence
   would push the prompt past 70% of limit, truncate the evidence sections starting
   from the least relevant (network metrics first, container inventory second, keep
   container logs and K8s events always).

CONSTRAINTS:
- Do not change the message format or tool call protocol — only the content string
  of tool results.
- Do not import anything outside the standard library + tiktoken + existing corvin
  imports.
- The truncation must be deterministic and reversible — the SRE can always see the
  full result in the evidence audit panel (separate concern, separate feature).
- Add a log warning at INFO level whenever truncation occurs, with the original
  line count and truncated line count.
- Write unit tests in tests/core/test_token_budget.py covering: under-budget (no
  truncation), over-budget (truncation fires), exact-boundary, unknown model name
  fallback, azure/ prefix handling.
```

---

### Feature 2 — PII Redaction Middleware

**What**: Before any tool result is injected into an LLM prompt, scan it for PII
(email addresses, IP addresses, phone numbers, usernames, national IDs) and redact
them with typed placeholders. The redaction map is stored per investigation so the
SRE can see original values in the evidence audit panel while the LLM sees only
redacted text.

**Why**: Elastic application logs and APIM gateway logs contain caller IPs, user
identifiers, and email addresses. Today these are sent verbatim to Azure OpenAI.
This is a GDPR compliance risk and a blocker for regulated industries.

**Affected files**: `corvin/enrich/enrichment_service.py`, new `corvin/core/pii_redactor.py`

---

#### Implementation Prompt — Feature 2

```
You are implementing PII redaction in Corvin, a Python FastAPI AI SRE Copilot.

PROBLEM: corvin/enrich/enrichment_service.py collects evidence from Elastic logs,
APIM gateway logs, and Container Insights. This evidence is passed directly to LLM
prompts in rca_generator.py and agent_service.py. It contains PII: IP addresses,
email addresses, usernames, caller IDs. This must be redacted before LLM injection.

TASK: Create corvin/core/pii_redactor.py with:

1. A `PIIRedactor` class with:
   - Regex patterns for: IPv4 addresses, IPv6 addresses, email addresses,
     phone numbers (E.164 and common formats), UUIDs (preserve as [UUID-XXXX]
     where XXXX is a short deterministic hash so correlation is possible),
     bearer tokens / API keys (Authorization: Bearer ... patterns).
   - A method `redact(text: str, context_id: str) -> tuple[str, dict[str, str]]`
     that replaces each detected PII value with a typed placeholder like
     [EMAIL-a1b2], [IP-c3d4], [PHONE-e5f6], where the suffix is the first 4
     chars of sha256(value). Returns the redacted text and a mapping
     {placeholder: original_value} called the redaction_map.
   - A method `restore(text: str, redaction_map: dict[str, str]) -> str` that
     reverses redaction for display in the evidence panel.

2. A `redact_evidence_bundle(bundle: EvidenceBundle, context_id: str) -> tuple[EvidenceBundle, dict]`
   function that applies redaction to all string fields in the bundle that come from
   log/event data (specifically: container_logs, apim_logs, elastic_logs, kube_events
   fields). Does NOT redact structured fields like service_name, namespace, timestamps.

3. In corvin/enrich/enrichment_service.py, call `redact_evidence_bundle()` after
   evidence collection completes, before returning the bundle. Store the redaction_map
   in the EvidenceBundle or alongside it (add a `pii_redaction_map: dict` field to
   EvidenceBundleRow in storage/models.py as a nullable JSONB column).

4. The redaction_map must be persisted per investigation so the evidence audit panel
   can restore original values for the SRE. Add a migration: ALTER TABLE evidence_bundles
   ADD COLUMN pii_redaction_map JSONB.

CONSTRAINTS:
- PII detection must be fast — use pre-compiled regex patterns (re.compile at class init).
- Do not use spaCy or any ML-based NER — regex only, no new heavy dependencies.
- UUID preservation with deterministic hash suffix is important: same UUID always gets
  same placeholder within an investigation, allowing log correlation to still work.
- The redactor must be stateless per call — context_id is passed in to allow
  cross-call correlation if needed, but the object itself holds no per-investigation state.
- Add a config flag `pii_redaction_enabled: bool` in config/policies/investigation.yaml.
  When False, redaction is a no-op (returns original text + empty map). Default: True.
- Write unit tests in tests/core/test_pii_redactor.py covering: email in log line,
  IP in APIM log, bearer token in header, UUID preservation and correlation,
  restore round-trip, disabled flag.
```

---

### Feature 3 — Parallel Evidence Collection

**What**: Replace the sequential `try/except` adapter calls in `EnrichmentService`
with `asyncio.gather()`. All 13 adapters fire concurrently. Total evidence collection
time becomes bounded by the slowest single adapter, not the sum of all 13.

**Why**: At P1 incident response, time-to-RCA matters. Sequential collection adds
latency unnecessarily. All 13 adapters are independent — there is no data dependency
between them.

**Affected files**: `corvin/enrich/enrichment_service.py`

---

#### Implementation Prompt — Feature 3

```
You are parallelizing evidence collection in Corvin, a Python FastAPI AI SRE Copilot.

PROBLEM: corvin/enrich/enrichment_service.py calls 13 evidence adapters sequentially
in a for-loop or sequential try/except block. Each adapter makes a network call
(Azure Monitor API, Elasticsearch, Kubernetes API). Total collection time =
sum of all adapter latencies (~3-8 seconds per adapter = 40-100 seconds total).
For P1 incidents, this is unacceptable.

TASK: Refactor EnrichmentService.enrich() and EnrichmentService.stream_enrich() to
run all adapter calls concurrently using asyncio.gather().

Requirements:
1. Each adapter call becomes an async coroutine. If the underlying adapter method
   is synchronous, wrap it with asyncio.get_event_loop().run_in_executor() using
   a ThreadPoolExecutor(max_workers=13).

2. Use asyncio.gather(*tasks, return_exceptions=True) so that one adapter failure
   does not cancel others. After gather, iterate results: if result is an Exception,
   log it at WARNING level with adapter name and exception message, assign empty list
   to that evidence slot. If result is valid data, assign it normally.

3. Preserve the existing graceful skip behaviour — a failing adapter returns an empty
   result, not an error. The EvidenceBundle must be fully populated even if some
   adapters return nothing.

4. The streaming variant (stream_enrich) should yield events as each adapter
   completes, not wait for all to finish. Use asyncio.as_completed() for streaming:
   as each coroutine finishes, yield an SSE event with adapter_name and partial result.

5. Add a timing log at INFO level: "Evidence collection completed in {elapsed_ms}ms
   ({adapters_succeeded}/{total} adapters succeeded)".

6. Add a config option `parallel_evidence: bool` in config/policies/investigation.yaml
   defaulting to True. When False, fall back to sequential execution (for debugging).

CONSTRAINTS:
- Do not change the EvidenceBundle structure or the adapter interfaces.
- The existing PII redaction (Feature 2) must be applied after all adapters complete,
  before returning the bundle.
- Thread safety: each adapter creates its own client connection — do not share client
  instances across concurrent calls. Check each adapter's __init__ to confirm it
  builds its own client (they do — ContainerLogsAdapter, AKSAdapter, etc. each init
  their own client in __init__).
- Write an integration test in tests/enrich/test_parallel_collection.py that mocks
  all 13 adapters with configurable sleep delays and verifies total time is bounded
  by max adapter delay (not sum), and that one adapter raising an exception does not
  prevent others from completing.
```

---

### Feature 4 — Tool Result Summarization

**What**: For tool results exceeding a configurable line threshold (default 100 lines),
automatically summarize the result using a cheap fast model before appending to context.
The full result is stored separately for the evidence audit panel.

**Why**: Large tool outputs (KQL returning 500 APIM log lines) add noise to LLM context.
The LLM cannot effectively reason over 500 lines — it pattern-matches on the first and
last visible lines. A 10-line summary of key signals is more useful than 500 raw lines.

**Affected files**: `corvin/strategy/agent_tools.py`, new `corvin/core/result_summarizer.py`

---

#### Implementation Prompt — Feature 4

```
You are implementing tool result summarization in Corvin, a Python FastAPI AI SRE Copilot.

PROBLEM: When tools like run_kql or query_apim_analytics return large result sets
(e.g., 500 APIM log lines, 200 KubePodInventory rows), the full result is appended
to the LLM context. This causes two problems: (1) context window bloat addressed
by Feature 1, but (2) even within budget, 500 raw lines are noisy — the LLM
pattern-matches on structure rather than reasoning over content.

TASK: Create corvin/core/result_summarizer.py with:

1. A `ResultSummarizer` class using litellm with a fast/cheap model
   (config key: `models.summarizer`, default: `azure/gpt-4.1-mini`).

2. A method `should_summarize(result: str, threshold_lines: int = 100) -> bool`
   that returns True if the result exceeds threshold_lines.

3. A method `summarize(result: str, tool_name: str, context: str) -> str` that:
   - Calls the summarizer model with a tightly scoped prompt:
     "You are summarizing a tool result for an SRE incident investigation.
      Tool: {tool_name}. Investigation context: {context}.
      Extract the 5-10 most diagnostically significant signals from the data below.
      Focus on: errors, anomalies, threshold breaches, recent changes, high counts.
      Output as a compact bulleted list. Do not include normal/expected values.
      Data: {result}"
   - Max output tokens: 300.
   - Returns the summary string prefixed with "[SUMMARIZED — {original_line_count} lines → summary]"

4. A method `summarize_if_large(result: str, tool_name: str, context: str,
   full_result_store: dict, store_key: str) -> str` that:
   - Stores result in full_result_store[store_key] always (for evidence panel).
   - If should_summarize(), calls summarize() and returns summary.
   - Otherwise returns result unchanged.

5. In corvin/strategy/agent_tools.py (or agent_service.py), in the tool executor
   dispatch loop, after each tool returns its result string, call
   `summarize_if_large()` with the full_result_store being the current investigation's
   evidence store (keyed by tool_name + call index). Pass the investigation description
   as context.

CONSTRAINTS:
- The summarizer LLM call must be async (use litellm.acompletion).
- The full_result_store must be accessible to the evidence audit panel (Feature 9).
  Store it in the investigation session — pass it through to the SSE event stream
  as a separate event type: `evidence_raw` with tool_name and full_result.
- Add a config flag `tool_summarization_enabled: bool` in config/policies/investigation.yaml,
  default True. When False, always return full result (for debugging or high-fidelity mode).
- The summarizer model should be different from the main RCA model — cheaper and faster.
- Write unit tests covering: under-threshold (no summarization), over-threshold
  (summarization fires), summarizer LLM failure (falls back to truncation from Feature 1).
```

---

### Feature 5 — Critic / Reflection Pass

**What**: After `RCAGenerator.generate()` returns an `RCAOutput`, pass it through a
second independent LLM call — the Critic — that reviews every claim in the RCA against
the evidence bundle and returns a structured critique: unsupported claims, alternative
explanations not considered, confidence score accuracy. The original RCA is amended or
flagged based on the critique before being returned to the user.

**Why**: This is the single highest-value agentic improvement. Today, RCA confidence
is self-reported by the same model that generated it. The Critic uses a different
model (or at minimum a different prompt context) to independently verify claims. This
is the practical equivalent of what NeuBird's RAEL achieves — not mechanically identical,
but produces the same user-facing outcome: a verified, challenged RCA rather than a
first-draft output.

**Affected files**: `corvin/investigation/engine.py`, `corvin/strategy/rca_generator.py`,
new `corvin/strategy/rca_critic.py`

---

#### Implementation Prompt — Feature 5

```
You are implementing the Critic/Reflection pass in Corvin, a Python FastAPI AI SRE Copilot.

PROBLEM: corvin/strategy/rca_generator.py generates an RCA and self-reports a confidence
score. There is no independent verification. Claims in the RCA may not be supported by
the evidence. A low confidence score means "the model is uncertain" — it does not mean
"these specific claims are unsupported." The investigation/engine.py just logs a warning
on low confidence and continues.

TASK: Create corvin/strategy/rca_critic.py with:

1. A `RCACritic` class that takes config (model config) and policy config. Uses a
   DIFFERENT model from the RCA generator for the critic call — config key
   `models.critic`, default `azure/gpt-4.1` (same capability tier, different temperature
   setting: 0.1 for determinism). If the RCA generator used gpt-4.1, the critic should
   still use gpt-4.1 but with an entirely different system prompt context so it approaches
   the RCA fresh.

2. A method `critique(rca: RCAOutput, evidence: EvidenceBundle,
   request: InvestigationRequest) -> CritiqueOutput` where CritiqueOutput is a
   Pydantic model with:
   - unsupported_claims: list[str] — claims in the RCA not traceable to evidence
   - alternative_explanations: list[str] — plausible root causes not considered
   - confidence_accuracy: Literal["accurate", "overconfident", "underconfident"]
   - confidence_adjustment: float — suggested adjustment to confidence score (-0.3 to +0.3)
   - critique_summary: str — one paragraph plain English critique
   - evidence_coverage_pct: float — percentage of RCA claims that have explicit evidence support

3. System prompt for the critic (do not deviate from this structure):
   "You are an independent RCA reviewer. You did NOT write the RCA below — you are
    reviewing it. Your job is adversarial: find what is wrong, unsupported, or missing.

    Rules:
    - For each factual claim in the RCA, check if it is explicitly supported by the
      evidence provided. A claim is UNSUPPORTED if no evidence entry directly confirms it.
    - Identify plausible root causes that the evidence could support but were not
      considered in the RCA.
    - Assess whether the confidence score is justified. 'High' confidence requires
      multiple independent evidence signals pointing to the same cause.
    - Be specific: cite the exact claim and the missing evidence, not vague criticism.
    - Output ONLY valid JSON matching the CritiqueOutput schema."

4. In corvin/investigation/engine.py, after `RCAGenerator.generate()` returns:
   - Call `RCACritic.critique()` with the RCA and evidence bundle.
   - If unsupported_claims is non-empty: append them to rca.summary as a section
     "⚠ Critic flagged: {claim1}; {claim2}..." and reduce rca.confidence_score by
     confidence_adjustment.
   - If confidence_accuracy == "overconfident" and original confidence was HIGH:
     downgrade to MEDIUM.
   - Store the full CritiqueOutput in the investigation result (add critique_json
     field to RCAOutputRow as nullable JSONB).
   - Log the critique_summary at INFO level.

5. Add config in config/policies/investigation.yaml:
   `critic_enabled: bool` (default true)
   `critic_on_high_confidence_only: bool` (default false — critique all RCAs)

CONSTRAINTS:
- The critic must use the serialized evidence bundle as its ground truth — it
  must not call any tools or make any external API calls.
- The critic call must be async (litellm.acompletion).
- If the critic LLM call fails, log at WARNING and return the original RCA unchanged —
  critic failure must never block investigation completion.
- The critique is stored but never shown to the LLM in subsequent calls — it is for
  the SRE and for the evidence audit panel only.
- Write unit tests in tests/strategy/test_rca_critic.py covering: well-supported RCA
  (few unsupported claims), hallucinated RCA (many unsupported claims), critic LLM
  failure (graceful pass-through), confidence downgrade logic.
```

---

### Feature 6 — Low-Confidence Retry Loop

**What**: When `RCAOutput.confidence` is LOW after the critic pass, the investigation
engine retries RCA generation with a broadened evidence window and a modified prompt
that explicitly names what was uncertain in the first attempt. Maximum 2 retries before
escalating to the SRE for additional context.

**Why**: Today, low confidence → warning logged → pipeline continues to fix strategy
generation. This produces a low-quality fix strategy with no warning to the SRE about
the underlying uncertainty. Automatic retry is a core agentic recovery behaviour that
Corvin is missing entirely.

**Affected files**: `corvin/investigation/engine.py`

---

#### Implementation Prompt — Feature 6

```
You are implementing the low-confidence retry loop in Corvin, a Python FastAPI AI SRE Copilot.

PROBLEM: corvin/investigation/engine.py has a confidence gate (_confidence_below_threshold)
that checks if RCA confidence is below threshold and logs a warning, but does NOT retry.
Investigation proceeds to fix strategy generation regardless of confidence. This produces
low-quality fix strategies built on uncertain RCAs.

TASK: Modify InvestigationEngine._run_investigation() (or equivalent pipeline method) to:

1. After RCAGenerator.generate() + RCACritic.critique() (Feature 5), check confidence.
   If confidence is LOW:

   RETRY ATTEMPT 1:
   - Extend the evidence lookback window by 2x (e.g., 60 minutes → 120 minutes).
   - Re-run EnrichmentService.enrich() with the extended window.
   - Re-run RCAGenerator.generate() with an augmented system prompt that includes:
     "PREVIOUS ATTEMPT NOTE: The first investigation attempt returned LOW confidence.
      Specific uncertainties identified: {critique.unsupported_claims}.
      Additional evidence has been collected for a longer time window. Re-investigate
      with fresh eyes — do not anchor on the first attempt's conclusion."
   - Re-run RCACritic.critique() on the new RCA.
   - If confidence is now MEDIUM or HIGH: proceed normally.

   RETRY ATTEMPT 2 (if still LOW after attempt 1):
   - Do not extend window further.
   - Re-run RCAGenerator with a different angle emphasis: ask it to consider the
     alternative_explanations surfaced by the critic in attempt 1.
   - If confidence is MEDIUM or HIGH: proceed.

   ESCALATE (if still LOW after 2 retries):
   - Set InvestigationResult.escalated = True.
   - Populate escalation_reason with the critic's critique_summary from the last attempt.
   - Skip fix strategy generation entirely.
   - Emit an SSE event type "escalation_required" with the escalation reason.
   - In the Teams notification, surface: "Corvin was unable to determine root cause
     with sufficient confidence after 2 attempts. Human investigation required.
     Partial findings: {rca.summary}"

2. Track retry count and duration in InvestigationResult (add retry_count: int,
   total_investigation_ms: int fields).

3. Add to config/policies/investigation.yaml:
   `max_retries: int` (default 2)
   `retry_lookback_multiplier: float` (default 2.0)
   `retry_enabled: bool` (default true)

CONSTRAINTS:
- Retries must reuse the parallel evidence collection from Feature 3.
- The EvidenceBundle from retry attempts must be merged with the original bundle,
  not replace it — the original evidence is still valid and relevant.
- Each retry must produce a new RCAOutputRow linked to the same investigation_request_id.
  Use a retry_index field (0 = original, 1 = first retry, 2 = second retry) so the
  full investigation history is queryable.
- Do not retry on MEDIUM confidence — only on LOW. MEDIUM is acceptable for fix suggestions
  with a disclaimer.
- Retry timing must be logged: "RCA retry {n} triggered after {ms}ms. Confidence was LOW.
  Unsupported claims: {claims}."
```

---

### Feature 7 — RAG Embedding Pipeline (pgvector)

**What**: Wire the existing pgvector schema stub to actually produce and store embeddings.
When an investigation closes with a completed RCA, build an index text from the RCA output
and investigation context, call the embedding API, and store the vector in `rca_outputs.embedding`.

**Why**: The pgvector column and HNSW index exist in the schema but no embedding is ever
written. The RAG feature is structurally present but non-functional. This is a half-day
implementation task that unlocks semantic memory over all past incidents.

**Affected files**: `corvin/storage/models.py`, `corvin/investigation/engine.py`,
new `corvin/storage/embedding_service.py`

---

#### Implementation Prompt — Feature 7

```
You are wiring the RAG embedding pipeline in Corvin, a Python FastAPI AI SRE Copilot.

CONTEXT: corvin/storage/models.py has an RCAOutputRow ORM model. The pgvector extension
is installed on the database. The embedding column and HNSW index need to be created
(migration), and the embedding API call needs to be wired at investigation close.

TASK:

1. DATABASE MIGRATION — create a migration script at alembic/versions/xxxx_add_rca_embedding.py:
   ALTER TABLE rca_outputs ADD COLUMN IF NOT EXISTS embedding vector(3072);
   CREATE INDEX IF NOT EXISTS rca_embedding_hnsw_idx
     ON rca_outputs USING hnsw (embedding vector_cosine_ops)
     WITH (m = 16, ef_construction = 64);
   Also add the column to RCAOutputRow in storage/models.py using pgvector's Vector type.

2. Create corvin/storage/embedding_service.py with:

   A function `build_index_text(rca: RCAOutput, request: InvestigationRequest) -> str`:
   Assembles a semantically rich text for embedding:
   ```
   Service: {request.service_name}
   Environment: {request.environment}
   Alert: {request.description}
   Root cause: {rca.root_cause}
   Summary: {rca.summary}
   Confidence: {rca.confidence}
   Fix actions: {comma-joined list of first 3 fix action types}
   ```

   An async function `index_completed_investigation(
       rca: RCAOutput,
       request: InvestigationRequest,
       db: AsyncSession
   ) -> bool`:
   - Calls `litellm.aembedding(model="azure/text-embedding-3-large", input=index_text)`
   - Extracts `response.data[0].embedding` (list of 3072 floats)
   - Updates rca_outputs SET embedding = $vector WHERE request_id = $id
   - Returns True on success, False on failure (log warning, never raise)

3. In corvin/investigation/engine.py, at the end of the investigation pipeline after
   InvestigationResult is fully assembled, call:
   `await embedding_service.index_completed_investigation(result.rca, request, db)`
   This must be fire-and-forget if async context allows — do not block the investigation
   result from being returned to the user.

4. Add a config key `embeddings.model` in config/models/llm.yaml defaulting to
   `azure/text-embedding-3-large`. Add `embeddings.enabled: bool` defaulting to True.
   When disabled, skip embedding entirely (for environments without embedding API access).

CONSTRAINTS:
- Never block investigation completion on embedding failure. If the embedding API call
  fails, log at WARNING and continue — the investigation result is still valid.
- Use the pgvector Python package (already in requirements) for the Vector type in SQLAlchemy.
- The embedding dimension must match the model: text-embedding-3-large = 3072 dimensions.
  This must be validated at startup if embeddings.enabled is True.
- Write unit tests in tests/storage/test_embedding_service.py covering: successful embed
  and update, embedding API failure (graceful), disabled config (no-op).
```

---

### Feature 8 — HyDE Retrieval (Hypothetical Document Embedding)

**What**: Before querying the evidence adapters, generate a hypothetical RCA from
the alert description using a cheap model, embed the hypothetical RCA, and retrieve
the top-K most semantically similar past investigations. Inject these as context
into the RCA generation prompt.

**Why**: Alert text and RCA text live in different embedding spaces. "High error rate
on payments-api" (alert) does not embed near "Database connection pool exhausted due
to slow query accumulation" (RCA). HyDE bridges this gap by generating a hypothetical
answer that lives in the same embedding space as real past RCAs.

**Affected files**: `corvin/storage/embedding_service.py`, `corvin/investigation/engine.py`,
`corvin/investigation/prompt_builder.py`

---

#### Implementation Prompt — Feature 8

```
You are implementing HyDE (Hypothetical Document Embedding) retrieval in Corvin, a Python
FastAPI AI SRE Copilot. Feature 7 (embedding pipeline) is already implemented.

CONTEXT: The pgvector rca_outputs.embedding column is populated for past investigations.
HyDE retrieval: instead of embedding the raw alert text and searching for similar alerts,
generate a hypothetical RCA from the alert, embed the hypothetical RCA, and search for
similar past RCAs. This works because hypothetical RCA text lives in the same embedding
space as real past RCA text.

TASK: Add to corvin/storage/embedding_service.py:

1. An async function `generate_hypothetical_rca(request: InvestigationRequest) -> str`:
   - Calls litellm.acompletion with model from config key `models.hyde_model`
     (default: `azure/gpt-4.1-mini`)
   - Prompt: "In 3 sentences, what is the most likely root cause of this incident?
     Service: {service_name}. Environment: {environment}. Alert: {description}.
     Be specific about the technical failure mode. Output only the root cause statement."
   - max_tokens: 150, temperature: 0.3
   - Returns the generated text string.
   - On failure: returns the raw alert description (graceful fallback to non-HyDE).

2. An async function `retrieve_similar_incidents(
       request: InvestigationRequest,
       db: AsyncSession,
       top_k: int = 5,
       min_similarity: float = 0.72,
       same_service_only: bool = True
   ) -> list[SimilarIncident]` where SimilarIncident is a Pydantic model with:
   request_id, service_name, alert_description, root_cause, summary, confidence,
   completed_at, similarity_score.

   Implementation:
   a. Call generate_hypothetical_rca() to get the hypothetical RCA text.
   b. Embed the hypothetical RCA text using litellm.aembedding.
   c. Query pgvector:
      SELECT r.request_id, r.root_cause, r.summary, r.confidence,
             i.service_name, i.description, i.completed_at,
             1 - (r.embedding <=> $1::vector) AS similarity
      FROM rca_outputs r
      JOIN investigation_requests i USING (request_id)
      WHERE i.service_name = $2  -- if same_service_only
        AND i.environment = $3
        AND r.embedding IS NOT NULL
        AND 1 - (r.embedding <=> $1::vector) >= $4
        AND i.request_id != $5  -- exclude current investigation
      ORDER BY r.embedding <=> $1::vector
      LIMIT $6
   d. Return as list of SimilarIncident.
   e. On any failure: return empty list (graceful).

3. In corvin/investigation/prompt_builder.py, add a method
   `add_similar_incidents(incidents: list[SimilarIncident]) -> None` that formats
   the similar incidents section:
   "SIMILAR PAST INCIDENTS (retrieved by semantic similarity):
    {for each incident}:
    - [{similarity:.0%} match] Service: {service_name}, Date: {completed_at}
      Root cause: {root_cause}
      Resolution: {summary}"
   Cap at top-3 incidents even if more are retrieved.

4. In corvin/investigation/engine.py, before calling RCAGenerator.generate():
   - Call retrieve_similar_incidents().
   - If results non-empty, call prompt_builder.add_similar_incidents().

CONSTRAINTS:
- The HyDE generation LLM call and embedding call must both be async.
- Both calls must complete within 3 seconds total (add a timeout via asyncio.wait_for).
  If timeout exceeded, skip RAG enrichment and proceed without it.
- The hypothetical RCA is never stored, never shown to users — it is an intermediate
  retrieval artifact only.
- min_similarity of 0.72 is the default but must be configurable via
  config/policies/investigation.yaml under `rag.min_similarity`.
- Write unit tests in tests/storage/test_hyde_retrieval.py covering: successful
  retrieval with results, no results above threshold (empty return), HyDE generation
  failure (falls back to raw alert), DB query failure (graceful empty return).
```

---

### Feature 9 — Searchable Evidence Audit Panel (RAEL Backdoor)

**What**: Build a structured evidence audit panel that links every claim in the RCA
to the specific log lines, metric values, or events that support it. Store the full
(un-truncated, pre-summary) tool results alongside claim-to-evidence mappings.
Expose via API so the frontend can render a searchable, filterable evidence browser.

**Why**: This is the competitive answer to NeuBird's RAEL. Instead of a proprietary
language that mechanically verifies claims (black box to the SRE), Corvin makes the
SRE the verifier — every RCA claim is annotated with its supporting evidence, and the
SRE can search the raw data to confirm or challenge the claim. This is more auditable
and more honest about AI limitations than a black-box verification system.

**Affected files**: `corvin/storage/models.py`, `corvin/strategy/rca_generator.py`,
`corvin/strategy/rca_critic.py`, new `corvin/investigation/evidence_linker.py`

---

#### Implementation Prompt — Feature 9

```
You are implementing the Evidence Audit Panel in Corvin, a Python FastAPI AI SRE Copilot.
This is the architectural response to NeuBird's RAEL verification system — instead of
mechanical claim verification, Corvin provides full transparency: every RCA claim is
linked to supporting evidence, and the SRE can verify claims directly.

TASK:

PART A — Evidence Linker

Create corvin/investigation/evidence_linker.py with:

1. A Pydantic model `EvidenceClaim` with:
   - claim_text: str — the exact sentence or phrase from the RCA
   - evidence_references: list[EvidenceReference]
   - supported: bool — True if at least one reference exists
   - critic_flagged: bool — True if the RCA critic identified this as unsupported

2. A Pydantic model `EvidenceReference` with:
   - source: str — adapter name (e.g., "container_logs", "apim_analytics")
   - data_type: str — table/index (e.g., "KubeEvents", "ApiManagementGatewayLogs")
   - excerpt: str — the specific log line, metric value, or event that supports the claim
   - timestamp: str | None
   - relevance_score: float — 0.0-1.0

3. An async function `link_claims_to_evidence(
       rca: RCAOutput,
       evidence: EvidenceBundle,
       full_tool_results: dict[str, str],  # from Feature 4 result_store
       critique: CritiqueOutput | None,
       request: InvestigationRequest
   ) -> list[EvidenceClaim]`:

   - Call litellm.acompletion with the fast model (gpt-4.1-mini).
   - Prompt: "You are linking RCA claims to supporting evidence.
     For each sentence in the RCA, identify which evidence entries (log lines,
     metric readings, events) directly support that sentence.
     RCA: {rca.root_cause} {rca.summary}
     Available evidence sources: {evidence_summary}
     Output JSON: list of {claim_text, evidence_references: [{source, excerpt, relevance_score}],
     supported: bool}"
   - Parse response into list[EvidenceClaim].
   - If critique is provided, mark claims appearing in critique.unsupported_claims
     with critic_flagged=True.
   - Return the list.

PART B — Storage

Add to corvin/storage/models.py:
- A new table `evidence_claims` (EvidenceClaimRow) with:
  request_id (FK), claims_json (JSONB), full_tool_results_json (JSONB), created_at.
- Add a relationship to InvestigationRequestRow.

PART C — API

Add a new route to the investigation router:
GET /investigations/{request_id}/evidence
Returns: { claims: list[EvidenceClaim], full_tool_results: dict[str, str] }

The full_tool_results dict maps tool_name → full raw result (pre-summary, pre-truncation).
This is what the frontend renders in the searchable evidence browser.

PART D — Trigger

In corvin/investigation/engine.py, after the critic pass (Feature 5), call
`link_claims_to_evidence()` and store the result. This must be non-blocking —
fire-and-forget, same as the embedding call.

CONSTRAINTS:
- The evidence linking LLM call failing must never block the investigation. If it fails,
  store an empty claims list and log at WARNING.
- full_tool_results must store the ORIGINAL un-redacted data (for the SRE's own eyes).
  The redaction_map from Feature 2 must be stored alongside so the panel can show either
  view. The API must accept a query param: ?redacted=true (default) or ?redacted=false
  (requires SRE role authorization).
- The claims list must be searchable by the frontend — the excerpt fields must be
  exact substrings of the full tool result so the frontend can highlight them.
- Write unit tests in tests/investigation/test_evidence_linker.py.
```

---

### Feature 10 — Multi-Model Routing (MoE Pattern)

**What**: Route each step of the investigation to the appropriate model based on
task complexity. High-reasoning model (GPT-4o / Claude Opus) for causal analysis,
critique, and hypothesis generation. Standard model (GPT-4.1) for RCA generation
with clear evidence. Fast/cheap model (GPT-4.1-mini) for tool calls, summarization,
and structured generation tasks.

**Why**: Using the most expensive model for every LLM call wastes cost on tasks that
don't need maximum reasoning depth. Routing also enables fallback — if the high-reasoning
model is slow or unavailable, the standard model can handle most investigation steps.

**Affected files**: `corvin/core/config_loader.py`, `corvin/strategy/rca_generator.py`,
`corvin/strategy/rca_critic.py`, `corvin/strategy/hypothesis_service.py`,
new `corvin/core/model_router.py`

---

#### Implementation Prompt — Feature 10

```
You are implementing multi-model routing in Corvin, a Python FastAPI AI SRE Copilot.

PROBLEM: Every LLM call in Corvin uses the same model configured in config/models/llm.yaml.
Some tasks (causal reasoning, critique) benefit from maximum reasoning depth. Others
(tool call generation, result summarization) are cheaper tasks that waste cost on a
high-reasoning model. There is no routing logic.

TASK: Create corvin/core/model_router.py with:

1. A `TaskType` enum:
   CAUSAL_REASONING, HYPOTHESIS_GENERATION, RCA_CRITIQUE, RCA_GENERATION,
   FIX_STRATEGY, TOOL_CALL, SUMMARIZATION, EMBEDDING, HYDE_GENERATION,
   EVIDENCE_LINKING, NL_TO_KQL, POSTMORTEM, COMMS_DRAFT

2. A `ModelRouter` class that reads from config/models/llm.yaml and provides:
   `def route(self, task: TaskType, incident_priority: str = "P3") -> str`:
   Returns the LiteLLM model string for the given task and priority.

   Routing rules (all overridable from config):
   - P1 incidents: always use `models.high_reasoning` for CAUSAL_REASONING,
     HYPOTHESIS_GENERATION, RCA_CRITIQUE, RCA_GENERATION.
   - P2/P3 incidents: use `models.standard` for RCA_GENERATION and FIX_STRATEGY;
     use `models.high_reasoning` for CAUSAL_REASONING and RCA_CRITIQUE only.
   - TOOL_CALL, SUMMARIZATION, HYDE_GENERATION, EVIDENCE_LINKING, NL_TO_KQL:
     always use `models.fast` regardless of priority.
   - EMBEDDING: always use `models.embedding`.

3. Config structure in config/models/llm.yaml (add these keys):
   ```yaml
   models:
     high_reasoning: "azure/gpt-4o"         # for causal tasks
     standard: "azure/gpt-4.1"              # for RCA generation
     fast: "azure/gpt-4.1-mini"             # for tool calls, summaries
     embedding: "azure/text-embedding-3-large"
     critic: "azure/gpt-4.1"               # for critique pass
     hyde_model: "azure/gpt-4.1-mini"      # for HyDE generation
     summarizer: "azure/gpt-4.1-mini"      # for tool result summarization
   ```

4. Update each LLM-calling service to use ModelRouter:
   - rca_generator.py: use router.route(TaskType.RCA_GENERATION, priority)
   - rca_critic.py: use router.route(TaskType.RCA_CRITIQUE, priority)
   - hypothesis_service.py: use router.route(TaskType.HYPOTHESIS_GENERATION, priority)
   - causal_chain.py: use router.route(TaskType.CAUSAL_REASONING, priority)
   - agent_tools.py (tool call dispatch): use router.route(TaskType.TOOL_CALL)
   - postmortem_service.py: use router.route(TaskType.POSTMORTEM)
   Pass incident_priority through from InvestigationRequest.incident_priority.

5. Add a `ModelRouter.explain(task: TaskType, priority: str) -> str` method that
   returns a human-readable string for logging: "Task CAUSAL_REASONING on P1 incident
   → gpt-4o (high_reasoning path)".

CONSTRAINTS:
- ModelRouter must be a singleton initialized at app startup — do not re-read config
  on every call.
- All model strings must pass through LiteLLM — do not call provider SDKs directly.
- If a configured model name is invalid or unavailable, ModelRouter.route() must fall
  back to the standard model and log a WARNING, never raise.
- Write unit tests in tests/core/test_model_router.py covering: P1 routing (high_reasoning),
  P3 routing (standard), tool call routing (always fast), config override, fallback on
  invalid model name.
```

---

### Feature 11 — LangGraph Investigation Pipeline

**What**: Replace the imperative sequential pipeline in `InvestigationEngine` and
`MultiAgentOrchestrator` with a LangGraph state graph. Each investigation stage
becomes a typed node. Conditional edges handle retry logic (Feature 6), HITL
interruption, and escalation. State is checkpointed at every node transition.

**Why**: LangGraph gives the investigation pipeline: typed state validation,
conditional re-entry (retry on low confidence becomes a graph edge), built-in
checkpointing (failed investigations resume from last completed node, not restart),
proper HITL via `interrupt_before`, and graph visualization. The current pipeline
fails silently at any step and always restarts from scratch.

**Affected files**: `corvin/investigation/engine.py`, `corvin/strategy/multi_agent.py`,
new `corvin/investigation/graph.py`

---

#### Implementation Prompt — Feature 11

```
You are migrating Corvin's investigation pipeline to LangGraph. Corvin is a Python
FastAPI AI SRE Copilot.

CONTEXT: corvin/investigation/engine.py runs a sequential 4-stage pipeline:
Enrich → RCA → Critic → Fix Strategy. corvin/strategy/multi_agent.py mirrors this
as a fake SelectorGroupChat. Both are imperative and stateless between steps.

TASK: Create corvin/investigation/graph.py implementing a LangGraph StateGraph.

1. Define the investigation state TypedDict:
```python
class InvestigationState(TypedDict):
    request: InvestigationRequest
    evidence: EvidenceBundle | None
    rca: RCAOutput | None
    critique: CritiqueOutput | None
    similar_incidents: list[SimilarIncident]
    fix_strategy: FixStrategyOutput | None
    retry_count: int
    escalated: bool
    escalation_reason: str | None
    stage: str  # current stage name for SSE streaming
    errors: list[str]  # non-fatal errors accumulated across stages
```

2. Define nodes (each is an async function receiving state, returning partial state update):
   - `enrich_node`: calls EnrichmentService.enrich() → updates evidence
   - `rca_node`: calls RCAGenerator.generate() → updates rca
   - `critic_node`: calls RCACritic.critique() → updates critique; amends rca
   - `rag_node`: calls retrieve_similar_incidents() → updates similar_incidents
   - `fix_strategy_node`: calls FixStrategyGenerator.generate() → updates fix_strategy
   - `escalation_node`: sets escalated=True, escalation_reason, emits Teams notification

3. Define conditional edges:
   - After critic_node:
     - If rca.confidence == LOW and retry_count < max_retries → back to enrich_node
       (with state update: retry_count += 1, extend lookback_minutes)
     - If rca.confidence == LOW and retry_count >= max_retries → escalation_node
     - Otherwise → fix_strategy_node
   - After fix_strategy_node: END
   - After escalation_node: END

4. Wire the graph:
```python
graph = StateGraph(InvestigationState)
graph.add_node("enrich", enrich_node)
graph.add_node("rag", rag_node)         # runs in parallel with enrich via Send API
graph.add_node("rca", rca_node)
graph.add_node("critic", critic_node)
graph.add_node("fix_strategy", fix_strategy_node)
graph.add_node("escalation", escalation_node)
graph.set_entry_point("enrich")
graph.add_edge("enrich", "rca")
graph.add_edge("rag", "rca")            # both enrich and rag must complete before rca
graph.add_conditional_edges("critic", route_after_critic)
graph.add_edge("fix_strategy", END)
graph.add_edge("escalation", END)
```

5. Add checkpointing using LangGraph's AsyncSqliteSaver or AsyncPostgresSaver
   (use the existing Postgres connection from corvin/storage/db.py).
   Pass `checkpointer=checkpointer` to `graph.compile()`.

6. Add `interrupt_before=["fix_strategy_node"]` to enable HITL — the graph pauses
   before executing fix strategy and waits for `graph.update_state()` with
   approval_status. This replaces the current execution_service.py approval gate.

7. In corvin/investigation/engine.py, replace the current pipeline with:
   `result = await graph.ainvoke({"request": request, ...initial_state})`
   Map the final InvestigationState back to InvestigationResult.

CONSTRAINTS:
- Do not remove InvestigationEngine entirely — wrap the graph invocation inside it
  so the existing API routes continue to work unchanged.
- The checkpointer table must be separate from Corvin's existing tables — LangGraph
  manages its own schema.
- Streaming: use graph.astream_events() to forward node-transition events to the
  existing SSE stream. Map LangGraph's event types to Corvin's existing event types
  (thinking, tool_call, tool_result, text).
- langgraph and langgraph-checkpoint-postgres must be added to requirements.txt.
- Write integration tests in tests/investigation/test_graph.py covering: happy path,
  retry loop (low confidence → retry → success), escalation (low confidence × 2),
  checkpoint resume (simulate mid-pipeline failure and resume).
```

---

### Feature 12 — Azure Monitor Metrics API Adapter

**What**: Add a `MetricsAdapter` that queries Azure Monitor Metrics Store (not Log
Analytics) for platform metrics. Replaces the LA `Perf` and `InsightsMetrics` table
queries with free, lower-latency Metrics API calls for AKS node CPU/memory, APIM
request counts and latency, Azure Functions execution metrics, Event Hub consumer lag.

**Why**: Platform metrics in the Azure Metrics Store are free and have ~1-minute
latency. The current approach queries LA `Perf` and `InsightsMetrics` tables which
have 1-5 minute ingestion lag AND cost ~$2.76/GB. This is an unnecessary cost and
a latency regression.

**Affected files**: `corvin/evidence/` (new `azure_metrics_adapter.py`),
`corvin/enrich/enrichment_service.py`

---

#### Implementation Prompt — Feature 12

```
You are implementing an Azure Monitor Metrics API adapter in Corvin, a Python FastAPI AI SRE Copilot.

PROBLEM: Corvin's container_logs_adapter.py queries LA tables Perf (K8SContainer) and
InsightsMetrics for AKS CPU/memory and network metrics. These queries cost ~$2.76/GB
and have 1-5 minute ingestion lag. The same data is available in the Azure Monitor
Metrics Store (free, ~1 minute latency) via the MetricsQueryClient.

TASK: Create corvin/evidence/azure_metrics_adapter.py with:

1. An `AzureMetricsAdapter` class using:
   `from azure.monitor.query import MetricsQueryClient`
   `from azure.identity import DefaultAzureCredential`
   Initialized with DefaultAzureCredential and a MetricsQueryClient.

2. A method `get_aks_node_metrics(
       cluster_resource_id: str,  # /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.ContainerService/managedClusters/{name}
       time_range_minutes: int = 60,
       granularity_minutes: int = 5
   ) -> list[dict]` that queries:
   Metrics: ["node_cpu_usage_percentage", "node_memory_rss_percentage",
             "node_disk_usage_percentage", "kube_pod_status_ready"]
   Returns list of {metric_name, node_name, timestamps, values, unit}.

3. A method `get_apim_metrics(
       apim_resource_id: str,
       time_range_minutes: int = 60
   ) -> dict` that queries:
   Metrics: ["TotalRequests", "SuccessfulRequests", "FailedRequests",
             "UnauthorizedRequests", "Duration", "Capacity"]
   Returns {metric_name: {total/average/p95, time_series: [...]}}

4. A method `get_function_app_metrics(
       function_resource_id: str,
       time_range_minutes: int = 60
   ) -> dict` that queries:
   Metrics: ["FunctionExecutionCount", "FunctionExecutionUnits", "Http2xx",
             "Http4xx", "Http5xx", "AverageResponseTime"]

5. A method `get_event_hub_metrics(
       eventhub_resource_id: str,
       time_range_minutes: int = 60
   ) -> dict` that queries:
   Metrics: ["IncomingMessages", "OutgoingMessages", "ThrottledRequests",
             "ActiveConnections", "IncomingBytes", "OutgoingBytes"]

6. Each method must handle ResourceNotFoundError and MetricsQueryError gracefully
   by returning {} and logging at WARNING.

7. Add to corvin/enrich/enrichment_service.py: if azure_metrics config is present
   (subscription_id, resource_id per connector), call AzureMetricsAdapter methods
   IN PARALLEL with the existing adapters (Feature 3). Results merge into EvidenceBundle
   under a new `platform_metrics` field.

8. Config in connector registry: add `source_type: azure_metrics` connector with fields:
   subscription_id, resource_group, resource_type (aks|apim|function|eventhub), resource_name.

CONSTRAINTS:
- MetricsQueryClient uses a different endpoint than LogsQueryClient — do not share clients.
- Resource IDs must be constructed from config, not hardcoded.
- The MetricsAdapter results must be formatted to match the style of existing adapter
  results — plain list[dict] with consistent field naming.
- azure-monitor-query is already in requirements (same package as LogsQueryClient).
- Write unit tests in tests/evidence/test_azure_metrics_adapter.py.
```

---

### Feature 13 — OpenTelemetry Tracing

**What**: Wrap every LiteLLM call and every tool execution in OpenTelemetry spans.
Add span attributes for model name, token usage, tool name, duration, and investigation
request ID. Forward traces to Azure Monitor via the OpenTelemetry exporter.

**Why**: When an investigation produces a wrong RCA in production, there is currently
no structured way to diagnose which step failed, which model was used, how many tokens
were consumed, or how long each step took. OTel is the industry standard for this.

**Affected files**: All files calling `litellm.acompletion` or `litellm.aembedding`,
`corvin/strategy/agent_tools.py`, new `corvin/core/telemetry.py`

---

#### Implementation Prompt — Feature 13

```
You are adding OpenTelemetry tracing to Corvin, a Python FastAPI AI SRE Copilot.

PROBLEM: Corvin has no structured tracing. When a production investigation produces a
wrong RCA, there is no way to identify which LLM call failed, which tool returned bad
data, or how long each step took. Custom _emit() events exist but are not correlated
into traces and not forwarded to Azure Monitor.

TASK:

1. Create corvin/core/telemetry.py with:
   - A `setup_telemetry()` function called at app startup that configures:
     - A TracerProvider with AzureMonitorTraceExporter (package: azure-monitor-opentelemetry-exporter)
     - Resource attributes: service.name="corvin", service.version from config
     - Batch span processor for async export
     - Falls back to ConsoleSpanExporter if APPLICATIONINSIGHTS_CONNECTION_STRING is not set
   - A module-level `tracer = trace.get_tracer("corvin")`
   - A context manager `llm_span(operation: str, model: str, request_id: str)` that creates
     a span with attributes: llm.operation, llm.model, investigation.request_id
   - A context manager `tool_span(tool_name: str, request_id: str)` for tool executions

2. In corvin/strategy/rca_generator.py: wrap the litellm.acompletion call in
   `with tracer.start_as_current_span("rca.generate") as span:` and add span attributes:
   span.set_attribute("llm.model", model_name)
   span.set_attribute("investigation.request_id", request_id)
   span.set_attribute("llm.prompt_tokens", response.usage.prompt_tokens)
   span.set_attribute("llm.completion_tokens", response.usage.completion_tokens)
   span.set_attribute("rca.confidence", str(rca.confidence))

3. Apply the same pattern to: rca_critic.py, hypothesis_service.py, causal_chain.py,
   fix_strategy_generator.py, postmortem_service.py.

4. In corvin/strategy/agent_tools.py (tool executor dispatch): wrap each tool execution:
   `with tracer.start_as_current_span(f"tool.{tool_name}") as span:`
   span.set_attribute("tool.name", tool_name)
   span.set_attribute("tool.success", str(not isinstance(result, Exception)))
   span.set_attribute("investigation.request_id", request_id)

5. In corvin/investigation/engine.py (or LangGraph graph.py from Feature 11):
   Create a parent span per investigation:
   `with tracer.start_as_current_span("investigation", attributes={"request_id": id, "service": svc, "priority": prio}) as root_span:`
   All child spans (rca, critic, tools) are automatically nested under this parent.

6. Add to config: `telemetry.enabled: bool` (default True),
   `telemetry.connection_string_env: str` (default "APPLICATIONINSIGHTS_CONNECTION_STRING").

CONSTRAINTS:
- OTel instrumentation must be transparent — zero changes to function signatures or
  return types. Only wrap existing calls, do not restructure.
- If the Azure Monitor exporter is unavailable (e.g., no connection string), fall back
  to OTLP exporter (Jaeger/Zipkin compatible) configured via standard OTEL_EXPORTER_OTLP_ENDPOINT env var.
- If both are unavailable, log a WARNING at startup and disable tracing — never fail startup.
- opentelemetry-sdk, opentelemetry-exporter-otlp, azure-monitor-opentelemetry-exporter
  must be added to requirements.txt.
- Do not use LiteLLM's built-in callback system — wrap calls directly with OTel spans
  for more control over span attributes.
```

---

### Feature 14 — RAGAS Evaluation Pipeline

**What**: A standalone eval harness that runs a labeled test suite through the full
Corvin investigation pipeline and scores each output on RAGAS metrics: Faithfulness,
Answer Relevance, and Context Precision. Produces a JSON report with per-investigation
scores and aggregate statistics. Run on demand, on a schedule, or as a CI gate.

**Why**: Corvin currently cannot answer "what is your RCA accuracy?" with numbers.
Even a 20-30 case labeled dataset produces a defensible accuracy metric. This is the
single most important trust-building artifact for the SRE expert review — it turns a
subjective quality claim into a measurement.

**Affected files**: New `corvin/evals/` package, new `corvin/evals/ragas_runner.py`

---

#### Implementation Prompt — Feature 14

```
You are implementing a RAGAS evaluation pipeline in Corvin, a Python FastAPI AI SRE Copilot.

CONTEXT: RAGAS (Retrieval Augmented Generation Assessment) measures RCA quality on three
metrics: Faithfulness (do RCA claims stay within the evidence?), Answer Relevance (does
the RCA address the actual alert?), Context Precision (is the retrieved evidence relevant?).

TASK: Create corvin/evals/ package with:

1. corvin/evals/schemas.py — Pydantic models:
   - `EvalCase`: request_id (optional), service_name, environment, alert_description,
     expected_root_cause: str (ground truth), expected_fix_type: str (e.g. "restart", "rollback"),
     mock_evidence: dict (pre-canned evidence to use instead of live adapters)
   - `EvalResult`: case_id, faithfulness_score: float, answer_relevance_score: float,
     context_precision_score: float, composite_score: float, rca_generated: str,
     expected_rca: str, passed: bool (composite >= threshold), notes: str
   - `EvalReport`: run_id, timestamp, model_config: dict, cases_run: int,
     cases_passed: int, avg_faithfulness: float, avg_answer_relevance: float,
     avg_context_precision: float, avg_composite: float, results: list[EvalResult]

2. corvin/evals/metrics.py — RAGAS-style metrics using LLM-as-judge:

   `async def score_faithfulness(rca: str, evidence: str, model: str) -> float`:
   Prompt: "Score from 0.0 to 1.0 how faithfully the following RCA stays within
   the provided evidence. 1.0 = every claim is directly supported by evidence.
   0.0 = RCA contains claims not in the evidence at all.
   Evidence: {evidence}
   RCA: {rca}
   Output only a float."

   `async def score_answer_relevance(rca: str, alert: str, model: str) -> float`:
   Prompt: "Score from 0.0 to 1.0 how directly the RCA addresses the alert.
   1.0 = RCA directly explains why the alert fired. 0.0 = RCA is unrelated to alert.
   Alert: {alert}. RCA: {rca}. Output only a float."

   `async def score_context_precision(evidence_used: str, evidence_retrieved: str, model: str) -> float`:
   Prompt: "Score from 0.0 to 1.0 what fraction of the retrieved evidence was actually
   relevant to the RCA. 1.0 = all retrieved evidence contributed. 0.0 = none was relevant.
   Retrieved: {evidence_retrieved}. Used in RCA: {evidence_used}. Output only a float."

3. corvin/evals/ragas_runner.py — `EvalRunner` class:
   - `load_cases(path: str) -> list[EvalCase]` — loads JSONL file of eval cases
   - `async run_case(case: EvalCase) -> EvalResult` — runs one eval case:
     a. Builds InvestigationRequest from case fields
     b. Uses case.mock_evidence to stub EnrichmentService (inject canned evidence)
     c. Runs the full investigation pipeline (RCA + Critic + Fix Strategy)
     d. Scores output using the three metric functions
     e. Computes composite_score = (faithfulness * 0.4 + answer_relevance * 0.4 + context_precision * 0.2)
     f. Passes if composite_score >= 0.75
   - `async run_suite(cases_path: str) -> EvalReport` — runs all cases concurrently (asyncio.gather),
     aggregates scores, returns EvalReport
   - `save_report(report: EvalReport, output_path: str)` — saves JSON report

4. corvin/evals/sample_cases.jsonl — 10 sample eval cases covering:
   - OOMKill scenario (clear evidence in mock kube_events)
   - Deployment regression (evidence in activity_log + pod_restarts)
   - APIM 5xx spike (evidence in apim_logs)
   - Database connection exhaustion (evidence in elastic_logs + resource_metrics)
   - External dependency timeout (evidence in apim_logs + container_logs)
   - Low-confidence case (sparse evidence — expected to trigger retry or escalation)
   - Config change root cause (evidence in activity_log only)
   - OOM + deployment same window (ambiguous — tests hypothesis diversity)
   - False alarm (healthy evidence — expected high answer_relevance, different conclusion)
   - Multi-service cascade (evidence spans 2 services)

5. A CLI entry point: `python -m corvin.evals.ragas_runner --cases corvin/evals/sample_cases.jsonl
   --output reports/eval_$(date +%Y%m%d).json` that prints a summary table and exits 1
   if avg_composite < 0.75.

CONSTRAINTS:
- The eval pipeline must not call live Azure Monitor or Kubernetes APIs — all evidence
  comes from mock_evidence in the case file. Mock EnrichmentService by dependency injection.
- Metric scoring uses the fast model (gpt-4.1-mini) — never the high-reasoning model.
- Each metric score must be parsed as float with a try/except — if the LLM returns
  non-numeric output, assign 0.5 (uncertain) and log a WARNING.
- The eval runner must be runnable independently of the FastAPI app — no app startup required.
- Write tests in tests/evals/test_ragas_runner.py covering: score parsing, case loading,
  mock evidence injection, report generation.
```

---

## Post-Improvement Feature Summary

| # | Feature | Week | Gap Closed | Competitive Impact |
|---|---|---|---|---|
| 1 | Context Window Budget | 1 | Silent context overflow | P0 safety — prerequisite for all else |
| 2 | PII Redaction | 1 | GDPR risk | P0 compliance — regulated industry blocker |
| 3 | Parallel Evidence Collection | 1 | P1 response latency | Demonstrable speed improvement |
| 4 | Tool Result Summarization | 1 | Context noise | Improves RCA signal quality |
| 5 | Critic / Reflection Pass | 2 | Unchallenged self-reported confidence | Most impactful single RCA quality improvement |
| 6 | Low-Confidence Retry | 2 | Silent low-quality output | Closes "autonomous recovery" gap |
| 7 | RAG Embedding Pipeline | 3 | No semantic memory | Unlocks incident pattern learning |
| 8 | HyDE Retrieval | 3 | Alert/RCA embedding space mismatch | Correct RAG retrieval quality |
| 9 | Evidence Audit Panel | 3 | Black-box trust | RAEL Backdoor — SRE as verifier |
| 10 | Multi-Model Routing | 4 | Single model for all tasks | Cost optimization + complexity routing |
| 11 | LangGraph Pipeline | 4 | Brittle sequential pipeline | Typed state, retry edges, checkpointing |
| 12 | Azure Monitor Metrics API | 4 | LA cost for free metrics | Cost reduction, lower latency |
| 13 | OpenTelemetry Tracing | 4 | Production debugging blind | Diagnosable production failures |
| 14 | RAGAS Eval Pipeline | 4 | No accuracy metrics | Provable RCA quality for expert review |
