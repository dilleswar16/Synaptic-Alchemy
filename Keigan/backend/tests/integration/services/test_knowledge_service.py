"""keigan/services/knowledge_service.py: grounding context and the flagged-document policy (V7)."""

from __future__ import annotations

import uuid

import pytest

from keigan.ai.ai_safety_settings import FlaggedDocumentPolicy, get_ai_safety_settings
from keigan.config.database_config import open_session
from keigan.entities.knowledge_entities import KnowledgeChunk, KnowledgeDocument
from keigan.services.knowledge_service import KnowledgeService
from keigan.utils.text_utils import term_frequencies


async def add_document(application_id: str, marker: str, *, flagged: bool) -> str:
    async with open_session() as session:
        document = KnowledgeDocument(
            application_id=application_id, document_title=f"Doc {marker}", document_category="architecture", original_file_name=f"{marker}.md", content_type="text/markdown",
            storage_path=f"x/{marker}.md", file_sha256_hash=uuid.uuid4().hex + uuid.uuid4().hex, ai_digest_markdown=f"Digest about {marker}", ai_digest_status="ready", possible_prompt_injection=flagged,
        )
        session.add(document)
        await session.flush()
        chunk_text = f"The {marker} component handles settlement retries."
        session.add(KnowledgeChunk(knowledge_document_id=document.knowledge_document_id, application_id=application_id, chunk_sequence_number=0, chunk_text=chunk_text, search_terms_json=term_frequencies(chunk_text)))
        return document.knowledge_document_id


async def grounding_for(application_id: str, marker: str):  # noqa: ANN201
    async with open_session() as session:
        return await KnowledgeService(session).build_grounding_context(application_id, f"{marker} settlement retries", token_budget=6000)


async def test_a_flagged_document_is_kept_but_the_grounding_says_it_is_flagged(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_ai_safety_settings(), "ai_flagged_document_policy", FlaggedDocumentPolicy.WARN)
    application_id = seed_context.application_ids_by_code["CLMJP"]
    marker = f"zq{uuid.uuid4().hex[:8]}"
    await add_document(application_id, marker, flagged=True)
    grounding = await grounding_for(application_id, marker)
    assert marker in grounding.knowledge_markdown
    assert grounding.contains_flagged_content is True


async def test_an_unflagged_document_does_not_flag_the_grounding(seed_context) -> None:
    application_id = seed_context.application_ids_by_code["PAYAU"]
    marker = f"zq{uuid.uuid4().hex[:8]}"
    await add_document(application_id, marker, flagged=False)
    grounding = await grounding_for(application_id, marker)
    assert marker in grounding.knowledge_markdown
    assert grounding.contains_flagged_content is False


async def test_the_exclude_policy_keeps_a_flagged_document_out_of_the_grounding(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_ai_safety_settings(), "ai_flagged_document_policy", FlaggedDocumentPolicy.EXCLUDE)
    application_id = seed_context.application_ids_by_code["CHAD"]
    marker = f"zq{uuid.uuid4().hex[:8]}"
    await add_document(application_id, marker, flagged=True)
    grounding = await grounding_for(application_id, marker)
    assert marker not in grounding.knowledge_markdown
    assert all(marker not in reference.title for reference in grounding.references)
    assert grounding.contains_flagged_content is False
