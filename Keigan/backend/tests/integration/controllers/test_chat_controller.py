"""keigan/controllers/chat_controller.py, the Ask Keigan endpoints (spec 23, 7.1; AC-21 to AC-25): the answer stream, the snapshot, a step's output and Stop.

Most tests call the app in process (the whole body is read at the end). The two that must see frames arrive while the run is still going (AC-23, AC-24) talk to a
real uvicorn server on a local port, through the full middleware stack.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import pytest
import uvicorn
from sqlalchemy import update

from keigan.ai.model_capabilities import resolve_model_capabilities
from keigan.config import application_context
from keigan.config.database_config import open_session
from keigan.config.settings import LlmProviderName, get_settings
from keigan.entities.incident_entities import ChatAnswerRun
from keigan.entities.status_values import ChatAnswerRunStatus
from keigan.utils.time_utils import utc_now
from support import users
from support.ask_keigan_conversations import running_runs_of, runs_of, seed_investigation
from support.ask_keigan_runs import ScriptedGateway, Turn, request_for
from support.http import AuthHeaders
from support.server_sent_events import parse_frames

pytestmark = pytest.mark.usefixtures("seed_context")

READER = users.CLMJP_AND_PAYAU_READER
EVENT_STREAM = {"Accept": "text/event-stream"}
QUESTION = "Show me evidence E2 and what the timeline says before it"
PROBLEM_JSON = "application/problem+json"


@dataclass(frozen=True)
class Chat:
    conversation_id: str
    investigation_id: str
    headers: dict[str, str]


@pytest.fixture(autouse=True)
def generous_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "chat_rate_limit_per_minute", 10_000)


@pytest.fixture
async def chat(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> Chat:
    """A fresh investigation of CLMJP and the reader's chat about it, created through the API as the investigation page does."""
    investigation = await seed_investigation(seed_context.application_ids_by_code["CLMJP"])
    headers = await auth_headers(READER)
    created = await client.post("/api/chat/conversations", headers=headers, json={"conversationScope": "investigation", "investigationId": investigation.investigation_id})
    assert created.status_code == 201, created.text
    return Chat(created.json()["conversationId"], investigation.investigation_id, headers)


async def ask(client: httpx.AsyncClient, chat: Chat, text: str = QUESTION, *, client_request_id: str | None = None, headers: dict[str, str] | None = None) -> httpx.Response:
    return await client.post(
        f"/api/chat/conversations/{chat.conversation_id}/answers", headers={**(headers or chat.headers), **EVENT_STREAM},
        json={"messageText": text, "clientRequestId": client_request_id or str(uuid.uuid4())},
    )


def use_gateway(monkeypatch: pytest.MonkeyPatch, gateway: ScriptedGateway) -> None:
    monkeypatch.setattr(application_context, "llm_gateway", lambda: gateway)


async def wait_for_a_running_run(conversation_id: str) -> str:
    for _ in range(200):
        running = await running_runs_of(conversation_id)
        if running:
            return running[0].answer_run_id
        await asyncio.sleep(0.05)
    raise AssertionError("no run started")


async def wait_for_a_finished_tool_call(client: httpx.AsyncClient, chat: Chat, answer_run_id: str) -> None:
    for _ in range(200):
        snapshot = (await client.get(f"/api/chat/answer-runs/{answer_run_id}", headers=chat.headers)).json()
        if any(step["kind"] == "tool_call" and step["status"] == "succeeded" for step in snapshot["steps"]):
            return
        await asyncio.sleep(0.05)
    raise AssertionError("the tool call did not finish")


def blocked_turn(release: asyncio.Event, **options) -> Turn:
    async def wait_for_release() -> None:
        await release.wait()

    return Turn(before=wait_for_release, **options)


