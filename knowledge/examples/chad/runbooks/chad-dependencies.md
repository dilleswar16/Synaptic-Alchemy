---
keywords: [cosmos, cdb14470aedv0101, cdb14470aepr0101, users, FundRequest, MemberProfile, Postback, PartnerConfigs, PartnerConfigsHistory, ProxyAuditLog, CosmosRepository, CosmosException, KeyVault, kyv14470aedv0101, kyv14470aepr0101, PingFederate, auth.asia.metlife.com, fundapis, fundsso, partnerapis, RestTemplate, elastic-agent-otlp, spring-cloud-azure-starter-data-cosmos, spring-cloud-azure-starter-keyvault, workload-identity, DefaultAzureCredential]
---
# CHAD Upstream & Downstream Dependencies

## Azure Cosmos DB

- **Database name:** `users` (configured in all three services via `azure.cosmos.database=users`)
- **Dev endpoint:** `https://cdb14470aedv0101.documents.azure.com:443/`
- **Prod endpoint:** `https://cdb14470aepr0101.documents.azure.com:443/`
- **Connection mode:** Gateway (default for `spring-cloud-azure-starter-data-cosmos` without explicit `DirectMode`; no `CosmosClientBuilder` with `.directMode()` found in code)
- **Credentials:** `azure-cosmos-key` and `azure-cosmos-secondary-key` — both resolved at runtime from Azure Key Vault via Spring Cloud Azure Key Vault property source. Never stored in application config files.

### Cosmos Containers

| Container Name | Used By | Entity Class | Repository Interface | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `FundRequest` | fundapis | `Request` | `RequestRepository` | Raw fund member data submitted by partner funds via XML or JSON |
| `MemberProfile` | fundapis, partnerapis | `MemberProfile` | `MemberProfileRepository` (both services) | Dynamic JSON member profile for SSO lookup and AXE API responses |
| `ProxyAuditLog` | fundapis | `ProxyAuditLog` | `ProxyAuditLogRepository` | Audit trail for B2B proxy call events |
| `Postback` | partnerapis | `Postback` | `PostbackRepository` | Amended insurance notifications received from AXE/MIP |
| `PartnerConfigs` | partnerapis | `PartnerConfigProperties` | `PolicyConfigRepository` | Per-fund partner configuration (scheme reference mappings, config); cached in-memory under cache name `StaticProps` |
| `PartnerConfigsHistory` | partnerapis | `PartnerConfigHistory` | `PartnerConfigHistoryRepository` | Audit trail of partner config changes |

- **Failure Mode:**
  - `CosmosException` with `statusCode=404` → handled by `GlobalExceptionHandler` → returns HTTP `404` with `ProblemDetails` body `"Resource Not Found"`
  - `CosmosException` with any other status code → returns HTTP `500` with `"Database Error"` body
  - `RequestRateTooLargeException` (Cosmos 429) is a subclass of `CosmosException` and will surface as HTTP `500` from the application unless the Cosmos SDK retries exhaust
- **SRE Action:** Check `com.azure.cosmos` log level (set to `WARN` in prod, `INFO` in dev). A spike in `CosmosException statusCode=429` means Cosmos RU capacity is exhausted — scale up RU or investigate query patterns. For `statusCode=503` or timeout, check Cosmos account health in Azure Portal. Do NOT restart pods; the fault is external to the pod.
- **Cache note (partnerapis):** `PartnerConfigs` container data is cached with Spring Cache (`@Cacheable`, cache `StaticProps`). Stale config after a partner config deploy requires calling `POST /internal/cache/evict/partner-configs` or the pod will serve stale data until the next scheduled refresh (`policy.config.cron=0 0 * * * *` — top of every hour).

---

## Azure Key Vault

- **Dev vault:** `https://kyv14470aedv0101.vault.azure.net/` (name: `kyv14470aedv0101`)
- **Prod vault:** `https://kyv14470aepr0101.vault.azure.net/` (name: `kyv14470aepr0101`)
- **Secrets consumed:**
  - `azure-cosmos-key` — Cosmos DB primary key (fundapis, partnerapis)
  - `azure-cosmos-secondary-key` — Cosmos DB secondary key (fundapis, partnerapis)
  - `ping-referanceid-uname` — PingFederate Reference ID Adaptor username (fundsso)
  - `ping-referanceid-pwd` — PingFederate Reference ID Adaptor password (fundsso)
  - `chad-test-1` — KV connectivity test secret (fundsso, fundapis)
  - `xml.access.key` (prod: `Xk9mP2qR7vLn4wJd` in prod properties, but overridden by KV in runtime) — debug XML access key (fundapis)
