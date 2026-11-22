"""keigan/services/evidence_service.py under spec 27: every evidence item says what its check found, a source that could not be read becomes a gap and never evidence, and what the
investigation left out is reported (AC-2 to AC-4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from keigan.ai.investigation_ai_schemas import PlannedQuery
from keigan.config.database_config import open_session
from keigan.config.settings import get_settings
from keigan.entities.application_entities import MonitoredService, ServiceLogSource
from keigan.entities.status_values import BaselineComparison, CoverageGapKind, CoverageGapReason, EvidenceCheckOutcome, RiskLevel
from keigan.exceptions.keigan_exceptions import IntegrationException
from keigan.integrations.telemetry_gateway import LogQueryResult, TelemetryQuery
from keigan.services.evidence_service import EvidenceDraft, EvidenceService, ServiceTelemetryContext
from keigan.services.investigation_coverage import CoverageGapCollector
from keigan.utils.pii_masker import MaskingContext

WINDOW_END = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
WINDOW_START = WINDOW_END - timedelta(hours=1)
BASELINE_END = WINDOW_START
BASELINE_START = BASELINE_END - timedelta(hours=1)


class FailingGateway:
    """Every log query raises ``error``."""

    def __init__(self, error: Exception):
        self.error = error
        self.queries: list[TelemetryQuery] = []

    async def query_logs(self, target: object, telemetry_query: TelemetryQuery) -> LogQueryResult:
        self.queries.append(telemetry_query)
        raise self.error

    async def query_activity_changes(self, *arguments: object, **keyword_arguments: object) -> list[object]:
        raise self.error

    def activity_is_simulated(self, use_simulation: bool = False) -> bool:
        return use_simulation


class EmptyGateway(FailingGateway):
    """Every log query succeeds with no rows."""

    async def query_logs(self, target: object, telemetry_query: TelemetryQuery) -> LogQueryResult:
        self.queries.append(telemetry_query)
        return LogQueryResult([], [], telemetry_query.query_text, telemetry_query.query_language)


def service_context(name: str = "claims-api", source_kinds: tuple[str, ...] = ("log_analytics",)) -> ServiceTelemetryContext:
    service = MonitoredService(service_id=f"svc-{name}", application_id="app-1", service_name=name, service_type="aks", criticality_tier="tier_2")
    sources = [ServiceLogSource(service_log_source_id=f"src-{name}-{kind}", service_id=service.service_id, source_kind=kind, query_scope_json=None) for kind in source_kinds]
    return ServiceTelemetryContext(service, None, sources, {})


def evidence_service(gateway: FailingGateway, coverage: CoverageGapCollector | None = None) -> EvidenceService:
    service = EvidenceService(None, coverage)  # type: ignore[arg-type]  # these tests never touch the database
    service.telemetry_gateway = gateway  # type: ignore[assignment]
    return service


def draft(category: str = "error_logs", *, strength: str = RiskLevel.HIGH, rule_out: bool = False, failure: CoverageGapReason | None = None, kind: str = "log_analytics") -> EvidenceDraft:
    return EvidenceDraft(
        service_id="svc-claims-api", service_name="claims-api", source_kind=kind, evidence_category=category, evidence_title=f"claims-api: {category}", evidence_summary="x",
        signal_strength=strength, is_rule_out=rule_out, failure_reason=failure,
    )


# ── What each check found, and whether it was compared with the baseline (AC-2) ──────────────────


def test_a_check_that_found_something_is_a_signal() -> None:
    assert draft().check_outcome == EvidenceCheckOutcome.SIGNAL


def test_a_healthy_or_empty_check_is_no_signal() -> None:
    assert draft(strength=RiskLevel.LOW, rule_out=True).check_outcome == EvidenceCheckOutcome.NO_SIGNAL


def test_a_check_that_could_not_read_its_source_is_not_checked_even_though_it_found_nothing() -> None:
    assert draft(strength=RiskLevel.LOW, rule_out=True, failure=CoverageGapReason.ACCESS_REFUSED).check_outcome == EvidenceCheckOutcome.NOT_CHECKED


@pytest.mark.parametrize(("category", "expected"), [
    ("failed_requests", BaselineComparison.COMPARED), ("slow_requests", BaselineComparison.COMPARED), ("metrics", BaselineComparison.COMPARED),
    ("change_event", BaselineComparison.NO_BASELINE_FOR_SOURCE), ("synthetic_probe", BaselineComparison.NO_BASELINE_FOR_SOURCE),
])
def test_only_changes_and_probes_have_no_baseline(category: str, expected: BaselineComparison) -> None:
    assert draft(category).baseline_comparison == expected


# ── A failed read is a gap, never evidence (AC-3) ────────────────────────────────────────────────


@pytest.mark.parametrize(("error", "reason"), [
    (IntegrationException("denied"), CoverageGapReason.SOURCE_ERROR),
    (TimeoutError(), CoverageGapReason.TIMED_OUT),
    (RuntimeError("boom"), CoverageGapReason.UNKNOWN),
])
async def test_a_template_whose_read_fails_gives_a_not_checked_draft_with_the_reason_code(error: Exception, reason: CoverageGapReason) -> None:
    context = service_context()
    service = evidence_service(FailingGateway(error))
    drafts = await service.collect_evidence([context], WINDOW_START, WINDOW_END, BASELINE_START, BASELINE_END, MaskingContext())
    assert drafts and all(item.check_outcome == EvidenceCheckOutcome.NOT_CHECKED and item.failure_reason == reason for item in drafts)
    assert all("Not available" in item.evidence_summary and "cannot rule this source in or out" in item.evidence_summary for item in drafts)


def test_the_exception_text_is_never_copied_into_the_summary() -> None:
    from keigan.services.evidence_service import describe_query_failure

    assert "workspace-secret-name" not in describe_query_failure(IntegrationException("workspace-secret-name is unreachable"))


async def test_unread_drafts_are_set_aside_and_reported_as_gaps_with_their_service_source_and_reason() -> None:
    coverage = CoverageGapCollector()
    service = evidence_service(EmptyGateway(RuntimeError()), coverage)
    readable = draft("failed_requests")
    unread = draft("error_logs", failure=CoverageGapReason.ACCESS_REFUSED, kind="application_insights")
    changes_unread = EvidenceDraft(None, "Azure Activity Log", "activity_log", "change_event", "Recent changes: could not be checked", "Not available", failure_reason=CoverageGapReason.TIMED_OUT)
    assert service.set_aside_unread([readable, unread, changes_unread]) == [readable]
    first, second = coverage.entries
    assert (first.kind, first.reason, first.service_name, first.source_kind) == (CoverageGapKind.SOURCE_NOT_READABLE, CoverageGapReason.ACCESS_REFUSED, "claims-api", "application_insights")
    assert (second.kind, second.reason) == (CoverageGapKind.CHANGES_NOT_READABLE, CoverageGapReason.TIMED_OUT)


async def test_a_failed_activity_log_read_is_a_not_checked_changes_draft() -> None:
    service = evidence_service(FailingGateway(IntegrationException("denied")))
    _, change_draft = await service.collect_change_evidence("app-1", [service_context()], WINDOW_START, WINDOW_END)
    assert change_draft is not None and change_draft.check_outcome == EvidenceCheckOutcome.NOT_CHECKED and change_draft.failure_reason == CoverageGapReason.SOURCE_ERROR


async def test_no_changes_found_is_a_rule_out_not_a_failure() -> None:
    service = evidence_service(EmptyGateway(RuntimeError()))
    service.telemetry_gateway.query_activity_changes = lambda *arguments, **keyword_arguments: _no_changes()  # type: ignore[method-assign]
    _, change_draft = await service.collect_change_evidence("app-1", [service_context()], WINDOW_START, WINDOW_END)
    assert change_draft is not None and change_draft.check_outcome == EvidenceCheckOutcome.NO_SIGNAL and change_draft.baseline_comparison == BaselineComparison.NO_BASELINE_FOR_SOURCE


async def _no_changes() -> list[object]:
    return []


# ── What Keigan left out is reported (AC-5) ──────────────────────────────────────────────────────


async def test_checks_beyond_the_limit_per_service_are_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "investigation_max_checks_per_service", 1)
    coverage = CoverageGapCollector()
    service = evidence_service(EmptyGateway(RuntimeError()), coverage)
    drafts = await service.collect_evidence([service_context()], WINDOW_START, WINDOW_END, BASELINE_START, BASELINE_END, MaskingContext())
    assert len(drafts) == 1
    (gap,) = coverage.entries
    assert gap.kind == CoverageGapKind.CHECKS_BEYOND_LIMIT and gap.service_name == "claims-api" and gap.parameters["limit"] == 1 and gap.parameters["count"] >= 1


async def test_a_service_with_no_log_source_is_reported_as_having_no_telemetry() -> None:
    coverage = CoverageGapCollector()
    service = evidence_service(EmptyGateway(RuntimeError()), coverage)
    await service.collect_evidence([service_context("mainframe", source_kinds=())], WINDOW_START, WINDOW_END, BASELINE_START, BASELINE_END, MaskingContext())
    (gap,) = coverage.entries
    assert (gap.kind, gap.service_name, gap.service_id) == (CoverageGapKind.SERVICE_WITHOUT_TELEMETRY, "mainframe", "svc-mainframe")


async def test_a_planner_query_that_safety_rules_refuse_is_reported() -> None:
    coverage = CoverageGapCollector()
    service = evidence_service(EmptyGateway(RuntimeError()), coverage)
    planned = PlannedQuery(service_name="claims-api", query_language="kql", query_text="AppRequests | union SecurityEvent", justification="x")
    await service.run_planned_queries([planned], [service_context()], WINDOW_START, WINDOW_END, BASELINE_START, BASELINE_END, MaskingContext())
    (gap,) = coverage.entries
    assert (gap.kind, gap.reason, gap.service_name) == (CoverageGapKind.PLANNED_QUERY_REJECTED, CoverageGapReason.QUERY_REJECTED, "claims-api")


async def test_a_planner_query_that_fails_is_reported_with_its_reason() -> None:
    coverage = CoverageGapCollector()
    service = evidence_service(FailingGateway(TimeoutError()), coverage)
    planned = PlannedQuery(service_name="claims-api", query_language="kql", query_text="AppRequests | summarize count()", justification="check")
    assert await service.run_planned_queries([planned], [service_context()], WINDOW_START, WINDOW_END, BASELINE_START, BASELINE_END, MaskingContext()) == []
    (gap,) = coverage.entries
    assert (gap.kind, gap.reason) == (CoverageGapKind.PLANNED_QUERY_FAILED, CoverageGapReason.TIMED_OUT)


def test_results_dropped_to_fit_the_evidence_budget_are_reported() -> None:
    coverage = CoverageGapCollector()
    service = evidence_service(EmptyGateway(RuntimeError()), coverage)
    drafts = [draft("failed_requests", strength=RiskLevel.HIGH)] + [draft(f"error_logs{number}", strength=RiskLevel.LOW, rule_out=True) for number in range(6)]
    kept = service.select_for_investigation(drafts, token_budget=60)
    left_out = len(drafts) - len(kept)
    assert left_out > 0
    (gap,) = coverage.entries
    assert (gap.kind, gap.parameters["count"]) == (CoverageGapKind.RESULTS_LEFT_OUT, left_out)


# ── What the model is shown (AC-4) ───────────────────────────────────────────────────────────────


def test_the_prompt_marks_a_rule_out_from_the_check_outcome_not_from_the_record_count() -> None:
    healthy_metrics = draft("metrics", strength=RiskLevel.LOW, rule_out=True)
    healthy_metrics.matched_record_count = 4  # healthy series still have points
    rendered = EvidenceService.render_draft_markdown(healthy_metrics, "E1")
    assert "checked: no signal (rule-out)" in rendered and "baseline: compared" in rendered


def test_the_prompt_says_when_there_is_no_baseline_for_a_source() -> None:
    rendered = EvidenceService.render_draft_markdown(draft("change_event"), "E2")
    assert "checked: signal" in rendered and "baseline: none for this source" in rendered and "rule-out" not in rendered
