"""In-memory re-run of the noise policy over recent alerts (sample plan 7A.5 'Apply these settings to the last 7 days').

Nothing is written: stored alerts are replayed through the same pure rules the live pipeline uses, so the funnel shows what a policy would do.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.dtos.alert_dtos import FunnelResponse, FunnelStep
from keigan.entities.alert_entities import Alert, AlertMuteRule, MaintenanceWindow
from keigan.entities.application_entities import Application, MonitoredService, ServiceDependency
from keigan.services import alert_rules


class NoisePreviewService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def preview(self, application_id: str, policy_settings: dict[str, Any], days: int) -> FunnelResponse:
        policy = alert_rules.merge_policy(policy_settings)
        period_end = alert_rules.utc_now()
        period_start = period_end - timedelta(days=days)
        application = await self.session.get(Application, application_id)
        alerts = list((await self.session.scalars(select(Alert).where(Alert.application_id == application_id, Alert.first_seen_at >= period_start).order_by(Alert.first_seen_at))).all())
        if not alerts:
            return self._illustration(period_start, period_end)
        services = {service.service_id: service for service in (await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id == application_id))).all()}
        neighbours: dict[str, set[str]] = {}
        for dependency in (await self.session.scalars(select(ServiceDependency).where(ServiceDependency.application_id == application_id))).all():
            neighbours.setdefault(dependency.upstream_service_id, set()).add(dependency.downstream_service_id)
            neighbours.setdefault(dependency.downstream_service_id, set()).add(dependency.upstream_service_id)
        windows = list((await self.session.scalars(select(MaintenanceWindow).where(MaintenanceWindow.application_id == application_id))).all())
        mute_rules = list((await self.session.scalars(select(AlertMuteRule).where(AlertMuteRule.application_id == application_id))).all())

        received_count = sum(alert.occurrence_count for alert in alerts)
        reopen_window = timedelta(minutes=policy["reopen_window_minutes"])
        distinct_alerts: list[Alert] = []
        latest_by_fingerprint: dict[str, datetime] = {}
        for alert in alerts:
            previous_end = latest_by_fingerprint.get(alert.alert_fingerprint)
            alert_end = alert.resolved_at or alert.last_seen_at
            if previous_end is not None and alert.first_seen_at - previous_end <= reopen_window:
                latest_by_fingerprint[alert.alert_fingerprint] = max(previous_end, alert_end)
                continue
            latest_by_fingerprint[alert.alert_fingerprint] = alert_end
            distinct_alerts.append(alert)

        reasons = {"repeats": received_count - len(distinct_alerts), "maintenance": 0, "muted": 0, "environment": 0, "severity": 0, "resolved_before_settle": 0}
        survivors: list[Alert] = []
        for alert in distinct_alerts:
            blocked_reason = self._suppression_reason(alert, policy, windows, mute_rules)
            if blocked_reason:
                reasons[blocked_reason] += 1
                continue
            delay = timedelta(minutes=0 if alert.severity_level in policy["no_delay_severities"] else policy["settle_delay_minutes"])
            if delay and alert.resolved_at is not None and alert.resolved_at - alert.first_seen_at <= delay:
                reasons["resolved_before_settle"] += 1
                continue
            survivors.append(alert)

        group_window = timedelta(minutes=policy["group_window_minutes"])
        groups: list[dict[str, Any]] = []
        for alert in survivors:
            target_group = next((group for group in groups if self._joins(group, alert, group_window, neighbours)), None)
            if target_group is None:
                target_group = {"last_activity": alert.first_seen_at, "first_seen": alert.first_seen_at, "services": set(), "rules": set(), "score": 0.0}
                groups.append(target_group)
            target_group["last_activity"] = max(target_group["last_activity"], alert.last_seen_at)
            target_group["rules"].add(alert.rule_identifier)
            if alert.service_id:
                target_group["services"].add(alert.service_id)
            tier = (services[alert.service_id].criticality_tier if alert.service_id in services else application.criticality_tier)
            target_group["score"] = max(target_group["score"], alert_rules.calculate_priority_score(alert.severity_level, tier, alert.environment_name, False, False))
        qualifying = sorted((group for group in groups if group["score"] >= policy["investigate_score_threshold"]), key=lambda group: group["first_seen"])
        started_times: list[datetime] = []
        for group in qualifying:
            recent_starts = [start for start in started_times if group["first_seen"] - start < timedelta(hours=1)]
            if len(recent_starts) < policy["max_investigations_per_hour"]:
                started_times.append(group["first_seen"])
        steps = [
            FunnelStep(step_key="received", step_label="Alerts received", count=received_count),
            FunnelStep(step_key="deduplicated", step_label="After de-duplication", count=len(distinct_alerts), detail=f"{reasons['repeats']} repeats counted on existing alerts"),
            FunnelStep(step_key="filtered", step_label="After suppression and settle", count=len(survivors), detail=f"{reasons['maintenance'] + reasons['muted']} in maintenance or muted, {reasons['environment'] + reasons['severity']} filtered, {reasons['resolved_before_settle']} resolved by themselves"),
            FunnelStep(step_key="groups", step_label="Alert groups", count=len(groups)),
            FunnelStep(step_key="investigations", step_label="Investigations", count=len(started_times), detail=f"Score threshold {policy['investigate_score_threshold']}, at most {policy['max_investigations_per_hour']} per hour"),
        ]
        sentence = (f"In the last {(period_end - period_start).days} days: {received_count} alerts became {len(groups)} groups. {reasons['repeats']} were repeats, {reasons['resolved_before_settle']} resolved "
                    f"within {policy['settle_delay_minutes']} minutes, {reasons['maintenance'] + reasons['muted']} arrived during maintenance or were muted.")
        return FunnelResponse(period_start=period_start, period_end=period_end, steps=steps, reason_counts=reasons, summary_sentence=sentence)

    @staticmethod
    def _suppression_reason(alert: Alert, policy: dict[str, Any], windows: list[MaintenanceWindow], mute_rules: list[AlertMuteRule]) -> str | None:
        if any(alert_rules.maintenance_window_applies(window, alert.service_id, alert.environment_name, alert.first_seen_at) for window in windows):
            return "maintenance"
        if any(alert_rules.mute_rule_matches(rule, alert.rule_name, alert.service_id, alert.severity_level, alert.alert_source_id, alert.alert_labels_json or {}, alert.first_seen_at) for rule in mute_rules):
            return "muted"
        if policy["investigate_environments"] and (alert.environment_name or "prod") not in policy["investigate_environments"]:
            return "environment"
        if alert.severity_level > policy["min_severity"]:
            return "severity"
        return None

    @staticmethod
    def _joins(group: dict[str, Any], alert: Alert, window: timedelta, neighbours: dict[str, set[str]]) -> bool:
        if alert.first_seen_at - group["last_activity"] > window:
            return False
        if alert.service_id and (alert.service_id in group["services"] or neighbours.get(alert.service_id, set()) & group["services"]):
            return True
        return alert.rule_identifier in group["rules"]

    @staticmethod
    def _illustration(period_start: datetime, period_end: datetime) -> FunnelResponse:
        steps = [("received", "Alerts received", 412), ("deduplicated", "After de-duplication", 111), ("filtered", "After suppression and settle", 58), ("groups", "Alert groups", 37), ("investigations", "Investigations", 9)]
        return FunnelResponse(
            period_start=period_start, period_end=period_end, is_illustration=True, steps=[FunnelStep(step_key=key, step_label=label, count=count) for key, label, count in steps],
            reason_counts={"repeats": 301, "resolved_before_settle": 52, "maintenance": 22}, summary_sentence="Example, not your data: 412 alerts became 37 groups. 301 were repeats, 52 resolved within 3 minutes, 22 arrived during maintenance.",
        )
