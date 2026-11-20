# 14 · Class diagrams

Keigan's backend follows a Java-like layered structure: **controller → service → repository / entity**, with DTOs at the
API edge and integrations behind small interfaces. These diagrams show the main classes and how they depend on each other;
the full list of tables is in [15 · Entity relationship diagram](15_ENTITY_RELATIONSHIP_DIAGRAM.md).

| Package (`backend/keigan/…`) | Holds | Rule |
|---|---|---|
| `controllers/` | FastAPI routers, one per area | Thin: check the role, call one service method, return a DTO |
| `services/` | Business logic, one class per area, constructed per request with the DB session | No HTTP, no SQL strings |
| `repositories/` | `BaseRepository[Entity]` for common queries | Services may also use SQLAlchemy `select()` directly |
| `entities/` | SQLAlchemy tables (`EntityBase`) | The single source of truth for the database and the Azure SQL scripts |
| `dtos/` | Pydantic request/response models (`ApiModel`, camelCase JSON) | Never return entities from controllers |
| `integrations/` | Azure, Graph, ServiceNow, log tools, Teams, email, secrets, files | Each has a live and a simulated mode |
| `ai/` | `LlmGateway`, prompts, output schemas, the investigation graph, prompt safety | Provider-neutral (Gemini, Azure OpenAI, OpenAI-compatible gateway, Anthropic, mock) |
| `workers/` | `JobQueue`, `JobWorker`, `Scheduler` | Jobs live in the `background_job` table |
| `security/` | `CurrentUser`, `SecurityMiddleware`, rate limiter | |
| `utils/` | `PiiMasker`, `query_safety`, log condenser, time and statistics helpers | Pure functions, no I/O |

## 1. Layers and the request path

```mermaid
classDiagram
    direction LR
    class ApplicationController {
        <<router>>
        +create_application(request) ApplicationResponse
        +update_access(application_id, request)
        +verify_access_groups(application_id) AccessVerificationResponse
        +get_platform_identity() PlatformIdentityResponse
    }
    class ApplicationService {
        -session AsyncSession
        +create_application(current_user, request) ApplicationResponse
        +update_access(current_user, application_id, request)
        +verify_access_groups(current_user, application_id) AccessVerificationResponse
        +get_platform_identity() PlatformIdentityResponse
        +delete_application(current_user, application_id)
    }
    class AuthorizationService {
        +application_roles(current_user) dict
        +ensure_keigan_admin(current_user)
        +ensure_application_admin(current_user, application_id)
        +ensure_application_reader(current_user, application_id)
        +readable_application_ids(current_user) set
    }
    class BaseRepository~EntityType~ {
        -session AsyncSession
        +get_by_id() EntityType
        +get_required() EntityType
        +find_all() list
        +find_one() EntityType
        +count() int
        +exists() bool
        +paginate()
        +add(entity) EntityType
        +delete(entity)
    }
    class Application {
        <<entity>>
        +application_id str
        +application_code str
        +admin_group_name str
        +admin_group_object_id str
        +reader_group_name str
        +reader_group_object_id str
        +lifecycle_status str
    }
    class ApplicationResponse {
        <<dto>>
        +applicationId str
        +applicationCode str
        +adminGroupName str
        +readerGroupName str
    }
    class AuditService {
        +record(actor, action, target, details)
    }
    class MicrosoftGraphClient {
        +find_group(display_name, object_id) dict
        +describe_group_members(group_id) dict
    }
    ApplicationController ..> ApplicationService : calls
    ApplicationController ..> AuthorizationService : require_application_admin
    ApplicationService ..> BaseRepository : uses
    ApplicationService ..> AuditService : records
    ApplicationService ..> MicrosoftGraphClient : verifies groups
    BaseRepository ..> Application : loads and saves
    ApplicationService ..> ApplicationResponse : returns
```

## 2. Identity and access

