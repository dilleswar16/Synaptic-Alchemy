"""The events of a real answer carry exactly the fields the TypeScript event types of ``askKeiganApi.ts`` declare (spec 23, 7.3), event by event."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from keigan.services.ask_keigan_cancellation import CancellationFlag
from keigan.services.ask_keigan_events import AnswerEvent, AnswerEventName
from support.ask_keigan_conversations import seed_investigation
from support.ask_keigan_runs import Finished, ask, profile_for, user
from support.ask_keigan_typescript import event_type_names, interface_fields

pytestmark = pytest.mark.usefixtures("seed_context")

ADMIN = user("keigan.admin@keigan.local", "KEIGAN_admin", is_admin=True)
EVENT_INTERFACES = {
    AnswerEventName.ANSWER_STARTED: "AnswerStartedEvent", AnswerEventName.ANSWER_TEXT: "AnswerTextEvent", AnswerEventName.TURN_NOTE: "TurnNoteEvent",
    AnswerEventName.TOOL_STARTED: "ToolStartedEvent", AnswerEventName.TOOL_PROGRESS: "ToolProgressEvent", AnswerEventName.TOOL_FINISHED: "ToolFinishedEvent",
    AnswerEventName.ANSWER_COMPLETED: "AnswerCompletedEvent", AnswerEventName.ANSWER_FAILED: "AnswerFailedEvent",
}


@dataclass(frozen=True)
class Runs:
    evidence_and_timeline: Finished
    log_query: Finished
    stopped: Finished


@pytest.fixture(scope="module")
async def runs(seed_context) -> Runs:
    investigation = await seed_investigation(seed_context.application_ids_by_code["CLMJP"])
    profile = await profile_for(ADMIN, investigation.investigation_id)
    evidence_and_timeline = await ask(profile, "Show me evidence E2 and what the timeline says before it", current_user=ADMIN)
    log_query = await ask(profile, "How many errors did claims-api log in the last hour?", current_user=ADMIN)
    flag = CancellationFlag()
    flag.request()
    stopped = await ask(profile, "Show me evidence E2", current_user=ADMIN, flag=flag)
    return Runs(evidence_and_timeline, log_query, stopped)


def fields_declared_for(name: AnswerEventName) -> set[str]:
    """What the screen reads from an event: the envelope and the event's own fields (``type`` is added by the browser from the frame's ``event:`` line, not sent)."""
    return (interface_fields("AnswerEventBase") | interface_fields(EVENT_INTERFACES[name])) - {"type"}


def events_named(events: list[AnswerEvent], name: AnswerEventName) -> list[AnswerEvent]:
    return [event for event in events if event.name is name]


@pytest.mark.parametrize("name", [name for name in EVENT_INTERFACES if name not in (AnswerEventName.ANSWER_FAILED, AnswerEventName.TURN_NOTE)])
def test_every_event_carries_exactly_the_fields_the_screen_declares(runs: Runs, name: AnswerEventName) -> None:
    events = events_named(runs.evidence_and_timeline.events + runs.log_query.events, name)
    assert events, f"no {name} event was produced by the offline answers"
    for event in events:
        assert set(event.data) == fields_declared_for(name), name


def test_the_failure_event_carries_exactly_the_fields_the_screen_declares(runs: Runs) -> None:
    (event,) = events_named(runs.stopped.events, AnswerEventName.ANSWER_FAILED)
    assert set(event.data) == fields_declared_for(AnswerEventName.ANSWER_FAILED)
    assert set(event.data["error"]) == interface_fields("ProblemSummary")


def test_the_event_interfaces_name_every_event_of_the_protocol() -> None:
    assert event_type_names() == {name.value for name in AnswerEventName}


def test_a_note_event_carries_the_step_number_the_screen_orders_by() -> None:
    assert interface_fields("TurnNoteEvent") - {"type"} == {"turnNumber", "runStepId", "sequenceNumber", "text"}
