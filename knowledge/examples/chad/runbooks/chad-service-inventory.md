---
keywords: [fundapis, partnerapis, fundSSO, FundApiApplication, PartnerApiApplication, FundIntegrationApplication, chad-fundapis, chad-partnerapis, chad-fundsso, b2bservice, chadservice, au.com.metlife.channel, au.com.metlife.fundapi, spring-cloud-azure-starter-data-cosmos, RestTemplate, FundApisCallInterceptor, MemberProfileService, APIUtils, SSOUtils, 8080, EAI14470]
---
# CHAD Service Inventory

## Total Service Count

- **Number of microservices:** 3

All three are standalone Spring Boot applications, each with their own `pom.xml`, `@SpringBootApplication` entry point, Dockerfile, and independent AKS Helm chart.

---

## Service List

| Service Name | Maven artifactId | `@SpringBootApplication` class | Port | AKS Deployment Name | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **fundapis** | `fundapis` | `au.com.metlife.channel.FundApiApplication` | `8080` | `chad-fundapis` | B2B inbound API — accepts XML and JSON member/insurance data from partner fund systems via APIM. Validates against fund-specific XSD, persists to Cosmos DB `FundRequest` and `MemberProfile` containers. Also serves internal endpoints consumed by `partnerapis` and `fundsso`. |
| **partnerapis** | `partnerapis` | `au.com.metlife.channel.PartnerApiApplication` | `8080` | `chad-partnerapis` | Outbound channel API for AXE/MIP (MetLife Insurance Platform). Exposes member detail and insurance data to AXE. Reads from Cosmos via `fundapis` internal endpoint and directly from `MemberProfile` container. Manages partner config cache (`PartnerConfigs` container). Accepts amended insurance postbacks from AXE. |
| **fundSSO** | `fundSSO` | `au.com.metlife.fundapi.FundIntegrationApplication` | `8080` | `chad-fundsso` | SSO broker — receives member ID and scheme reference from a fund system via APIM, fetches member profile from `fundapis`, drops attributes to PingFederate Reference ID Adaptor (`RefIDChadAU`), and returns an HTTP `302` redirect with `?REF=<referenceValue>` for the SAML flow into MIP. |

---

## Inter-Service Dependencies

### partnerapis → fundapis (sync HTTP, internal cluster)

- `partnerapis` calls `chad-fundapis:8080` via `RestTemplate` (with `FundApisCallInterceptor`) for two purposes:
  1. `GET http://chad-fundapis:8080/chadservice/v1/schemes/{fundCode}/member/{memberUID}` — look up a member to return to AXE (`APIUtils.getForEntity()`)
  2. `GET/POST http://chad-fundapis:8080/b2bservice/v1/schemes/{fundCode}/member/profile/...` — read/write `MemberProfile` data (`MemberProfileService` in `partnerapis`)
- **`FundApisCallInterceptor` role:** This `ClientHttpRequestInterceptor` bean intercepts every `RestTemplate` call from `partnerapis` to `fundapis`. It likely handles internal auth token relaying or request logging. If a call to `fundapis` fails with a connection error, the interceptor logs are the first place to check — run `kubectl logs -n chad deploy/chad-partnerapis --since=30m | grep FundApisCallInterceptor`.
- If `chad-fundapis` is down or returns non-2xx, `partnerapis` throws `RuntimeException` which propagates as HTTP `500` to the AXE caller.

### fundsso → fundapis (sync HTTP, internal cluster)

- `fundsso` calls `chad-fundapis:8080` via plain `RestTemplate`:
  1. `POST http://chad-fundapis:8080/b2bservice/v1/schemes/{fundCode}/member/profile` — save member profile during SSO initiation (`MemberProfileService.saveMemberProfile()`)
  2. `GET http://chad-fundapis:8080/b2bservice/v1/schemes/{fundCode}/member/profile/{uuid}` — retrieve profile for PingFederate attribute drop-off
  3. `GET http://chad-fundapis:8080/b2bservice/v1/schemes/{fundCode}/member/{id}` — alternate member lookup path (configured under `microservices.member-service.url`)
- If `chad-fundapis` is down, `fundsso` throws `RuntimeException("Failed to save/get member profile: ...")`, which surfaces as HTTP `500` to the APIM caller. The SSO flow is broken and the member cannot be redirected to MIP.

### fundsso → PingFederate (sync HTTP, external internet)

- `fundsso` calls `https://auth.asia.metlife.com/ext/ref/dropoff` via `RestTemplate` (within `SSOUtils.dropAttributesAndGetReference()`)
- If PingFederate is unreachable or returns no reference value, `fundsso` returns HTTP `500` with body `"Reference value not returned from PingFederate"`. Not a CHAD pod fault.

### partnerapis health-check → fundsso and fundapis (sync HTTP, internal cluster)

- `partnerapis` calls `http://chad-fundsso:8080/actuator/health` and `http://chad-fundapis:8080/actuator/health` only in the `GET /v1/schemes/axe/health-check/all` and `GET /v1/schemes/{scheme_reference}/health` endpoints (`HealthCheckService`). These calls use a `RestTemplateBuilder`-built `RestTemplate` with a configurable `health.check.timeout` (default `2` seconds).
- If either service is unreachable, the aggregate health response returns `overallStatus: DOWN` but the calling endpoint always returns HTTP `200`. This is not a load-bearing call — it does not affect member data flows.

---

## No Shared Database Risk

`fundapis` and `partnerapis` both connect to the same Cosmos DB account (database `users`) and both read/write the `MemberProfile` container. A Cosmos RU limit breach or network partition affecting one service will also affect the other. Monitor both services' Cosmos error rates together.

---

## No Message Bus

All three services communicate exclusively via synchronous HTTP. There is no Kafka, Service Bus, or event queue. This means:
- **Cascading failures propagate immediately** — a `fundapis` outage breaks both `partnerapis` data retrieval and `fundsso` SSO flows simultaneously.
- **No retry queues** — if a Cosmos write fails, the data is lost unless the caller retries at the HTTP level.
