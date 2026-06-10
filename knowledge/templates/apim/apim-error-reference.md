---
template: apim-error-reference
version: "1"
description: Generic Azure API Management error code reference — applies to all APIM deployments
note: This file requires NO customization. These are standard Azure APIM error codes.
---

# Azure APIM — Standard Error Code Reference

These error codes are produced by Azure API Management itself, not by backend services. When Corvin observes these codes, the investigation path leads to APIM policy configuration — not to service code or infrastructure.

---

## Gateway-Level Errors

| HTTP Status | Error Code | Meaning | Common Cause | Investigation Path |
|------------|-----------|---------|-------------|-------------------|
| `401` | `Unauthorized` | JWT token is missing, expired, malformed, or has wrong audience | Client token expired; wrong `aud` claim; wrong issuer | Check APIM JWT validation policy. Decode the token and verify `aud`, `iss`, `exp`. Not a service-code issue. |
| `403` | `IP_NOT_ALLOWED` | Source IP address is not in the APIM allowlist | New deployment environment, VPN change, IPv6 source | Check APIM IP filtering policy. Add IP range if legitimate. |
| `403` | `IPV6_NOT_SUPPORTED` | Source is using IPv6, which APIM policy blocks | Client connecting via IPv6 network | Confirm IPv6 restriction is intentional. Update APIM policy or advise client to use IPv4. |
| `413` | `PAYLOAD_TOO_LARGE` | Request body exceeds the APIM payload size policy | Client sending large file or bulk request | Check APIM policy for `body-size-limit`. Increase limit or reject oversized payloads by design. |
| `429` | `QUOTA_EXCEEDED` | Client has exceeded the rate limit defined in APIM | Traffic burst, misconfigured client retry loop | Check APIM rate-limit policy. If legitimate traffic, increase limit. If client bug, fix retry logic. |
| `429` | `RATE_LIMIT_EXCEEDED` | Variant of quota exceeded (per-second vs. per-period) | Same as QUOTA_EXCEEDED | Same investigation path as QUOTA_EXCEEDED |
| `500` | `InternalServerError` (APIM) | APIM policy itself threw an error (rare) | Policy expression bug; invalid policy XML | Check APIM diagnostic logs; look at policy execution trace |
| `502` | `BadGateway` | APIM could not reach the backend service | AKS service not running; wrong backend URL in APIM | Check AKS pod health; check APIM backend URL configuration |
| `503` | `ServiceUnavailable` | Backend returned 503 or APIM circuit breaker tripped | Backend overloaded or unhealthy | Check AKS pod health, deployment events, HPA status |
| `504` | `GatewayTimeout` | Backend did not respond within APIM timeout | Backend is slow (DB query, external call); APIM timeout too short | Check backend response times; check APIM `forward-request` timeout setting |

---

## Reading APIM Error Responses

APIM errors return a JSON body with a `code` field:

```json
{
  "statusCode": 403,
  "message": "Forbidden",
  "code": "IP_NOT_ALLOWED"
}
```

The `code` field maps to the Error Code column above.

---

## APIM vs. Service Errors — Decision Rule

When you see an HTTP error, use this decision rule to determine the origin:

```
Is there a matching log entry in the AKS pod logs for this request?
  YES → Error originated in the service code
  NO  → Error originated in APIM or the network layer
```

APIM blocks requests BEFORE they reach the backend. If there is no matching log entry in the service's pod, the error is APIM-generated.

---

## APIM Diagnostic Logs

Enable APIM diagnostic logging to see the full request/response lifecycle:

1. **Azure Portal** → API Management → APIs → select API → Settings → Diagnostics
2. **Log Analytics query (KQL):**

```kql
ApiManagementGatewayLogs
| where TimeGenerated > ago(1h)
| where ResponseCode >= 400
| project TimeGenerated, OperationName, ResponseCode, ErrorCode, BackendResponseCode, LastErrorMessage
| order by TimeGenerated desc
```

---

## See Also

- [service-api-spec.md](../runbooks/service-api-spec.md) — per-service APIM configuration documentation template
- [apim-policy-summary.md](apim-policy-summary.md) — template for documenting your APIM policy configuration
- Corvin generic runbook: `knowledge/runbooks/apim-5xx.md`
