"""Investigation lifecycle: start, run the investigation graph, re-run, feedback, and the read models behind the investigation page.

Slice S2. Contract methods (used by S3 alert groups and S4 predictive signals) keep their signatures.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.investigation_graph import InvestigationGraphRunner
from keigan.config.logging_config import current_correlation_id
from keigan.config.settings import get_settings
from keigan.dtos.common_dtos import JobAcceptedResponse, PagedResult
from keigan.dtos.incident_dtos import ApplicationReference
from keigan.ai.fix_plan import resolve_plan_steps
from keigan.dtos.investigation_dtos import (
    NOT_RECORDED_OUTCOME, CoverageGapDto, EvidenceDto, FixPlanDto, FixStepV2Dto, HypothesisDto, InvestigationDetailDto, InvestigationFeedbackRequest, InvestigationOutcomeDto, InvestigationProgressDto,
    InvestigationSummaryDto, RunbookReference, ServiceReference, StartInvestigationRequest, TimelineEventDto,
)
from keigan.entities.alert_entities import Alert, AlertDecision, AlertGroup
from keigan.entities.application_entities import Application, MonitoredService
from keigan.entities.incident_entities import Incident, Investigation, InvestigationCoverageGap, InvestigationEvidence, InvestigationHypothesis, InvestigationTimelineEvent
from keigan.entities.knowledge_entities import Runbook
from keigan.entities.status_values import CoverageGapKind, CoverageGapReason, EvidenceCheckOutcome, InvestigationStage, InvestigationStatus
from keigan.exceptions.keigan_exceptions import BusinessValidationException, NotFoundException
from keigan.security.current_user import CurrentUser
from keigan.services.alert_group_link_service import AlertGroupLinkService
from keigan.services.alert_service import AlertService
from keigan.services.audit_service import AuditService
from keigan.services.authorization_service import AuthorizationService
from keigan.services.incident_memory_builder import enqueue_memory_refresh
from keigan.services.service_scope import unknown_service_ids
from keigan.utils.pii_masker import PiiMasker
from keigan.utils.time_utils import utc_now
from keigan.workers.job_queue import JobQueue

logger = logging.getLogger(__name__)


def _evidence_number(evidence_code: str) -> int:
    return int("".join(character for character in evidence_code if character.isdigit()) or 0)


def outcome_code_of(investigation: Investigation) -> str | None:
    """The outcome as the list and the detail show it: the stored one, ``not_recorded`` for an investigation that finished before outcomes existed, nothing while it runs, failed or ended evidence only."""
    if investigation.investigation_outcome:
        return investigation.investigation_outcome
    return NOT_RECORDED_OUTCOME if investigation.investigation_status == InvestigationStatus.COMPLETED else None


def outcome_of(investigation: Investigation) -> InvestigationOutcomeDto | None:
    code = outcome_code_of(investigation)
    if code is None:
        return None
    return InvestigationOutcomeDto(
        code=code, proposed_code=investigation.proposed_investigation_outcome, guard_code=investigation.outcome_guard_code, reason_markdown=investigation.outcome_reason_markdown,
    )


class InvestigationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ══ Contract (S3, S4, jobs) ═══════════════════════════════════════════════
    async def start_investigation(
        self,
        application_id: str,
        investigation_trigger: str,
        *,
        incident_id: str | None = None,
        alert_group_id: str | None = None,
        service_ids: list[str] | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        description: str | None = None,
        requested_by_user_principal_name: str | None = None,
    ) -> str:
        """Create a queued investigation and enqueue ``run_investigation``. Returns investigation_id."""
        investigation = Investigation(
            application_id=application_id, incident_id=incident_id, investigation_trigger=investigation_trigger, investigation_status=InvestigationStatus.QUEUED,
            current_stage_name=InvestigationStage.TRIAGE, progress_percent=0, stage_messages_json=[{"at": utc_now().isoformat(), "stage": "queued", "message": "Investigation queued"}],
            investigation_window_start=window_start, investigation_window_end=window_end,
            triage_result_json={"manual_description": PiiMasker().mask_text(description)} if description else None,
            requested_by_user_principal_name=requested_by_user_principal_name, created_by_user_principal_name=requested_by_user_principal_name,
        )
        investigation.replace_linked_ids("investigated_service_links", service_ids or [])
        self.session.add(investigation)
        await self.session.flush()
        if alert_group_id:
            alert_group = await self.session.get(AlertGroup, alert_group_id)
            if alert_group is not None:
                await AlertGroupLinkService(self.session).link(alert_group, investigation_id=investigation.investigation_id)
        await JobQueue(self.session).enqueue("run_investigation", {"investigation_id": investigation.investigation_id}, deduplication_key=f"run_investigation:{investigation.investigation_id}", priority_number=10)
        return investigation.investigation_id

    async def attach_alerts_to_investigation(self, investigation_id: str, alert_ids: list[str]) -> None:
        """Record later alerts of the same alert group as timeline events (no new investigation)."""
        investigation = await self.session.get(Investigation, investigation_id)
        if investigation is None or not alert_ids:
            return
        known_references = set(
            (await self.session.scalars(select(InvestigationTimelineEvent.source_reference).where(InvestigationTimelineEvent.investigation_id == investigation_id, InvestigationTimelineEvent.event_type == "alert"))).all()
        )
        for alert in (await self.session.scalars(select(Alert).where(Alert.alert_id.in_(alert_ids)))).all():
            if alert.alert_id in known_references:
                continue
            self.session.add(
                InvestigationTimelineEvent(
                    incident_id=investigation.incident_id, investigation_id=investigation_id, event_occurred_at=alert.first_seen_at, event_type="alert",
                    event_title=f"Alert fired: {alert.rule_name}", event_details_markdown=alert.alert_summary, event_source="alert_intake", source_reference=alert.alert_id,
                )
            )

    async def run_investigation(self, investigation_id: str) -> dict[str, Any] | None:
        """Job handler: run the graph; failures are recorded on the investigation instead of retried blindly."""
        return await self._run(investigation_id, offline_ai=False)

    async def run_investigation_offline(self, investigation_id: str) -> dict[str, Any] | None:
        """Seed helper: same pipeline, but AI steps use the offline mock factories regardless of the configured provider."""
        return await self._run(investigation_id, offline_ai=True)

    async def _run(self, investigation_id: str, offline_ai: bool) -> dict[str, Any] | None:
        investigation = await self.session.get(Investigation, investigation_id)
        if investigation is None or investigation.investigation_status in (InvestigationStatus.COMPLETED, InvestigationStatus.COMPLETED_EVIDENCE_ONLY, InvestigationStatus.CANCELLED):
            return None
        runner = InvestigationGraphRunner(self.session, investigation, offline_ai=offline_ai, auto_send_communications=not offline_ai)
        try:
            result = await runner.run()
        except Exception as run_error:  # noqa: BLE001 — surface the failure to the UI
            logger.exception("Investigation %s failed", investigation_id)
            await self.session.rollback()
            investigation = await self.session.get(Investigation, investigation_id)
            assert investigation is not None
            # The technical detail is in the log above; users only see a generic reason and the correlation id (V19).
            investigation.investigation_status, investigation.failure_reason = InvestigationStatus.FAILED, f"The investigation could not finish because of an internal problem. Reference {current_correlation_id() or 'none'}."
            investigation.stage_messages_json = [*(investigation.stage_messages_json or []), {"at": utc_now().isoformat(), "stage": "failed", "message": "The investigation failed. Re-run it, or contact a Keigan admin."}]
            await runner.recorder.record_failure(runner.recorder.stage, current_correlation_id() or None)  # the failed stage was rolled back; the steps of the stages before it were committed
            await AuditService(self.session).record(
                investigation.requested_by_user_principal_name or "system:worker", "investigation.failed", target_entity_type="investigation", target_entity_id=investigation_id,
                application_id=investigation.application_id, action_details={"failedAfterStage": runner.recorder.stage, "promptVersions": dict(runner.recorder.prompt_versions), "traceStepCount": runner.recorder.step_count},
            )
            return {"investigationId": investigation_id, "status": "failed"}
        if not offline_ai:
            await JobQueue(self.session).enqueue("notify_investigation_completed", {"investigation_id": investigation_id}, deduplication_key=f"notify_investigation_completed:{investigation_id}", priority_number=15)
        return result

    # ══ API ═══════════════════════════════════════════════════════════════════
    async def start_manual_investigation(self, current_user: CurrentUser, request: StartInvestigationRequest) -> JobAcceptedResponse:
        await AuthorizationService(self.session).ensure_application_reader(current_user, request.application_id)
        if await unknown_service_ids(self.session, request.application_id, request.service_ids):
            raise BusinessValidationException("One or more services do not belong to this application.", field_errors=[{"field": "serviceIds", "message": "Unknown service."}])
        if request.window_start and request.window_end and request.window_end <= request.window_start:
            raise BusinessValidationException("The window end must be after the window start.")
        maximum_window_minutes = get_settings().investigation_max_window_minutes
        if request.window_start and request.window_end and request.window_end - request.window_start > timedelta(minutes=maximum_window_minutes):
            raise BusinessValidationException(
                f"The time window can be at most {maximum_window_minutes} minutes ({maximum_window_minutes / 60:g} hours). Choose a shorter window.",
                field_errors=[{"field": "windowEnd", "message": f"At most {maximum_window_minutes} minutes after the window start."}],
            )
        investigation_id = await self.start_investigation(
            request.application_id, "manual", service_ids=request.service_ids, window_start=request.window_start, window_end=request.window_end,
            description=request.description, requested_by_user_principal_name=current_user.user_principal_name,
        )
        await AuditService(self.session).record(current_user, "investigation.start_manual", target_entity_type="investigation", target_entity_id=investigation_id, application_id=request.application_id)
        return JobAcceptedResponse(job_id=investigation_id, status="queued", message="The investigation was queued.")

    async def rerun(self, current_user: CurrentUser, investigation_id: str) -> JobAcceptedResponse:
        original = await self.load_readable_investigation(current_user, investigation_id, require_admin=True)
        if original.investigation_status in (InvestigationStatus.QUEUED, InvestigationStatus.RUNNING):
            raise BusinessValidationException("This investigation is still running.")
        new_investigation_id = await self.start_investigation(
            original.application_id, "rerun", incident_id=original.incident_id, alert_group_id=None, service_ids=original.investigated_service_ids,
            window_start=None if original.incident_id else original.investigation_window_start, window_end=None if original.incident_id else original.investigation_window_end,
            description=(original.triage_result_json or {}).get("manual_description"), requested_by_user_principal_name=current_user.user_principal_name,
        )
        await AuditService(self.session).record(current_user, "investigation.rerun", target_entity_type="investigation", target_entity_id=new_investigation_id, application_id=original.application_id, action_details={"previousInvestigationId": investigation_id})
        return JobAcceptedResponse(job_id=new_investigation_id, status="queued", message="A new run was queued; open the new investigation to follow it.")

    async def submit_feedback(self, current_user: CurrentUser, investigation_id: str, request: InvestigationFeedbackRequest) -> InvestigationSummaryDto:
        # "correct" feeds later investigations as a confirmed past issue, so only an application admin may say it (V7).
        investigation = await self.load_readable_investigation(current_user, investigation_id, require_admin=request.verdict == "correct")
        investigation.user_feedback_verdict, investigation.user_feedback_comment = request.verdict, PiiMasker().mask_text(request.comment)
        investigation.user_feedback_by_user_principal_name = current_user.user_principal_name
        await AuditService(self.session).record(current_user, "investigation.feedback", target_entity_type="investigation", target_entity_id=investigation_id, application_id=investigation.application_id, action_details={"verdict": request.verdict})
        await self.session.flush()
        await enqueue_memory_refresh(self.session, investigation_id)  # the verdict changes how far the past incident is trusted, and which investigation of its incident stands for it
        return (await self.summarize_investigations([investigation]))[0]

    async def load_readable_investigation(self, current_user: CurrentUser, investigation_id: str, require_admin: bool = False) -> Investigation:
        investigation = await self.session.get(Investigation, investigation_id)
        if investigation is None:
            raise NotFoundException("The investigation was not found.")
        authorization = AuthorizationService(self.session)
        if require_admin:
            await authorization.ensure_application_admin(current_user, investigation.application_id)
        else:
            await authorization.ensure_application_reader(current_user, investigation.application_id)
        return investigation

    async def get_progress(self, current_user: CurrentUser, investigation_id: str) -> InvestigationProgressDto:
        investigation = await self.load_readable_investigation(current_user, investigation_id)
        return InvestigationProgressDto(
            investigation_id=investigation_id, status=investigation.investigation_status, current_stage_name=investigation.current_stage_name, progress_percent=investigation.progress_percent,
            stage_messages=investigation.stage_messages_json or [], failure_reason=investigation.failure_reason,
        )

    async def list_investigations(
        self, current_user: CurrentUser, *, application_ids: list[str] | None, statuses: list[str] | None, incident_id: str | None, from_time: datetime | None, to_time: datetime | None, page: int, page_size: int
    ) -> PagedResult[InvestigationSummaryDto]:
        scoped_ids = await AuthorizationService(self.session).scoped_application_ids(current_user, application_ids)
        conditions: list[Any] = [Investigation.application_id.in_(scoped_ids or ["none"])]
        if statuses:
            conditions.append(Investigation.investigation_status.in_(statuses))
        if incident_id:
            conditions.append(Investigation.incident_id == incident_id)
        if from_time:
            conditions.append(Investigation.created_at >= from_time)
        if to_time:
            conditions.append(Investigation.created_at <= to_time)
        total_count = int(await self.session.scalar(select(func.count()).select_from(Investigation).where(*conditions)) or 0)
        investigations = list((await self.session.scalars(select(Investigation).where(*conditions).order_by(Investigation.created_at.desc()).offset((page - 1) * page_size).limit(page_size))).all())
        return PagedResult[InvestigationSummaryDto](items=await self.summarize_investigations(investigations), total_count=total_count, page=page, page_size=page_size)

    async def summarize_investigations(self, investigations: list[Investigation]) -> list[InvestigationSummaryDto]:
        if not investigations:
            return []
        applications = {application.application_id: application for application in (await self.session.scalars(select(Application).where(Application.application_id.in_({item.application_id for item in investigations})))).all()}
        incident_ids = {item.incident_id for item in investigations if item.incident_id}
        incidents = {incident.incident_id: incident for incident in (await self.session.scalars(select(Incident).where(Incident.incident_id.in_(incident_ids)))).all()} if incident_ids else {}
        service_ids = {service_id for item in investigations for service_id in item.investigated_service_ids}
        service_names = {service.service_id: service.service_name for service in (await self.session.scalars(select(MonitoredService).where(MonitoredService.service_id.in_(service_ids)))).all()} if service_ids else {}
        summaries: list[InvestigationSummaryDto] = []
        for investigation in investigations:
            application, incident = applications[investigation.application_id], incidents.get(investigation.incident_id or "")
            summaries.append(
                InvestigationSummaryDto(
                    investigation_id=investigation.investigation_id,
                    application=ApplicationReference(application_id=application.application_id, application_code=application.application_code, application_name=application.application_name),
                    incident_id=investigation.incident_id, incident_number=incident.external_incident_number if incident else None, incident_title=incident.incident_title if incident else None,
                    investigation_trigger=investigation.investigation_trigger, investigation_status=investigation.investigation_status, current_stage_name=investigation.current_stage_name,
                    progress_percent=investigation.progress_percent, keigan_priority=incident.keigan_priority if incident else (investigation.triage_result_json or {}).get("final_priority"),
                    overall_confidence_score=investigation.overall_confidence_score, investigation_outcome=outcome_code_of(investigation), executive_summary=investigation.executive_summary,
                    investigated_service_names=[service_names[service_id] for service_id in investigation.investigated_service_ids if service_id in service_names],
                    created_at=investigation.created_at, started_at=investigation.started_at, completed_at=investigation.completed_at, requested_by_user_principal_name=investigation.requested_by_user_principal_name,
                )
            )
        return summaries

    async def get_investigation_detail(self, current_user: CurrentUser, investigation_id: str) -> InvestigationDetailDto:
        from keigan.services.incident_service import IncidentService

        investigation = await self.load_readable_investigation(current_user, investigation_id)
        summary = (await self.summarize_investigations([investigation]))[0]
        service_ids = investigation.investigated_service_ids
        services = list((await self.session.scalars(select(MonitoredService).where(MonitoredService.service_id.in_(service_ids)))).all()) if service_ids else []
        names_by_id = {service.service_id: service.service_name for service in services}
        evidence_rows = sorted((await self.session.scalars(select(InvestigationEvidence).where(InvestigationEvidence.investigation_id == investigation_id))).all(), key=lambda row: _evidence_number(row.evidence_code))
        hypothesis_rows = list((await self.session.scalars(select(InvestigationHypothesis).where(InvestigationHypothesis.investigation_id == investigation_id).order_by(InvestigationHypothesis.display_order))).all())
        runbook_ids = {*investigation.matched_runbook_ids, *(row.matched_runbook_id for row in hypothesis_rows if row.matched_runbook_id)}
        runbooks = {runbook.runbook_id: runbook for runbook in (await self.session.scalars(select(Runbook).where(Runbook.runbook_id.in_(runbook_ids)))).all()} if runbook_ids else {}
        incident = await self.session.get(Incident, investigation.incident_id) if investigation.incident_id else None
        incident_summary = (await IncidentService(self.session).summarize_incidents([incident]))[0] if incident else None
        return InvestigationDetailDto(
            **summary.model_dump(), incident=incident_summary, investigation_window_start=investigation.investigation_window_start, investigation_window_end=investigation.investigation_window_end,
            baseline_window_start=investigation.baseline_window_start, baseline_window_end=investigation.baseline_window_end,
            services=[ServiceReference(service_id=service.service_id, service_name=service.service_name, service_type=service.service_type) for service in services],
            outcome=outcome_of(investigation), leading_perspective_reason_markdown=investigation.leading_perspective_reason_markdown,
            coverage_gaps=await self._coverage_gaps(investigation.investigation_id, evidence_rows),
            triage=investigation.triage_result_json, what_went_wrong_markdown=investigation.what_went_wrong_markdown, why_it_happened_markdown=investigation.why_it_happened_markdown,
            how_to_fix_markdown=investigation.how_to_fix_markdown, fix_plan=self._fix_plan(investigation, hypothesis_rows), open_questions=investigation.open_questions_json or [],
            leading_hypothesis_id=investigation.leading_hypothesis_id,
            hypotheses=[
                HypothesisDto(
                    hypothesis_id=row.hypothesis_id, analysis_perspective=row.analysis_perspective, hypothesis_title=row.hypothesis_title, hypothesis_statement_markdown=row.hypothesis_statement_markdown,
                    reasoning_markdown=row.reasoning_markdown, confidence_score=row.confidence_score, state=row.hypothesis_state, proposed_state=row.proposed_hypothesis_state,
                    state_guard_code=row.state_guard_code, state_reason_markdown=row.state_reason_markdown, supporting_evidence_codes=row.supporting_evidence_codes_json or [],
                    contradicting_evidence_codes=row.contradicting_evidence_codes_json or [], proposed_fix=row.proposed_fix_json, fix_risk_level=row.fix_risk_level,
                    matched_runbook=RunbookReference(runbook_id=row.matched_runbook_id, runbook_title=runbooks[row.matched_runbook_id].runbook_title) if row.matched_runbook_id in runbooks else None,
                    is_leading_hypothesis=row.is_leading_hypothesis, display_order=row.display_order,
                )
                for row in hypothesis_rows
            ],
            evidence=[self._evidence_dto(row, names_by_id) for row in evidence_rows], blast_radius=investigation.blast_radius_json,
            matched_runbooks=[RunbookReference(runbook_id=runbook_id, runbook_title=runbooks[runbook_id].runbook_title) for runbook_id in investigation.matched_runbook_ids if runbook_id in runbooks],
            knowledge_references=investigation.knowledge_references_json or [], alert_group=await self._alert_group_payload(investigation.investigation_id), stage_messages=investigation.stage_messages_json or [],
            is_evidence_only=investigation.investigation_status == InvestigationStatus.COMPLETED_EVIDENCE_ONLY, failure_reason=investigation.failure_reason, user_feedback_verdict=investigation.user_feedback_verdict,
            user_feedback_comment=investigation.user_feedback_comment, total_input_token_count=investigation.total_input_token_count, total_output_token_count=investigation.total_output_token_count,
            model_names=investigation.model_names_json or [], detected_at=incident.detected_by_keigan_at if incident else investigation.created_at, first_update_sent_at=incident.first_update_sent_at if incident else None,
        )

    @staticmethod
    def _fix_plan(investigation: Investigation, hypothesis_rows: list[InvestigationHypothesis]) -> FixPlanDto | None:
        """The recommended steps resolved from the analysts' stored steps. None for an investigation written before the plan existed."""
        plan = investigation.fix_plan_json
        if not plan:
            return None
        hypotheses = [{"analysis_perspective": row.analysis_perspective, "proposed_fix": row.proposed_fix_json or {}} for row in hypothesis_rows]
        return FixPlanDto(overview_markdown=plan.get("overview_markdown", ""), steps=[FixStepV2Dto.model_validate(step) for step in resolve_plan_steps(plan, hypotheses)])

    async def _coverage_gaps(self, investigation_id: str, evidence_rows: list[InvestigationEvidence]) -> list[CoverageGapDto]:
        """The gaps Keigan stored, then the unread sources an older investigation stored as evidence items (they say \"not available\" in their text, and are listed here instead of being shown as findings)."""
        stored_gaps = (await self.session.scalars(select(InvestigationCoverageGap).where(InvestigationCoverageGap.investigation_id == investigation_id).order_by(InvestigationCoverageGap.display_order))).all()
        gaps = [
            CoverageGapDto(
                coverage_gap_id=gap.coverage_gap_id, gap_kind=gap.gap_kind, reason_code=gap.gap_reason_code, service_id=gap.service_id, service_name=gap.service_name,
                source_kind=gap.source_kind, parameters=gap.parameters_json or {},
            )
            for gap in stored_gaps
        ]
        gaps.extend(
            CoverageGapDto(
                coverage_gap_id=row.evidence_id, gap_kind=CoverageGapKind.SOURCE_NOT_READABLE, reason_code=CoverageGapReason.UNKNOWN, service_id=row.service_id, source_kind=row.evidence_source_kind,
                legacy_evidence_code=row.evidence_code,
            )
            for row in evidence_rows if row.check_outcome == EvidenceCheckOutcome.NOT_CHECKED
        )
        return gaps

    @staticmethod
    def _evidence_dto(row: InvestigationEvidence, names_by_id: dict[str, str]) -> EvidenceDto:
        return EvidenceDto(
            evidence_id=row.evidence_id, evidence_code=row.evidence_code, service_id=row.service_id, service_name=names_by_id.get(row.service_id or "") or ("Azure Activity Log" if row.evidence_category == "change_event" else None),
            evidence_source_kind=row.evidence_source_kind, evidence_category=row.evidence_category, evidence_title=row.evidence_title, evidence_summary=row.evidence_summary,
            query_language=row.query_language, query_text=row.query_text, query_time_range_start=row.query_time_range_start, query_time_range_end=row.query_time_range_end,
            matched_record_count=row.matched_record_count, baseline_record_count=row.baseline_record_count, condensed_patterns=row.condensed_patterns_json or [], metric_series=row.metric_series_json or [],
            signal_strength=row.signal_strength, check_outcome=row.check_outcome, baseline_comparison=row.baseline_comparison, masked_value_count=row.masked_value_count, possible_prompt_injection=row.possible_prompt_injection, deep_link_url=row.deep_link_url, collected_at=row.collected_at,
        )

    async def get_evidence_detail(self, current_user: CurrentUser, investigation_id: str, evidence_code: str) -> EvidenceDto:
        await self.load_readable_investigation(current_user, investigation_id)
        row = await self.session.scalar(select(InvestigationEvidence).where(InvestigationEvidence.investigation_id == investigation_id, InvestigationEvidence.evidence_code == evidence_code.upper()))
        if row is None:
            raise NotFoundException("That evidence item does not exist.")
        service = await self.session.get(MonitoredService, row.service_id) if row.service_id else None
        return self._evidence_dto(row, {service.service_id: service.service_name} if service else {})

    async def _alert_group_payload(self, investigation_id: str) -> dict[str, Any] | None:
        """The alert group this investigation covers (the oldest one when several joined it)."""
        alert_group = await self.session.scalar(select(AlertGroup).where(AlertGroup.investigation_id == investigation_id).order_by(AlertGroup.started_at).limit(1))
        if alert_group is None:
            return None
        alerts = list((await self.session.scalars(select(Alert).where(Alert.alert_group_id == alert_group.alert_group_id).order_by(Alert.first_seen_at).limit(50))).all())
        decisions = list((await self.session.scalars(select(AlertDecision).where(AlertDecision.alert_id.in_([alert.alert_id for alert in alerts] or ["none"])).order_by(AlertDecision.decided_at).limit(200))).all())
        service_names = {service.service_id: service.service_name for service in (await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id == alert_group.application_id))).all()}
        grouping_reason = (await AlertService(self.session).grouping_reasons([alert_group], service_names))[alert_group.alert_group_id]  # the same derivation the Alerts page uses
        return {
            "alertGroupId": alert_group.alert_group_id, "groupTitle": alert_group.group_title, "groupSummary": alert_group.group_summary, "groupStatus": alert_group.group_status,
            "priorityScore": alert_group.priority_score, "groupingReason": grouping_reason.model_dump(by_alias=True), "memberAlertCount": alert_group.member_alert_count, "startedAt": alert_group.started_at.isoformat(),
            "alerts": [{"alertId": alert.alert_id, "ruleName": alert.rule_name, "severityLevel": alert.severity_level, "alertStatus": alert.alert_status, "firstSeenAt": alert.first_seen_at.isoformat(), "alertSummary": alert.alert_summary, "finalDisposition": alert.final_disposition} for alert in alerts],
            "decisions": [{"alertId": decision.alert_id, "pipelineStage": decision.pipeline_stage, "decisionOutcome": decision.decision_outcome, "decisionReason": decision.decision_reason, "decidedAt": decision.decided_at.isoformat()} for decision in decisions],
        }

    async def get_timeline(self, current_user: CurrentUser, investigation_id: str) -> list[TimelineEventDto]:
        investigation = await self.load_readable_investigation(current_user, investigation_id)
        conditions = [InvestigationTimelineEvent.investigation_id == investigation_id]
        if investigation.incident_id:
            conditions.append(InvestigationTimelineEvent.incident_id == investigation.incident_id)
        from sqlalchemy import or_

        events = (await self.session.scalars(select(InvestigationTimelineEvent).where(or_(*conditions)).order_by(InvestigationTimelineEvent.event_occurred_at, InvestigationTimelineEvent.created_at))).all()
        unique_events: dict[str, InvestigationTimelineEvent] = {event.timeline_event_id: event for event in events}
        return [
            TimelineEventDto(
                timeline_event_id=event.timeline_event_id, event_occurred_at=event.event_occurred_at, event_type=event.event_type, event_title=event.event_title, event_details_markdown=event.event_details_markdown,
                event_source=event.event_source, source_reference=event.source_reference, actor_display_name=event.actor_display_name,
            )
            for event in unique_events.values()
        ]
