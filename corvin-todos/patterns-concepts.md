Agentic AI: Patterns, Concepts, and Corvin's Position
What Makes a System "Agentic"
A plain LLM call is stateless input → output. An agentic system adds four properties:

Property	Meaning
Autonomy	The system decides what to do next, not just what to say
Tool Use	It can take actions that affect the world (APIs, DBs, code execution)
Memory	It maintains state across steps and sessions
Goal Pursuit	It works toward an objective across multiple steps, not just one turn
The moment you add a loop that says "should I call a tool or am I done?" — you have an agent.

The Core Patterns
Pattern 1: ReAct (Reason + Act)
Origin: Yao et al., 2022 — "ReAct: Synergizing Reasoning and Acting in Language Models"

Concept: Interleave reasoning traces with tool actions in a loop. The LLM doesn't just answer — it thinks, acts, observes the result, thinks again.


Thought: The user is asking about pod restarts. I should check AKS first.
Action: get_aks_health(service="PartnerAPIs", namespace="prod")
Observation: 3 pods restarted in last 15 minutes, OOMKilled reason.
Thought: OOM kill means memory pressure. I should check container metrics.
Action: get_container_resource_metrics(service="PartnerAPIs")
Observation: Memory at 97% of limit on 2 pods.
Thought: I have enough to answer. Root cause is memory exhaustion.
Answer: ...
The loop structure:


while not done:
    response = llm(messages + tools)
    if response.has_tool_call:
        result = execute_tool(response.tool_call)
        messages.append(tool_result)
        continue
    break  # LLM chose to answer → done
Why it works: The observation step after each action grounds the LLM in actual data rather than hallucinated assumptions. Each action is informed by the previous result.

Where it breaks: For long chains (>6 tool calls), reasoning quality degrades. The LLM loses track of the original goal — this is called "lost in the middle" context collapse.

Pattern 2: Plan-and-Execute
Concept: Separate planning (what steps to take) from execution (actually taking them). A planner LLM creates a structured task list; an executor LLM (or system) runs each step.


User: Investigate the PartnerAPIs incident from 3am

Planner LLM:
  1. Collect logs from Elastic (time: 02:30–03:30)
  2. Check AKS pod status and restart history
  3. Query APIM for error rate spike
  4. Run KQL for 5xx distribution
  5. Synthesize RCA from all evidence

Executor: [runs step 1] → [runs step 2] → [runs step 3] → ...
Why it's better than pure ReAct: ReAct is greedy — it picks the next tool based only on the last observation. Plan-and-Execute has a global view of the task from the start. Less likely to miss a critical step or get stuck in a local loop.

Where it breaks: The plan is written before any evidence is seen. If step 2 reveals something unexpected, the plan is stale. Good implementations re-plan mid-execution.

Pattern 3: Reflexion (Self-Critique Loop)
Origin: Shinn et al., 2023 — "Reflexion: Language Agents with Verbal Reinforcement Learning"

Concept: After generating output, the agent reflects on it — "Was this correct? What could be wrong? What would I do differently?" — and uses that reflection to regenerate.


Round 1:
  RCA: "Root cause is network timeout between PartnerAPIs and upstream."
  
Reflection:
  "This conclusion is unsupported. Evidence shows OOM kills — not network timeouts.
   I anchored on the user's description ('slow responses') rather than the data.
   I should re-examine the container memory metrics."

Round 2:
  RCA: "Root cause is memory exhaustion — container hitting limit, triggering OOM kill
        and pod restart cycle causing the observed latency spikes."
Key insight: The reflection step uses the same LLM but with a different prompt — effectively a critic persona reviewing the generator persona's output.

Why it works: LLMs are better at evaluating answers than generating them from scratch. The reflection pass catches anchoring bias, missed evidence, and logical gaps.

Variants:

