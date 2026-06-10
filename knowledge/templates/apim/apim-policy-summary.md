---
template: apim-policy-summary
version: "1"
description: Document your Azure APIM policy configuration for Corvin's investigation context
---

# <APPLICATION_NAME> — APIM Policy Summary

Document your Azure API Management policies here. Corvin uses this to understand APIM-level enforcement rules when investigating API errors — distinguishing gateway rejections from service failures.

---

## JWT Validation Policy

```
Applies to:       <All APIs / specific API name>
Provider:         <Azure AD / Auth0 / Custom OIDC>
Token issuer:     <https://login.microsoftonline.com/<tenant-id>/v2.0>
Required audience:<api://your-app-id>
Validated at:     APIM gateway — services do NOT re-validate
Header forwarded: <x-ms-client-principal / custom header name>
```

**Effect:** Requests without a valid JWT token matching the issuer and audience receive `HTTP 401 Unauthorized`.

---

## Rate Limiting Policy

```
Applies to:       <All APIs / specific API name>
Rate limit:       <N> calls per <period> per <client IP / subscription key / JWT sub>
Burst allowance:  <N> calls per second
On exceed:        HTTP 429, body: {"code":"QUOTA_EXCEEDED"}
Retry-After:      <Yes — header tells client when to retry / No>
```

---

## IP Filtering Policy

```
Applies to:       <All APIs / specific API name>
Allowed ranges:   <list CIDR ranges, or "Not configured">
IPv6:             <Allowed / Blocked>
On deny:          HTTP 403, body: {"code":"IP_NOT_ALLOWED"}
```

*If no IP filtering is in place, write "Not configured" and remove this block.*

---

## Payload Size Policy

```
Maximum payload:  <N KB/MB>
Applies to:       <POST, PUT / all methods>
On exceed:        HTTP 413, body: {"code":"PAYLOAD_TOO_LARGE"}
```

*If no payload size limit is set, write "Not configured".*

---

## Backend Timeout Policy

```
Forward-request timeout: <N seconds>
Retry count on backend:  <N retries / No retry>
Circuit breaker:         <Yes: trips after N failures in Xs / No>
```

---

## APIM → Backend Routing

| API | Backend URL | Protocol | Notes |
|-----|------------|---------|-------|
| `<api-name>` | `<http://your-aks-service.namespace.svc.cluster.local:port>` | HTTP | `<notes>` |

---

## Operational Notes

- `<Any non-standard APIM policy behaviour specific to this application>`
- `<Known APIM issue or limitation, e.g. "IPv6 clients from corporate network are affected">`
- `<Any APIM policy that overrides the default behaviour>`
