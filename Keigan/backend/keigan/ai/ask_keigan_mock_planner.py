"""Deterministic stand-in for the model's tool use when ``LLM_PROVIDER=mock`` (spec 23, section 4.6.7).

Like the mock factories of the other AI features it is keyed by feature name and registered with the gateway, so the whole Ask Keigan loop, every
tool, the trace and the screens run offline. It is given exactly what a real model is given (the transcript and the offered tool schemas) and builds
its arguments only from what the schemas offer, so a question that works here must work against a real model too.

Turn rules: the question's keyword groups are matched against the offered tools, the first group (by position in the question) is requested in
turn 1, and when the question joins a second group with "and" that group's tool follows in turn 2. Once every planned tool has a result, the answer
has one sentence per tool call, each ending with its citation.

What the planner expects of a tool result in the transcript (after the spotlight block is removed): a JSON object with a ``summary`` text, or plain text;
a text that starts with ``refused``, ``failed`` or ``skipped`` (optionally after the tool's name) is a call that gave no data. A skipped call has no citation number, every other call has one.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from keigan.ai.ask_keigan_answer_format import FOLLOW_UP_MARKER, HISTORY_SECTION_TITLE, QUESTION_SECTION_TITLE, FixedAnswer, fixed_answer
from keigan.ai.llm_gateway import AgentPlannerInput, AgentToolRequest, AgentToolSpec, AgentTranscriptEntry, AgentTurnResult, estimate_token_count, register_mock_agent_planner
from keigan.config.settings import get_settings
from keigan.entities.status_values import ChatRunStepStatus, ToolCallingMode
from keigan.utils.string_table import FALLBACK_LANGUAGE_CODE


class AskKeiganFeature(StrEnum):
    """The feature names Ask Keigan calls the gateway with (usage accounting and mock planning are keyed by them)."""

    GLOBAL = "ask_keigan_global"
    INVESTIGATION = "ask_keigan_investigation"


OUTSIDE_SCOPE_ANSWER = fixed_answer(FixedAnswer.OUTSIDE_SCOPE, FALLBACK_LANGUAGE_CODE)  # the planner answers in English, with the sentence the string tables hold
NOTHING_LOOKED_UP_ANSWER = "I could not look anything up in Keigan's data for this question, so I cannot answer it."
MAXIMUM_TOOLS_PER_QUESTION = 2
# A tool result that gave no data starts with the step status word the engine records for it, optionally after the tool's name ("get_evidence refused (invalid_arguments): ...").
NO_DATA_STATUSES = (ChatRunStepStatus.REFUSED, ChatRunStepStatus.FAILED, ChatRunStepStatus.SKIPPED)
_NO_DATA_RESULT = re.compile(rf"^(?:\w+ )?({'|'.join(NO_DATA_STATUSES)})\b", re.IGNORECASE)

_SECOND_GROUP_JOINER = re.compile(r"\band\b|および|そして", re.IGNORECASE)
_SPOTLIGHT_BLOCK = re.compile(r"<untrusted_data[^>]*>\n?(.*?)\n?</untrusted_data[^>]*>", re.DOTALL)
_SERVICE_NAME = re.compile(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+)+\b", re.IGNORECASE)
_WINDOW = re.compile(r"(?:last|past)\s+(?:(\d+)\s*)?(minute|hour|day)s?|(?:過去|直近)\s*(\d+)\s*(分|時間|日)", re.IGNORECASE)
_MINUTES_PER_HOUR = 60
_WINDOW_MINUTES_PER_UNIT = {"minute": 1, "hour": _MINUTES_PER_HOUR, "day": 24 * _MINUTES_PER_HOUR, "分": 1, "時間": _MINUTES_PER_HOUR, "日": 24 * _MINUTES_PER_HOUR}
_PATTERN_WORDS = re.compile(r"\b(?:pattern|trend|over time|hourly|chart|graph)\b|推移|パターン", re.IGNORECASE)
_FAILURE_WORDS = re.compile(r"\b(?:errors?|fail\w*|exceptions?|5xx|broken)\b|エラー|失敗", re.IGNORECASE)
# Words that make a question about Keigan's own data; a question with none of them is answered as outside the scope.
_DOMAIN_WORDS = re.compile(
    r"\b(?:request\w*|latency|log\w*|traffic|incident\w*|alert\w*|service\w*|api|pod\w*|database|slo|availability|deploy\w*|runbook\w*|architecture|topology|"
    r"depend\w*|application\w*|document\w*|postmortem\w*|owner\w*|system\w*)\b|ログ|アラート|手順|構成|データベース",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _Question:
    text: str
    context_text: str  # the other data sections (for example the investigation digest); never the earlier conversation


@dataclass(frozen=True)
class _ToolRule:
    tool_name: str
    keywords: re.Pattern[str]
    candidate_arguments: Callable[[_Question, re.Match[str], dict[str, Any]], dict[str, Any] | None]
    follow_up_questions: tuple[str, ...]


@dataclass(frozen=True)
class _PlannedCall:
    position: int
    rule: _ToolRule
    arguments: dict[str, Any]


@dataclass(frozen=True)
class _ExecutedCall:
    tool_name: str
    arguments: dict[str, Any]
    result_text: str


def _code_from_properties(question: _Question, properties: dict[str, Any], property_name: str) -> str | None:
    """One value of an enum property: the first one the question names, else the first offered. None when the schema lists no values."""
    offered_values = properties.get(property_name, {}).get("enum") or []
    return next((value for value in offered_values if re.search(rf"\b{re.escape(value)}\b", question.text, re.IGNORECASE)), offered_values[0] if offered_values else None)


def _service_name(question: _Question, properties: dict[str, Any]) -> str | None:
    if properties.get("service_name", {}).get("enum"):
        return _code_from_properties(question, properties, "service_name")
    if named_in_question := _SERVICE_NAME.search(question.text):
        return named_in_question.group(0).lower()
    context_names = Counter(name.lower() for name in _SERVICE_NAME.findall(question.context_text))
    return context_names.most_common(1)[0][0] if context_names else None


def _window_minutes(text: str) -> int | None:
    window = _WINDOW.search(text)
    if window is None:
        return None
    amount, unit = (window.group(1), window.group(2)) if window.group(2) else (window.group(3), window.group(4))
    return int(amount or 1) * _WINDOW_MINUTES_PER_UNIT[unit.lower()]


def _evidence_arguments(question: _Question, keyword_match: re.Match[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {"evidence_code": f"E{keyword_match.group(1)}"}


def _timeline_arguments(question: _Question, keyword_match: re.Match[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {}


def _log_query_arguments(question: _Question, keyword_match: re.Match[str], properties: dict[str, Any]) -> dict[str, Any] | None:
    service_name = _service_name(question, properties)
    if service_name is None:
        return None
    arguments: dict[str, Any] = {
        "application_code": _code_from_properties(question, properties, "application_code"), "service_name": service_name, "question": question.text,
        "wants_pattern": bool(_PATTERN_WORDS.search(question.text)), "failures_only": bool(_FAILURE_WORDS.search(question.text)),
    }
    if (window_minutes := _window_minutes(question.text)) is not None:
        arguments["lookback_minutes"] = window_minutes
    return arguments


def _question_as_text_argument(question: _Question, properties: dict[str, Any], property_name: str) -> str:
    """The question, cut to the length the tool accepts for ``property_name``."""
    longest_text = properties.get(property_name, {}).get("maxLength")
    return question.text[:longest_text] if longest_text else question.text


def _knowledge_arguments(question: _Question, keyword_match: re.Match[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {"application_code": _code_from_properties(question, properties, "application_code"), "query": _question_as_text_argument(question, properties, "query")}


def _slo_status_arguments(question: _Question, keyword_match: re.Match[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {}  # every application of the scope, every state: the tool's own default


def _recent_changes_arguments(question: _Question, keyword_match: re.Match[str], properties: dict[str, Any]) -> dict[str, Any]:
    arguments: dict[str, Any] = {"application_code": _code_from_properties(question, properties, "application_code")}
    if (window_minutes := _window_minutes(question.text)) is not None:
        window_schema = properties.get("lookback_hours", {})
        lookback_hours = max(math.ceil(window_minutes / _MINUTES_PER_HOUR), window_schema.get("minimum", 1))
        arguments["lookback_hours"] = min(lookback_hours, window_schema.get("maximum", lookback_hours))
    return arguments


def _runbook_arguments(question: _Question, keyword_match: re.Match[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {"application_code": _code_from_properties(question, properties, "application_code"), "symptoms": _question_as_text_argument(question, properties, "symptoms")}


def _topology_arguments(question: _Question, keyword_match: re.Match[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {"application_code": _code_from_properties(question, properties, "application_code")}


# Table order breaks ties between groups that start at the same position.
_TOOL_RULES: tuple[_ToolRule, ...] = (
    _ToolRule(
        "get_evidence", re.compile(r"(?<![A-Za-z0-9])E(\d{1,3})(?![A-Za-z0-9])", re.IGNORECASE), _evidence_arguments,
        ("What does the timeline say around this evidence?", "Which hypothesis does this evidence support?", "What else was found on the same service?"),
    ),
    _ToolRule(
        "get_investigation_timeline", re.compile(r"\btimelines?\b|\bstatus updates?\b|\bexecutives?\b|タイムライン|状況報告|経営層", re.IGNORECASE), _timeline_arguments,
        ("Which evidence matches these events?", "What changed before the first event?", "Which runbook fits this situation?"),
    ),
    _ToolRule(
        "get_slo_status", re.compile(r"\bslos?\b|\berror budgets?\b|\bburn\w*|エラーバジェット", re.IGNORECASE), _slo_status_arguments,
        ("Did anything change before the budget started burning?", "Is there a runbook for this?", "What does the application depend on?"),
    ),
    _ToolRule(
        "list_recent_changes", re.compile(r"\b(?:chang\w*|deploy\w*|releases?|rollouts?)\b|変更|変わ|デプロイ", re.IGNORECASE), _recent_changes_arguments,
        ("What does the timeline say around the latest change?", "How are the SLOs doing?", "Is there a runbook for this?"),
    ),
    _ToolRule(
        "find_runbooks", re.compile(r"\brunbooks?\b|\bfix(?:es)?\b|手順", re.IGNORECASE), _runbook_arguments,
        ("What changed in the last 24 hours?", "What does the application depend on?", "How are the SLOs doing?"),
    ),
    _ToolRule(
        "get_topology", re.compile(r"\b(?:depend\w*|topology|architecture|new engineer)\b|依存|構成図|新任エンジニア", re.IGNORECASE), _topology_arguments,
        ("Is there a runbook for this?", "What changed in the last 24 hours?", "How are the SLOs doing?"),
    ),
    _ToolRule(
        "query_logs", re.compile(r"\b(?:how many|count|errors?(?!\s+budget)|fail\w*|pattern)\b|何件|件数|エラー(?!バジェット)|失敗|パターン", re.IGNORECASE), _log_query_arguments,
        ("Show the pattern over the last 24 hours.", "Which services does this one depend on?", "What do the knowledge documents say about these errors?"),
    ),
)
_KNOWLEDGE_RULE = _ToolRule(
    "search_knowledge", _DOMAIN_WORDS, _knowledge_arguments,
    ("Is there a runbook for this?", "Which services does this depend on?", "Were there related incidents?"),
)
_FOLLOW_UPS_BY_TOOL = {rule.tool_name: rule.follow_up_questions for rule in (*_TOOL_RULES, _KNOWLEDGE_RULE)}


def _read_question(transcript: tuple[AgentTranscriptEntry, ...]) -> _Question:
    data_sections = [entry.section for entry in transcript if entry.kind == "data" and entry.section is not None]
    question_text = next((section.content for section in data_sections if section.title == QUESTION_SECTION_TITLE), "")
    context_text = "\n".join(section.content for section in data_sections if section.title not in (QUESTION_SECTION_TITLE, HISTORY_SECTION_TITLE))
    return _Question(question_text.strip(), context_text)


def _fill_arguments(tool: AgentToolSpec, candidates: dict[str, Any] | None) -> dict[str, Any] | None:
    """The candidate values the tool's schema offers; None when a required argument has no value."""
    if candidates is None:
        return None
    offered_properties = tool.parameters_schema.get("properties", {})
    arguments = {name: value for name, value in candidates.items() if name in offered_properties and value is not None}
    return arguments if all(name in arguments for name in tool.parameters_schema.get("required", [])) else None


