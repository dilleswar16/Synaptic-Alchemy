"""keigan/services/investigation_service.py: a manual investigation end to end on the mock LLM and simulated telemetry."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import func, select

from keigan.config.database_config import open_session
from keigan.entities.incident_entities import Investigation, InvestigationEvidence, InvestigationHypothesis
from support import users
from support.http import AuthHeaders
from support.jobs import drain_jobs


@pytest.fixture(scope="module")
async def completed_investigation_id(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> str:
    response = await client.post(
        "/api/investigations",
        headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER),
        json={"applicationId": seed_context.application_ids_by_code["CLMJP"], "description": "Claim submissions are timing out for customers in Japan since 10:00."},
    )
    assert response.status_code == 202, response.text
    investigation_id = response.json()["jobId"]  # the accepted job id is the investigation id
    await drain_jobs()
    return investigation_id


async def test_investigation_completes_with_a_summary(completed_investigation_id: str) -> None:
    async with open_session() as session:
        investigation = await session.get(Investigation, completed_investigation_id)
    assert investigation is not None
    assert investigation.investigation_status == "completed", investigation.failure_reason
    assert investigation.executive_summary


async def test_investigation_has_one_hypothesis_per_perspective(completed_investigation_id: str) -> None:
    async with open_session() as session:
        perspectives = (await session.scalars(select(InvestigationHypothesis.analysis_perspective).where(InvestigationHypothesis.investigation_id == completed_investigation_id))).all()
    assert sorted(perspectives) == ["application", "dependencies", "infrastructure"]


async def test_investigation_collects_evidence(completed_investigation_id: str) -> None:
    async with open_session() as session:
        evidence_count = await session.scalar(select(func.count()).select_from(InvestigationEvidence).where(InvestigationEvidence.investigation_id == completed_investigation_id))
    assert evidence_count > 0


async def test_reader_of_the_application_can_open_the_investigation(client: httpx.AsyncClient, auth_headers: AuthHeaders, completed_investigation_id: str) -> None:
    response = await client.get(f"/api/investigations/{completed_investigation_id}", headers=await auth_headers(users.CLMJP_AND_PAYAU_READER))
    assert response.status_code == 200


async def test_non_member_cannot_open_the_investigation(client: httpx.AsyncClient, auth_headers: AuthHeaders, completed_investigation_id: str) -> None:
    response = await client.get(f"/api/investigations/{completed_investigation_id}", headers=await auth_headers(users.NO_ACCESS))
    assert response.status_code == 403
