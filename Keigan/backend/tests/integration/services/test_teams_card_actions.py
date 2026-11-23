"""keigan/services/teams_chat_service.py: a person presses a button on a Keigan card in the incident chat (roadmap D2).

The bot acts as the person who pressed it, so a button can never do more than that person could do on the investigation page.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.entities.application_entities import Application
from keigan.entities.incident_entities import ConversationMessage
from keigan.services.notification_service import NotificationService
from keigan.services.teams_card_actions import RATE_INVESTIGATION
from keigan.services.teams_chat_service import NOT_AUTHORIZED_REPLY
from keigan.utils.string_table import translate
from tests.integration.services.test_teams_chat_service import ADMIN_NAME, OUTSIDER_NAME, READER_NAME, activity, assistant_texts, expected_tenant, handle, investigation_of, make_chat, messages_of  # noqa: F401


def pressed(conversation_id: str, sender_name: str, investigation_id: str, verdict: str, **data: Any) -> dict[str, Any]:
    """What Teams sends when a button of a card is pressed: a message with no text and the button's data as its value."""
    return {**activity(conversation_id, sender_name, ""), "text": None, "value": {"keiganAction": RATE_INVESTIGATION, "investigationId": investigation_id, "verdict": verdict, **data}}


async def application_id(seed_context) -> str:
    return seed_context.application_ids_by_code["CLMJP"]


async def reply(seed_context, key: str) -> str:
    """The bot answers in the application's own language (the Claims application is Japanese)."""
    async with open_session() as session:
        application = await session.get(Application, await application_id(seed_context))
    assert application.primary_locale == "ja"
    return translate(application.primary_locale, key)


async def test_a_reader_rates_the_analysis_wrong_and_it_is_recorded_as_theirs(seed_context, expected_tenant: None) -> None:
    conversation_id, incident_id = await make_chat(await application_id(seed_context))
    investigation = await investigation_of(incident_id)
    await handle(pressed(conversation_id, READER_NAME, investigation.investigation_id, "incorrect"))
    stored = await investigation_of(incident_id)
    assert stored.user_feedback_verdict == "incorrect" and stored.user_feedback_by_user_principal_name == "rui.reader@keigan.local"
    assert await reply(seed_context, "chat.rating_recorded") in assistant_texts(await messages_of(conversation_id))


async def test_only_an_application_admin_can_say_the_analysis_was_correct(seed_context, expected_tenant: None) -> None:
    conversation_id, incident_id = await make_chat(await application_id(seed_context))
    investigation = await investigation_of(incident_id)
    await handle(pressed(conversation_id, READER_NAME, investigation.investigation_id, "correct"))
    assert (await investigation_of(incident_id)).user_feedback_verdict is None
    assert await reply(seed_context, "chat.rating_needs_admin") in assistant_texts(await messages_of(conversation_id))
    await handle(pressed(conversation_id, ADMIN_NAME, investigation.investigation_id, "correct"))
    assert (await investigation_of(incident_id)).user_feedback_verdict == "correct"


async def test_a_button_for_an_investigation_of_another_incident_is_not_followed(seed_context, expected_tenant: None) -> None:
    conversation_id, incident_id = await make_chat(await application_id(seed_context))
    _other_conversation, other_incident_id = await make_chat(await application_id(seed_context))
    other = await investigation_of(other_incident_id)
    await handle(pressed(conversation_id, READER_NAME, other.investigation_id, "incorrect"))
    assert (await investigation_of(other_incident_id)).user_feedback_verdict is None
    assert await reply(seed_context, "chat.rating_unavailable") in assistant_texts(await messages_of(conversation_id))


async def test_a_button_for_an_investigation_that_does_not_exist_says_so(seed_context, expected_tenant: None) -> None:
    conversation_id, _incident_id = await make_chat(await application_id(seed_context))
    await handle(pressed(conversation_id, READER_NAME, "0b6f1c4e-2d3a-4f5b-8c7d-9e0a1b2c3d4e", "incorrect"))
    assert await reply(seed_context, "chat.rating_unavailable") in assistant_texts(await messages_of(conversation_id))


async def test_someone_without_access_to_the_application_gets_the_usual_refusal_and_nothing_is_stored(seed_context, expected_tenant: None) -> None:
    conversation_id, incident_id = await make_chat(await application_id(seed_context))
    investigation = await investigation_of(incident_id)
    await handle(pressed(conversation_id, OUTSIDER_NAME, investigation.investigation_id, "incorrect"))
    assert (await investigation_of(incident_id)).user_feedback_verdict is None
    assert NOT_AUTHORIZED_REPLY in assistant_texts(await messages_of(conversation_id))


@pytest.mark.parametrize("value", [{"keiganAction": "delete_everything"}, {"keiganAction": RATE_INVESTIGATION, "verdict": "sudo", "investigationId": "x"}, "rate", ["a"]])
async def test_data_that_is_not_one_of_our_buttons_does_nothing_and_says_nothing(seed_context, expected_tenant: None, value: Any) -> None:
    conversation_id, incident_id = await make_chat(await application_id(seed_context))
    before = len(await messages_of(conversation_id))
    await handle({**activity(conversation_id, READER_NAME, ""), "text": None, "value": value})
    assert len(await messages_of(conversation_id)) == before and (await investigation_of(incident_id)).user_feedback_verdict is None


async def test_the_analysis_card_posted_to_the_chat_has_the_rating_buttons_and_the_open_link(seed_context, expected_tenant: None) -> None:
    conversation_id, incident_id = await make_chat(await application_id(seed_context))
    investigation = await investigation_of(incident_id)
    async with open_session() as session:
        result = await NotificationService(session).on_investigation_completed(investigation.investigation_id)
    assert result is not None and result["cardPosted"] is True
    async with open_session() as session:
        posted = (await session.scalars(select(ConversationMessage).where(ConversationMessage.author_role == "assistant").order_by(ConversationMessage.created_at.desc()))).all()
    card = next(message.message_payload_json["adaptiveCard"] for message in posted if message.message_payload_json and message.message_payload_json.get("adaptiveCard"))
    submits = [action for action in card["actions"] if action["type"] == "Action.Submit"]
    assert [action["data"]["verdict"] for action in submits] == ["correct", "partially_correct", "incorrect"] and {action["data"]["investigationId"] for action in submits} == {investigation.investigation_id}
    assert any(action["type"] == "Action.OpenUrl" for action in card["actions"])