# ── AC-21: the stream ─────────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_an_answer_streams_its_steps(client: httpx.AsyncClient, chat: Chat) -> None:
    response = await ask(client, chat)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = parse_frames(response.text)
    assert [frame.event for frame in frames] == ["answer.started", "tool.started", "tool.finished", "tool.started", "tool.finished", "answer.text", "answer.completed"]
    assert [int(frame.id) for frame in frames] == list(range(1, 8)) and [frame.data["sequence"] for frame in frames] == list(range(1, 8))
    assert {frame.data["answerRunId"] for frame in frames} == {frames[0].data["answerRunId"]} and all(frame.data["eventVersion"] == 1 for frame in frames)
    started, first_tool, first_done, second_tool, second_done, text, completed = frames
    assert started.data["userMessage"]["messageText"] == QUESTION and started.data["scope"] == "investigation" and started.data["maximumToolCalls"] == 6
    assert [(tool.data["tool"]["name"], tool.data["citationCode"], tool.data["boundArgumentNames"]) for tool in (first_tool, second_tool)] == [
        ("get_evidence", "T1", ["investigation_id"]), ("get_investigation_timeline", "T2", ["investigation_id"]),
    ]
    assert first_tool.data["arguments"]["evidence_code"] == "E2" and first_tool.data["target"]["applicationName"] == "Claims Processing (JP)"
    assert first_tool.data["sequenceNumber"] == first_done.data["sequenceNumber"] and first_done.data["runStepId"] == first_tool.data["runStepId"]
    assert first_done.data["status"] == "succeeded" and second_done.data["status"] == "succeeded" and first_done.data["summary"]
    assert {"T1", "T2"} <= {citation["code"] for citation in completed.data["answer"]["citations"]}
    assert "[T1]" in text.data["text"] and completed.data["stopReason"] == "answered" and completed.data["toolCallCount"] == 2
    assert sum(frame.event in ("answer.completed", "answer.failed") for frame in frames) == 1


async def test_the_events_carry_the_step_number_the_snapshot_uses(client: httpx.AsyncClient, chat: Chat) -> None:
    frames = parse_frames((await ask(client, chat)).text)
    answer_run_id = frames[0].data["answerRunId"]
    snapshot = (await client.get(f"/api/chat/answer-runs/{answer_run_id}", headers=chat.headers)).json()
    step_numbers_in_events = {frame.data["runStepId"]: frame.data["sequenceNumber"] for frame in frames if frame.event == "tool.started"}
    assert {step["runStepId"]: step["sequenceNumber"] for step in snapshot["steps"] if step["kind"] == "tool_call"} == step_numbers_in_events


# ── AC-22: errors before the stream starts ───────────────────────────────────────────────────────────────────────────────────
async def test_an_unauthenticated_request_is_refused_with_problem_json(client: httpx.AsyncClient, chat: Chat) -> None:
    response = await client.post(f"/api/chat/conversations/{chat.conversation_id}/answers", headers=EVENT_STREAM, json={"messageText": "Hi", "clientRequestId": str(uuid.uuid4())})
    assert response.status_code == 401 and response.headers["content-type"].startswith(PROBLEM_JSON) and response.json()["errorCode"] == "authentication_required"


async def test_someone_else_cannot_ask_in_my_conversation(client: httpx.AsyncClient, chat: Chat, auth_headers: AuthHeaders) -> None:
    response = await ask(client, chat, headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER))
    assert response.status_code == 403 and response.json()["errorCode"] == "forbidden" and response.headers["content-type"].startswith(PROBLEM_JSON)
    assert await runs_of(chat.conversation_id) == []


async def test_an_unknown_conversation_is_a_404_problem(client: httpx.AsyncClient, chat: Chat) -> None:
    response = await client.post(f"/api/chat/conversations/{uuid.uuid4()}/answers", headers={**chat.headers, **EVENT_STREAM}, json={"messageText": "Hi", "clientRequestId": str(uuid.uuid4())})
    assert response.status_code == 404 and response.json()["errorCode"] == "not_found"


async def test_a_request_that_does_not_accept_an_event_stream_is_a_406(client: httpx.AsyncClient, chat: Chat) -> None:
    response = await client.post(
        f"/api/chat/conversations/{chat.conversation_id}/answers", headers={**chat.headers, "Accept": "application/json"}, json={"messageText": "Hi", "clientRequestId": str(uuid.uuid4())},
    )
    assert response.status_code == 406 and response.json()["errorCode"] == "not_acceptable" and await runs_of(chat.conversation_id) == []


