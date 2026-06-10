---
template: service-security-context
version: "1"
description: Security architecture and identity context for an Azure-hosted microservice
---

# <SERVICE_NAME> — Security Context

## Authentication Architecture

| Component | Responsibility |
|-----------|---------------|
| `<APIM / API Gateway>` | Validates JWT tokens. Services trust forwarded identity. |
| `<Service>` | Does NOT validate tokens directly. Trusts the gateway. |
| Token issuer | `<Azure AD / Auth0 / custom OIDC endpoint>` |
| Token audience | `<api://your-app-registration-id>` |

```
Client → APIM (validates JWT) → Service (trusts APIM, reads forwarded headers)
```

*If your services validate tokens themselves rather than delegating to APIM, describe the token validation library and config here.*

---

## Azure Managed Identity (Workload Identity)

This service uses Azure Workload Identity to authenticate to Azure services without hardcoded credentials.

| Property | Value |
|----------|-------|
| Service Account | `<k8s-service-account-name>` in namespace `<namespace>` |
| Federated Identity Credential | `<federated-credential-name>` |
| Managed Identity | `<user-assigned-managed-identity-name>` |
| Identity client ID | `<managed-identity-client-id>` |

**Azure services accessed via this identity:**
- `<Azure Key Vault>` — read secrets
- `<Azure Cosmos DB>` — data plane access
- `<add others>` — `<purpose>`

*If not using Workload Identity, document the alternative credential mechanism here.*

---

## IP Access Control

| Level | Allowed Sources | Notes |
|-------|----------------|-------|
| APIM gateway | `<CIDR ranges or "any">` | APIM rejects requests from unlisted IPs with `IP_NOT_ALLOWED` |
| Kubernetes NetworkPolicy | `<namespace selectors or "any in cluster">` | Restricts pod-to-pod communication |

---

## Observability & Audit

| Signal | Where | Retention |
|--------|-------|----------|
| Access logs | `<APIM / service stdout / Azure Monitor>` | `<N days>` |
| Auth failures (401, 403) | `<APIM diagnostics / Application Insights>` | `<N days>` |
| Secret access audit | `<Azure Key Vault audit logs>` | `<N days>` |

---

## SRE Decision Guide — Security-Related Incidents

| Symptom | Most Likely Cause | Investigation Path |
|---------|------------------|--------------------|
| HTTP 401 from APIM | JWT missing, expired, or wrong audience | Check token expiry and `aud` claim; not a service issue |
| HTTP 403 from APIM + `IP_NOT_ALLOWED` | Source IP not in APIM allowlist | Check APIM policy; IP from new environment or VPN |
| Pod crash-loop on startup | Key Vault unreachable or permission denied | Check Managed Identity assignment; check Key Vault firewall; check federated credential config |
| HTTP 403 from service (not APIM) | Application-level authorization failed | Check service's authorization logic; this is not an APIM issue |
| `<Custom symptom>` | `<cause>` | `<steps>` |

---

## Secrets Inventory

Document which secrets are managed via Key Vault, so Corvin knows to check Key Vault connectivity when secrets-related failures occur.

| Secret Name | Purpose | Service(s) Using It |
|------------|---------|---------------------|
| `<secret-name>` | `<e.g. database connection string>` | `<service-name>` |
| `<secret-name>` | `<e.g. external API key>` | `<service-name>` |