```mermaid
classDiagram
    direction TB
    class CurrentUser {
        <<dataclass>>
        +user_principal_name str
        +display_name str
        +group_names frozenset
        +group_object_ids frozenset
        +is_keigan_admin bool
        +entra_object_id str
        +preferred_locale str
        +is_system_actor() bool
    }
    class AuthenticationService {
        +authenticate_bearer_token(token) CurrentUser
        +sign_in_local_user(user_principal_name) LocalSignInResponse
        +record_sign_in(current_user)
        +get_or_create_profile(current_user) PlatformUser
    }
    class _GroupMembershipCache {
        10-minute cache of Graph lookups
        +read(entra_object_id) tuple
        +write(entra_object_id, group_names, group_object_ids)
    }
    class AuthorizationService {
        +application_roles(current_user) dict
        +can_read_application(current_user, application_id) bool
        +can_edit_application(current_user, application_id) bool
    }
    class ApplicationRole {
        <<dataclass>>
        +application_id str
        +application_code str
        +application_name str
        +role str
    }
    class AzureCredentialProvider {
        +get_access_token(scope, tenant_id) str
        +resolve_keigan_identity() KeiganIdentity
    }
    class KeiganIdentity {
        <<dataclass>>
        +tenant_id str
        +client_id str
        +object_id str
        +display_name str
        +source str
        +missing_values tuple
        +is_complete bool
    }
    class RoleCommandBuilder {
        +build(component) RoleCommandsResponse
    }
    class SecurityMiddleware {
        +dispatch(request, call_next)
    }
    SecurityMiddleware ..> AuthenticationService : bearer token
    AuthenticationService ..> CurrentUser : creates
    AuthenticationService --> _GroupMembershipCache : Graph group lookups
    AuthorizationService ..> CurrentUser : reads groups
    AuthorizationService ..> ApplicationRole : returns
    AzureCredentialProvider ..> KeiganIdentity : resolves
    RoleCommandBuilder --> KeiganIdentity : object ID in commands
```

## 3. Incidents, investigations and notifications

```mermaid
classDiagram
    direction LR
    class IncidentService {
        +poll_servicenow_for_application(application_id)
        +create_servicenow_incident_from_alert_group(alert_group_id) str
        +resolve_incident(current_user, incident_id)
    }
    class InvestigationService {
        +start_investigation(application_id, trigger, incident_id) str
        +run_investigation(investigation_id)
        +rerun(current_user, investigation_id)
        +get_investigation_detail(current_user, investigation_id)
        +submit_feedback(current_user, investigation_id, feedback)
    }
    class InvestigationGraphRunner {
        LangGraph state machine
        +run() InvestigationState
        +triage_node(state)
        +context_node(state)
        +evidence_node(state)
        +planner_node(state)
        +finalize_evidence_node(state)
        -_hypothesis_node(perspective)
        +synthesis_node(state)
        +blast_radius_node(state)
        +communications_node(state)
    }
    class EvidenceService {
        +rank_and_trim(drafts, token_budget) list
        +persist_evidence(investigation_id, drafts) list
    }
    class TelemetryGateway {
        +query_logs(query) LogQueryResult
        +query_metrics(query) MetricQueryResult
        +query_activity_changes(target, window) list
        +test_log_source(source) ConnectionTestResult
    }
    class LlmGateway {
        +generate_structured(prompt, output_schema, usage_context) BaseModel
        +generate_text(prompt, usage_context) str
        +describe_image(image, usage_context) str
        +ensure_budget_available(application_id)
    }
    class PromptLibrary {
        +load_template(template_name)
        +render(template_name, sections)
        +version_of(template_name) str
    }
    class PiiMasker {
        +mask_text(text) str
        +mask_rows(rows) list
        +mask_value(value) object
    }
    class RcaSynthesisResult {
        <<schema>>
        +leading_perspective str
        +overall_confidence_score float
        +executive_summary str
        +what_went_wrong_markdown str
        +why_it_happened_markdown str
        +how_to_fix_markdown str
        +open_questions list
    }
    class HypothesisResult {
        <<schema>>
        one per perspective - application, dependencies, infrastructure
        +hypothesis_title str
        +hypothesis_statement_markdown str
        +reasoning_markdown str
        +confidence_score float
        +supporting_evidence_codes list
        +contradicting_evidence_codes list
        +proposed_fix ProposedFix
        +fix_risk_level str
    }
    class ProposedFix {
        <<schema>>
        +summary str
        +steps list~FixStep~
        +code_changes list~CodeChange~
        +verification_steps list
        +rollback_steps list
    }
    class NotificationService {
        +on_incident_detected(incident_id)
        +on_investigation_completed(investigation_id)
        +send_postmortem(postmortem_id)
        +deliver(notification_delivery_id)
    }
    class CommunicationService {
        +generate_communications(investigation_id, types, languages)
        +generate_postmortem(incident_id, trigger)
    }
    class TeamsChatService {
        +create_incident_chat(incident_id)
        +poll_incident_chat(chat_id)
        +handle_bot_activity(activity)
    }
    IncidentService ..> InvestigationService : start_investigation
    InvestigationService ..> InvestigationGraphRunner : run
    InvestigationGraphRunner ..> EvidenceService
    InvestigationGraphRunner ..> LlmGateway
    InvestigationGraphRunner ..> PiiMasker
    EvidenceService ..> TelemetryGateway
    EvidenceService ..> PiiMasker
    LlmGateway ..> PromptLibrary
    InvestigationGraphRunner ..> HypothesisResult : three in parallel
    InvestigationGraphRunner ..> RcaSynthesisResult : compares them
    HypothesisResult *-- ProposedFix
    InvestigationService ..> NotificationService : via job queue
    NotificationService ..> TeamsChatService
    TeamsChatService ..> CommunicationService : milestone phrase, postmortem job
```