@pytest.mark.parametrize("body", [
    {"messageText": "", "clientRequestId": "6b8f4d52-1c5c-4d6b-9a11-0a0f0f0f0f0f"},
    {"messageText": "x" * 4001, "clientRequestId": "6b8f4d52-1c5c-4d6b-9a11-0a0f0f0f0f0f"},
    {"messageText": "Hi", "clientRequestId": "not-a-uuid"},
    {"messageText": "Hi"},
])
async def test_an_invalid_question_is_a_422_with_the_field(client: httpx.AsyncClient, chat: Chat, body: dict) -> None:
    response = await client.post(f"/api/chat/conversations/{chat.conversation_id}/answers", headers={**chat.headers, **EVENT_STREAM}, json=body)
    assert response.status_code == 422 and response.json()["errorCode"] == "validation_failed" and response.json()["fieldErrors"]
    assert await runs_of(chat.conversation_id) == []


async def test_a_repeated_request_id_is_a_409_naming_the_existing_run(client: httpx.AsyncClient, chat: Chat) -> None:
    request_id = str(uuid.uuid4())
    first = parse_frames((await ask(client, chat, client_request_id=request_id)).text)
    repeated = await ask(client, chat, client_request_id=request_id)
    assert repeated.status_code == 409 and repeated.headers["content-type"].startswith(PROBLEM_JSON)
    assert repeated.json()["errorCode"] == "duplicate_request" and repeated.json()["answerRunId"] == first[0].data["answerRunId"]
    assert len(await runs_of(chat.conversation_id)) == 1


async def test_a_question_while_another_is_running_is_a_409_naming_the_running_run(client: httpx.AsyncClient, chat: Chat) -> None:
    first = await ask(client, chat)
    run_id = parse_frames(first.text)[0].data["answerRunId"]
    async with open_session() as session:  # as if another pod were still working on the first answer
        await session.execute(update(ChatAnswerRun).where(ChatAnswerRun.answer_run_id == run_id).values(run_status=ChatAnswerRunStatus.RUNNING, last_progress_at=utc_now()))
    second = await ask(client, chat, "And what about E1?")
    assert second.status_code == 409 and second.json()["errorCode"] == "answer_in_progress" and second.json()["answerRunId"] == run_id
    assert "still answering your previous question" in second.json()["detail"]


async def test_the_rate_limit_is_a_429_with_the_catalogue_wording(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "chat_rate_limit_per_minute", 1)
    investigation = await seed_investigation(seed_context.application_ids_by_code["CLMJP"])
    headers = await auth_headers(users.KEIGAN_ADMIN)  # no other test asks as this user, so its budget is untouched
    created = await client.post("/api/chat/conversations", headers=headers, json={"conversationScope": "investigation", "investigationId": investigation.investigation_id})
    limited_chat = Chat(created.json()["conversationId"], investigation.investigation_id, headers)
    assert (await ask(client, limited_chat)).status_code == 200
    response = await ask(client, limited_chat, "Another one", headers={**headers, "X-Correlation-Id": "corr-http-rate"})
    assert response.status_code == 429 and response.json()["errorCode"] == "rate_limited" and response.headers["content-type"].startswith(PROBLEM_JSON)
    assert response.json()["detail"] == "You are sending questions too quickly. Try again in a few seconds. Reference corr-http-rate."


async def test_a_model_that_cannot_use_tools_is_a_503_naming_the_model(client: httpx.AsyncClient, chat: Chat, monkeypatch: pytest.MonkeyPatch) -> None:
    capabilities = resolve_model_capabilities(LlmProviderName.MOCK, "mock", json.dumps({"providers": {"mock": [{"model": "*", "tool_calling": "none"}]}}))
    use_gateway(monkeypatch, ScriptedGateway([], capabilities=capabilities))
    response = await ask(client, chat)
    assert response.status_code == 503 and response.json()["errorCode"] == "ai_tools_unsupported" and "cannot use tools" in response.json()["detail"]
    assert await runs_of(chat.conversation_id) == []


