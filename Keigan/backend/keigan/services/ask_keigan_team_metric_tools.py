"""The team and reliability metrics tools of the global scope (spec 23, sections 5 and 5.2): list_team_members, get_reliability_metrics.

list_team_members aliases the people (decision D2): each member is named by role and number (sre 1, developer 2); no name, email, user principal name or Entra id
is ever read into the output, the summary or the stored trace. get_reliability_metrics has no acknowledgement figure: the data has no acknowledgement time (MTTA).
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from pydantic import BaseModel, Field

from keigan.ai.ask_keigan_tool_models import GetReliabilityMetricsInput, ListTeamMembersInput
from keigan.ai.tool_registry import RecordReference, ToolAuthorization, ToolContext, ToolMasking, ToolPresentation, tool_registry
from keigan.dtos.metrics_dtos import StatResponse
from keigan.services.ask_keigan_tool_support import (
    GLOBAL_SCOPE, application_id_of, applications_to_check, limited, plural, read_tool, readable_application, window_words,
)
from keigan.services.reliability_metrics_service import ReliabilityMetricsService
from keigan.services.stakeholder_service import StakeholderService
from keigan.utils.time_utils import utc_now


# ── list_team_members ─────────────────────────────────────────────────────────────────────────────────────────────────────────
class TeamMemberItem(BaseModel):
    alias: str = Field(description="The member's role and a number, for example sre 1. The name is never sent.")
    stakeholder_role: str
    recipient_type: str
    is_active: bool
    team_member_status: str = Field(description="listed, invited, active or inactive.")


class ListTeamMembersOutput(BaseModel):
    summary: str
    items: list[TeamMemberItem]
    item_count: int
    total_count: int
    is_truncated: bool
    records: list[RecordReference]


def _team_summary(roles: list[str]) -> str:
    if not roles:
        return "No team members"
    counts = Counter(roles)
    return f"{plural(len(roles), 'team member')}: " + ", ".join(f"{count} {role}" for role, count in sorted(counts.items()))


async def _list_team_members(context: ToolContext, arguments: ListTeamMembersInput) -> ListTeamMembersOutput:
    application = readable_application(context, application_id_of(context))
    members = await StakeholderService(context.session).list_stakeholders(application.id)
    wanted_roles = {role.value for role in arguments.roles}
    if wanted_roles:
        members = [member for member in members if member.stakeholder_role in wanted_roles]
    counts: Counter[str] = Counter()
    aliased: list[TeamMemberItem] = []
    for member in members:  # numbered over every member of the role, before the list is cut, so an alias never changes
        counts[member.stakeholder_role] += 1
        aliased.append(TeamMemberItem(
            alias=f"{member.stakeholder_role} {counts[member.stakeholder_role]}", stakeholder_role=member.stakeholder_role, recipient_type=member.recipient_type,
            is_active=member.is_active, team_member_status=member.team_member_status,
        ))
    shown, is_truncated = limited(aliased)
    return ListTeamMembersOutput(
        summary=_team_summary([member.stakeholder_role for member in members]), items=shown, item_count=len(shown), total_count=len(aliased), is_truncated=is_truncated,
        records=[RecordReference(kind="team", id=application.id, label=f"{application.name} team", application_id=application.id)],
    )


# ── get_reliability_metrics ───────────────────────────────────────────────────────────────────────────────────────────────────
class ApplicationReliabilityItem(BaseModel):
    application_code: str
    application_name: str
    incidents_opened_count: int
    incidents_resolved_count: int
    time_to_detect: StatResponse = Field(description="Seconds from the first alert to the incident opening; excluded_count counts the incidents with no alert to start from.")
    time_to_resolve: StatResponse = Field(description="Seconds from an incident opening to its resolution.")
    time_to_conclusion: StatResponse = Field(description="Seconds from an investigation's start to its conclusion.")
    investigation_count: int
    rated_count: int
    minimum_rating_sample: int
    share_correct: float | None = Field(description="Percent of the rated investigations marked correct; null below the minimum sample.")
    cost_per_investigation: StatResponse = Field(description="Estimated AI cost per investigation, in the unit of the configured model prices.")


class GetReliabilityMetricsOutput(BaseModel):
    summary: str
    period_start: datetime
    period_end: datetime
    items: list[ApplicationReliabilityItem]
    item_count: int
    total_count: int
    is_truncated: bool
    records: list[RecordReference]


async def _get_reliability_metrics(context: ToolContext, arguments: GetReliabilityMetricsInput) -> GetReliabilityMetricsOutput:
    period_end = utc_now()
    period_start = period_end - timedelta(hours=arguments.lookback_hours)
    all_applications = applications_to_check(context, arguments.application_codes)
    applications, is_truncated = limited(all_applications)
    service = ReliabilityMetricsService(context.session)
    items: list[ApplicationReliabilityItem] = []
    for application in applications:
        await context.ensure_application_reader(application.id)
        context.read_application_ids.add(application.id)
        summary = (await service.overview(context.current_user, application.id, None, period_start, None)).summary
        items.append(ApplicationReliabilityItem(
            application_code=application.code, application_name=application.name, incidents_opened_count=summary.incidents_opened_count,
            incidents_resolved_count=summary.incidents_resolved_count, time_to_detect=summary.time_to_detect, time_to_resolve=summary.time_to_resolve,
            time_to_conclusion=summary.time_to_conclusion, investigation_count=summary.investigation_count, rated_count=summary.ratings.rated_count,
            minimum_rating_sample=summary.ratings.minimum_sample, share_correct=summary.ratings.share_correct,
            cost_per_investigation=summary.ai_usage.cost.per_investigation,
        ))
    opened = sum(item.incidents_opened_count for item in items)
    resolved = sum(item.incidents_resolved_count for item in items)
    return GetReliabilityMetricsOutput(
        summary=f"{opened} incidents opened and {resolved} resolved {window_words(arguments.lookback_hours)}" if items else "No applications to measure",
        period_start=period_start, period_end=period_end, items=items, item_count=len(items), total_count=len(all_applications), is_truncated=is_truncated,
        records=[RecordReference(kind="application", id=application.id, label=application.name, application_id=application.id) for application in applications],
    )


# ── Registration ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
tool_registry.register(read_tool(
    name="list_team_members", label="Listed the team",
    description=(
        "List the team of one application: each member by role and number (for example sre 1), their notification role, whether they are active and their status "
        "(listed, invited, active or inactive). People are never named or given contact details: refer to them by their alias. Use it to see who is on the team."
    ),
    input_model=ListTeamMembersInput, output_model=ListTeamMembersOutput, presentation=ToolPresentation.RECORD_LIST, authorization=ToolAuthorization.APPLICATION_READER,
    bindable_arguments=frozenset({"application_code"}), application_argument="application_code", executor=_list_team_members, scopes=GLOBAL_SCOPE,
    masking=ToolMasking.MASK_ALL_AND_ALIAS_PEOPLE,
))
tool_registry.register(read_tool(
    name="get_reliability_metrics", label="Read reliability metrics",
    description=(
        "Read the reliability figures of the applications you were given over the last lookback_hours (up to 30 days): incidents opened and resolved, time to detect, "
        "time to resolve, time to conclusion, how often investigations were marked correct and the estimated AI cost per investigation. Each figure carries its sample "
        "size. Use it for questions about how reliable things are and how fast Keigan and the team respond."
    ),
    input_model=GetReliabilityMetricsInput, output_model=GetReliabilityMetricsOutput, presentation=ToolPresentation.METRICS, authorization=ToolAuthorization.SCOPED_APPLICATIONS,
    bindable_arguments=frozenset(), application_argument=None, executor=_get_reliability_metrics, scopes=GLOBAL_SCOPE,
))
