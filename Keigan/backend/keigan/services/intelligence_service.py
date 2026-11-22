"""Predictive intelligence: signals, status changes, the health score and the Keigan Intelligence Report (weekly digest and proactive alert)."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.llm_gateway import LlmUsageContext, ModelTier, PromptSection
from keigan.ai.notification_ai_schemas import IntelligenceNarrativeResult, IntelligenceReportResult
from keigan.ai.output_sanitizer import sanitize_ai_line, sanitize_ai_markdown
from keigan.config import application_context
from keigan.dtos.intelligence_dtos import (
    HealthScorePoint, HealthScoreTrendResponse, IntelligenceReportResponse, IntelligenceReportSummary, PredictiveSignalResponse, PredictiveSignalStatusRequest, SignalInvestigationResponse,
)
from keigan.entities.alert_entities import Alert
from keigan.entities.application_entities import Application, MonitoredService
from keigan.entities.incident_entities import Incident
from keigan.entities.slo_entities import IntelligenceReport, PredictiveSignal, ServiceLevelIndicator, ServiceLevelObjective, SliMeasurement
from keigan.entities.status_values import IntelligenceReportType, Priority, SignalSeverity, SignalStatus, SloHealthStatus
from keigan.exceptions.keigan_exceptions import NotFoundException
from keigan.security.current_user import CurrentUser
from keigan.services.audit_service import AuditService
from keigan.services.authorization_service import AuthorizationService
from keigan.services.intelligence_detectors import DetectedSignal, PredictiveDetectors
from keigan.services.notification_renderer import translate
from keigan.utils.time_utils import utc_now

logger = logging.getLogger(__name__)
SEVERITY_ORDER = {SignalSeverity.CRITICAL: 0, SignalSeverity.WARNING: 1, SignalSeverity.INFO: 2}
SLO_STATUS_POINTS = {SloHealthStatus.HEALTHY: 1.0, SloHealthStatus.AT_RISK: 0.6, SloHealthStatus.BREACHED: 0.2}
PROACTIVE_CONFIDENCE_THRESHOLD = 0.8
OPEN_SIGNAL_STATUSES = (SignalStatus.OPEN, SignalStatus.ACKNOWLEDGED)


def compute_health_score(slo_ratio: float | None, critical_signals: int, warning_signals: int, incident_penalty: float) -> tuple[int, float, float, float]:
    """Health score 0-100: SLO attainment (50) + predictive signals (25) + incidents (25). Returns (score, slo, signals, incidents) components."""
    slo_component = 50.0 * (slo_ratio if slo_ratio is not None else 0.8)
    signal_component = max(0.0, 25.0 - 10.0 * critical_signals - 5.0 * warning_signals)
    incident_component = max(0.0, 25.0 - incident_penalty)
    return round(slo_component + signal_component + incident_component), round(slo_component, 1), round(signal_component, 1), round(incident_component, 1)


def incident_penalty_for(priorities: list[str | None]) -> float:
    return sum({Priority.P1: 8.0, Priority.P2: 4.0}.get(priority or "", 1.5) for priority in priorities)


class IntelligenceService:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Job: run_predictive_analysis ───────────────────────────────────────────
    async def run_detectors_for_application(self, application_id: str) -> dict[str, Any] | None:
        application = await self.session.get(Application, application_id)
        if application is None:
            return None
        detected, completed_detectors = await PredictiveDetectors(self.session).run_all(application_id)
        open_signals = (await self.session.scalars(select(PredictiveSignal).where(PredictiveSignal.application_id == application_id, PredictiveSignal.signal_status.in_(OPEN_SIGNAL_STATUSES)))).all()
        existing_by_identity = {(signal.detector_name, signal.service_id, signal.sli_id, signal.metric_name or ""): signal for signal in open_signals}
        refreshed_identities: set[tuple[Any, ...]] = set()
        created_signals: list[PredictiveSignal] = []
        for detection in detected:
            existing = existing_by_identity.get(detection.identity)
            refreshed_identities.add(detection.identity)
            if existing is not None:
                self._copy_numbers(existing, detection)
                continue
            signal = PredictiveSignal(application_id=application_id, service_id=detection.service_id, sli_id=detection.sli_id, detector_name=detection.detector_name)
            self._copy_numbers(signal, detection)
            signal.explanation_markdown = await self._narrate(application, detection)
            self.session.add(signal)
            created_signals.append(signal)
        expired_count = 0
        for identity, signal in existing_by_identity.items():
            if identity not in refreshed_identities and signal.detector_name in completed_detectors and signal.signal_status == SignalStatus.OPEN and signal.detected_at < utc_now() - timedelta(hours=1):
                signal.signal_status = SignalStatus.EXPIRED
                expired_count += 1
        await self.session.flush()
        proactive_signal_ids = [signal.predictive_signal_id for signal in created_signals if signal.signal_severity == SignalSeverity.CRITICAL and signal.confidence_score >= PROACTIVE_CONFIDENCE_THRESHOLD]
        if proactive_signal_ids:
            from keigan.workers.job_queue import JobQueue

            await JobQueue(self.session).enqueue("send_intelligence_report", {"application_id": application_id, "report_type": IntelligenceReportType.PROACTIVE_ALERT, "signal_ids": proactive_signal_ids}, deduplication_key=f"proactive:{application_id}:{utc_now():%Y%m%d%H}")
        return {"detected": len(detected), "created": len(created_signals), "expired": expired_count}

    @staticmethod
    def _copy_numbers(signal: PredictiveSignal, detection: DetectedSignal) -> None:
        signal.signal_severity, signal.signal_title, signal.metric_name = detection.signal_severity, detection.signal_title[:400], detection.metric_name
        signal.observed_value, signal.expected_value, signal.deviation_score = detection.observed_value, detection.expected_value, detection.deviation_score
        signal.forecast_breach_at, signal.confidence_score, signal.evidence_series_json = detection.forecast_breach_at, detection.confidence_score, detection.evidence_series

    async def _narrate(self, application: Application, detection: DetectedSignal) -> str:
        try:
            prompt = application_context.prompt_library().render("intelligence_narrative", application_name=application.application_name)
            result = await application_context.llm_gateway().generate_structured(
                feature_name="intelligence_narrative", model_tier=ModelTier.FAST, system_prompt=prompt,
                prompt_sections=[PromptSection("Signal facts", detection.facts_text), PromptSection("Task", "Explain this signal for the on-call team.")],
                output_schema=IntelligenceNarrativeResult, usage_context=LlmUsageContext(application_id=application.application_id),
            )
            return sanitize_ai_markdown(result.narrative_markdown)
        except Exception:  # noqa: BLE001 - the numbers alone are a valid explanation
            logger.warning("Signal narrative for application %s failed; the facts are shown instead", application.application_id, exc_info=True)
            return detection.facts_text

    # ── Signals API ────────────────────────────────────────────────────────────
    async def list_signals(self, current_user: CurrentUser, application_ids: list[str] | None, detector_names: list[str] | None, severities: list[str] | None, statuses: list[str] | None, limit: int) -> list[PredictiveSignalResponse]:
        scoped_ids = await AuthorizationService(self.session).scoped_application_ids(current_user, application_ids)
        if not scoped_ids:
            return []
        conditions = [PredictiveSignal.application_id.in_(scoped_ids)]
        if detector_names:
            conditions.append(PredictiveSignal.detector_name.in_(detector_names))
        if severities:
            conditions.append(PredictiveSignal.signal_severity.in_(severities))
        conditions.append(PredictiveSignal.signal_status.in_(statuses) if statuses else PredictiveSignal.signal_status.in_(OPEN_SIGNAL_STATUSES))
        rows = (await self.session.scalars(select(PredictiveSignal).where(*conditions).order_by(PredictiveSignal.detected_at.desc()).limit(limit))).all()
        rows = sorted(rows, key=lambda signal: (SEVERITY_ORDER.get(signal.signal_severity, 3), -signal.detected_at.timestamp()))
        return await self._to_responses(rows)

    async def _to_responses(self, rows: list[PredictiveSignal]) -> list[PredictiveSignalResponse]:
        application_names = {application.application_id: application.application_name for application in (await self.session.scalars(select(Application))).all()}
        service_names = {service.service_id: service.service_name for service in (await self.session.scalars(select(MonitoredService))).all()}
        return [
            PredictiveSignalResponse(
                predictive_signal_id=row.predictive_signal_id, application_id=row.application_id, application_name=application_names.get(row.application_id), service_id=row.service_id, service_name=service_names.get(row.service_id or ""),
                sli_id=row.sli_id, detector_name=row.detector_name, signal_severity=row.signal_severity, signal_title=row.signal_title, explanation_markdown=row.explanation_markdown, metric_name=row.metric_name,
                observed_value=row.observed_value, expected_value=row.expected_value, deviation_score=row.deviation_score, forecast_breach_at=row.forecast_breach_at, confidence_score=row.confidence_score,
                evidence_series=row.evidence_series_json or [], signal_status=row.signal_status, detected_at=row.detected_at, status_changed_by_user_principal_name=row.status_changed_by_user_principal_name, intelligence_report_id=row.intelligence_report_id,
            ) for row in rows
        ]

    async def _editable_signal(self, current_user: CurrentUser, signal_id: str) -> PredictiveSignal:
        signal = await self.session.get(PredictiveSignal, signal_id)
        if signal is None:
            raise NotFoundException("Predictive signal not found.")
        await AuthorizationService(self.session).ensure_application_admin(current_user, signal.application_id)
        return signal

    async def update_signal_status(self, current_user: CurrentUser, signal_id: str, request: PredictiveSignalStatusRequest) -> PredictiveSignalResponse:
        signal = await self._editable_signal(current_user, signal_id)
        signal.signal_status, signal.status_changed_by_user_principal_name = request.signal_status, current_user.user_principal_name
        await AuditService(self.session).record(current_user, "predictive_signal.status_change", target_entity_type="predictive_signal", target_entity_id=signal_id, application_id=signal.application_id, action_details={"status": request.signal_status})
        await self.session.flush()
        return (await self._to_responses([signal]))[0]

    async def investigate_signal(self, current_user: CurrentUser, signal_id: str) -> SignalInvestigationResponse:
        signal = await self._editable_signal(current_user, signal_id)
        from keigan.services.investigation_service import InvestigationService

        description = f"Predictive signal ({signal.detector_name}): {signal.signal_title}\n\n{signal.explanation_markdown or ''}"
        investigation_id = await InvestigationService(self.session).start_investigation(
            signal.application_id, "manual", service_ids=[signal.service_id] if signal.service_id else None, description=description, requested_by_user_principal_name=current_user.user_principal_name,
        )
        signal.signal_status, signal.status_changed_by_user_principal_name = SignalStatus.CONVERTED_TO_INCIDENT, current_user.user_principal_name
        await AuditService(self.session).record(current_user, "predictive_signal.investigate", target_entity_type="predictive_signal", target_entity_id=signal_id, application_id=signal.application_id, action_details={"investigationId": investigation_id})
        await self.session.flush()
        return SignalInvestigationResponse(investigation_id=investigation_id, predictive_signal_id=signal_id)

    # ── Health score ───────────────────────────────────────────────────────────
    async def _slo_ratio(self, application_id: str) -> float | None:
        from keigan.services.slo_service import SloService

        summaries = await SloService(self.session).summarize_slos([application_id])
        points = [SLO_STATUS_POINTS[summary["status"]] for summary in summaries if summary["status"] in SLO_STATUS_POINTS]
        return sum(points) / len(points) if points else None

    async def current_health_score(self, application_id: str) -> tuple[int, dict[str, float]]:
        now = utc_now()
        signals = (await self.session.scalars(select(PredictiveSignal).where(PredictiveSignal.application_id == application_id, PredictiveSignal.signal_status.in_(OPEN_SIGNAL_STATUSES)))).all()
        priorities = (await self.session.scalars(select(Incident.keigan_priority).where(Incident.application_id == application_id, Incident.opened_at >= now - timedelta(days=7)))).all()
        score, slo_component, signal_component, incident_component = compute_health_score(
            await self._slo_ratio(application_id), sum(1 for signal in signals if signal.signal_severity == SignalSeverity.CRITICAL), sum(1 for signal in signals if signal.signal_severity == SignalSeverity.WARNING), incident_penalty_for(list(priorities)),
        )
        return score, {"slo": slo_component, "signals": signal_component, "incidents": incident_component}

    async def get_health_score_trend(self, current_user: CurrentUser, application_id: str, days: int) -> HealthScoreTrendResponse:
        await AuthorizationService(self.session).ensure_application_reader(current_user, application_id)
        now = utc_now()
        range_start = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        targets = {row[0]: (row[1], row[2]) for row in (await self.session.execute(
            select(ServiceLevelIndicator.sli_id, ServiceLevelObjective.target_percentage, ServiceLevelObjective.rolling_window_days).join(ServiceLevelObjective, ServiceLevelObjective.sli_id == ServiceLevelIndicator.sli_id).where(
                ServiceLevelObjective.application_id == application_id, ServiceLevelIndicator.is_enabled.is_(True)))).all()}
        daily: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
        if targets:
            for sli_id, window_start, good, total in (await self.session.execute(select(SliMeasurement.sli_id, SliMeasurement.measurement_window_start, SliMeasurement.good_event_count, SliMeasurement.total_event_count).where(
                    SliMeasurement.sli_id.in_(list(targets)), SliMeasurement.measurement_window_start >= range_start))).all():
                bucket = daily[(sli_id, window_start.strftime("%Y-%m-%d"))]
                bucket[0] += float(good or 0)
                bucket[1] += float(total or 0)
        signals = (await self.session.scalars(select(PredictiveSignal).where(PredictiveSignal.application_id == application_id, PredictiveSignal.detected_at >= range_start - timedelta(days=3)))).all()
        incidents = (await self.session.execute(select(Incident.opened_at, Incident.keigan_priority).where(Incident.application_id == application_id, Incident.opened_at >= range_start - timedelta(days=7)))).all()
        points: list[HealthScorePoint] = []
        for day_offset in range(days + 1):
            day_start = range_start + timedelta(days=day_offset)
            day_key = day_start.strftime("%Y-%m-%d")
            ratios = []
            for sli_id, (target, _) in targets.items():
                good, total = daily.get((sli_id, day_key), (0.0, 0.0))
                if total:
                    ratios.append(1.0 if good / total * 100 >= target else (0.6 if good / total * 100 >= target - 0.3 else 0.2))
            active_signals = [signal for signal in signals if day_start - timedelta(days=3) <= signal.detected_at < day_start + timedelta(days=1)]
            recent_priorities = [priority for opened_at, priority in incidents if day_start - timedelta(days=6) <= opened_at < day_start + timedelta(days=1)]
            score, slo_component, signal_component, incident_component = compute_health_score(
                sum(ratios) / len(ratios) if ratios else None, sum(1 for signal in active_signals if signal.signal_severity == SignalSeverity.CRITICAL), sum(1 for signal in active_signals if signal.signal_severity == SignalSeverity.WARNING), incident_penalty_for(recent_priorities),
            )
            points.append(HealthScorePoint(day=day_key, health_score=score, slo_component=slo_component, signal_component=signal_component, incident_component=incident_component))
        current_score, _ = await self.current_health_score(application_id)
        if points:
            points[-1] = points[-1].model_copy(update={"health_score": current_score})
        return HealthScoreTrendResponse(application_id=application_id, current_health_score=current_score, points=points)

    # ── Reports ────────────────────────────────────────────────────────────────
    async def generate_and_send_report(self, application_id: str, report_type: str = "proactive_alert", signal_ids: list[str] | None = None, send_to_stakeholders: bool = True) -> dict[str, Any] | None:
        application = await self.session.get(Application, application_id)
        if application is None:
            return None
        report = await self._build_report(application, report_type, signal_ids)
        recipients = await self._send_report(application, report) if send_to_stakeholders else []
        return {"intelligenceReportId": report.intelligence_report_id, "recipients": len(recipients)}

    async def _build_report(self, application: Application, report_type: str, signal_ids: list[str] | None, period_end: datetime | None = None) -> IntelligenceReport:
        from keigan.services.slo_service import SloService

        period_end = period_end or utc_now()
        period_start = period_end - timedelta(days=7 if report_type == IntelligenceReportType.WEEKLY_DIGEST else 1)
        signal_conditions = [PredictiveSignal.application_id == application.application_id]
        signal_conditions.append(PredictiveSignal.predictive_signal_id.in_(signal_ids) if signal_ids else PredictiveSignal.signal_status.in_(OPEN_SIGNAL_STATUSES))
        signals = sorted((await self.session.scalars(select(PredictiveSignal).where(*signal_conditions))).all(), key=lambda signal: SEVERITY_ORDER.get(signal.signal_severity, 3))
        incidents = (await self.session.scalars(select(Incident).where(Incident.application_id == application.application_id, Incident.opened_at >= period_start, Incident.opened_at <= period_end))).all()
        health_score, components = await self.current_health_score(application.application_id)
        summaries = await SloService(self.session).summarize_slos([application.application_id])
        alert_count = await self.session.scalar(select(func.count()).select_from(Alert).where(Alert.application_id == application.application_id, Alert.first_seen_at >= period_start)) or 0
        group_count = await self.session.scalar(select(func.count(func.distinct(Alert.alert_group_id))).where(Alert.application_id == application.application_id, Alert.first_seen_at >= period_start)) or 0
        slo_rows = [{"sliName": item["sliName"], "serviceName": item.get("serviceName"), "target": item["targetPercentage"], "compliance": item.get("compliancePercentage"), "budgetRemainingPercent": item.get("errorBudgetRemainingPercentage"), "status": item["status"]} for item in summaries]
        incident_counts: dict[str, int] = defaultdict(int)
        for incident in incidents:
            incident_counts[incident.keigan_priority or Priority.P3] += 1
        facts = [
            f"Application: {application.application_name}; period {period_start:%Y-%m-%d} to {period_end:%Y-%m-%d}.", f"Health score {health_score}/100 (SLOs {components['slo']}/50, signals {components['signals']}/25, incidents {components['incidents']}/25).",
            "SLOs: " + ("; ".join(f"{row['sliName']} {row['compliance']}% vs {row['target']}% ({row['status']})" for row in slo_rows[:8]) or "none defined"),
            "Predictive signals: " + ("; ".join(f"[{signal.signal_severity}] {signal.signal_title}" for signal in signals[:8]) or "none"),
            f"Incidents: {len(incidents)} ({', '.join(f'{count} x {priority}' for priority, count in sorted(incident_counts.items())) or 'none'}).", f"Alert noise: {alert_count} alerts reduced to {group_count} groups.",
        ]
        summary_text, recommendations = await self._narrate_report(application, report_type, "\n".join(f"- {fact}" for fact in facts))
        report_type_label = "weekly digest" if report_type == IntelligenceReportType.WEEKLY_DIGEST else "proactive alert"
        title = f"Keigan Intelligence Report: {application.application_name} ({report_type_label}, {period_end:%Y-%m-%d})"
        sections = {
            "healthScore": health_score, "healthComponents": components, "executiveSummary": summary_text, "slos": slo_rows, "recommendations": recommendations, "incidents": {"total": len(incidents), "byPriority": dict(incident_counts)},
            "noise": {"alerts": alert_count, "groups": group_count}, "signals": [{"predictiveSignalId": signal.predictive_signal_id, "title": signal.signal_title, "severity": signal.signal_severity, "detector": signal.detector_name, "confidence": signal.confidence_score, "explanation": signal.explanation_markdown} for signal in signals],
        }
        report = IntelligenceReport(application_id=application.application_id, report_type=report_type, report_title=title[:400], report_period_start=period_start, report_period_end=period_end, overall_health_score=health_score, report_markdown=sanitize_ai_markdown(self._report_markdown(title, sections)), report_sections_json=sections)
        self.session.add(report)
        await self.session.flush()
        for signal in signals:
            if signal_ids or signal.intelligence_report_id is None:
                signal.intelligence_report_id = report.intelligence_report_id
        return report

    async def _narrate_report(self, application: Application, report_type: str, facts_text: str) -> tuple[str, list[str]]:
        try:
            prompt = application_context.prompt_library().render("intelligence_report", application_name=application.application_name, report_type_label="weekly digest" if report_type == IntelligenceReportType.WEEKLY_DIGEST else "proactive alert")
            result = await application_context.llm_gateway().generate_structured(
                feature_name="intelligence_report", model_tier=ModelTier.FAST, system_prompt=prompt, prompt_sections=[PromptSection("Report facts", facts_text), PromptSection("Task", "Write the summary and recommendations.")],
                output_schema=IntelligenceReportResult, usage_context=LlmUsageContext(application_id=application.application_id),
            )
            return sanitize_ai_markdown(result.executive_summary), [sanitize_ai_line(recommendation, maximum_characters=500) for recommendation in result.recommendations[:4]]
        except Exception:  # noqa: BLE001
            logger.warning("Report summary for application %s failed; the facts are shown instead", application.application_id, exc_info=True)
            return facts_text.replace("- ", "", 2), ["Review the open predictive signals with the owning teams."]

    @staticmethod
    def _report_markdown(title: str, sections: dict[str, Any]) -> str:
        lines = [f"# {title}", "", f"**Health score: {sections['healthScore']}/100**", "", "## Summary", sections["executiveSummary"], ""]
        if sections["signals"]:
            lines += ["## Predictive signals", *[f"- **[{signal['severity']}] {signal['title']}** (confidence {round(signal['confidence'] * 100)}%)" for signal in sections["signals"]], ""]
        if sections["slos"]:
            lines += ["## SLO status", *[f"- {row['sliName']} ({row['serviceName'] or 'application'}): {row['compliance']}% against {row['target']}%, error budget left {row['budgetRemainingPercent']}% - {row['status']}" for row in sections["slos"]], ""]
        lines += ["## Incidents and noise", f"- {sections['incidents']['total']} incident(s) in the period.", f"- {sections['noise']['alerts']} alerts were reduced to {sections['noise']['groups']} groups.", ""]
        if sections["recommendations"]:
            lines += ["## Recommendations", *[f"- {recommendation}" for recommendation in sections["recommendations"]], ""]
        return "\n".join(lines)

    async def _send_report(self, application: Application, report: IntelligenceReport) -> list[str]:
        from keigan.services.notification_service import NotificationService

        notification_service = NotificationService(self.session)
        recipients: list[str] = []
        for stakeholder in await notification_service.matching_stakeholders(application.application_id, "intelligence_report", "email"):
            recipient_address = notification_service.recipient_address_for(stakeholder, "email")
            if not recipient_address:
                continue
            language = stakeholder.preferred_language_code
            rendered = notification_service.renderer.render_email(
                "intelligence_report", language, application.application_name, report.report_title, facts=[(translate(language, "labels.health_score"), f"{report.overall_health_score}/100"), (translate(language, "labels.period"), f"{report.report_period_start:%Y-%m-%d} - {report.report_period_end:%Y-%m-%d}")],
                body_markdown=report.report_markdown, action_path="/intelligence", subject_override=report.report_title,
            )
            if await notification_service.queue_email(application.application_id, "intelligence_report", recipient_address, rendered):
                recipients.append(recipient_address)
        report.sent_at, report.recipient_addresses_json = utc_now(), recipients
        await self.session.flush()
        return recipients

    async def request_report(self, current_user: CurrentUser, application_id: str, report_type: str, send_to_stakeholders: bool) -> str:
        await AuthorizationService(self.session).ensure_application_admin(current_user, application_id)
        from keigan.workers.job_queue import JobQueue

        job_id = await JobQueue(self.session).enqueue(
            "send_intelligence_report", {"application_id": application_id, "report_type": report_type, "send_to_stakeholders": send_to_stakeholders}, deduplication_key=f"report:{application_id}:{report_type}:{send_to_stakeholders}",
        )
        await AuditService(self.session).record(current_user, "intelligence_report.generate", target_entity_type="application", target_entity_id=application_id, application_id=application_id, action_details={"reportType": report_type, "send": send_to_stakeholders})
        return job_id

    async def list_reports(self, current_user: CurrentUser, application_id: str | None) -> list[IntelligenceReportSummary]:
        scoped_ids = await AuthorizationService(self.session).scoped_application_ids(current_user, [application_id] if application_id else None)
        if not scoped_ids:
            return []
        rows = (await self.session.scalars(select(IntelligenceReport).where(IntelligenceReport.application_id.in_(scoped_ids)).order_by(IntelligenceReport.created_at.desc()).limit(100))).all()
        names = {application.application_id: application.application_name for application in (await self.session.scalars(select(Application))).all()}
        return [self._summary(row, names.get(row.application_id)) for row in rows]

    async def get_report(self, current_user: CurrentUser, report_id: str) -> IntelligenceReportResponse:
        report = await self.session.get(IntelligenceReport, report_id)
        if report is None:
            raise NotFoundException("Intelligence report not found.")
        await AuthorizationService(self.session).ensure_application_reader(current_user, report.application_id)
        application = await self.session.get(Application, report.application_id)
        summary = self._summary(report, application.application_name if application else None)
        return IntelligenceReportResponse(**summary.model_dump(), report_markdown=report.report_markdown, report_sections=report.report_sections_json or {}, recipient_addresses=report.recipient_addresses_json or [])

    @staticmethod
    def _summary(report: IntelligenceReport, application_name: str | None) -> IntelligenceReportSummary:
        return IntelligenceReportSummary(
            intelligence_report_id=report.intelligence_report_id, application_id=report.application_id, application_name=application_name, report_type=report.report_type, report_title=report.report_title,
            report_period_start=report.report_period_start, report_period_end=report.report_period_end, overall_health_score=report.overall_health_score, sent_at=report.sent_at, recipient_count=len(report.recipient_addresses_json or []), created_at=report.created_at,
        )
