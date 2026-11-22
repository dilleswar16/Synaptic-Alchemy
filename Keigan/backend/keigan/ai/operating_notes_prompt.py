"""The application team's operating notes as a prompt section.

The notes are written by people, so they are untrusted text like uploaded knowledge: masked, checked for instruction-like phrasing with the same indicator
catalogue, never given a citation code. They are guidance for the AI, not evidence.
"""

from __future__ import annotations

from keigan.ai.ai_safety_settings import FlaggedDocumentPolicy, get_ai_safety_settings
from keigan.ai.llm_gateway import PromptSection
from keigan.ai.prompt_safety import assess_prompt_injection
from keigan.utils.pii_masker import PiiMasker

# The prompts that receive the section name it by this title. The setting caps the notes at 20 000 characters, which is the default length a prompt section keeps.
OPERATING_NOTES_TITLE = "Operating notes from the application team (guidance, not evidence)"
OPERATING_NOTES_SOURCE_LABEL = "application operating notes"


def build_operating_notes_section(notes_text: str | None, masker: PiiMasker) -> PromptSection | None:
    """``None`` when there are no notes, or when the notes look like an injection attempt and the flagged-document policy for knowledge is ``exclude``."""
    if not notes_text or not notes_text.strip():
        return None
    masked_text = masker.mask_text(notes_text.strip())
    is_flagged = assess_prompt_injection(masked_text).is_suspicious
    if is_flagged and get_ai_safety_settings().ai_flagged_document_policy == FlaggedDocumentPolicy.EXCLUDE:
        return None
    return PromptSection(OPERATING_NOTES_TITLE, masked_text, is_untrusted=True, source_label=OPERATING_NOTES_SOURCE_LABEL, is_flagged=is_flagged)
