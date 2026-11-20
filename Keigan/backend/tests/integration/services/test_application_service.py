"""keigan/services/application_service.py: access groups (H7) and the Entra rules around going live."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from keigan.config.database_config import open_session
from keigan.config.settings import AuthenticationMode, get_settings
from keigan.dtos.application_dtos import AccessUpdateRequest, ApplicationCreateRequest
from keigan.dtos.notification_dtos import StakeholderResponse
from keigan.entities.application_entities import Application
from keigan.entities.notification_entities import NotificationDelivery
from keigan.entities.status_values import TeamMemberStatus
from keigan.exceptions.keigan_exceptions import BusinessValidationException, ForbiddenException
from keigan.security.current_user import CurrentUser
from keigan.services.application_service import ApplicationService
from keigan.services.stakeholder_service import StakeholderService

pytestmark = pytest.mark.usefixtures("seed_context")  # creates the schema

GROUP_OBJECT_ID = "33333333-3333-3333-3333-333333333333"


def user(user_principal_name: str, *, is_keigan_admin: bool, group_names: set[str] | None = None) -> CurrentUser:
    return CurrentUser(
        user_principal_name=user_principal_name, display_name=user_principal_name, email_address=None,
        group_names=frozenset(group_names or set()), group_object_ids=frozenset(), is_keigan_admin=is_keigan_admin,
    )


async def create_application(code: str, lifecycle_status: str = "draft") -> str:
    async with open_session() as session:
        application = Application(
            application_name=f"Access {code}", application_code=code, lifecycle_status=lifecycle_status,
            admin_group_name=f"{code}_admin", reader_group_name=f"{code}_reader", created_by_user_principal_name="system:test",
        )
        session.add(application)
        await session.flush()
        return application.application_id


async def test_application_admin_cannot_change_the_group_object_ids() -> None:
    application_id = await create_application("ACC1")
    application_admin = user("acc1.admin@example.com", is_keigan_admin=False, group_names={"ACC1_admin"})
    async with open_session() as session:
        with pytest.raises(ForbiddenException) as denial:
            await ApplicationService(session).update_access(application_admin, application_id, AccessUpdateRequest(admin_group_object_id=GROUP_OBJECT_ID))
    assert denial.value.detail == "Only Keigan admins can change the group object IDs. Run 'Check in Entra' to link the groups."


async def test_keigan_admin_can_set_the_group_object_ids() -> None:
    application_id = await create_application("ACC2")
    keigan_admin = user("keigan.admin@example.com", is_keigan_admin=True)
    async with open_session() as session:
        response = await ApplicationService(session).update_access(
            keigan_admin, application_id, AccessUpdateRequest(admin_group_object_id=f" {GROUP_OBJECT_ID} ", reader_group_object_id=GROUP_OBJECT_ID)
        )
    assert (response.admin_group_object_id, response.reader_group_object_id) == (GROUP_OBJECT_ID, GROUP_OBJECT_ID)


async def test_group_object_id_that_is_not_a_guid_is_rejected_with_a_field_error() -> None:
    application_id = await create_application("ACC3")
    keigan_admin = user("keigan.admin@example.com", is_keigan_admin=True)
    async with open_session() as session:
        with pytest.raises(BusinessValidationException) as rejection:
            await ApplicationService(session).update_access(keigan_admin, application_id, AccessUpdateRequest(admin_group_object_id="KEIGAN_admin"))
    assert rejection.value.extra["fieldErrors"] == [{"field": "adminGroupObjectId", "message": "Enter the group's object ID as a GUID (for example 3f2a9c1b-0d4e-4c7a-9b1f-2e8d6a5c4b30)."}]


async def test_application_cannot_go_live_with_entra_sign_in_until_its_groups_are_linked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "auth_mode", AuthenticationMode.ENTRA)
    application_id = await create_application("ACC4")
    keigan_admin = user("keigan.admin@example.com", is_keigan_admin=True)
    async with open_session() as session:
        with pytest.raises(BusinessValidationException) as rejection:
            await ApplicationService(session).go_live(keigan_admin, application_id)
    assert rejection.value.detail == (
        "The application's access groups are not linked to Entra yet, so nobody could open it after go-live. "
        "Run 'Check in Entra' on the Access step first."
    )


# ── H7: new applications get their group object ids from Entra ─────────────────
async def test_new_application_is_linked_to_its_entra_groups_by_object_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from keigan.dtos.application_dtos import ApplicationCreateRequest
    from keigan.integrations.microsoft_graph_client import MicrosoftGraphClient

    group_ids = {"ACC5_admin": "44444444-4444-4444-4444-444444444444", "ACC5_reader": "55555555-5555-5555-5555-555555555555"}

    async def find_group(_self: object, display_name: str | None, object_id: str | None) -> dict[str, str] | None:
        return {"id": group_ids[display_name], "displayName": display_name} if display_name in group_ids else None

    monkeypatch.setattr(get_settings(), "auth_mode", AuthenticationMode.ENTRA)
    monkeypatch.setattr(MicrosoftGraphClient, "find_group", find_group)
    keigan_admin = user("keigan.admin@example.com", is_keigan_admin=True)
    async with open_session() as session:
        application = await ApplicationService(session).create_application(
            keigan_admin, ApplicationCreateRequest(application_name="Acc five", application_code="ACC5")
        )
        stored = await session.get(Application, application.application_id)
    assert (stored.admin_group_object_id, stored.reader_group_object_id) == tuple(group_ids.values())


async def test_new_application_is_still_created_when_entra_cannot_be_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    from keigan.dtos.application_dtos import ApplicationCreateRequest
    from keigan.exceptions.keigan_exceptions import IntegrationException
    from keigan.integrations.microsoft_graph_client import MicrosoftGraphClient

    async def find_group(_self: object, display_name: str | None, object_id: str | None) -> dict[str, str] | None:
        raise IntegrationException("Graph is down.")

    monkeypatch.setattr(get_settings(), "auth_mode", AuthenticationMode.ENTRA)
    monkeypatch.setattr(MicrosoftGraphClient, "find_group", find_group)
    async with open_session() as session:
        application = await ApplicationService(session).create_application(
            user("keigan.admin@example.com", is_keigan_admin=True), ApplicationCreateRequest(application_name="Acc six", application_code="ACC6")
        )
        stored = await session.get(Application, application.application_id)
    assert (stored.admin_group_object_id, stored.reader_group_object_id) == (None, None)


# ── Two Entra groups with the same name are never guessed between ───────────────
AMBIGUOUS_GROUP_MESSAGE = "Two or more Entra groups are named 'ACC7_admin'. An admin must link the right group by its object ID in 'Check in Entra'."


async def test_new_application_is_still_created_when_two_entra_groups_share_a_name(monkeypatch: pytest.MonkeyPatch) -> None:
    from keigan.dtos.application_dtos import ApplicationCreateRequest
    from keigan.exceptions.keigan_exceptions import AmbiguousGroupNameException
    from keigan.integrations.microsoft_graph_client import MicrosoftGraphClient

    async def find_group(_self: object, display_name: str | None, object_id: str | None) -> dict[str, str] | None:
        raise AmbiguousGroupNameException(AMBIGUOUS_GROUP_MESSAGE)

    monkeypatch.setattr(get_settings(), "auth_mode", AuthenticationMode.ENTRA)
    monkeypatch.setattr(MicrosoftGraphClient, "find_group", find_group)
    async with open_session() as session:
        application = await ApplicationService(session).create_application(
            user("keigan.admin@example.com", is_keigan_admin=True), ApplicationCreateRequest(application_name="Acc seven", application_code="ACC7")
        )
        stored = await session.get(Application, application.application_id)
    assert (stored.admin_group_object_id, stored.reader_group_object_id) == (None, None)


async def test_check_in_entra_tells_the_admin_to_link_by_object_id_when_two_groups_share_a_name(monkeypatch: pytest.MonkeyPatch) -> None:
    from keigan.exceptions.keigan_exceptions import AmbiguousGroupNameException
    from keigan.integrations.microsoft_graph_client import MicrosoftGraphClient

    async def find_group(_self: object, display_name: str | None, object_id: str | None) -> dict[str, str] | None:
        raise AmbiguousGroupNameException(AMBIGUOUS_GROUP_MESSAGE)

    monkeypatch.setattr(get_settings(), "auth_mode", AuthenticationMode.ENTRA)
    monkeypatch.setattr(MicrosoftGraphClient, "find_group", find_group)
    application_id = await create_application("ACC8")
    async with open_session() as session:
        response = await ApplicationService(session).verify_access_groups(user("keigan.admin@example.com", is_keigan_admin=True), application_id)
        stored = await session.get(Application, application_id)
    assert [(result.role, result.exists, result.message) for result in response.results] == [
        ("admin", None, AMBIGUOUS_GROUP_MESSAGE), ("reader", None, AMBIGUOUS_GROUP_MESSAGE),
    ]
    assert (stored.admin_group_object_id, stored.reader_group_object_id) == (None, None)


class TestSloDataFailureIsLoggedAndTheListStillLoads:
    async def test_a_failed_slo_summary_gives_no_compliance_and_logs_a_warning_that_names_the_applications(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        import logging
        from types import SimpleNamespace

        from keigan.services.application_service import ApplicationService
        from keigan.services.slo_service import SloService

        async def unavailable(self: SloService, application_ids: list[str]) -> list[dict[str, object]]:
            raise RuntimeError("slo store unavailable")

        monkeypatch.setattr(SloService, "summarize_slos", unavailable)
        compliance = await ApplicationService._slo_compliance_by_application(SimpleNamespace(session=None), ["application-9"])  # type: ignore[arg-type]
        assert compliance == {}
        assert any(record.levelno == logging.WARNING and "1 application" in record.getMessage() for record in caplog.records)


# ── Team members entered while the application is created ────────────────────────────────────────


KEIGAN_ADMIN = user("ana.admin@example.com", is_keigan_admin=True)


def creation_request(code: str, *team: dict[str, str], lifecycle_status: str | None = None) -> ApplicationCreateRequest:
    return ApplicationCreateRequest(application_name=f"Team {code}", application_code=code, lifecycle_status=lifecycle_status, team_members=list(team))  # type: ignore[arg-type]


async def team_of(application_id: str) -> list[StakeholderResponse]:
    async with open_session() as session:
        return await StakeholderService(session).list_stakeholders(application_id)


async def test_a_new_application_is_created_with_its_team_and_the_invitations_are_queued() -> None:
    async with open_session() as session:
        created = await ApplicationService(session).create_application(
            KEIGAN_ADMIN, creation_request("TM1", {"displayName": "Lena Lead", "emailAddress": "Lena.Lead@example.com", "stakeholderRole": "lead"}, {"displayName": "Dev Dan", "emailAddress": "dan@example.com", "stakeholderRole": "devops"}),
        )
    team = {member.email_address: member for member in await team_of(created.application_id)}
    assert team["lena.lead@example.com"].stakeholder_role == "lead" and team["dan@example.com"].stakeholder_role == "devops"
    assert {member.team_member_status for member in team.values()} == {TeamMemberStatus.INVITED}
    async with open_session() as session:
        queued = (await session.scalars(select(NotificationDelivery.recipient_address).where(NotificationDelivery.application_id == created.application_id, NotificationDelivery.notification_type == "team_invitation"))).all()
    assert sorted(queued) == ["dan@example.com", "lena.lead@example.com"]


async def test_an_application_that_is_only_requested_lists_its_team_but_sends_no_email() -> None:
    """A requested application is not approved yet: nobody is told about a workspace that may be turned down."""
    async with open_session() as session:
        created = await ApplicationService(session).create_application(
            user("requester@example.com", is_keigan_admin=False), creation_request("TM2", {"displayName": "Rui", "emailAddress": "rui@example.com", "stakeholderRole": "tester"}),
        )
    assert [member.team_member_status for member in await team_of(created.application_id)] == [TeamMemberStatus.LISTED]
    async with open_session() as session:
        assert not (await session.scalars(select(NotificationDelivery).where(NotificationDelivery.application_id == created.application_id))).all()


async def test_an_application_can_still_be_created_with_no_team() -> None:
    async with open_session() as session:
        created = await ApplicationService(session).create_application(KEIGAN_ADMIN, creation_request("TM3"))
    assert await team_of(created.application_id) == []


def test_the_same_person_listed_twice_in_one_request_is_refused_whatever_the_letter_case() -> None:
    with pytest.raises(ValidationError, match="rui@example.com is listed twice"):
        creation_request("TM4", {"displayName": "Rui", "emailAddress": "rui@example.com"}, {"displayName": "Rui again", "emailAddress": "RUI@example.com"})


def test_an_invalid_address_in_the_team_is_refused_with_the_message_for_the_field() -> None:
    with pytest.raises(ValidationError, match="Enter an email address like name@company.com."):
        creation_request("TM5", {"displayName": "Rui", "emailAddress": "rui-at-example"})


async def test_a_team_member_the_service_refuses_leaves_no_application_behind(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "team_members_maximum_per_application", 1)
    with pytest.raises(BusinessValidationException):
        async with open_session() as session:
            await ApplicationService(session).create_application(
                KEIGAN_ADMIN, creation_request("TM6", {"displayName": "One", "emailAddress": "one@example.com"}, {"displayName": "Two", "emailAddress": "two@example.com"}),
            )
    async with open_session() as session:
        assert await session.scalar(select(func.count()).select_from(Application).where(Application.application_code == "TM6")) == 0, "the application stayed although its team was refused"
