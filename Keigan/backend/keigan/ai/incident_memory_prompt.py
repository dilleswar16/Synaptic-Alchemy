"""Past incidents as a prompt section for the hypotheses (spec 34, 4.6).

Only what code wrote and what people confirmed goes in: one block per remembered incident, built here from stored fields (never a free-form model summary), masked, checked for instruction-like
phrasing like every other untrusted text, and given no citation code, so a memory can never count as grounding for a claim. The section is a hint about what happened before.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from keigan.ai.ai_safety_settings import FlaggedDocumentPolicy, get_ai_safety_settings
from keigan.ai.llm_gateway import PromptSection
from keigan.ai.prompt_safety import assess_prompt_injection
from keigan.entities.status_values import IncidentMemoryKeyKind, InvestigationFeedbackVerdict
from keigan.utils.pii_masker import PiiMasker

# The hypothesis prompts name the section by this title.
SIMILAR_INCIDENTS_TITLE = "Similar past incidents (hints, not evidence)"
SIMILAR_INCIDENTS_SOURCE_LABEL = "earlier investigations"
NONE_RECORDED = "None recorded."
_REASON_PHRASES = {
    IncidentMemoryKeyKind.SERVICE: "same service", IncidentMemoryKeyKind.SHARED_RESOURCE: "same shared resource", IncidentMemoryKeyKind.ALERT_RULE: "same alert rule",
    IncidentMemoryKeyKind.ERROR_SIGNATURE: "same error signature", IncidentMemoryKeyKind.CHANGE_OPERATION: "same kind of change", IncidentMemoryKeyKind.DEPENDENCY_TARGET: "same failing dependency",
    IncidentMemoryKeyKind.INCIDENT_CATEGORY: "same incident category",
}
_TRUST_PHRASES = {
    InvestigationFeedbackVerdict.CORRECT: "confirmed by an application admin", InvestigationFeedbackVerdict.PARTIALLY_CORRECT: "partly confirmed by an application admin", None: "not reviewed",
}


@dataclass(frozen=True)
class PromptMemory:
    entry_id: str
    age_days: int
    verdict: str | None
    reason_kinds: Sequence[str]
    is_stale: bool
    cause_text: str | None
    fix_text: str | None


@dataclass(frozen=True)
class MemorySection:
    section: PromptSection
    given_entry_ids: list[str]  # the entries that are in the section, in order


def _block(memory: PromptMemory, masker: PiiMasker) -> str:
    matched = ", ".join(_REASON_PHRASES.get(kind, kind) for kind in memory.reason_kinds) or "similar wording"
    lines = [f"- {memory.age_days} days ago; {_TRUST_PHRASES.get(memory.verdict, 'not reviewed')}; matched on: {matched}; may be out of date: {'yes' if memory.is_stale else 'no'}."]
    if memory.cause_text:
        lines.append(f"  Cause then: {masker.mask_text(memory.cause_text)}")
    if memory.fix_text:
        lines.append(f"  Fix then: {masker.mask_text(memory.fix_text)}")
    return "\n".join(lines)


def build_memory_section(memories: Sequence[PromptMemory], masker: PiiMasker) -> MemorySection:
    """The section for the given memories. One that looks like an injection attempt is left out under the ``exclude`` policy and kept, flagged, otherwise."""
    blocks: list[str] = []
    given: list[str] = []
    is_flagged = False
    for memory in memories:
        block = _block(memory, masker)
        flagged = assess_prompt_injection(block).is_suspicious
        if flagged and get_ai_safety_settings().ai_flagged_document_policy == FlaggedDocumentPolicy.EXCLUDE:
            continue
        is_flagged = is_flagged or flagged
        blocks.append(block)
        given.append(memory.entry_id)
    return MemorySection(
        PromptSection(SIMILAR_INCIDENTS_TITLE, "\n".join(blocks) or NONE_RECORDED, is_untrusted=True, source_label=SIMILAR_INCIDENTS_SOURCE_LABEL, is_flagged=is_flagged), given,
    )