- **Auth to KV:** Azure Workload Identity (`spring.cloud.azure.credential.workload-identity-enabled=true`); `DefaultAzureCredentialBuilder` fallback present in `AzureTokenCredentialConfig` (fundapis)
- **Failure Mode:** If Key Vault is unreachable at pod startup, Spring Cloud Azure will fail to resolve placeholder properties and the pod will crash-loop. Look for `com.azure.identity` or `com.azure.security.keyvault` errors in startup logs.
- **SRE Action:** If pods are crash-looping with Key Vault errors, verify: (1) AKS Workload Identity is correctly federated (`azure.workload.identity/use: "true"` label is on pod), (2) the service account `chad-sa` has `Key Vault Secrets User` RBAC on the vault, (3) the vault endpoint is reachable from the AKS subnet.

---

## External Services / APIs

### PingFederate (Ping CIAM) — used by fundsso only

- **Dev URL:** `https://dev.auth.asia.metlife.com`
- **Prod URL:** `https://auth.asia.metlife.com`
- **Endpoint called:** `POST <ping.url><ping.referanceid-url>` = `<pingURL>/ext/ref/dropoff`
- **Adaptor name:** `RefIDChadAU`
- **Call method:** `RestTemplate.postForEntity(...)` from `SSOUtils.dropAttributesAndGetReference()`
- **Credentials:** `ping-referanceid-uname` and `ping-referanceid-pwd` resolved from Key Vault
- **Failure Mode:** If PingFederate returns no `referenceValue` or throws, `fundsso` returns HTTP `500` to the APIM caller with body `"Reference value not returned from PingFederate"`. The member is never redirected to MIP.
- **SRE Action:** This is an external MetLife CIAM system. Do NOT restart the `fundsso` pod if PingFederate is unreachable — the fault is external. Check PingFederate availability at `https://auth.asia.metlife.com`. If it is up but returning errors, check credentials (`ping-referanceid-uname`/`ping-referanceid-pwd`) in Key Vault for expiry/rotation. Escalate to the MetLife IAM/CIAM team.

### fundapis (called internally by partnerapis and fundsso)

- **Internal cluster URL (partnerapis):** `http://chad-fundapis:8080/chadservice/v1/schemes/{fundCode}/member/{memberUID}` (property: `microservices.member-service.url`)
- **Internal cluster URL (partnerapis MemberProfileService):** `http://chad-fundapis:8080/b2bservice/v1/schemes/` (property: `microservices.fundapis.url`)
- **Internal cluster URL (fundsso):** `http://chad-fundapis:8080/b2bservice/v1/schemes/{fundCode}/member/` and `http://chad-fundapis:8080/b2bservice/v1/schemes/`
- **Call method:** `RestTemplate` (with `FundApisCallInterceptor` in partnerapis; plain `RestTemplate` in fundsso)
- **Failure Mode:** If `fundapis` is down, `partnerapis` `APIUtils.getForEntity()` throws `RuntimeException`; `fundsso` `MemberProfileService` throws `RuntimeException("Failed to save member profile: ...")` or `RuntimeException("Failed to get member profile: ...")`. Both surface as HTTP `500` to the caller.
- **SRE Action:** Check `chad-fundapis` pod health at `/actuator/health`. If the pod is down, restart it. If `fundapis` is up but returning errors, check Cosmos connectivity from `fundapis` pod.

### fundsso (health check URL referenced by partnerapis)

- **Health check URL:** `http://chad-fundsso:8080/actuator/health` (property: `health.check.fundsso.url`)
- **Failure Mode:** Used only for the `GET /v1/schemes/axe/health-check/all` aggregate health endpoint in both `partnerapis` and `fundsso`. A failure here degrades the health check response but does not break member API calls.

### fundapis actuator (health check by partnerapis)

- **Health check URL:** `http://chad-fundapis:8080/actuator/health`
- **Failure Mode:** Same as above — health check only.

---

## Observability / Telemetry Export

- **OTLP endpoint (all services, prod):** `http://elastic-agent-otlp.elastic-agent.svc.cluster.local:8200`
- **Metrics path:** `/v1/metrics` (Micrometer OTLP registry)
- **Traces/Logs:** OTEL Java agent (`opentelemetry-javaagent.jar`) ships traces and Logback log records to the same OTLP endpoint via `http/protobuf`
- **Failure Mode:** If `elastic-agent-otlp` is unreachable, metrics/traces are dropped silently. The application continues to serve requests but Elastic APM dashboards will go dark. This is NOT a cause to restart application pods.
- **SRE Action:** Check `elastic-agent` pod in namespace `elastic-agent`. Verify the DaemonSet/Deployment is healthy. Logs will still appear in pod stdout (Logback console appender is always active).

---

## Message Queues / Brokers

None. CHAD does not use Kafka, RabbitMQ, Azure Service Bus, or any message broker. All inter-service communication is synchronous HTTP via `RestTemplate`.
