# Corvin AI Context & Memory Architecture

The core challenge of an AI SRE co-pilot is that **LLMs are fundamentally stateless and blind**. They do not inherently know your network topology, API schemas, or organizational history. 

To solve this, Corvin must implement a highly structured **Context Delivery Strategy** that feeds the LLM exactly what it needs, at the exact moment it needs it, without blowing up the token limit.

Here is the ideal architecture for enabling LLM-based RCA in a real-world system.

---

## 1. Context Design (What the LLM Needs to Know)

To reason accurately, the LLM must be fed five distinct layers of knowledge:

1. **Topological Context (Service & Pod Structure):** What services exist, what namespace they live in, what dependencies they have. *Why:* So the LLM can trace an error in `payment-service` back to a DB timeout, rather than blaming the pod itself.
2. **API & Policy Context (Swagger/APIM):** The expected shape of endpoints (e.g., `POST /api/v1/orders`) and the APIM policies applied (e.g., rate limits of 100 req/min). *Why:* If the APIM log shows HTTP 429, the LLM needs to know the rate limit policy to suggest "Increase rate limit policy for premium tier" rather than "Restart the pod."
3. **Behavioral Context (Logs & Metrics):** The actual stream of events occurring right now (stack traces, JVM heap usage). *Why:* This is the raw evidence of the crime.
4. **Historical Context (Long-term Memory):** Past incidents and how they were solved. *Why:* To stop the SRE team from re-diagnosing the same bug twice.
5. **Procedural Context (Runbooks):** "If X happens, do Y." *Why:* To ensure the LLM's suggested fixes comply with your organization's compliance and safety rules.

---

## 2. Context Delivery Strategy (How It Gets There)

We cannot shove 10,000 pages of Swagger docs into the prompt. We must use a **Just-In-Time (JIT) Context Assembly** approach.

### Static Context (Injected on every request)
- **`site.md`:** The "lay of the land" (Cluster name, APIM workspace, list of core services). Extremely concise.
- **System Prompt:** The persona rules ("You are Corvin, an expert SRE...").

### Dynamic Context (Retrieved based on the incident)
- **RAG (Retrieval-Augmented Generation):**
  - *Runbooks:* When the alert says "OOMKilled", the Prompt Builder does a keyword search for `oom` in the `knowledge/runbooks` folder and injects `java-heap-oom.md`.
  - *Past Incidents:* We query the Postgres `investigations` table using vector similarity (pgvector) or simple text search for past RCAs with the same error signature.
- **Evidence Injection:**
  - The `EnrichmentService` pulls exactly the last 60 minutes of logs/metrics from the `ContainerLogsAdapter` and injects them as structured JSON.

---

## 3. Incident Understanding Flow (Step-by-Step)

When an alert fires, Corvin follows this deterministic path:

1. **Trigger Phase:** Webhook receives: `{"alert": "High HTTP 500s on partnerapis", "service": "chad"}`.
2. **Enrichment Phase (Gathering Evidence):** 
   - Ask APIM Log Analytics: "Give me the last 50 failed requests for `partnerapis`."
   - Ask AKS Container Insights: "Give me the logs and pod status for `chad` namespace."
3. **Retrieval Phase (Gathering Context):**
   - Look up `knowledge/runbooks/apim-5xx.md`.
   - Query Postgres for past investigations involving `partnerapis`.
4. **Prompt Assembly Phase:** The `SystemPromptBuilder` stitches Evidence + Runbooks + History together into a single mega-prompt.
5. **Generation Phase:** The LLM reads the assembled context, traces the APIM 500 to a specific pod's Java stack trace, and generates the structured RCA.

---

## 4. Prompt Builder Responsibility

The `SystemPromptBuilder` (located in `corvin/strategy/prompt_builder.py`) is the most important class in the backend. Its job is to **filter noise**.

- **What it DOES do:** 
  - Truncates logs to the last 200 lines to prevent token window overflow.
  - Formats metrics into clean markdown tables rather than raw JSON so the LLM can "read" them easily.
  - Appends the relevant runbooks.
- **What it MUST NOT do:**
  - Send raw, unfiltered gigabytes of logs.
  - Send the entire API spec for endpoints not involved in the alert.

---

## 5. Observability Integration Strategy

To correlate effectively, the adapters must normalize data before it hits the LLM:
- **Logs (ContainerLogsAdapter):** Extracted to show `Timestamp | PodName | ErrorMessage`.
- **Metrics (Azure Monitor):** Summarized as `Metric | Current Value | Threshold`.
- **Traces:** Extracted as `TraceID | Spans (A -> B -> C)`. 
By formatting these consistently, the LLM can easily spot that at `10:04:00`, the APIM latency spiked, which matches a Java Garbage Collection pause in the logs at `10:03:59`.

---

## 6. Output Design (The RCA Shape)

A good RCA is strictly structured (which is why we use `json_object` enforcement). It must include:

1. **`summary`:** 2-sentence executive summary.
2. **`root_cause`:** The exact technical fault (e.g., "Pod `chad-app-xyz` exhausted HikariCP connections due to an unindexed Postgres query").
3. **`impacted_endpoints`:** e.g., `POST /api/v1/users`.
4. **`evidence_used`:** "Correlated APIM Gateway Logs with ContainerLog stack trace".
5. **`confidence`:** HIGH / MEDIUM / LOW.
6. **`fix_actions`:** Array of actionable steps (e.g., `[{"type": "restart_pod", "target": "chad-app-xyz"}]`).

---

## 7. High-Level Architecture (Corvin Stack)

- **Frontend:** React + Vite + Tailwind (Premium ChatOps UI).
- **Backend:** FastAPI (Python). Orchestrates the flow.
- **Memory Store:** Azure Database for PostgreSQL (stores all past RCAs and state).
- **LLM Engine:** Azure AI Foundry (gpt-4.1) configured for `json_object` structured output.
- **Evidence Adapters:** 
  - `ContainerLogsAdapter` (AKS Logs & Inventory)
  - `LogAnalyticsAdapter` (APIM requests)
- **Delivery:** Microsoft Teams Bot API (Adaptive Cards).

---

## 8. The Hackathon Edge (How to Win)

If you want to win the "Ways of Working" hackathon, do not just build a log summarizer. You need to show **Organizational Learning and Automation.**

### The Winning Features:
1. **The "Approve & Execute" Loop (Self-Healing with Human Gate):**
   - The LLM doesn't just say "restart the pod." It puts a button in MS Teams saying `[Approve Restart]`. The judge clicks it, and Corvin hits the AKS API to restart the pod live during the demo.
2. **Incident Memory (The AI remembers):**
   - Show the judge an incident. Resolve it. Then trigger the *exact same incident* 5 minutes later. Corvin's RCA should explicitly say: *"This happened 5 minutes ago. Applying the exact same fix."*
3. **Blameless Post-Mortem Generator:**
   - Instead of developers spending 3 hours writing an RCA doc, Corvin generates a perfectly formatted Markdown RCA document automatically when the incident closes. 
