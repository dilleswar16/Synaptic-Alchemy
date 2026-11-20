"""Demo knowledge: Copilot-style code-context documents and runbooks for the seeded applications (fictional systems)."""

from __future__ import annotations

# (application_code, service_name, document_title, file_name, markdown)
DEMO_DOCUMENTS: list[tuple[str, str, str, str, str]] = [
    (
        "CLMJP",
        "claims-api",
        "claims-api code context",
        "keigan-knowledge-claims-api.md",
        """# claims-api

## Purpose
Core REST API of Claims Processing (JP). It accepts claim submissions from the customer portal and agent desktop, validates them, stores them in SQL and orchestrates assessment and payout.
Callers: claims-apim (all external traffic), claims-intake-func (batch intake). Dependants: claims-document-renderer, claims-workflow.

## Runtime and hosting
- Java 17, Spring Boot 3.2, built with Maven (`pom.xml`).
- AKS cluster `azjpeaaks21530pr01`, namespace `claims`, Deployment `claims-api`, 4 replicas (HPA 4-10 on CPU 70%).
- Requests 500m CPU / 1Gi memory, limits 1 CPU / 2Gi. Readiness probe `/actuator/health/readiness`, liveness `/actuator/health/liveness`.

## Entry points and APIs
| Method | Path | Handler | Notes |
|---|---|---|---|
| POST | /v1/claims | ClaimsController.submitClaim | Idempotency-Key header required |
| GET | /v1/claims/{claimId} | ClaimsController.getClaim | |
| POST | /v1/claims/{claimId}/documents | DocumentController.requestRender | calls claims-document-renderer |
| GET | /v1/claims/{claimId}/status | ClaimsController.getStatus | polled by the portal every 5 s |

## Sequence diagrams
```mermaid
sequenceDiagram
  participant P as Portal
  participant G as claims-apim
  participant A as claims-api
  participant S as claims-sql
  P->>G: POST /v1/claims
  G->>A: forward (mTLS)
  A->>S: INSERT claim (HikariCP connection)
  A-->>G: 201 Created
```

## Class / module overview
- `jp.metlife.claims.web` controllers and exception mapping (`GlobalExceptionHandler`).
- `jp.metlife.claims.service.ClaimService` validation, assessment routing, transaction boundary.
- `jp.metlife.claims.repository` Spring Data JPA repositories over SQL.
- `jp.metlife.claims.client.RendererClient` WebClient to claims-document-renderer.

## Data stores
- Azure SQL database `claims-sql` (schema `clm`). HikariCP: `maximumPoolSize=40`, `connectionTimeout=30000 ms`, `maxLifetime=1800000 ms` (`application-prod.yml`).
- Flyway migrations in `src/main/resources/db/migration`.

## Outbound dependencies
| Dependency | Protocol | Timeout | Retry |
|---|---|---|---|
| claims-sql | JDBC | 30 s connection, 60 s query | none (fail fast) |
| claims-document-renderer | HTTPS | 10 s | 2 retries, 500 ms backoff |
| Azure Service Bus topic `claims-events` | AMQP | 15 s | SDK default |

## Configuration and feature flags
- `claims.assessment.autoRoute.enabled` (default true) routes low-value claims automatically.
- `spring.datasource.hikari.maximum-pool-size` set in the Helm values `values-prod.yaml`.
- Secrets come from Key Vault `kv-clmjp-prd` through the CSI driver.

## Deployment route
Azure DevOps pipeline `azure-pipelines.yml`: build, test, image to `acrclmjp.azurecr.io`, deploy to `uat` then `prod` namespaces with Helm release `claims-api`. Rollback: `helm rollback claims-api <revision>`.

## Logging and telemetry
- JSON logs with `traceId`, `claimId`, `customerRef` (masked) and `logger`. Application Insights role name `claims-api`.
- Query exceptions: `AppExceptions | where AppRoleName == "claims-api"`; slow dependencies: `AppDependencies | where Target contains "claims-sql"`.

## Known failure modes
- Connection pool exhaustion: HikariCP pending threads climb, requests wait 30 s then fail with `SQLTransientConnectionException: Connection is not available`. Confirm with SQL `sessions_percent` above 90 and rising p95 latency. Mitigate by restarting the slowest pods and raising the pool temporarily.
- Renderer unavailable: `RendererClient` retries twice and returns 502 to the caller; claim submission itself is unaffected.

## Operational commands
- `kubectl -n claims get pods -l app=claims-api`
- `kubectl -n claims logs deploy/claims-api --since=15m | grep SQLTransientConnectionException`
- `kubectl -n claims rollout restart deploy/claims-api` (risk: brief capacity drop)

## Owners
Team JP-Claims-DevOps. Support group JP-Claims-L2-Support. Repository: Azure DevOps `CLMJP/claims-api`.
""",
    ),
    (
        "CLMJP",
        "claims-document-renderer",
        "claims-document-renderer code context",
        "keigan-knowledge-claims-document-renderer.md",
        """# claims-document-renderer

## Purpose
Generates claim decision letters and settlement PDFs (Japanese and English templates) on request from claims-api.

## Runtime and hosting
- .NET 8 worker with a headless Chromium renderer, AKS namespace `claims-docs`, Deployment `claims-document-renderer`, 3 replicas.
- Memory request 1Gi, limit 2Gi. Each render holds a Chromium process of roughly 350-600 MB.

## Entry points and APIs
| Method | Path | Handler | Notes |
|---|---|---|---|
| POST | /render | RenderController.Render | async, returns 202 and a job id |
| GET | /render/{jobId} | RenderController.Get | |

## Data stores
- Blob container `letters` on `stclmjpprd01` for finished PDFs. No SQL access.

## Outbound dependencies
| Dependency | Protocol | Timeout | Retry |
|---|---|---|---|
| Blob storage | HTTPS | 30 s | SDK default |
| Font service `fonts.internal` | HTTPS | 5 s | none |

## Logging and telemetry
Logs carry `jobId`, `claimId`, `templateName`, `renderMilliseconds`. Application Insights role name `claims-document-renderer`. Kubernetes events show `OOMKilled` for the container.

## Known failure modes
- Memory leak in the Chromium page pool when more than 5 pages are open: working set grows about 4% per hour until the pod is OOMKilled (exit code 137). Restarts are visible in `KubePodInventory` and as `OOMKilled` events. Mitigate by restarting the deployment and lowering `RENDER_MAX_PAGES` to 3.

## Operational commands
- `kubectl -n claims-docs get pods`, `kubectl -n claims-docs top pods`
- `kubectl -n claims-docs set env deploy/claims-document-renderer RENDER_MAX_PAGES=3`

## Owners
Team JP-Claims-DevOps.
""",
    ),
    (
        "CHAD",
        "azaustaekub14470pr0101",
        "Channel APIs cluster code context",
        "keigan-knowledge-channel-apis.md",
        """# Channel APIs (AKS cluster azaustaekub14470pr0101)

## Purpose
Hosts the channel-facing microservices of Channel APIs for Digital (AU): customer profile, quote, policy summary and notification dispatch. All traffic arrives through chad-apim.

## Runtime and hosting
- Node.js 20 services (NestJS) on AKS namespace `channel-apis`, 6 deployments, 3 replicas each.
- Ingress through the internal NGINX controller. Outbound calls to partners use mutual TLS with client certificates mounted from Key Vault `kv-chad-prd`.

## Entry points and APIs
| Method | Path | Handler | Notes |
|---|---|---|---|
| GET | /customers/{id}/profile | ProfileController | cached 60 s in Redis |
| POST | /quotes | QuoteController | calls the pricing partner |
| GET | /policies/{id}/summary | PolicyController | |

## Outbound dependencies
| Dependency | Protocol | Timeout | Retry |
|---|---|---|---|
| Pricing partner API | HTTPS mTLS | 8 s | 1 retry |
| chad-notifications-func | HTTPS | 5 s | 3 retries |
| Redis `redis-chad-prd` | TCP | 200 ms | none |

## Configuration and feature flags
- Client certificate `chad-partner-client` mounted at `/certs`; the application reloads it only on restart.
- Feature flag `quote.fallbackPricing` (default off).

## Logging and telemetry
Elastic index pattern `logs-chad-*`, service field `service.name`, fields `trace.id`, `http.response.status_code`, `tls.error`.

## Known failure modes
- Partner client certificate expiry: every call to the pricing partner fails with `UNABLE_TO_VERIFY_LEAF_SIGNATURE` or `certificate has expired`; the quote endpoint returns 502. Rotate the certificate in Key Vault and restart the `quote-service` deployment.
- APIM throttling (429) when a campaign spikes traffic beyond the product rate limit.

## Operational commands
- `kubectl -n channel-apis get pods`, `kubectl -n channel-apis rollout restart deploy/quote-service`
- `az keyvault certificate show --vault-name kv-chad-prd --name chad-partner-client --query attributes.expires`

## Owners
Team AU-Digital-Channels. Support group AU-Digital-Channels-Support.
""",
    ),
    (
        "PAYAU",
        "payment-api",
        "payment-api code context",
        "keigan-knowledge-payment-api.md",
        """# payment-api

## Purpose
Takes premium payments and pays out claims for Payments Platform (AU). It calls the partner bank to authorise and settle every payment.

## Runtime and hosting
- Kotlin, Spring Boot 3, AKS namespace `payments`, 4 replicas. Entry through payments-apim.

## Entry points and APIs
| Method | Path | Handler | Notes |
|---|---|---|---|
| POST | /v1/payments | PaymentController.create | idempotent on `paymentReference` |
| GET | /v1/payments/{id} | PaymentController.get | |

## Outbound dependencies
| Dependency | Protocol | Timeout | Retry |
|---|---|---|---|
| Partner bank gateway | HTTPS | 12 s | 2 retries |
| payment-confirmation-func | Service Bus | 15 s | dead-letter after 5 |

## Logging and telemetry
Application Insights role name `payment-api`. Custom event `PartnerBankCall` with `durationMilliseconds` and `partnerStatus`.

## Known failure modes
- Partner bank latency: calls exceed the 12 s timeout, payments stay `PENDING`, retries amplify load. Confirm with `PartnerBankCall` p95 above 10 s. Pause automatic retries via the feature flag `payments.retry.enabled=false` and notify the partner bank contact.

## Owners
Team AU-Payments-Platform. Support group AU-Payments-Support.
""",
    ),
]

