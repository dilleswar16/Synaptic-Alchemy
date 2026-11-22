"""The lists the screens offer (roles, channels, notification types) must be the lists the server accepts, and every one needs a label in every place that shows it."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import get_args

import pytest

from keigan.dtos.notification_dtos import NOTIFICATION_CHANNEL_VALUES, NOTIFICATION_TYPE_VALUES, StakeholderRole as StakeholderRoleLiteral
from keigan.entities.status_values import AlertGroupingReason, StakeholderRole

FRONTEND_SOURCE = Path(__file__).resolve().parents[3] / "frontend" / "src"
BACKEND_RESOURCES = Path(__file__).resolve().parents[2] / "keigan" / "resources"
NOTIFICATIONS_API = (FRONTEND_SOURCE / "api" / "notificationsApi.ts").read_text(encoding="utf-8")


def typescript_list(name: str) -> list[str]:
    """The strings of ``export const <name>: Type[] = ["a", "b"];``."""
    match = re.search(rf"export const {name}:[^=]*=\s*\[(.*?)\];", NOTIFICATIONS_API, re.DOTALL)
    assert match, f"{name} not found in frontend/src/api/notificationsApi.ts"
    return re.findall(r'"([^"]+)"', match.group(1))


def typescript_union(name: str) -> list[str]:
    match = re.search(rf"export type {name} =\s*(.*?);", NOTIFICATIONS_API, re.DOTALL)
    assert match, f"{name} not found in frontend/src/api/notificationsApi.ts"
    return re.findall(r'"([^"]+)"', match.group(1))


ROLE_VALUES = sorted(role.value for role in StakeholderRole)


def test_the_role_enum_and_the_request_type_accept_the_same_roles() -> None:
    assert sorted(get_args(StakeholderRoleLiteral)) == ROLE_VALUES


def test_the_screen_offers_exactly_the_roles_the_server_accepts() -> None:
    assert sorted(typescript_list("stakeholderRoles")) == ROLE_VALUES
    assert sorted(typescript_union("StakeholderRole")) == ROLE_VALUES


def test_the_screen_offers_exactly_the_channels_and_notification_types_the_server_accepts() -> None:
    assert sorted(typescript_list("notificationChannels")) == sorted(NOTIFICATION_CHANNEL_VALUES)
    assert sorted(typescript_list("notificationTypes")) == sorted(NOTIFICATION_TYPE_VALUES)


@pytest.mark.parametrize("locale", sorted(path.name for path in (FRONTEND_SOURCE / "i18n" / "locales").iterdir() if path.is_dir() and path.name != "es-MX"))
def test_every_role_has_a_label_in_every_screen_language(locale: str) -> None:
    labels = json.loads((FRONTEND_SOURCE / "i18n" / "locales" / locale / "notifications.json").read_text(encoding="utf-8"))["roles"]
    assert sorted(labels) == ROLE_VALUES


@pytest.mark.parametrize("language", ["en", "ja"])
def test_every_role_has_a_label_in_the_invitation_email(language: str) -> None:
    labels = json.loads((BACKEND_RESOURCES / "i18n" / f"{language}.json").read_text(encoding="utf-8"))["roles"]
    assert sorted(labels) == ROLE_VALUES


ALERTS_API = (FRONTEND_SOURCE / "api" / "alertsApi.ts").read_text(encoding="utf-8")
GROUPING_REASON_CODES = sorted(reason.value for reason in AlertGroupingReason)


def test_the_screen_knows_exactly_the_grouping_reasons_the_server_derives() -> None:
    match = re.search(r"export type AlertGroupingReasonCode =\s*(.*?);", ALERTS_API, re.DOTALL)
    assert match, "AlertGroupingReasonCode not found in frontend/src/api/alertsApi.ts"
    assert sorted(re.findall(r'"([^"]+)"', match.group(1))) == GROUPING_REASON_CODES


@pytest.mark.parametrize("locale", sorted(path.name for path in (FRONTEND_SOURCE / "i18n" / "locales").iterdir() if path.is_dir() and path.name != "es-MX"))
def test_every_grouping_reason_has_a_sentence_in_every_screen_language(locale: str) -> None:
    sentences = json.loads((FRONTEND_SOURCE / "i18n" / "locales" / locale / "alerts.json").read_text(encoding="utf-8"))["groupingReason"]
    assert sorted(sentences) == GROUPING_REASON_CODES
