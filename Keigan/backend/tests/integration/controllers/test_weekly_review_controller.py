"""POST /api/intelligence-reports/{id}/review: who may review a weekly digest (spec 31, AC-5, AC-7)."""

from __future__ import annotations

import httpx

from keigan.config.database_config import open_session
from keigan.entities.application_entities import Application
from keigan.services.intelligence_service import IntelligenceService
from support import users
from support.http import AuthHeaders


async def a_weekly_digest(seed_context) -> str:
    async with open_session() as session:
        application = await session.get(Application, seed_context.application_ids_by_code["CLMJP"])
        report = await IntelligenceService(session)._build_report(application, "weekly_digest", None)
        return report.intelligence_report_id


async def test_only_an_application_admin_reviews_and_only_once(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    report_id = await a_weekly_digest(seed_context)
    url = f"/api/intelligence-reports/{report_id}/review"
    assert (await client.post(url, headers=await auth_headers(users.CLMJP_AND_PAYAU_READER), json={"noteText": "I read it."})).status_code == 403
    assert (await client.post(url, headers=await auth_headers(users.NO_ACCESS), json={})).status_code == 403
    reviewed = await client.post(url, headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER), json={"noteText": "Agreed to chase the overdue items."})
    assert reviewed.status_code == 200, reviewed.text
    body = reviewed.json()
    assert body["reviewedBy"] == users.CLMJP_ADMIN_CHAD_READER and body["reviewedAt"] and body["reviewNote"] == "Agreed to chase the overdue items."
    assert {"budget", "actionItems"} <= set(body["reportSections"])
    assert (await client.post(url, headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER), json={})).status_code == 422
    listed = (await client.get("/api/intelligence-reports?applicationId=" + seed_context.application_ids_by_code["CLMJP"], headers=await auth_headers(users.CLMJP_AND_PAYAU_READER))).json()
    assert next(row for row in listed if row["intelligenceReportId"] == report_id)["reviewedBy"] == users.CLMJP_ADMIN_CHAD_READER