# (application_code, title, trigger symptoms, steps markdown, service names)
DEMO_RUNBOOKS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "CLMJP",
        "SQL connection pool exhaustion on claims-api",
        "claims-api 5xx rate rising, p95 latency above 3 s, SQLTransientConnectionException connection is not available, SQL sessions percent above 90, HikariCP pending threads",
        """1. Confirm: in Application Insights check `AppExceptions` for `SQLTransientConnectionException` and SQL `sessions_percent`.
2. Identify long-running queries: `SELECT TOP 10 * FROM sys.dm_exec_requests ORDER BY total_elapsed_time DESC`.
3. Mitigate: `kubectl -n claims rollout restart deploy/claims-api` one pod at a time.
4. If a recent deployment is the cause, `helm rollback claims-api <previous revision>`.
5. Verify: 5xx rate below 1% and SQL sessions below 60% for 15 minutes.
6. Escalate to the DBA team if blocking sessions persist.""",
        ["claims-api", "claims-sql"],
    ),
    (
        "CLMJP",
        "claims-document-renderer OOMKilled restarts",
        "claims-document-renderer pod restarts, OOMKilled, exit code 137, memory working set above 90 percent, letters not generated",
        """1. Confirm `OOMKilled` in `kubectl -n claims-docs describe pod <pod>`.
2. Restart the deployment: `kubectl -n claims-docs rollout restart deploy/claims-document-renderer`.
3. Reduce pressure: `kubectl -n claims-docs set env deploy/claims-document-renderer RENDER_MAX_PAGES=3`.
4. Verify memory growth is flat for 30 minutes. Raise a defect for the page pool leak.""",
        ["claims-document-renderer"],
    ),
    (
        "CLMJP",
        "API gateway throttling (429) on claims-apim",
        "APIM 429 responses, Too Many Requests, rate limit exceeded, spike in portal traffic",
        """1. Check the `Requests` metric split by response code on claims-apim.
2. Identify the caller from the `ApiManagementGatewayLogs` table.
3. Raise the product rate limit policy temporarily (change request required for prod) or ask the caller to back off.
4. Notify business owners if customers are affected.""",
        ["claims-apim"],
    ),
    (
        "CHAD",
        "Partner mTLS client certificate rotation",
        "quote endpoint 502, UNABLE_TO_VERIFY_LEAF_SIGNATURE, certificate has expired, tls.error in Elastic, channel API availability dropping",
        """1. Check expiry: `az keyvault certificate show --vault-name kv-chad-prd --name chad-partner-client --query attributes.expires`.
2. Import the renewed certificate into Key Vault (certificate team provides the PFX).
3. Restart: `kubectl -n channel-apis rollout restart deploy/quote-service`.
4. Verify a test quote returns 200 and `tls.error` disappears from Elastic.""",
        ["azaustaekub14470pr0101", "chad-apim"],
    ),
    (
        "CHAD",
        "APIM throttling during campaigns",
        "chad-apim 429, rate limit, traffic spike, marketing campaign, error budget burning",
        """1. Confirm the 429 share on chad-apim and the calling subscription key.
2. Agree a temporary limit increase with the API owner.
3. Scale the `channel-apis` deployments if backend latency is also rising.""",
        ["chad-apim"],
    ),
    (
        "PAYAU",
        "Partner bank timeouts",
        "payment-api latency, payments stuck PENDING, partner bank timeout, PartnerBankCall duration above 10 seconds, retries amplifying load",
        """1. Check `PartnerBankCall` p95 and `partnerStatus` in Application Insights.
2. Set `payments.retry.enabled=false` to stop retry amplification.
3. Contact the partner bank operations desk (number in the support contacts page) and share the failing request ids.
4. After recovery, re-enable retries and replay stuck payments with the reconciliation job.""",
        ["payment-api", "payments-apim"],
    ),
    (
        "PADMF",
        "PBIL0400 abend S0C7 restart",
        "PBIL0400 abend, S0C7 data exception, premium billing batch failed, IEF450I",
        """1. Read the abend in SDSF: job PBIL0400 step name and failing program.
2. S0C7 means invalid packed data. Identify the bad record from the dump with the application support analyst.
3. Fix or skip the record, then restart from the failed step using the restart JCL (`RESTART=STEP0400`).
4. Verify downstream job PBIL0500 starts and the billing window is met.""",
        ["premium-billing-batch"],
    ),
    (
        "BENSA",
        "SaaS vendor outage communications",
        "benefits portal unavailable, synthetic probe failing, vendor status page degraded, BenefitsCloud incident",
        """1. Confirm the outage on the vendor status page and with the synthetic probe.
2. Open a priority ticket with the vendor support contact and note the ticket number.
3. Notify HR operations and employee communications with the approved holding statement.
4. Post an update every 30 minutes until the vendor confirms recovery, then verify the probe is green for 15 minutes.""",
        ["benefits-portal"],
    ),
]

DEMO_RECORD_LINKS: dict[str, list[tuple[str, str]]] = {
    "CLMJP": [("eai", "EAI-21530"), ("cmdb", "CI0021530")],
    "CHAD": [("eai", "EAI-14470"), ("cmdb", "CI0014470")],
    "PAYAU": [("eai", "EAI-18820")],
    "PADMF": [("eai", "EAI-10440"), ("cmdb", "CI0010440")],
    "BENSA": [("eai", "EAI-30215")],
}
