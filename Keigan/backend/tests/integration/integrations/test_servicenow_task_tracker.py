"""keigan/integrations/servicenow_task_tracker.py: an action item becomes a ServiceNow task and its state is read back (spec 29, 4.7; roadmap D1)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from keigan.config.settings import IntegrationMode, Settings, get_settings
from keigan.exceptions.keigan_exceptions import IntegrationException
from keigan.integrations.action_item_tracker import ActionItemSnapshot, ExternalTaskTracker
from keigan.integrations.servicenow_client import ServiceNowClient
from keigan.integrations.servicenow_task_tracker import ServiceNowTaskTracker
from keigan.integrations.simulation.servicenow_simulator import ServiceNowSimulator
from keigan.services.action_item_external_rules import ExternalTaskOutcome

SNAPSHOT = ActionItemSnapshot(
    title="Add an alert on connection pool saturation", details="Alert at 80% so the team hears before requests fail.", action_type="detect", priority="top", due_on=date(2026, 12, 15), incident_reference="INC4100012",
)


def simulated_tracker() -> ServiceNowTaskTracker:
    return ServiceNowTaskTracker(get_settings(), ServiceNowClient(get_settings(), secret_store=None))  # type: ignore[arg-type]


def test_the_tracker_is_a_tracker() -> None:
    assert isinstance(simulated_tracker(), ExternalTaskTracker) and simulated_tracker().system_name == "servicenow"


async def test_a_task_is_created_with_its_number_and_identifier(seed_context) -> None:
    reference = await simulated_tracker().create_task(SNAPSHOT)
    assert reference.number.startswith("TASK") and len(reference.record_identifier) == 32 and reference.url and reference.number in reference.url


async def test_the_task_carries_the_mapped_priority_the_due_date_and_the_incident_but_nothing_else(seed_context) -> None:
    reference = await simulated_tracker().create_task(SNAPSHOT)
    record = (await ServiceNowSimulator().read_tasks([reference.record_identifier]))[0]
    assert record["priority"] == "1" and record["short_description"] == SNAPSHOT.title and record["due_date"].startswith("2026-12-15")
    assert "Alert at 80%" in record["description"] and "INC4100012" in record["description"] and "detect" in record["description"]
    assert set(record) <= {"sys_id", "number", "short_description", "description", "priority", "due_date", "state", "sys_updated_on", "sys_created_on"}


async def test_a_long_title_is_cut_to_what_servicenow_accepts(seed_context) -> None:
    reference = await simulated_tracker().create_task(ActionItemSnapshot("T" * 300, None, "prevent", "normal", None, None))
    record = (await ServiceNowSimulator().read_tasks([reference.record_identifier]))[0]
    assert len(record["short_description"]) == 160 and "due_date" not in record


async def test_a_new_task_is_open_and_closing_it_in_servicenow_is_read_back(seed_context) -> None:
    tracker = simulated_tracker()
    reference = await tracker.create_task(SNAPSHOT)
    state = (await tracker.read_task_states([reference.record_identifier]))[reference.record_identifier]
    assert state.outcome == ExternalTaskOutcome.OPEN and state.status_text == "Open"
    await ServiceNowSimulator().update_task(reference.record_identifier, {"state": "Closed Complete"})
    state = (await tracker.read_task_states([reference.record_identifier]))[reference.record_identifier]
    assert state.outcome == ExternalTaskOutcome.COMPLETE and state.status_text == "Closed Complete"


async def test_a_task_that_was_deleted_in_servicenow_is_simply_absent(seed_context) -> None:
    assert await simulated_tracker().read_task_states(["f" * 32]) == {}


async def test_an_empty_request_reads_nothing(seed_context) -> None:
    assert await simulated_tracker().read_task_states([]) == {}


# ── The live path: what is sent to ServiceNow ──────────────────────────────────────────────────


class RecordingClient(ServiceNowClient):
    def __init__(self) -> None:
        super().__init__(Settings(_env_file=None, servicenow_mode=IntegrationMode.LIVE, servicenow_instance_url="https://example.service-now.com"), secret_store=None)  # type: ignore[arg-type]
        self.requests: list[tuple[str, str, dict[str, Any] | None, dict[str, Any] | None]] = []

    async def _send_request(self, method: str, path: str, params: dict[str, str] | None = None, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.requests.append((method, path, params, json_body))
        if method == "POST":
            return {"result": {"sys_id": "a" * 32, "number": "TASK0012345", "state": "Open"}}
        return {"result": [{"sys_id": "a" * 32, "number": "TASK0012345", "state": "Closed Incomplete"}]}


async def test_live_creation_posts_to_the_configured_table() -> None:
    client = RecordingClient()
    reference = await ServiceNowTaskTracker(client.settings, client).create_task(SNAPSHOT)
    method, path, _params, body = client.requests[0]
    assert (method, path) == ("POST", "/api/now/table/task") and body["priority"] == "1" and body["short_description"] == SNAPSHOT.title
    assert reference.number == "TASK0012345" and reference.url == "https://example.service-now.com/nav_to.do?uri=task.do?sysparm_query=number=TASK0012345"


async def test_live_reading_asks_only_for_the_identifiers_it_was_given() -> None:
    client = RecordingClient()
    states = await ServiceNowTaskTracker(client.settings, client).read_task_states(["a" * 32])
    method, path, params, _body = client.requests[0]
    assert (method, path) == ("GET", "/api/now/table/task") and params["sysparm_query"] == f"sys_idIN{'a' * 32}" and states["a" * 32].outcome == ExternalTaskOutcome.INCOMPLETE


async def test_an_identifier_that_is_not_a_servicenow_id_is_never_put_in_the_query() -> None:
    client = RecordingClient()
    with pytest.raises(IntegrationException):
        await ServiceNowTaskTracker(client.settings, client).read_task_states(["a" * 32, "x^ORnumber!=0"])
    assert client.requests == []