# ── The snapshot, a step's output and the history ─────────────────────────────────────────────────────────────────────────────
async def test_the_snapshot_is_what_the_stream_said(client: httpx.AsyncClient, chat: Chat) -> None:
    frames = parse_frames((await ask(client, chat)).text)
    completed = frames[-1]
    response = await client.get(f"/api/chat/answer-runs/{frames[0].data['answerRunId']}", headers=chat.headers)
    assert response.status_code == 200
    snapshot = response.json()
    assert (snapshot["status"], snapshot["stopReason"], snapshot["scope"], snapshot["toolCallCount"], snapshot["maximumToolCalls"]) == ("completed", "answered", "investigation", 2, 6)
    assert snapshot["answer"]["markdown"] == completed.data["answer"]["markdown"] and snapshot["answer"]["messageId"] == completed.data["answer"]["messageId"]
    assert snapshot["answer"]["citations"] == completed.data["answer"]["citations"] and snapshot["error"] is None
    tool_steps = [step["tool"] for step in snapshot["steps"] if step["kind"] == "tool_call"]
    finished_events = [frame.data for frame in frames if frame.event == "tool.finished"]
    assert [tool["summary"] for tool in tool_steps] == [event["summary"] for event in finished_events]
    assert [tool["outputPreview"] for tool in tool_steps] == [event["outputPreview"] for event in finished_events]
    assert [tool["outputCharacterCount"] for tool in tool_steps] == [event["outputCharacterCount"] for event in finished_events]
    assert [tool["boundArgumentNames"] for tool in tool_steps] == [["investigation_id"], ["investigation_id"]]


async def test_a_snapshot_is_for_its_owner_only(client: httpx.AsyncClient, chat: Chat, auth_headers: AuthHeaders) -> None:
    run_id = parse_frames((await ask(client, chat)).text)[0].data["answerRunId"]
    for other in (users.CLMJP_ADMIN_CHAD_READER, users.KEIGAN_ADMIN):
        response = await client.get(f"/api/chat/answer-runs/{run_id}", headers=await auth_headers(other))
        assert response.status_code == 403, other
    assert (await client.get(f"/api/chat/answer-runs/{run_id}")).status_code == 401
    assert (await client.get(f"/api/chat/answer-runs/{uuid.uuid4()}", headers=chat.headers)).status_code == 404


async def test_the_full_output_of_a_step_is_for_its_owner_only(client: httpx.AsyncClient, chat: Chat, auth_headers: AuthHeaders) -> None:
    frames = parse_frames((await ask(client, chat)).text)
    run_id, step_id = frames[0].data["answerRunId"], next(frame.data["runStepId"] for frame in frames if frame.event == "tool.started")
    response = await client.get(f"/api/chat/answer-runs/{run_id}/steps/{step_id}/output", headers=chat.headers)
    assert response.status_code == 200
    body = response.json()
    assert body["runStepId"] == step_id and body["output"]["evidence_code"] == "E2" and body["outputIsTruncated"] is False and len(body["modelViewSha256"]) == 64 and body["modelViewText"]
    forbidden = await client.get(f"/api/chat/answer-runs/{run_id}/steps/{step_id}/output", headers=await auth_headers(users.KEIGAN_ADMIN))
    assert forbidden.status_code == 403
    assert (await client.get(f"/api/chat/answer-runs/{run_id}/steps/{uuid.uuid4()}/output", headers=chat.headers)).status_code == 404


async def test_the_conversation_history_links_each_answer_to_its_run(client: httpx.AsyncClient, chat: Chat) -> None:
    frames = parse_frames((await ask(client, chat)).text)
    detail = (await client.get(f"/api/chat/conversations/{chat.conversation_id}", headers=chat.headers)).json()
    question, answer = detail["messages"]
    assert (question["authorRole"], question["messageText"]) == ("user", QUESTION) and (answer["authorRole"], answer["authorDisplayName"]) == ("assistant", "Keigan")
    assert answer["messageId"] == frames[-1].data["answer"]["messageId"] and answer["messageText"] == frames[-1].data["answer"]["markdown"]
    assert answer["messagePayload"]["answerRunId"] == frames[0].data["answerRunId"] and question["messagePayload"] == {"answerRunId": frames[0].data["answerRunId"]}
    assert {"T1", "T2"} <= {citation["code"] for citation in answer["messagePayload"]["citations"]}
    assert answer["messagePayload"]["isUnverified"] is False and answer["messagePayload"]["followUps"] is not None and answer["messagePayload"]["stopReason"] == "answered"


