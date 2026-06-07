# Corvin vs. Google SRE Canon — Alignment & Gaps

## ✅ Where We're STRONGLY Aligned

| Google SRE Principle | Corvin Implementation | Book Chapter |
|---|---|---|
| **SLOs/SLIs/SLAs** | `corvin/slo/snapshot.py` — availability + latency SLIs, error budget % remaining, burn rate | Ch 4 |
| **Error Budgets** | `corvin/strategy/sla.py` — monthly downtime budget tracking, breach prediction, severity classification | Ch 3 |
| **Blameless Post-mortems** | `corvin/strategy/postmortem_service.py` — structured, deterministic assembly + LLM prevention section | Ch 15 |
| **Four Golden Signals** | Evidence adapters collect latency, traffic, errors, saturation from Elastic + Log Analytics + APIM | Ch 6 |
| **Eliminating Toil** | The entire product *is* toil elimination — automated investigation replaces manual triage | Ch 5 |
| **Automation Hierarchy** | Investigation engine automates: detect → enrich → RCA → fix strategy → comms | Ch 7 |
| **Incident Management Roles** | Incident Commander analog = Corvin autonomous agent; Communications = `comms_draft.py` (3 audience levels) | Ch 14 |
| **Live Incident State Doc** | Investigation results are persisted, real-time SSE streaming, live topology dashboard | Ch 14 |
| **Postmortem Triggers** | Auto-triggered after investigation (user-visible degradation, on-call intervention) | Ch 15 |
| **Monitoring: White-box + Black-box** | White-box: Elastic metrics/logs, KQL; Black-box: `validations/runner.py` synthetic HTTP checks | Ch 6 |
| **Capacity Planning** | `capacity_forecaster.py` — linear regression, time-to-exhaustion, scaling recommendations | Ch 18/22 |
| **Cascading Failure Prevention** | `blast_radius.py` + topology mapping + dependency graphs | Ch 22 |
| **Testing for Reliability** | `chaos_engine.py` — LLM-generated chaos experiments (pod-kill, network-delay, resource-exhaust) | Ch 17 |
| **Simplicity** | Config-driven YAML policies, pluggable adapters, no monolithic blob | Ch 9 |
| **Release Engineering** | CI/CD via Azure Pipelines + rollback_deployment() in execution service | Ch 8 |

---

## 🔴 MAJOR GAPS

### 1. Error Budget Policy Enforcement (Ch 3 — "Motivation for Error Budgets")

**What Google says**: Error budgets are a *governance mechanism* — when budget is exhausted, deployments STOP. SRE has authority to halt releases.

**What Corvin has**: SLO snapshots + burn rate math. But **no policy engine that blocks deployments when budget is spent**. No integration with CI/CD to gate releases based on error budget consumption.

**Why this matters**: An SRE expert will ask "so when the budget is consumed, what happens?" and our answer is "we show a red badge." That's observability, not governance.

**Fix**: Add an error budget policy check to the pipeline (even a stub that returns `deploy_allowed: bool` based on budget remaining).

---

### 2. On-Call Management (Ch 11 — "Being On-Call")

**What Google says**: On-call rotations, balanced workload (max 25% on-call time), handoff protocols, escalation chains, interrupts tracked quantitatively.

**What Corvin has**: **Nothing**. No on-call schedule, no rotation management, no pager fatigue tracking, no escalation policies.

**Why this matters**: Every competitor (PagerDuty, Rootly, incident.io) has this. An SRE leader will ask "how does this integrate with our on-call rotation?" — Corvin can't answer.

**Fix**: At minimum, model an `OnCallSchedule` that determines who receives Teams notifications. Even better: track pages-per-shift metrics.

---

### 3. Alert Noise Reduction / Symptom vs. Cause (Ch 6 & Ch 10)

**What Google says**: "Alert on symptoms, not causes." Google says "every page should be actionable" and "every page requires intelligence."

**What Corvin has**: `alert_correlation.py` groups related alerts, but **no suppression/deduplication window, no flapping detection, no alert quality scoring**. Every Azure alert fires a full investigation.

**Why this matters**: In production with 50+ services, alert storms will DDoS the investigation engine.

