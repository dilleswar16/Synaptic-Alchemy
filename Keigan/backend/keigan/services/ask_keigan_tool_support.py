"""What every Ask Keigan tool module shares (spec 23, sections 5 and 9.2): the registration of a read-only tool, the application checks, and the wording and list limit of outputs.

The tools themselves live in ``ask_keigan_tools`` (investigation tools and the first global ones) and in the modules grouped by domain beside it. Nothing here reads a
service: a helper that needs one belongs in the tool module that uses it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel

from keigan.ai.tool_registry import (
    ApplicationReference, AskKeiganScope, ToolAccess, ToolAuthorization, ToolContext, ToolDefinition, ToolExecutor, ToolMasking, ToolPresentation,
)
from keigan.config.settings import get_settings
from keigan.exceptions.keigan_exceptions import ForbiddenException
from keigan.utils.text_utils import truncate_text
from keigan.utils.time_utils import ensure_utc

MINUTES_PER_HOUR = 60
BOTH_SCOPES = frozenset({AskKeiganScope.GLOBAL, AskKeiganScope.INVESTIGATION})
GLOBAL_SCOPE = frozenset({AskKeiganScope.GLOBAL})


def passage(text: str | None) -> str | None:
    """A text cut to the passage limit, for the text Keigan and the systems write (a runbook's steps, an explanation); nothing when there is none."""
    return truncate_text(text, get_settings().ask_keigan_tool_passage_characters) if text else None


def plural(count: int, noun: str, plural_form: str | None = None) -> str:
    if count == 1:
        return f"{count} {noun}"
    return f"{count} {plural_form or noun + 's'}"


def utc_minute(timestamp: datetime) -> str:
    return f"{ensure_utc(timestamp):%Y-%m-%d %H:%M}"


def window_words(lookback_hours: int) -> str:
    return f"in the last {describe_window(lookback_hours * MINUTES_PER_HOUR)}"


def describe_window(minutes: int) -> str:
    hours, remaining_minutes = divmod(minutes, MINUTES_PER_HOUR)
    if hours == 0:
        return plural(remaining_minutes, "minute")
    if remaining_minutes == 0:
        return plural(hours, "hour")
    return f"{plural(hours, 'hour')} {plural(remaining_minutes, 'minute')}"


def application_id_of(context: ToolContext) -> str:
    """The application the registry resolved and authorized for this call (every tool that uses it declares an ``application_argument``)."""
    if context.resolved_application_id is None:
        raise RuntimeError("The tool registry did not resolve an application for a tool that needs one.")
    return context.resolved_application_id


def list_item_limit() -> int:
    return get_settings().ask_keigan_tool_list_item_limit


def limited[Item](items: Sequence[Item]) -> tuple[list[Item], bool]:
    """The first items up to the configured list limit, and whether any were left out (the caller keeps the full count as ``total_count``)."""
    item_limit = list_item_limit()
    return list(items[:item_limit]), len(items) > item_limit


def readable_application(context: ToolContext, application_id: str) -> ApplicationReference:
    """The application as the scope lists it (its code and name). A record of an application outside the scope of the answer is refused like one the person cannot read: a conversation can narrow the scope below what the person may read."""
    application = next((candidate for candidate in context.profile.readable_applications if candidate.id == application_id), None)
    if application is None:
        raise ForbiddenException("You can't read one of those applications, or it does not exist.")
    return application


def applications_to_check(context: ToolContext, application_codes: list[str]) -> list[ApplicationReference]:
    """The named applications, or every application of the scope when none is named. A code the scope does not list refuses the whole call (never a silent drop)."""
    readable_applications = list(context.profile.readable_applications)
    if not application_codes:
        return readable_applications
    applications_by_code = {application.code: application for application in readable_applications}
    if any(code not in applications_by_code for code in application_codes):
        raise ForbiddenException("You can't read one of those applications, or it does not exist.")
    return [applications_by_code[code] for code in dict.fromkeys(application_codes)]


async def checked_applications(context: ToolContext, application_codes: list[str]) -> list[ApplicationReference]:
    """The applications a list tool covers. Each is checked for the person's reader access right now (access removed during the answer refuses the call) and recorded as read."""
    applications = applications_to_check(context, application_codes)
    for application in applications:
        await context.ensure_application_reader(application.id)
        context.read_application_ids.add(application.id)
    return applications


def read_tool(
    *, name: str, label: str, description: str, input_model: type[BaseModel], output_model: type[BaseModel], presentation: ToolPresentation, authorization: ToolAuthorization,
    bindable_arguments: frozenset[str], application_argument: str | None, executor: ToolExecutor, scopes: frozenset[AskKeiganScope] = BOTH_SCOPES,
    masking: ToolMasking = ToolMasking.MASK_ALL,
) -> ToolDefinition:
    """A tool of this package: read-only, from Keigan's own services, offered in the given scopes (both by default), masked like every other output."""
    return ToolDefinition(
        name=name, version=1, source="keigan", label=label, label_key=f"chat:tools.{name}.label", description=description, access=ToolAccess.READ, scopes=scopes,
        input_model=input_model, output_model=output_model, presentation=presentation, authorization=authorization, bindable_arguments=bindable_arguments,
        application_argument=application_argument, output_model_characters=None, list_item_limit=None, masking=masking, executor=executor,
    )