async def test_a_stopped_answers_question_links_its_run_in_the_history(client: httpx.AsyncClient, chat: Chat, monkeypatch: pytest.MonkeyPatch) -> None:
    release = asyncio.Event()
    use_gateway(monkeypatch, ScriptedGateway([blocked_turn(release, text="never shown")]))
    pending = asyncio.create_task(ask(client, chat))
    run_id = await wait_for_a_running_run(chat.conversation_id)
    stop = await client.post(f"/api/chat/answer-runs/{run_id}/cancel", headers=chat.headers)
    assert stop.status_code == 202 and stop.json() == {"answerRunId": run_id, "cancelRequested": True}
    frames = parse_frames((await asyncio.wait_for(pending, timeout=10)).text)
    assert [frame.event for frame in frames] == ["answer.started", "answer.failed"] and frames[-1].data["error"]["errorCode"] == "cancelled" and frames[-1].data["stopReason"] == "cancelled_by_user"
    assert frames[-1].data["error"]["isRetryable"] is False
    detail = (await client.get(f"/api/chat/conversations/{chat.conversation_id}", headers=chat.headers)).json()
    assert [message["authorRole"] for message in detail["messages"]] == ["user"] and detail["messages"][0]["messagePayload"] == {"answerRunId": run_id}


LEFT_RUNNING: list[str] = []  # the run part one leaves behind, for part two (the two tests run in file order)


# ── No answer outlives its test (the cause of a "database is locked" seen once in a full run) ───────────────────────────────────────
async def test_part_one_an_answer_left_running_by_a_test(client: httpx.AsyncClient, chat: Chat, monkeypatch: pytest.MonkeyPatch) -> None:
    use_gateway(monkeypatch, ScriptedGateway([blocked_turn(asyncio.Event(), text="never released")]))
    asyncio.create_task(ask(client, chat))
    LEFT_RUNNING.append(await wait_for_a_running_run(chat.conversation_id))
    assert application_context.answer_run_registry().live_runs()


async def test_part_two_the_next_test_finds_no_live_answer_and_the_run_was_ended_as_interrupted() -> None:
    (left_running_run_id,) = LEFT_RUNNING
    assert application_context.answer_run_registry().live_runs() == []
    async with open_session() as session:
        run = await session.get(ChatAnswerRun, left_running_run_id)
    assert (run.run_status, run.error_code) == (ChatAnswerRunStatus.FAILED, "answer_interrupted")


# ── AC-25: Stop ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_cancel_stops_the_run(client: httpx.AsyncClient, chat: Chat, monkeypatch: pytest.MonkeyPatch) -> None:
    release = asyncio.Event()
    use_gateway(monkeypatch, ScriptedGateway([Turn(requests=(request_for("get_evidence", {"evidence_code": "E2"}),)), blocked_turn(release, text="never shown")]))
    pending = asyncio.create_task(ask(client, chat))
    run_id = await wait_for_a_running_run(chat.conversation_id)
    await wait_for_a_finished_tool_call(client, chat, run_id)
    assert (await client.post(f"/api/chat/answer-runs/{run_id}/cancel", headers=chat.headers)).status_code == 202
    await asyncio.wait_for(pending, timeout=10)
    snapshot = (await client.get(f"/api/chat/answer-runs/{run_id}", headers=chat.headers)).json()
    assert (snapshot["status"], snapshot["stopReason"], snapshot["answer"], snapshot["error"]["errorCode"]) == ("cancelled", "cancelled_by_user", None, "cancelled")
    assert snapshot["steps"][1]["status"] == "succeeded" and snapshot["steps"][-1]["status"] == "cancelled"
    again = await client.post(f"/api/chat/answer-runs/{run_id}/cancel", headers=chat.headers)
    assert again.status_code == 409 and again.json()["errorCode"] == "answer_not_running" and again.json()["answerRunId"] == run_id


