# 05 — API contract

Base path `/api`. JSON in **camelCase** (Pydantic alias generator); Python stays snake_case. OpenAPI at `/api/docs` (disabled in production unless `ENABLE_API_DOCS=true`).
Each vertical-slice owner keeps this file updated for their endpoints (short form is fine).

## 1. Conventions

| Topic | Rule |
|---|---|
| Auth | `Authorization: Bearer <token>` (Entra access token or local token). Public endpoints are listed explicitly. |
| IDs | UUID strings. Path params named after the entity: `/applications/{applicationId}`. |
| Lists | `GET` returns `{ "items": [...], "totalCount": n, "page": 1, "pageSize": 50 }` when paginated (`?page=&pageSize=`, max 200). Small bounded lists return arrays. |
| Filtering | Query params with descriptive names: `?applicationIds=a,b&priorities=P1,P2&statuses=investigating`. |
| Time | ISO 8601 UTC strings (`2026-11-19T04:12:00Z`). Time ranges: `?from=&to=` or `?lookback=PT17H`. |
| Errors | RFC 9457 problem+json: `{ "type", "title", "status", "detail", "errorCode", "correlationId", "fieldErrors": [{ "field", "message" }] }`. |
| Async work | Endpoints that start jobs return `202 { "jobId", "status": "queued" }`; the resource exposes its own status for polling. |
| Concurrency | Mutations return the updated resource. `updatedAt` echoed; optimistic conflicts return 409. |
| Correlation | `X-Correlation-Id` accepted and returned. |

## 2. Public

| Method | Path | Description |
|---|---|---|
| GET | `/public/client-configuration` | `{ authMode, entra: { tenantId, spaClientId, apiScope, authority }, environmentName, supportedLocales, defaultLocale, featureFlags, productVersion, allowedLinkHosts }` (`allowedLinkHosts`: hosts that links in AI-written text may point to; an exact host or `*.suffix`) |
| GET | `/public/health` | liveness `{ status: "ok" }` |
| GET | `/public/readiness` | database reachable, worker heartbeat age |
| POST | `/alerts/in/{alertSourceId}` | webhook intake (token in `X-Keigan-Token` header or `?token=`; optional `X-Keigan-Signature` HMAC-SHA256 whose key is the webhook secret itself, stored in the secret store; sources created before 2026-11-20 accept the token only until their secret is rotated) → 202 |
| POST | `/teams/messages` | Bot Framework activities (JWT validated) |

## 3. Authentication

| Method | Path | Description |
|---|---|---|
| GET | `/auth/local-users` | local mode only: dummy users (name, upn, role description, groups) |
| POST | `/auth/local-sign-in` | `{ userPrincipalName }` → `{ accessToken, expiresAt, user }` (local mode only) |
| GET | `/auth/me` | `{ userPrincipalName, displayName, email, isKeiganAdmin, applicationRoles: [{ applicationId, applicationCode, applicationName, role: "admin"|"reader" }], preferredLocale, preferredTheme }` |
| PATCH | `/auth/me/preferences` | `{ preferredLocale?, preferredTheme? }` |

## 4. Applications and onboarding

| Method | Path | Description |
|---|---|---|
| GET | `/applications` | readable applications with summary (counts, compliance, open incidents, readiness) |
| POST | `/applications` | create (Keigan admin) or request (`lifecycleStatus: requested`) |
| GET/PATCH/DELETE | `/applications/{id}` | detail / update / delete (admin; delete only if not live) |
| GET | `/applications/{id}/readiness` | `{ required: Requirement[], goodToKnow: Requirement[], canGoLive, steps: [{ stepKey, status }] }` |
| POST | `/applications/{id}/go-live` | requires `canGoLive` |
| POST | `/applications/{id}/pause` · `/resume` | |
| GET/PATCH | `/applications/{id}/access` | AD group names / object IDs, members (Entra mode) |
| GET | `/platform/identity` | Keigan identity for role grants (tenant, client id, object id, display name, multi-tenant client id) |
| GET/POST | `/applications/{id}/components` | list / add component (type-specific body) |
| GET/PATCH/DELETE | `/applications/{id}/components/{componentId}` | |
| POST | `/applications/{id}/components/{componentId}/verify` | 202; component shows `accessVerificationStatus` |
| POST | `/applications/{id}/components/{componentId}/discover` | 202 |
| GET | `/applications/{id}/components/{componentId}/role-commands` | `{ cli, powershell, terraform, portalSteps }` with real IDs |
| GET | `/applications/{id}/components/{componentId}/resources` | discovered resources (filter `classification`) |
| GET/POST | `/applications/{id}/services` | list / add manual service |
| PATCH/DELETE | `/applications/{id}/services/{serviceId}` | |
| PATCH | `/applications/{id}/services/bulk` | `{ serviceIds, changes }` |
| GET/PUT | `/applications/{id}/services/{serviceId}/log-sources` | |
| POST | `/applications/{id}/services/{serviceId}/log-sources/{logSourceId}/test` | read test |
| GET | `/applications/{id}/services/{serviceId}/diagnostic-setting-command` | |
| GET/PUT | `/applications/{id}/service-dependencies` | |
| GET/POST | `/applications/{id}/log-tool-connections` | secrets accepted on write only (`credentialValue`), never returned |
| PATCH/DELETE | `/applications/{id}/log-tool-connections/{connectionId}` | |
| POST | `/applications/{id}/log-tool-connections/{connectionId}/test` | |
| GET | `/integrations/field-schemas` | JSON field schemas per integration kind |
| GET/PUT | `/applications/{id}/integrations/{integrationKind}` | CMDB, EI portal, knowledge API |
| GET/POST/DELETE | `/applications/{id}/record-links` | EAI / CMDB codes |

