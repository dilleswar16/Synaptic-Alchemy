"""The checks every suggested command passes before it may be shown as copyable (spec 33, 4.4 steps 3, 5 and 8, applied to the commands a hypothesis proposes today).

A command that fails is *withheld*: the step keeps its description, the command is not shown, and the reason is stored. The hypothesis's risk still counts the command that was withheld.
"""

from __future__ import annotations

import re

from keigan.ai.command_risk_classifier import classify_command_risk, reveals_secrets
from keigan.ai.fix_command_shape import SLOT_PATTERN, FixCommandTool, FixWithheldReason, check_template_shape, infer_tool
from keigan.entities.status_values import RiskLevel
from keigan.utils.pii_masker import PiiMasker

_SECRET_PLACEHOLDERS = re.compile(r"<(SECRET|JWT|PRIVATE_KEY)>")
WARNING_PRINTS_SECRETS = "prints_secrets"


def contains_secret(text: str) -> bool:
    """True when the masker would replace part of ``text`` with a secret placeholder (a password, key, token, connection string or private key)."""
    return bool(_SECRET_PLACEHOLDERS.search(PiiMasker(enabled=True).mask_text(text)))


def check_suggested_command(command_text: str, command_language: str | None, maximum_characters: int) -> FixWithheldReason | None:
    """None when the command may be shown as copyable. A command written without slots may not contain one, and may not be a chain, a redirect, a placeholder, a secret or a data change."""
    if len(command_text) > maximum_characters:
        return FixWithheldReason.COMMAND_TOO_LONG
    if SLOT_PATTERN.search(command_text):
        return FixWithheldReason.UNKNOWN_SLOT
    tool = infer_tool(command_text, command_language)
    reason = check_template_shape(command_text.rstrip(";") if tool == FixCommandTool.SQL else command_text, tool)
    if reason is not None:
        return reason
    if contains_secret(command_text):
        return FixWithheldReason.SECRET_IN_COMMAND
    if tool == FixCommandTool.SQL and classify_command_risk(command_text) != RiskLevel.LOW:
        return FixWithheldReason.DATA_CHANGING_SQL
    return None


def command_warnings(command_text: str) -> list[str]:
    return [WARNING_PRINTS_SECRETS] if reveals_secrets(command_text) else []
