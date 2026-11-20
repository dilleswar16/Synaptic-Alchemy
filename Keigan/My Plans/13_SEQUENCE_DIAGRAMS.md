# 13 · Sequence diagrams

The main runtime flows of Keigan, drawn from the code (class and method names are the real ones, so you can search for them).
Diagrams are Mermaid: they render on GitHub, Azure DevOps wikis and in VS Code with a Mermaid preview extension.

| # | Flow | Why it matters |
|---|---|---|
| 1 | [Sign-in and access check](#1-sign-in-and-access-check) | How Keigan knows who is a Keigan admin, an application admin or a reader |
| 2 | [Keigan admin registers an application and its groups](#2-keigan-admin-registers-an-application-and-its-access-groups) | How new `<CODE>_admin` / `<CODE>_reader` groups become known before the owners sign in |
| 3 | [Grant access, verify and discover an Azure component](#3-grant-access-verify-and-discover-an-azure-component) | Which IDs the application team sees and what Keigan checks |
| 4 | [ServiceNow incident to root cause and notifications](#4-servicenow-incident-to-root-cause-and-notifications) | The core investigation pipeline, with PII masking and prompt safety |
| 5 | [Alert webhook to noise-reduced alert group](#5-alert-webhook-to-noise-reduced-alert-group) | Denoising and how an early alert group is adopted by a later ticket |
| 6 | [Teams "Keigan, this is finished" to postmortem email](#6-teams-keigan-this-is-finished-to-postmortem-email) | The milestone phrase flow |
| 7 | [Keigan AI chat: question to query to chart](#7-keigan-ai-chat-question-to-query-to-chart) | Natural language to a validated, read-only telemetry query |
| 8 | [Scheduled work: SLOs, burn alerts and the intelligence report](#8-scheduled-work-slos-burn-alerts-and-the-intelligence-report) | Background jobs and what triggers them |

Common to every flow: the API and the worker are the same image; the worker runs jobs from the `background_job` table
(`JobQueue.enqueue` → `JobWorker` → handler in `workers/job_handlers.py`). Keigan **never** changes a customer system: it
reads telemetry and proposes fixes and commands for a person to run.

## 1. Sign-in and access check

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Web as Keigan web (React + MSAL)
    participant Entra as Microsoft Entra ID
    participant API as Keigan API (SecurityMiddleware)
    participant Auth as AuthenticationService
    participant Graph as Microsoft Graph
    participant Authz as AuthorizationService
    participant DB as Azure SQL (keigan schema)

    User->>Web: Open Keigan
    alt AUTH_MODE = entra
        Web->>Entra: MSAL sign-in (SPA app registration)
        Entra-->>Web: Access token for api://keigan/access_as_user
    else AUTH_MODE = local
        Web->>API: POST /auth/local-sign-in (dummy user from local_users.yaml)
        API-->>Web: Locally signed token
    end
    Web->>API: GET /auth/me with Bearer token
    API->>Auth: authenticate_bearer_token(token)
    Auth->>Auth: Validate signature, audience, tenant, expiry
    Auth->>Auth: Group object IDs from the token's groups claim (if the app registration emits it)
    Auth->>Graph: GET /users/{oid}/transitiveMemberOf/microsoft.graph.group (cached 10 minutes)
    Note right of Graph: App-only call with Keigan's managed identity.<br/>Needs Graph application permission GroupMember.Read.All.
    alt Graph answers
        Graph-->>Auth: Group names and object IDs, nested groups included
    else Graph unavailable or permission missing
        Auth->>Auth: Only the token's group object IDs are known,<br/>so matching works only for applications with saved group object IDs
    end
    Auth->>Auth: is_keigan_admin = member of KEIGAN_ADMIN_GROUP_NAME (or its object ID)
    Auth->>DB: record_sign_in / get_or_create_profile (platform_user)
    Auth-->>API: CurrentUser(groups, is_keigan_admin)
    API->>Authz: application_roles(current_user)
    Authz->>DB: SELECT application_id, admin_group_name, admin_group_object_id, reader_group_name, reader_group_object_id
    Authz->>Authz: Match each application's groups by name or object ID
    Authz-->>API: role per application (admin / reader)
    API-->>Web: Profile + roles
    Web-->>User: Home shows only the applications this user may read or edit
```

## 2. Keigan admin registers an application and its access groups

Keigan does not need to "discover" new groups. The Keigan admin creates the application, which stores the group
**names** (`<CODE>_admin`, `<CODE>_reader` by default, editable). From then on every sign-in matches the user's groups
against those names (flow 1). "Check in Entra" confirms the groups exist and saves their object IDs, which also
makes matching work when the token carries only IDs.

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Keigan admin
    participant IAM as SailPoint / Entra groups team
    participant Web as Keigan web
    participant API as Keigan API
    participant Apps as ApplicationService
    participant Graph as Microsoft Graph
    participant DB as Azure SQL
    actor Owner as Application owner

    Admin->>IAM: Request groups CLMJP_admin and CLMJP_reader, add the owners and readers
    Admin->>Web: Applications - New application (code CLMJP)
    Web->>API: POST /applications
    API->>Apps: create_application (Keigan admin only)
    Apps->>Apps: Default groups from APPLICATION_ADMIN_GROUP_PATTERN / _READER_GROUP_PATTERN
    Apps->>DB: INSERT application (admin_group_name, reader_group_name)
    Admin->>Web: Onboarding - Access step (change the names if your groups differ)
    Web->>API: PATCH /applications/{id}/access (admin_group_name, reader_group_name, optional object IDs)
    Admin->>Web: Check in Entra
    Web->>API: POST /applications/{id}/access/verify
    API->>Apps: verify_access_groups
    loop admin group, then reader group
        Apps->>Graph: GET /groups/{objectId} or /groups?$filter=displayName eq 'CLMJP_admin'
        Graph-->>Apps: Group (or not found)
        Apps->>Graph: GET /groups/{id}/transitiveMembers/microsoft.graph.user ($count)
        Graph-->>Apps: Member count and first names
        Apps->>DB: Save the group object ID if it was missing
    end
    Apps->>DB: INSERT audit_event (application.access_verify)
    API-->>Web: Found / not found, member counts, object ID saved
    Note over Web,DB: Later - the owner signs in for the first time.<br/>Flow 1 finds CLMJP_admin in their groups,<br/>so they can edit CLMJP straight away.
    Owner->>Web: Sign in
    Web-->>Owner: CLMJP appears with admin rights
```

## 3. Grant access, verify and discover an Azure component

```mermaid
sequenceDiagram
    autonumber
    actor Team as Application admin
    participant Web as Keigan web
    participant API as Keigan API
    participant Onb as OnboardingService
    participant Id as AzureCredentialProvider
    participant Cmd as RoleCommandBuilder
    participant Q as JobQueue / JobWorker
    participant ARM as Azure Resource Manager
    participant DB as Azure SQL

    Team->>Web: Add component (subscription, resource group)
    Web->>API: GET /platform/identity
    API->>Id: resolve_keigan_identity()
    alt IDs set in configuration
        Id-->>API: tenant, client and object ID (source settings)
    else IDs left empty (recommended in AKS)
        Id->>Id: Get Keigan's own ARM token (workload identity)
        Id->>Id: Read tid, appid, oid claims
        Id-->>API: tenant, client and object ID (source discovered)
    end
    API-->>Web: Keigan identity (warning banner if anything is missing)
    Web->>API: GET /applications/{id}/components/{cid}/role-commands
    API->>Onb: get_role_commands
    Onb->>Cmd: Build az CLI, PowerShell and portal steps for Keigan's object ID
    Cmd-->>Web: Reader + Monitoring Reader + Log Analytics Reader on the resource group
    Team->>ARM: Runs the commands themselves (Keigan never grants itself access)
    Team->>Web: Verify access
    Web->>API: POST .../verify
    API->>Q: enqueue verify_component_access
    Q->>Onb: verify_component_access(component_id)
    Onb->>ARM: Read resource group, list resources, read a diagnostic setting
    Onb->>DB: access_verification_status = verified or failed, with each check's result
    Team->>Web: Discover resources
    Q->>Onb: discover_component(component_id)
    Onb->>ARM: List resources and their diagnostic settings
    Onb->>DB: UPSERT discovered_resource (classification, Log Analytics workspaces)
    Web-->>Team: Resources, which ones are monitored, which need diagnostic settings
```

## 4. ServiceNow incident to root cause and notifications

```mermaid
sequenceDiagram
    autonumber
    participant Sch as Scheduler (worker)
    participant Q as JobQueue / JobWorker
    participant Inc as IncidentService
    participant SN as ServiceNow
    participant Inv as InvestigationService
    participant G as InvestigationGraphRunner
    participant Ev as EvidenceService
    participant Tel as TelemetryGateway
    participant LLM as LlmGateway
    participant Ntf as NotificationService
    participant DB as Azure SQL

    Sch->>Q: every SERVICENOW_POLL_INTERVAL_SECONDS: enqueue poll_servicenow per live application
    Q->>Inc: poll_servicenow_for_application
    Inc->>SN: Incidents for the application's assignment groups since the watermark
    SN-->>Inc: New or changed incidents
    Inc->>DB: INSERT incident (ServiceNow P1-P4 kept, Keigan priority added)
    alt an open alert group already has an investigation
        Inc->>DB: Link incident to it (_adopt_open_alert_group_investigation)
    else
        Inc->>Inv: start_investigation(incident_id)
        Inv->>Q: enqueue run_investigation
    end
    Inc->>Q: enqueue notify_incident_detected
    Q->>Ntf: on_incident_detected - first email and, if stakeholders subscribed<br/>to Teams incident chats for this priority, enqueue create_incident_chat
    Q->>Inv: run_investigation(investigation_id)
    Inv->>G: run()
    G->>G: triage_node - PiiMasker.mask_text(ticket), affected services, time window
    G->>LLM: generate_structured(TriageResult)
    G->>G: context_node - topology, runbooks, knowledge (token budget)
    G->>Ev: evidence_node - logs, metrics, changes per affected service
    Ev->>Tel: query_logs / query_metrics / query_activity_changes
    Tel-->>Ev: Rows from Log Analytics, App Insights, Elastic, Splunk, Datadog
    Ev->>Ev: PiiMasker.mask_rows, then assess_prompt_injection on log text
    G->>LLM: planner_node - AdditionalQueryPlan (queries checked by validate_generated_query)
    G->>Ev: finalize_evidence_node - rank_and_trim, persist_evidence
    par three analysts in parallel
        G->>LLM: hypothesis_application - HypothesisResult with ProposedFix
    and
        G->>LLM: hypothesis_dependencies - HypothesisResult with ProposedFix
    and
        G->>LLM: hypothesis_infrastructure - HypothesisResult with ProposedFix
    end
    G->>LLM: synthesis_node - RcaSynthesisResult (leading perspective,<br/>what went wrong, why it happened, how to fix)
    G->>G: Drop citations to unknown evidence, neutralise links, flag high-risk commands
    G->>LLM: blast_radius_node - BlastRadiusNarrative
    G->>LLM: communications_node - CommunicationDraftSet (EN / JA)
    G->>DB: Save investigation, hypotheses, evidence, timeline, llm_usage_record
    Note over G,DB: Every model output is schema-validated and grounded in evidence IDs.<br/>Fix steps are proposals only - Keigan does not execute them.
    Inv->>Q: enqueue notify_investigation_completed
    Q->>Ntf: on_investigation_completed
    Ntf->>Ntf: matching_stakeholders (application, priority, language)
    Ntf->>DB: INSERT notification_delivery rows, enqueue deliver_notification
    Ntf->>Ntf: Post the RCA summary card to the Teams incident chat, if one exists
```

## 5. Alert webhook to noise-reduced alert group

```mermaid
sequenceDiagram
    autonumber
    participant Mon as Azure Monitor / Elastic / Datadog
    participant API as Keigan API (public ingress)
    participant Q as JobQueue / JobWorker
    participant Pipe as AlertPipelineService
    participant Inc as IncidentService
    participant Inv as InvestigationService
    participant DB as Azure SQL

    Mon->>API: POST /alerts/in/{alert_source_id} (shared secret or signature)
    API->>API: Check x-keigan-token or HMAC x-keigan-signature, rate limit
    API->>DB: INSERT alert_event (raw payload)
    API-->>Mon: 202 Accepted
    API->>Q: enqueue process_alert_event
    Q->>Pipe: process_event
    Pipe->>Pipe: Map payload to CanonicalAlert (alert_source mapping), mask PII in the alert text
    Pipe->>Pipe: Maintenance window? Mute rule? Duplicate fingerprint? Flapping?
    alt suppressed
        Pipe->>DB: alert_decision (suppressed, with the rule that matched)
    else kept
        Pipe->>DB: Alert + alert_decision, attach to an open alert_group (same service or dependency)
        Pipe->>Q: enqueue settle_alert after the settle delay
        Q->>Pipe: complete_settle_stage
        alt group crosses the policy threshold
            Pipe->>Inv: start_investigation(alert_group)
            opt policy says create the ticket
                Pipe->>Inc: create_servicenow_incident_from_alert_group
            end
        end
    end
    Note over Inc,Inv: If the ServiceNow ticket arrives later, the poller links it to this<br/>group's investigation instead of starting a second one (flow 4).
```

## 6. Teams "Keigan, this is finished" to postmortem email

```mermaid
sequenceDiagram
    autonumber
    actor Eng as Incident engineer
    participant Teams as Microsoft Teams incident chat
    participant Sch as Scheduler (worker)
    participant Ntf as NotificationService
    participant TC as TeamsChatService
    participant Q as JobQueue / JobWorker
    participant Com as CommunicationService
    participant LLM as LlmGateway
    participant Mail as Graph mail / SMTP

    Eng->>Teams: "Keigan, this is finished"
    alt Teams bot installed
        Teams->>TC: POST /teams/messages (handle_bot_activity)
    else polling
        Sch->>Q: every TEAMS_CHAT_POLL_INTERVAL_MINUTES: enqueue poll_incident_chat
        Q->>Ntf: poll_incident_chat
        Ntf->>TC: poll_incident_chat (new messages since last poll)
    end
    TC->>TC: Message matches a TEAMS_MILESTONE_PHRASES entry
    TC->>Q: enqueue generate_postmortem (trigger teams_phrase, deduplicated per incident)
    TC->>Teams: Acknowledge in the chat's language
    Q->>Com: generate_postmortem(incident_id)
    Com->>Com: Timeline from investigation, evidence, chat facts (PII-masked)
    Com->>LLM: generate_structured(PostmortemResult) - blameless wording
    Com->>Ntf: send_postmortem
    Ntf->>Mail: Email to the application's stakeholders
```

## 7. Keigan AI chat: question to query to chart

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Web as Keigan web (chat)
    participant API as Keigan API
    participant Chat as ChatService
    participant LLM as LlmGateway
    participant DQ as ChatDataQueryService
    participant Tel as TelemetryGateway
    participant DB as Azure SQL

    User->>Web: "Show 5xx errors for the claims API over the last 24 hours"
    Web->>API: POST /chat/conversations/{id}/messages
    API->>Chat: send_message
    Chat->>Chat: PiiMasker.mask_text(question), prompt-injection check
    Chat->>LLM: _classify - ChatIntentResult (application, service, time window, intent)
    Chat->>Chat: Only applications this user can read are offered to the model
    alt data question
        Chat->>DQ: run(intent)
        DQ->>LLM: generate_structured(ChatQueryResult) - KQL, Elastic query DSL or SPL
        DQ->>DQ: validate_generated_query - read-only, one statement, bounded time range
        DQ->>Tel: query_logs / query_metrics
        Tel-->>DQ: Rows
        DQ-->>Chat: DataQueryOutcome (series, totals, the query text)
        Chat->>LLM: ChatAnswerResult grounded in the returned rows
    else knowledge or incident question
        Chat->>LLM: Answer from the application's knowledge and investigations
    end
    Chat->>DB: conversation_message (answer, chart spec, query), llm_usage_record
    API-->>Web: Answer + chart + "show query"
```

## 8. Scheduled work: SLOs, burn alerts and the intelligence report

```mermaid
sequenceDiagram
    autonumber
    participant Sch as Scheduler (worker)
    participant Q as JobQueue / JobWorker
    participant Slo as SloService
    participant Tel as TelemetryGateway
    participant Ntf as NotificationService
    participant Int as IntelligenceService
    participant LLM as LlmGateway
    participant DB as Azure SQL

    loop every SLI_COLLECTION_INTERVAL_MINUTES
        Sch->>Q: enqueue collect_sli_measurements per application
        Q->>Slo: collect_due_measurements
        Slo->>Tel: Good / total events for each SLI window
        Slo->>DB: INSERT sli_measurement
        Q->>Slo: evaluate_burn_rates
        Slo->>Slo: Multi-window burn rate per SLO
        opt budget burning too fast
            Slo->>DB: INSERT slo_burn_alert
            Slo->>Ntf: notify_slo_burn_alert
        end
    end
    loop every PREDICTIVE_ANALYSIS_INTERVAL_MINUTES
        Sch->>Q: enqueue run_predictive_analysis per application
        Q->>Int: run_detectors_for_application
        Int->>Int: PredictiveDetectors - seasonal anomalies, error-budget forecasts,<br/>saturation trends, recurring incidents, change risks
        Int->>DB: predictive_signal, health score
    end
    loop hourly check, sends weekly
        Sch->>Q: enqueue send_intelligence_report / weekly_noise_report
        Q->>Int: generate_and_send_report
        Int->>LLM: IntelligenceReportResult (Keigan Intelligence Report)
        Int->>DB: intelligence_report
        Int->>Ntf: Email to stakeholders
    end
```
