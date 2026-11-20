"""SLI proposals (sample plan 7.2 and 7.3): measure 30 days, gate on data, propose realistic targets, accept in one click."""

from __future__ import annotations

import logging
import math
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.dtos.slo_dtos import AcceptProposalsRequest, AcceptProposalsResponse, ServiceProposalGroup, SliProposalResponse, SloProposalsResponse, SupportingSignalResponse
from keigan.entities.application_entities import MonitoredService, ServiceLogSource
from keigan.entities.platform_entities import PlatformSetting
from keigan.entities.slo_entities import ServiceLevelIndicator, ServiceLevelObjective
from keigan.security.current_user import CurrentUser
from keigan.services import alert_rules
from keigan.services.audit_service import AuditService
from keigan.services.sli_measurement_reader import SliMeasurementReader, SliSample, catalog_entries_for_service
from keigan.utils.statistics_utils import error_budget_minutes, propose_availability_target, propose_latency_threshold_milliseconds
from keigan.workers.job_queue import JobQueue

logger = logging.getLogger(__name__)
MINIMUM_EVENT_COUNT = 1000
SOURCE_CHIPS = {"application_insights": "App Insights", "metrics": "Metrics", "log_query": "Log query", "synthetic_probe": "Synthetic probe", "status_page": "Status page"}
HEADLINE_SERVICE_TYPE_ORDER = ("api_management", "app_service", "function_app", "aks", "mainframe_subsystem", "saas_service", "batch_job_stream", "sql_database")
PROPOSAL_INTERVAL_MINUTES = 60


def budget_text(target_percentage: float, window_days: int) -> str:
    minutes = error_budget_minutes(target_percentage, window_days)
    return f"{minutes:.0f} min of failure per {window_days} days" if minutes >= 10 else f"{minutes:.1f} min of failure per {window_days} days"


