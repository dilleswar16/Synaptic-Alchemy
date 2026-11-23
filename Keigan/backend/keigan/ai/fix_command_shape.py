"""The shape a suggested command must have to be shown as copyable (spec 33, 6.2).

One command per step, on one line, with no way to chain, redirect, substitute or read a placeholder: each command then gets its own risk, check and undo, and a value cannot change what
the command means. A template that fails is withheld; the step's description stays.
"""

from __future__ import annotations

import re
from enum import StrEnum

from keigan.ai.command_risk_classifier import executable_name, read_only_executable_names, read_only_executable_prefixes, tokenize_command

SLOT_PATTERN = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
_PLACEHOLDER_PATTERN = re.compile(r"<[A-Za-z_][A-Za-z0-9_ -]*>")  # "<resource-group>": bash reads it as a redirect from a file of that name, PowerShell refuses "<"
_POWERSHELL_CMDLET_PATTERN = re.compile(r"^[A-Za-z]+-[A-Za-z]+$")
_KUBECTL_FAMILY = frozenset({"kubectl", "oc", "k"})
_POWERSHELL_FORBIDDEN = ("@(", "iex", "invoke-expression", "--%")
_PIPE_TARGETS_THAT_WRITE = frozenset({"out-file", "tee-object", "set-content", "add-content", "export-csv", "export-clixml", "out-printer"})  # read-only by prefix, but they write


class FixWithheldReason(StrEnum):
    UNSAFE_SHELL_SYNTAX = "unsafe_shell_syntax"
    UNKNOWN_SLOT = "unknown_slot"
    SECRET_IN_COMMAND = "secret_in_command"
    DATA_CHANGING_SQL = "data_changing_sql"
    VALUE_NOT_INSERTABLE = "value_not_insertable"
    COMMAND_TOO_LONG = "command_too_long"
    DESTRUCTIVE_WITHOUT_REVERT = "destructive_without_revert"
    SECRET_SETTING_NAME = "secret_setting_name"
    UNKNOWN_EVIDENCE_CODE = "unknown_evidence_code"


class FixCommandTool(StrEnum):
    KUBECTL = "kubectl"
    AZ = "az"
    HELM = "helm"
    POWERSHELL = "powershell"
    SHELL = "shell"
    SQL = "sql"


def infer_tool(command_text: str, language: str | None = None) -> FixCommandTool:
    """The tool a command line belongs to, from its first word (used for commands that were written without a declared tool)."""
    if (language or "").lower() == "sql":
        return FixCommandTool.SQL
    first = executable_name((tokenize_command(command_text) or [""])[0])
    if first in _KUBECTL_FAMILY:
        return FixCommandTool.KUBECTL
    if first in ("az", "helm"):
        return FixCommandTool(first)
    if _POWERSHELL_CMDLET_PATTERN.match(first) and (language or "").lower() in ("powershell", "pwsh", ""):
        return FixCommandTool.POWERSHELL
    return FixCommandTool.SHELL


def check_template_shape(template: str, tool: FixCommandTool | str, dialect: str = "any") -> FixWithheldReason | None:
    """None when the template (slots allowed) may be shown as a copyable command; otherwise the reason it is withheld."""
    tool = FixCommandTool(tool)
    text = SLOT_PATTERN.sub("VALUE", template or "").strip()
    if not text or "\n" in text or "\r" in text or _PLACEHOLDER_PATTERN.search(text):
        return FixWithheldReason.UNSAFE_SHELL_SYNTAX
    if tool == FixCommandTool.SQL:
        return FixWithheldReason.UNSAFE_SHELL_SYNTAX if ";" in text.rstrip(";") else None  # one statement; a closing semicolon is fine
    if any(forbidden in text for forbidden in (";", "&", "<", ">", "`", "$")):  # chains, redirects, substitution, expansion
        return FixWithheldReason.UNSAFE_SHELL_SYNTAX
    if dialect == "powershell" or tool == FixCommandTool.POWERSHELL:
        lowered = text.lower()
        if any(forbidden in lowered for forbidden in _POWERSHELL_FORBIDDEN):
            return FixWithheldReason.UNSAFE_SHELL_SYNTAX
    if not _pipe_is_allowed(text):
        return FixWithheldReason.UNSAFE_SHELL_SYNTAX
    return None if _first_word_belongs_to(text.split("|")[0], tool) else FixWithheldReason.UNSAFE_SHELL_SYNTAX


def _pipe_is_allowed(text: str) -> bool:
    """At most one pipe, and only into a program that reads."""
    parts = text.split("|")
    if len(parts) == 1:
        return True
    if len(parts) > 2:
        return False
    tokens = tokenize_command(parts[1])
    if not tokens:
        return False
    target = executable_name(tokens[0])
    if target in _PIPE_TARGETS_THAT_WRITE:
        return False
    return target in read_only_executable_names() or target.startswith(read_only_executable_prefixes())


def _first_word_belongs_to(command_text: str, tool: FixCommandTool) -> bool:
    tokens = tokenize_command(command_text)
    if not tokens:
        return False
    first = executable_name(tokens[0])
    if tool == FixCommandTool.KUBECTL:
        return first in _KUBECTL_FAMILY
    if tool in (FixCommandTool.AZ, FixCommandTool.HELM):
        return first == tool.value
    if tool == FixCommandTool.POWERSHELL:
        return bool(_POWERSHELL_CMDLET_PATTERN.match(first))
    return True  # "shell": an unknown executable is allowed here and rated at least medium by the classifier
