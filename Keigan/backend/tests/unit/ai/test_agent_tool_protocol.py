"""keigan/ai/agent_tool_protocol.py: the prompted-JSON tool protocol for models without native tool calling (spec 23, 4.6.4)."""

from __future__ import annotations

import json

import pytest

from keigan.ai.agent_tool_protocol import (
    PROTOCOL_PROMPT_KEY, MalformedAgentReply, parse_agent_reply, prompted_transcript, protocol_system_prompt, repair_message,
)
from keigan.ai.agent_turn_types import AgentToolRequest, AgentToolSpec, AgentTranscriptEntry, PromptSection

EVIDENCE = AgentToolSpec("get_evidence", "Open one evidence item.", {"type": "object", "properties": {"evidence_code": {"type": "string"}}, "required": ["evidence_code"]})
SLO = AgentToolSpec("get_slo_status", "SLO status.", {"type": "object", "properties": {}})
TOOLS = (EVIDENCE, SLO)
ONE_REQUEST = {"kind": "tool_requests", "requests": [{"id": "k1", "tool": "get_evidence", "arguments": {"evidence_code": "E2"}}]}


def parse(reply: object, *, maximum_requests: int = 3, first_request_number: int = 1):
    return parse_agent_reply(reply if isinstance(reply, str) else json.dumps(reply), TOOLS, maximum_requests=maximum_requests, first_request_number=first_request_number)


# ── Parsing ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_tool_request_reply_becomes_requests_numbered_by_keigan() -> None:
    parsed = parse(ONE_REQUEST, first_request_number=4)
    assert parsed.text == ""
    assert parsed.tool_requests == (AgentToolRequest(request_id="k4", tool_name="get_evidence", arguments={"evidence_code": "E2"}, arguments_problem=None),)


def test_several_requests_are_numbered_in_order_whatever_ids_the_model_wrote() -> None:
    reply = {"kind": "tool_requests", "requests": [{"id": "x", "tool": "get_slo_status", "arguments": {}}, {"id": "x", "tool": "get_evidence", "arguments": {"evidence_code": "E1"}}]}
    assert [request.request_id for request in parse(reply).tool_requests] == ["k1", "k2"]


def test_a_request_without_an_id_or_arguments_is_accepted_with_empty_arguments() -> None:
    parsed = parse({"kind": "tool_requests", "requests": [{"tool": "get_slo_status"}]})
    assert parsed.tool_requests[0].arguments == {}


def test_an_answer_reply_becomes_the_text() -> None:
    parsed = parse({"kind": "answer", "text": "Evidence E2 shows a spike [T1]."})
    assert parsed.text == "Evidence E2 shows a spike [T1]." and parsed.tool_requests == ()


def test_follow_ups_follow_the_answer_after_the_marker_line_the_engine_splits_on() -> None:
    parsed = parse({"kind": "answer", "text": "Answer [T1].", "follow_ups": ["What changed?", "Which runbook?"]})
    assert parsed.text == "Answer [T1].\n\n<<follow-ups>>\nWhat changed?\nWhich runbook?"


@pytest.mark.parametrize("wrapper", ["```json\n{body}\n```", "```\n{body}\n```", "  ```JSON\n{body}\n```  "])
def test_one_surrounding_code_fence_is_removed(wrapper: str) -> None:
    assert parse(wrapper.replace("{body}", json.dumps(ONE_REQUEST))).tool_requests[0].tool_name == "get_evidence"


@pytest.mark.parametrize(
    ("reply", "problem_contains"),
    [
        ("The evidence shows a spike.", "not valid JSON"),
        ('{"kind": "tool_requests", "requests": [', "not valid JSON"),
        ('Sure! {"kind": "answer", "text": "x"}', "not valid JSON"),
        ('{"kind": "answer", "text": "x"} {"kind": "answer", "text": "y"}', "not valid JSON"),
        ("[1, 2]", "JSON object"),
        ({"text": "no kind"}, "kind"),
        ({"kind": "maybe"}, "kind"),
        ({"kind": "answer"}, "text"),
        ({"kind": "answer", "text": "   "}, "text"),
        ({"kind": "answer", "text": "x", "extra": 1}, "extra"),
        ({"kind": "tool_requests", "requests": []}, "requests"),
        ({"kind": "tool_requests", "requests": [{"tool": "get_evidence", "arguments": "E2"}]}, "arguments"),
        ({"kind": "tool_requests", "requests": [{"tool": "query_everything", "arguments": {}}]}, "query_everything"),
    ],
)
def test_a_reply_outside_the_format_is_malformed_with_a_specific_problem(reply: object, problem_contains: str) -> None:
    with pytest.raises(MalformedAgentReply) as problem:
        parse(reply)
    assert problem_contains in str(problem.value)