class SliProposalService:
    def __init__(self, session: AsyncSession, reader: SliMeasurementReader | None = None):
        self.session = session
        self.reader = reader or SliMeasurementReader(session)

    @staticmethod
    def _setting_key(application_id: str) -> str:
        return f"slo_proposals:{application_id}"

    async def _save(self, application_id: str, document: dict[str, Any]) -> None:
        setting = await self.session.get(PlatformSetting, self._setting_key(application_id))
        if setting is None:
            self.session.add(PlatformSetting(setting_key=self._setting_key(application_id), setting_value_json=document, setting_description="SLI proposals measured from the last 30 days"))
        else:
            setting.setting_value_json = dict(document)
        await self.session.flush()

    async def request_measurement(self, application_id: str) -> str:
        await self._save(application_id, {"status": "measuring", "stage": "Reading metric definitions", "started_at": alert_rules.utc_now().isoformat(), "groups": []})
        return await JobQueue(self.session).enqueue("measure_sli_proposals", {"application_id": application_id}, deduplication_key=f"measure_sli:{application_id}", priority_number=30)

    # ── Measuring ──────────────────────────────────────────────────────────────
    async def measure(self, application_id: str) -> dict[str, Any]:
        started_at = alert_rules.utc_now()
        await self._save(application_id, {"status": "measuring", "stage": "Reading metric definitions", "started_at": started_at.isoformat(), "groups": []})
        try:
            services = list((await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id == application_id, MonitoredService.is_monitoring_enabled.is_(True)).order_by(MonitoredService.service_name))).all())
            groups = [await self._measure_service(service) for service in services]
            self._mark_headline(groups, services)
            document = {"status": "ready", "stage": "Calculating baselines", "started_at": started_at.isoformat(), "finished_at": alert_rules.utc_now().isoformat(), "groups": groups}
        except Exception:  # noqa: BLE001
            logger.exception("SLI measurement failed for %s", application_id)
            document = {"status": "failed", "error": "Keigan could not measure the last 30 days. Try again in a few minutes. If it keeps failing, ask a Keigan admin to check the worker logs for this application.", "started_at": started_at.isoformat(), "groups": []}
        await self._save(application_id, document)
        return {"status": document["status"], "services": len(document["groups"])}

    async def _measure_service(self, service: MonitoredService) -> dict[str, Any]:
        has_application_insights = bool(service.application_insights_resource_id or service.application_insights_role_name) or bool(
            await self.session.scalar(select(ServiceLogSource.service_log_source_id).where(ServiceLogSource.service_id == service.service_id, ServiceLogSource.source_kind == "application_insights").limit(1))
        )
        entries, supporting_signals = catalog_entries_for_service(service, has_application_insights)
        proposals = [await self._measure_entry(service, entry) for entry in entries]
        return {
            "service_id": service.service_id, "service_name": service.service_name, "service_type": service.service_type, "proposals": proposals,
            "supporting_signals": [{"signal_key": signal["key"], "signal_name": signal["name"], "description": signal.get("description")} for signal in supporting_signals],
        }

    async def _measure_entry(self, service: MonitoredService, entry: dict[str, Any]) -> dict[str, Any]:
        end = alert_rules.utc_now().replace(second=0, microsecond=0)
        start = end - timedelta(days=30)
        kind = entry["kind"]
        proposal: dict[str, Any] = {
            "proposal_key": f"{service.service_id}:{entry['key']}", "catalog_entry_key": entry["key"], "service_id": service.service_id, "service_name": service.service_name, "sli_name": entry["display_name"],
            "sli_kind": kind, "explanation": entry["explanation"], "source_chip": SOURCE_CHIPS.get(entry["source"], entry["source"]), "good_total_definition": entry.get("good_total_definition"),
            "is_enabled_by_default": bool(entry.get("default_enabled", True)), "is_available": True, "rolling_window_days": 30, "is_approximate": bool(entry.get("approximate", False)),
            "headline_candidate": bool(entry.get("headline_candidate", False)), "is_headline": False,
        }
        exposed_metrics = [(metric.get("name") if isinstance(metric, dict) else str(metric)).lower() for metric in (service.available_metrics_json or [])]
        if entry.get("source") == "metrics" and entry.get("metric_name") and exposed_metrics and entry["metric_name"].lower() not in exposed_metrics:
            return {**proposal, "is_available": False, "is_enabled_by_default": False, "disabled_reason": "Metric not exposed by this resource."}
        threshold: int | None = None
        try:
            if kind == "latency":
                p95 = await self.reader.read_latency_p95_milliseconds(service.service_id, service.service_type, start, end)
                if p95 is None:
                    return {**proposal, "is_available": False, "is_enabled_by_default": False, "disabled_reason": "No latency data in the last 30 days."}
                threshold = propose_latency_threshold_milliseconds(p95)
            samples = await self.reader.read_samples(service.service_id, sli_kind=kind, catalog_entry_key=entry["key"], start=start, end=end, interval_minutes=PROPOSAL_INTERVAL_MINUTES, latency_threshold_milliseconds=threshold)
        except Exception as read_error:  # noqa: BLE001
            logger.info("Proposal %s for %s unavailable: %s", entry["key"], service.service_name, read_error)
            return {**proposal, "is_available": False, "is_enabled_by_default": False, "disabled_reason": "Needs Application Insights linked or a readable source for this service."}
        total_events = sum(sample.total or 0 for sample in samples)
        good_events = sum(sample.good or 0 for sample in samples)
        if total_events == 0:
            return {**proposal, "is_available": False, "is_enabled_by_default": False, "disabled_reason": "No requests in the last 30 days."}
        measured = round(100 * good_events / total_events, 3)
        proposal.update({"measured_percentage": measured, "event_count": total_events, "sparkline": self._daily_sparkline(samples), "proposed_latency_threshold_milliseconds": threshold})
        if total_events < MINIMUM_EVENT_COUNT:
            return {**proposal, "disabled_reason": f"Only {total_events} events in 30 days (fewer than {MINIMUM_EVENT_COUNT:,}), so no target is proposed. Enter one manually.", "is_enabled_by_default": False}
        if kind == "latency":
            target = 95.0
            proposal["warning"] = None if measured >= 95.0 else f"Currently {measured:.1f} % of requests are faster than {threshold} ms. Set a target you intend to reach."
        else:
            proposed = propose_availability_target(measured)
            target = proposed if proposed is not None else 95.0
            proposal["warning"] = None if proposed is not None else "Currently below 95 %. Set a target you intend to reach."
        proposal.update({"proposed_target_percentage": target, "error_budget_minutes": round(error_budget_minutes(target, 30), 1), "error_budget_text": budget_text(target, 30)})
        return proposal

    @staticmethod
    def _daily_sparkline(samples: list[SliSample]) -> list[float]:
        buckets: dict[str, list[int]] = {}
        for sample in samples:
            if sample.total:
                bucket = buckets.setdefault(sample.window_start.strftime("%Y-%m-%d"), [0, 0])
                bucket[0] += sample.good or 0
                bucket[1] += sample.total
        return [round(100 * good / total, 3) for _, (good, total) in sorted(buckets.items()) if total]

    @staticmethod
    def _mark_headline(groups: list[dict[str, Any]], services: list[MonitoredService]) -> None:
        for service_type in HEADLINE_SERVICE_TYPE_ORDER:
            for group in groups:
                if group["service_type"] != service_type:
                    continue
                candidate = next((item for item in group["proposals"] if item["is_available"] and item.get("proposed_target_percentage") and item["sli_kind"] in ("availability", "run_success") and item["headline_candidate"]), None)
                if candidate:
                    candidate["is_headline"] = True
                    return

    # ── Read ───────────────────────────────────────────────────────────────────
    async def get_proposals(self, application_id: str) -> SloProposalsResponse:
        setting = await self.session.get(PlatformSetting, self._setting_key(application_id))
        document = (setting.setting_value_json if setting else None) or {}
        if not document:
            return SloProposalsResponse(application_id=application_id, measurement_status="not_started")
        accepted_keys = {
            f"{sli.service_id}:{sli.catalog_entry_key}" for sli in (await self.session.scalars(select(ServiceLevelIndicator).where(ServiceLevelIndicator.application_id == application_id))).all()
        }
        groups: list[ServiceProposalGroup] = []
        for raw_group in document.get("groups", []):
            proposals = [SliProposalResponse.model_validate({**{key: value for key, value in raw.items() if key != "headline_candidate"}, "already_accepted": raw["proposal_key"] in accepted_keys}) for raw in raw_group["proposals"]]
            groups.append(ServiceProposalGroup(
                service_id=raw_group["service_id"], service_name=raw_group["service_name"], service_type=raw_group["service_type"], proposals=proposals,
                supporting_signals=[SupportingSignalResponse.model_validate(signal) for signal in raw_group.get("supporting_signals", [])],
            ))
        all_proposals = [proposal for group in groups for proposal in group.proposals]
        return SloProposalsResponse(
            application_id=application_id, measurement_status=document.get("status", "not_started"), progress_stage=document.get("stage"), started_at=alert_rules.parse_timestamp(document.get("started_at")),
            finished_at=alert_rules.parse_timestamp(document.get("finished_at")), error_message=document.get("error"),
            suggested_slo_count=sum(1 for proposal in all_proposals if proposal.is_available and proposal.is_enabled_by_default and proposal.proposed_target_percentage is not None),
            service_count=len({proposal.service_id for proposal in all_proposals if proposal.is_available and proposal.is_enabled_by_default}),
            headline_proposal=next((proposal for proposal in all_proposals if proposal.is_headline), None), groups=groups,
        )

    # ── Accept ─────────────────────────────────────────────────────────────────
    async def accept(self, current_user: CurrentUser | str, application_id: str, request: AcceptProposalsRequest, *, enqueue_backfill: bool = True) -> tuple[AcceptProposalsResponse, list[str]]:
        """Create SLIs and SLOs for the accepted proposals plus the supporting signals of those services. Returns the response and the new SLI ids."""
        setting = await self.session.get(PlatformSetting, self._setting_key(application_id))
        groups = ((setting.setting_value_json if setting else None) or {}).get("groups", [])
        by_key = {proposal["proposal_key"]: (group, proposal) for group in groups for proposal in group["proposals"]}
        existing_slis = {f"{sli.service_id}:{sli.catalog_entry_key}": sli for sli in (await self.session.scalars(select(ServiceLevelIndicator).where(ServiceLevelIndicator.application_id == application_id))).all()}
        actor = current_user.user_principal_name if hasattr(current_user, "user_principal_name") else str(current_user)
        new_sli_ids: list[str] = []
        created_slos = 0
        services_with_slo: set[str] = set()
        for accepted in request.accepted_proposals:
            key = f"{accepted.service_id}:{accepted.catalog_entry_key}"
            group_and_proposal = by_key.get(key)
            if group_and_proposal is None:
                continue
            _, proposal = group_and_proposal
            sli = existing_slis.get(key)
            if sli is None:
                sli = ServiceLevelIndicator(
                    application_id=application_id, service_id=accepted.service_id, catalog_entry_key=accepted.catalog_entry_key, sli_name=f"{proposal['service_name']}: {proposal['sli_name']}", sli_kind=proposal["sli_kind"],
                    data_source_kind={"App Insights": "application_insights", "Metrics": "metrics", "Synthetic probe": "synthetic_probe", "Status page": "status_page"}.get(proposal["source_chip"], "log_query"),
                    query_definition_json={"catalogEntryKey": accepted.catalog_entry_key}, latency_threshold_milliseconds=accepted.latency_threshold_milliseconds or proposal.get("proposed_latency_threshold_milliseconds"),
                    is_approximate=proposal.get("is_approximate", False), is_headline=bool(proposal.get("is_headline")),
                    measured_baseline_json={"measuredPercentage": proposal.get("measured_percentage"), "eventCount": proposal.get("event_count"), "measuredAt": alert_rules.utc_now().isoformat()},
                    created_by_user_principal_name=actor, updated_by_user_principal_name=actor,
                )
                self.session.add(sli)
                await self.session.flush()
                existing_slis[key] = sli
                new_sli_ids.append(sli.sli_id)
            elif accepted.latency_threshold_milliseconds:
                sli.latency_threshold_milliseconds = accepted.latency_threshold_milliseconds
            slo = await self.session.scalar(select(ServiceLevelObjective).where(ServiceLevelObjective.sli_id == sli.sli_id).limit(1))
            if slo is None:
                self.session.add(ServiceLevelObjective(sli_id=sli.sli_id, application_id=application_id, target_percentage=accepted.target_percentage, rolling_window_days=accepted.rolling_window_days,
                                                       burn_rate_policy_json={"page": {"burnRate": 14.4, "longWindow": "PT1H", "shortWindow": "PT5M"}, "ticket": {"burnRate": 6, "longWindow": "PT6H", "shortWindow": "PT30M"}},
                                                       created_by_user_principal_name=actor, updated_by_user_principal_name=actor))
                created_slos += 1
            else:
                slo.target_percentage, slo.rolling_window_days = accepted.target_percentage, accepted.rolling_window_days
            services_with_slo.add(accepted.service_id)
        for group in groups:
            if group["service_id"] not in services_with_slo:
                continue
            for signal in group.get("supporting_signals", []):
                key = f"{group['service_id']}:{signal['signal_key']}"
                if key not in existing_slis:
                    supporting = ServiceLevelIndicator(
                        application_id=application_id, service_id=group["service_id"], catalog_entry_key=signal["signal_key"], sli_name=f"{group['service_name']}: {signal['signal_name']}", sli_kind="supporting_signal",
                        data_source_kind="metrics", query_definition_json={"catalogEntryKey": signal["signal_key"]}, created_by_user_principal_name=actor, updated_by_user_principal_name=actor,
                    )
                    self.session.add(supporting)
                    await self.session.flush()
                    existing_slis[key] = supporting
                    new_sli_ids.append(supporting.sli_id)
        await self.session.flush()
        job_ids = [await JobQueue(self.session).enqueue("backfill_sli", {"sli_id": sli_id}, deduplication_key=f"backfill_sli:{sli_id}", priority_number=40) for sli_id in new_sli_ids] if enqueue_backfill else []
        await AuditService(self.session).record(current_user, "slo.accept_proposals", target_entity_type="application", target_entity_id=application_id, application_id=application_id, action_details={"accepted": len(request.accepted_proposals)})
        return AcceptProposalsResponse(accepted_count=len(request.accepted_proposals), created_sli_count=len(new_sli_ids), created_slo_count=created_slos, backfill_job_ids=job_ids), new_sli_ids

    def suggested_acceptance(self, proposals: SloProposalsResponse) -> AcceptProposalsRequest | None:
        """'Accept suggested': every available proposal that is on by default."""
        from keigan.dtos.slo_dtos import AcceptedProposal

        accepted = [AcceptedProposal(catalog_entry_key=proposal.catalog_entry_key, service_id=proposal.service_id, target_percentage=proposal.proposed_target_percentage, rolling_window_days=30,
                                     latency_threshold_milliseconds=proposal.proposed_latency_threshold_milliseconds)
                    for group in proposals.groups for proposal in group.proposals if proposal.is_available and proposal.is_enabled_by_default and proposal.proposed_target_percentage is not None]
        return AcceptProposalsRequest(accepted_proposals=accepted) if accepted else None


_ = math
