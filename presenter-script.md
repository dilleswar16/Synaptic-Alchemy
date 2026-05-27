# Corvin Hackathon — Presenter Script

> **Total Time:** 4–6 minutes (Deck ~3 min → Live Demo ~2–3 min)  
> **Slides to present:** 4, 5, 6, 8 → then switch to live web UI  
> **Tip:** Talk to the audience, not the screen. Point at visuals when referencing them.

---

## SLIDE 4 — Agentic Workflow ⏱️ ~50 sec

> So here's the core of Corvin — the investigation pipeline. Nine stages, **fully automated**, from alert to learning.
>
> An Azure alert fires — or an SRE triggers manually — and Corvin kicks off. It fans out across **seven live evidence adapters** — AKS, Elastic, APIM, Container Insights, Activity Logs — gathering telemetry in parallel. It then injects relevant **runbooks and incident memory** from past investigations.
>
> Now here's where it gets interesting. The AI layer — **GPT-5.1 on Azure AI Foundry** — doesn't just get one shot. It runs an **autonomous tool orchestration loop**. The LLM *reasons*, picks a tool, executes it, gets real data back, synthesises, and loops again — up to six rounds — until it has enough evidence to produce a high-confidence RCA.
>
> This isn't a chatbot wrapping an API. This is an **autonomous reasoning engine** with real tools.
>
> After the RCA and fix strategy are generated, everything stops at a **human approval gate** — nothing touches production without human sign-off. Once approved, Corvin executes the fix, verifies health, and auto-generates a blameless post-mortem. The whole pipeline — **under five minutes**.

### 🎯 Key points to emphasize:
- **9-stage pipeline** — point at the flow diagram
- **Agentic loop** — the LLM picks tools autonomously
- **Human approval gate** — nothing runs without sign-off
- **Under 5 minutes** — land this hard

---

## SLIDE 5 — Architecture ⏱️ ~50 sec

> The architecture is modular, adapter-based, and **100% Azure-native** — no new infrastructure required.
>
> At the top — five trigger sources — Azure Monitor webhooks, REST API, Teams bot, CLI, and the predictive anomaly detector — all funnel into the same investigation engine.
>
> The evidence layer — **five live adapters** — Container Logs via KQL, AKS context via the Kubernetes API, Log Analytics for APIM gateway data, Azure Activity for deployment changes, and APIM Analytics with **20+ pre-validated KQL templates**.
>
> The AI intelligence layer is the brain — **GPT-5.1 via Azure AI Foundry's Responses API** — visible chain-of-thought reasoning. The knowledge layer injects site architecture facts and runbooks into every prompt — so the LLM is *grounded*, not hallucinating.
>
> Below that — mandatory approval gate before AKS execution. And five delivery adapters — **Teams, Email, ADO Wiki, DevOps work items, and SharePoint** — so the RCA reaches every stakeholder automatically.
>
> Persistence is **PostgreSQL** — 12 Alembic migrations, JSONB evidence storage, and incident memory that gets smarter with every investigation.

### 🎯 Key points to emphasize:
- **100% Azure-native** — no new infra
- **5 evidence adapters** — point at the tier
- **5 delivery adapters** — Teams, Email, Wiki, DevOps, SharePoint
- **PostgreSQL + incident memory** — the system learns

---

## SLIDE 6 — Tools the LLM Can Call ⏱️ ~35 sec

> **"now let me show you what the AI actually works with.**
>
> **this is the tool registry. The AI decides on its own which tool to pick based on the problem.**
>
> **Site knowledge loads the platform blueprint. Runbooks match your team's SOPs automatically.** 
>
> **Incident memory checks — have we seen this before? What fixed it? That knowledge compounds with every incident.**
>
> **Then live telemetry — container metrics from AKS, APIM logs via KQL — all real-time. And the kicker — the LLM can write its own KQL on the fly and run it against Log Analytics.**
>
> **All five tools follow the MCP schema pattern — zero hallucination — every answer grounded in real data from your Azure environment.**
>
> **That's not a chatbot. That's a co-pilot that actually flies the plane.**
>
> **Let me show you this live..."**

### 🎯 Punchline: *"That's not a chatbot — that's a co-pilot that actually flies the plane"*

---

## 🖥️ LIVE DEMO — Transition ⏱️ ~10 sec

> Alright — enough slides. Let me switch to the live platform and show you Corvin investigating a real incident — real Azure data, real reasoning, real results.

### Demo flow suggestion:
1. Open **Command Center** (chatbot)
2. Ask something like *"What's happening with order-service?"*
3. Show the **streaming response** — tool calls appearing live
4. Point out **thinking tokens** visible in real-time
5. Show an **investigation detail page** — RCA + Fix Strategy
6. Quick flash of **Predictive Analytics** or **Topology** page

---

## SLIDE 8 — Future Roadmap ⏱️ ~35 sec

> So where does Corvin go from here? Four enhancements that take it from powerful to **unstoppable**.
>
> First — an **Auto-Approve Engine**. If confidence is above 90%, we have a matching runbook, and it's a P3 at 3AM — skip the human, auto-execute, full audit trail preserved.
>
> Second — **Multi-Agent Mesh**. Instead of one LLM doing everything sequentially, we split into specialist agents — Evidence, RCA, Fix — all running in **parallel**. Three-x faster convergence on complex P1s.
>
> Third — **Evidence Parallelization** with `asyncio.gather`. Right now our 7 adapters run sequentially — about 10 seconds. Fire them all concurrently? **Under 2 seconds**. Five-x speedup on the critical path.
>
> And finally — **Enterprise Auth and RBAC**. Azure AD SSO, JWT-secured endpoints, four roles from Admin to Read-Only. This is what unlocks Corvin for **every team across the enterprise**.
>
> The foundation is live. The roadmap is clear.

### 🎯 Key points to emphasize:
- **Auto-approve** — removes human latency for known issues
- **Multi-agent** — future evolution, shows you've thought ahead
- **asyncio.gather** — technical depth, judges appreciate it
- **RBAC** — enterprise readiness story

---

## 🗣️ If Judges Ask...

| Question | Your Answer |
|----------|-------------|
| *"Is this multi-agent?"* | "Today it's a single orchestrator agent with a deterministic evidence pipeline — which is the right call for reliability. Multi-agent is our V5 evolution for parallel specialist reasoning." |
| *"How do you prevent hallucination?"* | "Every tool returns real Azure telemetry. The LLM is grounded in live data, runbooks, and incident memory — not generating from training data." |
| *"What model are you using?"* | "GPT-5.1 via Azure AI Foundry, Responses API with chain-of-thought reasoning. Fallback to GPT-4.1-mini for low-latency paths." |
| *"Is this deployed?"* | "Yes — live on Azure App Service + Static Web Apps + PostgreSQL. Not a prototype — a working platform with 437 tests." |
| *"What about security?"* | "Human approval is mandatory for all execution. No PII in payloads. Blameless post-mortems by design. RBAC is on the V5 roadmap." |

---

> 🔥 **Remember:** You're not reading slides — you're telling a story.  
> The story is: *"3AM alert → AI investigates → human approves → problem solved → system learns."*