def _plan_calls(question: _Question, tools: tuple[AgentToolSpec, ...]) -> list[_PlannedCall]:
    tools_by_name = {tool.name: tool for tool in tools}
    planned_calls: list[_PlannedCall] = []
    for rule in _TOOL_RULES:
        tool = tools_by_name.get(rule.tool_name)
        keyword_match = rule.keywords.search(question.text) if tool else None
        if tool is None or keyword_match is None:
            continue
        if (arguments := _fill_arguments(tool, rule.candidate_arguments(question, keyword_match, tool.parameters_schema.get("properties", {})))) is not None:
            planned_calls.append(_PlannedCall(keyword_match.start(), rule, arguments))
    if not planned_calls and (knowledge_tool := tools_by_name.get(_KNOWLEDGE_RULE.tool_name)) and (keyword_match := _KNOWLEDGE_RULE.keywords.search(question.text)):
        knowledge_arguments = _fill_arguments(knowledge_tool, _knowledge_arguments(question, keyword_match, knowledge_tool.parameters_schema.get("properties", {})))
        planned_calls = [_PlannedCall(keyword_match.start(), _KNOWLEDGE_RULE, knowledge_arguments)] if knowledge_arguments is not None else []
    planned_calls.sort(key=lambda call: call.position)
    return planned_calls[:MAXIMUM_TOOLS_PER_QUESTION if _SECOND_GROUP_JOINER.search(question.text) else 1]


