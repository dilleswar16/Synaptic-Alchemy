"""The buttons on a Keigan Teams card, and what a pressed button may ask for (roadmap D2). Pure: no database, no network.

Teams sends a pressed button's data back exactly as the card carried it, but it passes through the person's client, so it is untrusted: only the one action is understood, with a well-formed
investigation id and one of the three verdicts. Everything else, and every extra key, is ignored. Who may do what is decided afterwards by the same rules as the investigation page.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from keigan.entities.status_values import InvestigationFeedbackVerdict
from keigan.utils.string_table import translate

RATE_INVESTIGATION = "rate_investigation"
_IDENTIFIER = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_BUTTON_TEXT_KEY = {
    InvestigationFeedbackVerdict.CORRECT: "cards.rate_correct",
    InvestigationFeedbackVerdict.PARTIALLY_CORRECT: "cards.rate_partial",
    InvestigationFeedbackVerdict.INCORRECT: "cards.rate_incorrect",
}


@dataclass(frozen=True)
class CardAction:
    name: str
    investigation_id: str
    verdict: str


def rating_actions(investigation_id: str, language_code: str | None) -> list[dict[str, Any]]:
    """One Adaptive Card ``Action.Submit`` per verdict, in the card's language."""
    return [
        {"type": "Action.Submit", "title": translate(language_code, text_key), "data": {"keiganAction": RATE_INVESTIGATION, "investigationId": investigation_id, "verdict": verdict.value}}
        for verdict, text_key in _BUTTON_TEXT_KEY.items()
    ]


def parse_card_action(value: Any) -> CardAction | None:
    """The action a pressed button asks for, or None when ``value`` is not the data of one of our buttons."""
    if not isinstance(value, dict) or value.get("keiganAction") != RATE_INVESTIGATION:
        return None
    investigation_id, verdict = value.get("investigationId"), value.get("verdict")
    if not isinstance(investigation_id, str) or not _IDENTIFIER.match(investigation_id) or not isinstance(verdict, str):
        return None
    if verdict not in {member.value for member in InvestigationFeedbackVerdict}:
        return None
    return CardAction(RATE_INVESTIGATION, investigation_id, verdict)