def test_an_unknown_tool_problem_lists_the_offered_names() -> None:
    with pytest.raises(MalformedAgentReply, match="get_evidence, get_slo_status"):
        parse({"kind": "tool_requests", "requests": [{"tool": "nope", "arguments": {}}]})


def test_more_requests_than_one_turn_may_run_is_malformed() -> None:
    reply = {"kind": "tool_requests", "requests": [{"tool": "get_slo_status", "arguments": {}}] * 3}
    with pytest.raises(MalformedAgentReply, match="at most 2"):
        parse(reply, maximum_requests=2)


def test_the_values_of_arguments_are_not_judged_here_the_tool_registry_does_that_for_both_modes() -> None:
    parsed = parse({"kind": "tool_requests", "requests": [{"tool": "get_evidence", "arguments": {"evidence_code": 99999, "unknown": True}}]})
    assert parsed.tool_requests[0].arguments == {"evidence_code": 99999, "unknown": True}


# ── Repair message ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_repair_message_names_the_problem_and_restates_the_format() -> None:
    message = repair_message("The reply is not valid JSON.")
    assert "The reply is not valid JSON." in message and '"kind"' in message and "exactly one JSON object" in message


def test_a_very_long_problem_is_cut_in_the_repair_message() -> None:
    assert len(repair_message("x" * 10_000)) < 3000


# ── The system prompt ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_system_prompt_keeps_the_original_and_lists_the_tools_with_their_schemas() -> None:
    prompt = protocol_system_prompt("You are Keigan.", TOOLS, allow_tool_requests=True, maximum_requests=3)
    assert prompt.startswith("You are Keigan.")
    assert "get_evidence" in prompt and "Open one evidence item." in prompt and json.dumps(EVIDENCE.parameters_schema) in prompt
    assert "at most 3" in prompt and '"kind": "tool_requests"' in prompt and '"kind": "answer"' in prompt


def test_on_the_final_turn_the_prompt_tells_the_model_to_answer_and_does_not_offer_tool_requests() -> None:
    prompt = protocol_system_prompt("You are Keigan.", TOOLS, allow_tool_requests=False, maximum_requests=3)
    assert "Tool requests are not accepted" in prompt and '"kind": "tool_requests"' not in prompt


def test_the_protocol_prompt_is_a_versioned_fragment() -> None:
    from keigan.config import application_context

    assert PROTOCOL_PROMPT_KEY == "_agent_tool_protocol" and application_context.prompt_library().version_of(PROTOCOL_PROMPT_KEY) == "1"


# ── The transcript the model reads ──────────────────────────────────────────────────────────────────────────────────────────
def test_earlier_turns_become_the_json_they_would_have_written_and_results_one_block_per_run() -> None:
    question = AgentTranscriptEntry(kind="data", section=PromptSection("Question", "Show E2", is_untrusted=True))
    requests = (AgentToolRequest("k1", "get_evidence", {"evidence_code": "E2"}), AgentToolRequest("k2", "get_slo_status", {}))
    transcript = [
        question,
        AgentTranscriptEntry(kind="assistant", tool_requests=requests),
        AgentTranscriptEntry(kind="tool_result", tool_request_id="k1", tool_name="get_evidence", tool_result_text="<untrusted_data>spike</untrusted_data>"),
        AgentTranscriptEntry(kind="tool_result", tool_request_id="k2", tool_name="get_slo_status", tool_result_text="refused (invalid_arguments): bad"),
    ]
    converted = prompted_transcript(transcript)
    assert [entry.kind for entry in converted] == ["data", "assistant", "data"]
    assert converted[0] is question
    assert converted[1].tool_requests == () and json.loads(converted[1].text) == {
        "kind": "tool_requests",
        "requests": [{"id": "k1", "tool": "get_evidence", "arguments": {"evidence_code": "E2"}}, {"id": "k2", "tool": "get_slo_status", "arguments": {}}],
    }
    results = converted[2].section
    assert results is not None and results.title == "Tool results" and results.is_untrusted is False
    assert "k1" in results.content and "get_evidence" in results.content and "<untrusted_data>spike</untrusted_data>" in results.content and "refused (invalid_arguments): bad" in results.content


def test_a_request_whose_arguments_could_not_be_read_is_replayed_with_empty_arguments() -> None:
    converted = prompted_transcript([AgentTranscriptEntry(kind="assistant", tool_requests=(AgentToolRequest("k1", "get_evidence", None, "not JSON"),))])
    assert json.loads(converted[0].text)["requests"][0]["arguments"] == {}


def test_an_earlier_text_only_turn_is_replayed_as_an_answer_reply() -> None:
    converted = prompted_transcript([AgentTranscriptEntry(kind="assistant", text="Earlier answer.")])
    assert json.loads(converted[0].text) == {"kind": "answer", "text": "Earlier answer."}
