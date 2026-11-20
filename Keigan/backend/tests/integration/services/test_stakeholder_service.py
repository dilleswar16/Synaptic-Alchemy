"""keigan/services/stakeholder_service.py and team_invitation_service.py: the application team (roles, duplicates, last lead, invitations and the first sign-in)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.config.settings import get_settings
from keigan.dtos.notification_dtos import StakeholderCreateRequest, StakeholderUpdateRequest
from keigan.entities.notification_entities import NotificationDelivery, Stakeholder
from keigan.entities.status_values import TeamMemberStatus
from keigan.exceptions.keigan_exceptions import BusinessValidationException, RateLimitedException
from keigan.security.current_user import CurrentUser
from keigan.services.stakeholder_service import StakeholderService
from keigan.services.team_invitation_service import TeamInvitationService
from support.telemetry_scope import create_scoped_application

pytestmark = pytest.mark.usefixtures("seed_context")

ADMIN = CurrentUser(user_principal_name="admin@example.com", display_name="Ana Admin", email_address="admin@example.com", group_names=frozenset(), group_object_ids=frozenset(), is_keigan_admin=True)


def member(email: str, name: str = "Rui Reader", role: str = "developer", **options: object) -> StakeholderCreateRequest:
    return StakeholderCreateRequest(display_name=name, email_address=email, stakeholder_role=role, **options)  # type: ignore[arg-type]


async def add(application_id: str, request: StakeholderCreateRequest):  # noqa: ANN201
    async with open_session() as session:
        return await StakeholderService(session).create_stakeholder(ADMIN, application_id, request)


async def invitations_for(address: str) -> list[NotificationDelivery]:
    async with open_session() as session:
        return list((await session.scalars(select(NotificationDelivery).where(NotificationDelivery.notification_type == "team_invitation", NotificationDelivery.recipient_address == address))).all())


# ── Roles and addresses ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ["lead", "infra", "devops", "tester", "developer", "sre"])
async def test_every_team_role_can_be_saved(role: str) -> None:
    application = await create_scoped_application()
    saved = await add(application.application_id, member(f"{role}.person@example.com", role=role))
    assert saved.stakeholder_role == role


def test_a_role_that_does_not_exist_is_refused() -> None:
    with pytest.raises(ValidationError):
        member("someone@example.com", role="astronaut")


@pytest.mark.parametrize("typed", ["not-an-address", "rui@", "rui@example", "rui@@example.com"])
def test_an_invalid_address_is_refused_before_anything_is_saved(typed: str) -> None:
    with pytest.raises(ValidationError, match="Enter an email address like name@company.com."):
        StakeholderCreateRequest(display_name="Rui", email_address=typed)


async def test_a_person_needs_an_email_address() -> None:
    application = await create_scoped_application()
    with pytest.raises(BusinessValidationException) as refusal:
        await add(application.application_id, StakeholderCreateRequest(display_name="No address"))
    assert refusal.value.extra["fieldErrors"] == [{"field": "emailAddress", "message": "An email address is required for people and distribution lists."}]


async def test_an_address_is_saved_trimmed_and_in_lower_case() -> None:
    application = await create_scoped_application()
    saved = await add(application.application_id, member("  Rui.Reader@Example.COM "))
    assert saved.email_address == "rui.reader@example.com"


async def test_the_same_person_cannot_be_added_twice_even_with_another_letter_case() -> None:
    application = await create_scoped_application()
    await add(application.application_id, member("rui@example.com"))
    with pytest.raises(BusinessValidationException) as refusal:
        await add(application.application_id, member("RUI@example.com", name="Rui again"))
    assert refusal.value.extra["fieldErrors"] == [{"field": "emailAddress", "message": "rui@example.com is already on this team."}]


async def test_the_same_address_may_be_on_two_different_applications() -> None:
    first, second = await create_scoped_application(), await create_scoped_application()
    await add(first.application_id, member("shared@example.com"))
    assert (await add(second.application_id, member("shared@example.com"))).email_address == "shared@example.com"


async def test_changing_an_address_to_one_already_on_the_team_is_refused() -> None:
    application = await create_scoped_application()
    await add(application.application_id, member("one@example.com"))
    other = await add(application.application_id, member("two@example.com", name="Two"))
    async with open_session() as session:
        with pytest.raises(BusinessValidationException, match="The team member is not valid"):
            await StakeholderService(session).update_stakeholder(ADMIN, application.application_id, other.stakeholder_id, StakeholderUpdateRequest(email_address="ONE@example.com"))


async def test_a_team_cannot_grow_past_the_configured_maximum(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "team_members_maximum_per_application", 2)
    application = await create_scoped_application()
    await add(application.application_id, member("a@example.com", name="A"))
    await add(application.application_id, member("b@example.com", name="B"))
    with pytest.raises(BusinessValidationException) as refusal:
        await add(application.application_id, member("c@example.com", name="C"))
    assert refusal.value.extra["fieldErrors"] == [{"field": "emailAddress", "message": "A team can have at most 2 people."}]


# ── Status and invitations ────────────────────────────────────────────────────────────────────────


async def test_a_person_who_was_only_added_is_listed_and_no_email_is_sent() -> None:
    application = await create_scoped_application()
    saved = await add(application.application_id, member("listed@example.com"))
    assert saved.team_member_status == TeamMemberStatus.LISTED and saved.can_send_invitation is True
    assert await invitations_for("listed@example.com") == []


async def test_inviting_a_person_queues_one_email_and_marks_them_invited() -> None:
    application = await create_scoped_application()
    saved = await add(application.application_id, member("invited@example.com", role="lead", send_invitation=True))
    assert saved.team_member_status == TeamMemberStatus.INVITED and saved.invited_at is not None and saved.can_send_invitation is False
    assert saved.next_invitation_allowed_at is not None
    deliveries = await invitations_for("invited@example.com")
    assert len(deliveries) == 1 and "Scope" in deliveries[0].subject_line
    assert "SCP" in deliveries[0].body_text and "_reader" in deliveries[0].body_text, "the email must say which group gives access"


async def test_only_people_can_be_invited() -> None:
    application = await create_scoped_application()
    with pytest.raises(BusinessValidationException, match="Only people can be invited"):
        await add(application.application_id, StakeholderCreateRequest(recipient_type="distribution_list", display_name="Ops list", email_address="ops@example.com", send_invitation=True))


async def test_an_invitation_cannot_be_sent_again_before_the_cooldown_ends() -> None:
    application = await create_scoped_application()
    saved = await add(application.application_id, member("cooldown@example.com", send_invitation=True))
    async with open_session() as session:
        with pytest.raises(RateLimitedException, match="You can send another in"):
            await StakeholderService(session).send_invitation(ADMIN, application.application_id, saved.stakeholder_id)
    assert len(await invitations_for("cooldown@example.com")) == 1


async def test_an_invitation_can_be_sent_again_after_the_cooldown() -> None:
    application = await create_scoped_application()
    saved = await add(application.application_id, member("again@example.com", send_invitation=True))
    async with open_session() as session:
        row = await session.get(Stakeholder, saved.stakeholder_id)
        row.last_invitation_sent_at = datetime.now(UTC) - timedelta(minutes=get_settings().team_invitation_resend_cooldown_minutes + 1)
    async with open_session() as session:
        resent = await StakeholderService(session).send_invitation(ADMIN, application.application_id, saved.stakeholder_id)
    assert resent.team_member.team_member_status == TeamMemberStatus.INVITED
    assert len(await invitations_for("again@example.com")) == 2


async def test_an_invitation_is_not_sent_to_someone_who_already_signed_in() -> None:
    application = await create_scoped_application()
    saved = await add(application.application_id, member("joined@example.com"))
    async with open_session() as session:
        (await session.get(Stakeholder, saved.stakeholder_id)).joined_at = datetime.now(UTC)
    async with open_session() as session:
        with pytest.raises(BusinessValidationException, match="already signed in"):
            await StakeholderService(session).send_invitation(ADMIN, application.application_id, saved.stakeholder_id)


async def test_an_invitation_is_not_sent_to_someone_who_is_switched_off() -> None:
    application = await create_scoped_application()
    saved = await add(application.application_id, member("off@example.com", is_active=False))
    assert saved.team_member_status == TeamMemberStatus.INACTIVE and saved.can_send_invitation is False
    async with open_session() as session:
        with pytest.raises(BusinessValidationException, match="switched off"):
            await StakeholderService(session).send_invitation(ADMIN, application.application_id, saved.stakeholder_id)


async def test_an_invitation_older_than_the_limit_without_a_sign_in_is_marked_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    application = await create_scoped_application()
    saved = await add(application.application_id, member("stale@example.com", send_invitation=True))
    assert saved.invitation_is_stale is False
    async with open_session() as session:
        (await session.get(Stakeholder, saved.stakeholder_id)).invited_at = datetime.now(UTC) - timedelta(days=get_settings().team_invitation_stale_after_days + 1)
    async with open_session() as session:
        listed = await StakeholderService(session).list_stakeholders(application.application_id)
    assert listed[0].invitation_is_stale is True


# ── First sign-in ─────────────────────────────────────────────────────────────────────────────────


def signed_in_user(user_principal_name: str, email_address: str | None = None) -> CurrentUser:
    return CurrentUser(user_principal_name=user_principal_name, display_name="Someone", email_address=email_address, group_names=frozenset(), group_object_ids=frozenset(), is_keigan_admin=False)


async def test_the_first_sign_in_of_an_invited_person_makes_them_active() -> None:
    application = await create_scoped_application()
    saved = await add(application.application_id, member("first.signin@example.com", send_invitation=True))
    async with open_session() as session:
        assert await TeamInvitationService(session).record_sign_in(signed_in_user("First.SignIn@Example.com")) == 1
    async with open_session() as session:
        listed = await StakeholderService(session).list_stakeholders(application.application_id)
    assert listed[0].stakeholder_id == saved.stakeholder_id and listed[0].team_member_status == TeamMemberStatus.ACTIVE and listed[0].joined_at is not None


async def test_a_sign_in_is_matched_on_the_email_when_the_sign_in_name_differs() -> None:
    application = await create_scoped_application()
    await add(application.application_id, member("by.email@example.com"))
    async with open_session() as session:
        assert await TeamInvitationService(session).record_sign_in(signed_in_user("bye12345@corp.example.com", "By.Email@example.com")) == 1


async def test_a_sign_in_marks_the_person_on_every_application_they_are_on() -> None:
    first, second = await create_scoped_application(), await create_scoped_application()
    await add(first.application_id, member("both@example.com"))
    await add(second.application_id, member("both@example.com"))
    async with open_session() as session:
        assert await TeamInvitationService(session).record_sign_in(signed_in_user("both@example.com")) == 2


async def test_a_second_sign_in_changes_nothing_and_a_switched_off_person_is_not_marked() -> None:
    application = await create_scoped_application()
    await add(application.application_id, member("once@example.com"))
    await add(application.application_id, member("off.signin@example.com", name="Off", is_active=False))
    async with open_session() as session:
        service = TeamInvitationService(session)
        assert await service.record_sign_in(signed_in_user("once@example.com")) == 1
        assert await service.record_sign_in(signed_in_user("once@example.com")) == 0
        assert await service.record_sign_in(signed_in_user("off.signin@example.com")) == 0


# ── The last lead ─────────────────────────────────────────────────────────────────────────────────


async def test_the_only_lead_cannot_be_removed() -> None:
    application = await create_scoped_application()
    lead = await add(application.application_id, member("lead@example.com", name="Lena Lead", role="lead"))
    async with open_session() as session:
        with pytest.raises(BusinessValidationException, match="only team lead"):
            await StakeholderService(session).delete_stakeholder(ADMIN, application.application_id, lead.stakeholder_id)


async def test_the_only_lead_cannot_be_switched_off_or_given_another_role() -> None:
    application = await create_scoped_application()
    lead = await add(application.application_id, member("lead2@example.com", name="Lena Lead", role="lead"))
    for changes in ({"is_active": False}, {"stakeholder_role": "developer"}):
        async with open_session() as session:
            with pytest.raises(BusinessValidationException, match="only team lead"):
                await StakeholderService(session).update_stakeholder(ADMIN, application.application_id, lead.stakeholder_id, StakeholderUpdateRequest(**changes))


async def test_a_lead_can_be_removed_once_another_lead_exists() -> None:
    application = await create_scoped_application()
    first = await add(application.application_id, member("lead3@example.com", name="First", role="lead"))
    await add(application.application_id, member("lead4@example.com", name="Second", role="lead"))
    async with open_session() as session:
        await StakeholderService(session).delete_stakeholder(ADMIN, application.application_id, first.stakeholder_id)
    async with open_session() as session:
        assert [row.display_name for row in await StakeholderService(session).list_stakeholders(application.application_id)] == ["Second"]


async def test_an_application_with_no_lead_is_not_blocked_from_removing_people() -> None:
    application = await create_scoped_application()
    person = await add(application.application_id, member("nolead@example.com"))
    async with open_session() as session:
        await StakeholderService(session).delete_stakeholder(ADMIN, application.application_id, person.stakeholder_id)


# ── Found by the independent review ───────────────────────────────────────────────────────────────


async def test_two_people_added_at_the_same_moment_with_one_address_get_the_clean_message_not_a_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both requests pass the pre-check; the unique index then rejects the loser. It must read as a validation message."""
    application = await create_scoped_application()
    await add(application.application_id, member("race@example.com"))

    async def pre_check_saw_nothing(self: StakeholderService, application_id: str, values: dict, existing: object, errors: list) -> None:  # noqa: ANN001
        return None

    monkeypatch.setattr(StakeholderService, "_validate_team_membership", pre_check_saw_nothing)
    with pytest.raises(BusinessValidationException) as refusal:
        await add(application.application_id, member("race@example.com", name="Loser"))
    assert refusal.value.extra["fieldErrors"] == [{"field": "emailAddress", "message": "race@example.com is already on this team."}]


