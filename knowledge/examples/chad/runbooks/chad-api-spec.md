---
keywords: [fundapis, partnerapis, fundsso, b2bservice, chadservice, scheme_reference, fundCode, member_uuid, amended_insurance, health-check, postback, xml, profile, FundController, PartnerController, PostbackController, MemberProfileController, FundIntegrationController, ProxyAuditLogController, CacheManagementController, PartnerFundController, 200, 201, 400, 401, 403, 404, 413, 500]
---
# CHAD API Specification & APIM Policies

## Service: fundapis (`artifactId: fundapis`)
Base path prefix (all B2B routes): `/b2bservice/v1/schemes/`  
Base path prefix (internal CHAD fetch route): `/chadservice/v1/schemes/`  
Base path prefix (proxy audit): `/b2bservice/v1/proxy/`

### Endpoints

- `POST /b2bservice/v1/schemes/{fundCode}/member/xml`: Accept raw XML member payload, validate against fund-specific XSD schema, unmarshal and persist to Cosmos DB `FundRequest` container. Returns `MemberResponse` with assigned `memberUUID`.
  - **Auth:** Bearer JWT validated by APIM `validate-jwt` (Azure AD tenant `ca56a4a5-e300-406a-98ff-7e36a0baac5b`, audience `api://bc5fa7ea-7bce-4add-be17-da17fe9b37e1`) + IP allowlist enforced at APIM inbound
  - **Rate Limit:** 100 calls/60s per client IP; 500 calls/60s per subscription key; quota 1000 calls/hour per client IP
  - **Request size limit:** 5 MB (enforced by APIM; returns `413 PAYLOAD_TOO_LARGE`)
  - **Failure Mode:** `400` (`XMLValidationException`) — malformed XML or schema mismatch; return error body to partner fund IT team, not a pod issue. `400` (`XSDFileNameException`) — XSD not deployed for this `fundCode`; deploy missing schema file and redeploy `fundapis`. `400` (`BusinessValidationException`) — business rule violation; return `List<BusinessValidationErrorResponse>` to caller. `500` — check `kubectl logs -n chad deploy/chad-fundapis --since=1h | grep "Unexpected error"` for stack trace; see `chad-known-errors.md`.

- `POST /b2bservice/v1/schemes/{fundCode}/member`: Accept JSON member payload and persist to Cosmos DB.
  - **Auth:** Same JWT + IP allowlist as above
  - **Rate Limit:** Same as above
  - **Failure Mode:** `400` (`BusinessValidationException`) — return error to caller. `500` — check Cosmos account `cdb14470aepr0101` health in Azure Portal; if 429 throttling, scale RU/s on `FundRequest` container.

- `GET /b2bservice/v1/schemes/{fundCode}/member/{id}`: Retrieve a persisted member record by its Cosmos DB document ID.
  - **Auth:** JWT + IP allowlist
  - **Failure Mode:** `404` (`MemberNotFoundException`) — caller passed an invalid UUID; return 404 to caller, not a pod issue. `500` — Cosmos error; check Azure Portal → `cdb14470aepr0101` → Metrics.

- `GET /b2bservice/v1/schemes/{schemeRef}/member/{clientRefNumber}/xml`: Retrieve persisted member data formatted as XML (produces `application/xml`). Requires `X-Internal-Debug-Key` header matching `xml.access.key` property.
  - **Auth:** JWT + IP allowlist + internal debug header
  - **Failure Mode:** `403` — `X-Internal-Debug-Key` missing or wrong; caller must provide the key from Key Vault secret `xml.access.key`. `404` (`MemberNotFoundException`) — no XML payload for this `clientRefNumber` in Cosmos `FundRequest` container.

