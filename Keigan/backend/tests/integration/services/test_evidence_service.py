"""keigan/services/evidence_service.py: planner queries get a real baseline, and activity-log people are masked."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from keigan.ai.investigation_ai_schemas import PlannedQuery
from keigan.config.database_config import open_session
from keigan.entities.application_entities import MonitoredService, ServiceLogSource
from keigan.exceptions.keigan_exceptions import ForbiddenException, IntegrationException
from keigan.integrations.telemetry_gateway import ChangeEvent, LogQueryResult, TelemetryQuery
from keigan.services.evidence_service import EvidenceDraft, EvidenceService, ServiceTelemetryContext
from keigan.utils.pii_masker import MaskingContext
from keigan.utils.query_safety import QueryRejectedError

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

    def activity_is_simulated(self, use_simulation: bool = False) -> bool:
        return use_simulation


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



class TestAFailedActivityLogReadIsNotReportedAsNoChanges:
    class FailingChangesGateway(RecordingGateway):
        async def query_activity_changes(self, *arguments: object, **keyword_arguments: object) -> list[ChangeEvent]:
            raise IntegrationException("Forbidden", error_code="azure_forbidden")

    async def test_a_refused_read_says_the_changes_could_not_be_checked(self) -> None:
        evidence_service = await _service(self.FailingChangesGateway([], []))
        change_events, draft = await evidence_service.collect_change_evidence("app-1", [_service_context()], WINDOW_START, WINDOW_END)
        assert change_events == []
        assert draft is not None
        assert draft.evidence_summary.startswith("Not available:")
        assert "refused access" in draft.evidence_summary
        assert "cannot rule this source in or out" in draft.evidence_summary
        assert "none found" not in draft.evidence_title.lower() and "no deployments" not in draft.evidence_summary.lower()

    async def test_a_read_that_works_and_finds_nothing_still_says_no_changes(self) -> None:
        evidence_service = await _service(RecordingGateway([], []))
        _, draft = await evidence_service.collect_change_evidence("app-1", [_service_context()], WINDOW_START, WINDOW_END)
        assert draft is not None and draft.evidence_summary.startswith("Rule-out: no deployments")


class TestReadingChangeEventsRaisesWhenTheReadFails:
    """``read_change_events`` is the Activity Log read both the investigation pipeline and Ask Keigan use; a failed read must reach the caller as a failure, never as an empty list."""

    class RefusingGateway(RecordingGateway):
        async def query_activity_changes(self, *arguments: object, **keyword_arguments: object) -> list[ChangeEvent]:
            raise ForbiddenException("This application's activity log is not approved.")

    class UnreachableGateway(RecordingGateway):
        async def query_activity_changes(self, *arguments: object, **keyword_arguments: object) -> list[ChangeEvent]:
            raise IntegrationException("Azure answered 503", error_code="azure_unavailable")

    class ArgumentRecordingGateway(RecordingGateway):
        def __init__(self, change_events: list[ChangeEvent]) -> None:
            super().__init__([], change_events)
            self.requests: list[tuple[tuple[object, ...], dict[str, object]]] = []

        async def query_activity_changes(self, *arguments: object, **keyword_arguments: object) -> list[ChangeEvent]:
            self.requests.append((arguments, keyword_arguments))
            return self.change_events

    async def test_the_events_are_returned_as_the_source_gave_them(self) -> None:
        event = ChangeEvent(occurred_at=WINDOW_START, change_kind="deployment", operation_name="Microsoft.Web/sites/write", resource_identifier="/subscriptions/x", description="Release 41", caller="taro.yamada@metlife.co.jp")
        evidence_service = await _service(RecordingGateway([], [event]))
        assert await evidence_service.read_change_events("app-1", [_service_context()], WINDOW_START, WINDOW_END) == [event]

    async def test_an_empty_answer_from_a_source_that_worked_is_an_empty_list(self) -> None:
        evidence_service = await _service(RecordingGateway([], []))
        assert await evidence_service.read_change_events("app-1", [_service_context()], WINDOW_START, WINDOW_END) == []

    async def test_the_azure_component_of_the_services_decides_where_the_log_is_read(self) -> None:
        from keigan.entities.application_entities import ApplicationComponent

        gateway = self.ArgumentRecordingGateway([])
        component = ApplicationComponent(
            application_id="app-1", component_type="azure_resource_group", component_name="rg-polaris", azure_tenant_id="tenant-1", azure_subscription_id="subscription-1",
            azure_resource_group_name="rg-polaris", component_configuration_json={"simulated": True},
        )
        service_context = ServiceTelemetryContext(_service_context().service, component, [], {})
        await (await _service(gateway)).read_change_events("app-1", [service_context], WINDOW_START, WINDOW_END)
        assert gateway.requests == [(("app-1", "tenant-1", "subscription-1", "rg-polaris", WINDOW_START, WINDOW_END), {"use_simulation": True})]

    async def test_the_changes_are_simulated_when_the_gateway_says_so_for_the_component_of_the_services(self) -> None:
        from keigan.entities.application_entities import ApplicationComponent

        def context_with(configuration: dict) -> ServiceTelemetryContext:
            component = ApplicationComponent(
                application_id="app-1", component_type="azure_resource_group", component_name="rg-polaris", azure_tenant_id="tenant-1", azure_subscription_id="subscription-1",
                azure_resource_group_name="rg-polaris", component_configuration_json=configuration,
            )
            return ServiceTelemetryContext(_service_context().service, component, [], {})

        evidence_service = await _service(RecordingGateway([], []))
        assert evidence_service.are_changes_simulated([context_with({"simulated": True})]) is True
        assert evidence_service.are_changes_simulated([context_with({})]) is False
        assert evidence_service.are_changes_simulated([_service_context()]) is False  # no Azure component: the gateway's own mode rule decides

    async def test_a_failed_read_raises_instead_of_returning_no_changes(self) -> None:
        evidence_service = await _service(self.UnreachableGateway([], []))
        with pytest.raises(IntegrationException):
            await evidence_service.read_change_events("app-1", [_service_context()], WINDOW_START, WINDOW_END)

    async def test_a_source_the_access_policy_refuses_raises_the_refusal(self) -> None:
        evidence_service = await _service(self.RefusingGateway([], []))
        with pytest.raises(ForbiddenException):
            await evidence_service.read_change_events("app-1", [_service_context()], WINDOW_START, WINDOW_END)

    async def test_the_pipeline_still_turns_the_same_failure_into_a_could_not_be_checked_item(self) -> None:
        evidence_service = await _service(self.UnreachableGateway([], []))
        change_events, draft = await evidence_service.collect_change_evidence("app-1", [_service_context()], WINDOW_START, WINDOW_END)
        assert change_events == []
        assert draft is not None and draft.evidence_title == "Recent changes: could not be checked"


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


class TestFailedPlannerQueryIsLoggedAndSkipped:
    async def test_a_planned_query_that_fails_is_skipped_and_logged_as_a_warning_that_names_the_service(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging
        from types import SimpleNamespace

        async def workspace_throttled(*arguments: object, **keyword_arguments: object) -> None:
            raise RuntimeError("workspace throttled")

        service = SimpleNamespace(service_name="claims-api", service_id="service-1", criticality_tier="tier_1")
        log_source = SimpleNamespace(source_kind="log_analytics", query_scope_json={"workspaceId": "workspace-1"}, log_tool_connection_id="connection-1")
        service_context = SimpleNamespace(service=service, log_sources=[log_source], target_for=lambda source: None)
        planned_query = SimpleNamespace(service_name="claims-api", query_language="kql", query_text="AppRequests | where Success == false | summarize count()", justification="failed requests")
        window_start = datetime(2026, 11, 20, 11, 0, tzinfo=UTC)
        window_end = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
        fake_self = SimpleNamespace(_source_supports_language=EvidenceService._source_supports_language, _fill_log_evidence=workspace_throttled)
        drafts = await EvidenceService.run_planned_queries(fake_self, [planned_query], [service_context], window_start, window_end, window_start - timedelta(days=1), window_start, None)  # type: ignore[arg-type]
        assert drafts == []
        assert any(record.levelno == logging.WARNING and "claims-api" in record.getMessage() for record in caplog.records)


class FailingGateway:
    def __init__(self, error: Exception):
        self.error = error

    async def query_logs(self, target: object, telemetry_query: TelemetryQuery) -> LogQueryResult:
        raise self.error


async def _draft_for_failing_source(error: Exception) -> EvidenceDraft:
    from keigan.services.evidence_service import load_query_templates

    evidence_service = await _service(FailingGateway(error))  # type: ignore[arg-type]
    context = _service_context()
    template = next(template for template in load_query_templates() if template["query_language"] == "kql" and "aks" in template["service_types"] and "log_analytics" in template["source_kinds"])
    return await evidence_service._run_template(context, context.log_sources[0], template, WINDOW_START, WINDOW_END, BASELINE_START, BASELINE_END, MaskingContext())


class TestAFailedQueryTellsWhyTheSourceCouldNotBeRead:
    @pytest.mark.parametrize(
        ("error", "reason"),
        [
            (IntegrationException("raw es-prod.internal text", error_code="azure_forbidden"), "was refused access to this source"),
            (IntegrationException("raw es-prod.internal text", error_code="azure_throttled"), "was busy and asked Keigan to slow down"),
            (IntegrationException("raw es-prod.internal text", error_code="azure_not_found"), "was not found"),
            (IntegrationException("raw es-prod.internal text"), "returned an error"),
            (asyncio.TimeoutError(), "took too long to answer"),
            (ForbiddenException("raw policy text"), "is not approved for this application"),
            (QueryRejectedError("raw query text"), "safety rules refused the query"),
            (RuntimeError("raw secret-token text"), "for a reason Keigan could not identify"),
        ],
    )
    async def test_each_kind_of_failure_has_its_own_plain_reason(self, error: Exception, reason: str) -> None:
        draft = await _draft_for_failing_source(error)
        assert draft.evidence_summary.startswith("Not available: ") and reason in draft.evidence_summary
        assert draft.evidence_summary.endswith("Keigan cannot rule this source in or out.")
        assert "raw" not in draft.evidence_summary and "es-prod" not in draft.evidence_summary and "secret-token" not in draft.evidence_summary
        assert draft.is_rule_out is True