## 5. Knowledge

| Method | Path | Description |
|---|---|---|
| GET | `/applications/{id}/knowledge/capture-prompt?serviceId=` | `{ promptMarkdown, lineCount, version }` |
| GET | `/applications/{id}/knowledge/documents` | |
| POST | `/applications/{id}/knowledge/documents` | multipart: `file`, `serviceId?`, `documentCategory`, `documentTitle?` → 202 digest |
| GET/DELETE | `/applications/{id}/knowledge/documents/{documentId}` | detail includes digest |
| GET | `/applications/{id}/knowledge/documents/{documentId}/content` | download (auth) |
| POST | `/applications/{id}/topology/build` | 202 |
| GET | `/applications/{id}/topology` | current version + versions list |
| POST | `/applications/{id}/topology/{topologyId}/reviews` | `{ targetElementKey?, reviewVerdict, reviewCommentText }` |
| GET/POST | `/applications/{id}/runbooks` | |
| GET/PATCH/DELETE | `/applications/{id}/runbooks/{runbookId}` | |

## 6. Incidents and investigations

| Method | Path | Description |
|---|---|---|
| GET | `/incidents` | incident room: filters `applicationIds, priorities, statuses, sources, from, to, search, onlyMine` (comma-separated lists, paginated). Items carry `keiganPriority`, `servicenowPriority` (P-label), `keiganConfidence`, `latestInvestigationId` |
| GET | `/incidents/{incidentId}` | detail with latest investigation summary |
| GET/PUT | `/applications/{id}/servicenow-groups` | assignment groups |
| GET | `/servicenow/groups/search?query=` | typeahead when connected |
| POST | `/investigations` | manual: `{ applicationId, serviceIds, description, windowStart?, windowEnd? }` → 202 `{ jobId }` (`jobId` is the investigation id) |
| GET | `/investigations` | list (filters) |
| GET | `/investigations/{investigationId}` | full: incident, triage, RCA, hypotheses, evidence, blast radius, matched runbooks, alert group |
| GET | `/investigations/{investigationId}/progress` | `{ status, currentStageName, progressPercent, stageMessages[] }` (polled every 2 s while running) |
| POST | `/investigations/{investigationId}/rerun` | 202 `{ jobId }` where `jobId` is the NEW investigation id (the previous run and its feedback are kept) |
| GET | `/investigations/{investigationId}/evidence/{evidenceCode}` | one evidence item (e.g. `E3`) |
| POST | `/investigations/{investigationId}/feedback` | `{ verdict, comment }` |
| GET | `/investigations/{investigationId}/timeline` | |
| GET | `/investigations/{investigationId}/communications` | drafts and sent |
| POST | `/investigations/{investigationId}/communications/generate` | `{ communicationType, languageCodes }` → 202 |
| PATCH | `/communications/{communicationId}` | edit body / subject |
| POST | `/communications/{communicationId}/approve` · `/send` | send → `{ communication, deliveriesQueued, message }`; when delivery is not enabled yet the communication stays `approved` and `deliveriesQueued` is 0 |
| POST | `/incidents/{incidentId}/resolve` | `{ resolutionNote?, generatePostmortem: true }` |
| GET | `/incidents/{incidentId}/postmortem` | postmortem or JSON `null` when none exists; `reportStatus`: generating, draft, final, failed |
| POST | `/incidents/{incidentId}/postmortem/generate` | 202 |
| PATCH | `/postmortems/{postmortemId}` | edit |
| POST | `/postmortems/{postmortemId}/finalize` · `/send` | send → `{ postmortem, deliveriesQueued, message }` (same not-yet-enabled behaviour) |
| POST | `/alert-groups/{alertGroupId}/create-servicenow-incident` | route owned by S3's alert controller; S2 provides `IncidentService.create_servicenow_incident_from_alert_group` |
| GET | `/incidents/{incidentId}/teams-chat` | chat info + mirrored messages (simulated mode shows full chat) |
| POST | `/incidents/{incidentId}/teams-chat/messages` | simulated mode only: post as the current user |

