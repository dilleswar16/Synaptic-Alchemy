"""keigan/services/alert_grouping_reason.py: the one reason an alert group shows for why its alerts belong together (roadmap B3).

The reasons are the ones the pipeline's group stage produces (alert_pipeline_service._select_group): same service, dependency, same rule, attached to an open incident.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from keigan.entities.status_values import AlertGroupingReason
from keigan.services.alert_grouping_reason import GroupedAlert, GroupingReason, derive_grouping_reason

START = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
SERVICE_NAMES = {"svc-api": "claims-api", "svc-db": "claims-db", "svc-queue": "claims-queue", "svc-web": "claims-web"}
NEIGHBOURS = {"svc-api": {"svc-db"}, "svc-db": {"svc-api"}}


def alert(minutes: int, service_id: str | None, rule_identifier: str | None, rule_name: str = "Error rate high") -> GroupedAlert:
    return GroupedAlert(service_id=service_id, rule_identifier=rule_identifier, rule_name=rule_name, first_seen_at=START + timedelta(minutes=minutes))


def reason_of(alerts: list[GroupedAlert], *, incident_name: str | None = None, window_minutes: int = 10) -> GroupingReason:
    return derive_grouping_reason(alerts, neighbours_by_service_id=NEIGHBOURS, service_names=SERVICE_NAMES, window_minutes=window_minutes, incident_name=incident_name)


def test_a_group_of_one_alert_has_nothing_to_explain() -> None:
    assert reason_of([alert(0, "svc-api", "rule-a")]) == GroupingReason(AlertGroupingReason.SINGLE_ALERT, {})


def test_a_group_of_one_alert_stays_single_even_when_it_is_linked_to_an_incident() -> None:
    assert reason_of([alert(0, "svc-api", "rule-a")], incident_name="INC0012345").code == AlertGroupingReason.SINGLE_ALERT


def test_a_group_whose_alerts_are_gone_is_not_recorded() -> None:
    assert reason_of([]) == GroupingReason(AlertGroupingReason.NOT_RECORDED, {})


def test_alerts_on_the_same_service_name_the_service_the_count_and_the_policy_window() -> None:
    result = reason_of([alert(0, "svc-api", "rule-a"), alert(3, "svc-api", "rule-b"), alert(5, "svc-api", "rule-c")], window_minutes=15)
    assert result == GroupingReason(AlertGroupingReason.SAME_SERVICE, {"serviceName": "claims-api", "alertCount": 3, "windowMinutes": 15})


def test_the_window_in_the_sentence_is_the_one_the_caller_passes() -> None:
    members = [alert(0, "svc-api", "rule-a"), alert(1, "svc-api", "rule-b")]
    assert reason_of(members, window_minutes=7).parameters["windowMinutes"] == 7
    assert reason_of(members, window_minutes=30).parameters["windowMinutes"] == 30


def test_alerts_on_dependent_services_name_both_services() -> None:
    result = reason_of([alert(0, "svc-api", "rule-a"), alert(2, "svc-db", "rule-b")])
    assert result == GroupingReason(AlertGroupingReason.DEPENDENCY, {"serviceName": "claims-db", "relatedServiceName": "claims-api", "windowMinutes": 10})


def test_the_same_rule_on_unrelated_services_names_the_rule_and_counts_its_alerts() -> None:
    result = reason_of([alert(0, "svc-api", "rule-a", "Latency p95"), alert(4, "svc-web", "rule-a", "Latency p95"), alert(6, "svc-queue", "rule-z", "Queue depth")])
    assert result == GroupingReason(AlertGroupingReason.SAME_RULE, {"ruleName": "Latency p95", "alertCount": 2, "windowMinutes": 10})


def test_the_same_rule_works_for_alerts_that_have_no_service() -> None:
    result = reason_of([alert(0, None, "rule-a", "Disk full"), alert(1, None, "rule-a", "Disk full")])
    assert result.code == AlertGroupingReason.SAME_RULE


def test_an_alert_that_joined_through_an_open_incident_names_the_incident() -> None:
    result = reason_of([alert(0, "svc-api", "rule-a"), alert(2, "svc-web", "rule-b")], incident_name="INC0012345")
    assert result == GroupingReason(AlertGroupingReason.ATTACHED_TO_INCIDENT, {"incidentName": "INC0012345", "windowMinutes": 10})


def test_alerts_with_no_shared_service_dependency_or_rule_and_no_incident_are_not_recorded_rather_than_guessed() -> None:
    assert reason_of([alert(0, "svc-api", "rule-a"), alert(2, "svc-web", "rule-b")]) == GroupingReason(AlertGroupingReason.NOT_RECORDED, {})


def test_alerts_without_service_or_rule_identifier_are_never_matched_to_each_other() -> None:
    assert reason_of([alert(0, None, None), alert(1, None, None)]).code == AlertGroupingReason.NOT_RECORDED


def test_with_mixed_reasons_the_strongest_one_wins_in_the_pipelines_own_order() -> None:
    """The pipeline tries same service, then dependency, then same rule, then the incident; the group shows the first of these that any member joined by."""
    same_service = [alert(0, "svc-api", "rule-a"), alert(1, "svc-api", "rule-b"), alert(2, "svc-db", "rule-c"), alert(3, "svc-web", "rule-a")]
    assert reason_of(same_service, incident_name="INC1").code == AlertGroupingReason.SAME_SERVICE
    dependency_and_rule = [alert(0, "svc-api", "rule-a"), alert(1, "svc-db", "rule-b"), alert(2, "svc-web", "rule-a")]
    assert reason_of(dependency_and_rule, incident_name="INC1").code == AlertGroupingReason.DEPENDENCY
    rule_and_incident = [alert(0, "svc-api", "rule-a"), alert(1, "svc-web", "rule-a"), alert(2, "svc-queue", "rule-q")]
    assert reason_of(rule_and_incident, incident_name="INC1").code == AlertGroupingReason.SAME_RULE


def test_the_result_does_not_depend_on_the_order_the_alerts_are_passed_in() -> None:
    members = [alert(0, "svc-api", "rule-a"), alert(3, "svc-db", "rule-b"), alert(5, "svc-api", "rule-c")]
    assert reason_of(list(reversed(members))) == reason_of(members)


def test_an_alert_that_only_matches_a_later_alert_does_not_count_as_joining_it() -> None:
    """The first alert starts the group; only later alerts have a reason for joining it."""
    members = [alert(0, "svc-web", "rule-a"), alert(2, "svc-api", "rule-b"), alert(4, "svc-api", "rule-c")]
    assert reason_of(members) == GroupingReason(AlertGroupingReason.SAME_SERVICE, {"serviceName": "claims-api", "alertCount": 2, "windowMinutes": 10})


def test_a_service_without_a_known_name_falls_back_to_its_identifier_instead_of_failing() -> None:
    result = derive_grouping_reason([alert(0, "svc-gone", "rule-a"), alert(1, "svc-gone", "rule-b")], neighbours_by_service_id={}, service_names={}, window_minutes=10, incident_name=None)
    assert result.parameters["serviceName"] == "svc-gone"
