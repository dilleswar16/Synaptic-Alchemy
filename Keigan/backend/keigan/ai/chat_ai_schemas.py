"""Structured output of the log query writer, plus its deterministic offline (mock-provider) planner.

With ``LLM_PROVIDER=mock`` the query writer (feature ``ai_chat_query_generation``) is answered by the deterministic
function at the bottom of this file, so questions like "How many requests failed in the last 17 hours on claims-api?"
return real numbers from the telemetry simulator without an API key.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from keigan.ai.llm_gateway import PromptSection, register_mock_response


class ChatQueryResult(BaseModel):
    query_text: str = Field(description="One read-only query in the requested language")
    explanation: str = Field(default="", description="One sentence on what the query measures")


# ── Deterministic query writer for the mock provider ─────────────────────────────────────────────────────────────────
_KQL_TABLES_BY_SERVICE_TYPE: dict[str, tuple[str, str]] = {
    "api_management": ("ApiManagementGatewayLogs", "where ResponseCode >= 500"),
    "aks": ("ContainerLogV2", 'where LogMessage has "error"'),
    "sql_database": ("AzureDiagnostics", 'where Category == "Errors"'),
    "logic_app": ("AzureDiagnostics", 'where status_s == "Failed"'),
    "data_factory": ("ADFActivityRun", 'where Status == "Failed"'),
}
_DEFAULT_KQL_TABLE = ("AppRequests", "where Success == false")


def bucket_for_range(range_minutes: int) -> str:
    return "5m" if range_minutes <= 180 else "15m" if range_minutes <= 720 else "1h" if range_minutes <= 2880 else "6h" if range_minutes <= 10080 else "1d"


def build_query_offline(query_language: str, service_type: str, wants_failures: bool, wants_pattern: bool, range_minutes: int) -> ChatQueryResult:
    bucket = bucket_for_range(range_minutes)
    if query_language == "kql":
        table, failure_filter = _KQL_TABLES_BY_SERVICE_TYPE.get(service_type, _DEFAULT_KQL_TABLE)
        stages = [table] + ([failure_filter] if wants_failures else [])
        stages.append(f"summarize count() by bin(TimeGenerated, {bucket})" if wants_pattern else "summarize count()")
        return ChatQueryResult(query_text="\n| ".join(stages), explanation="Counts matching records" + (" per time bucket." if wants_pattern else "."))
    if query_language == "spl":
        spl = "search " + ("(level=ERROR OR status>=500) " if wants_failures else "")
        spl += f"| timechart span={bucket} count" if wants_pattern else "| stats count"
        return ChatQueryResult(query_text=spl, explanation="Counts matching events.")
    filters: list[dict[str, Any]] = [{"match": {"log.level": "error"}}] if wants_failures else []
    body: dict[str, Any] = {"size": 0, "query": {"bool": {"filter": filters}}}
    if wants_pattern:
        body["aggs"] = {"over_time": {"date_histogram": {"field": "@timestamp", "fixed_interval": bucket}}}
    return ChatQueryResult(query_text=json.dumps(body), explanation="Counts matching documents.")


def _section(prompt_sections: list[PromptSection], title: str) -> str:
    return next((section.content for section in prompt_sections if section.title == title), "")


def _mock_query(schema: type[BaseModel], prompt_sections: list[PromptSection]) -> BaseModel:
    request = json.loads(_section(prompt_sections, "Query request") or "{}")
    return build_query_offline(
        request.get("queryLanguage", "kql"), request.get("serviceType", ""), bool(request.get("wantsFailures")), bool(request.get("wantsPattern")), int(request.get("rangeMinutes", 1440))
    )


register_mock_response("ai_chat_query_generation", _mock_query)
