"""Chat author names are personal data: models see a stable placeholder (``<PERSON_1>``) instead of a name (V12).

Postmortems and chat digests name roles, not people, so every name is replaced before a prompt is built. Where a model's answer
is shown back to responders, :class:`AuthorAliases` can restore the names the model never saw.
"""

from __future__ import annotations

import re

from keigan.utils.pii_masker import PiiMasker

PERSON_PLACEHOLDER_NAME = "PERSON"
UNKNOWN_AUTHOR_LABEL = "Participant"
MINIMUM_NAME_LENGTH = 3  # shorter strings would also match inside ordinary words


def mask_author_name(masker: PiiMasker, author_name: str | None) -> str:
    """The same person always gets the same placeholder within one masker; an unknown author becomes ``Participant``."""
    if not author_name or not author_name.strip():
        return UNKNOWN_AUTHOR_LABEL
    if not masker.enabled:
        return author_name
    return masker.masking_context.placeholder_for(PERSON_PLACEHOLDER_NAME, author_name.strip().lower())


def mask_known_names(masker: PiiMasker, text: str, names: set[str]) -> str:
    """Replace every occurrence of each known person name in ``text`` (whole words, any case) with that person's placeholder."""
    masked_text = text
    for name in sorted((name.strip() for name in names if name and len(name.strip()) >= MINIMUM_NAME_LENGTH), key=len, reverse=True):
        masked_text = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", lambda _match, name=name: mask_author_name(masker, name), masked_text, flags=re.IGNORECASE)
    return masked_text


class AuthorAliases:
    """Placeholders for the authors of one batch of messages, with a way back to the real names for display."""

    def __init__(self, masker: PiiMasker):
        self.masker = masker
        self._names_by_placeholder: dict[str, str] = {}

    def alias(self, author_name: str | None) -> str:
        placeholder = mask_author_name(self.masker, author_name)
        if author_name and placeholder != author_name:
            self._names_by_placeholder[placeholder] = author_name.strip()
        return placeholder

    def restore_names(self, text: str) -> str:
        for placeholder, name in self._names_by_placeholder.items():
            text = text.replace(placeholder, name)
        return text
