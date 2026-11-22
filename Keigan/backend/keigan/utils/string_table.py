"""The EN/JA string tables in ``resources/i18n`` and the lookup both the notification renderer and the Ask Keigan error catalogue use."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from keigan.config.settings import RESOURCES_DIRECTORY

SUPPORTED_LANGUAGE_CODES = ("en", "ja")
FALLBACK_LANGUAGE_CODE = "en"


@lru_cache(maxsize=4)
def string_table(language_code: str) -> dict[str, Any]:
    table_path = RESOURCES_DIRECTORY / "i18n" / f"{language_code}.json"
    return json.loads(table_path.read_text(encoding="utf-8"))


def resolve_language_code(language_code: str | None) -> str:
    short_code = (language_code or FALLBACK_LANGUAGE_CODE).split("-")[0].lower()
    return short_code if short_code in SUPPORTED_LANGUAGE_CODES else FALLBACK_LANGUAGE_CODE


def find_string(language_code: str | None, dotted_path: str) -> str | None:
    """The unformatted string at ``dotted_path`` in the requested language, falling back to English; None when neither has it."""
    for candidate_language in (resolve_language_code(language_code), FALLBACK_LANGUAGE_CODE):
        node: Any = string_table(candidate_language)
        for path_part in dotted_path.split("."):
            node = node.get(path_part) if isinstance(node, dict) else None
        if isinstance(node, str):
            return node
    return None


def translate(language_code: str | None, dotted_path: str, **format_values: Any) -> str:
    """Looks a string up in the requested language, falling back to English; ``{placeholders}`` are formatted."""
    template = find_string(language_code, dotted_path)
    if template is None:
        return dotted_path
    try:
        return template.format(**format_values)
    except (KeyError, IndexError):
        return template
