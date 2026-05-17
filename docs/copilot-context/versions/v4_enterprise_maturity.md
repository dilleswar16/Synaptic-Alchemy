# Corvin V4.0 & V4.1 — Enterprise Risk & UI Maturity

## Overview
Based on stakeholder feedback, V3.99 was incredibly feature-rich but suffered from "Cockpit Syndrome" (too much information at once) and lacked a critical enterprise dimension: Incident Priority (P1/P2/P3). 

V4.0 and V4.1 address these gaps, transitioning Corvin from a technical debugging tool to a mature Incident Management Platform.

---

## V4.0: Risk & Priority Classification
**Goal:** Align AI investigations with real-world ITIL and SRE triage practices.

### Implementation Details:
*   **Schema Update:** Added an `incident_priority` field (P1, P2, P3) to the `InvestigationRequest` domain model.
*   **Classification Logic:**
    *   **P1 (Critical):** Major outages in `prod`, core dependencies down (e.g., `fundsso`), or massive blast radius.
    *   **P2 (Degraded):** Performance degradation, partial pod failures, or high-severity predictive alerts.
    *   **P3 (Warning):** Issues in `dev`/`test` environments, or low-impact anomalies.
*   **UI Integration:** High-contrast Priority Badges added to the Dashboard list and Investigation Hero cards. This allows operators to visually triage the queue instantly.

---

## V4.1: Progressive Disclosure UI (De-cluttering)
**Goal:** Enforce a "Crisis ➔ Cause ➔ Action" visual hierarchy. Stop overwhelming the user with raw logs before they understand the problem.

### Architectural Decisions:
1.  **Re-ordering the Detail Page:**
    *   *Old Flow:* Context → Evidence (Logs) → Similar Incidents → RCA.
    *   *New Flow:* Context → **RCA (The Answer)** → **Fix Strategy (The Action)** → Collapsed Evidence (The Proof).
2.  **Progressive Disclosure:**
    *   The `EvidenceSection` and `AuditTrailSection` are now **collapsed by default**.
    *   *Reasoning:* SREs don't want to read 50 lines of JSON logs if the AI has already provided a high-confidence summary. The logs remain accessible for verification, but they no longer block the critical path to remediation.
3.  **Visual Hierarchy:**
    *   The `TransparencyTrace` (Mermaid diagram) is elevated to act as the primary visual anchor for the RCA, replacing text-heavy analysis as the first thing the eye sees.

## Status
*   **V4.0**: Database migrations and API contracts updated.
*   **V4.1**: React components re-ordered and state defaults updated.
