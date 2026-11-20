"""Validation and hardening of AI-generated telemetry queries (KQL, Elastic Query DSL, Splunk SPL).

Generated queries are untrusted. They must be read-only, single-statement, bounded in time and rows, and may
only touch allow-listed tables / indices for the data source. :func:`validate_generated_query` returns the
hardened query text or raises :class:`QueryRejectedError` with a human-readable reason.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

from keigan.exceptions.keigan_exceptions import BusinessValidationException

MAXIMUM_RESULT_ROWS = 500

DEFAULT_ALLOWED_KQL_TABLES = frozenset(
    {
        "AppRequests", "AppDependencies", "AppExceptions", "AppTraces", "AppAvailabilityResults", "AppPageViews", "AppMetrics", "AppEvents",
        "requests", "dependencies", "exceptions", "traces", "availabilityResults", "customEvents", "customMetrics",
        "ContainerLogV2", "ContainerLog", "KubeEvents", "KubePodInventory", "KubeNodeInventory", "KubeServices", "InsightsMetrics", "Perf",
        "FunctionAppLogs", "AppServiceHTTPLogs", "AppServiceConsoleLogs", "AppServiceAppLogs", "AppServicePlatformLogs",
        "ApiManagementGatewayLogs", "AzureDiagnostics", "AzureMetrics", "AzureActivity",
        "ADFPipelineRun", "ADFActivityRun", "ADFTriggerRun", "LogicAppWorkflowRuntime",
        "AzureDiagnosticsSql", "Syslog", "Event", "Heartbeat",
    }
)

_FORBIDDEN_KQL_PATTERNS = tuple(
    (re.compile(forbidden_pattern, re.IGNORECASE), reason)
    for forbidden_pattern, reason in (
        (r"^\s*\.", "management commands are not allowed"),
        (r"\bexternaldata\b", "external data is not allowed"),
        (r"\bevaluate\s+(http_request|http_request_post|python|r)\b", "plugins that call out or run code are not allowed"),
        (r"\b(cluster|database|workspace|app|resource)\s*\(", "cross-resource queries are not allowed"),
        (r"\binvoke\b", "invoking functions is not allowed"),
        (r"\bset\s+\w+\s*=", "query options are not allowed"),
        (r";\s*\S", "only one statement is allowed"),
    )
)

_FORBIDDEN_SPL_COMMANDS = ("sendemail", "outputlookup", "outputcsv", "collect", "script", "rest", "delete", "map", "sendalert", "tscollect", "mcollect", "run", "dbxquery")
_ALLOWED_ELASTIC_TOP_LEVEL_KEYS = frozenset({"query", "aggs", "aggregations", "size", "sort", "_source", "track_total_hits"})


class QueryRejectedError(BusinessValidationException):
    error_code = "query_rejected"
    title = "Keigan rejected a generated query"


@dataclass(frozen=True)
class HardenedQuery:
    query_language: str
    query_text: str
    applied_hardening: tuple[str, ...]


def _format_kql_datetime(timestamp: datetime) -> str:
    return f"datetime({timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')})"


def _strip_kql_comments_and_strings(kql_text: str) -> str:
    without_comments = re.sub(r"//[^\n]*", "", kql_text)
    return re.sub(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'", "''", without_comments)


def validate_kql(
    kql_text: str, time_range_start: datetime, time_range_end: datetime, allowed_tables: frozenset[str] = DEFAULT_ALLOWED_KQL_TABLES, time_column: str = "TimeGenerated"
) -> HardenedQuery:
    if not kql_text or len(kql_text) > 8000:
        raise QueryRejectedError("The query is empty or too long.")
    analysable_text = _strip_kql_comments_and_strings(kql_text).strip()
    for forbidden_pattern, reason in _FORBIDDEN_KQL_PATTERNS:
        if forbidden_pattern.search(analysable_text):
            raise QueryRejectedError(f"The generated query was rejected: {reason}.")

    let_statement_names = set(re.findall(r"\blet\s+(\w+)\s*=", analysable_text))
    source_expression = re.split(r"\|", re.sub(r"\blet\s+\w+\s*=[^;]*;", "", analysable_text), maxsplit=1)[0]
    referenced_tables = {
        identifier for identifier in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", source_expression)
        if identifier not in {"union", "withsource", "kind", "isfuzzy", "true", "false", "outer", "inner"} and identifier not in let_statement_names
    }
    for joined_table in re.findall(r"\b(?:join|lookup)\b[^(|]*\(\s*([A-Za-z_][A-Za-z0-9_]*)", analysable_text):
        referenced_tables.add(joined_table)
    disallowed_tables = {table_name for table_name in referenced_tables if table_name not in allowed_tables}
    if not referenced_tables or disallowed_tables:
        raise QueryRejectedError(f"The query may only read these tables: {', '.join(sorted(allowed_tables))[:400]}.")

    hardening_steps: list[str] = []
    first_pipe_index = kql_text.find("|")
    time_filter = f"| where {time_column} between ({_format_kql_datetime(time_range_start)} .. {_format_kql_datetime(time_range_end)}) "
    if first_pipe_index == -1:
        hardened_text = f"{kql_text.strip()}\n{time_filter}"
    else:
        hardened_text = f"{kql_text[:first_pipe_index].rstrip()}\n{time_filter}{kql_text[first_pipe_index:]}"
    hardening_steps.append("time range enforced")
    if not re.search(r"\|\s*(take|limit|top|summarize|count)\b", analysable_text, re.IGNORECASE):
        hardened_text = f"{hardened_text.rstrip()}\n| take {MAXIMUM_RESULT_ROWS}"
        hardening_steps.append(f"row limit {MAXIMUM_RESULT_ROWS} added")
    return HardenedQuery("kql", hardened_text.strip(), tuple(hardening_steps))


def validate_elastic_query(query_json_text: str, time_range_start: datetime, time_range_end: datetime, time_field: str = "@timestamp") -> HardenedQuery:
    try:
        query_body = json.loads(query_json_text)
    except json.JSONDecodeError as decode_error:
        raise QueryRejectedError("The Elastic query is not valid JSON.") from decode_error
    if not isinstance(query_body, dict):
        raise QueryRejectedError("The Elastic query must be a JSON object.")
    unexpected_keys = set(query_body) - _ALLOWED_ELASTIC_TOP_LEVEL_KEYS
    if unexpected_keys:
        raise QueryRejectedError(f"Unsupported Elastic query keys: {', '.join(sorted(unexpected_keys))}.")
    if "script" in query_json_text or "_update" in query_json_text or "_delete" in query_json_text:
        raise QueryRejectedError("Scripts and write operations are not allowed in Elastic queries.")
    time_range_filter = {"range": {time_field: {"gte": time_range_start.isoformat(), "lte": time_range_end.isoformat()}}}
    original_query = query_body.get("query", {"match_all": {}})
    query_body["query"] = {"bool": {"filter": [time_range_filter], "must": [original_query]}}
    query_body["size"] = min(int(query_body.get("size", 100) or 0), MAXIMUM_RESULT_ROWS)
    return HardenedQuery("elastic_dsl", json.dumps(query_body), ("time range enforced", "size bounded"))


def validate_spl(spl_text: str, time_range_start: datetime, time_range_end: datetime) -> HardenedQuery:
    normalized_text = spl_text.strip()
    if not re.match(r"^(search\b|\|\s*tstats\b)", normalized_text, re.IGNORECASE):
        normalized_text = f"search {normalized_text}"
    for spl_command in re.findall(r"\|\s*(\w+)", normalized_text):
        if spl_command.lower() in _FORBIDDEN_SPL_COMMANDS:
            raise QueryRejectedError(f"The Splunk command '{spl_command}' is not allowed.")
    time_bounds = f" earliest={int(time_range_start.timestamp())} latest={int(time_range_end.timestamp())}"
    normalized_text = re.sub(r"\b(earliest|latest)\s*=\s*\S+", "", normalized_text)
    normalized_text = re.sub(r"^(search)\b", r"\1" + time_bounds, normalized_text, count=1, flags=re.IGNORECASE)
    if not re.search(r"\|\s*(head|stats|tstats|timechart|top|chart)\b", normalized_text, re.IGNORECASE):
        normalized_text += f" | head {MAXIMUM_RESULT_ROWS}"
    return HardenedQuery("spl", normalized_text, ("time range enforced", "row limit"))


def validate_generated_query(query_language: str, query_text: str, time_range_start: datetime, time_range_end: datetime, **options: object) -> HardenedQuery:
    if query_language == "kql":
        return validate_kql(query_text, time_range_start, time_range_end, **options)  # type: ignore[arg-type]
    if query_language == "elastic_dsl":
        return validate_elastic_query(query_text, time_range_start, time_range_end, **options)  # type: ignore[arg-type]
    if query_language == "spl":
        return validate_spl(query_text, time_range_start, time_range_end)
    raise QueryRejectedError(f"Keigan cannot run generated {query_language} queries yet.")
