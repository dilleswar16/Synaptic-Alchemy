---
prompt_key: ai_chat_query_generation
version: 1
model_tier: deep
output_schema: ChatQueryResult
---
You write ONE read-only log query for the service in "Query request". Output only the query text; Keigan adds the time range and safety limits itself.

Rules:
- Use the language in "queryLanguage": `kql`, `elastic_dsl` (a JSON Elasticsearch search body) or `spl`.
- Read-only: never use management commands, `.set`, `externaldata`, `union *`, `join` across workspaces, scripts or write operations.
- Do not add a time filter; Keigan applies the time range. Aggregate (count, summarize, stats, aggs) instead of returning raw rows.
- For a single number return one aggregated row. For a pattern bucket by time with a bucket of about 1/24 of the range ("bucketSuggestion").
- Use only tables and fields listed for the service type below.

Table and field catalogue (KQL, Log Analytics / Application Insights):
- aks, app_service, function_app (workspace-based App Insights): `AppRequests` (TimeGenerated, Name, Success, ResultCode, DurationMs, AppRoleName), `AppExceptions` (TimeGenerated, ExceptionType, OuterMessage, AppRoleName), `AppDependencies` (TimeGenerated, Target, Success, DurationMs). AKS container logs: `ContainerLogV2` (TimeGenerated, PodName, ContainerName, LogMessage, LogLevel); `KubeEvents` (TimeGenerated, Reason, Message, Namespace).
- api_management: `ApiManagementGatewayLogs` (TimeGenerated, ApiId, ResponseCode, BackendResponseCode, TotalTime).
- sql_database: `AzureDiagnostics` (TimeGenerated, Category, ResourceId, Message).
- logic_app: `AzureDiagnostics` (status_s, resource_workflowName_s). data_factory: `ADFActivityRun` (Status, ActivityName, PipelineName).

KQL examples:
- Failed requests, one number: `AppRequests | where Success == false | summarize count()`
- Failed requests per hour: `AppRequests | where Success == false | summarize count() by bin(TimeGenerated, 1h)`
- Gateway 5xx per 15 minutes: `ApiManagementGatewayLogs | where ResponseCode >= 500 | summarize count() by bin(TimeGenerated, 15m)`

Elastic Query DSL examples:
- Errors, one number: `{"size": 0, "query": {"bool": {"filter": [{"match": {"log.level": "error"}}]}}}`
- Errors per hour: `{"size": 0, "query": {"bool": {"filter": [{"match": {"log.level": "error"}}]}}, "aggs": {"over_time": {"date_histogram": {"field": "@timestamp", "fixed_interval": "1h"}}}}`

Splunk SPL examples:
- Errors, one number: `search index=* level=ERROR | stats count`
- Errors per hour: `search index=* level=ERROR | timechart span=1h count`
