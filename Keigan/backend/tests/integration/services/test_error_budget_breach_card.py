"""keigan/services/error_budget_policy_notifier.py: a single-incident breach is posted to the incident's Teams chat as a card in the application's language (spec 30, 4.6)."""

from __future__ import annotations

from typing import Any

from keigan.config.database_config import open_session
from keigan.entities.application_entities import Application
from keigan.entities.error_budget_entities import ErrorBudgetPolicyBreach
from keigan.services.error_budget_policy_notifier import ErrorBudgetPolicyNotifier
from keigan.utils.string_table import translate
from keigan.utils.time_utils import utc_now
from tests.integration.services.test_teams_chat_service import expected_tenant, make_chat, messages_of  # noqa: F401


async def breach_of(application_id: str, incident_id: str) -> str:
    async with open_session() as session:
        breach = ErrorBudgetPolicyBreach(
            application_id=application_id, breach_kind="single_incident", incident_id=incident_id, window_days=30, measured_share_percent=41.7, threshold_percent=20.0, sli_name_text="Checkout availability",
            incident_reference_text="INC0099001", detected_at=utc_now(), requirement_status="open", requirement_changed_at=utc_now(), is_provisional=False,
        )
        session.add(breach)
        await session.flush()
        return breach.error_budget_policy_breach_id


async def cards_in(conversation_id: str) -> list[dict[str, Any]]:
    return [message.message_payload_json["adaptiveCard"] for message in await messages_of(conversation_id) if (message.message_payload_json or {}).get("adaptiveCard")]


async def test_a_single_incident_breach_posts_a_card_in_the_application_language_with_the_numbers_and_a_button(seed_context, expected_tenant: None) -> None:
    application_id = seed_context.application_ids_by_code["CLMJP"]
    conversation_id, incident_id = await make_chat(application_id)
    breach_id = await breach_of(application_id, incident_id)
    async with open_session() as session:
        application = await session.get(Application, application_id)
        language = application.primary_locale
        await ErrorBudgetPolicyNotifier(session).notify(await session.get(ErrorBudgetPolicyBreach, breach_id), application)
    [card] = [card for card in await cards_in(conversation_id) if "Checkout availability" in str(card)]
    assert card["type"] == "AdaptiveCard"
    texts = [block["text"] for block in card["body"] if block["type"] == "TextBlock"]
    assert translate(language, "cards.error_budget_breach") in texts and "Checkout availability" in texts
    facts = {fact["title"]: fact["value"] for block in card["body"] if block["type"] == "FactSet" for fact in block["facts"]}
    assert facts[translate(language, "labels.budget_share")] == "41.7 %" and facts[translate(language, "labels.threshold")] == "20 %" and facts[translate(language, "labels.incident")] == "INC0099001"
    assert [action["type"] for action in card["actions"]] == ["Action.OpenUrl"] and card["actions"][0]["title"] == translate(language, "cards.open")
