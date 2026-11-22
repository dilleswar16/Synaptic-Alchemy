"""Alert views and administration: noise policy, maintenance windows, mute rules, groups, funnel, feedback, weekly noise report, scenario alerts.

Intake and source handling live in ``AlertSourceService``; the nine-stage pipeline lives in ``AlertPipelineService``. This class also holds the
job-handler methods named in ``workers/job_handlers.py``.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.dtos.alert_dtos import (
    AlertDecisionResponse, AlertGroupDetailResponse, AlertGroupFeedbackRequest, AlertGroupSummaryResponse, AlertMemberResponse, FunnelResponse, FunnelStep, GroupingReasonResponse,
    MaintenanceWindowRequest, MaintenanceWindowResponse, MaintenanceWindowUpdateRequest, MuteRuleRequest, MuteRuleResponse, MuteRuleUpdateRequest, NoisePolicyResponse,
    NoisePolicySettings, NoisePolicyUpdateRequest, NoiseReportResponse, NoiseReportRow, ServiceReference,
)
from keigan.dtos.common_dtos import PagedResult
from keigan.entities.alert_entities import Alert, AlertDecision, AlertEvent, AlertGroup, AlertMuteRule, MaintenanceWindow, NoiseReductionPolicy
from keigan.entities.application_entities import Application, MonitoredService, ServiceDependency
from keigan.entities.incident_entities import Incident
from keigan.entities.platform_entities import PlatformSetting
from keigan.entities.status_values import AlertGroupFeedbackVerdict, AlertPipelineStage, NoisePolicyMode
from keigan.exceptions.keigan_exceptions import BusinessValidationException, NotFoundException
from keigan.integrations.simulation.simulation_scenarios import SCENARIO_CATALOG
from keigan.security.current_user import CurrentUser
from keigan.services import alert_rules
from keigan.services.alert_grouping_reason import GroupedAlert, derive_grouping_reason
from keigan.services.alert_pipeline_service import ACTIVE_INVESTIGATION_OUTCOMES, AlertPipelineService, group_code
from keigan.services.alert_source_service import AlertSourceService
from keigan.services.audit_service import AuditService
from keigan.services.authorization_service import AuthorizationService
from keigan.services.noise_preview_service import NoisePreviewService
from keigan.services.service_scope import unknown_service_ids

OBSERVE_MODE_DAYS = 14


class AlertService:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Job handlers ───────────────────────────────────────────────────────────
    async def process_alert_event(self, alert_event_id: str) -> dict[str, Any] | None:
        pipeline = AlertPipelineService(self.session)
        result = await pipeline.process_event(alert_event_id)
        event = await self.session.get(AlertEvent, alert_event_id)
        if event is not None:
            await pipeline.close_quiet_flapping_alerts(event.application_id, event.received_at)
            await pipeline.start_queued_groups(event.application_id)
        return result

    async def complete_settle_stage(self, alert_id: str) -> dict[str, Any] | None:
        pipeline = AlertPipelineService(self.session)
        result = await pipeline.complete_settle_stage(alert_id)
        alert = await self.session.get(Alert, alert_id)
        if alert is not None:
            await pipeline.start_queued_groups(alert.application_id)
        return result

    async def simulate_alerts_for_scenario(self, application_id: str, scenario_window: dict[str, Any], replay_mode: bool = False) -> dict[str, Any] | None:
        scenario = SCENARIO_CATALOG.get(scenario_window.get("scenario_key", ""))
        if scenario is None or not scenario.alert_rule_names:
            return {"events": 0}
        started_at = alert_rules.parse_timestamp(scenario_window["started_at"])
        ended_at = alert_rules.parse_timestamp(scenario_window.get("ended_at"))
        now = alert_rules.utc_now()
        services = {service.service_id: service for service in (await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id == application_id))).all()}
        primary_ids = [service_id for service_id in scenario_window.get("primary_service_ids", []) if service_id in services]
        dependency_ids = [service_id for service_id in scenario_window.get("dependency_service_ids", []) if service_id in services]
        if not primary_ids:
            return {"events": 0}
        source = await AlertSourceService(self.session).get_or_create_simulation_source(application_id)
        random_source = random.Random(f"{scenario.scenario_key}|{started_at.isoformat()}")
        end_of_activity = ended_at or min(now, started_at + timedelta(minutes=30))
        planned: list[tuple[datetime, dict[str, Any]]] = []

        def add_event(timestamp: datetime, rule_name: str, service: MonitoredService, severity: int, is_resolved: bool, instance_key: str) -> None:
            planned.append((timestamp, self._azure_payload(service, rule_name, severity, is_resolved, timestamp, instance_key)))

        for rule_index, rule_name in enumerate(scenario.alert_rule_names):
            service = services[dependency_ids[0]] if dependency_ids and rule_index % 2 == 1 else services[primary_ids[0]]
            severity = (1, 2, 2, 3)[rule_index % 4]
            instance_key = f"{scenario.scenario_key}-{started_at:%Y%m%d%H%M}-{rule_index}"
            fire_time = started_at + timedelta(minutes=rule_index * random_source.randint(1, 2))
            if rule_index % 3 == 2:  # flapping rule: fired / resolved alternating every 3 to 4 minutes
                cursor = fire_time
                for step in range(7):
                    add_event(cursor, rule_name, service, severity, step % 2 == 1, instance_key)
                    cursor += timedelta(minutes=random_source.randint(3, 4))
                    if cursor > end_of_activity:
                        break
            else:
                cursor = fire_time
                while cursor <= end_of_activity and len([1 for _, payload in planned if payload["data"]["essentials"]["alertId"].endswith(instance_key)]) < 28:
                    add_event(cursor, rule_name, service, severity, False, instance_key)
                    cursor += timedelta(minutes=random_source.randint(2, 5))
                if ended_at:
                    add_event(ended_at + timedelta(minutes=random_source.randint(1, 3)), rule_name, service, severity, True, instance_key)
        blip_service = services[primary_ids[0]]  # a short blip that clears by itself, so the noise funnel has something to show
        blip_start = started_at - timedelta(minutes=25)
        if blip_start < now:
            add_event(blip_start, f"{blip_service.service_name} memory > 90%", blip_service, 2, False, f"{scenario.scenario_key}-blip")
            add_event(blip_start + timedelta(seconds=70), f"{blip_service.service_name} memory > 90%", blip_service, 2, True, f"{scenario.scenario_key}-blip")
        pipeline = AlertPipelineService(self.session, replay_mode=replay_mode)
        processed = 0
        for timestamp, payload in sorted(planned, key=lambda item: item[0]):
            if timestamp > now + timedelta(minutes=1):
                continue
            event = AlertEvent(alert_source_id=source.alert_source_id, application_id=application_id, received_at=timestamp, raw_payload_json=payload, payload_size_bytes=600)
            self.session.add(event)
            await self.session.flush()
            await pipeline.process_event(event.alert_event_id)
            source.last_received_at = max(source.last_received_at or timestamp, timestamp)
            source.received_alert_count += 1
            processed += 1
        if replay_mode:
            await pipeline.finish_replay_settles()
        return {"events": processed, "scenario": scenario.scenario_key}

    @staticmethod
    def _azure_payload(service: MonitoredService, rule_name: str, severity: int, is_resolved: bool, timestamp: datetime, instance_key: str) -> dict[str, Any]:
        resource_id = service.external_resource_identifier or f"/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/simulated/providers/Microsoft.Web/sites/{service.service_name}"
        essentials: dict[str, Any] = {
            "alertId": f"/subscriptions/00000000-0000-0000-0000-000000000000/providers/Microsoft.AlertsManagement/alerts/{instance_key}", "alertRule": rule_name, "severity": f"Sev{severity}",
            "signalType": "Metric", "monitorCondition": "Resolved" if is_resolved else "Fired", "monitoringService": "Platform", "alertTargetIDs": [resource_id],
            "firedDateTime": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"), "description": f"{rule_name} on {service.service_name}",
        }
        if is_resolved:
            essentials["resolvedDateTime"] = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
        return {"schemaId": "azureMonitorCommonAlertSchema", "data": {"essentials": essentials, "alertContext": {"condition": {"allOf": [{"metricName": "Simulated", "operator": "GreaterThan", "threshold": "5", "metricValue": "9"}]}}}}

    async def build_noise_report(self, application_id: str) -> dict[str, Any] | None:
        report = await self._compute_noise_report(application_id)
        setting_key = f"noise_report:{application_id}"
        setting = await self.session.get(PlatformSetting, setting_key)
        payload = report.model_dump(mode="json", by_alias=False)
        if setting is None:
            self.session.add(PlatformSetting(setting_key=setting_key, setting_value_json=payload, setting_description="Latest weekly noise report"))
        else:
            setting.setting_value_json = payload
        return {"rows": len(report.rows)}

    async def get_noise_report(self, application_id: str) -> NoiseReportResponse:
        setting = await self.session.get(PlatformSetting, f"noise_report:{application_id}")
        if setting is not None and setting.setting_value_json:
            return NoiseReportResponse.model_validate(setting.setting_value_json)
        await self.build_noise_report(application_id)
        await self.session.flush()
        return await self._compute_noise_report(application_id)

    async def _compute_noise_report(self, application_id: str) -> NoiseReportResponse:
        period_end = alert_rules.utc_now()
        period_start = period_end - timedelta(days=7)
        policy = alert_rules.merge_policy((await self._get_policy_entity(application_id)).policy_settings_json)
        alerts = list((await self.session.scalars(select(Alert).where(Alert.application_id == application_id, Alert.first_seen_at >= period_start))).all())
        service_names = {service.service_id: service.service_name for service in (await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id == application_id))).all()}
        group_ids = {alert.alert_group_id for alert in alerts if alert.alert_group_id}
        groups = {group.alert_group_id: group for group in (await self.session.scalars(select(AlertGroup).where(AlertGroup.alert_group_id.in_(group_ids)))).all()} if group_ids else {}
        by_rule: dict[str, list[Alert]] = {}
        for alert in alerts:
            by_rule.setdefault(alert.rule_name, []).append(alert)
        delay = timedelta(minutes=policy["settle_delay_minutes"])
        rows: list[NoiseReportRow] = []
        for rule_name, rule_alerts in by_rule.items():
            occurrences = sum(alert.occurrence_count for alert in rule_alerts)
            quick = sum(1 for alert in rule_alerts if alert.resolved_at and alert.resolved_at - alert.first_seen_at <= delay)
            quick_percentage = round(100 * quick / len(rule_alerts))
            flapping = sum(1 for alert in rule_alerts if alert.is_flapping)
            led_to_action = any((groups.get(alert.alert_group_id or "") and (groups[alert.alert_group_id].investigation_id or groups[alert.alert_group_id].incident_id or groups[alert.alert_group_id].user_feedback_verdict == AlertGroupFeedbackVerdict.USEFUL)) for alert in rule_alerts)
            if quick_percentage >= 80 and occurrences >= 10:
                suggestion = f"'{rule_name}' fired {occurrences} times; {quick_percentage} % cleared within {policy['settle_delay_minutes']} minutes. Consider raising the threshold or lengthening its evaluation window."
            elif flapping:
                suggestion = f"'{rule_name}' keeps flipping between firing and resolved. Consider adding hysteresis or a longer evaluation window."
            elif not led_to_action and occurrences >= 5:
                suggestion = f"'{rule_name}' fired {occurrences} times and never led to an investigation or incident. Consider lowering its severity or removing it."
            else:
                suggestion = "No change suggested."
            service_counts: dict[str, int] = {}
            for alert in rule_alerts:
                if alert.service_id:
                    service_counts[alert.service_id] = service_counts.get(alert.service_id, 0) + 1
            top_service = max(service_counts, key=service_counts.get) if service_counts else None
            rows.append(NoiseReportRow(rule_name=rule_name, service_name=service_names.get(top_service or ""), alert_count=len(rule_alerts), occurrence_count=occurrences,
                                       resolved_within_settle_delay_percentage=quick_percentage, flapping_count=flapping, led_to_action=bool(led_to_action), suggestion=suggestion))
        rows.sort(key=lambda row: row.occurrence_count, reverse=True)
        total_occurrences = sum(alert.occurrence_count for alert in alerts)
        return NoiseReportResponse(
            application_id=application_id, generated_at=period_end, period_start=period_start, period_end=period_end, total_alert_count=len(alerts), total_occurrence_count=total_occurrences, group_count=len(groups), rows=rows[:10],
            headline=f"{total_occurrences} alert notifications in 7 days became {len(alerts)} alerts and {len(groups)} groups. Keigan only suggests changes; it never edits rules in your monitoring tool.",
        )

    # ── Noise policy ───────────────────────────────────────────────────────────
    async def _get_policy_entity(self, application_id: str) -> NoiseReductionPolicy:
        entity = await self.session.get(NoiseReductionPolicy, application_id)
        if entity is None:
            entity = NoiseReductionPolicy(application_id=application_id, policy_settings_json=dict(alert_rules.DEFAULT_NOISE_POLICY), policy_mode=NoisePolicyMode.OBSERVE, observe_mode_started_at=alert_rules.utc_now())
            self.session.add(entity)
            await self.session.flush()
        return entity

    async def _policy_for_reading(self, application_id: str) -> NoiseReductionPolicy:
        """The application's policy as it stands, without creating its row: a read never writes (the observe-mode clock starts when the policy page first opens it)."""
        return await self.session.get(NoiseReductionPolicy, application_id) or NoiseReductionPolicy(
            application_id=application_id, policy_settings_json=dict(alert_rules.DEFAULT_NOISE_POLICY), policy_mode=NoisePolicyMode.OBSERVE, observe_mode_started_at=None,
        )

    async def get_policy(self, application_id: str) -> NoisePolicyResponse:
        entity = await self._get_policy_entity(application_id)
        settings = alert_rules.merge_policy(entity.policy_settings_json)
        started_at = entity.observe_mode_started_at
        days_remaining = max(0, OBSERVE_MODE_DAYS - (alert_rules.utc_now() - started_at).days) if entity.policy_mode == NoisePolicyMode.OBSERVE and started_at else None
        observed_effect = await self.build_funnel([application_id], started_at or alert_rules.utc_now() - timedelta(days=OBSERVE_MODE_DAYS), alert_rules.utc_now(), settings) if entity.policy_mode == NoisePolicyMode.OBSERVE else None
        total_services = await self.session.scalar(select(func.count()).select_from(MonitoredService).where(MonitoredService.application_id == application_id)) or 0
        with_dependencies = len(set((await self.session.scalars(select(ServiceDependency.upstream_service_id).where(ServiceDependency.application_id == application_id))).all())
                                | set((await self.session.scalars(select(ServiceDependency.downstream_service_id).where(ServiceDependency.application_id == application_id))).all()))
        hint = f"Grouping works better when service dependencies are set: {with_dependencies} of {total_services} services have them." if total_services and with_dependencies < total_services else None
        return NoisePolicyResponse(
            application_id=application_id, policy_mode=entity.policy_mode, policy_settings=NoisePolicySettings(**settings), policy_sentences=alert_rules.policy_sentences(settings),
            observe_mode_started_at=started_at, observe_mode_days_remaining=days_remaining, observed_effect=observed_effect, dependency_hint=hint, updated_at=entity.updated_at,
        )

    async def update_policy(self, current_user: CurrentUser, application_id: str, request: NoisePolicyUpdateRequest) -> NoisePolicyResponse:
        entity = await self._get_policy_entity(application_id)
        if request.reset_to_defaults:
            entity.policy_settings_json = dict(alert_rules.DEFAULT_NOISE_POLICY)
        elif request.policy_settings is not None:
            entity.policy_settings_json = alert_rules.merge_policy(request.policy_settings.model_dump(by_alias=False))
        if request.policy_mode is not None:
            if request.policy_mode == NoisePolicyMode.OBSERVE and entity.policy_mode != NoisePolicyMode.OBSERVE:
                entity.observe_mode_started_at = alert_rules.utc_now()
            entity.policy_mode = request.policy_mode
        entity.updated_by_user_principal_name = current_user.user_principal_name
        await AuditService(self.session).record(current_user, "noise_policy.update", target_entity_type="noise_reduction_policy", target_entity_id=application_id, application_id=application_id,
                                                action_details={"mode": entity.policy_mode, "settings": entity.policy_settings_json})
        await self.session.flush()
        return await self.get_policy(application_id)

    async def preview_policy(self, application_id: str, policy_settings: NoisePolicySettings | None, days: int) -> FunnelResponse:
        entity = await self._get_policy_entity(application_id)
        settings = policy_settings.model_dump(by_alias=False) if policy_settings else entity.policy_settings_json
        return await NoisePreviewService(self.session).preview(application_id, settings, days)

    # ── Maintenance windows ────────────────────────────────────────────────────
    async def _window_response(self, window: MaintenanceWindow) -> MaintenanceWindowResponse:
        service_ids = window.applies_to_service_ids
        names = [service.service_name for service in (await self.session.scalars(select(MonitoredService).where(MonitoredService.service_id.in_(service_ids)))).all()] if service_ids else []
        return MaintenanceWindowResponse(
            maintenance_window_id=window.maintenance_window_id, application_id=window.application_id, window_name=window.window_name, applies_to_service_ids=service_ids, applies_to_service_names=names,
            applies_to_environments=window.applies_to_environments_json or [], starts_at=window.starts_at, ends_at=window.ends_at, repeats_weekly=window.repeats_weekly,
            is_active_now=alert_rules.maintenance_window_is_active(window.starts_at, window.ends_at, window.repeats_weekly, alert_rules.utc_now()), created_by_user_principal_name=window.created_by_user_principal_name,
        )

    async def list_maintenance_windows(self, application_id: str) -> list[MaintenanceWindowResponse]:
        windows = (await self.session.scalars(select(MaintenanceWindow).where(MaintenanceWindow.application_id == application_id).order_by(MaintenanceWindow.starts_at.desc()))).all()
        return [await self._window_response(window) for window in windows]

    async def _ensure_services_belong_to_application(self, application_id: str, service_ids: list[str] | None) -> None:
        if await unknown_service_ids(self.session, application_id, service_ids):
            raise BusinessValidationException("A selected service is not part of this application.", field_errors=[{"field": "appliesToServiceIds", "message": "Unknown service."}])

    async def create_maintenance_window(self, current_user: CurrentUser, application_id: str, request: MaintenanceWindowRequest) -> MaintenanceWindowResponse:
        if request.ends_at <= request.starts_at:
            raise BusinessValidationException("The window must end after it starts.", field_errors=[{"field": "endsAt", "message": "Must be after the start."}])
        await self._ensure_services_belong_to_application(application_id, request.applies_to_service_ids)
        window = MaintenanceWindow(
            application_id=application_id, window_name=request.window_name.strip(), applies_to_environments_json=request.applies_to_environments or [],
            starts_at=request.starts_at, ends_at=request.ends_at, repeats_weekly=request.repeats_weekly, created_by_user_principal_name=current_user.user_principal_name, updated_by_user_principal_name=current_user.user_principal_name,
        )
        window.replace_linked_ids("service_links", request.applies_to_service_ids)
        self.session.add(window)
        await self.session.flush()
        await AuditService(self.session).record(current_user, "maintenance_window.create", target_entity_type="maintenance_window", target_entity_id=window.maintenance_window_id, application_id=application_id, action_details={"name": window.window_name})
        return await self._window_response(window)

    async def _get_window(self, application_id: str, window_id: str) -> MaintenanceWindow:
        window = await self.session.get(MaintenanceWindow, window_id)
        if window is None or window.application_id != application_id:
            raise NotFoundException("Maintenance window not found.")
        return window

    async def update_maintenance_window(self, current_user: CurrentUser, application_id: str, window_id: str, request: MaintenanceWindowUpdateRequest) -> MaintenanceWindowResponse:
        window = await self._get_window(application_id, window_id)
        provided = request.model_fields_set
        if request.window_name is not None:
            window.window_name = request.window_name.strip()
        if "applies_to_service_ids" in provided:
            await self._ensure_services_belong_to_application(application_id, request.applies_to_service_ids)
            window.replace_linked_ids("service_links", request.applies_to_service_ids)
        if "applies_to_environments" in provided:
            window.applies_to_environments_json = request.applies_to_environments or []
        window.starts_at = request.starts_at or window.starts_at
        window.ends_at = request.ends_at or window.ends_at
        if request.repeats_weekly is not None:
            window.repeats_weekly = request.repeats_weekly
        if window.ends_at <= window.starts_at:
            raise BusinessValidationException("The window must end after it starts.")
        window.updated_by_user_principal_name = current_user.user_principal_name
        await AuditService(self.session).record(current_user, "maintenance_window.update", target_entity_type="maintenance_window", target_entity_id=window_id, application_id=application_id)
        return await self._window_response(window)

    async def delete_maintenance_window(self, current_user: CurrentUser, application_id: str, window_id: str) -> None:
        window = await self._get_window(application_id, window_id)
        await self.session.delete(window)
        await AuditService(self.session).record(current_user, "maintenance_window.delete", target_entity_type="maintenance_window", target_entity_id=window_id, application_id=application_id, action_details={"name": window.window_name})

    # ── Mute rules ─────────────────────────────────────────────────────────────
    @staticmethod
    def _mute_response(rule: AlertMuteRule) -> MuteRuleResponse:
        return MuteRuleResponse(mute_rule_id=rule.mute_rule_id, application_id=rule.application_id, rule_name=rule.rule_name, matcher=rule.matcher_json, mute_reason=rule.mute_reason, expires_at=rule.expires_at,
                                is_expired=rule.expires_at <= alert_rules.utc_now(), created_by_user_principal_name=rule.created_by_user_principal_name)

    async def list_mute_rules(self, application_id: str) -> list[MuteRuleResponse]:
        rules = (await self.session.scalars(select(AlertMuteRule).where(AlertMuteRule.application_id == application_id).order_by(AlertMuteRule.expires_at.desc()))).all()
        return [self._mute_response(rule) for rule in rules]

    @staticmethod
    def _validate_matcher(matcher: dict[str, Any]) -> dict[str, Any]:
        cleaned = {key: value for key, value in matcher.items() if value not in (None, "")}
        if not cleaned or ("label_value" in cleaned and "label_key" not in cleaned):
            raise BusinessValidationException("Choose at least one matcher: rule name contains, service, source, severity or label.", field_errors=[{"field": "matcher", "message": "Required."}])
        return cleaned

    async def create_mute_rule(self, current_user: CurrentUser, application_id: str, request: MuteRuleRequest) -> MuteRuleResponse:
        if request.expires_at <= alert_rules.utc_now():
            raise BusinessValidationException("A mute rule must expire in the future.", field_errors=[{"field": "expiresAt", "message": "Must be in the future."}])
        rule = AlertMuteRule(
            application_id=application_id, rule_name=request.rule_name.strip(), matcher_json=self._validate_matcher(request.matcher.model_dump(by_alias=False)), mute_reason=request.mute_reason.strip(),
            expires_at=request.expires_at, created_by_user_principal_name=current_user.user_principal_name, updated_by_user_principal_name=current_user.user_principal_name,
        )
        self.session.add(rule)
        await self.session.flush()
        await AuditService(self.session).record(current_user, "mute_rule.create", target_entity_type="alert_mute_rule", target_entity_id=rule.mute_rule_id, application_id=application_id, action_details={"name": rule.rule_name, "reason": rule.mute_reason})
        return self._mute_response(rule)

    async def update_mute_rule(self, current_user: CurrentUser, application_id: str, mute_rule_id: str, request: MuteRuleUpdateRequest) -> MuteRuleResponse:
        rule = await self.session.get(AlertMuteRule, mute_rule_id)
        if rule is None or rule.application_id != application_id:
            raise NotFoundException("Mute rule not found.")
        if request.rule_name is not None:
            rule.rule_name = request.rule_name.strip()
        if request.matcher is not None:
            rule.matcher_json = self._validate_matcher(request.matcher.model_dump(by_alias=False))
        if request.mute_reason is not None:
            rule.mute_reason = request.mute_reason.strip()
        if request.expires_at is not None:
            rule.expires_at = request.expires_at
        rule.updated_by_user_principal_name = current_user.user_principal_name
        await AuditService(self.session).record(current_user, "mute_rule.update", target_entity_type="alert_mute_rule", target_entity_id=mute_rule_id, application_id=application_id)
        return self._mute_response(rule)

    async def delete_mute_rule(self, current_user: CurrentUser, application_id: str, mute_rule_id: str) -> None:
        rule = await self.session.get(AlertMuteRule, mute_rule_id)
        if rule is None or rule.application_id != application_id:
            raise NotFoundException("Mute rule not found.")
        await self.session.delete(rule)
        await AuditService(self.session).record(current_user, "mute_rule.delete", target_entity_type="alert_mute_rule", target_entity_id=mute_rule_id, application_id=application_id, action_details={"name": rule.rule_name})

    # ── Funnel ─────────────────────────────────────────────────────────────────
    async def funnel_for_user(self, current_user: CurrentUser, application_ids: list[str] | None, period_start: datetime | None, period_end: datetime | None) -> FunnelResponse:
        scoped_ids = await AuthorizationService(self.session).scoped_application_ids(current_user, application_ids)
        end = period_end or alert_rules.utc_now()
        return await self.build_funnel(scoped_ids, period_start or end - timedelta(days=7), end, None)

    async def build_funnel(self, application_ids: list[str], period_start: datetime, period_end: datetime, policy_settings: dict[str, Any] | None) -> FunnelResponse:
        """Counts what happened (Active) or would have happened (Observe) using the decision log, so the funnel is auditable."""
        if not application_ids:
            return FunnelResponse(period_start=period_start, period_end=period_end, steps=[])
        alerts = list((await self.session.scalars(select(Alert).where(Alert.application_id.in_(application_ids), Alert.first_seen_at >= period_start, Alert.first_seen_at <= period_end))).all())
        received = sum(alert.occurrence_count for alert in alerts)
        alert_ids = [alert.alert_id for alert in alerts]
        decisions_by_alert: dict[str, dict[str, str]] = {}
        started_group_by_alert: dict[str, str] = {}
        for chunk_start in range(0, len(alert_ids), 500):
            chunk = alert_ids[chunk_start:chunk_start + 500]
            rows = (await self.session.execute(
                select(AlertDecision.alert_id, AlertDecision.pipeline_stage, AlertDecision.decision_outcome, AlertDecision.would_have_outcome_in_active_mode, AlertDecision.alert_group_id)
                .where(AlertDecision.alert_id.in_(chunk), AlertDecision.pipeline_stage.in_((AlertPipelineStage.SUPPRESS, AlertPipelineStage.SETTLE, AlertPipelineStage.GROUP, AlertPipelineStage.DECIDE)))
            )).all()
            for alert_id, stage, outcome, would_have, group_id in rows:
                decisions_by_alert.setdefault(alert_id, {})[stage] = would_have or outcome
                if stage == "decide" and outcome in ACTIVE_INVESTIGATION_OUTCOMES and group_id:
                    started_group_by_alert[alert_id] = group_id
        reasons = {"repeats": received - len(alerts), "maintenance": 0, "muted": 0, "environment": 0, "severity": 0, "resolved_before_settle": 0, "flapping": sum(1 for alert in alerts if alert.is_flapping)}
        survivors = 0
        started_groups: set[str] = set()
        surviving_group_ids: set[str] = set()
        for alert in alerts:
            stages = decisions_by_alert.get(alert.alert_id, {})
            suppression = stages.get("suppress", "")
            if suppression.startswith("suppressed_"):
                reasons[{"suppressed_maintenance": "maintenance", "suppressed_mute": "muted", "suppressed_environment": "environment", "suppressed_severity": "severity"}[suppression]] += 1
            elif stages.get("settle") == "resolved_before_settle":
                reasons["resolved_before_settle"] += 1
            else:
                survivors += 1
                if alert.alert_id in started_group_by_alert:
                    started_groups.add(started_group_by_alert[alert.alert_id])
                if alert.alert_group_id:
                    surviving_group_ids.add(alert.alert_group_id)
        group_count = len(surviving_group_ids | started_groups)  # a group is counted once, however its alerts arrived, so groups ≥ investigations
        policy = alert_rules.merge_policy(policy_settings or (await self._policy_for_reading(application_ids[0])).policy_settings_json)
        steps = [
            FunnelStep(step_key="received", step_label="Alerts received", count=received),
            FunnelStep(step_key="deduplicated", step_label="After de-duplication", count=len(alerts), detail=f"{reasons['repeats']} repeats counted on existing alerts"),
            FunnelStep(step_key="filtered", step_label="After suppression and settle", count=survivors),
            FunnelStep(step_key="groups", step_label="Alert groups", count=group_count),
            FunnelStep(step_key="investigations", step_label="Investigations", count=len(started_groups)),
        ]
        sentence = (f"{received} alerts became {group_count} groups. {reasons['repeats']} were repeats, {reasons['resolved_before_settle']} resolved within {policy['settle_delay_minutes']} minutes, "
                    f"{reasons['maintenance'] + reasons['muted']} arrived during maintenance or were muted.")
        return FunnelResponse(period_start=period_start, period_end=period_end, steps=steps, reason_counts=reasons, summary_sentence=sentence, is_illustration=False)

    # ── Alert groups ───────────────────────────────────────────────────────────
    async def list_groups(
        self, current_user: CurrentUser, application_ids: list[str] | None, statuses: list[str] | None, period_start: datetime | None, period_end: datetime | None, minimum_score: float | None, page: int, page_size: int,
    ) -> PagedResult[AlertGroupSummaryResponse]:
        scoped_ids = await AuthorizationService(self.session).scoped_application_ids(current_user, application_ids)
        conditions = [AlertGroup.application_id.in_(scoped_ids)]
        if statuses:
            conditions.append(AlertGroup.group_status.in_(statuses))
        if period_start:
            conditions.append(AlertGroup.last_activity_at >= period_start)
        if period_end:
            conditions.append(AlertGroup.started_at <= period_end)
        if minimum_score is not None:
            conditions.append(AlertGroup.priority_score >= minimum_score)
        total = await self.session.scalar(select(func.count()).select_from(AlertGroup).where(*conditions)) or 0
        page_size = max(1, min(page_size, 200))
        groups = list((await self.session.scalars(select(AlertGroup).where(*conditions).order_by(AlertGroup.last_activity_at.desc()).offset((max(page, 1) - 1) * page_size).limit(page_size))).all())
        return PagedResult(items=await self._summaries(groups), total_count=total, page=page, page_size=page_size)

    async def _summaries(self, groups: list[AlertGroup]) -> list[AlertGroupSummaryResponse]:
        if not groups:
            return []
        group_ids = [group.alert_group_id for group in groups]
        service_names = {service.service_id: service.service_name for service in (await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id.in_({group.application_id for group in groups})))).all()}
        application_names = {app.application_id: app.application_name for app in (await self.session.scalars(select(Application).where(Application.application_id.in_({group.application_id for group in groups})))).all()}
        occurrence_totals = dict((await self.session.execute(select(Alert.alert_group_id, func.sum(Alert.occurrence_count)).where(Alert.alert_group_id.in_(group_ids)).group_by(Alert.alert_group_id))).all())
        latest_decisions: dict[str, AlertDecision] = {}
        for decision in (await self.session.scalars(select(AlertDecision).where(AlertDecision.alert_group_id.in_(group_ids), AlertDecision.pipeline_stage == AlertPipelineStage.DECIDE, AlertDecision.decision_outcome.not_like("servicenow_%")).order_by(AlertDecision.decided_at))).all():
            latest_decisions[decision.alert_group_id or ""] = decision
        grouping_reasons = await self.grouping_reasons(groups, service_names)
        summaries = []
        for group in groups:
            decision = latest_decisions.get(group.alert_group_id)
            summaries.append(AlertGroupSummaryResponse(
                alert_group_id=group.alert_group_id, application_id=group.application_id, application_name=application_names.get(group.application_id), group_title=group.group_title, group_summary=group.group_summary,
                group_status=group.group_status, priority_score=group.priority_score, grouping_reason=grouping_reasons[group.alert_group_id], member_alert_count=group.member_alert_count, total_occurrence_count=int(occurrence_totals.get(group.alert_group_id) or 0),
                services=[ServiceReference(service_id=service_id, service_name=service_names[service_id]) for service_id in group.affected_service_ids if service_id in service_names],
                highest_severity_level=group.highest_severity_level, started_at=group.started_at, last_activity_at=group.last_activity_at, resolved_at=group.resolved_at, investigation_id=group.investigation_id,
                incident_id=group.incident_id, servicenow_incident_suggested=group.servicenow_incident_suggested, user_feedback_verdict=group.user_feedback_verdict,
                decision_reason=decision.decision_reason if decision else group.grouping_reason, decision_outcome=(decision.would_have_outcome_in_active_mode or decision.decision_outcome) if decision else None,
            ))
        return summaries

    async def grouping_reasons(self, groups: list[AlertGroup], service_names: dict[str, str]) -> dict[str, GroupingReasonResponse]:
        """Why each group's alerts belong together, worked out from its alerts, the application's dependencies and its group window (the policy, or its default)."""
        group_ids = [group.alert_group_id for group in groups]
        application_ids = {group.application_id for group in groups}
        members_by_group: dict[str, list[GroupedAlert]] = {}
        for group_id, service_id, rule_identifier, rule_name, first_seen_at in (await self.session.execute(
            select(Alert.alert_group_id, Alert.service_id, Alert.rule_identifier, Alert.rule_name, Alert.first_seen_at).where(Alert.alert_group_id.in_(group_ids))
        )).all():
            members_by_group.setdefault(group_id, []).append(GroupedAlert(service_id, rule_identifier, rule_name, first_seen_at))
        window_by_application = {application_id: alert_rules.merge_policy(None)["group_window_minutes"] for application_id in application_ids}
        for policy in (await self.session.scalars(select(NoiseReductionPolicy).where(NoiseReductionPolicy.application_id.in_(application_ids)))).all():
            window_by_application[policy.application_id] = alert_rules.merge_policy(policy.policy_settings_json)["group_window_minutes"]
        dependencies = (await self.session.scalars(select(ServiceDependency).where(ServiceDependency.application_id.in_(application_ids)))).all()
        neighbours = alert_rules.service_neighbours((dependency.upstream_service_id, dependency.downstream_service_id) for dependency in dependencies)
        incident_ids = {group.incident_id for group in groups if group.incident_id}
        incident_names = {
            incident.incident_id: incident.external_incident_number or incident.incident_title
            for incident in (await self.session.scalars(select(Incident).where(Incident.incident_id.in_(incident_ids)))).all()
        } if incident_ids else {}
        reasons: dict[str, GroupingReasonResponse] = {}
        for group in groups:
            derived = derive_grouping_reason(
                members_by_group.get(group.alert_group_id, []), neighbours_by_service_id=neighbours, service_names=service_names,
                window_minutes=window_by_application[group.application_id], incident_name=incident_names.get(group.incident_id or ""),
            )
            reasons[group.alert_group_id] = GroupingReasonResponse(code=derived.code, parameters=derived.parameters)
        return reasons

    async def _readable_group(self, current_user: CurrentUser, alert_group_id: str, *, require_admin: bool = False) -> AlertGroup:
        group = await self.session.get(AlertGroup, alert_group_id)
        if group is None:
            raise NotFoundException("Alert group not found.")
        authorization = AuthorizationService(self.session)
        if require_admin:
            await authorization.ensure_application_admin(current_user, group.application_id)
        else:
            await authorization.ensure_application_reader(current_user, group.application_id)
        return group

    async def get_group(self, current_user: CurrentUser, alert_group_id: str) -> AlertGroupDetailResponse:
        group = await self._readable_group(current_user, alert_group_id)
        summary = (await self._summaries([group]))[0]
        alerts = (await self.session.scalars(select(Alert).where(Alert.alert_group_id == alert_group_id).order_by(Alert.first_seen_at))).all()
        service_names = {service.service_id: service.service_name for service in (await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id == group.application_id))).all()}
        rule_names = {alert.alert_id: alert.rule_name for alert in alerts}
        decisions = (await self.session.scalars(select(AlertDecision).where(AlertDecision.alert_id.in_(list(rule_names))).order_by(AlertDecision.decided_at, AlertDecision.pipeline_stage))).all() if rule_names else []
        policy = await self._policy_for_reading(group.application_id)
        application = await self.session.get(Application, group.application_id)
        return AlertGroupDetailResponse(
            **summary.model_dump(), user_feedback_reason=group.user_feedback_reason, policy_mode=policy.policy_mode, incident_creation_policy=application.incident_creation_policy_json if application else None,
            members=[AlertMemberResponse(
                alert_id=alert.alert_id, rule_name=alert.rule_name, alert_status=alert.alert_status, severity_level=alert.severity_level, service_id=alert.service_id, service_name=service_names.get(alert.service_id or ""),
                alert_summary=alert.alert_summary, alert_link_url=alert.alert_link_url, occurrence_count=alert.occurrence_count, is_flapping=alert.is_flapping, first_seen_at=alert.first_seen_at,
                last_seen_at=alert.last_seen_at, resolved_at=alert.resolved_at, final_disposition=alert.final_disposition) for alert in alerts],
            decisions=[AlertDecisionResponse(
                alert_decision_id=decision.alert_decision_id, alert_id=decision.alert_id, rule_name=rule_names.get(decision.alert_id), pipeline_stage=decision.pipeline_stage, decision_outcome=decision.decision_outcome,
                decision_reason=decision.decision_reason, would_have_outcome_in_active_mode=decision.would_have_outcome_in_active_mode, decided_at=decision.decided_at) for decision in decisions],
        )

    async def record_feedback(self, current_user: CurrentUser, alert_group_id: str, request: AlertGroupFeedbackRequest) -> AlertGroupSummaryResponse:
        group = await self._readable_group(current_user, alert_group_id)
        group.user_feedback_verdict = request.verdict
        group.user_feedback_reason = request.reason
        group.user_feedback_by_user_principal_name = current_user.user_principal_name
        await AuditService(self.session).record(current_user, "alert_group.feedback", target_entity_type="alert_group", target_entity_id=alert_group_id, application_id=group.application_id, action_details={"verdict": request.verdict, "reason": request.reason})
        return (await self._summaries([group]))[0]

    async def create_servicenow_incident(self, current_user: CurrentUser, alert_group_id: str) -> str:
        group = await self._readable_group(current_user, alert_group_id, require_admin=True)
        if group.incident_id:
            return group.incident_id
        from keigan.services.incident_service import IncidentService

        incident_id = await IncidentService(self.session).create_servicenow_incident_from_alert_group(alert_group_id, current_user.user_principal_name)
        group.servicenow_incident_suggested = False
        await AuditService(self.session).record(current_user, "alert_group.create_incident", target_entity_type="alert_group", target_entity_id=alert_group_id, application_id=group.application_id, action_details={"incident_id": incident_id})
        return incident_id


__all__ = ["AlertService", "group_code"]
