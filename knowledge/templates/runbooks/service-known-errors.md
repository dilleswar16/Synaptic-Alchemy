---
template: service-known-errors
version: "1"
description: Known exception types and error taxonomy for a Java Spring Boot microservice
---

# <SERVICE_NAME> — Known Errors & Exception Taxonomy

## Application Exception Handler

This service uses a `@ControllerAdvice` `GlobalExceptionHandler` class that maps Java exceptions to HTTP responses. Understanding this mapping is critical for distinguishing application bugs from infrastructure failures.

| Exception Class | HTTP Status | Meaning | Investigation Path |
|----------------|------------|---------|-------------------|
| `<com.company.service.SomeNotFoundException>` | `404` | `<resource not found>` | Check if data exists; not an infrastructure issue |
| `<com.company.service.ValidationException>` | `400` | `<input validation failed>` | Client-side issue; check request payload |
| `<com.company.service.ExternalServiceException>` | `502` | `<upstream dependency failed>` | Check dependency health |
| `<org.springframework.dao.DataAccessException>` | `500` | `<database error>` | Check DB connectivity and error logs |
| `<Exception (catch-all)>` | `500` | `<unexpected error>` | Check service logs for stack trace |

*If this service does not use a GlobalExceptionHandler (uses inline try/catch instead), document the inline handling patterns here instead.*

---

## Infrastructure-Level Errors

These errors come from the infrastructure layer, not application code. They indicate dependencies failing, not bugs.

| Error Pattern (in logs) | Source | Meaning | Action |
|------------------------|--------|---------|--------|
| `<com.azure.cosmos.CosmosException: 429>` | Cosmos DB | Throttled — too many requests | Check RU/s consumption; scale up or optimize queries |
| `<java.net.ConnectException: Connection refused>` | Downstream service | Target service not running | Check pod status for downstream service |
| `<io.netty.channel.ConnectTimeoutException>` | Network / downstream | Timeout reaching dependency | Check network policy and downstream latency |
| `<org.springframework.vault.VaultException>` | Key Vault | Cannot retrieve secrets | Check Managed Identity permission on Key Vault |
| `<Add your patterns here>` | | | |

---

## APIM-Level Errors

If this service is fronted by Azure APIM, these errors originate at the gateway — not in the service code.

See [apim-error-reference.md](../apim/apim-error-reference.md) for the complete Azure APIM error code reference.

Key errors for this service's APIM config:
- `IP_NOT_ALLOWED` (403) — source IP not in allowlist configured for this API
- `QUOTA_EXCEEDED` (429) — client has exceeded the rate limit for this API
- `Unauthorized` (401) — JWT token missing, expired, or invalid for this API's audience

---

## Distinguishing Application vs. Infrastructure Failures

| Observation | Likely Category | Next Step |
|-------------|----------------|-----------|
| `5xx from service + DB exception in logs` | Infrastructure | Check database connectivity |
| `5xx from service + NullPointerException in logs` | Application bug | Examine stack trace |
| `5xx from APIM (no service logs)` | Infrastructure / APIM | Check APIM diagnostics |
| `4xx consistently for one client` | Client error | Check client request format |
| `4xx spike across all clients` | Infrastructure or deployment | Check recent deployments |

---

## Error Rate Thresholds

| Metric | Warning | Critical |
|--------|---------|---------|
| HTTP 5xx rate | `<N%>` over `<5m>` | `<N%>` over `<5m>` |
| HTTP 4xx rate | `<N%>` | `<N%>` (if 4xx spike indicates upstream change) |
| Exception rate in logs | `<N errors/min>` | `<N errors/min>` |