def _executed_calls(transcript: tuple[AgentTranscriptEntry, ...]) -> list[_ExecutedCall]:
    arguments_by_request_id = {request.request_id: request.arguments or {} for entry in transcript if entry.kind == "assistant" for request in entry.tool_requests}
    return [
        _ExecutedCall(entry.tool_name, arguments_by_request_id.get(entry.tool_request_id, {}), entry.tool_result_text)
        for entry in transcript
        if entry.kind == "tool_result"
    ]


def _unwrapped(result_text: str) -> str:
    spotlight_block = _SPOTLIGHT_BLOCK.search(result_text)
    return (spotlight_block.group(1) if spotlight_block else result_text).strip()


def _summary_of(result_body: str) -> str:
    try:
        parsed_result = json.loads(result_body)
    except json.JSONDecodeError:
        parsed_result = None
    if isinstance(parsed_result, dict) and isinstance(parsed_result.get("summary"), str):
        return parsed_result["summary"].strip()
    return next((line.strip() for line in result_body.splitlines() if line.strip()), "")


def _answer_from(executed_calls: list[_ExecutedCall]) -> tuple[str, list[str]]:
    """One sentence per tool call and the follow-up questions of the tools that gave data."""
    sentences: list[str] = []
    follow_ups: list[str] = []
    citation_number = 0
    for executed_call in executed_calls:
        result_body = _unwrapped(executed_call.result_text)
        no_data_result = _NO_DATA_RESULT.match(result_body)
        if no_data_result:
            if no_data_result.group(1).lower() != ChatRunStepStatus.SKIPPED:
                citation_number += 1
            reason = result_body.partition(":")[2].strip().rstrip(".")
            sentences.append(f"I could not check {executed_call.tool_name}: {reason}." if reason else f"I could not check {executed_call.tool_name}.")
            continue
        citation_number += 1
        evidence_code = executed_call.arguments.get("evidence_code")
        citations = f"[T{citation_number}]" + (f" [{str(evidence_code).upper()}]" if evidence_code else "")
        sentences.append(f"{_summary_of(result_body).rstrip('.')} {citations}.")
        follow_ups.extend(_FOLLOW_UPS_BY_TOOL.get(executed_call.tool_name, ()))
    return "\n".join(sentences), follow_ups


