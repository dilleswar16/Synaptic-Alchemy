"""Pure (database-free) derivation of the one reason an alert group shows for why its alerts belong together (roadmap B3).

The reasons are the ones the pipeline's group stage produces (``AlertPipelineService._select_group``), tried in this order: the alert is on a service the
group already touches, on a service next to one it touches (a dependency), has the same rule as an alert in the group, or the group is attached to an
open incident. Nothing here stores or guesses: the answer is recomputed from the group's alerts, and a group the rules cannot explain is "not recorded".

A group usually joined by several of these reasons. The group shows the first of them, in the order above (the strongest grouping reason), that any of its
later alerts joined by. The first alert starts the group, so it has no reason of its own.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from keigan.entities.status_values import AlertGroupingReason

JOINING_REASONS_STRONGEST_FIRST = (AlertGroupingReason.SAME_SERVICE, AlertGroupingReason.DEPENDENCY, AlertGroupingReason.SAME_RULE)


@dataclass(frozen=True)
class GroupedAlert:
    """The facts of one member alert that the group stage looks at."""

    service_id: str | None
    rule_identifier: str | None
    rule_name: str
    first_seen_at: datetime


@dataclass(frozen=True)
class GroupingReason:
    """``parameters`` holds what the sentence needs: ``serviceName``, ``relatedServiceName``, ``ruleName``, ``incidentName``, ``alertCount``, ``windowMinutes``."""

    code: AlertGroupingReason
    parameters: dict[str, str | int] = field(default_factory=dict)


def derive_grouping_reason(
    alerts: Iterable[GroupedAlert], *, neighbours_by_service_id: Mapping[str, set[str]], service_names: Mapping[str, str], window_minutes: int, incident_name: str | None
) -> GroupingReason:
    """``window_minutes`` is the application's group window; ``incident_name`` is the incident the group is attached to, if any."""
    members = sorted(alerts, key=lambda alert: alert.first_seen_at)
    if not members:
        return GroupingReason(AlertGroupingReason.NOT_RECORDED)
    if len(members) == 1:
        return GroupingReason(AlertGroupingReason.SINGLE_ALERT)
    name_of = lambda service_id: service_names.get(service_id, service_id)  # noqa: E731
    first_joiner: dict[AlertGroupingReason, GroupingReason] = {}
    earlier_service_ids = {members[0].service_id} - {None}
    earlier_rule_identifiers = {members[0].rule_identifier} - {None}
    for member in members[1:]:
        reason = _how_it_joined(member, earlier_service_ids, earlier_rule_identifiers, neighbours_by_service_id)
        if reason is not None and reason not in first_joiner:
            first_joiner[reason] = _reason_parameters(reason, member, members, earlier_service_ids, neighbours_by_service_id, name_of, window_minutes)
        earlier_service_ids |= {member.service_id} - {None}
        earlier_rule_identifiers |= {member.rule_identifier} - {None}
    for reason in JOINING_REASONS_STRONGEST_FIRST:
        if reason in first_joiner:
            return first_joiner[reason]
    if incident_name:
        return GroupingReason(AlertGroupingReason.ATTACHED_TO_INCIDENT, {"incidentName": incident_name, "windowMinutes": window_minutes})
    return GroupingReason(AlertGroupingReason.NOT_RECORDED)


def _how_it_joined(member: GroupedAlert, earlier_service_ids: set[str | None], earlier_rule_identifiers: set[str | None], neighbours_by_service_id: Mapping[str, set[str]]) -> AlertGroupingReason | None:
    """The first of the pipeline's checks that this alert passes against the alerts before it."""
    if member.service_id:
        if member.service_id in earlier_service_ids:
            return AlertGroupingReason.SAME_SERVICE
        if neighbours_by_service_id.get(member.service_id, set()) & earlier_service_ids:
            return AlertGroupingReason.DEPENDENCY
    if member.rule_identifier and member.rule_identifier in earlier_rule_identifiers:
        return AlertGroupingReason.SAME_RULE
    return None


def _reason_parameters(
    reason: AlertGroupingReason, member: GroupedAlert, members: list[GroupedAlert], earlier_service_ids: set[str | None], neighbours_by_service_id: Mapping[str, set[str]], name_of, window_minutes: int
) -> GroupingReason:
    if reason == AlertGroupingReason.SAME_SERVICE:
        alert_count = sum(1 for other in members if other.service_id == member.service_id)
        return GroupingReason(reason, {"serviceName": name_of(member.service_id), "alertCount": alert_count, "windowMinutes": window_minutes})
    if reason == AlertGroupingReason.DEPENDENCY:
        related_service_ids = neighbours_by_service_id[member.service_id] & earlier_service_ids
        related_name = min(name_of(service_id) for service_id in related_service_ids)
        return GroupingReason(reason, {"serviceName": name_of(member.service_id), "relatedServiceName": related_name, "windowMinutes": window_minutes})
    alert_count = sum(1 for other in members if other.rule_identifier == member.rule_identifier)
    return GroupingReason(reason, {"ruleName": member.rule_name, "alertCount": alert_count, "windowMinutes": window_minutes})
