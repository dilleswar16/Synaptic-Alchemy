"""keigan/services/ask_keigan_signal_tools.py: get_slo_history, list_predictive_signals and get_health_score of the global scope (spec 23, 5, 9.2)."""

from __future__ import annotations

import math
import uuid

import pytest
from keigan.ai.tool_registry import AskKeiganScope
from keigan.config.settings import get_settings
from keigan.entities.status_values import ChatRunStepStatus
from keigan.services import ask_keigan_tools  # noqa: F401 — registers the tools
from support.ask_keigan_global_tool_data import create_predictive_signal, slo_id_of
from support.ask_keigan_tool_calls import run_tool, user
from support.ask_keigan_tool_data import create_slo_application
from support.telemetry_scope import create_scoped_application

pytestmark = pytest.mark.usefixtures("seed_context")
GLOBAL = AskKeiganScope.GLOBAL


def reader_of(*applications) -> object:  # type: ignore[no-untyped-def]
    return user(f"reader.{uuid.uuid4().hex[:6]}@keigan.local", *(f"{application.application_code}_reader" for application in applications))


# ── get_slo_history ───────────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_slo_history_gives_the_points_and_the_compliance_of_the_slo() -> None:
    slo_application = await create_slo_application()
    slo_id = await slo_id_of(slo_application.application_id, "Checkout availability")
    outcome = await run_tool("get_slo_history", {"slo_id": slo_id}, reader_of(slo_application), scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED, outcome.outcome_message
    assert outcome.output.summary.startswith("Checkout availability: 1 point in the last 168 hours, compliance 99.0% against target 99.9%")
    assert outcome.output.points[0].sli_percentage == 99.0 and outcome.output.points[0].total_event_count == 1000
    assert (outcome.output.sli_name, outcome.output.target_percentage, outcome.output.rolling_window_days) == ("Checkout availability", 99.9, 30)
    assert [(record.kind, record.id, record.label, record.application_id) for record in outcome.records] == [("slo", slo_id, "Checkout availability", slo_application.application_id)]
    assert outcome.applications_read == frozenset({slo_application.application_id})


async def test_slo_history_says_when_an_slo_has_no_measurements() -> None:
    slo_application = await create_slo_application()
    slo_id = await slo_id_of(slo_application.application_id, "Batch success")
    outcome = await run_tool("get_slo_history", {"slo_id": slo_id}, reader_of(slo_application), scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED
    assert outcome.output.summary == "Batch success: no measurements in the last 168 hours"
    assert outcome.output.points == [] and outcome.output.compliance_percentage is None


async def test_slo_history_picks_a_resolution_that_keeps_the_points_within_the_series_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    slo_application = await create_slo_application()
    slo_id = await slo_id_of(slo_application.application_id, "Checkout availability")
    monkeypatch.setattr(get_settings(), "ask_keigan_tool_series_point_limit", 10)
    outcome = await run_tool("get_slo_history", {"slo_id": slo_id, "lookback_hours": 168}, reader_of(slo_application), scope=GLOBAL)
    assert outcome.output.resolution_minutes == math.ceil(168 * 60 / 9)  # nine intervals plus the bucket the window starts in
    assert outcome.output.point_count <= 10


async def test_slo_history_of_an_unknown_slo_is_not_found() -> None:
    slo_application = await create_slo_application()
    outcome = await run_tool("get_slo_history", {"slo_id": str(uuid.uuid4())}, reader_of(slo_application), scope=GLOBAL)
    assert (outcome.status, outcome.outcome_code, outcome.output) == (ChatRunStepStatus.FAILED, "not_found", None)


async def test_slo_history_of_an_application_the_person_cannot_read_is_refused() -> None:
    readable = await create_scoped_application()
    slo_application = await create_slo_application()
    slo_id = await slo_id_of(slo_application.application_id, "Checkout availability")
    outcome = await run_tool("get_slo_history", {"slo_id": slo_id}, reader_of(readable), scope=GLOBAL)
    assert (outcome.status, outcome.outcome_code, outcome.output) == (ChatRunStepStatus.REFUSED, "access_denied", None)
    assert "Checkout availability" not in outcome.model_message


async def test_slo_history_outside_the_scope_of_the_answer_is_refused_even_when_the_person_may_read_it() -> None:
    slo_application = await create_slo_application()
    slo_id = await slo_id_of(slo_application.application_id, "Checkout availability")
    both = reader_of(slo_application)
    narrowed = await create_scoped_application()
    outcome = await run_tool("get_slo_history", {"slo_id": slo_id}, both, scope=GLOBAL, profile_user=reader_of(narrowed))
    assert (outcome.status, outcome.outcome_code) == (ChatRunStepStatus.REFUSED, "access_denied")


async def test_slo_history_is_refused_to_a_person_whose_access_was_removed_while_the_answer_ran() -> None:
    slo_application = await create_slo_application()
    slo_id = await slo_id_of(slo_application.application_id, "Checkout availability")
    reader = reader_of(slo_application)
    outcome = await run_tool("get_slo_history", {"slo_id": slo_id}, user("nobody@keigan.local"), scope=GLOBAL, profile_user=reader)
    assert (outcome.status, outcome.outcome_code) == (ChatRunStepStatus.REFUSED, "access_denied")


# ── list_predictive_signals ───────────────────────────────────────────────────────────────────────────────────────────────────
async def test_predictive_signals_list_the_open_and_acknowledged_most_severe_first_with_a_summary() -> None:
    application = await create_scoped_application()
    warning = await create_predictive_signal(application.application_id, title="Latency climbs", severity="warning")
    critical = await create_predictive_signal(application.application_id, title="Queue will fill", severity="critical")
    await create_predictive_signal(application.application_id, title="Dismissed", severity="critical", status="dismissed")
    acknowledged = await create_predictive_signal(application.application_id, title="Known", severity="info", status="acknowledged")
    outcome = await run_tool("list_predictive_signals", {}, reader_of(application), scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED, outcome.outcome_message
    assert [item.predictive_signal_id for item in outcome.output.items] == [critical, warning, acknowledged]
    assert outcome.output.summary == "3 predictive signals"
    first = outcome.output.items[0]
    assert (first.title, first.severity, first.status, first.application_code, first.detector_name) == ("Queue will fill", "critical", "open", application.application_code, "latency_trend")
    assert [(record.kind, record.id) for record in outcome.records][:1] == [("signal", critical)]


async def test_predictive_signals_filter_by_severity_and_status() -> None:
    application = await create_scoped_application()
    await create_predictive_signal(application.application_id, title="Latency climbs", severity="warning")
    critical = await create_predictive_signal(application.application_id, title="Queue will fill", severity="critical")
    dismissed = await create_predictive_signal(application.application_id, title="Dismissed", severity="critical", status="dismissed")
    by_severity = await run_tool("list_predictive_signals", {"severities": ["critical"]}, reader_of(application), scope=GLOBAL)
    by_status = await run_tool("list_predictive_signals", {"statuses": ["dismissed"]}, reader_of(application), scope=GLOBAL)
    assert [item.predictive_signal_id for item in by_severity.output.items] == [critical]  # dismissed is not open or acknowledged
    assert [item.predictive_signal_id for item in by_status.output.items] == [dismissed]


async def test_predictive_signals_refuse_an_application_code_the_person_cannot_read() -> None:
    readable, hidden = await create_scoped_application(), await create_scoped_application()
    await create_predictive_signal(hidden.application_id, title="Hidden signal")
    outcome = await run_tool("list_predictive_signals", {"application_codes": [hidden.application_code]}, reader_of(readable), scope=GLOBAL)
    assert (outcome.status, outcome.outcome_code, outcome.output) == (ChatRunStepStatus.REFUSED, "access_denied", None)


async def test_predictive_signals_report_every_application_they_covered() -> None:
    first, second = await create_scoped_application(), await create_scoped_application()
    await create_predictive_signal(first.application_id, title="First signal")
    outcome = await run_tool("list_predictive_signals", {}, reader_of(first, second), scope=GLOBAL)
    assert outcome.applications_read == frozenset({first.application_id, second.application_id})


async def test_predictive_signals_cut_to_the_list_limit_and_say_there_are_more(monkeypatch: pytest.MonkeyPatch) -> None:
    application = await create_scoped_application()
    for title in ("First", "Second", "Third"):
        await create_predictive_signal(application.application_id, title=title)
    monkeypatch.setattr(get_settings(), "ask_keigan_tool_list_item_limit", 2)
    outcome = await run_tool("list_predictive_signals", {}, reader_of(application), scope=GLOBAL)
    assert (outcome.output.item_count, outcome.output.is_truncated) == (2, True)
    assert outcome.output.summary == "More than 2 predictive signals"


async def test_predictive_signals_are_refused_to_a_person_whose_access_was_removed_while_the_answer_ran() -> None:
    application = await create_scoped_application()
    await create_predictive_signal(application.application_id, title="Latency climbs")
    reader = reader_of(application)
    outcome = await run_tool("list_predictive_signals", {"application_codes": [application.application_code]}, user("nobody@keigan.local"), scope=GLOBAL, profile_user=reader)
    assert (outcome.status, outcome.outcome_code) == (ChatRunStepStatus.REFUSED, "access_denied")


# ── get_health_score ──────────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_health_score_gives_the_current_score_and_the_trend_of_the_days_asked() -> None:
    application = await create_scoped_application()
    outcome = await run_tool("get_health_score", {"application_code": application.application_code, "days": 7}, reader_of(application), scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED, outcome.outcome_message
    assert outcome.output.current_health_score == 90  # no SLO (0.8 of 50), no signal, no incident
    assert outcome.output.summary == f"Health score 90 for Scope {application.application_code}, 7 days of trend"
    assert outcome.output.point_count == 8 and len(outcome.output.points) == 8
    assert [(record.kind, record.id, record.application_id) for record in outcome.records] == [("application", application.application_id, application.application_id)]


async def test_health_score_refuses_an_application_the_person_cannot_read() -> None:
    readable, hidden = await create_scoped_application(), await create_scoped_application()
    outcome = await run_tool("get_health_score", {"application_code": hidden.application_code}, reader_of(readable), scope=GLOBAL)
    assert (outcome.status, outcome.outcome_code, outcome.output) == (ChatRunStepStatus.REFUSED, "access_denied", None)


async def test_health_score_reports_only_the_application_it_read() -> None:
    first, second = await create_scoped_application(), await create_scoped_application()
    outcome = await run_tool("get_health_score", {"application_code": second.application_code}, reader_of(first, second), scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED and outcome.applications_read == frozenset({second.application_id})


@pytest.mark.parametrize("days", [6, 91])
async def test_health_score_refuses_a_trend_outside_seven_to_ninety_days(days: int) -> None:
    application = await create_scoped_application()
    outcome = await run_tool("get_health_score", {"application_code": application.application_code, "days": days}, reader_of(application), scope=GLOBAL)
    assert (outcome.status, outcome.outcome_code) == (ChatRunStepStatus.REFUSED, "invalid_arguments")


async def test_health_score_is_refused_to_a_person_whose_access_was_removed_while_the_answer_ran() -> None:
    application = await create_scoped_application()
    reader = reader_of(application)
    outcome = await run_tool("get_health_score", {"application_code": application.application_code}, user("nobody@keigan.local"), scope=GLOBAL, profile_user=reader)
    assert (outcome.status, outcome.outcome_code) == (ChatRunStepStatus.REFUSED, "access_denied")

