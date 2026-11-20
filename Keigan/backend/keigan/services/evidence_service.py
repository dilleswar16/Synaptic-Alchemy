"""Deterministic evidence collection for investigations (doc 06 section 3.3).

For every candidate service and its log sources, runs the query templates from ``query_templates.yaml`` over the
investigation window and the baseline window, masks PII, condenses log lines into patterns, diffs against the
baseline, scores the signal strength and ranks / trims the result to the token budget. Empty results are kept
as rule-outs. The AI never decides *what was found*; it only interprets this evidence.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import string
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.llm_gateway import estimate_token_count
from keigan.ai.prompt_safety import assess_prompt_injection
from keigan.config import application_context
from keigan.config.settings import RESOURCES_DIRECTORY, get_settings
from keigan.entities.application_entities import ApplicationComponent, LogToolConnection, MonitoredService, ServiceLogSource
from keigan.entities.incident_entities import InvestigationEvidence
from keigan.exceptions.keigan_exceptions import ReaderNotAvailableException
from keigan.integrations.telemetry_gateway import ChangeEvent, LogQueryResult, TelemetryQuery, TelemetryTarget
from keigan.utils.log_condenser import LEVEL_SEVERITY_ORDER, LogPattern, condense_log_records
from keigan.utils.pii_masker import MaskingContext, PiiMasker
from keigan.utils.query_safety import QueryRejectedError, describe_query_limits, validate_generated_query
from keigan.utils.statistics_utils import robust_baseline
from keigan.utils.text_utils import truncate_text
from keigan.entities.status_values import CriticalityTier, RiskLevel

logger = logging.getLogger(__name__)

QUERY_TEMPLATES_PATH = RESOURCES_DIRECTORY / "catalogs" / "query_templates.yaml"
MAXIMUM_TEMPLATES_PER_SERVICE = 7
MAXIMUM_CONCURRENT_QUERIES = 4
STRENGTH_RANK = {RiskLevel.HIGH: 0, RiskLevel.MEDIUM: 1, RiskLevel.LOW: 2}
DISCRETE_EVENT_CATEGORIES = {"kubernetes_events", "pod_restarts", "batch_failures", "hardware_status", "synthetic_probe", "change_event"}
CRITICALITY_RANK = {CriticalityTier.TIER_1: 0, CriticalityTier.TIER_2: 1, CriticalityTier.TIER_3: 2}
SAFE_VARIABLE_PATTERN = re.compile(r"[^A-Za-z0-9_.\-/ ]")


@dataclass
class EvidenceDraft:
    """One evidence item before ranking and code assignment."""

    service_id: str | None
    service_name: str
    source_kind: str
    evidence_category: str
    evidence_title: str
    evidence_summary: str
    query_language: str = "none"
    query_text: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    matched_record_count: int = 0
    baseline_record_count: int | None = None
    condensed_patterns: list[dict[str, Any]] = field(default_factory=list)
    metric_series: list[dict[str, Any]] = field(default_factory=list)
    signal_strength: str = RiskLevel.LOW
    masked_value_count: int = 0
    possible_prompt_injection: bool = False
    deep_link_url: str | None = None
    criticality_tier: str = CriticalityTier.TIER_2
    latest_activity_at: datetime | None = None
    is_rule_out: bool = False

    def ranking_key(self) -> tuple[int, int, int, float]:
        recency = -(self.latest_activity_at.timestamp()) if self.latest_activity_at else 0.0
        return (STRENGTH_RANK[self.signal_strength], 1 if self.is_rule_out else 0, CRITICALITY_RANK.get(self.criticality_tier, 1), recency)


@dataclass
class ServiceTelemetryContext:
    service: MonitoredService
    component: ApplicationComponent | None
    log_sources: list[ServiceLogSource]
    log_tool_connections_by_id: dict[str, LogToolConnection]

    def target_for(self, log_source: ServiceLogSource | None) -> TelemetryTarget:
        connection = self.log_tool_connections_by_id.get(log_source.log_tool_connection_id) if log_source and log_source.log_tool_connection_id else None
        return TelemetryTarget.from_entities(self.service, log_source, self.component, connection)


@lru_cache
def load_query_templates() -> list[dict[str, Any]]:
    return list(yaml.safe_load(QUERY_TEMPLATES_PATH.read_text(encoding="utf-8")).get("templates", []))


def _sanitize_variable(variable_value: str | None) -> str:
    return SAFE_VARIABLE_PATTERN.sub("", variable_value or "")[:120]


class EvidenceService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.telemetry_gateway = application_context.telemetry_gateway()

    # ── Collection ─────────────────────────────────────────────────────────────
    async def load_service_contexts(self, services: list[MonitoredService]) -> list[ServiceTelemetryContext]:
        service_ids = [service.service_id for service in services]
        log_sources = list((await self.session.scalars(select(ServiceLogSource).where(ServiceLogSource.service_id.in_(service_ids)))).all()) if service_ids else []
        component_ids = {service.component_id for service in services if service.component_id}
        components = {
            component.component_id: component
            for component in (await self.session.scalars(select(ApplicationComponent).where(ApplicationComponent.component_id.in_(component_ids)))).all()
        } if component_ids else {}
        connection_ids = {log_source.log_tool_connection_id for log_source in log_sources if log_source.log_tool_connection_id}
        connections = {
            connection.log_tool_connection_id: connection
            for connection in (await self.session.scalars(select(LogToolConnection).where(LogToolConnection.log_tool_connection_id.in_(connection_ids)))).all()
        } if connection_ids else {}
        return [
            ServiceTelemetryContext(
                service, components.get(service.component_id or ""), [source for source in log_sources if source.service_id == service.service_id], connections
            )
            for service in services
        ]

    async def collect_evidence(
        self,
        service_contexts: list[ServiceTelemetryContext],
        window_start: datetime,
        window_end: datetime,
        baseline_start: datetime,
        baseline_end: datetime,
        masking_context: MaskingContext,
    ) -> list[EvidenceDraft]:
        concurrency_limiter = asyncio.Semaphore(MAXIMUM_CONCURRENT_QUERIES)

        async def run_limited(service_context: ServiceTelemetryContext, log_source: ServiceLogSource, template: dict[str, Any]) -> EvidenceDraft:
            async with concurrency_limiter:
                return await self._run_template(service_context, log_source, template, window_start, window_end, baseline_start, baseline_end, masking_context)

        pending_runs = []
        for service_context in service_contexts:
            selected_runs = self._select_templates(service_context)
            pending_runs.extend(run_limited(service_context, log_source, template) for log_source, template in selected_runs)
        return list(await asyncio.gather(*pending_runs))

    def _select_templates(self, service_context: ServiceTelemetryContext) -> list[tuple[ServiceLogSource, dict[str, Any]]]:
        selected: list[tuple[ServiceLogSource, dict[str, Any]]] = []
        for log_source in service_context.log_sources:
            connection = service_context.log_tool_connections_by_id.get(log_source.log_tool_connection_id or "")
            for template in load_query_templates():
                if service_context.service.service_type not in template["service_types"] or log_source.source_kind not in template["source_kinds"]:
                    continue
                if log_source.source_kind == "log_tool":
                    tool_types = template.get("tool_types", ["*"])
                    tool_type = connection.tool_type if connection else ""
                    is_specific_match = tool_type in tool_types
                    is_wildcard_match = "*" in tool_types and tool_type not in ("elastic", "splunk", "datadog")
                    if not (is_specific_match or is_wildcard_match):
                        continue
                selected.append((log_source, template))
        return selected[:MAXIMUM_TEMPLATES_PER_SERVICE]

    def _template_variables(self, service_context: ServiceTelemetryContext, log_source: ServiceLogSource) -> dict[str, str]:
        service = service_context.service
        scope = log_source.query_scope_json or {}
        return {
            "service_name": _sanitize_variable(service.service_name),
            "namespace": _sanitize_variable(service.aks_namespace_filter or scope.get("namespace") or "default"),
            "role_name": _sanitize_variable(service.application_insights_role_name or service.service_name),
            "resource_id": _sanitize_variable(service.external_resource_identifier),
            "index_pattern": _sanitize_variable(scope.get("index") or scope.get("index_pattern") or "*"),
        }

    async def _run_template(
        self,
        service_context: ServiceTelemetryContext,
        log_source: ServiceLogSource,
        template: dict[str, Any],
        window_start: datetime,
        window_end: datetime,
        baseline_start: datetime,
        baseline_end: datetime,
        masking_context: MaskingContext,
    ) -> EvidenceDraft:
        service = service_context.service
        variables = self._template_variables(service_context, log_source)
        title = string.Template(template["title"]).safe_substitute(variables)
        query_text = string.Template(template.get("query_text", "")).safe_substitute(variables).strip()
        draft = EvidenceDraft(
            service_id=service.service_id, service_name=service.service_name, source_kind=log_source.source_kind,
            evidence_category=template["evidence_category"], evidence_title=f"{service.service_name}: {title}", evidence_summary="",
            query_language=template["query_language"], query_text=query_text or ", ".join(template.get("metric_names", [])),
            window_start=window_start, window_end=window_end, criticality_tier=service.criticality_tier,
        )
        target = service_context.target_for(log_source)
        try:
            if template["query_language"] == "metrics_api":
                await self._fill_metric_evidence(draft, target, template, window_start, window_end, baseline_start, baseline_end)
            elif template["query_language"] == "probe":
                await self._fill_probe_evidence(draft, target)
            else:
                await self._fill_log_evidence(draft, target, template, query_text, window_start, window_end, baseline_start, baseline_end, masking_context)
        except ReaderNotAvailableException as reader_error:
            draft.evidence_summary = f"Not available: {reader_error.detail}. Keigan cannot rule this source in or out."
            draft.is_rule_out = True
        except Exception as query_error:  # noqa: BLE001 — one failing query must not stop the investigation
            logger.warning("Evidence query %s for %s failed: %s", template["template_key"], service.service_name, query_error)
            draft.evidence_summary = f"The query could not be completed ({type(query_error).__name__}). This source is inconclusive."
            draft.is_rule_out = True
        return draft

    # ── Logs ───────────────────────────────────────────────────────────────────
    async def _fill_log_evidence(
        self, draft: EvidenceDraft, target: TelemetryTarget, template: dict[str, Any], query_text: str,
        window_start: datetime, window_end: datetime, baseline_start: datetime, baseline_end: datetime, masking_context: MaskingContext,
        baseline_query_text: str | None = None,
    ) -> None:
        """``baseline_query_text`` is for queries that carry their own time filter: the baseline must be filtered to the baseline window."""
        signal_kind = template["signal_kind"]

        def build_query(range_start: datetime, range_end: datetime, text: str) -> TelemetryQuery:
            return TelemetryQuery(template["query_language"], text, range_start, range_end, query_purpose=template["template_key"], purpose_parameters={"signal_kind": signal_kind})

        window_result, baseline_result = await asyncio.gather(
            self.telemetry_gateway.query_logs(target, build_query(window_start, window_end, query_text)),
            self.telemetry_gateway.query_logs(target, build_query(baseline_start, baseline_end, baseline_query_text or query_text)),
        )
        draft.deep_link_url = window_result.deep_link_url or self._portal_link(target)
        # Masking happens only in the synchronous part below, with no await in it, so no other query can count into the
        # shared masking context meanwhile: the difference is exactly the number of values masked for this evidence.
        masked_count_before = masking_context.masked_value_count
        self._summarize_log_results(draft, signal_kind, PiiMasker(masking_context), window_result, baseline_result)
        draft.masked_value_count = masking_context.masked_value_count - masked_count_before

    def _summarize_log_results(self, draft: EvidenceDraft, signal_kind: str, masker: PiiMasker, window_result: LogQueryResult, baseline_result: LogQueryResult) -> None:
        window_rows = masker.mask_rows(window_result.rows)
        baseline_rows = masker.mask_rows(baseline_result.rows)
        if signal_kind == "slow_requests":
            self._summarize_slow_requests(draft, window_rows, baseline_rows)
            return
        window_records = self._prepare_log_records(signal_kind, window_rows)
        baseline_records = self._expand_by_count(self._prepare_log_records(signal_kind, baseline_rows))
        condensed = condense_log_records(window_records, baseline_records)
        draft.matched_record_count = sum(self._record_weight(record) for record in window_records)
        draft.baseline_record_count = len(baseline_records)
        draft.condensed_patterns = [self._neutralized_pattern(log_pattern, draft) for log_pattern in condensed.patterns]
        draft.latest_activity_at = max((log_pattern.last_seen_at for log_pattern in condensed.patterns if log_pattern.last_seen_at), default=None)
        draft.signal_strength = self._signal_strength(condensed.patterns, draft.evidence_category)
        draft.evidence_summary = self._describe_patterns(draft, condensed.patterns)
        draft.is_rule_out = draft.matched_record_count == 0

    @staticmethod
    def _record_weight(record: dict[str, Any]) -> int:
        count_value = record.get("count_")
        return int(count_value) if isinstance(count_value, (int, float)) and count_value >= 1 else 1

    @staticmethod
    def _expand_by_count(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        expanded: list[dict[str, Any]] = []
        for record in records:
            expanded.extend([record] * min(EvidenceService._record_weight(record), 1000))
        return expanded

    @staticmethod
    def _prepare_log_records(signal_kind: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Give aggregated rows a readable Message and Level so condensing produces meaningful patterns."""
        prepared: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            if signal_kind == "failed_requests":
                record.update(Message=f"HTTP {row.get('ResultCode', '5xx')} on {row.get('OperationName', 'unknown operation')}", Level="error")
            elif signal_kind == "exceptions":
                record.update(Message=f"{row.get('ExceptionType', 'Exception')}: {row.get('OuterMessage', '')}", Level="error")
            elif signal_kind == "failed_dependencies":
                record.update(Message=f"Call to dependency {row.get('Target', '?')} ({row.get('DependencyType') or row.get('Type', 'unknown')}) failed with {row.get('ResultCode', 'error')}", Level="error")
            elif signal_kind == "kube_events":
                record.update(Message=f"{row.get('Reason', 'Warning')}: {row.get('Message', row.get('Name', ''))}", Level="warning")
            elif signal_kind == "pod_restarts":
                if not row.get("RestartCount"):
                    continue
                record.update(Message=f"Container restarts observed on pod {row.get('PodName', '?')}", Level="warning", count_=row["RestartCount"])
            prepared.append(record)
        return prepared

    @staticmethod
    def _signal_strength(log_patterns: list[LogPattern], evidence_category: str) -> str:
        high_minimum_count = 5 if evidence_category in DISCRETE_EVENT_CATEGORIES else 20
        strongest = RiskLevel.LOW
        for log_pattern in log_patterns:
            if LEVEL_SEVERITY_ORDER.get(log_pattern.level.lower(), 3) > 2:
                continue
            change_ratio = log_pattern.change_ratio or 0
            if (log_pattern.is_new_pattern or change_ratio >= 5) and log_pattern.count >= high_minimum_count:
                return RiskLevel.HIGH
            if (log_pattern.is_new_pattern and log_pattern.count >= 3) or (change_ratio >= 2 and log_pattern.count >= 5):
                strongest = RiskLevel.MEDIUM
        return strongest

    def _neutralized_pattern(self, log_pattern: LogPattern, draft: EvidenceDraft) -> dict[str, Any]:
        pattern_dictionary = log_pattern.to_dictionary()
        safe_samples: list[str] = []
        for sample_line in pattern_dictionary["sampleLinesMasked"]:
            if assess_prompt_injection(sample_line).is_suspicious:
                draft.possible_prompt_injection = True
                sample_line = f'[possible prompt injection, quoted as data] "{truncate_text(sample_line, 120)}"'
            safe_samples.append(truncate_text(sample_line, 300))
        pattern_dictionary["sampleLinesMasked"] = safe_samples
        if assess_prompt_injection(pattern_dictionary["template"]).is_suspicious:
            draft.possible_prompt_injection = True
            pattern_dictionary["template"] = f'[possible prompt injection, quoted as data] "{truncate_text(pattern_dictionary["template"], 120)}"'
        return pattern_dictionary

    @staticmethod
    def _describe_patterns(draft: EvidenceDraft, log_patterns: list[LogPattern]) -> str:
        if draft.matched_record_count == 0:
            return f"Rule-out: no matching events for {draft.service_name} in the investigation window (baseline: {draft.baseline_record_count or 0})."
        top_pattern = log_patterns[0]
        trend_text = "new compared with the baseline" if top_pattern.is_new_pattern else f"x{top_pattern.change_ratio} versus the baseline" if top_pattern.change_ratio else "similar to the baseline"
        return (
            f"{draft.matched_record_count} matching events (baseline window: {draft.baseline_record_count or 0}). "
            f"Top pattern: \"{truncate_text(top_pattern.template, 160)}\" occurred {top_pattern.count} times, {trend_text}."
        )

    @staticmethod
    def _summarize_slow_requests(draft: EvidenceDraft, window_rows: list[dict[str, Any]], baseline_rows: list[dict[str, Any]]) -> None:
        baseline_by_operation = {row.get("OperationName"): float(row.get("P95DurationMs", 0) or 0) for row in baseline_rows}
        patterns: list[dict[str, Any]] = []
        strongest = RiskLevel.LOW
        for row in sorted(window_rows, key=lambda candidate: -float(candidate.get("P95DurationMs", 0) or 0))[:8]:
            current_p95 = float(row.get("P95DurationMs", 0) or 0)
            baseline_p95 = baseline_by_operation.get(row.get("OperationName"), 0.0)
            ratio = round(current_p95 / baseline_p95, 2) if baseline_p95 else None
            if ratio and ratio >= 3:
                strongest = RiskLevel.HIGH
            elif ratio and ratio >= 1.6 and strongest != RiskLevel.HIGH:
                strongest = RiskLevel.MEDIUM
            patterns.append(
                {
                    "template": f"{row.get('OperationName')}: p95 duration {current_p95:.0f} ms (baseline {baseline_p95:.0f} ms)", "level": "warning",
                    "count": int(row.get("RequestCount", 0) or 0), "baselineCount": 0, "firstSeenAt": None, "lastSeenAt": None,
                    "isNewPattern": False, "changeRatio": ratio, "sampleLinesMasked": [], "topDimensionValues": {},
                }
            )
        draft.condensed_patterns = patterns
        draft.matched_record_count = sum(pattern["count"] for pattern in patterns)
        draft.signal_strength = strongest
        draft.evidence_summary = (
            f"Slowest operation {patterns[0]['template']}." if patterns and strongest != RiskLevel.LOW else "Rule-out: request latency is in line with the baseline."
        )
        draft.is_rule_out = strongest == RiskLevel.LOW

    @staticmethod
    def _portal_link(target: TelemetryTarget) -> str | None:
        return f"https://portal.azure.com/#@/resource{target.azure_resource_id}/overview" if target.azure_resource_id and target.azure_resource_id.startswith("/subscriptions/") else None

    # ── Metrics and probes ─────────────────────────────────────────────────────
    async def _fill_metric_evidence(
        self, draft: EvidenceDraft, target: TelemetryTarget, template: dict[str, Any],
        window_start: datetime, window_end: datetime, baseline_start: datetime, baseline_end: datetime,
    ) -> None:
        metric_names = list(template["metric_names"])
        window_result, baseline_result = await asyncio.gather(
            self.telemetry_gateway.query_metrics(target, metric_names, window_start, window_end, 5),
            self.telemetry_gateway.query_metrics(target, metric_names, baseline_start, baseline_end, 5),
        )
        baseline_series_by_name = {series.metric_name: series for series in baseline_result.series}
        series_summaries: list[dict[str, Any]] = []
        descriptions: list[str] = []
        strongest = RiskLevel.LOW
        for series in window_result.series:
            window_values = [value for _, value in series.points if value is not None]
            if not window_values:
                continue
            baseline_values = [value for _, value in baseline_series_by_name.get(series.metric_name, series).points if value is not None] if series.metric_name in baseline_series_by_name else []
            baseline_statistics = robust_baseline(baseline_values)
            peak_value = max(window_values)
            peak_time = next(timestamp for timestamp, value in series.points if value == peak_value)
            baseline_median = baseline_statistics.median if baseline_statistics else 0.0
            z_score = min(99.0, baseline_statistics.robust_z_score(peak_value)) if baseline_statistics else 0.0
            ratio = peak_value / baseline_median if baseline_median else (99.0 if peak_value > 0 else 1.0)
            series_strength = RiskLevel.HIGH if z_score > 3 and ratio >= 1.3 else RiskLevel.MEDIUM if z_score > 2 and ratio >= 1.15 else RiskLevel.LOW
            if STRENGTH_RANK[series_strength] < STRENGTH_RANK[strongest]:
                strongest = series_strength
            step = max(1, len(series.points) // 48)
            series_summaries.append(
                {
                    "metricName": series.metric_name, "unit": series.unit, "baselineMedian": round(baseline_median, 2), "windowPeak": round(peak_value, 2),
                    "windowPeakAt": peak_time.isoformat(), "robustZScore": round(z_score, 1), "signalStrength": series_strength,
                    "points": [{"t": timestamp.isoformat(), "v": value} for timestamp, value in series.points[::step]],
                }
            )
            if series_strength != RiskLevel.LOW:
                descriptions.append(f"{series.metric_name} peaked at {peak_value:.1f} {series.unit.lower()} (baseline median {baseline_median:.1f}, robust z {z_score:.1f})")
        draft.metric_series = series_summaries
        draft.signal_strength = strongest
        draft.matched_record_count = len(series_summaries)
        draft.latest_activity_at = window_end if strongest != RiskLevel.LOW else None
        draft.evidence_summary = "; ".join(descriptions) + "." if descriptions else f"Rule-out: {', '.join(metric_names)} stayed within the baseline range."
        draft.is_rule_out = strongest == RiskLevel.LOW
        draft.deep_link_url = self._portal_link(target)

    async def _fill_probe_evidence(self, draft: EvidenceDraft, target: TelemetryTarget) -> None:
        probe_url = str(target.query_scope.get("probe_url", ""))
        probe_results = [await self.telemetry_gateway.probe_endpoint(probe_url, application_id=target.application_id, use_simulation=target.use_simulation) for _ in range(5)]
        failure_count = sum(1 for probe_result in probe_results if not probe_result.succeeded)
        draft.matched_record_count = len(probe_results)
        draft.condensed_patterns = [
            {
                "template": f"Synthetic probe {probe_result.message} after {probe_result.latency_milliseconds} ms", "level": "error" if not probe_result.succeeded else "information",
                "count": 1, "baselineCount": 0, "isNewPattern": not probe_result.succeeded, "changeRatio": None, "sampleLinesMasked": [], "topDimensionValues": {},
                "firstSeenAt": None, "lastSeenAt": None,
            }
            for probe_result in probe_results
            if not probe_result.succeeded
        ][:3]
        draft.signal_strength = RiskLevel.HIGH if failure_count >= 3 else RiskLevel.MEDIUM if failure_count else RiskLevel.LOW
        draft.evidence_summary = f"{failure_count} of {len(probe_results)} synthetic probes failed." if failure_count else "Rule-out: all synthetic probes succeeded."
        draft.is_rule_out = failure_count == 0

    # ── Changes ────────────────────────────────────────────────────────────────
    async def collect_change_evidence(self, application_id: str, service_contexts: list[ServiceTelemetryContext], start: datetime, end: datetime, masking_context: MaskingContext | None = None) -> tuple[list[ChangeEvent], EvidenceDraft | None]:
        """Returned events are already masked: Activity Log callers are people (UPNs, emails) and descriptions can quote them."""
        component = next((context.component for context in service_contexts if context.component), None)
        change_events: list[ChangeEvent] = []
        try:
            change_events = await self.telemetry_gateway.query_activity_changes(
                application_id,
                component.azure_tenant_id if component else None,
                component.azure_subscription_id if component else None,
                component.azure_resource_group_name if component else None,
                start, end, use_simulation=bool((component.component_configuration_json or {}).get("simulated")) if component else False,
            )
        except Exception as change_error:  # noqa: BLE001
            logger.warning("Could not read activity log changes: %s", change_error)
        masker = PiiMasker(masking_context)
        change_events = [
            replace(change_event, description=masker.mask_text(change_event.description), caller=masker.mask_text(change_event.caller) if change_event.caller else None)
            for change_event in change_events
        ]
        if not change_events:
            return [], EvidenceDraft(None, "Azure Activity Log", "activity_log", "change_event", "Recent changes: none found", "Rule-out: no deployments or configuration changes in the window or the 24 hours before.", is_rule_out=True)
        draft = EvidenceDraft(
            None, "Azure Activity Log", "activity_log", "change_event", "Recent deployments and configuration changes", "",
            window_start=start, window_end=end, matched_record_count=len(change_events), latest_activity_at=max(event.occurred_at for event in change_events),
        )
        draft.condensed_patterns = [
            {
                "template": change_event.description, "level": "change", "count": 1, "baselineCount": 0, "isNewPattern": True, "changeRatio": None,
                "firstSeenAt": change_event.occurred_at.isoformat(), "lastSeenAt": change_event.occurred_at.isoformat(),
                "sampleLinesMasked": [f"{change_event.operation_name} by {change_event.caller or 'unknown'}"], "topDimensionValues": {},
                "changeKind": change_event.change_kind, "caller": change_event.caller,
            }
            for change_event in change_events[-10:]
        ]
        non_routine = [event for event in change_events if "outine" not in event.description]
        draft.signal_strength = RiskLevel.HIGH if non_routine else RiskLevel.MEDIUM
        newest_event = max(change_events, key=lambda event: event.occurred_at)
        draft.evidence_summary = f"{len(change_events)} change(s) in the window and the 24 hours before. Most recent: {newest_event.description} at {newest_event.occurred_at.strftime('%Y-%m-%d %H:%M')} UTC."
        return change_events, draft

    # ── Planner-requested queries ──────────────────────────────────────────────
    async def run_planned_queries(
        self, planned_queries: list[Any], service_contexts: list[ServiceTelemetryContext], window_start: datetime, window_end: datetime,
        baseline_start: datetime, baseline_end: datetime, masking_context: MaskingContext,
    ) -> list[EvidenceDraft]:
        drafts: list[EvidenceDraft] = []
        for planned_query in planned_queries[:3]:
            service_context = next((context for context in service_contexts if context.service.service_name == planned_query.service_name), None)
            if service_context is None:
                continue
            language = planned_query.query_language
            matching_source = next((source for source in service_context.log_sources if self._source_supports_language(source, service_context, language)), None)
            if matching_source is None:
                continue
            try:
                # The planner's raw text is hardened once per window, so the baseline is filtered to the baseline window (not the incident window).
                hardened_query = validate_generated_query(language, planned_query.query_text, window_start, window_end, query_scope=matching_source.query_scope_json)
                hardened_baseline_query = validate_generated_query(language, planned_query.query_text, baseline_start, baseline_end, query_scope=matching_source.query_scope_json)
            except QueryRejectedError as rejection:
                logger.info("Planner query rejected: %s", rejection.detail)
                continue
            template = {
                "template_key": "planner_query", "query_language": language, "signal_kind": "generic", "evidence_category": "ai_planned_query",
                "title": f"AI-planned query: {truncate_text(planned_query.justification, 90)}", "service_types": [], "source_kinds": [],
            }
            draft = EvidenceDraft(
                service_context.service.service_id, service_context.service.service_name, matching_source.source_kind, "ai_planned_query",
                f"{service_context.service.service_name}: {template['title']}", "", language, hardened_query.query_text, window_start, window_end,
                criticality_tier=service_context.service.criticality_tier,
            )
            try:
                await self._fill_log_evidence(draft, service_context.target_for(matching_source), template, hardened_query.query_text, window_start, window_end, baseline_start, baseline_end, masking_context, hardened_baseline_query.query_text)
            except Exception as query_error:  # noqa: BLE001
                logger.info("Planner query failed: %s", query_error)
                continue
            drafts.append(draft)
        return drafts

    @staticmethod
    def _query_language_of(log_source: ServiceLogSource, service_context: ServiceTelemetryContext) -> str | None:
        """The language the planner may write for this log source, or None when Keigan cannot run generated queries on it."""
        if log_source.source_kind in ("log_analytics", "application_insights"):
            return "kql"
        connection = service_context.log_tool_connections_by_id.get(log_source.log_tool_connection_id or "")
        return {"elastic": "elastic_dsl", "splunk": "spl"}.get(connection.tool_type) if connection else None

    @staticmethod
    def _source_supports_language(log_source: ServiceLogSource, service_context: ServiceTelemetryContext, language: str) -> bool:
        return EvidenceService._query_language_of(log_source, service_context) == language

    @staticmethod
    def describe_query_limits_for_planner(service_contexts: list[ServiceTelemetryContext]) -> str:
        """JSON for the planner prompt: per service, each log source the planner can query, its language and what a query may use."""
        services: list[dict[str, Any]] = []
        for service_context in service_contexts:
            log_sources: list[dict[str, Any]] = []
            for log_source in service_context.log_sources:
                language = EvidenceService._query_language_of(log_source, service_context)
                if language is None:
                    continue
                connection = service_context.log_tool_connections_by_id.get(log_source.log_tool_connection_id or "")
                log_sources.append({"sourceKind": log_source.source_kind, **describe_query_limits(language, log_source.query_scope_json, connection.connection_configuration_json if connection else None)})
            services.append({"serviceName": service_context.service.service_name, "serviceType": service_context.service.service_type, "logSources": log_sources})
        return json.dumps(services)

    # ── Ranking and persistence ────────────────────────────────────────────────
    @staticmethod
    def rank_and_trim(drafts: list[EvidenceDraft], token_budget: int) -> list[EvidenceDraft]:
        ranked_drafts = sorted(drafts, key=EvidenceDraft.ranking_key)
        kept: list[EvidenceDraft] = []
        used_tokens = 0
        for draft in ranked_drafts:
            draft_tokens = estimate_token_count(EvidenceService.render_draft_markdown(draft, "E0"))
            if used_tokens + draft_tokens > token_budget and draft.signal_strength == RiskLevel.LOW:
                continue
            used_tokens += draft_tokens
            kept.append(draft)
        return kept

    async def persist_evidence(self, investigation_id: str, drafts: list[EvidenceDraft]) -> list[InvestigationEvidence]:
        evidence_rows: list[InvestigationEvidence] = []
        for evidence_number, draft in enumerate(drafts, start=1):
            evidence_row = InvestigationEvidence(
                investigation_id=investigation_id, evidence_code=f"E{evidence_number}", service_id=draft.service_id, evidence_source_kind=draft.source_kind,
                evidence_category=draft.evidence_category, evidence_title=draft.evidence_title[:300], evidence_summary=draft.evidence_summary,
                query_language=draft.query_language, query_text=draft.query_text, query_time_range_start=draft.window_start, query_time_range_end=draft.window_end,
                matched_record_count=draft.matched_record_count, baseline_record_count=draft.baseline_record_count,
                condensed_patterns_json=draft.condensed_patterns or None, metric_series_json=draft.metric_series or None, signal_strength=draft.signal_strength,
                masked_value_count=draft.masked_value_count, possible_prompt_injection=draft.possible_prompt_injection, deep_link_url=draft.deep_link_url,
            )
            self.session.add(evidence_row)
            evidence_rows.append(evidence_row)
        await self.session.flush()
        return evidence_rows

    # ── Rendering for prompts ──────────────────────────────────────────────────
    @staticmethod
    def render_draft_markdown(draft: EvidenceDraft, evidence_code: str) -> str:
        return EvidenceService._render_markdown(
            evidence_code, draft.evidence_title, draft.service_name, draft.signal_strength, draft.evidence_summary, draft.condensed_patterns, draft.metric_series, draft.is_rule_out
        )

    @staticmethod
    def render_evidence_markdown(evidence_rows: list[InvestigationEvidence], service_names_by_id: dict[str, str]) -> str:
        return "\n\n".join(
            EvidenceService._render_markdown(
                row.evidence_code, row.evidence_title, service_names_by_id.get(row.service_id or "", "platform"), row.signal_strength, row.evidence_summary or "",
                row.condensed_patterns_json or [], row.metric_series_json or [], row.matched_record_count == 0,
            )
            for row in evidence_rows
        )

    @staticmethod
    def _render_markdown(code: str, title: str, service_name: str, strength: str, summary: str, patterns: list[dict[str, Any]], metrics: list[dict[str, Any]], is_rule_out: bool) -> str:
        lines = [f"[{code}] {title} | service: {service_name} | signal: {strength}{' | rule-out' if is_rule_out else ''}", f"  {summary}"]
        for pattern in patterns[:5]:
            trend = "NEW" if pattern.get("isNewPattern") else f"x{pattern['changeRatio']} vs baseline" if pattern.get("changeRatio") else ""
            when = f" first seen {pattern['firstSeenAt']}" if pattern.get("firstSeenAt") else ""
            lines.append(f"  - ({pattern.get('level')}) {truncate_text(pattern.get('template'), 220)} | count {pattern.get('count')} {trend}{when}")
            for sample_line in pattern.get("sampleLinesMasked", [])[:1]:
                lines.append(f"      sample: {truncate_text(sample_line, 200)}")
        for metric in metrics:
            if metric.get("signalStrength") != RiskLevel.LOW:
                lines.append(f"  - metric {metric['metricName']}: peak {metric['windowPeak']} {metric['unit']} at {metric['windowPeakAt']} (baseline median {metric['baselineMedian']}, robust z {metric['robustZScore']})")
        return "\n".join(lines)