Self-Reflection: Same model critiques itself
Adversarial Critique: Separate model tries to disprove the first model's output
Constitutional AI: A set of rules the output must satisfy; fail → retry
Pattern 4: Tool Use & Function Calling
Concept: The LLM can invoke external functions. Tools are the agent's actuators — how it reaches into the real world.

The three-part contract for every tool:


{
  "name": "get_aks_health",
  "description": "Returns pod status, restart count, and events for a K8s deployment. Use this when investigating pod instability or availability issues.",
  "parameters": {
    "service": "The deployment name in Kubernetes",
    "namespace": "The K8s namespace (prod, staging, dev)",
    "lookback_minutes": "How far back to check (default 60)"
  }
}
The description is not documentation for humans — it is the signal the LLM uses to decide when to call this tool. A vague description means the tool gets called at the wrong time or not at all.

Tool categories:

Category	Examples	Risk Level
Read-only queries	DB queries, API reads, log search	Low — safe to auto-run
Transformations	Summarize, translate, classify	Low
Stateful writes	DB inserts, API POSTs	Medium — needs audit log
Destructive actions	Restart pod, rollback, delete	High — needs human approval
Code execution	Run Python/shell in sandbox	High — needs sandboxing
Best practice: Gate by category. Auto-approve reads. Require confirmation for writes. Require explicit APPROVED status for destructive ops.

Pattern 5: Memory Architecture
The most underappreciated agentic pattern. A system without memory is not an agent — it's a stateless function.

There are four memory types, each with a distinct role:


┌─────────────────────────────────────────────────────────┐
│                    MEMORY ARCHITECTURE                   │
├─────────────────┬───────────────────────────────────────┤
│  Working Memory │  The current context window.           │
│  (In-context)   │  What the model is "thinking about"    │
│                 │  right now. Ephemeral, expensive.       │
├─────────────────┼───────────────────────────────────────┤
│  Episodic       │  What happened. Per-session event log. │
│  Memory         │  "Last Tuesday, PartnerAPIs had OOM."  │
│                 │  Retrieved by time or session ID.       │
├─────────────────┼───────────────────────────────────────┤
│  Semantic       │  What the agent knows. Facts, docs,    │
│  Memory         │  embeddings. "PartnerAPIs uses 2GB     │
│                 │  memory limit and runs in prod ns."    │
│                 │  Retrieved by similarity search.        │
├─────────────────┼───────────────────────────────────────┤
│  Procedural     │  How to do things. Tool preferences,   │
│  Memory         │  learned patterns, failure modes.      │
│                 │  "For OOM issues, always check node     │
│                 │  pressure before pod metrics."          │
└─────────────────┴───────────────────────────────────────┘
The write problem: Every memory type needs a write strategy:

Working memory → managed automatically (token budget)
Episodic → write after each session, indexed by timestamp + service
Semantic → write when new facts are learned, embed and store in vector DB
Procedural → write when the agent discovers a better strategy (hardest — requires feedback signal)
Pattern 6: Multi-Agent Coordination
When one agent isn't enough. Multi-agent systems distribute cognition across specialized roles.

Sub-pattern A: Orchestrator-Specialist


Orchestrator
├── Evidence Collector (knows how to query 4 data sources)
├── RCA Analyst (knows how to reason about failures)
└── Fix Strategist (knows K8s operations + remediation)
The orchestrator routes tasks. Specialists have deep, narrow capability. This is the pattern Corvin's F9 targets.

Sub-pattern B: Debate / Adversarial


Hypothesis Generator → "OOM kill is the root cause (80% confidence)"
Critic Agent → "Refute: OOM happened AFTER the spike, not before. Check logs at T-5min."
Generator → "Acknowledged. Revised: upstream timeout caused spike → OOM is secondary."
Two agents argue until convergence. Output quality is dramatically higher than single-shot. Used in high-stakes decisions.

Sub-pattern C: Parallel Fan-Out


Orchestrator spawns 3 agents simultaneously:
  Agent A → investigates Elastic logs
  Agent B → investigates AKS metrics  
  Agent C → investigates APIM traffic
  
