"""The kinds of value a suggested fix may put into a command, and the rules a value must meet (spec 33, 4.2.2 and 6.3).

Telemetry, tickets and notes are untrusted. A value from them reaches a command only through a typed slot: it must match the kind's pattern (which excludes every shell-special character and
a leading dash), and the renderer quotes it. A value that fails is never shown, because it may be the attack.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from typing import Any

import yaml

from keigan.config.settings import RESOURCES_DIRECTORY


class ValueRefusal(StrEnum):
    UNKNOWN_KIND = "unknown_kind"
    MASKED = "masked"  # the masker's placeholder: Keigan never keeps the real value
    TOO_LONG = "too_long"
    STARTS_WITH_DASH = "starts_with_dash"  # would be read as an option
    PATTERN = "pattern"


@dataclass(frozen=True)
class _Kinds:
    patterns: dict[str, re.Pattern[str]]
    maximum_lengths: dict[str, int]
    bare_safe: re.Pattern[str]
    masking_placeholder: re.Pattern[str]
    secret_setting_name_fragments: tuple[str, ...]
    raw: dict[str, Any]


@lru_cache
def _load() -> _Kinds:
    catalog = yaml.safe_load((RESOURCES_DIRECTORY / "catalogs" / "fix_parameter_kinds.yaml").read_text(encoding="utf-8"))
    return _Kinds(
        patterns={name: re.compile(entry["pattern"]) for name, entry in catalog["kinds"].items()}, maximum_lengths={name: int(entry["maximum_length"]) for name, entry in catalog["kinds"].items()},
        bare_safe=re.compile(catalog["bare_safe_pattern"]), masking_placeholder=re.compile(catalog["masking_placeholder_pattern"]),
        secret_setting_name_fragments=tuple(catalog["secret_setting_name_fragments"]), raw=catalog["kinds"],
    )


def kind_names() -> list[str]:
    return sorted(_load().patterns)


def kind_catalogue() -> dict[str, dict[str, Any]]:
    """The catalogue entries the API sends to the browser, so typed input is checked with the same patterns."""
    return {name: dict(entry) for name, entry in _load().raw.items()}


def check_value(kind: str, value: str) -> ValueRefusal | None:
    """None when ``value`` may be inserted for ``kind``; otherwise why not."""
    kinds = _load()
    if kind not in kinds.patterns:
        return ValueRefusal.UNKNOWN_KIND
    if kinds.masking_placeholder.fullmatch(value):
        return ValueRefusal.MASKED
    if len(value) > kinds.maximum_lengths[kind]:
        return ValueRefusal.TOO_LONG
    if value.startswith("-"):
        return ValueRefusal.STARTS_WITH_DASH
    if not kinds.patterns[kind].fullmatch(value):  # fullmatch: a pattern's $ also matches before a trailing newline
        return ValueRefusal.PATTERN
    return None


def needs_quotes(value: str) -> bool:
    return not _load().bare_safe.fullmatch(value)


def quote(value: str) -> str:
    """Bare when safe, otherwise in single quotes. Correct in bash and PowerShell because no value that passed ``check_value`` contains a quote character."""
    assert "'" not in value, "a value with a quote must never reach the renderer"
    return f"'{value}'" if needs_quotes(value) else value


def is_secret_setting_name(setting_name: str) -> bool:
    lowered = setting_name.lower().replace("_", "").replace("-", "").replace(".", "").replace(":", "")
    return any(fragment in lowered for fragment in _load().secret_setting_name_fragments)
