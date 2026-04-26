---
keywords: [unauthorized, 401, 403, forbidden, token, jwt, azure-ad, workload-identity, DefaultAzureCredential, validate-jwt, Bearer, ocp-apim-subscription-key, IP_NOT_ALLOWED, IPV6_NOT_SUPPORTED, QUOTA_EXCEEDED, KeyVault, kyv14470aepr0101, chad-sa, opentelemetry-javaagent, OTEL, elastic-agent-otlp, Micrometer, OTLP, ca56a4a5-e300-406a-98ff-7e36a0baac5b, 94148a30-8d1b-4c56-8e50-84d50ebbdac1, traceparent, X-CorrelationId, X-CHAD-Request-ID, apim_request_id, correlation_id, fund_code]
---
# CHAD Security & Observability Context

## Authentication

- **Method:** Bearer JWT validated entirely at APIM. Spring Boot services have **no Spring Security filter** — they do not validate tokens themselves. If a request reaches the pod, APIM has already accepted it.
- **Token issuer (Azure AD):** tenant `ca56a4a5-e300-406a-98ff-7e36a0baac5b`
- **Token audience (prod/qa):** `api://bc5fa7ea-7bce-4add-be17-da17fe9b37e1`
- **Token audience (dev):** `api://f169b588-a2ed-45ca-b9af-305d519e0142`
- **Token validation config in APIM:**
  ```xml
  <validate-jwt header-name="Authorization"
                failed-validation-httpcode="401"
                failed-validation-error-message="Unauthorized"
                require-expiration-time="true"
                require-scheme="Bearer"
                require-signed-tokens="true"
                clock-skew="60">
      <openid-config url="https://login.microsoftonline.com/ca56a4a5-e300-406a-98ff-7e36a0baac5b/.well-known/openid-configuration" />
  ```
- **Failure Mode:** If the token is expired, has the wrong audience, or is missing, APIM returns `HTTP 401` with body `{"message":"Unauthorized"}` and the request **never reaches the Spring Boot pod**. The pod will show **zero log entries** for that request.

---

## IP Allowlist (APIM — defense in depth)

- All inbound requests are checked against an IPv4 allowlist embedded in the APIM policy (MetLife Australia ranges `10.173.x.x`, `10.174.x.x`; MetLife India; CareSuper; APEX; REIS; other internal ranges).
- IPv6 is explicitly blocked with `403 {"code":"IPV6_NOT_SUPPORTED"}`.
- Non-allowlisted IPv4 returns `403 {"code":"IP_NOT_ALLOWED"}`.
- These checks happen **before JWT validation** and **before reaching any pod**.

---

## Azure Managed Identity (Workload Identity)

- **Used:** Yes — all three pods use Azure Workload Identity (federated credential)
- **Mechanism:** `spring.cloud.azure.credential.workload-identity-enabled=true`; `DefaultAzureCredentialBuilder` fallback present in `AzureTokenCredentialConfig` (fundapis); Kubernetes `ServiceAccount: chad-sa` with annotation `azure.workload.identity/client-id: 94148a30-8d1b-4c56-8e50-84d50ebbdac1`; pod label `azure.workload.identity/use: "true"`
- **Managed Identity Client ID (prod):** `94148a30-8d1b-4c56-8e50-84d50ebbdac1`
- **Azure Tenant ID:** `ca56a4a5-e300-406a-98ff-7e36a0baac5b`
- **Accesses via Managed Identity:**
  - **Azure Key Vault** (`kyv14470aepr0101` in prod) — required RBAC role: `Key Vault Secrets User`
  - **Azure Cosmos DB** (`cdb14470aepr0101` in prod) — Cosmos key is fetched from Key Vault (not via Managed Identity directly to Cosmos; uses key-based auth from Key Vault secret)
- **Failure Mode (HTTP 403 from Azure):** If the Managed Identity lacks the required RBAC role on Key Vault, the pod will fail to resolve Key Vault secrets at startup and crash-loop. Look for `ForbiddenException` or `CredentialUnavailableException` in startup logs from `com.azure.identity` or `com.azure.security.keyvault`.
- **Failure Mode (token federation broken):** If the OIDC issuer URL or federated credential binding between `chad-sa` and the Managed Identity is misconfigured, Workload Identity token exchange fails. The pod will log `CredentialUnavailableException` or `ClientAuthenticationException` from `com.azure.identity`.

---

## Application Insights

- **Instrumentation key / connection string:** NOT active in prod. The `applicationinsights-runtime-attach` dependency is present in `fundapis/pom.xml` but is commented out. No `APPLICATIONINSIGHTS_CONNECTION_STRING` or `azure.application-insights` config found in any active profile.
- **What is traced:** OpenTelemetry Java Agent (`opentelemetry-javaagent.jar` v2.8.0) is used instead of Application Insights SDK. Traces, metrics, and logs are exported via OTLP to `http://elastic-agent-otlp.elastic-agent.svc.cluster.local:8200` (in-cluster Elastic APM agent).