**Fix**: Add a suppression window (e.g., "don't re-investigate same service within 15min if already active") and alert quality feedback loop.

---

### 4. Toil Measurement & Tracking (Ch 5)

**What Google says**: Track toil quantitatively (% of time). Cap at 50%. Report quarterly. If toil is rising, alarm.

**What Corvin has**: ROI calculator estimates MTTR savings, but **no actual toil tracking** — no measurement of how much time engineers spend on manual work before/after Corvin.

**Why this matters**: Leadership will ask "how much toil did this eliminate?" and you need a metric, not a projection.

**Fix**: Track `time_to_acknowledge`, `time_to_resolve`, `manual_steps_avoided` per investigation. Show a toil-reduction dashboard.

---

### 5. Canarying / Progressive Rollout (Workbook Ch 16)

**What Google says**: Test releases on small subsets before full deployment. Canary duration and size are critical parameters.

**What Corvin has**: `rollback_deployment()` exists but **no canary analysis, no progressive rollout support, no deployment risk scoring**.

**Why this matters**: When Corvin recommends a fix (e.g., "scale to 5 replicas"), there's no mechanism to canary that change before full execution.

**Fix**: Add a `canary_percentage` field to fix actions, and a validation step post-execution that checks metrics before proceeding to full rollout.

---

### 6. Incident Roles / Commander Handoff (Ch 14)

**What Google says**: Explicit roles: Incident Commander, Ops Lead, Communications Lead, Planning Lead. Clear handoff protocol ("You're now IC, okay?").

**What Corvin has**: No role assignment or rotation during an incident. The `autonomous_agent.py` acts as a solo operator.

**Why this matters**: Enterprise SRE teams are 5-15 people. "Who's working on what?" is a real-time coordination problem.

**Fix**: Add incident role tracking (even just `commander`, `ops_lead`, `comms_lead` fields on investigation). Allow reassignment.

---

### 7. Change Management / Deployment Correlation (Ch 12 — "Effective Troubleshooting")

**What Google says**: "What changed?" is always the first question. Correlate recent deployments with incidents.

**What Corvin has**: `azure_activity_adapter.py` fetches activity logs, but **no first-class "recent deployments" panel or auto-correlation score** between a deployment event and the incident timeline.

**Why this matters**: This is table-stakes for SRE tools. Datadog's Bits AI and Rootly both auto-correlate deployments.

**Fix**: Surface a "Recent Changes" section in investigation results with a time-proximity score to the incident start. Data already exists — just surface it prominently.

---

## 🟡 Minor Gaps (Nice-to-Have)

| Gap | Google Concept | Risk |
|---|---|---|
| No runbook versioning/diff | Postmortem action items evolve | Low |
| No "Wheel of Misfortune" / game days | Ch 28 — training exercises | Low |
| No structured incident severity levels (SEV1-4) | Industry standard | Medium |
| No Service Catalog ownership model | "Who owns this?" | Medium |
| No "production meeting" automation | Appendix F | Low |

---

## 📊 Alignment Score

| Domain | Score | Notes |
|---|---|---|
| SLOs & Error Budgets | 7/10 | Math is there, governance is not |
| Monitoring & Alerting | 8/10 | Four golden signals ✓, noise reduction ✗ |
| Incident Response | 6/10 | Automated well, but no role coordination |
| Post-Mortems | 9/10 | Best-in-class for an internal tool |
| Toil Elimination | 7/10 | *Is* the product, but doesn't measure itself |
| Capacity Planning | 9/10 | Forecasting + cost estimation ✓ |
| Chaos Engineering | 8/10 | Experiments generated, approval gated |
| On-Call & Escalation | 2/10 | Major gap |
| Change Management | 5/10 | Data exists, not surfaced well |
| Release Engineering | 6/10 | Rollback exists, no canary |

---

## 🎯 Top 3 Fixes Before Presenting to Leadership

1. **Error Budget Policy Gate** — Add a `should_allow_deploy()` function that checks budget
2. **Alert Suppression Window** — Prevent re-investigation of the same service within a configurable window
3. **Incident Severity Classification** (SEV1-4) — Add `severity` enum to `InvestigationRequest`, route differently based on severity

---

*References: Google SRE Book (2016), Google SRE Workbook (2018)*
