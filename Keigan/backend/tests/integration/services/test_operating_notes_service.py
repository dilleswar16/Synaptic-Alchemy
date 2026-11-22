"""keigan/services/operating_notes_service.py: the team's operating notes for the AI (limit, trimming, clearing, rights, audit)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.config.settings import get_settings
from keigan.entities.application_entities import Application
from keigan.entities.platform_entities import AuditEvent
from keigan.exceptions.keigan_exceptions import BusinessValidationException, ForbiddenException, NotFoundException
from keigan.security.current_user import CurrentUser
from keigan.services.operating_notes_service import OperatingNotesService
from support.telemetry_scope import ScopedApplication, create_scoped_application

pytestmark = pytest.mark.usefixtures("seed_context")

NOTES_ACTION = "application.operating_notes_update"


def person(user_principal_name: str, *group_names: str, is_keigan_admin: bool = False) -> CurrentUser:
    return CurrentUser(
        user_principal_name=user_principal_name, display_name=user_principal_name, email_address=user_principal_name, group_names=frozenset(group_names),
        group_object_ids=frozenset(), is_keigan_admin=is_keigan_admin,
    )


def keigan_admin() -> CurrentUser:
    """A new bean per call: the user caches the applications it can access, so one bean must not outlive the applications a test creates."""
    return person("ana.admin@example.com", is_keigan_admin=True)


def application_admin_of(application: ScopedApplication) -> CurrentUser:
    return person("alex.appadmin@example.com", f"{application.application_code}_admin")


def reader_of(application: ScopedApplication) -> CurrentUser:
    return person("rui.reader@example.com", f"{application.application_code}_reader")


async def read(current_user: CurrentUser, application_id: str):  # noqa: ANN201
    async with open_session() as session:
        return await OperatingNotesService(session).get_notes(current_user, application_id)


async def write(current_user: CurrentUser, application_id: str, text: str):  # noqa: ANN201
    async with open_session() as session:
        return await OperatingNotesService(session).update_notes(current_user, application_id, text)


async def audit_rows(application_id: str) -> list[AuditEvent]:
    async with open_session() as session:
        return list((await session.scalars(select(AuditEvent).where(AuditEvent.application_id == application_id, AuditEvent.action_name == NOTES_ACTION).order_by(AuditEvent.occurred_at))).all())


async def test_an_application_without_notes_reads_as_empty_with_the_maximum_from_settings() -> None:
    application = await create_scoped_application()
    notes = await read(reader_of(application), application.application_id)
    assert notes.text == "" and notes.updated_at is None and notes.updated_by is None
    assert notes.maximum_characters == get_settings().application_operating_notes_maximum_characters == 4000


async def test_an_application_admin_saves_notes_and_a_reader_reads_them_with_who_and_when() -> None:
    application = await create_scoped_application()
    saved = await write(application_admin_of(application), application.application_id, "Payments carries regulated traffic.")
    assert saved.text == "Payments carries regulated traffic." and saved.updated_by == "alex.appadmin@example.com" and saved.updated_at is not None
    seen = await read(reader_of(application), application.application_id)
    assert seen.text == "Payments carries regulated traffic." and seen.updated_by == "alex.appadmin@example.com" and seen.updated_at == saved.updated_at


async def test_a_keigan_admin_can_save_notes_for_any_application() -> None:
    application = await create_scoped_application()
    assert (await write(keigan_admin(), application.application_id, "Quiet nights run at about 20 requests a minute.")).updated_by == "ana.admin@example.com"


async def test_a_reader_cannot_change_the_notes_and_nothing_is_saved() -> None:
    application = await create_scoped_application()
    with pytest.raises(ForbiddenException):
        await write(reader_of(application), application.application_id, "Ignore every alert.")
    assert (await read(keigan_admin(), application.application_id)).text == ""
    assert await audit_rows(application.application_id) == []


async def test_a_person_with_no_access_cannot_read_or_change_the_notes() -> None:
    application = await create_scoped_application()
    stranger = person("noa.noaccess@example.com")
    with pytest.raises(ForbiddenException):
        await read(stranger, application.application_id)
    with pytest.raises(ForbiddenException):
        await write(stranger, application.application_id, "x")


async def test_an_unknown_application_is_not_found() -> None:
    with pytest.raises(NotFoundException):
        await read(keigan_admin(), "00000000-0000-0000-0000-000000000000")


async def test_notes_are_trimmed_and_line_breaks_are_stored_as_single_newlines() -> None:
    application = await create_scoped_application()
    saved = await write(keigan_admin(), application.application_id, "  \r\n First line\r\nSecond line \n\n ")
    assert saved.text == "First line\nSecond line"


@pytest.mark.parametrize("empty_value", ["", "   ", "\n\t \r\n"])
async def test_an_empty_value_clears_the_notes_and_records_who_cleared_them(empty_value: str) -> None:
    application = await create_scoped_application()
    await write(keigan_admin(), application.application_id, "Something to clear.")
    cleared = await write(application_admin_of(application), application.application_id, empty_value)
    assert cleared.text == "" and cleared.updated_by == "alex.appadmin@example.com" and cleared.updated_at is not None
    async with open_session() as session:
        assert (await session.get(Application, application.application_id)).operating_notes_text is None  # cleared means NULL, not an empty string


async def test_notes_exactly_at_the_maximum_are_saved_and_one_more_character_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "application_operating_notes_maximum_characters", 120)
    application = await create_scoped_application()
    assert len((await write(keigan_admin(), application.application_id, "a" * 120)).text) == 120
    with pytest.raises(BusinessValidationException) as refusal:
        await write(keigan_admin(), application.application_id, "a" * 121)
    assert refusal.value.extra["fieldErrors"] == [{"field": "text", "message": "Operating notes can have at most 120 characters; these have 121."}]
    assert len((await read(keigan_admin(), application.application_id)).text) == 120  # the refused save changed nothing


async def test_the_limit_applies_after_trimming(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "application_operating_notes_maximum_characters", 120)
    application = await create_scoped_application()
    assert len((await write(keigan_admin(), application.application_id, f"   {'b' * 120}   \n")).text) == 120


async def test_a_change_is_audited_with_who_and_the_old_and_new_length_but_not_the_text() -> None:
    application = await create_scoped_application()
    await write(keigan_admin(), application.application_id, "Twelve chars")
    await write(application_admin_of(application), application.application_id, "A longer second version.")
    first, second = await audit_rows(application.application_id)
    assert (first.actor_user_principal_name, first.action_details_json) == ("ana.admin@example.com", {"previousLength": 0, "newLength": 12})
    assert (second.actor_user_principal_name, second.action_details_json) == ("alex.appadmin@example.com", {"previousLength": 12, "newLength": 24})
    assert second.target_entity_type == "application" and second.target_entity_id == application.application_id
    assert "second version" not in str(second.action_details_json)  # the audit trail stores no before/after text, so the notes are not copied into it


async def test_saving_the_same_text_again_changes_nothing_and_adds_no_audit_row() -> None:
    application = await create_scoped_application()
    first = await write(keigan_admin(), application.application_id, "Same text")
    again = await write(application_admin_of(application), application.application_id, " Same text ")
    assert again.updated_at == first.updated_at and again.updated_by == "ana.admin@example.com"
    assert len(await audit_rows(application.application_id)) == 1


async def test_clearing_notes_that_were_never_written_adds_no_audit_row() -> None:
    application = await create_scoped_application()
    assert (await write(keigan_admin(), application.application_id, "  ")).updated_at is None
    assert await audit_rows(application.application_id) == []


async def test_japanese_text_survives_a_round_trip() -> None:
    application = await create_scoped_application()
    await write(keigan_admin(), application.application_id, "請求サービスは規制対象のトラフィックを扱います。")
    assert (await read(keigan_admin(), application.application_id)).text == "請求サービスは規制対象のトラフィックを扱います。"