def _with_follow_ups(answer_text: str, follow_ups: list[str]) -> str:
    chosen_follow_ups = list(dict.fromkeys(follow_ups))[:get_settings().ask_keigan_follow_up_question_limit]
    return f"{answer_text}\n\n{FOLLOW_UP_MARKER}\n" + "\n".join(chosen_follow_ups) if chosen_follow_ups else answer_text


def _transcript_text(planner_input: AgentPlannerInput) -> str:
    texts = [planner_input.system_prompt]
    for entry in planner_input.transcript:
        texts.append(entry.section.content if entry.section else entry.text or entry.tool_result_text)
    return "\n".join(texts)


def plan_agent_turn(planner_input: AgentPlannerInput) -> AgentTurnResult:
    """The next turn for the question in ``planner_input``: the next planned tool request, or the answer once every planned tool has a result."""
    question = _read_question(planner_input.transcript)
    executed_calls = _executed_calls(planner_input.transcript)
    planned_calls = _plan_calls(question, planner_input.tools)
    next_call = planned_calls[len(executed_calls)] if planner_input.allow_tool_requests and len(executed_calls) < len(planned_calls) else None
    if next_call is not None:
        answer_text = ""
        tool_requests = (AgentToolRequest(request_id=f"k{len(executed_calls) + 1}", tool_name=next_call.rule.tool_name, arguments=next_call.arguments),)
    else:
        tool_requests = ()
        if executed_calls:
            answer_sentences, follow_ups = _answer_from(executed_calls)
            answer_text = _with_follow_ups(answer_sentences, follow_ups)
        else:
            answer_text = NOTHING_LOOKED_UP_ANSWER if planned_calls else OUTSIDE_SCOPE_ANSWER
    return AgentTurnResult(
        text=answer_text, tool_requests=tool_requests, finish="tool_requests" if tool_requests else "answer",
        input_token_count=estimate_token_count(_transcript_text(planner_input)), output_token_count=estimate_token_count(answer_text + json.dumps([request.arguments for request in tool_requests])),
        token_counts_estimated=True, model_name="mock", tool_calling_mode=ToolCallingMode.SCRIPTED_MOCK,
    )


for _feature in AskKeiganFeature:
    register_mock_agent_planner(_feature, plan_agent_turn)