async def test_cancel_is_for_the_owner_only_and_needs_a_sign_in(client: httpx.AsyncClient, chat: Chat, auth_headers: AuthHeaders) -> None:
    run_id = parse_frames((await ask(client, chat)).text)[0].data["answerRunId"]
    assert (await client.post(f"/api/chat/answer-runs/{run_id}/cancel", headers=await auth_headers(users.KEIGAN_ADMIN))).status_code == 403
    assert (await client.post(f"/api/chat/answer-runs/{run_id}/cancel")).status_code == 401
    assert (await client.post(f"/api/chat/answer-runs/{uuid.uuid4()}/cancel", headers=chat.headers)).status_code == 404


async def test_the_old_message_endpoint_still_answers_the_global_chat(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    headers = await auth_headers(READER)
    created = await client.post("/api/chat/conversations", headers=headers, json={"conversationScope": "keigan_ai_chat"})
    response = await client.post(f"/api/chat/conversations/{created.json()['conversationId']}/messages", headers=headers, json={"messageText": "What is the architecture of my application?"})
    assert response.status_code == 200 and response.json()["authorRole"] == "assistant"


async def global_chat(client: httpx.AsyncClient, headers: dict[str, str]) -> Chat:
    created = await client.post("/api/chat/conversations", headers=headers, json={"conversationScope": "keigan_ai_chat"})
    assert created.status_code == 201, created.text
    return Chat(created.json()["conversationId"], "", headers)


async def test_the_answers_endpoint_answers_a_global_conversation_with_the_global_scope(client: httpx.AsyncClient, auth_headers: AuthHeaders, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_provider", LlmProviderName.MOCK)
    chat = await global_chat(client, await auth_headers(READER))
    response = await ask(client, chat, "How are the SLOs doing?")
    assert response.status_code == 200, response.text
    frames = parse_frames(response.text)
    assert frames[0].event == "answer.started" and frames[0].data["scope"] == "global" and frames[-1].event == "answer.completed"
    assert [frame.data["tool"]["name"] for frame in frames if frame.event == "tool.started"] == ["get_slo_status"]
    assert "[T1]" in frames[-1].data["answer"]["markdown"]


async def test_a_global_answer_is_hidden_on_every_read_path_once_the_person_cannot_read_an_application_it_used(
    client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "llm_provider", LlmProviderName.MOCK)
    chat = await global_chat(client, await auth_headers(READER))
    run_id = parse_frames((await ask(client, chat, "How are the SLOs doing?")).text)[0].data["answerRunId"]
    snapshot = await client.get(f"/api/chat/answer-runs/{run_id}", headers=chat.headers)
    tool_step_id = next(step["runStepId"] for step in snapshot.json()["steps"] if step["kind"] == "tool_call")
    assert snapshot.status_code == 200 and (await client.get(f"/api/chat/answer-runs/{run_id}/steps/{tool_step_id}/output", headers=chat.headers)).status_code == 200
    async with open_session() as session:  # the run used CHAD too, which this reader cannot read: the same state as a reader who has since lost it
        await session.execute(update(ChatAnswerRun).where(ChatAnswerRun.answer_run_id == run_id).values(used_application_ids_json=[seed_context.application_ids_by_code["CHAD"]]))
    for path in (f"/api/chat/answer-runs/{run_id}", f"/api/chat/answer-runs/{run_id}/steps/{tool_step_id}/output"):
        refused = await client.get(path, headers=chat.headers)
        assert refused.status_code == 403 and "SLO" not in refused.text
    conversation = await client.get(f"/api/chat/conversations/{chat.conversation_id}", headers=chat.headers)
    answer = next(message for message in conversation.json()["messages"] if message["authorRole"] == "assistant")
    assert answer["messageText"] == "You no longer have access to an application this answer used." and answer["messagePayload"] == {"answerRunId": run_id}


# ── AC-23 and AC-24: through a real server ───────────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
async def live_server_url(seed_context) -> AsyncIterator[str]:
    from keigan.main import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="on"))
    serving = asyncio.create_task(server.serve())
    while not server.started:
        assert not serving.done(), "the test server stopped while starting"
        await asyncio.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    await asyncio.wait_for(serving, timeout=15)