- `POST /b2bservice/v1/schemes/{fundCode}/members/profile`: Save a dynamic JSON member profile (no fixed schema; supports REIS-specific payload validation). Returns `{"id": "<cosmosDocumentId>"}` with HTTP 201.
  - **Auth:** JWT + IP allowlist
  - **Failure Mode:** `400` (`BusinessValidationException`) — REIS business rule failed; return error to caller. `500` — Cosmos write failed; check Azure Portal → `cdb14470aepr0101` → `MemberProfile` container metrics.

- `GET /b2bservice/v1/schemes/{fundCode}/member/profile/{uuid}`: Retrieve member profile by Cosmos document UUID. Used internally by `fundsso`.
  - **Auth:** JWT + IP allowlist
  - **Failure Mode:** `404` (`MemberNotFoundException`) — profile not in `MemberProfile` container; check if the profile was previously written by a `POST /members/profile` call for this UUID.

- `GET /b2bservice/v1/schemes/{fundCode}/member/profile/search/{integratedPartnerSystemId}`: Search member profile by external partner system ID.
  - **Auth:** JWT + IP allowlist
  - **Failure Mode:** `404` (`MemberNotFoundException`) — no profile for this `integratedPartnerSystemId`; return 404 to caller, not a pod issue.

- `GET /b2bservice/v1/schemes/{fundCode}/member/profile/{memberUUID}/details`: Get member details portion of profile.
  - **Auth:** JWT + IP allowlist
  - **Failure Mode:** `404` — profile or details sub-object not in Cosmos `MemberProfile`; return to caller.

- `GET /b2bservice/v1/schemes/{fundCode}/member/profile/{memberUUID}/insurance`: Get member insurance portion of profile.
  - **Auth:** JWT + IP allowlist
  - **Failure Mode:** `404` — insurance sub-object not in Cosmos `MemberProfile`; return to caller.

- `POST /b2bservice/v1/proxy/{fundCode}/{operationType}`: Log a B2B proxy audit event.
  - **Auth:** JWT + IP allowlist
  - **Failure Mode:** `500` — Cosmos write to `ProxyAuditLog` container failed; check `kubectl logs -n chad deploy/chad-fundapis --since=1h | grep "Failed to save proxy audit log"` and verify Cosmos account health.

- `GET /chadservice/v1/schemes/{fundCode}/member/{memberUID}`: Internal endpoint — fetches member data for a given fund and memberUID. Called by `partnerapis` via `RestTemplate`.
  - **Auth:** Internal cluster traffic (ClusterIP service, no APIM policy)
  - **Failure Mode:** `404` — member not in Cosmos; `partnerapis` caller will throw `RuntimeException` → HTTP 500 to AXE. Check `fundapis` logs for `MemberNotFoundException`.

---

## Service: partnerapis (`artifactId: partnerapis`)
Base path prefix (AXE/MIP-facing routes): `/v1/schemes`  
Base path prefix (AXE member profile routes): `profile/v1/schemes`  
Base path prefix (internal cache management): `/internal/cache`

### Endpoints

- `GET /v1/schemes/{scheme_reference}/members/{member_uuid}/details`: Retrieve member personal details for a given scheme and member UUID. Requires `X-CorrelationId` header.
  - **Auth:** Bearer JWT (same Azure AD config) + IP allowlist at APIM
  - **Rate Limit:** 100 calls/60s per IP; 500/60s per subscription; 1000/hour per IP
  - **Failure Mode:** `404` (`MEMBER_UUID_NOT_FOUND`) — UUID not in Cosmos `MemberProfile`; return to AXE caller, not a pod issue. `400` (`MISSING_HEADER`) — `X-CorrelationId` absent; return to caller. `500` (`GENERAL_ERROR`) — check `kubectl logs -n chad deploy/chad-partnerapis --since=1h | grep "Error retrieving member data"` and verify Cosmos account health.

