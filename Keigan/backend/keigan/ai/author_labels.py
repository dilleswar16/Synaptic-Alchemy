"""Chat author names are personal data: models see a stable placeholder (``<PERSON_1>``) instead of a name (V12)."""

from __future__ import annotations

from keigan.utils.pii_masker import PiiMasker

PERSON_PLACEHOLDER_NAME = "PERSON"


def mask_author_name(masker: PiiMasker, author_name: str | None) -> str:
    """The same person always gets the same placeholder within one masker; an unknown author becomes ``Participant``."""
    if not author_name or not author_name.strip():
        return "Participant"
    if not masker.enabled:
        return author_name
    return masker.masking_context.placeholder_for(PERSON_PLACEHOLDER_NAME, author_name.strip().lower())
