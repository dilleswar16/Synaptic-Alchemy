---
template: service-api-spec
version: "1"
description: API surface documentation for an APIM-fronted microservice
---

# <SERVICE_NAME> — API Specification & APIM Policy

## Overview

| Property | Value |
|----------|-------|
| API base path | `<e.g. /api/v1/orders>` |
| APIM product | `<APIM product name>` |
| Auth | `<Bearer JWT / API Key / mTLS / None>` |
| Rate limit | `<N calls per Xs per client IP>` |
| Payload size limit | `<N KB/MB>` |

---

## Endpoints

| Method | Path | Auth Required | Rate Limited | Success | Common Failure |
|--------|------|--------------|-------------|---------|---------------|
| `GET` | `<path>` | `<Yes/No>` | `<Yes/No>` | `200` | `<404, 500 — why?>` |
| `POST` | `<path>` | `<Yes/No>` | `<Yes/No>` | `201` | `<400, 422 — why?>` |

---

## APIM Policy Summary

### JWT Validation

```
Provider:   <Azure AD / Auth0 / custom OIDC>
Tenant:     <tenant-id-placeholder>
Audience:   <api://your-app-id>
Issuer:     <https://login.microsoftonline.com/<tenant>/v2.0>
Validated:  At APIM gateway — services trust the forwarded claims header
```

### Rate Limiting

```
Policy:     <calls/period per key>
Key:        <client IP / subscription key / JWT sub>
On exceed:  HTTP 429, Retry-After header set
```

### IP Allowlist

```
Allowed:    <CIDR ranges — remove if not applicable>
IPv6:       <Allowed / Blocked>
On deny:    HTTP 403, body: {"code":"IP_NOT_ALLOWED"}
```

### Payload Limits

```
Max size:   <N KB>
On exceed:  HTTP 413, body: {"code":"PAYLOAD_TOO_LARGE"}
```

---

## Known Failure Modes

| Scenario | HTTP Status | APIM Error Code | Diagnosis |
|----------|------------|-----------------|----------|
| JWT expired or invalid | `401` | `Unauthorized` | Check token issuer and expiry |
| IP not in allowlist | `403` | `IP_NOT_ALLOWED` | APIM allowlist — not a service issue |
| IPv6 source address | `403` | `IPV6_NOT_SUPPORTED` | Client using IPv6 — APIM policy blocks |
| Request too large | `413` | `PAYLOAD_TOO_LARGE` | Client sending oversized payload |
| Too many requests | `429` | `QUOTA_EXCEEDED` | Client hitting rate limit |
| Backend service down | `502/503` | — | AKS pod not ready or crashing |
| `<Custom failure mode>` | `<code>` | `<error code>` | `<how to diagnose>` |

---

## SRE Notes

- **401 from APIM** → Token issue. Check token expiry, audience, and issuer. Not a service code issue.
- **403 from APIM** → IP allowlist or auth policy. Check APIM logs first, not service logs.
- **503 from APIM** → Backend unreachable. Check AKS pod health (`kubectl get pods`).
- `<Add your specific operational notes here>`