All 3 return → Synthesizer merges results → Single coherent output
Fastest pattern for independent evidence collection. Requires a merge step.

Sub-pattern D: Hierarchical (Swarm)


Lead Agent
├── Sub-Agent 1 (spawns its own sub-agents for subtasks)
│   ├── Sub-Sub-Agent 1a
│   └── Sub-Sub-Agent 1b
└── Sub-Agent 2
Full autonomy. Used in code generation agents (devin-style). High capability, hard to control, expensive.

The key principle for all multi-agent patterns: Agents must share a communication protocol — a structured message format they all read and write. Without it, you have sequential function calls, not a multi-agent system.

Pattern 7: Human-in-the-Loop (HITL)
Concept: Insert a human decision point at critical junctions. The agent pauses, presents its reasoning, and waits.


HITL placement options:
  [Before action]  → "I plan to restart 3 pods. Approve?"
  [After output]   → "Here's the RCA. Is this correct before I generate fixes?"
  [On low confidence] → "Confidence is 40%. Please provide more context."
  [On irreversibility] → Always gate before any destructive action.
The three HITL modes:

Interrupt — agent pauses mid-run for human input, then continues
Approval gate — entire pipeline pauses until explicit approval before next phase
Feedback loop — human corrects/annotates output, which feeds back as context
The anti-pattern: HITL on every step. This removes all value from the agent. The design question is: "What is the minimum set of human checkpoints to maintain safety without destroying autonomy?"

Pattern 8: Context Management
The most critical operational pattern. Models have finite context windows. Agentic loops accumulate messages aggressively.

The problem:


Turn 1: System prompt (2,000 tokens)
Turn 2: User message (200 tokens)  
Turn 3: Tool call result — 500 log lines (8,000 tokens)
Turn 4: Another tool result (3,000 tokens)
Turn 5: Another tool result (4,000 tokens)
→ Total: 17,200 tokens. GPT-4 limit: 128K. Still ok.
But: 6 tools × 8,000 tokens = 65,000+ tokens consumed silently.
The LLM never tells you it's running out. It just starts ignoring early context — including your system prompt. Output degrades silently.

Solutions:

Technique	How	When
Token budget per tool	Truncate tool results to max N tokens before appending	Always
Result summarization	After each tool call, have LLM summarize result before storing	When result > threshold
Sliding window	Keep only last N messages + system prompt	Long sessions
Episodic compression	Summarize older turns into a compact paragraph	Very long sessions
Selective retrieval	Don't load full history — retrieve only relevant past turns via RAG	Production memory systems
Pattern 9: Structured Output & Output Contracts
Concept: Force the LLM to produce machine-parseable output by specifying the exact schema in the prompt and using model-level enforcement.


Without structured output:            With structured output:
"The root cause is likely             {"root_cause": "Memory exhaustion",
memory exhaustion, probably            "confidence": "high",
high confidence..."                    "evidence": ["pod_restarts[2]", "metrics[1]"]}
↑ Cannot be parsed reliably           ↑ Directly validated with Pydantic
Three enforcement layers (use all three):

Model-level: response_format={"type": "json_object"} or JSON Schema mode
Prompt-level: Include the exact schema in the prompt: "Output ONLY valid JSON matching this schema: ..."
Parser-level: Validate with Pydantic model_validate() — retry if invalid
Output contracts: The schema is a contract between the LLM and downstream code. Treat it like a typed API. Changing the schema is a breaking change.

Pattern 10: Observability & Evals
The pattern most teams skip until production breaks.

Tracing: Every LLM call, tool call, and tool result should be a span in a distributed trace:


