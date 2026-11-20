"""keigan/services/evidence_service.py: planner queries get a real baseline, and activity-log people are masked."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from keigan.ai.investigation_ai_schemas import PlannedQuery
from keigan.config.database_config import open_session
from keigan.entities.application_entities import MonitoredService, ServiceLogSource
from keigan.integrations.telemetry_gateway import ChangeEvent, LogQueryResult, TelemetryQuery
from keigan.services.evidence_service import EvidenceDraft, EvidenceService, ServiceTelemetryContext
from keigan.utils.pii_masker import MaskingContext

WINDOW_END = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
WINDOW_START = WINDOW_END - timedelta(hours=1)
BASELINE_END = WINDOW_START
BASELINE_START = BASELINE_END - timedelta(hours=1)


@dataclass
class RecordingGateway:
    """Records every log query and every activity-log request instead of calling Azure."""

    queries: list[TelemetryQuery]
    change_events: list[ChangeEvent]

    async def query_logs(self, target: object, telemetry_query: TelemetryQuery) -> LogQueryResult:
        self.queries.append(telemetry_query)
        return LogQueryResult([], [], telemetry_query.query_text, telemetry_query.query_language)

    async def query_activity_changes(self, *arguments: object, **keyword_arguments: object) -> list[ChangeEvent]:
        return self.change_events


def _service_context(source_kind: str = "log_analytics", query_scope: dict | None = None) -> ServiceTelemetryContext:
    service = MonitoredService(service_id="svc-1", application_id="app-1", service_name="claims-api", service_type="aks", criticality_tier="tier_2")
    log_source = ServiceLogSource(service_log_source_id="src-1", service_id="svc-1", source_kind=source_kind, query_scope_json=query_scope)
    return ServiceTelemetryContext(service, None, [log_source], {})


async def _service(gateway: RecordingGateway) -> EvidenceService:
    async with open_session() as session:
        evidence_service = EvidenceService(session)
    evidence_service.telemetry_gateway = gateway  # type: ignore[assignment]
    return evidence_service


class TestPlannedQueriesHaveARealBaseline:
    async def test_the_window_query_and_the_baseline_query_each_carry_their_own_time_filter(self) -> None:
        gateway = RecordingGateway([], [])
        evidence_service = await _service(gateway)
        planned = PlannedQuery(service_name="claims-api", query_language="kql", query_text="AppExceptions | summarize count() by ExceptionType", justification="check exceptions")
        await evidence_service.run_planned_queries([planned], [_service_context()], WINDOW_START, WINDOW_END, BASELINE_START, BASELINE_END, MaskingContext())
        assert len(gateway.queries) == 2
        texts_by_start = {query.time_range_start: query.query_text for query in gateway.queries}
        assert "datetime(2026-11-20T11:00:00Z) .. datetime(2026-11-20T12:00:00Z)" in texts_by_start[WINDOW_START]
        assert "datetime(2026-11-20T10:00:00Z) .. datetime(2026-11-20T11:00:00Z)" in texts_by_start[BASELINE_START]

    async def test_the_baseline_query_does_not_contain_the_investigation_window(self) -> None:
        gateway = RecordingGateway([], [])
        evidence_service = await _service(gateway)
        planned = PlannedQuery(service_name="claims-api", query_language="kql", query_text="AppRequests | where Success == false | summarize count()", justification="check failures")
        await evidence_service.run_planned_queries([planned], [_service_context()], WINDOW_START, WINDOW_END, BASELINE_START, BASELINE_END, MaskingContext())
        baseline_text = next(query.query_text for query in gateway.queries if query.time_range_start == BASELINE_START)
        assert "T12:00:00Z" not in baseline_text

    async def test_splunk_planner_queries_use_the_index_of_the_log_source_for_both_windows(self) -> None:
        from keigan.entities.application_entities import LogToolConnection

        gateway = RecordingGateway([], [])
        evidence_service = await _service(gateway)
        context = _service_context("log_tool", {"index": "zos_syslog"})
        context.log_tool_connections_by_id["c1"] = LogToolConnection(log_tool_connection_id="c1", tool_type="splunk", connection_name="s", authentication_method="api_key")
        context.log_sources[0].log_tool_connection_id = "c1"
        planned = PlannedQuery(service_name="claims-api", query_language="spl", query_text="search index=* error | stats count", justification="abends")
        await evidence_service.run_planned_queries([planned], [context], WINDOW_START, WINDOW_END, BASELINE_START, BASELINE_END, MaskingContext())
        assert len(gateway.queries) == 2
        assert all(query.query_text.startswith("search index=zos_syslog earliest=") for query in gateway.queries)

    async def test_a_rejected_planner_query_is_skipped_and_nothing_runs(self) -> None:
        gateway = RecordingGateway([], [])
        evidence_service = await _service(gateway)
        planned = PlannedQuery(service_name="claims-api", query_language="kql", query_text="AppRequests | union SecurityEvent", justification="x")
        drafts = await evidence_service.run_planned_queries([planned], [_service_context()], WINDOW_START, WINDOW_END, BASELINE_START, BASELINE_END, MaskingContext())
        assert drafts == []
        assert gateway.queries == []


class TestPlannerKnowsWhatItMayQuery:
    def test_lists_the_language_tables_and_index_of_every_log_source(self) -> None:
        import json

        from keigan.entities.application_entities import LogToolConnection

        kql_context = _service_context()
        splunk_context = _service_context("log_tool", {"index": "zos_syslog"})
        splunk_context.service.service_name = "batch-runner"
        splunk_context.log_tool_connections_by_id["c1"] = LogToolConnection(log_tool_connection_id="c1", tool_type="splunk", connection_name="s", authentication_method="api_key")
        splunk_context.log_sources[0].log_tool_connection_id = "c1"
        description = json.loads(EvidenceService.describe_query_limits_for_planner([kql_context, splunk_context]))
        assert description[0]["serviceName"] == "claims-api"
        assert description[0]["logSources"][0]["queryLanguage"] == "kql"
        assert "AppRequests" in description[0]["logSources"][0]["allowedTables"]
        assert description[1]["logSources"][0]["queryLanguage"] == "spl"
        assert description[1]["logSources"][0]["index"] == "zos_syslog"

    def test_leaves_out_log_sources_that_the_planner_cannot_write_queries_for(self) -> None:
        import json

        description = json.loads(EvidenceService.describe_query_limits_for_planner([_service_context("synthetic_probe")]))
        assert description[0]["logSources"] == []


class TestActivityLogPeopleAreMasked:
    @staticmethod
    def _event() -> ChangeEvent:
        return ChangeEvent(
            occurred_at=WINDOW_START, change_kind="deployment", operation_name="Microsoft.Web/sites/write", resource_identifier="/subscriptions/x",
            description="Deployment started by taro.yamada@metlife.co.jp", caller="taro.yamada@metlife.co.jp",
        )

    async def test_caller_and_description_are_masked_in_the_returned_events_and_the_evidence(self) -> None:
        evidence_service = await _service(RecordingGateway([], [self._event()]))
        change_events, draft = await evidence_service.collect_change_evidence("app-1", [_service_context()], WINDOW_START, WINDOW_END)
        assert draft is not None
        everything = repr(change_events) + repr(draft.condensed_patterns) + draft.evidence_summary
        assert "taro.yamada" not in everything
        assert "<EMAIL_1>" in everything

    async def test_the_same_person_gets_the_same_placeholder_as_in_the_rest_of_the_investigation(self) -> None:
        masking_context = MaskingContext()
        evidence_service = await _service(RecordingGateway([], [self._event()]))
        change_events, _ = await evidence_service.collect_change_evidence("app-1", [_service_context()], WINDOW_START, WINDOW_END, masking_context)
        assert change_events[0].caller == "<EMAIL_1>"
        assert masking_context.masked_value_count >= 1



class StaggeredGateway:
    """Answers each query after a different pause, so concurrent queries finish in a different order than they started."""

    def __init__(self, rows_by_scope: dict[str, list[dict]], pause_seconds_by_scope: dict[str, float]) -> None:
        self.rows_by_scope = rows_by_scope
        self.pause_seconds_by_scope = pause_seconds_by_scope

    async def query_logs(self, target: object, telemetry_query: TelemetryQuery) -> LogQueryResult:
        scope = telemetry_query.query_text
        await asyncio.sleep(self.pause_seconds_by_scope[scope])
        return LogQueryResult(["message"], self.rows_by_scope[scope], scope, telemetry_query.query_language)


class TestMaskedValueCountBelongsToItsOwnEvidence:
    async def test_concurrent_queries_sharing_one_masking_context_each_count_only_their_own_masked_values(self) -> None:
        """The count stored with each evidence item used to be a before/after difference of a counter shared by all concurrent queries."""
        slow_scope, fast_scope = "slow-source", "fast-source"
        gateway = StaggeredGateway(
            rows_by_scope={
                slow_scope: [{"message": "failed for first.person@example.com"}],
                fast_scope: [{"message": f"failed for person{index}@example.com"} for index in range(5)],
            },
            pause_seconds_by_scope={slow_scope: 0.05, fast_scope: 0.0},
        )
        evidence_service = await _service(gateway)  # type: ignore[arg-type]
        masking_context = MaskingContext()
        template = {"template_key": "planner_query", "query_language": "kql", "signal_kind": "generic", "evidence_category": "ai_planned_query"}
        service_context = _service_context()

        def new_draft() -> EvidenceDraft:
            return EvidenceDraft("svc-1", "claims-api", "log_analytics", "ai_planned_query", "claims-api: x", "", "kql", "", WINDOW_START, WINDOW_END, criticality_tier="tier_2")

        slow_draft, fast_draft = new_draft(), new_draft()
        target = service_context.target_for(service_context.log_sources[0])
        await asyncio.gather(
            evidence_service._fill_log_evidence(slow_draft, target, template, slow_scope, WINDOW_START, WINDOW_END, BASELINE_START, BASELINE_END, masking_context),
            evidence_service._fill_log_evidence(fast_draft, target, template, fast_scope, WINDOW_START, WINDOW_END, BASELINE_START, BASELINE_END, masking_context),
        )
        assert slow_draft.masked_value_count == 2  # the window query and the baseline query each return the one address
        assert fast_draft.masked_value_count == 10
        assert masking_context.masked_value_count == 12
