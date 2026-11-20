"""PII and secret masking with stable placeholders.

The same original value always maps to the same placeholder within one :class:`MaskingContext` (for example one
investigation), so the AI can still correlate "the same customer failed 12 times" without ever seeing who.
"""

from __future__ import annotations

import ipaddress
import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import yaml

from keigan.config.settings import RESOURCES_DIRECTORY, get_settings

_IPV4_PATTERN = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
# Candidates only: every match is confirmed with ipaddress, so clock times such as 10:00:00 are left alone.
_IPV6_CANDIDATE_PATTERN = re.compile(r"(?<![\w:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])")
_JSON_KEY_SEPARATOR_PATTERN = re.compile(r"[\s_-]")


@dataclass(frozen=True)
class MaskingPattern:
    pattern_name: str
    placeholder_name: str
    compiled_regex: re.Pattern[str]
    is_numbered: bool
    check_validator: Callable[[str], bool] | None


def normalize_json_key(json_key: Any) -> str:
    """Canonical form of a key so client_secret, Client-Secret and full-width variants match one catalog entry."""
    return _JSON_KEY_SEPARATOR_PATTERN.sub("", unicodedata.normalize("NFKC", str(json_key)).lower())


@lru_cache
def _load_masking_configuration() -> tuple[tuple[MaskingPattern, ...], dict[str, str]]:
    configuration = yaml.safe_load((RESOURCES_DIRECTORY / "catalogs" / "pii_patterns.yaml").read_text(encoding="utf-8"))
    masking_patterns = tuple(
        _build_masking_pattern(pattern_entry) for pattern_entry in configuration["patterns"] if pattern_entry.get("enabled", True)
    )
    placeholder_by_json_key = {
        normalize_json_key(json_key): placeholder_name
        for placeholder_name, json_keys in (configuration.get("sensitive_json_keys") or {}).items()
        for json_key in json_keys
    }
    return masking_patterns, placeholder_by_json_key


def _build_masking_pattern(pattern_entry: dict[str, Any]) -> MaskingPattern:
    validator_name = pattern_entry.get("validator")
    if validator_name is not None and validator_name not in _CHECK_VALIDATORS:
        raise ValueError(f"pii_patterns.yaml pattern '{pattern_entry['name']}' names unknown validator '{validator_name}'.")
    return MaskingPattern(
        pattern_name=pattern_entry["name"],
        placeholder_name=pattern_entry["placeholder"],
        compiled_regex=re.compile(pattern_entry["regex"]),
        is_numbered=pattern_entry.get("numbered", True),
        check_validator=_CHECK_VALIDATORS[validator_name] if validator_name else None,
    )