- `GET /v1/schemes/{scheme_reference}/members/{member_uuid}/insurance`: Retrieve member insurance data. Requires `X-CorrelationId`.
  - **Auth:** JWT + IP allowlist
  - **Rate Limit:** Same as above
  - **Failure Mode:** `404` (`MEMBER_UUID_NOT_FOUND`) — UUID not in Cosmos. `400` (`MISSING_HEADER`) — missing `X-CorrelationId`. `500` — check `kubectl logs -n chad deploy/chad-partnerapis --since=1h | grep "Error retrieving member insurance data"`.

- `POST /v1/schemes/{scheme_reference}/search/members`: Search for members within a scheme. Requires `X-CorrelationId`.
  - **Auth:** JWT + IP allowlist
  - **Rate Limit:** Same as above
  - **Failure Mode:** `404` (`MEMBER_UUID_NOT_FOUND`) — no member matches search criteria. `400` (`MISSING_HEADER`) — `X-CorrelationId` absent. `500` — check `kubectl logs -n chad deploy/chad-partnerapis --since=1h | grep "Error searching member data"`.

- `POST /v1/schemes/{scheme_reference}/members/{member_uuid}/amended_insurance`: Save postback (amended insurance notification) to Cosmos DB `Postback` container. Requires `X-CorrelationId`.
  - **Auth:** JWT + IP allowlist
  - **Rate Limit:** Same as above
  - **Failure Mode:** `500` — Cosmos write to `Postback` container failed; check `kubectl logs -n chad deploy/chad-partnerapis --since=1h | grep "Error saving postback"` and verify Cosmos account health. `400` (`MISSING_HEADER`) — missing `X-CorrelationId`.

- `GET /v1/schemes/{scheme_reference}/health`: Scheme-level health check.
  - **Auth:** None (health endpoint)
  - **Failure Mode:** Always returns 200. `overallStatus: DOWN` means `fundapis` or `fundsso` actuator health returned non-2xx; check those services directly.

- `GET /v1/schemes/axe/health-check/all`: Full dependent-service health check (calls `fundapis` and `fundsso` actuator health endpoints).
  - **Auth:** None
  - **Failure Mode:** 200 always. `overallStatus: DOWN` does NOT block member data calls — investigate the downstream service separately.

- `GET profile/v1/schemes/{scheme_reference}/members/{member_uuid}/details`: Same as above but under `profile/` path prefix (AXE profile API variant).
  - **Auth:** JWT + IP allowlist
  - **Failure Mode:** Same as `/v1/schemes` equivalent; check `kubectl logs -n chad deploy/chad-partnerapis --since=1h | grep "Error retrieving member profile details"`.

- `GET profile/v1/schemes/{scheme_reference}/members/{member_uuid}/insurance`: Same insurance lookup under `profile/` prefix.
  - **Auth:** JWT + IP allowlist
  - **Failure Mode:** Same as `/v1/schemes` equivalent; check `kubectl logs -n chad deploy/chad-partnerapis --since=1h | grep "Error retrieving member insurance information"`.

- `POST profile/v1/schemes/{scheme_reference}/search/members`: Member search under `profile/` prefix.
  - **Auth:** JWT + IP allowlist
  - **Failure Mode:** Same as `/v1/schemes` equivalent; check `kubectl logs -n chad deploy/chad-partnerapis --since=1h | grep "Error searching member profiles"`.

- `GET profile/v1/schemes/{scheme_reference}/health`: Health under `profile/` prefix.
  - **Auth:** None
  - **Failure Mode:** 200 always

- `POST /internal/cache/evict/partner-configs`: Evict all partner config cache entries (cache name: `StaticProps`). Called by deployment pipelines after partner config updates.
  - **Auth:** Internal cluster only (no APIM policy)
  - **Failure Mode:** `500` — cache eviction threw an exception; check `kubectl logs -n chad deploy/chad-partnerapis --since=5m | grep "Error during cache eviction"`. If this fails after a partner config deploy, the stale cache will auto-clear at the next hourly cron tick (`0 0 * * * *`).