## 4. Integrations behind interfaces (live or simulated)

```mermaid
classDiagram
    direction TB
    class LogToolClient {
        <<abstract>>
        +search(query, window) LogQueryResult
        +test_connection() ConnectionTestResult
    }
    class ElasticClient
    class SplunkClient
    class DatadogClient
    class PlaceholderReader {
        SolarWinds and other tools not built yet
    }
    class LogToolClientFactory {
        +client_for(connection) LogToolClient
    }
    LogToolClient <|-- ElasticClient
    LogToolClient <|-- SplunkClient
    LogToolClient <|-- DatadogClient
    LogToolClient <|-- PlaceholderReader
    LogToolClientFactory ..> LogToolClient : creates

    class SecretStore {
        <<abstract>>
        +set_secret(name, value)
        +get_secret(name) str
        +delete_secret(name)
    }
    class LocalEncryptedSecretStore
    class KeyVaultSecretStore
    SecretStore <|-- LocalEncryptedSecretStore
    SecretStore <|-- KeyVaultSecretStore

    class FileStorage {
        <<abstract>>
        +save_file(storage_path, file_bytes, content_type)
        +read_file(storage_path) bytes
        +delete_file(storage_path)
    }
    class LocalFileStorage
    class AzureBlobFileStorage
    FileStorage <|-- LocalFileStorage
    FileStorage <|-- AzureBlobFileStorage

    class TelemetryGateway {
        +query_logs(query) LogQueryResult
        +query_metrics(query) MetricQueryResult
    }
    class AzureClient {
        +list_resource_group_resources() list
        +get_diagnostic_settings() list
        +query_log_analytics() LogQueryResult
        +query_metrics() MetricQueryResult
        +list_activity_changes() list
        +verify_read_access() AccessCheckResult
    }
    class TelemetrySimulator {
        +query_logs(query) LogQueryResult
        +query_metrics(query) MetricQueryResult
        +query_activity_changes() list
    }
    TelemetryGateway ..> AzureClient : TELEMETRY_MODE=live
    TelemetryGateway ..> LogToolClientFactory : Elastic, Splunk, Datadog
    TelemetryGateway ..> TelemetrySimulator : TELEMETRY_MODE=simulated

    class ServiceNowClient {
        +list_incidents() list
        +create_incident() str
        +update_incident()
    }
    class ServiceNowSimulator
    class BotFrameworkClient {
        +send_activity()
        +validate_inbound_request()
    }
    class SmtpEmailSender {
        +send(message)
    }
    class MicrosoftGraphClient {
        +send_mail()
        +create_group_chat() str
        +install_app_in_chat()
        +list_chat_messages_since() list
        +find_group() dict
        +describe_group_members() dict
    }
    ServiceNowClient .. ServiceNowSimulator : SERVICENOW_MODE
```

## 5. Background work

```mermaid
classDiagram
    direction LR
    class JobQueue {
        +enqueue(job_type, arguments, deduplication_key, priority_number, available_at) str
    }
    class JobWorker {
        +run_forever()
        +stop()
    }
    class Scheduler {
        +run_forever()
        +stop()
    }
    class IntervalSchedule {
        <<dataclass>>
        +schedule_name str
        +interval_seconds float
        +action
    }
    class JobHandlerReference {
        <<dataclass>>
        +module_path str
        +service_class_name str
        +method_name str
    }
    class BackgroundJob {
        <<entity>>
        +background_job_id str
        +job_type str
        +job_payload_json json
        +job_status str
        +priority_number int
        +deduplication_key str
        +attempt_count int
        +available_at datetime
        +leased_by_worker_name str
        +lease_expires_at datetime
    }
    Scheduler *-- IntervalSchedule
    Scheduler ..> JobQueue : enqueue on interval
    JobQueue ..> BackgroundJob : INSERT
    JobWorker ..> BackgroundJob : claim, run, retry
    JobWorker ..> JobHandlerReference : JOB_HANDLERS lookup
```

