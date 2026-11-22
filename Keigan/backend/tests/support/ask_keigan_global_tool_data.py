"""Rows the global Ask Keigan tools read (incidents, investigations, alert groups, predictive signals, team members), built for the tests of those tools."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.entities.alert_entities import Alert, AlertDecision, AlertGroup
from keigan.entities.incident_entities import Incident, Investigation, InvestigationEvidence, InvestigationHypothesis
from keigan.entities.notification_entities import Stakeholder
from keigan.entities.slo_entities import PredictiveSignal, ServiceLevelIndicator, ServiceLevelObjective
from keigan.utils.time_utils import utc_now

TEST_AUTHOR = "system:test"


async def create_incident(
    application_id: str, *, title: str, number: str | None = None, status: str = "investigating", priority: str = "P2", source: str = "servicenow",
    opened_at: datetime | None = None, description: str | None = None,
) -> str:
    async with open_session() as session:
        incident = Incident(
            application_id=application_id, incident_title=title, external_incident_number=number or f"INC{uuid.uuid4().hex[:7]}", incident_status=status,
            keigan_priority=priority, incident_source=source, opened_at=opened_at or utc_now(), incident_description=description, created_by_user_principal_name=TEST_AUTHOR,
        )
        session.add(incident)
        await session.flush()
        return incident.incident_id


async def create_investigation(
    application_id: str, *, status: str = "completed", incident_id: str | None = None, executive_summary: str | None = None, created_at: datetime | None = None,
) -> str:
    async with open_session() as session:
        investigation = Investigation(
            application_id=application_id, incident_id=incident_id, investigation_status=status, executive_summary=executive_summary,
            overall_confidence_score=0.8 if status == "completed" else None, created_at=created_at or utc_now(), requested_by_user_principal_name="requester@keigan.local",
            created_by_user_principal_name=TEST_AUTHOR,
        )
        session.add(investigation)
        await session.flush()
        return investigation.investigation_id


async def add_hypothesis(investigation_id: str, *, title: str, confidence: float, leading: bool, supporting_codes: list[str], contradicting_codes: list[str] | None = None) -> None:
    async with open_session() as session:
        session.add(InvestigationHypothesis(
            investigation_id=investigation_id, analysis_perspective="application", hypothesis_title=title, hypothesis_statement_markdown=f"{title} explains the failure.",
            confidence_score=confidence, supporting_evidence_codes_json=supporting_codes, contradicting_evidence_codes_json=contradicting_codes or [], is_leading_hypothesis=leading,
            display_order=0 if leading else 1,
        ))


async def create_alert_group(
    application_id: str, *, title: str, status: str = "open", priority_score: float = 60.0, last_activity_at: datetime | None = None,
    investigation_id: str | None = None, incident_id: str | None = None, rule_name: str = "High error rate", decision_outcome: str = "investigation_started",
) -> str:
    activity = last_activity_at or utc_now()
    async with open_session() as session:
        group = AlertGroup(
            application_id=application_id, group_title=title, group_status=status, priority_score=priority_score, member_alert_count=1, highest_severity_level=2,
            started_at=activity - timedelta(minutes=5), last_activity_at=activity, investigation_id=investigation_id, incident_id=incident_id,
            grouping_reason="same_rule",
        )
        session.add(group)
        await session.flush()
        alert = Alert(
            application_id=application_id, alert_group_id=group.alert_group_id, alert_fingerprint=uuid.uuid4().hex, rule_name=rule_name, rule_identifier=rule_name.lower(),
            severity_level=2, alert_status=status if status == "resolved" else "firing", alert_summary=f"{rule_name} on the checkout service", first_seen_at=activity - timedelta(minutes=5),
            last_seen_at=activity, occurrence_count=3,
        )
        session.add(alert)
        await session.flush()
        session.add(AlertDecision(alert_id=alert.alert_id, alert_group_id=group.alert_group_id, pipeline_stage="decide", decision_outcome=decision_outcome, decision_reason="Enough alerts to investigate."))
        return group.alert_group_id


async def create_predictive_signal(application_id: str, *, title: str, severity: str = "warning", status: str = "open", detected_at: datetime | None = None) -> str:
    async with open_session() as session:
        signal = PredictiveSignal(
            application_id=application_id, detector_name="latency_trend", signal_severity=severity, signal_title=title, explanation_markdown="Latency climbs every hour.",
            confidence_score=0.7, signal_status=status, detected_at=detected_at or utc_now(),
        )
        session.add(signal)
        await session.flush()
        return signal.predictive_signal_id


async def add_team_member(application_id: str, *, display_name: str, email: str, role: str = "sre", is_active: bool = True) -> str:
    async with open_session() as session:
        member = Stakeholder(
            application_id=application_id, display_name=display_name, email_address=email, user_principal_name=email, entra_object_id=str(uuid.uuid4()), stakeholder_role=role,
            is_active=is_active, created_by_user_principal_name=TEST_AUTHOR,
        )
        session.add(member)
        await session.flush()
        return member.stakeholder_id


async def add_evidence(investigation_id: str, *, code: str, title: str, signal_strength: str = "high", matched_record_count: int = 12) -> None:
    async with open_session() as session:
        session.add(InvestigationEvidence(
            investigation_id=investigation_id, evidence_code=code, evidence_source_kind="log_analytics", evidence_category="error_pattern", evidence_title=title,
            evidence_summary=f"{title} was seen.", query_language="kql", query_text="requests | where success == false", matched_record_count=matched_record_count,
            signal_strength=signal_strength,
        ))


async def slo_id_of(application_id: str, sli_name: str) -> str:
    async with open_session() as session:
        return await session.scalar(
            select(ServiceLevelObjective.slo_id)
            .join(ServiceLevelIndicator, ServiceLevelIndicator.sli_id == ServiceLevelObjective.sli_id)
            .where(ServiceLevelObjective.application_id == application_id, ServiceLevelIndicator.sli_name == sli_name)
        )