## 7. Chat

| Method | Path | Description |
|---|---|---|
| GET | `/chat/conversations?scope=keigan_ai_chat` | user's conversations |
| POST | `/chat/conversations` | `{ conversationScope, applicationIds?, investigationId? }` |
| GET/PATCH/DELETE | `/chat/conversations/{conversationId}` | messages included in GET |
| POST | `/chat/conversations/{conversationId}/messages` | `{ messageText, clarificationResponse? }` → assistant message `{ messageText, messagePayload: { answerKind: "text"|"number"|"chart"|"table"|"clarification", chartSpecification?, tableRows?, queryDetails?: { serviceName, sourceKind, queryLanguage, queryText, timeRange, rowCount }, citations?: [{ kind, title, reference }], clarificationOptions?: [{ label, value }] } }` |
| GET | `/chat/suggested-prompts?applicationId=` | |

Chart specification (shared with frontend `ChartMessage`):

```json
{ "chartType": "line|area|bar|stacked_bar|pie|table",
  "title": "Failed requests per hour", "xField": "timestamp", "xFieldKind": "time|category",
  "series": [{ "field": "failedCount", "label": "Failed", "colorToken": "danger" }],
  "unit": "count", "rows": [{ "timestamp": "2026-11-19T01:00:00Z", "failedCount": 3 }] }
```

## 8. Alerts

| Method | Path | Description |
|---|---|---|
| GET/POST | `/applications/{id}/alert-sources` | create returns `{ alertSource, webhookUrl, webhookSecret }` (secret shown once) |
| PATCH/DELETE | `/applications/{id}/alert-sources/{sourceId}` | |
| POST | `/applications/{id}/alert-sources/{sourceId}/rotate-secret` | |
| POST | `/applications/{id}/alert-sources/{sourceId}/test` | send a simulated alert through the pipeline |
| GET | `/applications/{id}/alert-sources/{sourceId}/recent-events` | live listener (poll) |
| GET | `/applications/{id}/alert-sources/{sourceId}/setup-instructions` | Azure / Elastic / generic instructions with real values |
| POST | `/applications/{id}/alert-sources/mapping-preview` | S3 addition: parse a sample payload with a candidate mapping, suggestions and matched service |
| POST | `/alert-groups/{alertGroupId}/create-servicenow-incident` | S3 addition: 501 when ServiceNow creation is unavailable |
| GET | `/applications/{id}/azure-alert-rules` | discovered rules and whether they target Keigan; `unreadableResourceGroups` lists the resource groups whose rules could not be read (their rules are missing from the list) |
| GET/PUT | `/applications/{id}/noise-policy` | |
| POST | `/applications/{id}/noise-policy/preview` | `{ policySettings, days: 7 }` → funnel |
| GET/POST/PATCH/DELETE | `/applications/{id}/maintenance-windows[/{windowId}]` | |
| GET/POST/PATCH/DELETE | `/applications/{id}/mute-rules[/{muteRuleId}]` | |
| GET | `/alerts/funnel?applicationIds=&from=&to=` | |
| GET | `/alert-groups` | filters |
| GET | `/alert-groups/{alertGroupId}` | members + decisions |
| POST | `/alert-groups/{alertGroupId}/feedback` | |
| GET | `/applications/{id}/noise-report` | latest weekly report |

## 9. SLOs and intelligence

| Method | Path | Description |
|---|---|---|
| POST | `/applications/{id}/slo-proposals/measure` | 202 |
| GET | `/applications/{id}/slo-proposals` | grouped by service: proposed SLIs with measured baseline, proposed target, budget, disabled reasons; supporting signals |
| POST | `/applications/{id}/slo-proposals/accept` | `{ acceptedProposals: [{ catalogEntryKey, serviceId, targetPercentage, rollingWindowDays, latencyThresholdMilliseconds? }] }` |
| GET/POST | `/applications/{id}/slis` | custom SLI create |
| PATCH/DELETE | `/slis/{sliId}` | |
| GET/POST | `/applications/{id}/slos` · PATCH/DELETE `/slos/{sloId}` | |
| GET | `/slo-dashboard?applicationIds=` | per SLO: compliance, budget remaining %, minutes left, burn rates 1h/6h, status, sparkline |
| GET | `/slos/{sloId}/series?from=&to=&resolution=` | SLI series, target, budget burn-down (`resolution` in minutes) |
| GET | `/slo-ecosystem-heatmap?days=30` | |
| GET | `/predictive-signals` | filters |
| PATCH | `/predictive-signals/{signalId}` | status change |
| POST | `/predictive-signals/{signalId}/investigate` | creates manual investigation |
| GET | `/intelligence-reports?applicationId=` · GET `/intelligence-reports/{reportId}` | |
| POST | `/applications/{id}/intelligence-reports/generate` | 202 (send optional) |
| GET | `/applications/{id}/health-score-trend?days=30` | |