async def test_the_only_lead_cannot_be_turned_into_a_list_or_a_channel() -> None:
    application = await create_scoped_application()
    lead = await add(application.application_id, member("lead5@example.com", name="Lena Lead", role="lead"))
    for recipient_type in ("distribution_list", "teams_channel"):
        async with open_session() as session:
            with pytest.raises(BusinessValidationException, match="only team lead"):
                await StakeholderService(session).update_stakeholder(ADMIN, application.application_id, lead.stakeholder_id, StakeholderUpdateRequest(recipient_type=recipient_type))


async def test_changing_a_persons_address_starts_a_new_invitation_history_and_moves_the_sign_in_name() -> None:
    """The new address belongs to someone else: they have not been invited and have not signed in."""
    application = await create_scoped_application()
    saved = await add(application.application_id, member("old.address@example.com", send_invitation=True))
    async with open_session() as session:
        row = await session.get(Stakeholder, saved.stakeholder_id)
        row.joined_at = datetime.now(UTC)
    async with open_session() as session:
        changed = await StakeholderService(session).update_stakeholder(ADMIN, application.application_id, saved.stakeholder_id, StakeholderUpdateRequest(email_address="New.Address@example.com"))
    assert changed.team_member_status == TeamMemberStatus.LISTED and changed.joined_at is None and changed.invited_at is None and changed.last_invitation_sent_at is None
    assert changed.user_principal_name == "new.address@example.com"
    async with open_session() as session:
        assert await TeamInvitationService(session).record_sign_in(signed_in_user("old.address@example.com")) == 0, "the old address still claims the member"


async def test_changing_something_else_keeps_the_invitation_history() -> None:
    application = await create_scoped_application()
    saved = await add(application.application_id, member("keeps@example.com", send_invitation=True))
    async with open_session() as session:
        changed = await StakeholderService(session).update_stakeholder(ADMIN, application.application_id, saved.stakeholder_id, StakeholderUpdateRequest(stakeholder_role="devops"))
    assert changed.team_member_status == TeamMemberStatus.INVITED


async def test_two_clicks_on_invite_at_the_same_moment_send_one_email() -> None:
    import asyncio

    application = await create_scoped_application()
    saved = await add(application.application_id, member("double.click@example.com"))

    async def click() -> object:
        async with open_session() as session:
            try:
                return await StakeholderService(session).send_invitation(ADMIN, application.application_id, saved.stakeholder_id)
            except RateLimitedException as refusal:
                return refusal

    results = await asyncio.gather(click(), click())
    assert sum(isinstance(result, RateLimitedException) for result in results) == 1
    assert len(await invitations_for("double.click@example.com")) == 1
