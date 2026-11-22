"""Calling an Ask Keigan tool the way the engine does, as a given person, for the tests of the tools (spec 23, 4.5.3 and 9.2)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import select

from keigan.ai.llm_gateway import LlmUsageContext
from keigan.ai.tool_registry import AskKeiganScope, ToolContext, ToolDefinition, ToolOutcome, tool_registry
from keigan.config.database_config import open_session
from keigan.entities.application_entities import Application
from keigan.security.current_user import CurrentUser
from keigan.services.authorization_service import AuthorizationService
from keigan.utils.pii_masker import PiiMasker


def user(user_principal_name: str, *group_names: str, is_admin: bool = False) -> CurrentUser:
    return CurrentUser(user_principal_name, user_principal_name, user_principal_name, frozenset(group_names), frozenset(), is_admin)


ADMIN = user("keigan.admin@keigan.local", "KEIGAN_admin", is_admin=True)
CLMJP_READER = user("clmjp.reader@keigan.local", "CLMJP_reader")
CLMJP_AND_PAYAU_READER = user("rui.reader@keigan.local", "CLMJP_reader", "PAYAU_reader")
NO_ACCESS = user("noa.noaccess@keigan.local")


@dataclass(frozen=True)
class ApplicationRef:
    id: str
    code: str
    name: str


@dataclass(frozen=True)
class Profile:
    scope: AskKeiganScope
    readable_applications: tuple[ApplicationRef, ...]
    offered_tools: tuple[ToolDefinition, ...]
    bound_arguments: dict[str, Any]


class ProgressLog:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, name: str, details: dict[str, Any]) -> None:
        self.events.append((name, details))


async def run_tool(
    tool_name: str, arguments: dict[str, Any], current_user: CurrentUser, *, bound: dict[str, Any] | None = None, scope: AskKeiganScope = AskKeiganScope.INVESTIGATION,
    progress: ProgressLog | None = None, citation_code: str = "T1", profile_user: CurrentUser | None = None,
) -> ToolOutcome:
    """One tool call the way the engine makes it: a fresh session, the person's readable applications, the person's own reader check.

    ``profile_user`` is the person the profile was built for when the call runs as someone else: the access the profile saw is gone by the time the tool runs.
    """
    current_user = replace(current_user, application_roles_by_application_id=None)  # roles are cached per request; every call here is a new request
    async with open_session() as session:
        authorization = AuthorizationService(session)
        readable_ids = await authorization.readable_application_ids(replace(profile_user or current_user, application_roles_by_application_id=None))
        applications = (await session.scalars(select(Application).where(Application.application_id.in_(readable_ids)).order_by(Application.application_code))).all()
        profile = Profile(scope, tuple(ApplicationRef(row.application_id, row.application_code, row.application_name) for row in applications), tuple(tool_registry.tools_for(scope)), bound or {})
        context = ToolContext(
            current_user=current_user, profile=profile, session=session, masker=PiiMasker(), usage_context=LlmUsageContext(requested_by_user_principal_name=current_user.user_principal_name),
            report_progress=progress or ProgressLog(), ensure_application_reader=lambda application_id: authorization.ensure_application_reader(current_user, application_id), citation_code=citation_code,
        )
        return await tool_registry.execute_by_name(tool_name, context, arguments)
