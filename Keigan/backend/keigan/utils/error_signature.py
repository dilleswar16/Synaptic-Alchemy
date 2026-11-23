"""Turns an error message template into a signature that is the same for the same problem (spec 34, 4.3). Pure: no database, no network.

Two occurrences of one error differ in the numbers, ids and personal details they carry, not in the problem. The signature drops those: numbers become ``#``, GUIDs and hex ids become ``<id>``,
and values the masker replaced become their category (``<email>``). The signature is hashed for the key table; the readable form is kept, shortened and masked, for "matched on ...".
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

MAXIMUM_SIGNATURE_CHARACTERS = 300

_MASKING_PLACEHOLDER = re.compile(r"<([A-Za-z]+(?:_[A-Za-z]+)*)_\d+>")  # <EMAIL_1>, <IP_ADDRESS_14>
_GUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
_HEX_LITERAL = re.compile(r"\b0x[0-9a-f]+\b")
_HEX_TOKEN = re.compile(r"\b(?=[0-9a-f]*\d)[0-9a-f]{8,}\b")  # eight or more hex characters with at least one digit: a hash or an id, not a word such as "deadbeef"
_NUMBER = re.compile(r"\d+(?:\.\d+)*")
_WHITESPACE = re.compile(r"\s+")


def normalize_error_template(template: str | None) -> str:
    if not template or not template.strip():
        return ""
    text = unicodedata.normalize("NFKC", template)
    text = _MASKING_PLACEHOLDER.sub(lambda match: f"<{match.group(1).lower()}>", text)
    text = text.lower()
    for pattern in (_GUID, _HEX_LITERAL, _HEX_TOKEN):
        text = pattern.sub("<id>", text)
    text = _NUMBER.sub("#", text)
    return _WHITESPACE.sub(" ", text).strip()[:MAXIMUM_SIGNATURE_CHARACTERS]


def hash_key_value(normalised_value: str) -> str:
    """SHA-256 of a normalised key value, as 64 hex characters (the key table stores the hash, so lookups are one indexed equality)."""
    return hashlib.sha256(normalised_value.encode("utf-8")).hexdigest()
