"""GET /api/applications/{id}/runbook-health: who may read it and what it returns (spec 32, AC-5)."""

from __future__ import annotations

from datetime import timedelta

import httpx

from keigan.config.database_config import open_session
from keigan.entities.knowledge_entities import Runbook
from keigan.utils.time_utils import utc_now
from support import users
from support.http import AuthHeaders


async def test_a_reader_sees_the_findings_and_an_outsider_does_not(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    application_id = seed_context.application_ids_by_code["PADMF"]
    async with open_session() as session:
        session.add(Runbook(
            application_id=application_id, runbook_title="Old and never used", trigger_symptoms_text="x", runbook_steps_markdown="y", times_referenced_count=0,
            created_at=utc_now() - timedelta(days=400), updated_at=utc_now() - timedelta(days=400),
        ))
    admin = await auth_headers(users.KEIGAN_ADMIN)
    body = (await client.get(f"/api/applications/{application_id}/runbook-health", headers=admin)).json()
    row = next(row for row in body["runbooks"] if row["runbookTitle"] == "Old and never used")
    assert {finding["kind"] for finding in row["findings"]} == {"never_used", "not_updated"} and row["findings"][0]["parameters"]["days"] >= 400
    assert body["withFindingsCount"] >= 1 and body["runbooks"][0]["findings"]  # findings first
    assert (await client.get(f"/api/applications/{application_id}/runbook-health", headers=await auth_headers(users.NO_ACCESS))).status_code == 403