`JOB_HANDLERS` in `workers/job_handlers.py` maps each job type to a service method, for example
`run_investigation → InvestigationService.run_investigation` and `generate_postmortem → CommunicationService.generate_postmortem`.
Schedules: ServiceNow poll, SLI collection, predictive analysis, Teams chat poll, weekly reports, retention cleanup.

## 6. Linked ids, alert group links, status values and reference release

Four small building blocks keep the data model honest. Lists of ids of other rows are association tables read and written through
`LinkedIdsMixin`; every link between an alert group, an investigation and an incident is written by `AlertGroupLinkService`; every fixed
value set is a `StrEnum` that also becomes the database CHECK constraint; deleting a service, runbook or document releases the rows that
still point at it. Tables and constraints are described in [03 · Database design](03_DATABASE_DESIGN.md) §11 to §14.

```mermaid
classDiagram
    direction LR
    class LinkedIdsMixin {
        <<mixin>>
        +link_relationship_names tuple
        +linked_ids(relationship_name) list
        +replace_linked_ids(relationship_name, identifiers)
    }
    class OrderedLinkColumns {
        <<mixin>>
        +linked_id_attribute str
        +position int
    }
    class Incident {
        <<entity>>
        +affected_service_links list
        +affected_service_ids list
    }
    class IncidentAffectedService {
        <<association entity>>
        +incident_id str
        +service_id str
        +position int
    }
    class MonitoredService {
        <<entity>>
        +service_id str
    }
    class AlertGroupLinkService {
        -session AsyncSession
        +link(alert_group, investigation_id, incident_id)
    }
    class AlertGroup {
        <<entity>>
        +investigation_id str
        +incident_id str
        +affected_service_links list
    }
    class Investigation {
        <<entity>>
        +incident_id str
    }
    class reference_release {
        <<module>>
        +columns_that_block_deleting(referenced_column) list
        +release_references(session, referenced_attribute, referenced_ids)
    }
    class service_scope {
        <<module>>
        +unknown_service_ids(session, application_id, service_ids) set
    }
    class status_values {
        <<module>>
        one StrEnum per fixed-value column
        +sql_in_list(values) str
        +values_check(column_name, values) CheckConstraint
    }
    class AlertGroupStatus {
        <<StrEnum>>
        OPEN
        INVESTIGATING
        QUEUED
        RESOLVED
    }
    Incident --|> LinkedIdsMixin
    AlertGroup --|> LinkedIdsMixin
    IncidentAffectedService --|> OrderedLinkColumns
    Incident "1" *-- "0..*" IncidentAffectedService : cascade
    IncidentAffectedService "0..*" --> "1" MonitoredService : NO ACTION
    AlertGroupLinkService ..> AlertGroup : sets investigation_id and incident_id
    AlertGroupLinkService ..> Investigation : sets incident_id
    AlertGroupLinkService ..> Incident : loads, checks application
    reference_release ..> MonitoredService : releases rows that name it
    service_scope ..> MonitoredService : checks ids belong to the application
    status_values *-- AlertGroupStatus
    AlertGroup ..> status_values : values_check on group_status
```

- Modules: `entities/linked_ids.py`, `entities/status_values.py`, `services/reference_release.py` and `services/service_scope.py`; the service is
  `services/alert_group_link_service.py`.
- `Incident`, `Investigation`, `AlertGroup`, `Conversation`, `MaintenanceWindow`, `Runbook`, `Stakeholder` and `ApplicationTopology` use
  `LinkedIdsMixin`; `Incident` and `AlertGroup` are shown as the example. Each association entity (nine in all) extends `OrderedLinkColumns`
  and names its linked id column in `linked_id_attribute`.
- `AlertGroupLinkService.link` is the only writer of `alert_group.investigation_id` and `alert_group.incident_id`. It raises
  `NotFoundException` or `ConflictException` instead of storing a combination that disagrees.
- `release_references` walks the foreign keys in the entity metadata, so a new reference is released without editing a list of tables. A
  nullable referencing column is set to NULL, a column that cannot be NULL (an association row) means the row is deleted.
- `unknown_service_ids` is the one check, shared by the alert, investigation, runbook and stakeholder services, that the service ids a user
  sent belong to the application.
