"""The runbook health of an application (spec 32): the findings of each runbook with the figures behind them, computed on read from stored rows."""

from __future__ import annotations

from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import get_settings
from keigan.dtos.knowledge_dtos import RunbookFindingDto, RunbookHealthResponse, RunbookHealthRowDto
from keigan.entities.incident_entities import Investigation, InvestigationMatchedRunbook
from keigan.entities.knowledge_entities import Runbook
from keigan.entities.status_values import InvestigationFeedbackVerdict
from keigan.services.runbook_health_rules import RunbookFacts, RunbookHealthThresholds, findings_for
from keigan.utils.time_utils import ensure_utc, utc_now


class RunbookHealthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    def thresholds(self) -> RunbookHealthThresholds:
        settings = self.settings
        return RunbookHealthThresholds(
            unused_after_days=settings.runbook_health_unused_after_days, stale_after_days=settings.runbook_health_stale_after_days,
            minimum_rated_investigations=settings.runbook_health_minimum_rated_investigations, wrong_share_percent=settings.runbook_health_wrong_share_percent,
        )

    async def rows(self, application_id: str, today: date | None = None) -> list[RunbookHealthRow]:
        """Every runbook of the application with its counts and findings."""
        today = today or utc_now().date()
        runbooks = list((await self.session.scalars(select(Runbook).where(Runbook.application_id == application_id).order_by(Runbook.runbook_title))).all())
        if not runbooks:
            return []
        counts = {
            runbook_id: (int(matched or 0), int(rated or 0), int(incorrect or 0))
            for runbook_id, matched, rated, incorrect in (await self.session.execute(
                select(
                    InvestigationMatchedRunbook.runbook_id, func.count(), func.sum(case((Investigation.user_feedback_verdict.is_not(None), 1), else_=0)),
                    func.sum(case((Investigation.user_feedback_verdict == InvestigationFeedbackVerdict.INCORRECT, 1), else_=0)),
                ).join(Investigation, Investigation.investigation_id == InvestigationMatchedRunbook.investigation_id)
                .where(InvestigationMatchedRunbook.runbook_id.in_([runbook.runbook_id for runbook in runbooks])).group_by(InvestigationMatchedRunbook.runbook_id)
            )).all()
        }
        thresholds = self.thresholds()
        result: list[RunbookHealthRow] = []
        for runbook in runbooks:
            matched, rated, incorrect = counts.get(runbook.runbook_id, (0, 0, 0))
            facts = RunbookFacts(
                has_trigger_symptoms=bool((runbook.trigger_symptoms_text or "").strip()), has_steps=bool((runbook.runbook_steps_markdown or "").strip()),
                times_referenced_count=runbook.times_referenced_count or 0, created_on=(ensure_utc(runbook.created_at) or utc_now()).date(), updated_on=(ensure_utc(runbook.updated_at) or utc_now()).date(),
                rated_investigation_count=rated, incorrect_rated_count=incorrect,
            )
            result.append(RunbookHealthRow(runbook, matched, rated, incorrect, findings_for(facts, today, thresholds)))
        return result

    async def report(self, application_id: str) -> RunbookHealthResponse:
        rows = await self.rows(application_id)
        ordered = sorted(rows, key=lambda row: (not row.findings, row.runbook.runbook_title.lower()))
        return RunbookHealthResponse(
            runbook_count=len(rows), with_findings_count=sum(1 for row in rows if row.findings),
            runbooks=[
                RunbookHealthRowDto(
                    runbook_id=row.runbook.runbook_id, runbook_title=row.runbook.runbook_title, times_referenced_count=row.runbook.times_referenced_count or 0, last_referenced_at=row.runbook.last_referenced_at,
                    created_at=row.runbook.created_at, updated_at=row.runbook.updated_at, matched_investigation_count=row.matched_count, rated_investigation_count=row.rated_count, incorrect_rated_count=row.incorrect_count,
                    findings=[RunbookFindingDto(kind=finding.kind, parameters=finding.parameters) for finding in row.findings],
                )
                for row in ordered
            ],
        )


class RunbookHealthRow:
    def __init__(self, runbook: Runbook, matched_count: int, rated_count: int, incorrect_count: int, findings: list):  # noqa: ANN001
        self.runbook, self.matched_count, self.rated_count, self.incorrect_count, self.findings = runbook, matched_count, rated_count, incorrect_count, findings
