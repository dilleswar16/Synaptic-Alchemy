"""keigan/services/alert_service.py: a maintenance window may only name services of its own application (H11: the list is now a foreign key, so a bad id must be a 422, never a database error)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.dtos.alert_dtos import MaintenanceWindowRequest, MaintenanceWindowUpdateRequest
from keigan.entities.alert_entities import Alert, AlertGroup
from keigan.entities.status_values import AlertGroupStatus
from keigan.exceptions.keigan_exceptions import BusinessValidationException
from keigan.security.current_user import CurrentUser
from keigan.services.alert_pipeline_service import OPEN_GROUP_STATUSES
from keigan.services.alert_service import AlertService
from support import users
from support.alerts import AlertSourceFixture, generic_alert_payload, post_alert
from support.http import AuthHeaders
from support.jobs import drain_jobs

pytestmark = pytest.mark.usefixtures("seed_context")
ADMIN = CurrentUser(user_principal_name="admin@example.com", display_name="Admin", email_address=None, group_names=frozenset(), group_object_ids=frozenset(), is_keigan_admin=True)


def window_request(service_ids: list[str]) -> MaintenanceWindowRequest:
    starts_at = datetime.now(UTC)
    return MaintenanceWindowRequest(window_name="Patch window", applies_to_service_ids=service_ids, starts_at=starts_at, ends_at=starts_at + timedelta(hours=1))


async def test_a_window_for_a_service_that_does_not_exist_is_refused_with_a_clear_message(seed_context) -> None:
    async with open_session() as session:
        with pytest.raises(BusinessValidationException) as refusal:
            await AlertService(session).create_maintenance_window(ADMIN, seed_context.application_ids_by_code["CLMJP"], window_request(["no-such-service"]))
    assert refusal.value.extra["fieldErrors"] == [{"field": "appliesToServiceIds", "message": "Unknown service."}]


async def test_a_window_cannot_name_a_service_of_another_application(seed_context) -> None:
    other_application_service = next(service_id for key, service_id in seed_context.service_ids_by_key.items() if key.startswith("CHAD/"))
    async with open_session() as session:
        with pytest.raises(BusinessValidationException):
            await AlertService(session).create_maintenance_window(ADMIN, seed_context.application_ids_by_code["CLMJP"], window_request([other_application_service]))


async def test_updating_a_window_to_an_unknown_service_is_refused_and_leaves_the_list_unchanged(seed_context) -> None:
    clmjp = seed_context.application_ids_by_code["CLMJP"]
    own_service = seed_context.service_id("CLMJP", "claims-api")
    async with open_session() as session:
        created = await AlertService(session).create_maintenance_window(ADMIN, clmjp, window_request([own_service]))
    async with open_session() as session:
        with pytest.raises(BusinessValidationException):
            await AlertService(session).update_maintenance_window(ADMIN, clmjp, created.maintenance_window_id, MaintenanceWindowUpdateRequest(applies_to_service_ids=["no-such-service"]))
    async with open_session() as session:
        windows = {window.maintenance_window_id: window for window in await AlertService(session).list_maintenance_windows(clmjp)}
    assert windows[created.maintenance_window_id].applies_to_service_ids == [own_service]


# ── Why the alerts of a group belong together (roadmap B3) ─────────────────────
GROUP_WINDOW_MINUTES = 15  # deliberately not the default (10): the sentence must carry the application's own policy


@pytest.fixture
async def active_grouping(client: httpx.AsyncClient, auth_headers: AuthHeaders, alert_source: AlertSourceFixture):
    """CLMJP in Active mode (so alerts really join groups) with a group window that is not the default; put back to the defaults afterwards.

    Groups left open by earlier tests are resolved first: a new alert would otherwise join one of them (or its incident) instead of starting its own group."""
    async with open_session() as session:
        for open_group in (await session.scalars(select(AlertGroup).where(AlertGroup.application_id == alert_source.application_id, AlertGroup.group_status.in_(OPEN_GROUP_STATUSES)))).all():
            open_group.group_status = AlertGroupStatus.RESOLVED
    headers = await auth_headers(users.CLMJP_ADMIN_CHAD_READER)
    url = f"/api/applications/{alert_source.application_id}/noise-policy"
    settings = (await client.get(url, headers=headers)).json()["policySettings"]
    updated = await client.put(url, headers=headers, json={"policyMode": "active", "policySettings": {**settings, "groupWindowMinutes": GROUP_WINDOW_MINUTES}})
    assert updated.status_code == 200, updated.text
    yield headers
    await client.put(url, headers=headers, json={"policyMode": "observe", "resetToDefaults": True})


def sev1_payload(rule_id: str, *, service: str | None, resource: str) -> dict[str, object]:
    payload = {**generic_alert_payload(rule_id), "severity": 1, "resourceRef": resource}
    if service is None:
        payload.pop("service")
    else:
        payload["service"] = service
    return payload


async def ingest(client: httpx.AsyncClient, source: AlertSourceFixture, payloads: list[dict[str, object]]) -> None:
    for payload in payloads:
        assert (await post_alert(client, source, payload)).status_code == 202
        await drain_jobs()


async def group_id_of_rule(rule_id: str) -> str:
    async with open_session() as session:
        group_ids = set((await session.scalars(select(Alert.alert_group_id).where(Alert.rule_identifier == rule_id))).all())
    assert len(group_ids) == 1 and None not in group_ids
    return group_ids.pop()


async def detail_and_list_item(client: httpx.AsyncClient, headers: dict[str, str], application_id: str, alert_group_id: str) -> tuple[dict, dict]:
    detail = await client.get(f"/api/alert-groups/{alert_group_id}", headers=headers)
    listing = await client.get("/api/alert-groups", params={"applicationIds": application_id, "pageSize": 200}, headers=headers)
    assert detail.status_code == 200 and listing.status_code == 200
    return detail.json(), next(item for item in listing.json()["items"] if item["alertGroupId"] == alert_group_id)


async def test_alerts_of_the_same_rule_are_grouped_for_that_rule_within_the_policy_window(client, alert_source, active_grouping) -> None:
    rule_id = f"why-same-rule-{uuid.uuid4().hex[:8]}"
    await ingest(client, alert_source, [sev1_payload(rule_id, service=None, resource="pytest-nowhere-a"), sev1_payload(rule_id, service=None, resource="pytest-nowhere-b")])

    detail, listed = await detail_and_list_item(client, active_grouping, alert_source.application_id, await group_id_of_rule(rule_id))

    expected = {"code": "same_rule", "parameters": {"ruleName": f"Test rule {rule_id}", "alertCount": 2, "windowMinutes": GROUP_WINDOW_MINUTES}}
    assert detail["groupingReason"] == expected
    assert listed["groupingReason"] == expected


async def test_alerts_on_the_same_service_are_grouped_for_that_service(client, alert_source, active_grouping) -> None:
    rule_ids = [f"why-same-service-{uuid.uuid4().hex[:8]}" for _ in range(2)]
    await ingest(client, alert_source, [sev1_payload(rule_id, service="claims-sql", resource=f"pytest-resource-{index}") for index, rule_id in enumerate(rule_ids)])

    detail, listed = await detail_and_list_item(client, active_grouping, alert_source.application_id, await group_id_of_rule(rule_ids[0]))

    on_the_service = sum(1 for member in detail["members"] if member["serviceName"] == "claims-sql")
    assert on_the_service >= 2
    assert detail["groupingReason"] == {"code": "same_service", "parameters": {"serviceName": "claims-sql", "alertCount": on_the_service, "windowMinutes": GROUP_WINDOW_MINUTES}}
    assert listed["groupingReason"] == detail["groupingReason"]


async def test_alerts_on_dependent_services_are_grouped_for_the_dependency(client, alert_source, active_grouping) -> None:
    """The seed declares claims-workflow as calling claims-intake-func."""
    rule_ids = [f"why-dependency-{uuid.uuid4().hex[:8]}" for _ in range(2)]
    await ingest(client, alert_source, [sev1_payload(rule_ids[0], service="claims-workflow", resource="pytest-dependency-0"), sev1_payload(rule_ids[1], service="claims-intake-func", resource="pytest-dependency-1")])

    detail, listed = await detail_and_list_item(client, active_grouping, alert_source.application_id, await group_id_of_rule(rule_ids[0]))

    assert detail["groupingReason"] == {"code": "dependency", "parameters": {"serviceName": "claims-intake-func", "relatedServiceName": "claims-workflow", "windowMinutes": GROUP_WINDOW_MINUTES}}
    assert listed["groupingReason"] == detail["groupingReason"]


async def test_a_group_of_one_alert_says_so(client, alert_source, active_grouping) -> None:
    rule_id = f"why-single-{uuid.uuid4().hex[:8]}"
    await ingest(client, alert_source, [sev1_payload(rule_id, service=None, resource="pytest-nowhere-single")])

    detail, listed = await detail_and_list_item(client, active_grouping, alert_source.application_id, await group_id_of_rule(rule_id))

    assert detail["memberAlertCount"] == 1
    assert detail["groupingReason"] == {"code": "single_alert", "parameters": {}}
    assert listed["groupingReason"] == detail["groupingReason"]


async def test_a_group_with_unrelated_alerts_and_no_recorded_reason_says_it_was_not_recorded(client, alert_source, auth_headers) -> None:
    """Such a group can only exist from before reasons could be derived (or from edited data), so the answer is 'not recorded', never a guess."""
    async with open_session() as session:
        group = AlertGroup(application_id=alert_source.application_id, group_title="Legacy group", group_status="open", member_alert_count=2, highest_severity_level=2)
        session.add(group)
        await session.flush()
        for index in range(2):
            session.add(Alert(application_id=alert_source.application_id, alert_fingerprint=uuid.uuid4().hex, rule_identifier=f"legacy-{uuid.uuid4().hex[:8]}", rule_name=f"Legacy rule {index}", alert_group_id=group.alert_group_id))
        group_id = group.alert_group_id

    detail, listed = await detail_and_list_item(client, await auth_headers(users.CLMJP_ADMIN_CHAD_READER), alert_source.application_id, group_id)

    assert detail["groupingReason"] == {"code": "not_recorded", "parameters": {}}
    assert listed["groupingReason"] == detail["groupingReason"]