def _passes_luhn_check(candidate_text: str) -> bool:
    digits = [int(character) for character in candidate_text if character.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    for position, digit in enumerate(reversed(digits)):
        if position % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _passes_japan_my_number_check_digit(candidate_text: str) -> bool:
    """Official My Number check digit: weights 2..7 then 2..6 from the right, remainder mod 11 (0 or 1 gives check digit 0)."""
    digits = [int(character) for character in candidate_text if character.isdigit()]
    if len(digits) != 12:
        return False
    weighted_sum = 0
    for position_from_right, digit in enumerate(reversed(digits[:11]), start=1):
        weight = position_from_right + 1 if position_from_right <= 6 else position_from_right - 5
        weighted_sum += digit * weight
    remainder = weighted_sum % 11
    expected_check_digit = 0 if remainder <= 1 else 11 - remainder
    return digits[11] == expected_check_digit


_CHECK_VALIDATORS: dict[str, Callable[[str], bool]] = {
    "luhn": _passes_luhn_check,
    "japan_my_number_check_digit": _passes_japan_my_number_check_digit,
}


@dataclass
class MaskingContext:
    """Keeps placeholder numbering stable across many texts (one investigation, one chat turn)."""

    placeholders_by_original_value: dict[str, str] = field(default_factory=dict)
    counters_by_placeholder_name: dict[str, int] = field(default_factory=dict)
    masked_value_count: int = 0

    def placeholder_for(self, placeholder_name: str, original_value: str, is_numbered: bool = True) -> str:
        self.masked_value_count += 1
        if not is_numbered:
            return f"<{placeholder_name}>"
        lookup_key = f"{placeholder_name}:{original_value}"
        existing_placeholder = self.placeholders_by_original_value.get(lookup_key)
        if existing_placeholder:
            return existing_placeholder
        next_number = self.counters_by_placeholder_name.get(placeholder_name, 0) + 1
        self.counters_by_placeholder_name[placeholder_name] = next_number
        new_placeholder = f"<{placeholder_name}_{next_number}>"
        self.placeholders_by_original_value[lookup_key] = new_placeholder
        return new_placeholder


class PiiMasker:
    def __init__(self, masking_context: MaskingContext | None = None, ip_address_mode: str | None = None, enabled: bool | None = None):
        settings = get_settings()
        self.masking_context = masking_context or MaskingContext()
        self.ip_address_mode = ip_address_mode or settings.pii_mask_ip_addresses
        self.enabled = settings.pii_masking_enabled if enabled is None else enabled
        self.masking_patterns, self.placeholder_by_json_key = _load_masking_configuration()

    @property
    def masked_value_count(self) -> int:
        return self.masking_context.masked_value_count

    def mask_text(self, text: str | None) -> str:
        if not text or not self.enabled:
            return text or ""
        # Full-width and other compatibility forms are folded first, so patterns see the same characters the LLM would.
        masked_text = self._mask_embedded_json(unicodedata.normalize("NFKC", text))
        for masking_pattern in self.masking_patterns:
            masked_text = masking_pattern.compiled_regex.sub(lambda match, pattern=masking_pattern: self._replace_match(match, pattern), masked_text)
        return self._mask_ip_addresses(masked_text)

    def mask_value(self, value: Any) -> Any:
        """Recursively mask strings inside dicts and lists; values under sensitive keys are replaced entirely."""
        if not self.enabled:
            return value
        if isinstance(value, str):
            return self.mask_text(value)
        if isinstance(value, list):
            return [self.mask_value(list_item) for list_item in value]
        if isinstance(value, dict):
            masked_dictionary: dict[Any, Any] = {}
            for dictionary_key, dictionary_value in value.items():
                sensitive_placeholder = self.placeholder_by_json_key.get(normalize_json_key(dictionary_key))
                if sensitive_placeholder and dictionary_value not in (None, "", [], {}):
                    masked_dictionary[dictionary_key] = self.masking_context.placeholder_for(
                        sensitive_placeholder, json.dumps(dictionary_value, default=str), sensitive_placeholder not in ("SECRET", "DOB")
                    )
                else:
                    masked_dictionary[dictionary_key] = self.mask_value(dictionary_value)
            return masked_dictionary
        return value

    def mask_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.mask_value(row) for row in rows]

    def _replace_match(self, match: re.Match[str], masking_pattern: MaskingPattern) -> str:
        matched_text = match.group(0)
        if matched_text.startswith("<") and matched_text.endswith(">"):
            return matched_text
        if masking_pattern.check_validator and not masking_pattern.check_validator(matched_text):
            return matched_text
        return self.masking_context.placeholder_for(masking_pattern.placeholder_name, matched_text, masking_pattern.is_numbered)

    def _mask_embedded_json(self, text: str) -> str:
        stripped_text = text.strip()
        if not (stripped_text.startswith("{") and stripped_text.endswith("}")) or len(stripped_text) > 200_000:
            return text
        try:
            parsed_json = json.loads(stripped_text)
        except json.JSONDecodeError:
            return text
        return json.dumps(self.mask_value(parsed_json), ensure_ascii=False)

    def _mask_ip_addresses(self, text: str) -> str:
        if self.ip_address_mode == "none":
            return text

        def replace_ipv4(match: re.Match[str]) -> str:
            address_text = match.group(0)
            try:
                parsed_address = ipaddress.ip_address(address_text)
            except ValueError:
                return address_text
            if parsed_address.is_loopback or parsed_address.is_unspecified:
                return address_text
            if self.ip_address_mode == "partial":
                address_octets = address_text.split(".")
                return f"{address_octets[0]}.{address_octets[1]}.x.x"
            return self.masking_context.placeholder_for("IP", address_text)

        masked_text = _IPV4_PATTERN.sub(replace_ipv4, text)
        return _IPV6_CANDIDATE_PATTERN.sub(self._replace_ipv6_candidate, masked_text)

    def _replace_ipv6_candidate(self, match: re.Match[str]) -> str:
        address_text = match.group(0)
        try:
            parsed_address = ipaddress.IPv6Address(address_text)
        except ValueError:
            return address_text
        if parsed_address.is_loopback or parsed_address.is_unspecified:
            return address_text
        if self.ip_address_mode == "partial":
            leading_groups = parsed_address.exploded.split(":")[:2]
            return f"{leading_groups[0]}:{leading_groups[1]}:x:x"
        return self.masking_context.placeholder_for("IP", address_text)