---

## Observability Stack

### OpenTelemetry Java Agent (all three pods in prod)

- **Agent version:** `opentelemetry-javaagent` `2.8.0`
- **OTEL exporter endpoint:** `http://elastic-agent-otlp.elastic-agent.svc.cluster.local:8200` (HTTP/protobuf)
- **What is auto-instrumented:** Spring MVC HTTP requests (spans), Cosmos SDK calls (spans), Key Vault calls (spans), JVM metrics (CPU, heap, GC, threads), Logback log records (with `trace_id` and `span_id` correlation)
- **MDC attributes captured to Elastic labels:** `apim_request_id`, `correlation_id`, `fund_code` (all MDC keys via `OTEL_INSTRUMENTATION_LOGBACK_APPENDER_EXPERIMENTAL_CAPTURE_MDC_ATTRIBUTES: "*"`)

### Micrometer OTLP Registry

- **Metrics push URL:** `http://elastic-agent-otlp.elastic-agent.svc.cluster.local:8200/v1/metrics`
- **Metrics include:** JVM, system, process, HTTP server request histograms with SLO buckets (50ms, 100ms, 200ms, 300ms, 500ms, 1s, 2s, 5s), business KPI metrics (custom `partner.api.request.duration.seconds`, `partner.external.service.response.duration.seconds`)
- **Service tags in Elastic:**
  - `fundapis` → `service.name=ChAD-Fund-APIs-PROD`, `service.namespace=ChAD`, `deployment.environment=EAI14470-Prod`
  - `partnerapis` → `service.name=ChAD-Partner-APIs-PROD`
  - `fundsso` → `service.name=ChAD-Fund-SSO-PROD`
- **Known issue (fixed):** Without excluding `OtlpMetricsExportAutoConfiguration` in `fundapis`, Spring Boot 3 creates a second OTLP registry alongside the custom `@Primary` `OtlpMeterRegistry` bean, doubling every metric in Elastic. The exclusion `spring.autoconfigure.exclude=org.springframework.boot.actuate.autoconfigure.metrics.export.otlp.OtlpMetricsExportAutoConfiguration` is applied in `fundapis` `application.properties`.

### Trace Correlation (APIM ↔ Elastic)

- APIM injects a `traceparent` W3C header (derived from APIM `context.RequestId`) that the OTEL Java agent reads automatically. The `trace_id` in Elastic APM for a pod span therefore matches the APIM diagnostic log `RequestId` (strip hyphens to convert UUID to 32-hex trace_id).
- `X-CHAD-Request-ID` header carries the same `clientRequestId` value — Envoy/Istio does NOT replace this header (unlike `x-request-id` which Envoy regenerates if not a valid UUID4).
- To correlate a request end-to-end: search Elastic for the `X-CHAD-Request-ID` value; this matches the APIM-generated request ID logged in APIM diagnostic traces.

---

## SRE Notes

- **An HTTP `401` from CHAD** almost always means the Azure AD Bearer token has expired, was obtained for the wrong audience, or was not sent at all. The fault is at APIM — the Spring Boot pod was never reached. Do NOT restart the pod. Direct the caller to re-authenticate against Azure AD tenant `ca56a4a5-e300-406a-98ff-7e36a0baac5b`.
- **An HTTP `403` with `code: IP_NOT_ALLOWED`** means the caller's IP is not in the APIM allowlist. Do NOT restart the pod. The partner fund's IP must be added to the APIM policy.
- **An HTTP `403` from Azure (not APIM)** — e.g. `ForbiddenException` during pod startup or Key Vault access — means the Managed Identity (`chad-sa`, client ID `94148a30-8d1b-4c56-8e50-84d50ebbdac1`) lacks the required RBAC role on the target Azure resource (`Key Vault Secrets User` on `kyv14470aepr0101`).
- **Pod crash-loop at startup** with Key Vault errors: Workload Identity federation is broken or the RBAC role is missing. Check the `azure-identity-token` volume mount in the pod (`/var/run/secrets/azure/tokens/azure-identity-token`) and verify the `chad-sa` service account annotations.
- **Elastic APM goes dark (no new traces/metrics)** but pods are serving requests: the `elastic-agent-otlp` service in namespace `elastic-agent` is down. Application continues to function — this is an observability gap, not an application outage.
- **`fundsso` returning `500`** consistently during business hours most often indicates PingFederate (`https://auth.asia.metlife.com`) is degraded, not a CHAD pod fault. Check PingFederate health before considering a pod restart.
