"""keigan/services/teams_card_actions.py: the buttons on a Keigan Teams card and what a pressed button may ask for (roadmap D2).

A button's data comes back from Teams as the user's browser or phone sent it, so it is untrusted: only the one action, with a well-formed id and one of the three verdicts, is understood.
"""

from __future__ import annotations

from typing import Any

import pytest

from keigan.services.teams_card_actions import RATE_INVESTIGATION, CardAction, parse_card_action, rating_actions

INVESTIGATION_ID = "0b6f1c4e-2d3a-4f5b-8c7d-9e0a1b2c3d4e"


def test_the_card_has_one_button_per_verdict_carrying_the_investigation_and_the_verdict() -> None:
    actions = rating_actions(INVESTIGATION_ID, "en")
    assert [action["type"] for action in actions] == ["Action.Submit"] * 3
    assert [action["data"]["verdict"] for action in actions] == ["correct", "partially_correct", "incorrect"]
    assert all(action["data"]["keiganAction"] == RATE_INVESTIGATION and action["data"]["investigationId"] == INVESTIGATION_ID for action in actions)
    assert [action["title"] for action in actions] == ["Analysis was correct", "Partly correct", "Analysis was wrong"]


def test_the_buttons_are_written_in_the_cards_language() -> None:
    titles = [action["title"] for action in rating_actions(INVESTIGATION_ID, "ja")]
    assert len(set(titles)) == 3 and all(title and not title.startswith("cards.") for title in titles)


@pytest.mark.parametrize("verdict", ["correct", "partially_correct", "incorrect"])
def test_a_pressed_button_is_understood(verdict: str) -> None:
    assert parse_card_action({"keiganAction": RATE_INVESTIGATION, "investigationId": INVESTIGATION_ID, "verdict": verdict}) == CardAction(RATE_INVESTIGATION, INVESTIGATION_ID, verdict)


@pytest.mark.parametrize("value", [
    None, "rate", [], 5, {}, {"keiganAction": RATE_INVESTIGATION},
    {"keiganAction": "delete_everything", "investigationId": INVESTIGATION_ID, "verdict": "correct"},
    {"keiganAction": RATE_INVESTIGATION, "investigationId": INVESTIGATION_ID, "verdict": "sudo"},
    {"keiganAction": RATE_INVESTIGATION, "investigationId": INVESTIGATION_ID, "verdict": None},
    {"keiganAction": RATE_INVESTIGATION, "investigationId": "x' OR '1'='1", "verdict": "correct"},
    {"keiganAction": RATE_INVESTIGATION, "investigationId": "", "verdict": "correct"},
    {"keiganAction": RATE_INVESTIGATION, "investigationId": INVESTIGATION_ID.upper(), "verdict": "correct"},
    {"keiganAction": RATE_INVESTIGATION, "investigationId": 12345, "verdict": "correct"},
    {"keiganAction": ["rate_investigation"], "investigationId": INVESTIGATION_ID, "verdict": "correct"},
])
def test_anything_else_is_not_an_action(value: Any) -> None:
    assert parse_card_action(value) is None


def test_extra_keys_in_the_data_are_ignored_not_trusted() -> None:
    action = parse_card_action({"keiganAction": RATE_INVESTIGATION, "investigationId": INVESTIGATION_ID, "verdict": "correct", "applicationId": "another", "isAdmin": True})
    assert action == CardAction(RATE_INVESTIGATION, INVESTIGATION_ID, "correct")
