"""Structured outputs for Keigan AI chat, plus deterministic offline (mock-provider) planners.

With ``LLM_PROVIDER=mock`` the three chat features (intent, query generation, answer) are answered by the deterministic
functions at the bottom of this file, so questions like "How many requests failed in the last 17 hours on claims-api?"
return real numbers from the telemetry simulator without an API key.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from keigan.ai.llm_gateway import PromptSection, register_mock_response

DATA_INTENTS = ("data_count", "data_pattern", "mixed")


class ChatIntentResult(BaseModel):
    intent: Literal["knowledge", "data_count", "data_pattern", "mixed", "out_of_scope"]
    application_name: str | None = Field(default=None, description="Exact application name from the candidate list, if the question names one")
    service_name: str | None = Field(default=None, description="Exact service name from the candidate list, if the question names one")
    wants_failures_only: bool = Field(default=False, description="True when the question is about failed requests, errors or exceptions")


class ChatQueryResult(BaseModel):
    query_text: str = Field(description="One read-only query in the requested language")
    explanation: str = Field(default="", description="One sentence on what the query measures")


class ChatAnswerResult(BaseModel):
    answer_text: str = Field(description="One or two plain sentences that answer the question with the real numbers")


# ── Deterministic planning shared by the mock provider and the fallback path ──────────────────────────────────────────
_PATTERN_WORDS = re.compile(r"\b(pattern|trend|chart|graph|plot|over time|per hour|hourly|by hour|timeline|distribution|breakdown)\b", re.I)
_COUNT_WORDS = re.compile(r"\b(how many|how much|count|number of|total)\b", re.I)
_KNOWLEDGE_WORDS = re.compile(r"\b(how do|how to|what is|what does|explain|runbook|architecture|depends?|dependenc\w+|topology|who owns|which services?|describe|documentation|procedure|why)\b", re.I)
_FAILURE_WORDS = re.compile(r"\b(fail\w*|error\w*|exception\w*|5xx|500s?|broken|unsuccessful)\b", re.I)
_DOMAIN_WORDS = re.compile(r"\b(request\w*|latency|log\w*|traffic|incident\w*|alert\w*|service\w*|api|pod\w*|database|slo|availability|deploy\w*|runbook\w*|architecture|topology|depend\w*|application\w*|document\w*|postmortem\w*|owner\w*|system\w*)\b", re.I)


def plan_intent_offline(question: str, candidate_service_names: list[str], has_previous_context: bool) -> ChatIntentResult:
    lowered = question.lower()
    service_name = next((name for name in sorted(candidate_service_names, key=len, reverse=True) if name.lower() in lowered), None)
    wants_failures = bool(_FAILURE_WORDS.search(question))
    if _PATTERN_WORDS.search(question) and (_COUNT_WORDS.search(question) or wants_failures):
        intent = "mixed"
    elif _PATTERN_WORDS.search(question):
        intent = "data_pattern"
    elif _COUNT_WORDS.search(question) or (wants_failures and (service_name or has_previous_context)):
        intent = "data_count"
    elif _KNOWLEDGE_WORDS.search(question) and (_DOMAIN_WORDS.search(question) or service_name or has_previous_context):
        intent = "knowledge"
    elif service_name or (has_previous_context and _DOMAIN_WORDS.search(question)):
        intent = "data_count"
    elif _DOMAIN_WORDS.search(question):
        intent = "knowledge"
    else:
        intent = "out_of_scope"
    return ChatIntentResult(intent=intent, service_name=service_name, wants_failures_only=wants_failures)


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


def build_answer_offline(facts: dict[str, Any]) -> str:
    service, window = facts.get("serviceName", "the service"), facts.get("windowText", "the selected period")
    subject = "failed requests" if facts.get("wantsFailures") else "requests"
    total = int(facts.get("total") or 0)
    if facts.get("kind") == "chart":
        peak_text = f" The peak was {facts.get('peakValue')} around {facts.get('peakLabel')}." if facts.get("peakLabel") else ""
        return f"Here is how {subject} on {service} developed over {window}: {total:,} in total.{peak_text}"
    return f"{service} recorded {total:,} {subject} over {window}."


def _section(prompt_sections: list[PromptSection], title: str) -> str:
    return next((section.content for section in prompt_sections if section.title == title), "")


def _mock_intent(schema: type[BaseModel], prompt_sections: list[PromptSection]) -> BaseModel:
    context = json.loads(_section(prompt_sections, "Candidates") or "{}")
    return plan_intent_offline(_section(prompt_sections, "Question"), context.get("serviceNames", []), bool(context.get("hasPreviousContext")))


def _mock_query(schema: type[BaseModel], prompt_sections: list[PromptSection]) -> BaseModel:
    request = json.loads(_section(prompt_sections, "Query request") or "{}")
    return build_query_offline(
        request.get("queryLanguage", "kql"), request.get("serviceType", ""), bool(request.get("wantsFailures")), bool(request.get("wantsPattern")), int(request.get("rangeMinutes", 1440))
    )


def _mock_answer(schema: type[BaseModel], prompt_sections: list[PromptSection]) -> BaseModel:
    return ChatAnswerResult(answer_text=build_answer_offline(json.loads(_section(prompt_sections, "Facts") or "{}")))


register_mock_response("ai_chat_intent", _mock_intent)
register_mock_response("ai_chat_query_generation", _mock_query)
register_mock_response("ai_chat_answer", _mock_answer)