async def test_events_are_not_buffered(live_server_url: str, chat: Chat, monkeypatch: pytest.MonkeyPatch) -> None:
    """The run is held back at its second model turn: if the first tool's frames arrive, the server is not collecting the response before sending it."""
    release = asyncio.Event()
    use_gateway(monkeypatch, ScriptedGateway([Turn(requests=(request_for("get_evidence", {"evidence_code": "E2"}),)), blocked_turn(release, text="Release 41 came first [T1].")]))
    seen: list[str] = []
    async with httpx.AsyncClient(base_url=live_server_url, timeout=15) as live_client:
        async with live_client.stream(
            "POST", f"/api/chat/conversations/{chat.conversation_id}/answers", headers={**chat.headers, **EVENT_STREAM}, json={"messageText": QUESTION, "clientRequestId": str(uuid.uuid4())},
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream") and response.headers["x-accel-buffering"] == "no" and response.headers["cache-control"] == "no-store"
            lines = response.aiter_lines()
            async for line in lines:
                if line.startswith("event: "):
                    seen.append(line.removeprefix("event: "))
                if seen[-1:] == ["tool.finished"]:
                    break
            assert seen == ["answer.started", "tool.started", "tool.finished"]
            assert len(await running_runs_of(chat.conversation_id)) == 1  # the run has not finished: these frames really were sent while it was running
            release.set()
            async for line in lines:
                if line.startswith("event: "):
                    seen.append(line.removeprefix("event: "))
    assert seen[-2:] == ["answer.text", "answer.completed"]


async def test_the_run_finishes_after_the_client_disconnects(live_server_url: str, chat: Chat, monkeypatch: pytest.MonkeyPatch) -> None:
    release = asyncio.Event()
    use_gateway(monkeypatch, ScriptedGateway([Turn(requests=(request_for("get_evidence", {"evidence_code": "E2"}),)), blocked_turn(release, text="Release 41 came first [T1].")]))
    async with httpx.AsyncClient(base_url=live_server_url, timeout=15) as live_client:
        async with live_client.stream(
            "POST", f"/api/chat/conversations/{chat.conversation_id}/answers", headers={**chat.headers, **EVENT_STREAM}, json={"messageText": QUESTION, "clientRequestId": str(uuid.uuid4())},
        ) as response:
            async for line in response.aiter_lines():
                if line == "event: tool.started":
                    break
        # the connection is closed here, with the run still going
        run_id = (await running_runs_of(chat.conversation_id))[0].answer_run_id
        release.set()
        snapshot: dict = {}
        for _ in range(200):
            snapshot = (await live_client.get(f"/api/chat/answer-runs/{run_id}", headers=chat.headers)).json()
            if snapshot["status"] != "running":
                break
            await asyncio.sleep(0.05)
    assert snapshot["status"] == "completed" and snapshot["answer"]["markdown"] == "Release 41 came first [T1]." and snapshot["toolCallCount"] == 1


async def test_a_stopped_stream_reads_the_finished_answer_from_the_snapshot(live_server_url: str, chat: Chat, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reconnecting means polling the snapshot (spec 7.5): after a dropped stream the whole answer is there."""
    use_gateway(monkeypatch, ScriptedGateway([Turn(text="E1 is the error spike [E1].")]))
    async with httpx.AsyncClient(base_url=live_server_url, timeout=15) as live_client:
        async with live_client.stream(
            "POST", f"/api/chat/conversations/{chat.conversation_id}/answers", headers={**chat.headers, **EVENT_STREAM}, json={"messageText": "What is E1?", "clientRequestId": str(uuid.uuid4())},
        ) as response:
            async for line in response.aiter_lines():
                if line == "event: answer.started":
                    break
        run_id = (await runs_of(chat.conversation_id))[0].answer_run_id
        for _ in range(200):
            snapshot = (await live_client.get(f"/api/chat/answer-runs/{run_id}", headers=chat.headers)).json()
            if snapshot["status"] != "running":
                break
            await asyncio.sleep(0.05)
    assert snapshot["status"] == "completed" and snapshot["answer"]["markdown"] == "E1 is the error spike [E1]."