## 10. Notifications

| Method | Path | Description |
|---|---|---|
| GET/POST | `/applications/{id}/stakeholders` | |
| PATCH/DELETE | `/applications/{id}/stakeholders/{stakeholderId}` | |
| POST | `/applications/{id}/stakeholders/{stakeholderId}/test` | |
| GET | `/directory/users/search?query=` | Entra people search (Graph) / local users in local mode |
| GET | `/outbox` | Keigan admins (filters) |
| GET | `/outbox/{deliveryId}` | rendered HTML |

## 11. Dashboard and administration

| Method | Path | Description |
|---|---|---|
| GET | `/dashboard/home?applicationIds=` | greeting data, KPI tiles, application health cards, live incidents, intelligence feed, maintenance windows, recent postmortems |
| GET | `/administration/settings` | effective settings (secrets redacted) + connection statuses |
| POST | `/administration/connection-tests/{integration}` | `servicenow`, `graph`, `llm`, `azure`, `email` |
| GET | `/administration/usage?from=&to=&groupBy=day|application|feature` | |
| GET | `/administration/audit-events` | filters |
| GET | `/administration/jobs` | queue stats, dead letters; POST `/administration/jobs/{jobId}/retry` |
| POST | `/administration/simulation/scenarios/{scenarioKey}` | local/test only: trigger a simulated incident scenario |

### S1 implementation notes (2026-11-19)
Path parameters are named `{application_id}`, `{component_id}`, `{service_id}`, `{log_source_id}`, `{connection_id}`, `{integration_kind}`, `{record_link_id}`, `{document_id}`, `{topology_id}`, `{runbook_id}`.
Additions beyond the table: `GET /applications/{id}/integrations` (all kinds), `GET /applications/{id}/servicenow-groups`, `PUT /applications/{id}/servicenow-groups` (`{groupNames}`), `GET /servicenow/groups/search?query=`, `DELETE /applications/{id}/record-links/{recordLinkId}`.
`PUT /applications/{id}/services/{serviceId}/log-sources` takes a bare JSON array of log sources (replace semantics). `PUT /applications/{id}/service-dependencies` takes `{dependencies:[{upstreamServiceId,downstreamServiceId,dependencyKind}]}`.
Readiness `required[]`/`goodToKnow[]` items: `{requirementKey, stepKey, isDone, detail, count}`; `steps[]`: `{stepKey, status, summary}`; plus `canGoLive`, `nextStepKey`. Step keys: components, services, log_tools, knowledge, topology, runbooks, incidents, slo, notifications, access, review.
`GET /applications` returns an array of summaries (counts, `componentTypes`, `sloCompliancePercentage`, `requiredDoneCount/requiredTotalCount` for applications not yet live), not a paged result.

### S5 implementation notes (2026-11-20)
Chat: `POST /chat/conversations` with `investigation` scope returns the user's existing conversation for that investigation. Assistant `messagePayload` also carries `numberValue`, `queryDetails.timeRange` as `{start,end}`, `queryDetails.isSimulated` and `conversationContext` (used for follow-ups). `PATCH` accepts `conversationTitle` and `applicationIds`.
Administration: `GET /administration/settings` returns `{environment, productVersion, groups[], integrations[], keiganIdentity, simulationControlsAvailable}`; `GET /administration/usage?from=&to=&groupBy=`; `GET /administration/audit-events?actor=&action=&applicationId=&from=&to=&page=&pageSize=`; `GET /administration/jobs` -> `{countsByStatus, countsByType, deadLetters, recentJobs}`; `GET /administration/simulation/scenarios`; `POST /administration/simulation/scenarios/{scenarioKey}` `{applicationId}`.
Home: `GET /dashboard/home?applicationIds=` returns `{greetingName, statusSentence, kpis, applicationCards, liveIncidents, intelligenceFeed, maintenanceWindows, recentPostmortems, generatedAt}`.