- `POST /internal/cache/evict/partner-configs/{fundCode}`: Evict cache for a single fund code.
  - **Auth:** Internal cluster only
  - **Failure Mode:** `500` — check `kubectl logs -n chad deploy/chad-partnerapis --since=5m | grep "Error during cache eviction for fund"`.

- `GET /internal/cache/health`: Cache management health check.
  - **Auth:** Internal cluster only
  - **Failure Mode:** `500` — cache manager bean is broken; redeploy `chad-partnerapis`.

---

## Service: fundsso (`artifactId: fundSSO`)
No base `@RequestMapping`; all paths are absolute.

### Endpoints

- `POST /v1/schemes/{scheme_reference}/members?resumePath=&id=`: Fetch member info from `fundapis` by ID and scheme reference, drop attributes to PingFederate Reference ID Adaptor (`RefIDChadAU`), then return HTTP `302 FOUND` redirect to `pingURL + resumePath + ?REF=<referenceValue>`.
  - **Auth:** JWT + IP allowlist at APIM
  - **Rate Limit:** APIM-enforced
  - **Failure Mode:** `400` — blank/null `id`, `resumePath`, or `scheme_reference`; return to caller, not a pod issue. `404` — member not found in `fundapis`; confirm the member was previously submitted via `POST /b2bservice/v1/schemes/{fundCode}/member`. `500` — PingFederate returned no `referenceValue` (check `https://auth.asia.metlife.com` availability) OR `fundapis` is unreachable (check `kubectl get pods -n chad -l app=chad-fundapis`). `302` on success — this is the normal path.

- `POST /v1/schemes/members?schemeReference=&resumePath=&id=`: Same SSO flow but `schemeReference` passed as query param instead of path variable.
  - **Auth:** JWT + IP allowlist
  - **Failure Mode:** Same as above.

- `GET /v1/schemes/secrets`: Diagnostic endpoint that returns the value of KeyVault secret `chad-test-1`. Confirms Key Vault connectivity.
  - **Auth:** JWT + IP allowlist
  - **Failure Mode:** If this endpoint fails at startup (pod crash-loop), Key Vault `kyv14470aepr0101` is unreachable; verify Workload Identity on pod and `Key Vault Secrets User` RBAC for `chad-sa`.

- `GET /v1/health-check/all`: Health check across all dependent services.
  - **Auth:** None
  - **Failure Mode:** 200 always; `DOWN` in response body indicates a dependent service issue — investigate that service separately.

- `GET /v1/health`: Simple health.
  - **Auth:** None
  - **Failure Mode:** 200 always

---

## APIM Policy Summary (both fundapis and partnerapis)

| Policy | Value |
| :--- | :--- |
| JWT validation header | `Authorization: Bearer <token>` |
| Azure AD tenant | `ca56a4a5-e300-406a-98ff-7e36a0baac5b` |
| Audience (prod/qa) | `api://bc5fa7ea-7bce-4add-be17-da17fe9b37e1` |
| Audience (dev) | `api://f169b588-a2ed-45ca-b9af-305d519e0142` |
| JWT issuers | `https://sts.windows.net/ca56a4a5-e300-406a-98ff-7e36a0baac5b/` and `https://login.microsoftonline.com/ca56a4a5-e300-406a-98ff-7e36a0baac5b/v2.0` |
| Rate limit per IP | 100 calls per 60 seconds |
| Rate limit per subscription | 500 calls per 60 seconds |
| Hourly quota per IP | 1000 calls per hour |
| Max payload size | 5 MB |
| IPv6 | Blocked; returns `403 {"code":"IPV6_NOT_SUPPORTED"}` |
| IP not in allowlist | Returns `403 {"code":"IP_NOT_ALLOWED"}` |
| Request ID header | `X-Request-ID` and `X-CHAD-Request-ID` (APIM injects if absent) |
| Trace propagation | `traceparent` W3C header injected by APIM; OTEL Java agent in pods reads it for trace correlation in Elastic |
| Swagger UI | Disabled in prod (`springdoc.api-docs.enabled=false`) |
