"""keigan/services/alert_service.py: a maintenance window may only name services of its own application (H11: the list is now a foreign key, so a bad id must be a 422, never a database error)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from keigan.config.database_config import open_session
from keigan.dtos.alert_dtos import MaintenanceWindowRequest, MaintenanceWindowUpdateRequest
from keigan.exceptions.keigan_exceptions import BusinessValidationException
from keigan.security.current_user import CurrentUser
from keigan.services.alert_service import AlertService

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
