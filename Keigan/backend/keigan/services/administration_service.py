"""Administration: effective settings, connection tests, usage, audit queries, job queue view, retention cleanup, simulation."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.llm_gateway import LlmUsageContext, ModelTier
from keigan.config import application_context
from keigan.config.settings import Settings, get_settings, safe_settings_for_display
from keigan.dtos.administration_dtos import (
    AdministrationSettingsResponse, AuditEventResponse, ConnectionTestOutcome, IntegrationStatusResponse, JobResponse, JobStatsResponse, KeiganIdentityResponse,
    SettingsGroupResponse, SimulationScenarioResponse, UsageBucketResponse, UsageResponse,
)
from keigan.dtos.common_dtos import PagedResult
from keigan.entities.all_entities import (
    Alert, AlertDecision, AlertEvent, AlertGroup, Application, AuditEvent, BackgroundJob, Investigation, LlmUsageRecord, SliMeasurement,
)
from keigan.exceptions.keigan_exceptions import BusinessValidationException, NotFoundException
from keigan.security.current_user import CurrentUser
from keigan.services.audit_service import AuditService
from keigan.services.incident_retention import purge_expired_incidents
from keigan.services.simulation_service import SimulationService
from keigan.utils.time_utils import utc_now
from keigan.workers.worker_settings import get_worker_settings

logger = logging.getLogger(__name__)
SETTING_GROUPS: list[tuple[str, str, tuple[str, ...]]] = [
    ("general", "General", ("environment", "log_level", "product_version", "public_base_url", "frontend_base_url", "run_workers_in_process", "worker_", "auto_create_schema")),
    ("authentication", "Authentication", ("auth_", "entra_", "keigan_admin_group", "application_admin_group", "application_reader_group", "local_token")),
    ("integrations", "Integrations", ("telemetry_mode", "servicenow_", "teams_", "email_", "smtp_", "graph_", "azure_", "keigan_managed", "keigan_multi")),
    ("ai", "AI", ("llm_", "log_prompts", "investigation_", "auto_send")),
    ("safety", "Safety and limits", ("pii_", "alert_intake_", "chat_rate", "max_", "raw_alert", "incident_retention", "sli_raw")),
    ("storage", "Storage and monitoring", ("file_storage", "azure_blob", "secret_store", "azure_key_vault", "local_secret", "data_directory", "database_", "sli_", "slo_", "predictive_", "intelligence_")),
]
RETENTION_AUDIT_AND_USAGE_DAYS = 400
RETENTION_FINISHED_JOB_DAYS = 14


class AdministrationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings: Settings = get_settings()

    # ── Settings ─────────────────────────────────────────────────────────────────────────────────────────────────────
    async def get_settings(self) -> AdministrationSettingsResponse:
        displayed = safe_settings_for_display(self.settings)
        groups: dict[str, dict[str, Any]] = {key: {} for key, _, _ in SETTING_GROUPS}
        for name, value in displayed.items():
            group_key = next((key for key, _, prefixes in SETTING_GROUPS if any(name.startswith(prefix) for prefix in prefixes)), "general")
            groups[group_key][name] = value.value if hasattr(value, "value") else value
        s = self.settings
        keigan_identity = await application_context.azure_credential_provider().resolve_keigan_identity()
        identity = KeiganIdentityResponse(
            managed_identity_object_id=keigan_identity.object_id or "", managed_identity_client_id=keigan_identity.client_id or "",
            managed_identity_display_name=keigan_identity.display_name or "", multi_tenant_app_client_id=s.keigan_multi_tenant_app_client_id or None)
        return AdministrationSettingsResponse(
            environment=str(s.environment.value), product_version=s.product_version,
            groups=[SettingsGroupResponse(group_key=key, group_title=title, settings=groups[key]) for key, title, _ in SETTING_GROUPS if groups[key]],
            integrations=self._integration_statuses(), keigan_identity=identity, simulation_controls_available=s.is_local_environment or s.environment.value == "test")

    def _integration_statuses(self) -> list[IntegrationStatusResponse]:
        s = self.settings
        llm_mock = s.llm_provider.value == "mock"
        return [
            IntegrationStatusResponse(integration_key="telemetry", mode=s.telemetry_mode.value, is_simulated=s.telemetry_mode.value == "simulated", is_configured=True, summary="Log and metric reading"),
            IntegrationStatusResponse(integration_key="servicenow", mode=s.servicenow_mode.value, is_simulated=s.servicenow_mode.value == "simulated", is_configured=bool(s.servicenow_instance_url) or s.servicenow_mode.value == "simulated", summary=s.servicenow_instance_url or "Simulated ServiceNow"),
            IntegrationStatusResponse(integration_key="teams", mode=s.teams_mode.value, is_simulated=s.teams_mode.value == "simulated", is_configured=bool(s.teams_bot_app_id) or s.teams_mode.value == "simulated", summary="Teams incident chats and bot"),
            IntegrationStatusResponse(integration_key="email", mode=s.email_mode.value, is_simulated=s.email_mode.value == "simulated", is_configured=s.email_mode.value == "simulated" or bool(s.smtp_host or s.graph_sender_mailbox), summary=s.email_from_address),
            IntegrationStatusResponse(integration_key="llm", mode=s.llm_provider.value, is_simulated=llm_mock, is_configured=llm_mock or bool(s.llm_api_key) or s.llm_use_managed_identity, summary=f"{s.llm_fast_model} / {s.llm_deep_model}"),
            IntegrationStatusResponse(integration_key="azure", mode=s.azure_identity_mode.value, is_simulated=s.azure_identity_mode.value == "none", is_configured=s.azure_identity_mode.value != "none", summary="Azure resource reading identity"),
            IntegrationStatusResponse(integration_key="authentication", mode=s.auth_mode.value, is_simulated=s.auth_mode.value == "local", is_configured=True, summary="Sign-in provider"),
        ]

    async def test_connection(self, current_user: CurrentUser, integration: str) -> ConnectionTestOutcome:
        testers = {"servicenow": self._test_servicenow, "graph": self._test_graph, "llm": self._test_llm, "azure": self._test_azure, "email": self._test_email}
        if integration not in testers:
            raise BusinessValidationException(f"Unknown integration '{integration}'. Use one of: {', '.join(testers)}.")
        try:
            succeeded, message, details = await testers[integration]()
        except Exception as test_error:  # noqa: BLE001 — a failed test is a result, not a server error
            succeeded, message, details = False, str(test_error)[:400], {}
        await AuditService(self.session).record(current_user, "administration.connection_test", action_details={"integration": integration, "succeeded": succeeded})
        return ConnectionTestOutcome(integration=integration, succeeded=succeeded, message=message, details=details, tested_at=utc_now())

    async def _test_servicenow(self) -> tuple[bool, str, dict[str, Any]]:
        if self.settings.servicenow_mode.value == "simulated":
            return True, "ServiceNow is in simulated mode; the built-in simulator is reachable.", {"mode": "simulated"}
        from keigan.integrations.servicenow_client import ServiceNowClient

        client = ServiceNowClient(self.settings, application_context.secret_store())
        await client.list_incidents(["Keigan connection test"], utc_now() - timedelta(minutes=1))
        return True, f"Reached {self.settings.servicenow_instance_url}.", {"mode": "live"}

    async def _test_graph(self) -> tuple[bool, str, dict[str, Any]]:
        if self.settings.teams_mode.value == "simulated" and self.settings.email_mode.value == "simulated":
            return True, "Microsoft Graph features run in simulated mode.", {"mode": "simulated"}
        if self.settings.azure_identity_mode.value == "none":
            return False, "No Azure identity is configured for Microsoft Graph.", {}
        return True, "An Azure identity is configured; Graph permissions are checked when a message is first sent.", {"mailbox": self.settings.graph_sender_mailbox}

    async def _test_llm(self) -> tuple[bool, str, dict[str, Any]]:
        gateway = application_context.llm_gateway()
        if gateway.is_mock:
            return True, "The AI provider is in mock mode; no external model is called.", {"provider": "mock"}
        result = await gateway.generate_text(
            feature_name="connection_test", model_tier=ModelTier.FAST, system_prompt="Reply with the single word OK.", prompt_sections=[],
            usage_context=LlmUsageContext(enforce_token_budget=False))
        return True, f"{gateway.provider_name} answered: {result.text.strip()[:40]}", {"model": result.model_name, "inputTokens": result.input_token_count}

    async def _test_azure(self) -> tuple[bool, str, dict[str, Any]]:
        if self.settings.azure_identity_mode.value == "none":
            return True, "Azure reading is simulated (no Azure identity configured).", {"mode": "simulated"}
        return True, f"Azure identity mode '{self.settings.azure_identity_mode.value}' is configured; access is verified per component.", {}

    async def _test_email(self) -> tuple[bool, str, dict[str, Any]]:
        if self.settings.email_mode.value == "simulated":
            return True, "Email is simulated; messages appear in the outbox instead of being sent.", {"mode": "simulated"}
        if self.settings.email_mode.value == "smtp" and not self.settings.smtp_host:
            return False, "SMTP is selected but no host is configured.", {}
        return True, f"Email is configured with sender {self.settings.email_from_address}.", {"mode": self.settings.email_mode.value}

    # ── Usage ────────────────────────────────────────────────────────────────────────────────────────────────────────
    async def get_usage(self, period_start: datetime | None, period_end: datetime | None, group_by: str) -> UsageResponse:
        if group_by not in ("day", "application", "feature"):
            raise BusinessValidationException("groupBy must be day, application or feature.")
        end = period_end or utc_now()
        start = period_start or end - timedelta(days=14)
        rows = (await self.session.execute(select(
            LlmUsageRecord.created_at, LlmUsageRecord.application_id, LlmUsageRecord.feature_name, LlmUsageRecord.input_token_count, LlmUsageRecord.output_token_count, LlmUsageRecord.outcome_status).where(
            LlmUsageRecord.created_at >= start, LlmUsageRecord.created_at <= end))).all()
        application_names = {item.application_id: item.application_name for item in (await self.session.scalars(select(Application))).all()}
        totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        labels: dict[str, str] = {}
        failed = 0
        for created_at, application_id, feature_name, input_tokens, output_tokens, outcome in rows:
            key = created_at.strftime("%Y-%m-%d") if group_by == "day" else (application_id or "platform") if group_by == "application" else feature_name
            labels[key] = key if group_by != "application" else application_names.get(application_id or "", "Platform (no application)")
            bucket = totals[key]
            bucket[0] += 1
            bucket[1] += input_tokens or 0
            bucket[2] += output_tokens or 0
            failed += 1 if outcome == "failed" else 0
        buckets = [UsageBucketResponse(bucket_key=key, bucket_label=labels[key], call_count=calls, input_token_count=input_tokens, output_token_count=output_tokens,
                                       estimated_cost=self._estimate_cost(input_tokens, output_tokens)) for key, (calls, input_tokens, output_tokens) in sorted(totals.items())]
        if group_by != "day":
            buckets.sort(key=lambda bucket: -(bucket.input_token_count + bucket.output_token_count))
        investigation_tokens = (await self.session.execute(select(func.avg(Investigation.total_input_token_count + Investigation.total_output_token_count)).where(
            Investigation.created_at >= start, Investigation.created_at <= end, Investigation.total_input_token_count > 0))).scalar()
        total_input, total_output = sum(item.input_token_count for item in buckets), sum(item.output_token_count for item in buckets)
        return UsageResponse(
            period_start=start, period_end=end, group_by=group_by, buckets=buckets, total_call_count=sum(item.call_count for item in buckets), total_input_token_count=total_input,
            total_output_token_count=total_output, total_estimated_cost=self._estimate_cost(total_input, total_output),
            average_tokens_per_investigation=round(float(investigation_tokens), 0) if investigation_tokens else None, failed_call_count=failed)

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return round(input_tokens / 1_000_000 * self.settings.llm_price_per_million_input_tokens + output_tokens / 1_000_000 * self.settings.llm_price_per_million_output_tokens, 4)

    # ── Audit ────────────────────────────────────────────────────────────────────────────────────────────────────────
    async def list_audit_events(self, *, actor: str | None, action: str | None, application_id: str | None, period_start: datetime | None, period_end: datetime | None,
                                page: int, page_size: int) -> PagedResult[AuditEventResponse]:
        conditions = []
        if actor:
            conditions.append(AuditEvent.actor_user_principal_name.ilike(f"%{actor}%"))
        if action:
            conditions.append(AuditEvent.action_name.ilike(f"%{action}%"))
        if application_id:
            conditions.append(AuditEvent.application_id == application_id)
        if period_start:
            conditions.append(AuditEvent.occurred_at >= period_start)
        if period_end:
            conditions.append(AuditEvent.occurred_at <= period_end)
        bounded_size, bounded_page = max(1, min(page_size, 200)), max(1, page)
        total = await self.session.scalar(select(func.count()).select_from(AuditEvent).where(*conditions)) or 0
        events = (await self.session.scalars(select(AuditEvent).where(*conditions).order_by(AuditEvent.occurred_at.desc()).offset((bounded_page - 1) * bounded_size).limit(bounded_size))).all()
        return PagedResult(items=[AuditEventResponse(
            audit_event_id=item.audit_event_id, actor_user_principal_name=item.actor_user_principal_name, action_name=item.action_name, target_entity_type=item.target_entity_type,
            target_entity_id=item.target_entity_id, application_id=item.application_id, action_details=item.action_details_json, occurred_at=item.occurred_at) for item in events],
            total_count=total, page=bounded_page, page_size=bounded_size)

    # ── Jobs ─────────────────────────────────────────────────────────────────────────────────────────────────────────
    async def get_job_stats(self) -> JobStatsResponse:
        by_status = dict((await self.session.execute(select(BackgroundJob.job_status, func.count()).group_by(BackgroundJob.job_status))).all())
        by_type = dict((await self.session.execute(select(BackgroundJob.job_type, func.count()).group_by(BackgroundJob.job_type))).all())
        dead = (await self.session.scalars(select(BackgroundJob).where(BackgroundJob.job_status == "dead_lettered").order_by(BackgroundJob.created_at.desc()).limit(50))).all()
        recent = (await self.session.scalars(select(BackgroundJob).order_by(BackgroundJob.created_at.desc()).limit(25))).all()
        return JobStatsResponse(counts_by_status=by_status, counts_by_type=by_type, dead_letters=[self._to_job(item) for item in dead], recent_jobs=[self._to_job(item) for item in recent])

    async def retry_job(self, current_user: CurrentUser, job_id: str) -> JobResponse:
        job = await self.session.get(BackgroundJob, job_id)
        if job is None:
            raise NotFoundException("That job does not exist.")
        if job.job_status not in ("dead_lettered", "failed"):
            raise BusinessValidationException("Only failed or dead-lettered jobs can be retried.")
        job.job_status, job.attempt_count, job.available_at, job.last_error_message, job.finished_at = "queued", 0, utc_now(), None, None
        await AuditService(self.session).record(current_user, "administration.job_retry", target_entity_type="background_job", target_entity_id=job_id, action_details={"jobType": job.job_type})
        return self._to_job(job)

    @staticmethod
    def _to_job(job: BackgroundJob) -> JobResponse:
        return JobResponse(job_id=job.background_job_id, job_type=job.job_type, job_status=job.job_status, attempt_count=job.attempt_count, maximum_attempt_count=job.maximum_attempt_count,
                           last_error_message=job.last_error_message, created_at=job.created_at, finished_at=job.finished_at)

    # ── Simulation ───────────────────────────────────────────────────────────────────────────────────────────────────
    def list_simulation_scenarios(self) -> list[SimulationScenarioResponse]:
        SimulationService.ensure_simulation_allowed()
        return [SimulationScenarioResponse(scenario_key=item["scenarioKey"], title=item["title"], category=item["category"], service_types=item["serviceTypes"]) for item in SimulationService.list_scenarios()]

    async def trigger_simulation_scenario(self, current_user: CurrentUser, scenario_key: str, application_id: str) -> dict[str, Any]:
        SimulationService.ensure_simulation_allowed()
        result = await SimulationService(self.session).trigger_scenario(application_id, scenario_key)
        await AuditService(self.session).record(current_user, "administration.simulation_trigger", target_entity_type="application", target_entity_id=application_id, application_id=application_id, action_details={"scenarioKey": scenario_key})
        return result

    # ── Retention job handler (see workers/job_handlers.py) ──────────────────────────────────────────────────────────
    async def run_retention_cleanup(self) -> dict[str, Any] | None:
        now = utc_now()
        incident_cutoff = now - timedelta(days=self.settings.incident_retention_days)
        removed: dict[str, int] = {}

        async def purge(label: str, statement: Any) -> None:
            removed[label] = (await self.session.execute(statement)).rowcount or 0

        await purge("alertEvents", delete(AlertEvent).where(AlertEvent.received_at < now - timedelta(days=self.settings.raw_alert_retention_days)))
        await purge("sliMeasurements", delete(SliMeasurement).where(SliMeasurement.measurement_window_start < now - timedelta(days=self.settings.sli_raw_retention_days)))
        old_alert_ids = select(Alert.alert_id).where(Alert.last_seen_at < incident_cutoff, Alert.resolved_at.is_not(None))
        await purge("alertDecisions", delete(AlertDecision).where(AlertDecision.alert_id.in_(old_alert_ids)))
        await purge("alerts", delete(Alert).where(Alert.last_seen_at < incident_cutoff, Alert.resolved_at.is_not(None)))
        await purge("alertGroups", delete(AlertGroup).where(AlertGroup.group_status == "resolved", AlertGroup.last_activity_at < incident_cutoff))
        removed.update(await purge_expired_incidents(self.session, incident_cutoff, get_worker_settings().retention_delete_batch_size))
        await purge("finishedJobs", delete(BackgroundJob).where(BackgroundJob.job_status.in_(("succeeded", "completed", "cancelled")), BackgroundJob.finished_at < now - timedelta(days=RETENTION_FINISHED_JOB_DAYS)))
        await purge("auditEvents", delete(AuditEvent).where(AuditEvent.occurred_at < now - timedelta(days=RETENTION_AUDIT_AND_USAGE_DAYS)))
        await purge("llmUsageRecords", delete(LlmUsageRecord).where(LlmUsageRecord.created_at < now - timedelta(days=RETENTION_AUDIT_AND_USAGE_DAYS)))
        logger.info("Retention cleanup removed %s", removed)
        return removed
