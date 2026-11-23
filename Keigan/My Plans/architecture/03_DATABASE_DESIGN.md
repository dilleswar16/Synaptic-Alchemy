# 03 — Database design (static schema)

Source of truth for persistence. The SQLAlchemy entities in `backend/keigan/entities/*.py` implement exactly this.
Any change must be made here first (or recorded in the change log at the bottom) and then in the entity.

## 1. Conventions

| Rule | Detail |
|---|---|
| Names | `snake_case`, fully descriptive, singular table names (`incident`, not `incidents`). No abbreviations except the accepted acronyms (`id`, `url`, `sli`, `slo`, `kql`, `llm`, `ai`, `aks`, `pii`). |
| Primary keys | `<table>_id` `VARCHAR(36)` holding a UUID v4 string, generated in Python. Exception: high-volume `sli_measurement` uses `BIGINT` autoincrement. |
| Foreign keys | Same name as the referenced primary key (`application_id`). Every column that names an application, incident, investigation, SLI or service has a real foreign key (section 12). `ON DELETE CASCADE` only for owned children where the table has a single cascade path; otherwise `NO ACTION`. |
| Time | `TIMESTAMP WITH TIME ZONE`, stored in UTC, columns end with `_at` (instants) or `_start` / `_end` (ranges). |
| Enumerations | `VARCHAR(40)` with allowed values listed below (portable across SQLite and PostgreSQL). Each fixed value set is one Python `StrEnum` in `keigan/entities/status_values.py` and the database enforces it with a `CHECK` constraint (section 14). |
| Flexible data | `JSON` columns end with `_json`. Only for data that is read as a whole (configuration, AI payloads), never for data we filter on and never for lists of ids of other Keigan rows (those are association tables, section 11). |
| Audit columns | Mixin on most tables: `created_at`, `updated_at`, `created_by_user_principal_name`, `updated_by_user_principal_name`. Marked **[audit]** below. |
| Soft delete | Not used. Retention jobs purge by age. |
| Secrets | Never stored in plain text. Only `credential_secret_name` (a reference into Key Vault / the local encrypted store). |
| PII | Telemetry-derived text is stored **masked** (`*_masked` columns or documented as masked). |

Database engines: SQLite (local, WAL mode), **Azure SQL Database** (production target) and PostgreSQL 16 (still supported).
Local schema is created with `Base.metadata.create_all`. In Azure the schema comes from the generated scripts in
`database/azure_sql/` (run once before the first install) and Alembic migrations afterwards (baseline `94692c828bd3`, current head `f1b9d3a5c7e2`).
The column types written below as `VARCHAR` / `TIMESTAMPTZ` are the logical types; on Azure SQL they are created as:

| Logical type | Azure SQL type | Why |
|---|---|---|
| `VARCHAR(n)`, `TEXT` | `NVARCHAR(n)`, `NVARCHAR(max)` | Japanese and Chinese text needs Unicode |
| `TIMESTAMP WITH TIME ZONE` | `DATETIME2(6)` holding UTC | SQL Server's `DATETIMEOFFSET` is not needed when every value is UTC |
| `JSON` | `NVARCHAR(max)` | SQL Server has no JSON column type; `JSON_VALUE` still works on it |
| `BOOLEAN` / `FLOAT` | `BIT` / `FLOAT` | |

All tables live in schema `DATABASE_SCHEMA` (`keigan`). Constraint and index names follow one convention so migrations can
change them by name: `pk_<table>`, `fk_<table>_<column>_<referenced table>`, `uq_<table>_<columns>`, `ix_<table>_<columns>`.
Diagrams: [15 · Entity relationship diagram](15_ENTITY_RELATIONSHIP_DIAGRAM.md) (generated from the entities).

## 2. Entity overview

```
platform:      platform_user · platform_setting · stored_secret · audit_event · llm_usage_record · background_job
application:   application ─┬─ application_component ─── discovered_resource
                            ├─ monitored_service ─┬─ service_log_source ── log_tool_connection
                            │                     └─ service_dependency
                            ├─ external_integration · application_record_link
knowledge:     knowledge_document ── knowledge_chunk · application_topology · topology_review_comment · runbook
incident:      servicenow_assignment_group · incident ─── investigation ─┬─ investigation_hypothesis
                                                                       ├─ investigation_evidence
                                                                       └─ investigation_timeline_event
               incident_communication · postmortem_report · conversation ─┬─ conversation_message
                                                                          └─ chat_answer_run ── chat_run_step
alert:         alert_source ── alert_event · alert ── alert_decision · alert_group · noise_reduction_policy · maintenance_window · alert_mute_rule
slo:           service_level_indicator ── service_level_objective · sli_measurement · slo_burn_alert
intelligence:  predictive_signal · intelligence_report
notification:  stakeholder · notification_delivery · teams_incident_chat
association:   nine tables that hold ordered id lists, named in section 11
```

## 3. Platform tables (`platform_entities.py`)

### `platform_user`
| Column | Type | Notes |
|---|---|---|
| platform_user_id | VARCHAR(36) PK | |
| user_principal_name | VARCHAR(320) UNIQUE NOT NULL | Entra UPN or local user id |
| display_name | VARCHAR(200) | |
| email_address | VARCHAR(320) | |
| entra_object_id | VARCHAR(36) | null in local mode |
| preferred_locale | VARCHAR(10) | `en`, `ja`, `zh-CN`, `es`, `es-MX`, `nl`, `fr` |
| preferred_theme | VARCHAR(10) | `light`, `dark`, `system` |
| last_known_group_names_json | JSON | for display only, never for authorization |
| last_sign_in_at | TIMESTAMPTZ | |
| [audit] | | |

### `platform_setting`
| Column | Type | Notes |
|---|---|---|
| setting_key | VARCHAR(200) PK | e.g. `servicenow_watermark:{application_id}` |
| setting_value_json | JSON | |
| setting_description | TEXT | |
| updated_at, updated_by_user_principal_name | | |

### `stored_secret`
Local encrypted secret store (used only when `SECRET_STORE_MODE=local_encrypted`; in Key Vault mode only metadata rows exist).
| Column | Type | Notes |
|---|---|---|
| secret_name | VARCHAR(200) PK | e.g. `logtool-elastic-3f2a…` |
| encrypted_secret_value | TEXT | Fernet token; null in Key Vault mode |
| secret_description | VARCHAR(400) | |
| last_rotated_at | TIMESTAMPTZ | |
| [audit] | | |

### `audit_event`
| Column | Type | Notes |
|---|---|---|
| audit_event_id | VARCHAR(36) PK | |
| actor_user_principal_name | VARCHAR(320) | `system:worker` for jobs |
| action_name | VARCHAR(120) | e.g. `application.update`, `ai.query.execute` |
| target_entity_type | VARCHAR(80) | |
| target_entity_id | VARCHAR(36) | |
| application_id | VARCHAR(36) | nullable, indexed |
| action_details_json | JSON | masked |
| client_ip_address | VARCHAR(64) | |
| correlation_id | VARCHAR(64) | |
| occurred_at | TIMESTAMPTZ | indexed |

### `llm_usage_record`
| Column | Type | Notes |
|---|---|---|
| llm_usage_record_id | VARCHAR(36) PK | |
| application_id | VARCHAR(36) | nullable, indexed |
| investigation_id | VARCHAR(36) | nullable |
| conversation_id | VARCHAR(36) | nullable |
| feature_name | VARCHAR(80) | `triage`, `hypothesis_application`, `synthesis`, `communications`, `postmortem`, `chat_answer`, `query_generation`, `topology`, `document_digest`, `intelligence_narrative`, … |
| provider_name | VARCHAR(40) | |
| model_name | VARCHAR(120) | |
| model_tier | VARCHAR(20) | `fast`, `deep`, `vision` |
| input_token_count | INTEGER | |
| output_token_count | INTEGER | |
| cached_input_token_count | INTEGER | |
| latency_milliseconds | INTEGER | |
| outcome_status | VARCHAR(20) | `succeeded`, `failed`, `blocked_by_budget`, `validation_retry` |
| error_message | TEXT | |
| requested_by_user_principal_name | VARCHAR(320) | |
| created_at | TIMESTAMPTZ | indexed |

### `background_job`
| Column | Type | Notes |
|---|---|---|
| background_job_id | VARCHAR(36) PK | |
| job_type | VARCHAR(80) | indexed |
| job_payload_json | JSON | |
| job_status | VARCHAR(20) | `queued`, `running`, `succeeded`, `failed`, `dead_lettered`, `cancelled` |
| priority_number | INTEGER | lower runs first, default 100 |
| deduplication_key | VARCHAR(200) | UNIQUE among non-finished jobs (enforced in code) |
| attempt_count | INTEGER | |
| maximum_attempt_count | INTEGER | |
| available_at | TIMESTAMPTZ | indexed with status |
| leased_by_worker_name | VARCHAR(120) | |
| lease_expires_at | TIMESTAMPTZ | |
| last_error_message | TEXT | |
| result_summary_json | JSON | |
| created_at, started_at, finished_at | TIMESTAMPTZ | |

## 4. Application tables (`application_entities.py`)

