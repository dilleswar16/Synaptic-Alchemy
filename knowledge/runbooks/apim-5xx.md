# Runbook: APIM 5xx Spike Investigation

**Trigger keyword:** `apim-5xx`

Match when alert description or rule name contains: `apim`, `5xx`, `gateway`, `ApiManagement`

---

## 1. Trigger

Azure Monitor alert fires for elevated 5xx response rate on the APIM gateway.
Typical threshold: > 5% of requests returning 5xx over a 5-minute window.

---

## 2. Evidence to Collect

Priority order:

1. **Log Analytics** – `ApiManagementGatewayLogs` for the affected API, last 30 min
   - Focus on: `ResponseCode`, `BackendResponseCode`, `Url`, `ApiId`, `OperationId`
2. **Elastic logs** – backend service logs for the same time window
   - Filter by: `log.level: ERROR`, `http.response.status_code: [500 TO 599]`
3. **AKS context** – pod status and recent events for the backend service deployment
4. **Azure Activity Log** – any deployments or config changes in the last 60 min

---

## 3. Common Root Causes

1. Backend service is returning 500 due to an unhandled exception (check Elastic logs)
2. Backend service pods are in CrashLoopBackOff (check AKS pod events)
3. Connection pool exhaustion at backend (check connection metrics in Elastic)
4. A recent deployment introduced a regression (check Activity Log for recent deploys)
5. Downstream dependency (DB, cache, external API) is unavailable
6. APIM policy misconfiguration (rare; check APIM policy editor)

---

## 4. Fix Patterns

- If pod crash-loop: identify root exception from pod logs, roll back if recent deploy
- If connection pool: increase pool size or reduce request concurrency
- If downstream dependency: escalate to dependency owner, enable circuit breaker
- If deployment regression: initiate rollback (V3 feature; in V1 flag for manual action)

---

## 5. Escalation Path

- First: check if Engineering on-call is aware
- If backend service: escalate to owning service team
- If APIM policy: escalate to API platform team
- SLA breach risk: notify Engineering Manager
