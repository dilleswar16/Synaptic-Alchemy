"""keigan/services/communication_service.py: drafts are sanitised and never carry fix commands to stakeholders (V3 audience rule, V8)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from keigan.ai.investigation_ai_schemas import CommunicationDraft, CommunicationDraftSet
from keigan.ai.llm_gateway import PromptSection
from keigan.config.database_config import open_session
from keigan.entities.incident_entities import IncidentCommunication, Investigation
from keigan.services.communication_service import CommunicationService
from support import users
from support.http import AuthHeaders
from support.jobs import drain_jobs


@pytest.fixture(scope="module")
async def investigation_id(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> str:
    response = await client.post(
        "/api/investigations", headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER),
        json={"applicationId": seed_context.application_ids_by_code["CLMJP"], "description": "Claim submissions are timing out for customers in Japan since 10:00."},
    )
    assert response.status_code == 202, response.text
    await drain_jobs()
    return response.json()["jobId"]


async def draft_with(investigation_id: str, draft: CommunicationDraft) -> tuple[list[IncidentCommunication], list[PromptSection]]:
    seen_sections: list[PromptSection] = []

    async def ask(feature_name: str, sections: list[PromptSection], output_schema: type, **_: object) -> CommunicationDraftSet:
        seen_sections.extend(sections)
        return CommunicationDraftSet(drafts=[draft])

    async with open_session() as session:
        investigation = await session.get(Investigation, investigation_id)
        investigation.how_to_fix_markdown = "Run:\n```bash\nkubectl -n prod delete pod claims-api-0\n```"
        created = await CommunicationService(session).draft_investigation_communications(investigation, ["preliminary_report"], ["en"], auto_send=False, ask=ask)
        return created, seen_sections


async def test_a_hostile_draft_is_stored_with_no_links_images_html_or_header_injection(investigation_id: str) -> None:
    hostile = CommunicationDraft(
        communication_type="preliminary_report", language_code="en", subject_line="[P2] Claims\r\nBcc: attacker@evil.example",
        body_markdown="Please [verify here](https://evil.example/login) ![t](https://evil.example/p.png) <script>x</script> and open https://evil.example/y",
    )
    created, _ = await draft_with(investigation_id, hostile)
    stored = created[0]
    assert "\n" not in stored.subject_line and "\r" not in stored.subject_line
    assert "](https://evil.example" not in stored.body_markdown
    assert "![" not in stored.body_markdown
    assert "\\<script>" in stored.body_markdown and "<script>" not in stored.body_markdown.replace("\\<script>", "")
    assert "`https://evil.example/y`" in stored.body_markdown


async def test_the_fix_commands_are_not_given_to_the_model_that_writes_stakeholder_updates(investigation_id: str) -> None:
    benign = CommunicationDraft(communication_type="preliminary_report", language_code="en", subject_line="[P2] Claims", body_markdown="We are investigating.")
    _, sections = await draft_with(investigation_id, benign)
    findings = next(section.content for section in sections if section.title == "Investigation findings")
    assert "kubectl" not in findings
    assert "How to fix" not in findings


async def test_a_draft_edited_by_an_admin_is_sanitised_too(client: httpx.AsyncClient, auth_headers: AuthHeaders, investigation_id: str) -> None:
    benign = CommunicationDraft(communication_type="preliminary_report", language_code="en", subject_line="[P2] Claims", body_markdown="We are investigating.")
    created, _ = await draft_with(investigation_id, benign)
    response = await client.patch(
        f"/api/communications/{created[0].communication_id}", headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER),
        json={"subjectLine": "Hi\r\nBcc: x@evil.example", "bodyMarkdown": "[a](https://evil.example/z)"},
    )
    assert response.status_code == 200, response.text
    assert "\n" not in response.json()["subjectLine"]
    assert "](https://evil.example" not in response.json()["bodyMarkdown"]
    async with open_session() as session:
        assert await session.scalar(select(IncidentCommunication.subject_line).where(IncidentCommunication.communication_id == created[0].communication_id)) == response.json()["subjectLine"]