### `application`
| Column | Type | Notes |
|---|---|---|
| application_id | VARCHAR(36) PK | |
| application_name | VARCHAR(200) NOT NULL | |
| application_code | VARCHAR(20) UNIQUE NOT NULL | upper case, used in AD group names |
| application_description | TEXT | |
| business_unit_name | VARCHAR(200) | |
| region_code | VARCHAR(10) | `JP`, `AU`, `US`, `MX`, `CN`, `NL`, `FR`, … |
| primary_locale | VARCHAR(10) | |
| time_zone_name | VARCHAR(60) | IANA, e.g. `Asia/Tokyo` |
| criticality_tier | VARCHAR(10) | `tier_1`, `tier_2`, `tier_3` |
| lifecycle_status | VARCHAR(20) | `requested`, `draft`, `onboarding`, `live`, `paused` |
| admin_group_name | VARCHAR(200) | default from pattern |
| admin_group_object_id | VARCHAR(36) | optional |
| reader_group_name | VARCHAR(200) | |
| reader_group_object_id | VARCHAR(36) | optional |
| incident_creation_policy_json | JSON | `{mode: suggest|automatic, minimum_score, assignment_group_name}` |
| onboarding_progress_json | JSON | per-step "nothing to add" markers, last visited step |
| went_live_at | TIMESTAMPTZ | |
| went_live_by_user_principal_name | VARCHAR(320) | |
| operating_notes_text | TEXT (NVARCHAR(max)) | nullable; the team's guidance for the AI, trimmed, line breaks stored as `
`; longest allowed is `APPLICATION_OPERATING_NOTES_MAXIMUM_CHARACTERS` (default 4000, at most 20000); null = no notes |
| operating_notes_updated_at | TIMESTAMPTZ | nullable; set only when the text changes |
| operating_notes_updated_by_user_principal_name | VARCHAR(320) | nullable |
| [audit] | | |

### `application_component`
| Column | Type | Notes |
|---|---|---|
| component_id | VARCHAR(36) PK | |
| application_id | FK application CASCADE | indexed |
| component_type | VARCHAR(40) | `azure_resource_group`, `hardware`, `mainframe`, `saas_platform` |
| component_name | VARCHAR(200) | RG name, device name, system name, vendor product |
| environment_name | VARCHAR(20) | `dev`, `test`, `uat`, `prod` |
| azure_tenant_id | VARCHAR(36) | Azure only |
| azure_subscription_id | VARCHAR(36) | Azure only |
| azure_subscription_name | VARCHAR(200) | Azure only |
| azure_resource_group_name | VARCHAR(200) | Azure only |
| component_configuration_json | JSON | type-specific fields (hardware category, hostname, location, CMDB CI; mainframe LPAR, subsystems, job prefixes, batch windows; SaaS vendor, instance URL, status page URL, probe URL, SLA) |
| access_verification_status | VARCHAR(20) | `not_checked`, `checking`, `verified`, `missing_roles`, `failed`, `not_applicable` |
| access_verification_details_json | JSON | per check: name, passed, message, missing role |
| last_verified_at | TIMESTAMPTZ | |
| last_discovered_at | TIMESTAMPTZ | |
| discovery_summary_json | JSON | counts for the card |
| [audit] | | |

### `discovered_resource`
| Column | Type | Notes |
|---|---|---|
| discovered_resource_id | VARCHAR(36) PK | |
| component_id | FK application_component CASCADE | |
| application_id | FK application NO ACTION | indexed |
| azure_resource_id | VARCHAR(600) | full ARM id (unique per component) |
| resource_name | VARCHAR(260) | |
| resource_type | VARCHAR(200) | ARM type |
| resource_kind | VARCHAR(120) | |
| location_name | VARCHAR(60) | |
| monitoring_classification | VARCHAR(30) | `monitored_service`, `telemetry_source`, `not_monitored_type` |
| has_diagnostic_setting | BOOLEAN | |
| diagnostic_settings_json | JSON | destinations, categories |
| log_analytics_workspace_resource_ids_json | JSON | |
| resource_tags_json | JSON | |
| last_seen_at | TIMESTAMPTZ | |
| no_longer_found_at | TIMESTAMPTZ | |

### `monitored_service`
| Column | Type | Notes |
|---|---|---|
| service_id | VARCHAR(36) PK | |
| application_id | FK application CASCADE | indexed |
| component_id | FK application_component | |
| discovered_resource_id | VARCHAR(36) | nullable (manual services) |
| service_name | VARCHAR(200) | display name |
| service_type | VARCHAR(40) | `aks`, `function_app`, `app_service`, `logic_app`, `api_management`, `data_factory`, `sql_database`, `server`, `network_appliance`, `storage_device`, `mainframe_subsystem`, `batch_job_stream`, `saas_service`, `other` |
| external_resource_identifier | VARCHAR(600) | ARM id / hostname / vendor service id |
| environment_name | VARCHAR(20) | |
| criticality_tier | VARCHAR(10) | `tier_1`, `tier_2`, `tier_3` |
| is_monitoring_enabled | BOOLEAN | default true |
| aks_namespace_filter | VARCHAR(200) | AKS only |
| application_insights_resource_id | VARCHAR(600) | linked component |
| application_insights_role_name | VARCHAR(200) | `cloud_RoleName` filter |
| available_metrics_json | JSON | cached metric definitions (name, unit, aggregations) |
| repository_provider | VARCHAR(40) | `azure_devops`, `github_enterprise` |
| repository_url | VARCHAR(600) | |
| repository_default_branch | VARCHAR(200) | |
| repository_path | VARCHAR(400) | monorepo subpath |
| repository_credential_secret_name | VARCHAR(200) | |
| service_description | TEXT | |
| [audit] | | |

### `service_dependency`
| Column | Type | Notes |
|---|---|---|
| service_dependency_id | VARCHAR(36) PK | |
| application_id | FK application NO ACTION | indexed |
| upstream_service_id | FK monitored_service CASCADE | the caller / consumer |
| downstream_service_id | FK monitored_service CASCADE | the dependency |
| dependency_kind | VARCHAR(30) | `calls`, `reads_from`, `writes_to`, `publishes_to`, `hosted_on` |
| dependency_source | VARCHAR(30) | `user_declared`, `topology_inferred` |
| created_at | TIMESTAMPTZ | |

### `log_tool_connection`
| Column | Type | Notes |
|---|---|---|
| log_tool_connection_id | VARCHAR(36) PK | |
| application_id | FK application CASCADE | |
| tool_type | VARCHAR(40) | `elastic`, `splunk`, `datadog`, `solarwinds`, `ibm_z_log_analytics`, `vendor_api`, `other` |
| connection_name | VARCHAR(200) | |
| endpoint_url | VARCHAR(600) | |
| authentication_method | VARCHAR(40) | `api_key`, `basic`, `bearer_token`, `oauth_client_credentials`, `managed_identity`, `none` |
| credential_secret_name | VARCHAR(200) | |
| connection_configuration_json | JSON | index patterns, field names, site, source types… |
| connection_status | VARCHAR(30) | `not_tested`, `connected`, `failed`, `reader_not_available` |
| last_tested_at | TIMESTAMPTZ | |
| last_test_message | TEXT | |
| newest_log_timestamp_seen_at | TIMESTAMPTZ | |
| [audit] | | |

### `service_log_source`
| Column | Type | Notes |
|---|---|---|
| service_log_source_id | VARCHAR(36) PK | |
| service_id | FK monitored_service CASCADE | indexed |
| source_kind | VARCHAR(40) | `log_analytics`, `application_insights`, `azure_monitor_metrics`, `log_tool`, `synthetic_probe`, `vendor_status_page` |
| log_tool_connection_id | FK log_tool_connection | nullable |
| log_analytics_workspace_resource_id | VARCHAR(600) | |
| log_analytics_workspace_customer_id | VARCHAR(36) | GUID used by the query API |
| query_scope_json | JSON | index, namespace, labels, tags, host filter, service field value |
| is_primary_source | BOOLEAN | |
| was_auto_detected | BOOLEAN | |
| last_read_test_status | VARCHAR(20) | `not_tested`, `passed`, `failed` |
| last_read_test_at | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ | |

### `external_integration`
Generic record for placeholder and real integrations (CMDB, EI portal, enterprise knowledge API, application-specific ServiceNow).
| Column | Type | Notes |
|---|---|---|
| external_integration_id | VARCHAR(36) PK | |
| application_id | FK application CASCADE | null = platform-wide |
| integration_kind | VARCHAR(40) | `cmdb`, `ei_portal`, `knowledge_api`, `servicenow` |
| integration_configuration_json | JSON | rendered from `integration_field_schemas.yaml` |
| credential_secret_name | VARCHAR(200) | |
| integration_status | VARCHAR(30) | `not_set_up`, `configured`, `saved_reader_in_development` |
| integration_notes | TEXT | |
| [audit] | | |

### `application_record_link`
| Column | Type | Notes |
|---|---|---|
| application_record_link_id | VARCHAR(36) PK | |
| application_id | FK application CASCADE | |
| record_system | VARCHAR(30) | `eai`, `cmdb` |
| record_identifier | VARCHAR(100) | e.g. EAI `14470`, CMDB CI number |
| link_status | VARCHAR(30) | `saved_reader_in_development` (the only value the backend writes today; no CHECK) |
| created_at | TIMESTAMPTZ | |

## 5. Knowledge tables (`knowledge_entities.py`)

### `knowledge_document`
| Column | Type | Notes |
|---|---|---|
| knowledge_document_id | VARCHAR(36) PK | |
| application_id | FK application CASCADE | indexed |
| service_id | FK monitored_service NO ACTION | nullable (whole application) |
| document_title | VARCHAR(300) | |
| document_category | VARCHAR(40) | `code_context`, `architecture_diagram`, `design_document`, `operational_note`, `cmdb_record`, `ei_portal_record` |
| original_file_name | VARCHAR(300) | sanitised |
| content_type | VARCHAR(120) | |
| file_size_bytes | BIGINT | |
| storage_path | VARCHAR(600) | blob path / local relative path |
| file_sha256_hash | VARCHAR(64) | duplicate detection |
| extracted_text | TEXT | for Markdown/PDF; for images the vision description |
| extracted_headings_json | JSON | |
| ai_digest_markdown | TEXT | structured summary used for grounding |
| ai_digest_status | VARCHAR(20) | `pending`, `running`, `ready`, `failed` |
| ai_digest_error_message | TEXT | |
| estimated_token_count | INTEGER | |
| uploaded_by_user_principal_name | VARCHAR(320) | |
| uploaded_at | TIMESTAMPTZ | |
| stale_after_at | TIMESTAMPTZ | uploaded_at + 90 days |

### `knowledge_chunk`
| Column | Type | Notes |
|---|---|---|
| knowledge_chunk_id | VARCHAR(36) PK | |
| knowledge_document_id | FK knowledge_document CASCADE | |
| application_id | FK application NO ACTION | indexed |
| service_id | FK monitored_service NO ACTION | nullable |
| chunk_sequence_number | INTEGER | |
| section_heading | VARCHAR(400) | |
| chunk_text | TEXT | |
| estimated_token_count | INTEGER | |
| search_terms_json | JSON | normalised term frequencies for lexical (BM25) retrieval; replaced by embeddings when RAG arrives |

### `application_topology`
| Column | Type | Notes |
|---|---|---|
| topology_id | VARCHAR(36) PK | |
| application_id | FK application CASCADE | |
| topology_version_number | INTEGER | |
| topology_graph_json | JSON | `{nodes:[{node_key, label, node_type, service_id?, technology, description, criticality}], edges:[{source_node_key, target_node_key, relationship, protocol, description}]}` |
| understanding_summary_markdown | TEXT | Keigan's narrative of how the application works |
| source documents | association table `topology_source_document` | section 11 |
| generation_status | VARCHAR(20) | `building`, `ready` |
| generated_by_model_name | VARCHAR(120) | |
| review_status | VARCHAR(30) | `awaiting_review`, `reviewed`, `needs_correction` |
| is_current_version | BOOLEAN | |
| created_at | TIMESTAMPTZ | |

### `topology_review_comment`
| Column | Type | Notes |
|---|---|---|
| topology_review_comment_id | VARCHAR(36) PK | |
| topology_id | FK application_topology CASCADE | |
| target_element_key | VARCHAR(200) | node key or `source->target` edge key; null = whole topology |
| review_verdict | VARCHAR(30) | `looks_right`, `needs_correction`, `comment` |
| review_comment_text | TEXT | |
| reviewer_user_principal_name | VARCHAR(320) | |
| created_at | TIMESTAMPTZ | |

### `runbook`
| Column | Type | Notes |
|---|---|---|
| runbook_id | VARCHAR(36) PK | |
| application_id | FK application CASCADE | |
| runbook_title | VARCHAR(300) | |
| trigger_symptoms_text | TEXT | when it applies: symptoms, alert names, error signatures |
| runbook_steps_markdown | TEXT | |
| source_url | VARCHAR(600) | |
| applies to services | association table `runbook_applies_to_service` | section 11; empty = whole application |
| knowledge_document_id | VARCHAR(36) | if uploaded as a file |
| search_terms_json | JSON | lexical retrieval |
| times_referenced_count | INTEGER | |
| last_referenced_at | TIMESTAMPTZ | |
| [audit] | | |

## 6. Incident and investigation tables (`incident_entities.py`)

### `servicenow_assignment_group`
| Column | Type | Notes |
|---|---|---|
| assignment_group_id | VARCHAR(36) PK | |
| application_id | FK application CASCADE | |
| group_name | VARCHAR(200) | exact ServiceNow name |
| servicenow_sys_id | VARCHAR(64) | when verified |
| verification_status | VARCHAR(20) | `unverified`, `verified` |
| created_at | TIMESTAMPTZ | |

### `incident`
| Column | Type | Notes |
|---|---|---|
| incident_id | VARCHAR(36) PK | |
| application_id | FK application | indexed |
| incident_source | VARCHAR(20) | `servicenow`, `alert`, `manual` |
| external_incident_number | VARCHAR(40) | `INC0012345`; indexed |
| external_system_identifier | VARCHAR(64) | ServiceNow sys_id |
| incident_title | VARCHAR(500) | |
| incident_description | TEXT | as received (access-controlled; masked before AI) |
| servicenow_priority | VARCHAR(10) | `1`–`5` as in ServiceNow |
| servicenow_impact | VARCHAR(10) | |
| servicenow_urgency | VARCHAR(10) | |
| keigan_priority | VARCHAR(4) | `P1`–`P4` |
| priority_rationale | TEXT | |
| incident_category | VARCHAR(40) | `availability`, `latency`, `errors`, `data`, `batch`, `security`, `capacity`, `dependency`, `change_related`, `unknown` |
| incident_status | VARCHAR(20) | `new`, `investigating`, `identified`, `monitoring`, `resolved`, `closed` |
| affected services | association table `incident_affected_service` | section 11; the first one is the primary service |
| assignment_group_name | VARCHAR(200) | |
| external_state | VARCHAR(40) | ServiceNow state label |
| opened_at | TIMESTAMPTZ | |
| detected_by_keigan_at | TIMESTAMPTZ | |
| first_update_sent_at | TIMESTAMPTZ | TTFU |
| resolved_at | TIMESTAMPTZ | |
| keigan_help | VARCHAR(20) NULL | the resolver's answer to "how did Keigan's analysis help?": `found_cause`, `helped_partly`, `did_not_help`, `not_used`; null when not answered (revision `a1b5c9d3e7f2`, 2026-11-24) |
| closed_at | TIMESTAMPTZ | |
| external_last_updated_at | TIMESTAMPTZ | |
| [audit] | | |
UNIQUE (`application_id`, `external_incident_number`).

### `investigation`
| Column | Type | Notes |
|---|---|---|
| investigation_id | VARCHAR(36) PK | |
| application_id | FK application | indexed |
| incident_id | FK incident | nullable |
| investigation_trigger | VARCHAR(20) | `incident`, `alert_group`, `manual`, `rerun` |
| investigation_status | VARCHAR(30) | `queued`, `running`, `completed`, `completed_evidence_only`, `failed`, `cancelled` |
| current_stage_name | VARCHAR(30) | `triage`, `context`, `evidence`, `hypotheses`, `synthesis`, `communications`, `completed` |
| progress_percent | INTEGER | |
| investigation_window_start | TIMESTAMPTZ | |
| investigation_window_end | TIMESTAMPTZ | |
| baseline_window_start | TIMESTAMPTZ | |
| baseline_window_end | TIMESTAMPTZ | |
| investigated services | association table `investigation_investigated_service` | section 11; in the order triage found them |
| triage_result_json | JSON | priority, category, candidates, summary |
| executive_summary | TEXT | 2–3 sentences |
| what_went_wrong_markdown | TEXT | |
| why_it_happened_markdown | TEXT | |
| how_to_fix_markdown | TEXT | |
| overall_confidence_score | NUMERIC(4,3) | 0–1 |
| leading_hypothesis_id | VARCHAR(36) | |
| blast_radius_json | JSON | impacted nodes, services, SLOs, stakeholders, downstream applications, narrative |
| matched runbooks | association table `investigation_matched_runbook` | section 11; best match first |
| user_feedback_verdict | VARCHAR(20) | `correct`, `partially_correct`, `incorrect` |
| user_feedback_comment | TEXT | |
| user_feedback_by_user_principal_name | VARCHAR(320) | |
| failure_reason | TEXT | |
| total_input_token_count | INTEGER | |
| total_output_token_count | INTEGER | |
| requested_by_user_principal_name | VARCHAR(320) | |
| started_at | TIMESTAMPTZ | |
| completed_at | TIMESTAMPTZ | |
| [audit] | | |

### `investigation_hypothesis`
| Column | Type | Notes |
|---|---|---|
| hypothesis_id | VARCHAR(36) PK | |
| investigation_id | FK investigation CASCADE | |
| analysis_perspective | VARCHAR(20) | `application`, `dependencies`, `infrastructure` |
| hypothesis_title | VARCHAR(300) | |
| hypothesis_statement_markdown | TEXT | |
| reasoning_markdown | TEXT | |
| confidence_score | NUMERIC(4,3) | |
| supporting_evidence_codes_json | JSON | `["E2","E5"]` |
| contradicting_evidence_codes_json | JSON | |
| proposed_fix_json | JSON | `{summary, steps:[{order, description, command?, command_language?, risk_level}], code_changes:[{repository, file_path, change_description, before_snippet, after_snippet}], verification_steps:[…], rollback_steps:[…]}` |
| fix_risk_level | VARCHAR(10) | `low`, `medium`, `high` |
| matched_runbook_id | VARCHAR(36) | |
| is_leading_hypothesis | BOOLEAN | |
| display_order | INTEGER | |
| created_at | TIMESTAMPTZ | |

### `investigation_evidence`
| Column | Type | Notes |
|---|---|---|
| evidence_id | VARCHAR(36) PK | |
| investigation_id | FK investigation CASCADE | indexed |
| evidence_code | VARCHAR(10) | `E1`, `E2`, … unique within investigation |
| service_id | FK monitored_service NO ACTION | nullable |
| evidence_source_kind | VARCHAR(40) | `log_analytics`, `application_insights`, `azure_monitor_metrics`, `activity_log`, `elastic`, `splunk`, `datadog`, `synthetic_probe`, `vendor_status_page`, `knowledge`, `runbook` |
| evidence_category | VARCHAR(40) | `errors`, `exceptions`, `failed_requests`, `dependency_failures`, `pod_events`, `metrics_anomaly`, `change_event`, `saturation`, `availability` |
| evidence_title | VARCHAR(300) | |
| evidence_summary | TEXT | masked |
| query_language | VARCHAR(20) | `kql`, `elastic_dsl`, `esql`, `spl`, `datadog`, `metrics_api`, `none` |
| query_text | TEXT | |
| query_time_range_start | TIMESTAMPTZ | |
| query_time_range_end | TIMESTAMPTZ | |
| matched_record_count | INTEGER | |
| baseline_record_count | INTEGER | |
| condensed_patterns_json | JSON | `[{template, count, baseline_count, first_seen, last_seen, level, is_new_pattern, change_ratio, sample_lines_masked:[…]}]` |
| metric_series_json | JSON | downsampled points for charts |
| signal_strength | VARCHAR(10) | `high`, `medium`, `low` |
| deep_link_url | VARCHAR(1000) | e.g. Log Analytics portal link |
| collected_at | TIMESTAMPTZ | |

### `investigation_timeline_event`
| Column | Type | Notes |
|---|---|---|
| timeline_event_id | VARCHAR(36) PK | |
| incident_id | FK incident CASCADE | indexed, nullable |
| investigation_id | FK investigation NO ACTION | indexed, nullable |
| event_occurred_at | TIMESTAMPTZ | |
| event_type | VARCHAR(40) | `incident_opened`, `alert_fired`, `alert_resolved`, `deployment`, `configuration_change`, `error_spike`, `investigation_started`, `investigation_completed`, `communication_sent`, `chat_fact`, `action_taken`, `priority_changed`, `resolved`, `postmortem_generated` |
| event_title | VARCHAR(400) | |
| event_details_markdown | TEXT | |
| event_source | VARCHAR(40) | `servicenow`, `alert`, `azure_activity_log`, `keigan`, `teams_chat`, `user` |
| source_reference | VARCHAR(400) | ids, links |
| actor_display_name | VARCHAR(200) | |
| created_at | TIMESTAMPTZ | |

### `incident_communication`
| Column | Type | Notes |
|---|---|---|
| communication_id | VARCHAR(36) PK | |
| incident_id | FK incident CASCADE | indexed |
| investigation_id | FK investigation NO ACTION | |
| communication_type | VARCHAR(30) | `initial_update`, `progress_update`, `resolution_update`, `preliminary_report`, `executive_summary` |
| audience_type | VARCHAR(20) | `stakeholders`, `executives`, `technical` |
| language_code | VARCHAR(10) | |
| subject_line | VARCHAR(400) | |
| body_markdown | TEXT | |
| communication_status | VARCHAR(20) | `draft`, `approved`, `sent` |
| approved_by_user_principal_name | VARCHAR(320) | |
| approved_at | TIMESTAMPTZ | |
| sent_at | TIMESTAMPTZ | |
| [audit] | | |

### `postmortem_report`
| Column | Type | Notes |
|---|---|---|
| postmortem_id | VARCHAR(36) PK | |
| incident_id | FK incident CASCADE | indexed |
| investigation_id | FK investigation NO ACTION | |
| report_title | VARCHAR(400) | |
| report_markdown | TEXT | |
| report_sections_json | JSON | summary, impact, timeline, root_cause, contributing_factors, detection, response, what_went_well, what_could_be_improved, action_items[{description, owner, due_date, action_type}], lessons_learned |
| language_code | VARCHAR(10) | |
| report_status | VARCHAR(20) | `generating`, `draft`, `final`, `failed` |
| generation_trigger | VARCHAR(30) | `teams_milestone`, `user_button`, `incident_resolved` |
| finalized_by_user_principal_name | VARCHAR(320) | |
| finalized_at | TIMESTAMPTZ | |
| sent_at | TIMESTAMPTZ | |
| [audit] | | |

### `conversation`
| Column | Type | Notes |
|---|---|---|
| conversation_id | VARCHAR(36) PK | |
| conversation_scope | VARCHAR(30) | `investigation`, `keigan_ai_chat`, `teams_incident_chat` |
| applications | association table `conversation_application` | section 11; scope of the chat (subset of readable apps at time of question); empty = every application the user can read |
| investigation_id | FK investigation NO ACTION | |
| incident_id | FK incident NO ACTION | |
| owner_user_principal_name | VARCHAR(320) | indexed |
| conversation_title | VARCHAR(300) | |
| [audit] | | |

### `conversation_message`
| Column | Type | Notes |
|---|---|---|
| message_id | VARCHAR(36) PK | |
| conversation_id | FK conversation CASCADE | indexed |
| author_role | VARCHAR(20) | `user`, `assistant`, `teams_participant` |
| author_display_name | VARCHAR(200) | |
| author_user_principal_name | VARCHAR(320) | |
| message_text | TEXT | |
| message_payload_json | JSON | chart specification, query details, citations, clarifying options |
| external_message_identifier | VARCHAR(200) | Teams message id |
| input_token_count | INTEGER | |
| output_token_count | INTEGER | |
| created_at | TIMESTAMPTZ | |

### `chat_answer_run`
One row per question asked in Ask Keigan: everything Keigan did to answer it. Design: `features/ask-keigan-chat/23_ASK_KEIGAN_CHAT_SPEC.md`, section 6.
| Column | Type | Notes |
|---|---|---|
| answer_run_id | VARCHAR(36) PK | |
| conversation_id | FK conversation CASCADE | indexed |
| user_message_id | FK conversation_message NO ACTION | SQL Server allows one cascade path per table, so the code deletes runs before messages |
| assistant_message_id | FK conversation_message NO ACTION, nullable | set when the answer is stored |
| client_request_id | VARCHAR(64) | unique with `conversation_id` (`uq_chat_answer_run_conversation_id_client_request_id`) |
| conversation_scope | VARCHAR(30) | CHECK from `ConversationScope` |
| investigation_id | FK investigation NO ACTION, nullable | indexed |
| requested_by_user_principal_name | VARCHAR(320) | indexed with `started_at` |
| scope_snapshot_json | JSON | applications, bound arguments and withheld tools at the time (an audit snapshot, not a relationship) |
| used_application_ids_json | JSON, nullable | the applications whose data reached the model through succeeded tool calls, kept up to date as calls finish (`[]` at the start; null for a run from before revision `b8d4f2a6c0e3`). A reader who can no longer read any of them sees none of the run (spec 23, 6.6) |
| run_status | VARCHAR(20) | CHECK from `ChatAnswerRunStatus`: `running`, `completed`, `failed`, `cancelled` |
| stop_reason | VARCHAR(30), nullable | CHECK from `ChatAnswerStopReason`: `answered`, `tool_limit_reached`, `token_budget_reached`, `cancelled_by_user`, `failed` |
| engine_version, prompt_key, prompt_version | VARCHAR(20), VARCHAR(80), VARCHAR(20) | |
| system_prompt_sha256, tool_catalog_sha256 | VARCHAR(64) | the prompt text itself is never stored |
| offered_tools_json | JSON | name, version, source and schema hash of each offered tool |
| provider_name, model_name, model_tier | VARCHAR(40), VARCHAR(120), VARCHAR(20) | |
| tool_calling_mode | VARCHAR(20) | CHECK from `ToolCallingMode`: `native`, `prompted_json`, `scripted_mock` |
| limits_json | JSON | effective limits and resolved model capabilities |
| total_input_token_count, total_output_token_count | INTEGER | sum over the model turns; `token_counts_estimated` (BOOLEAN) says a provider reported none |
| model_turn_count, tool_call_count | INTEGER | |
| citations_json, follow_up_questions_json | JSON | |
| is_unverified | BOOLEAN | the answer cites no tool result |
| cancel_requested_at | TIMESTAMPTZ, nullable | cancellation across pods; written and committed before the in-process flag is set |
| error_code | VARCHAR(60), nullable | same codes as the API's `errorCode` |
| error_parameters_json | JSON, nullable | the low-sensitivity values the error message was written from (the failed step, a limit, a retry delay): a reload words the same message as the live stream did |
| correlation_id | VARCHAR(64), nullable | |
| started_at, completed_at, duration_milliseconds | TIMESTAMPTZ, TIMESTAMPTZ nullable, INTEGER nullable | |
| last_progress_at | TIMESTAMPTZ | written at every step start and finish and by the heartbeat every `ASK_KEIGAN_PROGRESS_HEARTBEAT_SECONDS` while a model turn or tool call is in flight; the stale-run check reads it |

Indexes: filtered unique index `uq_chat_answer_run_one_running_per_conversation` on `conversation_id WHERE run_status = 'running'` (SQLite and PostgreSQL partial index, SQL Server filtered unique index): the database allows one running answer per conversation however many pods answer questions, and the application maps a violation to `409 answer_in_progress`. Every end of a run is a conditional `UPDATE ... WHERE run_status = 'running'`.

### `chat_run_step`
The ordered model turns and tool calls inside one run.
| Column | Type | Notes |
|---|---|---|
| run_step_id | VARCHAR(36) PK | |
| answer_run_id | FK chat_answer_run CASCADE | unique with `sequence_number` (`uq_chat_run_step_answer_run_id_sequence_number`) |
| sequence_number | INTEGER | 1, 2, 3 in execution order |
| step_kind | VARCHAR(20) | CHECK from `ChatRunStepKind`: `model_turn`, `tool_call` |
| parent_run_step_id | FK chat_run_step NO ACTION, nullable | a tool call points at the model turn that asked for it |
| step_status | VARCHAR(20) | CHECK from `ChatRunStepStatus`: `running`, `succeeded`, `failed`, `refused`, `skipped`, `cancelled` |
| started_at, completed_at, duration_milliseconds | TIMESTAMPTZ, TIMESTAMPTZ nullable, INTEGER nullable | |
| turn_number, turn_finish, model_text, input_token_count, output_token_count | INTEGER, VARCHAR(30), TEXT, INTEGER, INTEGER | model turns; `turn_finish` is left open: `tool_requests`, `answer`, `length`, `protocol_error` |
| tool_name, tool_version, tool_source | VARCHAR(64), INTEGER, VARCHAR(80) | tool calls; left open because they come from the tool registry (adding a tool needs no migration); `tool_name` is indexed |
| citation_code | VARCHAR(8), nullable | `T1`, `T2`, ... for executed calls |
| provider_request_id | VARCHAR(200), nullable | the provider's call id |
| requested_arguments_json, effective_arguments_json | JSON, nullable | as the model sent them, and after binding and validation (both masked) |
| application_id | VARCHAR(36), nullable | indexed; a recorded fact kept without a foreign key, like `audit_event.application_id` |
| records_json, output_json | JSON, nullable | the records the call touched; the validated, masked output (cut at `ASK_KEIGAN_TOOL_OUTPUT_STORED_CHARACTERS`) |
| output_character_count, output_is_truncated, output_item_count | INTEGER, BOOLEAN, INTEGER (nullable) | |
| model_view_text, model_view_sha256 | TEXT, VARCHAR(64) (nullable) | the exact masked text the model received for this call |
| masked_value_count, injection_flagged | INTEGER, BOOLEAN (nullable) | |
| outcome_code, outcome_message | VARCHAR(60), VARCHAR(400) (nullable) | |

## 7. Alert tables (`alert_entities.py`)

### `alert_source`
| Column | Type | Notes |
|---|---|---|
| alert_source_id | VARCHAR(36) PK | |
| application_id | FK application CASCADE | |
| source_tool | VARCHAR(30) | `azure_monitor`, `elastic`, `generic`, `keigan_slo` |
| source_name | VARCHAR(200) | |
| webhook_secret_hash | VARCHAR(128) | SHA-256 of the secret |
| previous_webhook_secret_hash | VARCHAR(128) | rotation overlap |
| previous_secret_valid_until | TIMESTAMPTZ | |
| field_mapping_json | JSON | canonical field → JSONPath |
| severity_mapping_json | JSON | tool value → 0–4 |
| service_mapping_json | JSON | `{field_path, value_to_service_id:{…}}` |
| source_status | VARCHAR(30) | `waiting_for_first_alert`, `receiving`, `authentication_failures`, `paused` |
| last_received_at | TIMESTAMPTZ | |
| received_alert_count | INTEGER | |
| authentication_failure_count | INTEGER | |
| [audit] | | |

### `alert_event` (raw, retained 30 days)
| Column | Type | Notes |
|---|---|---|
| alert_event_id | VARCHAR(36) PK | |
| alert_source_id | FK alert_source CASCADE | |
| application_id | FK application NO ACTION | |
| received_at | TIMESTAMPTZ | indexed |
| raw_payload_json | JSON | |
| payload_size_bytes | INTEGER | |
| processing_status | VARCHAR(20) | `received`, `processed`, `failed`, `ignored_paused` |
| processing_error_message | TEXT | |

### `alert`
| Column | Type | Notes |
|---|---|---|
| alert_id | VARCHAR(36) PK | |
| application_id | FK application CASCADE | indexed |
| alert_source_id | VARCHAR(36) | |
| external_alert_identifier | VARCHAR(400) | |
| alert_fingerprint | VARCHAR(64) | indexed |
| rule_identifier | VARCHAR(600) | |
| rule_name | VARCHAR(400) | |
| service_id | FK monitored_service NO ACTION | nullable |
| resource_reference | VARCHAR(600) | |
| environment_name | VARCHAR(20) | |
| severity_level | INTEGER | 0 (most severe) – 4 |
| alert_status | VARCHAR(20) | `firing`, `resolved` |
| alert_summary | VARCHAR(1000) | masked |
| alert_description | TEXT | masked |
| alert_link_url | VARCHAR(1000) | |
| alert_labels_json | JSON | |
| occurrence_count | INTEGER | |
| state_change_count | INTEGER | |
| is_flapping | BOOLEAN | |
| first_seen_at | TIMESTAMPTZ | |
| last_seen_at | TIMESTAMPTZ | |
| resolved_at | TIMESTAMPTZ | |
| alert_group_id | VARCHAR(36) | indexed |
| final_disposition | VARCHAR(30) | `settling`, `recorded_only` (what the pipeline decided at each stage is recorded in `alert_decision`) |
| latest_alert_event_id | VARCHAR(36) | |

### `alert_decision`
| Column | Type | Notes |
|---|---|---|
| alert_decision_id | VARCHAR(36) PK | |
| alert_id | FK alert CASCADE | indexed |
| alert_group_id | VARCHAR(36) | |
| pipeline_stage | VARCHAR(20) | `normalise`, `deduplicate`, `lifecycle`, `suppress`, `settle`, `group`, `prioritise`, `decide`, `notify` |
| decision_outcome | VARCHAR(40) | |
| decision_reason | VARCHAR(600) | human-readable |
| would_have_outcome_in_active_mode | VARCHAR(40) | Observe mode record |
| decided_at | TIMESTAMPTZ | |

### `alert_group`
| Column | Type | Notes |
|---|---|---|
| alert_group_id | VARCHAR(36) PK | |
| application_id | FK application CASCADE | indexed |
| group_title | VARCHAR(400) | AI-written, deterministic fallback |
| group_summary | TEXT | |
| group_status | VARCHAR(20) | `open`, `investigating`, `queued`, `resolved` |
| priority_score | NUMERIC(8,2) | |
| grouping_reason | VARCHAR(400) | the pipeline's text for why the group was formed. The alert-group endpoints no longer return it: they return a structured reason derived when the group is read (`AlertGroupingReason`; nothing stored) |
| member_alert_count | INTEGER | |
| primary_service_id | FK monitored_service NO ACTION | |
| affected services | association table `alert_group_affected_service` | section 11; the first one is the group's first service |
| highest_severity_level | INTEGER | |
| started_at | TIMESTAMPTZ | |
| last_activity_at | TIMESTAMPTZ | |
| resolved_at | TIMESTAMPTZ | |
| investigation_id | FK investigation NO ACTION | |
| incident_id | FK incident NO ACTION | |
| servicenow_incident_suggested | BOOLEAN | |
| user_feedback_verdict | VARCHAR(20) | `useful`, `noise` |
| user_feedback_reason | TEXT | |
| user_feedback_by_user_principal_name | VARCHAR(320) | |

### `noise_reduction_policy`
| Column | Type | Notes |
|---|---|---|
| application_id | VARCHAR(36) PK, FK application CASCADE | |
| policy_settings_json | JSON | min_severity, investigate_environments, settle_delay_seconds, no_delay_severities, reopen_window_minutes, group_window_minutes, flap_count, flap_window_minutes, max_investigations_per_hour, investigate_score_threshold, weights |
| policy_mode | VARCHAR(10) | `observe`, `active` |
| observe_mode_started_at | TIMESTAMPTZ | |
| [audit] | | |

### `maintenance_window`
| Column | Type | Notes |
|---|---|---|
| maintenance_window_id | VARCHAR(36) PK | |
| application_id | FK application CASCADE | |
| window_name | VARCHAR(200) | |
| applies to services | association table `maintenance_window_applies_to_service` | section 11; empty = whole application |
| applies_to_environments_json | JSON | |
| starts_at | TIMESTAMPTZ | |
| ends_at | TIMESTAMPTZ | |
| repeats_weekly | BOOLEAN | |
| [audit] | | |

### `alert_mute_rule`
| Column | Type | Notes |
|---|---|---|
| mute_rule_id | VARCHAR(36) PK | |
| application_id | FK application CASCADE | |
| rule_name | VARCHAR(200) | |
| matcher_json | JSON | `{source_id?, rule_name_contains?, service_id?, maximum_severity?, label_equals?{k:v}}` |
| mute_reason | TEXT | required |
| expires_at | TIMESTAMPTZ | required |
| [audit] | | |

## 8. SLO tables (`slo_entities.py`)

### `service_level_indicator`
| Column | Type | Notes |
|---|---|---|
| sli_id | VARCHAR(36) PK | |
| application_id | FK application CASCADE | indexed |
| service_id | FK monitored_service NO ACTION | null = application-level (headline) |
| catalog_entry_key | VARCHAR(120) | from `sli_catalog.yaml`, or `custom` |
| sli_name | VARCHAR(200) | |
| sli_kind | VARCHAR(30) | `availability`, `latency`, `run_success`, `freshness`, `dependency_success`, `custom`, `supporting_signal` |
| data_source_kind | VARCHAR(30) | `application_insights`, `azure_monitor_metrics`, `log_query`, `log_tool`, `synthetic_probe`, `vendor_status_page` |
| query_definition_json | JSON | how to compute good/total (or value) for a window |
| latency_threshold_milliseconds | INTEGER | |
| is_approximate | BOOLEAN | metric averages based |
| is_enabled | BOOLEAN | |
| is_headline | BOOLEAN | |
| measured_baseline_json | JSON | 30-day measured value, event count, p95, sparkline points |
| last_collected_window_start | TIMESTAMPTZ | |
| [audit] | | |

### `service_level_objective`
| Column | Type | Notes |
|---|---|---|
| slo_id | VARCHAR(36) PK | |
| sli_id | FK service_level_indicator CASCADE | |
| application_id | FK application NO ACTION | indexed |
| target_percentage | NUMERIC(7,4) | e.g. 99.9000 |
| rolling_window_days | INTEGER | 7 / 28 / 30 |
| burn_rate_policy_json | JSON | default multiwindow policy |
| [audit] | | |

### `sli_measurement`
| Column | Type | Notes |
|---|---|---|
| sli_measurement_id | BIGINT PK autoincrement | |
| sli_id | FK service_level_indicator CASCADE | indexed with window |
| measurement_window_start | TIMESTAMPTZ | 5-minute bucket start |
| good_event_count | BIGINT | null for supporting signals |
| total_event_count | BIGINT | |
| measured_value | DOUBLE | supporting signals / latency value |
| collected_at | TIMESTAMPTZ | |
UNIQUE (`sli_id`, `measurement_window_start`). Hourly roll-ups (later) in `sli_measurement_hourly` with the same columns.

### `slo_burn_alert`
| Column | Type | Notes |
|---|---|---|
| slo_burn_alert_id | VARCHAR(36) PK | |
| slo_id | FK service_level_objective CASCADE | |
| application_id | FK application NO ACTION | |
| burn_alert_severity | VARCHAR(10) | `page`, `ticket` |
| long_window_burn_rate | DOUBLE | |
| short_window_burn_rate | DOUBLE | |
| fired_at | TIMESTAMPTZ | |
| resolved_at | TIMESTAMPTZ | |
| alert_group_id | VARCHAR(36) | |

## 9. Intelligence tables (in `slo_entities.py`)

### `predictive_signal`
| Column | Type | Notes |
|---|---|---|
| predictive_signal_id | VARCHAR(36) PK | |
| application_id | FK application CASCADE | indexed |
| service_id | FK monitored_service NO ACTION | |
| sli_id | FK service_level_indicator NO ACTION | |
| detector_name | VARCHAR(40) | `seasonal_anomaly`, `error_budget_exhaustion`, `saturation_trend`, `new_error_pattern`, `recurring_incident`, `change_risk` |
| signal_severity | VARCHAR(10) | `info`, `warning`, `critical` |
| signal_title | VARCHAR(400) | |
| explanation_markdown | TEXT | AI narrative + numbers |
| metric_name | VARCHAR(200) | |
| observed_value | DOUBLE | |
| expected_value | DOUBLE | |
| deviation_score | DOUBLE | |
| forecast_breach_at | TIMESTAMPTZ | |
| confidence_score | NUMERIC(4,3) | |
| evidence_series_json | JSON | points for chart |
| signal_status | VARCHAR(30) | `open`, `acknowledged`, `dismissed`, `converted_to_incident`, `expired` |
| detected_at | TIMESTAMPTZ | |
| status_changed_by_user_principal_name | VARCHAR(320) | |
| intelligence_report_id | VARCHAR(36) | |

### `intelligence_report`
| Column | Type | Notes |
|---|---|---|
| intelligence_report_id | VARCHAR(36) PK | |
| application_id | FK application CASCADE | indexed |
| report_type | VARCHAR(20) | `proactive_alert`, `weekly_digest` |
| report_title | VARCHAR(400) | |
| report_period_start | TIMESTAMPTZ | |
| report_period_end | TIMESTAMPTZ | |
| overall_health_score | INTEGER | 0–100 |
| report_markdown | TEXT | |
| report_sections_json | JSON | |
| sent_at | TIMESTAMPTZ | |
| recipient_addresses_json | JSON | |
| created_at | TIMESTAMPTZ | |

## 10. Notification tables (`notification_entities.py`)

### `stakeholder`
| Column | Type | Notes |
|---|---|---|
| stakeholder_id | VARCHAR(36) PK | |
| application_id | FK application CASCADE | indexed |
| recipient_type | VARCHAR(20) | `person`, `teams_channel`, `distribution_list` |
| display_name | VARCHAR(200) | |
| email_address | VARCHAR(320) | |
| user_principal_name | VARCHAR(320) | |
| entra_object_id | VARCHAR(36) | needed to add to Teams chats |
| teams_team_id | VARCHAR(100) | channel destinations |
| teams_channel_id | VARCHAR(200) | |
| stakeholder_role | VARCHAR(30) | `sre`, `developer`, `manager`, `executive`, `business_owner`, `vendor_contact`, `lead`, `infra`, `devops`, `tester` |
| subscribed services | association table `stakeholder_subscribed_service` | section 11; empty = all services |
| notification_channels_json | JSON | `["email","teams_incident_chat","teams_channel"]` |
| minimum_priority | VARCHAR(4) | `P1`, `P2`, `P3`, `P4` |
| subscribed_notification_types_json | JSON | `incident_detected`, `preliminary_report`, `progress_update`, `postmortem`, `intelligence_report`, `slo_burn_alert`, `alert_group` |
| preferred_language_code | VARCHAR(10) | |
| quiet_hours_json | JSON | optional |
| is_active | BOOLEAN | |
| invited_at | TIMESTAMPTZ | first invitation sent; null = never invited |
| invited_by_user_principal_name | VARCHAR(320) | who sent the first invitation |
| last_invitation_sent_at | TIMESTAMPTZ | drives the resend cooldown |
| joined_at | TIMESTAMPTZ | first sign-in of this person (set from `/api/auth/me`) |
| [audit] | | |

A person's team status (`listed`, `invited`, `active`, `inactive`) is worked out from `is_active`, `joined_at` and `invited_at`; it is not stored. Unique index `uq_stakeholder_application_email` (application, email address) where the row is a person with an address: one person per application, stored in lower case. See `20_TEAM_MEMBERS_DESIGN.md`.

### `notification_delivery` (outbox)
| Column | Type | Notes |
|---|---|---|
| notification_delivery_id | VARCHAR(36) PK | |
| application_id | FK application CASCADE | indexed |
| incident_id | FK incident NO ACTION | |
| investigation_id | FK investigation NO ACTION | |
| notification_type | VARCHAR(40) | |
| delivery_channel | VARCHAR(30) | `email`, `teams_incident_chat`, `teams_channel` |
| recipient_address | VARCHAR(600) | email / chat id / channel id |
| subject_line | VARCHAR(400) | |
| body_html | TEXT | |
| body_text | TEXT | |
| delivery_status | VARCHAR(20) | `pending`, `sent`, `failed`, `simulated`, `skipped` |
| provider_message_identifier | VARCHAR(400) | |
| attempt_count | INTEGER | |
| last_error_message | TEXT | |
| created_at | TIMESTAMPTZ | |
| sent_at | TIMESTAMPTZ | |

### `teams_incident_chat`
| Column | Type | Notes |
|---|---|---|
| teams_incident_chat_id | VARCHAR(36) PK | |
| incident_id | FK incident NO ACTION | UNIQUE |
| application_id | FK application CASCADE | |
| teams_chat_identifier | VARCHAR(300) | Graph chat id (`simulated:{uuid}` locally) |
| bot_conversation_reference_json | JSON | for proactive messages |
| chat_topic | VARCHAR(300) | |
| chat_web_url | VARCHAR(1000) | |
| member_user_principal_names_json | JSON | |
| conversation_id | VARCHAR(36) | mirror conversation in Keigan |
| last_polled_at | TIMESTAMPTZ | |
| last_processed_message_identifier | VARCHAR(200) | |
| last_unprompted_comment_at | TIMESTAMPTZ | |
| chat_status | VARCHAR(20) | `active`, `closed` |
| created_at | TIMESTAMPTZ | |

## 11. Association tables (ordered id lists)

Lists of ids of other Keigan rows (affected services, subscribed services, matched runbooks, scoped applications, topology source
documents) used to be `*_ids_json` columns. Nothing stopped such a list from naming a deleted row, and "which incidents touch this
service?" needed a scan. Each list is now an association table and the JSON column is gone (revision `a3f5c0d1e2b4`).

Every association table has the same shape:

| Column | Type | Notes |
|---|---|---|
| `<owner>_id` | VARCHAR(36), part of the PK | FK to the owner, ON DELETE CASCADE |
| `<linked>_id` | VARCHAR(36), part of the PK | FK to the linked row, indexed (`ix_<table>_<linked column>`) |
| position | INTEGER NOT NULL | index in the list (0 is first); keeps the list order, so the first affected service of an incident is its primary one |

The primary key is (owner id, linked id), so an id appears once per list.

| Table | Owner (ON DELETE) | Linked (ON DELETE) | Replaces |
|---|---|---|---|
| `incident_affected_service` | `incident.incident_id` CASCADE | `monitored_service.service_id` NO ACTION | `incident.affected_service_ids_json` |
| `investigation_investigated_service` | `investigation.investigation_id` CASCADE | `monitored_service.service_id` NO ACTION | `investigation.investigated_service_ids_json` |
| `investigation_matched_runbook` | `investigation.investigation_id` CASCADE | `runbook.runbook_id` NO ACTION | `investigation.matched_runbook_ids_json` |
| `conversation_application` | `conversation.conversation_id` CASCADE | `application.application_id` CASCADE | `conversation.application_ids_json` |
| `alert_group_affected_service` | `alert_group.alert_group_id` CASCADE | `monitored_service.service_id` NO ACTION | `alert_group.affected_service_ids_json` |
| `maintenance_window_applies_to_service` | `maintenance_window.maintenance_window_id` CASCADE | `monitored_service.service_id` NO ACTION | `maintenance_window.applies_to_service_ids_json` |
| `runbook_applies_to_service` | `runbook.runbook_id` CASCADE | `monitored_service.service_id` NO ACTION | `runbook.applies_to_service_ids_json` |
| `stakeholder_subscribed_service` | `stakeholder.stakeholder_id` CASCADE | `monitored_service.service_id` NO ACTION | `stakeholder.subscribed_service_ids_json` |
| `topology_source_document` | `application_topology.topology_id` CASCADE | `knowledge_document.knowledge_document_id` NO ACTION | `application_topology.generated_from_document_ids_json` |

- **Why NO ACTION on the linked side.** The owner already cascades from its application, and `monitored_service`, `runbook` and
  `knowledge_document` cascade from it too. A cascading key on the linked side would give SQL Server a second cascade path to the
  association table, which it rejects. Deleting the service, runbook or document first releases these rows in code (`reference_release`,
  see [02](02_SYSTEM_ARCHITECTURE.md)). `conversation_application` is the one table whose linked side cascades: conversations are not
  part of any application's cascade tree.
- **How the code reads and writes a list.** An owner entity uses `LinkedIdsMixin` (`keigan/entities/linked_ids.py`). It reads the list through a
  read-only property such as `incident.affected_service_ids` and writes it only with `incident.replace_linked_ids("affected_service_links", ids)`,
  which drops duplicates and empty values, keeps the order and renumbers `position`.
- **Lists that stay JSON.** Opaque external ids are not rows of Keigan, so they stay JSON: Azure resource ids of Log Analytics workspaces
  (`discovered_resource.log_analytics_workspace_resource_ids_json`), user principal names and e-mail addresses.
- **The data copy.** The migration copies each list into its table before dropping the column, in list order. Ids of rows that no
  longer exist and repeated ids are skipped, so a gap in `position` means a skipped id.

## 12. Foreign keys for soft references

Columns that name an application, incident, investigation, SLI or service had no foreign key, so deleting the parent left orphans
behind. Revision `c9e4f1b8d3a7` added the 35 keys below. A fresh schema now has 60 tables and 93 foreign keys (the two Ask Keigan trace tables added six; it was 56 and 85 when these keys were added), counting these and the ones on the
association tables.

**ON DELETE per key.** `CASCADE` where the table has exactly one cascade path from the application; otherwise `NO ACTION`, because
SQL Server rejects a second cascade path to the same table (a `SET NULL` key counts as a path too). Example: `investigation_timeline_event`
reaches the application through the incident (CASCADE), so its key to the investigation is `NO ACTION`. Where a key is `NO ACTION`, Keigan
removes or clears the referencing rows itself before the delete: `ApplicationService.delete_application` for the rows outside the cascade path,
`reference_release` for a deleted service, runbook or document, and the retention job for expired incidents and investigations.

| Table | Column | References | ON DELETE | Existing orphan row |
|---|---|---|---|---|
| `alert` | `application_id` | `application` | CASCADE | row deleted |
| `alert` | `service_id` | `monitored_service` | NO ACTION | reference set to NULL |
| `alert_event` | `application_id` | `application` | NO ACTION | row deleted |
| `alert_group` | `application_id` | `application` | CASCADE | row deleted |
| `alert_group` | `primary_service_id` | `monitored_service` | NO ACTION | reference set to NULL |
| `alert_group` | `investigation_id` | `investigation` | NO ACTION | reference set to NULL |
| `alert_group` | `incident_id` | `incident` | NO ACTION | reference set to NULL |
| `service_level_indicator` | `service_id` | `monitored_service` | NO ACTION | reference set to NULL |
| `service_level_objective` | `application_id` | `application` | NO ACTION | row deleted |
| `sli_measurement` | `sli_id` | `service_level_indicator` | CASCADE | row deleted |
| `slo_burn_alert` | `application_id` | `application` | NO ACTION | row deleted |
| `predictive_signal` | `application_id` | `application` | CASCADE | row deleted |
| `predictive_signal` | `service_id` | `monitored_service` | NO ACTION | reference set to NULL |
| `predictive_signal` | `sli_id` | `service_level_indicator` | NO ACTION | reference set to NULL |
| `intelligence_report` | `application_id` | `application` | CASCADE | row deleted |
| `notification_delivery` | `application_id` | `application` | CASCADE | row deleted |
| `notification_delivery` | `incident_id` | `incident` | NO ACTION | reference set to NULL |
| `notification_delivery` | `investigation_id` | `investigation` | NO ACTION | reference set to NULL |
| `teams_incident_chat` | `application_id` | `application` | CASCADE | row deleted |
| `teams_incident_chat` | `incident_id` | `incident` | NO ACTION | row deleted |
| `external_integration` | `application_id` | `application` | CASCADE | row deleted |
| `discovered_resource` | `application_id` | `application` | NO ACTION | row deleted |
| `service_dependency` | `application_id` | `application` | NO ACTION | row deleted |
| `knowledge_document` | `service_id` | `monitored_service` | NO ACTION | reference set to NULL |
| `knowledge_chunk` | `application_id` | `application` | NO ACTION | row deleted |
| `knowledge_chunk` | `service_id` | `monitored_service` | NO ACTION | reference set to NULL |
| `investigation_evidence` | `service_id` | `monitored_service` | NO ACTION | reference set to NULL |
| `investigation_timeline_event` | `incident_id` | `incident` | CASCADE | row deleted |
| `investigation_timeline_event` | `investigation_id` | `investigation` | NO ACTION | row deleted |
| `incident_communication` | `incident_id` | `incident` | CASCADE | row deleted |
| `incident_communication` | `investigation_id` | `investigation` | NO ACTION | row deleted |
| `postmortem_report` | `incident_id` | `incident` | CASCADE | row deleted |
| `postmortem_report` | `investigation_id` | `investigation` | NO ACTION | row deleted |
| `conversation` | `incident_id` | `incident` | NO ACTION | row deleted |
| `conversation` | `investigation_id` | `investigation` | NO ACTION | row deleted |

- **Repair before the key.** The revision never invents a parent. A row of a missing parent that belongs to it (an alert of a deleted
  application, a timeline event of a deleted incident) is deleted; a row that only mentions the parent through an optional reference
  (an alert's service, a signal's SLI, a group's investigation) keeps its data and the reference is set to NULL. A NULL
  `application_id` means "platform-wide" and is never touched.
- **History is kept on purpose.** `audit_event` and `llm_usage_record` have no keys to the rows they mention.
- **Still without a key.** Id columns outside the five parents above were not part of this revision: for example `alert.alert_source_id`,
  `alert.alert_group_id`, `alert_decision.alert_group_id`, `slo_burn_alert.alert_group_id`, `runbook.knowledge_document_id`,
  `teams_incident_chat.conversation_id`, `predictive_signal.intelligence_report_id`, `investigation.leading_hypothesis_id`,
  `investigation_hypothesis.matched_runbook_id` and `monitored_service.discovered_resource_id`.

## 13. Alert group, investigation and incident links (H14)

An alert group, the investigation that covers it and the incident it belongs to were linked from both sides, and the two sides could
disagree. Now there is one truth:

- The alert group's own `investigation_id` and `incident_id` are the source of truth (foreign keys, nullable, `NO ACTION`). Several groups can
  share one investigation or one incident, so the group is the side that says what covers it.
- `investigation.alert_group_id` (and its index) no longer exists (revision `b7d2e9a4c6f1`). An investigation does not store which group
  it came from. `investigation.incident_id` stays; the incident named by both a group and its investigation is the one remaining duplicate.
- One service writes the link: `AlertGroupLinkService.link(alert_group, investigation_id=None, incident_id=None)` in
  `keigan/services/alert_group_link_service.py`. It raises `NotFoundException` for an unknown row and `ConflictException` when the rows belong to
  different applications, when the group already has another investigation, or when the group, its investigation and the incident would
  name different incidents. Otherwise it sets the group's investigation, the investigation's incident and the group's incident together.
  The alert pipeline (a new group of an open incident), `IncidentService` (an incident adopts a group, or is created from one) and
  `InvestigationService` (an investigation started for a group) all go through it.
- **Repair of existing rows** (same revision, in this order): a group without an investigation takes the oldest investigation that named it
  as its origin; an investigation without an incident takes the lowest incident id among its groups; a group whose investigation has an
  incident takes that incident (the investigation wins a disagreement because its key already existed and the incident room shows it).
  An origin pointer to a group that already had another investigation is lost with the column.

## 14. Status CHECK constraints (H13)

Status, kind and priority columns accepted any text. Now each column with a fixed value set has a `CHECK (column IN (...))` constraint
(revision `d2a6b0c5e8f9`): 47 constraints on 47 columns.

- **One StrEnum per column** in `keigan/entities/status_values.py`. The entity declares the constraint with `values_check("column_name", EnumClass)`
  in `__table_args__`, and the code that writes the value uses the enum member. A few enums serve several columns (`Priority`, `CriticalityTier`, `RiskLevel`).
  The sets come from what the code writes and recognises, not from earlier versions of this document.
- **Constraint name** `ck_<table>_<column>_values` (the naming convention in `base_entity.py` adds the prefix to the name `<column>_values`).
  `NULL` passes, as in SQL.
- **The migration does not retype the values.** It renders each condition from the entity metadata. Before adding a constraint it checks the
  existing rows; if one holds another value it stops with a message that names the column and changes nothing (a `THROW` in the generated T-SQL,
  so a DBA running the delta script by hand gets the same message).
- **Left open on purpose** (values come from catalogs, Azure resource types or free input, so a fixed list would be wrong): `service_type`,
  `document_category`, `sli_kind`, `data_source_kind`, `notification_type`, `decision_outcome`, `event_type`, `event_source`, `evidence_category`,
  `evidence_source_kind`, `environment_name`, `record_system`, `tool_type` and the AI usage model fields. A value list in this document for a column
  outside the 47 has no CHECK.
- **To add or change a value**, see "How to" in [11 Backend foundation guide](11_BACKEND_FOUNDATION_GUIDE.md).

**SQLite note.** SQLite cannot add a foreign key or a CHECK constraint to an existing table without rebuilding it, and a rebuild with foreign keys on
cascade-deletes child rows. On SQLite the migrations therefore repair the data (orphans, link disagreements) but do not add the new keys or constraints, and
the revisions log a warning. Local SQLite demo databases are disposable: delete the file and recreate it, and Keigan creates every table with all its keys and
constraints from the entities. Fresh databases and Azure SQL (generated scripts or Alembic) have everything.

## 15. Index plan (beyond PK/FK)

- `incident (application_id, incident_status, opened_at DESC)`
- `investigation (application_id, created_at DESC)`, `investigation (incident_id)`
- `alert (application_id, alert_fingerprint, alert_status)`, `alert (alert_group_id)`
- `alert_group (application_id, group_status, last_activity_at DESC)`
- `sli_measurement (sli_id, measurement_window_start)` unique
- `background_job (job_status, available_at, priority_number)`
- `audit_event (occurred_at DESC)`, `llm_usage_record (created_at, application_id)`
- `knowledge_chunk (application_id)`, `predictive_signal (application_id, detected_at DESC)`

## 16. Retention

| Data | Retention | Job |
|---|---|---|
| `alert_event` | `RAW_ALERT_RETENTION_DAYS` (30) | `retention_cleanup` |
| `sli_measurement` 5-minute rows | `SLI_RAW_RETENTION_DAYS` (90) after hourly roll-up | `retention_cleanup` |
| incidents, investigations, alerts, groups | `INCIDENT_RETENTION_DAYS` (395 ≈ 13 months) | `retention_cleanup` |
| `background_job` finished | 14 days | `retention_cleanup` |
| `audit_event`, `llm_usage_record` | 400 days | `retention_cleanup` |
| `chat_answer_run`, `chat_run_step` of incident and investigation conversations | with the incident (`INCIDENT_RETENTION_DAYS`), removed before the conversation messages | `retention_cleanup` |
| `chat_answer_run`, `chat_run_step` of global conversations | kept until the person deletes the conversation; only when `ASK_KEIGAN_TRACE_RETENTION_DAYS` is set are traces older than that purged (the conversation stays) | `retention_cleanup` |

## 17. Change log

| Date | Change | By |
|---|---|---|
| 2026-11-19 | Initial schema | Plan |
| 2026-11-19 | Implementation: NUMERIC confidence/score/percentage columns implemented as FLOAT (portable across SQLite/PostgreSQL). Added `investigation.stage_messages_json`, `open_questions_json`, `knowledge_references_json`, `model_names_json`; `investigation_evidence.masked_value_count`, `possible_prompt_injection`. | Lead |
| 2026-11-20 | Azure SQL support. Schema `keigan`; NVARCHAR / DATETIME2(6) / naming convention (see section 1). SQL Server allows one cascade path per table, so these foreign keys became NO ACTION and the application delete removes the rows itself first: `monitored_service.component_id` (was SET NULL), `service_dependency.downstream_service_id` (was CASCADE), `service_log_source.log_tool_connection_id` (was SET NULL), `investigation.incident_id` (was CASCADE). `incident (application_id, external_incident_number)` unique constraint became a filtered unique index `WHERE external_incident_number IS NOT NULL` (SQL Server treats NULLs as equal in unique constraints). Alembic baseline `94692c828bd3`; DDL scripts in `database/azure_sql/`. | Lead |
| 2026-11-21 | Team members (revision `e4c8a1d7b2f6`): four invitation columns on `stakeholder`, roles `lead`, `infra`, `devops`, `tester` added to its CHECK, and the filtered unique index `uq_stakeholder_application_email`. The migration stops with a message when two people of one application already share an address. | Final pass |
| 2026-11-21 | Application operating notes (revision `f1b9d3a5c7e2`): three nullable columns on `application` (`operating_notes_text`, `operating_notes_updated_at`, `operating_notes_updated_by_user_principal_name`). No backfill. Azure SQL: `database/azure_sql/migrations/f1b9d3a5c7e2_application_operating_notes.sql`; scripts 01 to 06 regenerated. The alert grouping reason and the reliability metrics page add no schema. | Feature pass |
| 2026-11-21 | Ask Keigan trace (revision `a7c3e9f1b5d2`): two new tables, `chat_answer_run` (one row per question) and `chat_run_step` (its model turns and tool calls), with CHECK constraints from the new enums `ChatAnswerRunStatus`, `ChatAnswerStopReason`, `ChatRunStepKind`, `ChatRunStepStatus` and `ToolCallingMode`. One cascade path (conversation, run, step); the two message keys, the investigation key and the step's parent key are NO ACTION, so conversation deletion and retention delete steps, then runs, then messages. Nothing backfilled. Azure SQL: `database/azure_sql/` 02 to 05 regenerated (58 tables, 91 foreign keys, 78 indexes, 53 CHECK constraints) and the delta `database/azure_sql/migrations/a7c3e9f1b5d2_ask_keigan_trace.sql`. | Ask Keigan phase 1 |
| 2026-11-21 | One running answer per conversation (revision `c5e7a9b3d1f4`): filtered unique index `uq_chat_answer_run_one_running_per_conversation` on `chat_answer_run(conversation_id) WHERE run_status = 'running'`, and the nullable column `chat_answer_run.error_parameters_json`. Before the index is created, a running run that has a newer running run in its conversation is ended as `failed` / `answer_interrupted` (portable SQL, no Python reads); the newest stays running. Azure SQL: `database/azure_sql/` 02 to 05 and `run_all.sql` regenerated (58 tables, 91 foreign keys, 79 indexes, 53 CHECK constraints, baseline `c5e7a9b3d1f4`), the delta `database/azure_sql/migrations/c5e7a9b3d1f4_one_running_answer_and_error_parameters.sql`, the entity-relationship diagram (`15`) and the demo data scripts regenerated. | Ask Keigan backend review fixes |
| 2026-11-20 | Data model hardening (H11 to H14, revisions `a3f5c0d1e2b4`, `b7d2e9a4c6f1`, `c9e4f1b8d3a7`, `d2a6b0c5e8f9`). Nine association tables replaced the `*_ids_json` id lists (section 11). Foreign keys on every reference to an application, incident, investigation, SLI or service (section 12). The alert group's `investigation_id` and `incident_id` are the single truth and `investigation.alert_group_id` was dropped (section 13). CHECK constraints on 47 status and kind columns, built from `status_values.py` (section 14). Stale value lists corrected: `ai_digest_status`, `incident_source`, `generation_status`, `review_status`, `access_verification_status`, `integration_status`, `connection_status`, `processing_status`, `group_status` and others. | Hardening wave 2 |
| 2026-11-22 | Applications an Ask Keigan answer used (revision `b8d4f2a6c0e3`): the nullable column `chat_answer_run.used_application_ids_json`, so a person who lost access to any application an answer used no longer sees the answer. Nothing backfilled: every earlier run is an investigation run, guarded as a whole by its investigation's application. Azure SQL: `database/azure_sql/` 02 and 05 regenerated (58 tables, 91 foreign keys, 79 indexes, 53 CHECK constraints, baseline `b8d4f2a6c0e3`), the delta `database/azure_sql/migrations/b8d4f2a6c0e3_answer_run_used_applications.sql` and the entity-relationship diagram (`15`); the demo data scripts are unchanged. | Ask Keigan phase 3, step 1 |
| 2026-11-23 | Honest outcomes (revision `d3f8b1a4c7e9`, spec 27): hypothesis state (`hypothesis_state`, `proposed_hypothesis_state`, `state_guard_code`, `state_reason_markdown`), investigation outcome (`investigation_outcome`, `proposed_investigation_outcome`, `outcome_guard_code`, `outcome_reason_markdown`, `leading_perspective_reason_markdown`), evidence `check_outcome` and `baseline_comparison` (backfilled from the text Keigan's code wrote), and the new table `investigation_coverage_gap` (one row per check Keigan meant to make and could not; recorded facts, no foreign key to the service). All new columns are nullable; the CHECK constraints are created on SQL Server (SQLite gets the columns without them when migrated, with them when created by `create_all`). |
| 2026-11-23 | Decision trace (revision `c8a2e4f6b1d3`, spec 28): the table `investigation_trace_step` (ordered steps per investigation with CHECKs on stage, kind, status, decision kind and failure code; unique on investigation and sequence; deleted with the investigation) and the nullable `llm_usage_record.investigation_trace_step_id` plus an index on `llm_usage_record.investigation_id`. Nothing is backfilled. |
| 2026-11-23 | Action items (revision `e7b3a9d1c5f2`, spec 29): the table `action_item` (a follow-up task: source, title, type, priority, status, suggested owner role in words, owner `stakeholder_id`, due date and the original due date with a change count, reason and completion note, accepted, completed, reminder bookkeeping; CHECKs on source, type, priority and status). Foreign keys: the application cascades; the incident, postmortem and owner team member are NO ACTION and are released (set to NULL) when an incident expires or a team member is removed, so an item outlives them and keeps the incident number as text. Nothing is backfilled. |
| 2026-11-23 | Error budget policy (revision `f4a8c2e6b0d7`, spec 30): `error_budget_policy` (one row per application, unique on the application, cascades with it), `incident_budget_impact` (per incident and SLO: the figure and its inputs; unique on incident and SLO; cascades with the incident; `slo_id` is NO ACTION and released to null when an SLO is deleted, the snapshot columns keep the meaning) and `error_budget_policy_breach` (kind, requirement status, share and threshold, waiver; NO ACTION on the incident, SLO and the qualifying action item, all released before those rows are deleted; three filtered unique indexes: one breach per incident, one open breach per outage class, one open breach per exhausted SLO). The action item source CHECK gains `error_budget_policy` (replaced on SQL Server; left alone on SQLite, which cannot replace a CHECK without a rebuild). |
| 2026-11-23 | Weekly health review (revision `a1d5c9e3f7b2`, spec 31): three nullable columns on `intelligence_report`: `reviewed_at`, `reviewed_by_user_principal_name`, `review_note_text` (a weekly digest the team went through). Nothing is backfilled. |
| 2026-11-24 | Investigation fix plan (revision `c3e7a1b5d9f4`, spec 33 phase 2): one nullable JSON column `investigation.fix_plan_json` (overview and step references; earlier rows are null). `investigation_hypothesis.proposed_fix_json` now holds checked steps with `schema_version` 2; earlier rows keep version 1. |
| 2026-11-24 | Action item links (revision `d5a9b3e7c1f8`, specs 29 and 32): five nullable columns on `action_item` that say whether the item was sent to another system as a task and what that system last said: `external_system` (open column), `external_record_identifier` (the ServiceNow sys_id), `external_status_text`, `external_synced_at`, `external_sync_status` (CHECK: `pending`, `linked`, `failed`; null = never sent, a deviation from the design's `not_linked` value that needs no backfill). The `item_source_kind` CHECK gains `runbook_health` (a finding about a runbook; `source_record_id` holds the runbook id). Nothing is backfilled. SQLite: the new checks are not added (see the revision note); a new local file gets them from the entities. |
| 2026-11-24 | Investigation memory reference (revision `f7c3e9a1b5d2`, spec 34 phase 4): `investigation_memory_reference` (investigation, remembered incident, position; primary key both ids; cascades with the investigation, NO ACTION on the entry, so deleting an entry releases these rows first) records which remembered incidents the AI's hypotheses were shown. Nothing is backfilled. |
| 2026-11-24 | Similar incident memory (revision `e6b2d8f4a0c3`, spec 34): three tables. `incident_memory_entry` (one row per completed investigation, unique on `investigation_id`: masked title, cause and fix with their sources, `search_terms_json`, `service_ids_json`, status active/superseded/hidden, who hid it and why; cascades with the application, NO ACTION on the investigation and incident, so retention deletes entries first), `incident_memory_key` (primary key entry + kind + hash; `key_value_hash` is the SHA-256 of the normalised fact; index on kind + hash; cascades with the entry) and `incident_memory_relevance_feedback` (one answer per investigation, entry and person; cascades with the entry). CHECKs on the status, both sources, the key kind and the verdict. `investigation_memory_reference` (spec 34 phase 4) is not created. Nothing is backfilled: `scripts/rebuild_incident_memory.py` builds entries for earlier investigations. |