Trace: investigation-req-abc123
  ├── Span: evidence_collection (1.2s)
  │     ├── Span: elastic_adapter (0.8s) → 42 records
  │     └── Span: aks_adapter (0.4s) → 1 pod context
  ├── Span: rca_generation (3.1s)
  │     ├── prompt_tokens: 12,400
  │     ├── completion_tokens: 800
  │     └── model: gpt-5.1
  └── Span: fix_strategy_generation (2.2s)
Without this, when an investigation produces a wrong RCA, you cannot diagnose which step failed or why.

Evals: Automated quality measurement of agent outputs over time.

Factual grounding: Did the RCA reference actual evidence?
Confidence calibration: When the model says "high confidence", is it correct >80% of the time?
Hallucination detection: Did the model suggest checking something Corvin already checked?
Action safety: Did the fix strategy ever recommend actions that contradict the evidence?
Part 2: Pattern-by-Pattern Comparison with Corvin
ReAct Loop
Criterion	Best Practice	Corvin
Loop structure	While not done: think → act → observe	for round in range(6) — hard cap, correct structure
Message threading	Tool result appended as role: tool message	Correct
Termination	LLM signals finish_reason: stop	Correct
Max rounds guard	Config-driven, with warning on hit	Hardcoded _MAX_TOOL_ROUNDS = 6
Context exhaustion	Token budget check before each round	Missing — no token counting
Round 6 behavior	Alert user that round cap was hit	Silent — loop just ends
Verdict: ReAct is implemented correctly but incompletely. The missing token budget check is the most dangerous gap — a session with large tool results will silently degrade at round 4-5 with no signal.

Plan-and-Execute
Criterion	Best Practice	Corvin
Explicit plan step	Planner LLM generates step list before execution	Not present
Plan visibility	Plan shown to user/operator before running	Not present
Re-planning	Mid-execution plan update on unexpected evidence	Not present
Investigation pipeline	engine.py 4-stage pipeline approximates a fixed plan	Hardcoded, not LLM-generated
Verdict: Corvin's investigation pipeline (Evidence → RCA → Fix → Result) is a hand-coded plan, not a dynamic one. It works for known investigation shapes but cannot adapt to unusual incidents (e.g., a multi-service cascade failure that needs 3 extra evidence rounds before RCA is reliable). This is the pattern with the highest architectural impact to add.

Reflexion / Self-Critique
Criterion	Best Practice	Corvin
Critic pass on RCA	Separate LLM call reviews output before acceptance	Missing entirely
Confidence as quality gate	Low confidence → retry with different angle	Low confidence → UI warning, execution continues
Evidence grounding check	Critic verifies each claim is traceable to evidence	Missing
Self-correction loop	Agent can loop back to collect more evidence	Missing
Hypothesis debate	N adversarial agents argue competing hypotheses	F8 generates N hypotheses in one call — not adversarial
Verdict: This is Corvin's most significant agentic gap. The RCA is a single-shot generation. If the model anchors on the wrong cause (common when evidence is mixed), no mechanism exists to catch it before it propagates to fix strategy generation. A one-pass critic prompt costs ~$0.02 per investigation and would catch the most dangerous class of errors.

Tool Use & Function Calling
Criterion	Best Practice	Corvin
Tool descriptions	Precise, use-case-specific, LLM-facing	Generally good — most tools have clear names
Tool categorization	Read / Write / Destructive with automatic gating	Not present — all tools treated equally
Tool result type safety	Typed return contracts	Returns raw dict / list[dict] — no contract
Tool failure handling	Retry with backoff, fallback tool	try/except in enrichment — silent skip
Tool result size limit	Truncate before appending to context	Missing
Tool middleware	Log, rate-limit, cache at the tool layer	Missing
Dynamic tool registration	Add tools at runtime	Missing — static list at startup
Verdict: Tool definitions are adequate for the current 15-tool set. The critical missing pieces are: (1) result size limits before context append, and (2) write/destructive categorization so the agent cannot accidentally call a destructive tool without an explicit approval flag.

