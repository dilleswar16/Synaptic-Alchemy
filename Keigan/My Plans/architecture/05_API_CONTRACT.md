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
| POST | `/applications` | create (Keigan admin) or request (`lifecycleStatus: requested`). Optional `teamMembers: [{ displayName, emailAddress, stakeholderRole }]` are saved in the same transaction (all or nothing); a duplicate or invalid address is a 422. Invitations are queued only when the application is created, not requested |
| GET/PATCH/DELETE | `/applications/{id}` | detail / update / delete (admin; delete only if not live) |
| GET | `/applications/{id}/readiness` | `{ required: Requirement[], goodToKnow: Requirement[], canGoLive, steps: [{ stepKey, status }] }` |
| POST | `/applications/{id}/go-live` | requires `canGoLive` |
| POST | `/applications/{id}/pause` · `/resume` | |
| GET/PATCH | `/applications/{id}/access` | AD group names / object IDs, members (Entra mode) |
| GET/PUT | `/applications/{id}/operating-notes` | the team's guidance for the AI (`{ text }` in, `{ text, maximumCharacters, updatedAt, updatedBy }` out). Readers read; Keigan admins and the application's admin group write. Text is trimmed; longer than the maximum is a 422 with a `text` field error. See the 2026-11-21 notes |
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
| POST | `/chat/conversations/{conversationId}/messages` | Investigation chats only, since phase 3 step 4: `{ messageText }` → the assistant message `{ messageText, messagePayload: { answerKind: "text", citations? } }`, answered as the Teams bot is. A Keigan AI chat gets `422` (`/answers` answers it). `clarificationResponse` is gone. The old global answers (`answerKind` "number", "chart" or "clarification") stay readable in GET |
| GET | `/chat/suggested-prompts?applicationId=` | |
| POST | `/chat/conversations/{conversationId}/answers` | **Ask Keigan** (spec 23). Header `Accept: text/event-stream` (else `406 not_acceptable`); body `{ messageText (1..4000), clientRequestId (UUID) }`. Answers `200 text/event-stream` with the events of section "Ask Keigan event protocol" below; the answer is a detached task, so it finishes even when the reader goes away. The scope of the answer is the scope of its conversation: an investigation chat is answered with the investigation scope, a Keigan AI chat (`keigan_ai_chat`) with the global scope (the applications the person can read, narrowed to the conversation's applications; since phase 3 step 1; the global page uses it since phase 3 step 3); any other conversation gets `422` |
| GET | `/chat/answer-runs/{answerRunId}` | `AnswerRunView` snapshot of the stored trace: works for a running run and a finished one; the way to recover after a dropped stream (poll every 1 s, 3 s after 20 polls). Owner of the conversation who can still read it (`403` otherwise: also after access to the investigation's application was removed, and, for any run, when the person can no longer read **any** application the answer used (`used_application_ids_json`); the answer, notes, citation titles and every step are then withheld, also the steps on an application they can still read; `404` unknown). A run that went silent for `ASK_KEIGAN_STALE_RUN_SECONDS` with no live task in the answering process is ended here as `failed`/`answer_interrupted` |
| GET | `/chat/answer-runs/{answerRunId}/steps/{runStepId}/output` | `{ runStepId, output, outputCharacterCount, outputIsTruncated, modelViewText, modelViewSha256 }`: the full stored output of one tool call. Owner who can still read the conversation; `403` when the reader can no longer read the step's application or any application its answer used; `404` for a model turn or a step of another run |
| POST | `/chat/answer-runs/{answerRunId}/cancel` | `202 { answerRunId, cancelRequested: true }`: stores and commits `cancelRequestedAt` first (another pod sees it), then sets the stop flag of a run that lives in this pod. Asking again changes nothing. `409 answer_not_running` (with `answerRunId`) when the run already ended, also when it ended between the check and the write. Owner only: a person who lost access to the application may still stop their own run (it reveals nothing and ends work they started) |

Messages stay in `GET /chat/conversations/{conversationId}`: an Ask Keigan answer is a normal assistant message whose `messagePayload` is `{ answerRunId, citations, followUps, isUnverified, isRefusal, stopReason }`, and its question message carries `messagePayload.answerRunId` from the moment the run starts (so a reload during the answer, a stopped answer or a failed one still finds its run; those runs have no assistant message). When the reader can no longer read an application an answer used, `GET /chat/conversations/{conversationId}` returns that assistant message with `messageText` replaced by one sentence in the reader's language ("You no longer have access to an application this answer used.") and `messagePayload` reduced to `{ answerRunId }` (null for an answer of the old router, which has no run), so the screen asks for the run, gets `403` and shows its "no access" caption; the question message is unchanged. An old-router answer is withheld only when its payload names an application (`conversationContext.applicationId`).

Errors before the stream starts are RFC 9457 `problem+json` with these `errorCode`s: `401 authentication_required`, `403 forbidden` (not the owner, or access to the investigation lost), `404 not_found`, `406 not_acceptable`, `409 answer_in_progress` and `409 duplicate_request` (both with the extension member `answerRunId`: the run that is running, or the run that already answers this `clientRequestId`; also when the race is lost to another pod and only the database unique constraint saw it: nothing is stored then, and no 500 is returned), `422 validation_failed` (empty or too long question, malformed `clientRequestId`), `429 rate_limited` (`CHAT_RATE_LIMIT_PER_MINUTE`, the same per-user budget as `/messages`), `429 token_budget_exceeded`, `503 ai_tools_unsupported` (the model cannot use tools; nothing is stored). Their wording comes from the Ask Keigan error catalogue (spec 23, 4.10). After the stream has started, failures are an `answer.failed` event, never an HTTP status.

#### Ask Keigan event protocol (version 1)

Every frame is `id: <sequence>`, `event: <name>`, `data: <json>` and a blank line; `data` is `{ eventVersion, sequence, answerRunId, emittedAt, ...fields }` (camelCase). Sequence numbers start at 1 without gaps. While the run is quiet a comment line `: keep-alive` goes out every `ASK_KEIGAN_HEARTBEAT_SECONDS`. Response headers: `Content-Type: text/event-stream; charset=utf-8`, `Cache-Control: no-store`, `X-Accel-Buffering: no`, `Connection: keep-alive`.

| Event | Fields |
|---|---|
| `answer.started` | `userMessage {messageId, messageText, createdAt}`, `scope`, `offeredTools [{name,label,labelKey}]`, `maximumToolCalls` |
| `answer.text` | `turnNumber`, `text` (one sanitised paragraph) |
| `turn.note` | `turnNumber`, `runStepId`, `sequenceNumber`, `text` (the turn asked for tools: its text is a note in the trace) |
| `tool.started` | `runStepId`, `sequenceNumber`, `parentRunStepId`, `citationCode` (null for a skipped request), `boundArgumentNames`, `tool {name,label,labelKey,source,presentation}`, `arguments`, `target {applicationId, applicationName}` |
| `tool.progress` | `runStepId`, `sequenceNumber`, `stage`, `detail` (`query_logs` only: the generated query) |
| `tool.finished` | `runStepId`, `sequenceNumber`, `status`, `durationMilliseconds`, `summary`, `outputPreview`, `outputCharacterCount`, `outputIsTruncated`, `itemCount`, `isSimulated`, `totalCount`, `isTruncated` (the three trust flags, each `null` when the tool has no such notion, read from the whole output and never from the preview), `records`, `maskedValueCount`, `injectionFlagged`, `outcomeCode`, `outcomeMessage` |
| `answer.completed` | `answer {messageId, markdown, citations, followUps, isUnverified, isRefusal}`, `stopReason`, `toolCallCount`, `inputTokenCount`, `outputTokenCount`, `durationMilliseconds` |
| `answer.failed` | `error {errorCode, title, detail, correlationId, isRetryable}` (`errorCode: "cancelled"` for a stop), `stopReason` (`failed` or `cancelled_by_user`) |

Exactly one of `answer.completed` and `answer.failed` ends a stream that finishes normally. A stream can also end without one (the browser closed it, a proxy cut it, or the reader was too slow and the server dropped the stream so the run is never slowed): the client then reads `GET /chat/answer-runs/{id}` until `status` is not `running`. There is no `Last-Event-ID` replay: the single in-process event channel is read once, and the run may live in another pod, so the stored trace is the recovery path. `AnswerRunView` (`status`, `stopReason`, `scope`, counts, `steps[]` with `tool {boundArgumentNames, label, labelKey, source, presentation, citationCode, arguments, target, summary, outputPreview, ..., isSimulated, totalCount, isTruncated, ..., isRedacted}` (`RunStepView.tool` and `.note` are sent as `null` when absent, never left out; a citation leaves out the target fields it does not have), `answer`, `error`, `lastSequence`) is the same shape the events build up; `lastSequence` is the last event the answering process published for a run it is still running and `0` otherwise. `error` (and the `error` of `answer.failed`) is a `ProblemSummary { errorCode, title, detail, correlationId, isRetryable, parameters }`: `parameters` are the low-sensitivity values the message was written from, stored with the run, so a reload names the same failed step and delay as the live stream. `tool.progress` stages: `query_generated`. A step on an application the reader can no longer read comes back redacted (`isRedacted: true`, no arguments, output or target). `tests/unit/test_ask_keigan_frontend_contract.py` and `tests/integration/services/test_ask_keigan_events_frontend_contract.py` keep these names identical to `frontend/src/api/askKeiganApi.ts`.

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
| GET | `/applications/{id}/azure-alert-rules` | discovered rules and whether they target Keigan; `unreadableResourceGroups` lists each resource group whose rules could not be fully read, with `resourceGroupName`, `subscriptionId` and `reasonCode` (`forbidden`, `not_found`, `throttled` or `failed`; the UI shows the message) |
| GET/PUT | `/applications/{id}/noise-policy` | |
| POST | `/applications/{id}/noise-policy/preview` | `{ policySettings, days: 7 }` → funnel |
| GET/POST/PATCH/DELETE | `/applications/{id}/maintenance-windows[/{windowId}]` | |
| GET/POST/PATCH/DELETE | `/applications/{id}/mute-rules[/{muteRuleId}]` | |
| GET | `/alerts/funnel?applicationIds=&from=&to=` | |
| GET | `/alert-groups` | filters; every group carries `groupingReason` (see the 2026-11-21 notes) |
| GET | `/alert-groups/{alertGroupId}` | members + decisions; carries `groupingReason` like the list |
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
| GET | `/metrics/overview?applicationId=&days=&from=&to=` | reliability metrics for the applications the caller can read (one application when `applicationId` is given). See the 2026-11-21 notes |

## 10. Notifications

| Method | Path | Description |
|---|---|---|
| GET/POST | `/applications/{id}/stakeholders` | The application's team and recipients. POST takes `sendInvitation` (people only). Roles: `lead`, `developer`, `infra`, `devops`, `tester`, `sre`, `manager`, `executive`, `business_owner`, `vendor_contact`. Addresses are checked and stored lower case; one person per address per application (422 with a `fieldErrors` entry for `emailAddress`). Each row carries `teamMemberStatus` (`listed`, `invited`, `active`, `inactive`), `invitedAt`, `lastInvitationSentAt`, `joinedAt`, `invitationIsStale`, `canSendInvitation`, `nextInvitationAllowedAt` |
| PATCH/DELETE | `/applications/{id}/stakeholders/{stakeholderId}` | The only active team lead cannot be removed, switched off or given another role (422) |
| POST | `/applications/{id}/stakeholders/{stakeholderId}/invitation` | Admin only. Sends or resends the invitation email; returns `{ teamMember, deliveryId, message }`. 429 inside the cooldown (`TEAM_INVITATION_RESEND_COOLDOWN_MINUTES`), 422 for lists and channels, for someone who already signed in, or who is switched off. An invitation never grants access: access comes from the AD groups |
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

### Implementation notes (2026-11-21)

**Reliability metrics** (`GET /metrics/overview`, `controllers/metrics_controller.py`; feature doc `24_RELIABILITY_METRICS.md`). Parameters: `applicationId` (optional; must be readable), `days` or `from` and `to`. `days` cannot be combined with `from`/`to`, `to` needs `from`, an end before the start is a 422, and a period longer than `METRICS_MAXIMUM_WINDOW_DAYS` is a 422. With none of them the period is the last 30 days. The response is `{ periodStart, periodEnd, applicationId, minimumRatingSample, maximumWindowDays, summary, applications[], weeklyTrend[], notAvailable[], definitionKeys[], generatedAt }`. `summary` (and each `applications[]` entry, which adds `applicationId`, `applicationName`, `applicationCode`) holds `incidentsOpenedCount`, `incidentsResolvedCount`, `byPriority[]` (`P1` to `P4` and `unassigned`), the four durations `timeToDetect`, `timeToFirstUpdate`, `timeToResolve`, `timeToConclusion`, `investigationCount`, `investigationsByStatus[]`, `ratings` (`ratedCount`, `correctCount`, `partiallyCorrectCount`, `incorrectCount`, `minimumSample`, `shareCorrect`, null below the minimum sample) and `aiUsage` (`investigationCount`, `callCount`, `failedCallCount`, `inputTokens`, `outputTokens`, `latencyMilliseconds`, `cost`). Every duration or token figure is a stat `{ sampleCount, median, p90, mean, excludedCount }` in seconds, tokens or milliseconds; the three number fields are null when `sampleCount` is 0, never zero. `cost` is `{ isConfigured, totalEstimatedCost, perInvestigation, unpricedModels[], unpricedInvestigationCount }`. `weeklyTrend[]` entries start on Monday 00:00 UTC. `notAvailable[]` lists metrics that cannot be computed, each with a reason key (today only `timeToAcknowledge`, reason `no_acknowledgement_timestamp`).

**Operating notes** (`GET` and `PUT /applications/{id}/operating-notes`, `controllers/operating_notes_controller.py`; feature doc `25_APPLICATION_OPERATING_NOTES.md`). `PUT` replaces the text; an empty text clears it; a save that changes nothing writes no audit event. The audit event is `application.operating_notes_update` with `previousLength` and `newLength` (no text).

**`groupingReason` on alert groups** (feature doc `26_ALERT_GROUPING_REASON.md`). `AlertGroupSummaryResponse.groupingReason` (list and detail) was a nullable string; it is now always present as `{ "code": string, "parameters": object }`. The code is one of `same_service`, `dependency`, `same_rule`, `attached_to_incident`, `single_alert`, `not_recorded`. Parameters can hold `serviceName`, `relatedServiceName`, `ruleName`, `incidentName`, `alertCount` (number) and `windowMinutes` (number); which ones depend on the code. The screen writes the sentence from a localised template, so no sentence travels in the API. The reason is derived on read; nothing new is stored. `GET /api/investigations/{id}` returns the same `{ code, parameters }` as `alertGroup.groupingReason` (it was the stored English string until 2026-11-21).
