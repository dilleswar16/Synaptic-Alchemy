"""The nine-stage noise-reduction pipeline (sample plan 7A.4).

normalise, deduplicate, lifecycle, suppress, settle, group, prioritise, decide, notify. Every stage writes an ``alert_decision`` row with a
human-readable reason and, in Observe mode, the outcome Active mode *would* have produced. Nothing is dropped: the raw event is always stored.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.alert_ai_schemas import AlertGroupTitleResult, deterministic_group_title
from keigan.ai.llm_gateway import LlmUsageContext, ModelTier, PromptSection
from keigan.config import application_context
from keigan.entities.alert_entities import Alert, AlertDecision, AlertEvent, AlertGroup, AlertMuteRule, AlertSource, MaintenanceWindow, NoiseReductionPolicy
from keigan.entities.application_entities import Application, MonitoredService, ServiceDependency
from keigan.entities.incident_entities import Incident, Investigation
from keigan.services import alert_rules
from keigan.services.alert_rules import CanonicalAlert
from keigan.utils.pii_masker import PiiMasker
from keigan.utils.json_path_utils import read_json_path

logger = logging.getLogger(__name__)
_application_locks: dict[str, asyncio.Lock] = {}
OPEN_GROUP_STATUSES = ("open", "queued")
ACTIVE_INVESTIGATION_OUTCOMES = ("investigation_started", "investigation_replayed")


def group_code(alert_group_id: str) -> str:
    return "AG-" + alert_group_id.replace("-", "")[:6].upper()


@dataclass
class ApplicationAlertContext:
    application: Application
    policy_entity: NoiseReductionPolicy
    policy: dict[str, Any]
    mode: str
    services_by_id: dict[str, MonitoredService]
    neighbours_by_service_id: dict[str, set[str]]
    maintenance_windows: list[MaintenanceWindow]
    mute_rules: list[AlertMuteRule]
    deferred_settle_alert_ids: list[str] = field(default_factory=list)


class AlertPipelineService:
    def __init__(self, session: AsyncSession, *, replay_mode: bool = False):
        """``replay_mode`` is used by the seed: settle waits are completed afterwards from event times, AI titles and investigations are skipped."""
        self.session = session
        self.replay_mode = replay_mode
        self._contexts: dict[str, ApplicationAlertContext] = {}

    # ── Context ────────────────────────────────────────────────────────────────
    async def load_context(self, application_id: str) -> ApplicationAlertContext:
        if application_id in self._contexts:
            return self._contexts[application_id]
        application = await self.session.get(Application, application_id)
        policy_entity = await self.session.get(NoiseReductionPolicy, application_id)
        if policy_entity is None:
            policy_entity = NoiseReductionPolicy(application_id=application_id, policy_settings_json=dict(alert_rules.DEFAULT_NOISE_POLICY), policy_mode="observe", observe_mode_started_at=alert_rules.utc_now())
            self.session.add(policy_entity)
            await self.session.flush()
        services = list((await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id == application_id))).all())
        neighbours: dict[str, set[str]] = {}
        for dependency in (await self.session.scalars(select(ServiceDependency).where(ServiceDependency.application_id == application_id))).all():
            neighbours.setdefault(dependency.upstream_service_id, set()).add(dependency.downstream_service_id)
            neighbours.setdefault(dependency.downstream_service_id, set()).add(dependency.upstream_service_id)
        context = ApplicationAlertContext(
            application=application, policy_entity=policy_entity, policy=alert_rules.merge_policy(policy_entity.policy_settings_json), mode=policy_entity.policy_mode,
            services_by_id={service.service_id: service for service in services}, neighbours_by_service_id=neighbours,
            maintenance_windows=list((await self.session.scalars(select(MaintenanceWindow).where(MaintenanceWindow.application_id == application_id))).all()),
            mute_rules=list((await self.session.scalars(select(AlertMuteRule).where(AlertMuteRule.application_id == application_id))).all()),
        )
        self._contexts[application_id] = context
        return context

    # ── Entry points ───────────────────────────────────────────────────────────
    async def process_event(self, alert_event_id: str) -> dict[str, Any]:
        """Process one event and commit.

        The database (unique index on open alerts, see ``_create_alert_or_merge_into_winner``) is what prevents duplicate alerts across pods.
        The per-application lock below is kept only as a local optimisation: inside one process it avoids pointless insert collisions.
        """
        event = await self.session.get(AlertEvent, alert_event_id)
        if event is None:
            return {"skipped": True, "reason": "event not found"}
        async with _application_locks.setdefault(event.application_id, asyncio.Lock()):
            await self.session.refresh(event)
            result = await self._process_event_locked(event)
            if not self.replay_mode:
                await self.session.commit()
            return result

    async def _process_event_locked(self, event: AlertEvent) -> dict[str, Any]:
        alert_event_id = event.alert_event_id
        if event.processing_status != "received":
            return {"skipped": True, "reason": "already processed"}
        source = await self.session.get(AlertSource, event.alert_source_id)
        context = await self.load_context(event.application_id)
        try:
            canonical = alert_rules.normalise_payload(source.source_tool, event.raw_payload_json or {}, source.field_mapping_json, source.severity_mapping_json)
        except ValueError as parse_error:
            event.processing_status = "failed"
            event.processing_error_message = str(parse_error)[:1000]
            return {"failed": True, "error": str(parse_error)}
        alert_rules.mask_alert_text(canonical)
        if source.source_status in ("waiting_for_first_alert", "authentication_failures"):
            source.source_status = "receiving"
        service = self._resolve_service(context, source, canonical, event.raw_payload_json or {})
        reference_time = event.received_at
        fingerprint = alert_rules.compute_fingerprint(source.alert_source_id, canonical.rule_id, canonical.resource_ref or (service.service_id if service else None), canonical.labels)
        event.processing_status = "processed"
        if canonical.status == "resolved":
            open_alert = await self._find_alert(context, fingerprint, only_open=True)
            if open_alert is None:
                event.processing_error_message = "Resolved notification for an alert Keigan has not seen firing; stored only."
                return {"outcome": "resolved_unknown_alert"}
            await self._apply_resolution(context, open_alert, canonical, event, reference_time)
            return {"outcome": "resolved", "alertId": open_alert.alert_id}
        existing_alert = await self._find_alert(context, fingerprint, only_open=False, reopen_reference=reference_time)
        if existing_alert is not None:
            await self._apply_repeat(context, existing_alert, event, reference_time)
            return {"outcome": "repeat", "alertId": existing_alert.alert_id, "occurrenceCount": existing_alert.occurrence_count}
        alert, was_created = await self._create_alert_or_merge_into_winner(context, source, canonical, service, fingerprint, event, reference_time)
        if not was_created:  # another pod stored the same alert first; this event counted as a repeat on it
            return {"outcome": "repeat", "alertId": alert.alert_id, "occurrenceCount": alert.occurrence_count}
        await self._run_stages_after_creation(context, alert, canonical, service, reference_time)
        return {"outcome": "new_alert", "alertId": alert.alert_id, "disposition": alert.final_disposition, "groupId": alert.alert_group_id}

    async def complete_settle_stage(self, alert_id: str) -> dict[str, Any] | None:
        alert = await self.session.get(Alert, alert_id)
        if alert is None or alert.final_disposition != "settling":
            return {"skipped": True}
        context = await self.load_context(alert.application_id)
        delay = timedelta(minutes=context.policy["settle_delay_minutes"])
        due_time = alert.first_seen_at + delay
        reference_time = due_time if self.replay_mode else max(alert_rules.utc_now(), due_time)
        if alert.resolved_at is not None and alert.resolved_at - alert.first_seen_at <= delay:
            alert.final_disposition = "recorded_only"
            await self._record(alert, "settle", "resolved_before_settle", f"Not investigated: resolved by itself after {alert_rules.seconds_text((alert.resolved_at - alert.first_seen_at).total_seconds())} (settle delay {context.policy['settle_delay_minutes']} min).", reference_time)
            return {"outcome": "resolved_before_settle"}
        await self._record(alert, "settle", "settled", f"Still firing after {context.policy['settle_delay_minutes']} min, so it continues to grouping.", reference_time)
        service = context.services_by_id.get(alert.service_id or "")
        await self._group_prioritise_decide_notify(context, alert, service, reference_time)
        return {"outcome": "settled", "groupId": alert.alert_group_id}

    async def finish_replay_settles(self) -> None:
        """Seed only: complete every deferred settle stage in chronological order."""
        for context in self._contexts.values():
            pending = [await self.session.get(Alert, alert_id) for alert_id in context.deferred_settle_alert_ids]
            for alert in sorted((alert for alert in pending if alert), key=lambda item: item.first_seen_at):
                await self.complete_settle_stage(alert.alert_id)
            context.deferred_settle_alert_ids.clear()

    # ── Stage 1 and 2: normalise and deduplicate ──────────────────────────────
    def _resolve_service(self, context: ApplicationAlertContext, source: AlertSource, canonical: CanonicalAlert, raw_payload: dict[str, Any]) -> MonitoredService | None:
        services = list(context.services_by_id.values())
        if canonical.service_hint and canonical.service_hint in context.services_by_id:
            return context.services_by_id[canonical.service_hint]
        resource_reference = (canonical.resource_ref or "").lower()
        if resource_reference:
            for service in services:
                external_identifier = (service.external_resource_identifier or "").lower()
                if external_identifier and (resource_reference == external_identifier or resource_reference.startswith(external_identifier + "/")):
                    return service
        mapping = source.service_mapping_json or {}
        hint = canonical.service_hint
        if mapping.get("field_path"):
            mapped_hint = read_json_path(raw_payload, mapping["field_path"])
            hint = str(mapped_hint) if mapped_hint not in (None, "") else hint
        if hint:
            lowered_hint = hint.strip().lower()
            for mapped_value, mapped_service_id in (mapping.get("value_map") or {}).items():
                if str(mapped_value).strip().lower() == lowered_hint and mapped_service_id in context.services_by_id:
                    return context.services_by_id[mapped_service_id]
            if mapping.get("auto_match", True):
                for service in services:
                    if service.service_name.lower() == lowered_hint or (service.aks_namespace_filter or "").lower() == lowered_hint:
                        return service
        if resource_reference:
            resource_name = resource_reference.rsplit("/", 1)[-1]
            for service in services:
                if service.service_name.lower() == resource_name:
                    return service
        return None

    async def _find_alert(self, context: ApplicationAlertContext, fingerprint: str, *, only_open: bool, reopen_reference: datetime | None = None) -> Alert | None:
        conditions = [Alert.application_id == context.application.application_id, Alert.alert_fingerprint == fingerprint]
        latest_alert = await self.session.scalar(select(Alert).where(*conditions).order_by(Alert.last_seen_at.desc()).limit(1))
        if latest_alert is None:
            return None
        if latest_alert.alert_status == "firing":
            return latest_alert
        if only_open:
            return None
        reopen_window = timedelta(minutes=context.policy["reopen_window_minutes"])
        if latest_alert.resolved_at is not None and reopen_reference is not None and reopen_reference - latest_alert.resolved_at <= reopen_window:
            return latest_alert
        return None

    async def _create_alert_or_merge_into_winner(
        self, context: ApplicationAlertContext, source: AlertSource, canonical: CanonicalAlert, service: MonitoredService | None, fingerprint: str, event: AlertEvent, reference_time: datetime
    ) -> tuple[Alert, bool]:
        """Insert the alert; if the unique index on open alerts rejects it, another pod won the race, so count a repeat on the winner instead.

        The insert runs in a SAVEPOINT so only it is undone. Returns the alert and whether this call created it.
        """
        try:
            return await self._create_alert(context, source, canonical, service, fingerprint, event, reference_time), True
        except IntegrityError as insert_error:
            winner = await self._find_alert(context, fingerprint, only_open=False, reopen_reference=reference_time)
            if winner is None:
                raise insert_error  # not the fingerprint index (or the winner is not visible): let the job retry in a fresh transaction
            logger.info("Alert %s was created by another worker at the same moment; merging this event into it", fingerprint[:12])
        await self._apply_repeat(context, winner, event, reference_time)
        return winner, False

    async def _create_alert(self, context: ApplicationAlertContext, source: AlertSource, canonical: CanonicalAlert, service: MonitoredService | None, fingerprint: str, event: AlertEvent, reference_time: datetime) -> Alert:
        environment_name = (canonical.environment or (service.environment_name if service else None) or "prod").lower()
        alert = Alert(
            application_id=context.application.application_id, alert_source_id=source.alert_source_id, external_alert_identifier=canonical.external_id[:400], alert_fingerprint=fingerprint,
            rule_identifier=canonical.rule_id[:600], rule_name=canonical.rule_name, service_id=service.service_id if service else None, resource_reference=(canonical.resource_ref or "")[:600] or None,
            environment_name=environment_name, severity_level=canonical.severity, alert_status="firing", alert_summary=canonical.summary, alert_description=canonical.description,
            alert_link_url=canonical.link, alert_labels_json=canonical.labels, occurrence_count=1, state_change_count=1, first_seen_at=reference_time, last_seen_at=reference_time,
            latest_alert_event_id=event.alert_event_id,
        )
        async with self.session.begin_nested():
            self.session.add(alert)
            await self.session.flush()
        where_text = f"service {service.service_name}" if service else "no service (application-level)"
        await self._record(alert, "normalise", "normalised", f"Parsed {source.source_tool.replace('_', ' ')} alert '{canonical.rule_name}': Sev {canonical.severity}, {environment_name}, mapped to {where_text}.", reference_time)
        await self._record(alert, "deduplicate", "new_alert", "First time this alert has been seen, so it starts a new alert.", reference_time)
        return alert

    async def _apply_repeat(self, context: ApplicationAlertContext, alert: Alert, event: AlertEvent, reference_time: datetime) -> None:
        alert.occurrence_count += 1
        alert.last_seen_at = max(alert.last_seen_at, reference_time)
        alert.latest_alert_event_id = event.alert_event_id
        was_resolved = alert.alert_status == "resolved"
        if was_resolved:
            alert.alert_status = "firing"
            alert.resolved_at = None
            alert.state_change_count += 1
            await self._record(alert, "lifecycle", "reopened", f"Fired again within the {context.policy['reopen_window_minutes']} min re-open window, so the same alert was re-opened (seen {alert.occurrence_count} times).", reference_time)
            await self._evaluate_flapping(context, alert, reference_time)
            if alert.alert_group_id:
                group = await self.session.get(AlertGroup, alert.alert_group_id)
                if group is not None and group.group_status == "resolved":
                    group.group_status = "open"
                    group.resolved_at = None
        else:
            await self._upsert_dedupe_decision(alert, f"Repeat of {alert.rule_name} (seen {alert.occurrence_count} times); counted on the existing alert, no new alert.", reference_time)
        if alert.alert_group_id:
            group = await self.session.get(AlertGroup, alert.alert_group_id)
            if group is not None:
                group.last_activity_at = max(group.last_activity_at, reference_time)

    async def _upsert_dedupe_decision(self, alert: Alert, reason: str, reference_time: datetime) -> None:
        dedupe_decision = await self.session.scalar(
            select(AlertDecision).where(AlertDecision.alert_id == alert.alert_id, AlertDecision.pipeline_stage == "deduplicate", AlertDecision.decision_outcome == "repeat").limit(1)
        )
        if dedupe_decision is None:
            await self._record(alert, "deduplicate", "repeat", reason, reference_time)
        else:
            dedupe_decision.decision_reason = reason[:600]
            dedupe_decision.decided_at = reference_time

    # ── Stage 3: lifecycle ─────────────────────────────────────────────────────
    async def _apply_resolution(self, context: ApplicationAlertContext, alert: Alert, canonical: CanonicalAlert, event: AlertEvent, reference_time: datetime) -> None:
        resolved_time = max(reference_time, alert.first_seen_at)
        alert.state_change_count += 1
        alert.last_seen_at = max(alert.last_seen_at, resolved_time)
        alert.latest_alert_event_id = event.alert_event_id
        if alert.is_flapping:
            await self._record(alert, "lifecycle", "kept_open_flapping", f"Flapping alert: the recovery was noted but it stays one open alert until it is quiet for {context.policy['flap_window_minutes']} min.", resolved_time)
            return
        alert.alert_status = "resolved"
        alert.resolved_at = resolved_time
        duration = alert_rules.seconds_text((resolved_time - alert.first_seen_at).total_seconds())
        await self._record(alert, "lifecycle", "resolved", f"Resolved after {duration}.", resolved_time)
        await self._evaluate_flapping(context, alert, resolved_time)
        if context.mode == "observe" and alert.alert_group_id:
            await self._note_observed_settle_resolution(context, alert, resolved_time)
        if alert.alert_group_id:
            await self._resolve_group_if_complete(alert.alert_group_id, resolved_time)

    async def _note_observed_settle_resolution(self, context: ApplicationAlertContext, alert: Alert, resolved_time: datetime) -> None:
        delay = timedelta(minutes=context.policy["settle_delay_minutes"])
        duration = resolved_time - alert.first_seen_at
        if alert.severity_level in context.policy["no_delay_severities"] or duration > delay:
            return
        settle_decision = await self.session.scalar(select(AlertDecision).where(AlertDecision.alert_id == alert.alert_id, AlertDecision.pipeline_stage == "settle").limit(1))
        if settle_decision is not None:
            settle_decision.would_have_outcome_in_active_mode = "resolved_before_settle"
            settle_decision.decision_reason = f"Observe mode: not waiting. It resolved by itself after {alert_rules.seconds_text(duration.total_seconds())}, so Active mode would have recorded it without investigating."[:600]

    async def _evaluate_flapping(self, context: ApplicationAlertContext, alert: Alert, reference_time: datetime) -> None:
        window_start = reference_time - timedelta(minutes=context.policy["flap_window_minutes"])
        change_count = await self.session.scalar(
            select(func.count()).select_from(AlertDecision).where(
                AlertDecision.alert_id == alert.alert_id, AlertDecision.pipeline_stage == "lifecycle", AlertDecision.decision_outcome.in_(("resolved", "reopened")), AlertDecision.decided_at >= window_start
            )
        )
        if (change_count or 0) >= context.policy["flap_count"] and not alert.is_flapping:
            alert.is_flapping = True
            alert.alert_status = "firing"
            alert.resolved_at = None
            await self._record(alert, "lifecycle", "flapping", f"Changed state {change_count} times in {context.policy['flap_window_minutes']} min, so it is treated as flapping and kept as one continuously open alert.", reference_time)

    async def close_quiet_flapping_alerts(self, application_id: str, reference_time: datetime) -> None:
        context = await self.load_context(application_id)
        quiet_before = reference_time - timedelta(minutes=context.policy["flap_window_minutes"])
        quiet_alerts = (await self.session.scalars(select(Alert).where(Alert.application_id == application_id, Alert.is_flapping.is_(True), Alert.alert_status == "firing", Alert.last_seen_at < quiet_before))).all()
        for alert in quiet_alerts:
            alert.is_flapping = False
            alert.alert_status = "resolved"
            alert.resolved_at = alert.last_seen_at
            await self._record(alert, "lifecycle", "resolved", f"Quiet for {context.policy['flap_window_minutes']} min after flapping, so it was closed.", reference_time)
            if alert.alert_group_id:
                await self._resolve_group_if_complete(alert.alert_group_id, reference_time)

    async def _resolve_group_if_complete(self, alert_group_id: str, reference_time: datetime) -> None:
        await self.session.flush()  # sessions do not autoflush: write the alert's new status before counting firing members
        still_firing = await self.session.scalar(select(func.count()).select_from(Alert).where(Alert.alert_group_id == alert_group_id, Alert.alert_status == "firing"))
        group = await self.session.get(AlertGroup, alert_group_id)
        if group is not None and not still_firing and group.group_status != "resolved":
            group.group_status = "resolved"
            group.resolved_at = reference_time
            group.last_activity_at = max(group.last_activity_at, reference_time)

    # ── Stage 4 to 5: suppress and settle ──────────────────────────────────────
    async def _run_stages_after_creation(self, context: ApplicationAlertContext, alert: Alert, canonical: CanonicalAlert, service: MonitoredService | None, reference_time: datetime) -> None:
        policy, mode = context.policy, context.mode
        suppression = self._find_suppression(context, alert, service, reference_time)
        if suppression is not None:
            outcome, reason = suppression
            is_always_applied = outcome == "suppressed_severity"
            if mode == "active" or is_always_applied:
                alert.final_disposition = "recorded_only"
                await self._record(alert, "suppress", outcome, reason, reference_time)
                return
            await self._record(alert, "suppress", "passed", f"Observe mode: not suppressed. Active mode would have recorded it only ({reason})", reference_time, would_have=outcome)
        else:
            await self._record(alert, "suppress", "passed", "Not suppressed: no maintenance window, mute rule or filter matched.", reference_time)
        delay_minutes = 0 if alert.severity_level in policy["no_delay_severities"] else policy["settle_delay_minutes"]
        if delay_minutes == 0:
            await self._record(alert, "settle", "skipped_wait", f"No wait: Sev {alert.severity_level} alerts are investigated immediately.", reference_time)
        elif mode == "observe":
            await self._record(alert, "settle", "skipped_wait", f"Observe mode: not waiting. Active mode would wait {delay_minutes} min in case it clears by itself.", reference_time, would_have="waiting")
        else:
            alert.final_disposition = "settling"
            await self._record(alert, "settle", "waiting", f"Waiting {delay_minutes} min before investigating, in case it clears by itself.", reference_time)
            if self.replay_mode:
                context.deferred_settle_alert_ids.append(alert.alert_id)
            else:
                from keigan.workers.job_queue import JobQueue

                await JobQueue(self.session).enqueue("settle_alert", {"alert_id": alert.alert_id}, deduplication_key=f"settle_alert:{alert.alert_id}", available_at=alert_rules.utc_now() + timedelta(minutes=delay_minutes) if alert.first_seen_at > alert_rules.utc_now() - timedelta(hours=1) else None)
            return
        await self._group_prioritise_decide_notify(context, alert, service, reference_time)

    def _find_suppression(self, context: ApplicationAlertContext, alert: Alert, service: MonitoredService | None, reference_time: datetime) -> tuple[str, str] | None:
        for window in context.maintenance_windows:
            if alert_rules.maintenance_window_applies(window, alert.service_id, alert.environment_name, reference_time):
                return "suppressed_maintenance", f"Suppressed: maintenance window '{window.window_name}'."
        for mute_rule in context.mute_rules:
            if alert_rules.mute_rule_matches(mute_rule, alert.rule_name, alert.service_id, alert.severity_level, alert.alert_source_id, alert.alert_labels_json or {}, reference_time):
                return "suppressed_mute", f"Suppressed: mute rule '{mute_rule.rule_name}' until {mute_rule.expires_at:%Y-%m-%d %H:%M} UTC ({mute_rule.mute_reason})."
        investigated_environments = context.policy["investigate_environments"]
        if investigated_environments and (alert.environment_name or "prod") not in investigated_environments:
            return "suppressed_environment", f"Recorded only: {alert.environment_name} is not an investigated environment (investigating {', '.join(investigated_environments)})."
        if alert.severity_level > context.policy["min_severity"]:
            return "suppressed_severity", f"Recorded only: Sev {alert.severity_level} is less severe than the minimum Sev {context.policy['min_severity']}."
        return None

    # ── Stage 6 to 9: group, prioritise, decide, notify ───────────────────────
    async def _group_prioritise_decide_notify(self, context: ApplicationAlertContext, alert: Alert, service: MonitoredService | None, reference_time: datetime) -> None:
        group, joined, grouping_reason, incident_investigation_id = await self._select_group(context, alert, service, reference_time)
        would_have_outcome = None
        if joined and context.mode == "observe":
            would_have_outcome, joined_group, joined = "joined_group", group, False
            grouping_reason = f"Observe mode: grouping is not applied. Active mode would have joined {group_code(joined_group.alert_group_id)} ({grouping_reason})."
            group = None
        score = await self._calculate_score(context, alert, service, reference_time)
        if group is None:
            group = await self._create_group(context, alert, service, score, grouping_reason, reference_time)
            if incident_investigation_id:
                group.investigation_id = incident_investigation_id[1]
                group.incident_id = incident_investigation_id[0]
            await self._record(alert, "group", "new_group", grouping_reason or "No open group matched, so this alert starts a new group.", reference_time, group_id=group.alert_group_id, would_have=would_have_outcome)
        else:
            await self._join_group(group, alert, score, reference_time)
            await self._record(alert, "group", "joined_group", f"Joined group {group_code(group.alert_group_id)}: {grouping_reason}.", reference_time, group_id=group.alert_group_id)
        await self._record(alert, "prioritise", "scored", self._score_sentence(alert, service, context, score), reference_time, group_id=group.alert_group_id)
        await self._decide(context, group, alert, joined, reference_time)
        notify_reason = (
            f"Joined the notification thread of {group_code(group.alert_group_id)}: later alerts update the same thread, never a new message."
            if joined else "One notification per group: recipients from the notification step are told by severity threshold when the investigation reports."
        )
        await self._record(alert, "notify", "thread_updated" if joined else "notification_planned", notify_reason, reference_time, group_id=group.alert_group_id)

    async def _select_group(self, context: ApplicationAlertContext, alert: Alert, service: MonitoredService | None, reference_time: datetime) -> tuple[AlertGroup | None, bool, str, tuple[str, str | None] | None]:
        window = timedelta(minutes=context.policy["group_window_minutes"])
        window_text = f"{context.policy['group_window_minutes']} minutes"
        candidates = list((await self.session.scalars(
            select(AlertGroup).where(AlertGroup.application_id == alert.application_id, AlertGroup.group_status.in_(OPEN_GROUP_STATUSES), AlertGroup.last_activity_at >= reference_time - window).order_by(AlertGroup.last_activity_at.desc()).limit(60)
        )).all())
        services_of = lambda group: set(group.affected_service_ids_json or []) | ({group.primary_service_id} if group.primary_service_id else set())  # noqa: E731
        if alert.service_id:
            for group in candidates:
                if alert.service_id in services_of(group):
                    return group, True, f"same service within {window_text}", None
            neighbours = context.neighbours_by_service_id.get(alert.service_id, set())
            for group in candidates:
                shared = neighbours & services_of(group)
                if shared:
                    related_name = context.services_by_id[next(iter(shared))].service_name
                    return group, True, f"depends on or is depended on by {related_name} within {window_text}", None
        if candidates and alert.rule_identifier:
            same_rule_group_id = await self.session.scalar(
                select(Alert.alert_group_id).where(Alert.alert_group_id.in_([group.alert_group_id for group in candidates]), Alert.rule_identifier == alert.rule_identifier, Alert.alert_id != alert.alert_id).limit(1)
            )
            if same_rule_group_id:
                return next(group for group in candidates if group.alert_group_id == same_rule_group_id), True, f"same rule '{alert.rule_name}' within {window_text}", None
        open_incident = await self.session.scalar(
            select(Incident).where(Incident.application_id == alert.application_id, Incident.incident_status.not_in(("resolved", "closed")), Incident.opened_at >= reference_time - window, Incident.opened_at <= reference_time).order_by(Incident.opened_at.desc()).limit(1)
        )
        if open_incident is not None:
            investigation_id = await self.session.scalar(select(Investigation.investigation_id).where(Investigation.incident_id == open_incident.incident_id).limit(1))
            incident_group = await self.session.scalar(select(AlertGroup).where(AlertGroup.incident_id == open_incident.incident_id, AlertGroup.group_status.in_(OPEN_GROUP_STATUSES)).limit(1))
            if incident_group is not None:
                return incident_group, True, f"attached to open ServiceNow incident {open_incident.external_incident_number or ''} created within {window_text}".strip(), None
            return None, False, f"Attached to open ServiceNow incident {open_incident.external_incident_number or open_incident.incident_title}: its investigation covers this alert", (open_incident.incident_id, investigation_id)
        return None, False, "No open group matched on service, dependency, rule or incident, so this alert starts a new group.", None

    async def _calculate_score(self, context: ApplicationAlertContext, alert: Alert, service: MonitoredService | None, reference_time: datetime) -> float:
        criticality_tier = (service.criticality_tier if service else None) or context.application.criticality_tier
        slo_is_burning = False
        if service is not None:
            try:
                from keigan.services.slo_service import SloService

                slo_is_burning = await SloService(self.session).is_service_burning_budget(service.service_id, 2.0)
            except Exception:  # noqa: BLE001
                logger.debug("SLO burn lookup skipped", exc_info=True)
        firing_count = await self.session.scalar(
            select(func.count()).select_from(Alert).where(Alert.application_id == alert.application_id, Alert.rule_identifier == alert.rule_identifier, Alert.first_seen_at >= reference_time - timedelta(days=30), Alert.first_seen_at <= reference_time)
        )
        return alert_rules.calculate_priority_score(alert.severity_level, criticality_tier, alert.environment_name, slo_is_burning, (firing_count or 0) < alert_rules.RARE_RULE_FIRING_COUNT)

    def _score_sentence(self, alert: Alert, service: MonitoredService | None, context: ApplicationAlertContext, score: float) -> str:
        tier = (service.criticality_tier if service else None) or context.application.criticality_tier
        return (f"Priority score {score}: severity Sev {alert.severity_level} (x{alert_rules.SEVERITY_WEIGHTS.get(alert.severity_level, 1)}) times {tier.replace('_', ' ')} "
                f"(x{alert_rules.CRITICALITY_WEIGHTS.get(tier, 2)}) times {alert.environment_name} (x{alert_rules.ENVIRONMENT_WEIGHTS.get(alert.environment_name or 'prod', 1)}), with boosts for burning SLOs or rare rules when they apply.")

    async def _create_group(self, context: ApplicationAlertContext, alert: Alert, service: MonitoredService | None, score: float, grouping_reason: str, reference_time: datetime) -> AlertGroup:
        title, summary = await self._generate_title(context, [service.service_name] if service else [], [alert.rule_name], 1, alert.severity_level)
        group = AlertGroup(
            application_id=alert.application_id, group_title=title, group_summary=summary, group_status="open", priority_score=score, grouping_reason=grouping_reason[:400], member_alert_count=1,
            primary_service_id=alert.service_id, affected_service_ids_json=[alert.service_id] if alert.service_id else [], highest_severity_level=alert.severity_level, started_at=reference_time, last_activity_at=reference_time,
        )
        self.session.add(group)
        await self.session.flush()
        alert.alert_group_id = group.alert_group_id
        return group

    async def _join_group(self, group: AlertGroup, alert: Alert, score: float, reference_time: datetime) -> None:
        group.member_alert_count += 1
        group.last_activity_at = max(group.last_activity_at, reference_time)
        group.priority_score = max(group.priority_score, score)
        group.highest_severity_level = min(group.highest_severity_level, alert.severity_level)
        affected = list(group.affected_service_ids_json or [])
        if alert.service_id and alert.service_id not in affected:
            affected.append(alert.service_id)
            group.affected_service_ids_json = affected
        alert.alert_group_id = group.alert_group_id

    async def _generate_title(self, context: ApplicationAlertContext, service_names: list[str], rule_names: list[str], alert_count: int, highest_severity_level: int) -> tuple[str, str]:
        fallback_title, fallback_summary = deterministic_group_title(service_names, rule_names, alert_count)
        if self.replay_mode:
            return fallback_title, fallback_summary
        try:
            masker = PiiMasker()
            result = await application_context.llm_gateway().generate_structured(
                feature_name="alert_group_title", model_tier=ModelTier.FAST,
                system_prompt=application_context.prompt_library().render("alert_group_title", application_name=context.application.application_name),
                prompt_sections=[
                    PromptSection("Services", "Services: " + ", ".join(service_names or ["application-level"])),
                    PromptSection("Severity", f"Severity: Sev {highest_severity_level} (Sev 0 is the most severe, Sev 4 the least)"),
                    PromptSection("Alert group facts", "Rules: " + "; ".join(masker.mask_text(name) for name in rule_names), is_untrusted=True, source_label="alert rule names"),
                    PromptSection("Task", "Write the group title and one-sentence summary."),
                ],
                output_schema=AlertGroupTitleResult, usage_context=LlmUsageContext(application_id=context.application.application_id),
            )
            return result.group_title.strip()[:400] or fallback_title, result.group_summary.strip() or fallback_summary
        except Exception:  # noqa: BLE001 - budget, outage or invalid output: deterministic fallback
            logger.info("Alert group title fell back to the deterministic title", exc_info=True)
            return fallback_title, fallback_summary

    # ── Stage 8: decide ────────────────────────────────────────────────────────
    async def _decide(self, context: ApplicationAlertContext, group: AlertGroup, alert: Alert, joined: bool, reference_time: datetime) -> None:
        code = group_code(group.alert_group_id)
        if joined and group.investigation_id:
            try:
                from keigan.services.investigation_service import InvestigationService

                async with self.session.begin_nested():
                    await InvestigationService(self.session).attach_alerts_to_investigation(group.investigation_id, [alert.alert_id])
                await self._record(alert, "decide", "joined_investigation", f"Added as evidence to the investigation of {code}; no second investigation was started.", reference_time, group_id=group.alert_group_id)
            except Exception as attach_error:  # noqa: BLE001
                await self._record(alert, "decide", "joined_group", f"Joined {code}, which is already being investigated (evidence attach unavailable: {type(attach_error).__name__}).", reference_time, group_id=group.alert_group_id)
            return
        if joined and group.investigation_id is None and group.group_status != "queued" and group.priority_score < context.policy["investigate_score_threshold"]:
            await self._record(alert, "decide", "joined_group", f"Joined {code}; its score {group.priority_score} is still below the investigation threshold {context.policy['investigate_score_threshold']}.", reference_time, group_id=group.alert_group_id)
            return
        await self._try_start_investigation(context, group, alert, reference_time)
        await self._apply_incident_creation_policy(context, group, alert, reference_time)

    async def _try_start_investigation(self, context: ApplicationAlertContext, group: AlertGroup, alert: Alert, reference_time: datetime) -> None:
        code, threshold = group_code(group.alert_group_id), context.policy["investigate_score_threshold"]
        if group.investigation_id:
            await self._record(alert, "decide", "joined_investigation", f"{code} is already covered by an investigation.", reference_time, group_id=group.alert_group_id)
            return
        if group.priority_score < threshold:
            await self._record(alert, "decide", "below_threshold", f"Not investigated: score {group.priority_score} is below the investigation threshold {threshold}. It stays visible as {code}.", reference_time, group_id=group.alert_group_id)
            return
        started_in_last_hour = await self.session.scalar(
            select(func.count(func.distinct(AlertDecision.alert_group_id))).select_from(AlertDecision).join(Alert, Alert.alert_id == AlertDecision.alert_id).where(
                Alert.application_id == context.application.application_id, AlertDecision.pipeline_stage == "decide", AlertDecision.decision_outcome.in_(ACTIVE_INVESTIGATION_OUTCOMES),
                AlertDecision.decided_at >= reference_time - timedelta(hours=1), AlertDecision.decided_at <= reference_time,
            )
        )
        maximum = context.policy["max_investigations_per_hour"]
        if (started_in_last_hour or 0) >= maximum:
            group.group_status = "queued"
            await self._record(alert, "decide", "queued", f"Queued: {started_in_last_hour} investigations were already started in the last hour (limit {maximum}); highest score goes first.", reference_time, group_id=group.alert_group_id)
            return
        if self.replay_mode:
            await self._record(alert, "decide", "investigation_replayed", f"Investigation would start: new group {code} scored {group.priority_score} (threshold {threshold}). Historical replay does not start investigations.", reference_time, group_id=group.alert_group_id)
            return
        try:
            from keigan.services.investigation_service import InvestigationService

            async with self.session.begin_nested():
                investigation_id = await InvestigationService(self.session).start_investigation(
                    context.application.application_id, "alert_group", alert_group_id=group.alert_group_id, service_ids=list(group.affected_service_ids_json or []),
                    description=f"Alert group {code}: {group.group_title}",
                )
            group.investigation_id = investigation_id
            group.group_status = "open"
            await self._record(alert, "decide", "investigation_started", f"Investigation started: new group {code} scored {group.priority_score} (threshold {threshold}).", reference_time, group_id=group.alert_group_id)
        except Exception as start_error:  # noqa: BLE001
            group.group_status = "queued"
            logger.warning("Could not start an investigation for %s: %s", code, start_error)
            await self._record(alert, "decide", "queued", f"Group {code} is queued: the investigation engine is not available right now ({type(start_error).__name__}).", reference_time, group_id=group.alert_group_id)

    async def start_queued_groups(self, application_id: str) -> int:
        """Start queued groups, highest score first, while the hourly limit allows. Called by the settle job and after groups resolve."""
        context = await self.load_context(application_id)
        reference_time = alert_rules.utc_now()
        started = 0
        queued_groups = (await self.session.scalars(select(AlertGroup).where(AlertGroup.application_id == application_id, AlertGroup.group_status == "queued", AlertGroup.investigation_id.is_(None)).order_by(AlertGroup.priority_score.desc()))).all()
        for group in queued_groups:
            anchor_alert = await self.session.scalar(select(Alert).where(Alert.alert_group_id == group.alert_group_id).order_by(Alert.first_seen_at).limit(1))
            if anchor_alert is None:
                continue
            await self._try_start_investigation(context, group, anchor_alert, reference_time)
            if group.investigation_id:
                started += 1
            elif group.group_status == "queued":
                break
        return started

    async def _apply_incident_creation_policy(self, context: ApplicationAlertContext, group: AlertGroup, alert: Alert, reference_time: datetime) -> None:
        policy = context.application.incident_creation_policy_json or {}
        mode = str(policy.get("mode") or policy.get("creationMode") or "suggest")
        threshold = float(policy.get("minimum_score") or policy.get("minimumScore") or policy.get("scoreThreshold") or policy.get("score_threshold") or 40)
        if group.incident_id or group.servicenow_incident_suggested or group.priority_score < threshold or self.replay_mode and mode == "automatic":
            return
        if mode == "automatic":
            try:
                from keigan.services.incident_service import IncidentService

                async with self.session.begin_nested():
                    group.incident_id = await IncidentService(self.session).create_servicenow_incident_from_alert_group(group.alert_group_id)
                await self._record(alert, "decide", "servicenow_incident_created", f"ServiceNow incident created automatically: score {group.priority_score} reached the policy threshold {threshold}.", reference_time, group_id=group.alert_group_id)
                return
            except Exception as creation_error:  # noqa: BLE001
                logger.info("Automatic incident creation unavailable: %s", creation_error)
        group.servicenow_incident_suggested = True
        await self._record(alert, "decide", "servicenow_incident_suggested", f"Suggesting a ServiceNow incident: score {group.priority_score} reached the policy threshold {threshold}.", reference_time, group_id=group.alert_group_id)

    # ── Decision log ───────────────────────────────────────────────────────────
    async def _record(self, alert: Alert, stage: str, outcome: str, reason: str, decided_at: datetime, *, group_id: str | None = None, would_have: str | None = None) -> None:
        self.session.add(AlertDecision(
            alert_id=alert.alert_id, alert_group_id=group_id or alert.alert_group_id, pipeline_stage=stage, decision_outcome=outcome, decision_reason=reason[:600],
            would_have_outcome_in_active_mode=would_have, decided_at=decided_at,
        ))