Memory Architecture
Memory Type	Best Practice	Corvin
Working Memory	Token budget managed, oldest turns summarized	Raw message list from DB — no budget management
Episodic Memory	Per-session event log, retrievable by time/service	corvin_messages table — raw turns, not structured events
Semantic Memory	Embeddings of facts, retrieved by similarity	pgvector on past RCAs — partial; only incident-scoped
Procedural Memory	Learned tool preferences, failure pattern library	Missing — no learning from past runs
Verdict: Corvin has working memory (the message list) and a partial semantic memory (pgvector similarity on past RCAs). Episodic and procedural memory are absent. The practical consequence: Corvin investigates the same service having the same incident type for the 10th time with no accumulated knowledge from the previous 9 — every investigation starts from scratch.

The highest-value addition: After each investigation closes, write a structured episodic record: {service, environment, root_cause, confidence, actions_taken, outcome}. Retrieve the top-3 similar records at investigation start and inject them into the system prompt. This is 30 lines of code and would meaningfully improve RCA accuracy for recurring incidents.

Multi-Agent Coordination
Criterion	Best Practice	Corvin F9
Agent communication	Shared message thread all agents read/write	Agents receive function arguments, not a thread
Dynamic routing	LLM-based selector uses all prior messages	Selector has a deterministic fast-path — LLM rarely fires
Agent specialization	Each agent has its own system prompt + tool set	Agents are LLM wrappers with no distinct tool sets
Agent-to-agent query	Agent A can ask Agent B for clarification	Impossible in current architecture
Looping / re-entry	Orchestrator can send evidence collector back	Not present
Parallel execution	Multiple agents run concurrently	Sequential only
Termination contract	Typed termination signal or node	String match if _TERMINATION_SIGNAL in msg.content
Trace per agent	Each agent's turns individually traced	MultiAgentTrace.turns — exists, basic
Verdict: F9 is a sequential function call chain with agent-flavored naming. The fix is not complex — agents need a shared thread: list[AgentMessage] that they all append to and read from, with each agent receiving the full thread (not just its predecessor's output). This unlocks the RCA Analyst being able to send a message back to the Evidence Collector asking for a specific additional query.

Human-in-the-Loop
Criterion	Best Practice	Corvin
Approval before destructive action	Hard gate — execution blocked until APPROVED	Correct — approval_status != APPROVED raises
HITL on low confidence	Escalate to human when confidence < threshold	Warning flag only — execution still proceeds
Mid-run interrupt	Pause agent mid-investigation for human input	Not present — investigation runs to completion
Approval channels	In-app, Teams, email — wherever human is	Teams notification for autonomous agent
Approval audit	Who approved, when, what they saw	approved_by column exists — good
Partial approval	Approve action 1 and 3, reject action 2	Not present — all-or-nothing approval
Verdict: HITL for execution is correctly implemented. The gap is mid-pipeline HITL — the investigation runs fully before a human ever sees anything. For P1 incidents where the RCA is complex or uncertain, there's no mechanism to pause after evidence collection and ask: "We found OOM kills and a recent deployment — which do you think is primary?" This would feed directly into the F8 hypothesis selection flow.

Context Management
Criterion	Best Practice	Corvin
Token counting	Count before every append	Missing — tiktoken is installed but unused in agent loop
Tool result truncation	Max N tokens per result	Missing
Result summarization	Summarize large results before storing	Missing
Sliding window	Drop oldest non-system messages	Missing
Context warning	Warn when approaching 80% of limit	Missing
Session history loading	Load full history from DB	load_session_history() loads ALL messages — dangerous for long sessions
Verdict: This is the highest-severity unaddressed gap in the entire codebase. Every other gap causes degraded output. This one can cause complete failure — a long Corvin Command Center session that ran 10 tool calls with large results will load a 60,000+ token history on the next message, silently truncating the system prompt and early context. The fix is straightforward: count tokens after each tool result append, truncate the result to stay under budget.

Structured Output & Output Contracts
Criterion	Best Practice	Corvin
Model-level enforcement	response_format=json_object	Correct
Prompt-level schema	Schema embedded in user message	Correct — RCAOutput.model_json_schema() injected
Parser-level validation	Pydantic model_validate() with retry	model_validate() present, retry missing
Parse failure handling	Retry with corrected prompt	Missing — raises exception
Schema versioning	Output schema treated as versioned API	Missing — schema changes silently break parsing
Partial output recovery	If field X is missing, use default	Pydantic defaults used — partially covered
Verdict: Two out of three enforcement layers are in place. The missing retry on parse failure means that in ~2-3% of cases (when the model produces invalid JSON despite json_object mode), the investigation crashes rather than retrying. A simple for attempt in range(3): try: parse(); break; except: retry_with_correction() wrapper would eliminate this failure mode.

Observability & Evals
Criterion	Best Practice	Corvin
Distributed tracing	OpenTelemetry spans per LLM call + tool call	Missing — custom _emit() only
Prompt token tracking	Log prompt/completion tokens per call	Missing
Latency tracking	Per-phase timing	MultiAgentTrace.total_elapsed_ms — partial
LLM call logging	Request/response stored for debugging	Missing outside of message history
Quality evals	Automated scoring of RCA accuracy	Missing
Confidence calibration	Track model's self-reported confidence vs. actual	Missing
Hallucination detection	Check if RCA references non-existent evidence	Missing
Cost tracking	$ per investigation	Missing
Regression detection	Alert when RCA quality degrades after model upgrade	Missing
Verdict: Corvin has observability at the business event level (investigation_started, teams_notified) but zero observability at the LLM level. This is the pattern gap with the highest operational consequence — when a model upgrade changes output quality, there is no way to detect it before users report wrong RCAs.

Summary Scorecard

Pattern                      Implementation   Completeness
─────────────────────────────────────────────────────────
ReAct Loop                       ✅ Present       75%  (missing token budget)
Plan-and-Execute                 🔴 Missing        0%  (fixed pipeline ≠ plan)
Reflexion / Self-Critique        🔴 Missing        0%
Tool Use & Function Calling      ✅ Present       65%  (missing size limits, categorization)
Memory — Working                 🟡 Partial       40%  (no budget management)
Memory — Episodic                🟡 Partial       30%  (message log, not structured events)
Memory — Semantic                🟡 Partial       40%  (RCA-scoped pgvector only)
Memory — Procedural              🔴 Missing        0%
Multi-Agent Coordination         🟡 Present       30%  (sequential pipeline, not conversational)
Human-in-the-Loop                ✅ Present       70%  (missing mid-pipeline interrupt + partial approval)
Context Management               🔴 Missing        5%  (tiktoken installed, not used)
Structured Output                ✅ Present       80%  (missing retry on parse failure)
Observability & Evals            🔴 Missing       10%  (business events only, no LLM tracing)

─────────────────────────────────────────────────────────
Overall Agentic Maturity                         ~42%
Priority Order for Closing the Gaps
Ordered by: (impact × implementation ease) ÷ risk

Priority	Pattern	Change	Effort
1	Context Management	Count tokens per tool result; truncate at 80% of limit	1 day
2	Structured Output	Wrap model_validate() in retry loop (3 attempts)	2 hours
3	Reflexion	Add critic LLM pass after RCA generation	1 day
4	Memory — Episodic	Structured incident record written after close; retrieved at start	2 days
5	Parallel Evidence	asyncio.gather() on the 4 enrichment adapters	1 day
6	Observability	OTel spans on LLM calls + tool calls → Azure Monitor	3 days
7	Multi-Agent — Shared Thread	Give all F9 agents a shared message thread they read/write	2 days
8	Plan-and-Execute	Planner LLM generates investigation plan before evidence collection	3 days
Items 1–3 eliminate the most dangerous failure modes. Items 4–8 advance the system from ~42% to ~75% agentic maturity.