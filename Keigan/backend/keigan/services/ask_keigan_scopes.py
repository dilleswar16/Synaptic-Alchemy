"""The scope of one Ask Keigan answer: which tools, arguments, context, citation codes, limits and budget it gets (spec 23, 4.4.2).

``ScopeProfile`` is the only thing the engine and the tool registry know about where a question was asked. Both scopes are built here: the investigation scope
(one application and one investigation, fixed by the scope) and the global scope of the Keigan AI chat page (the applications the person can read, narrowed to the
conversation's applications; every tool registered for the scope; no bound arguments and no digest).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.ask_keigan_mock_planner import AskKeiganFeature
from keigan.ai.llm_gateway import PromptSection
from keigan.ai.prompt_library import sanitize_prompt_value
from keigan.ai.tool_registry import AskKeiganScope, ToolDefinition, tool_registry
from keigan.config.settings import get_settings
from keigan.entities.status_values import ConversationScope
from keigan.security.current_user import CurrentUser
from keigan.services import ask_keigan_tools  # noqa: F401 — importing it registers the tools the scopes offer
from keigan.services.ask_keigan_investigation_context import load_investigation_context
from keigan.services.ask_keigan_run_state import AnswerCitation
from keigan.services.authorization_service import AuthorizationService
from keigan.services.investigation_service import InvestigationService
from keigan.utils.time_utils import utc_now

INVESTIGATION_PROMPT_KEY = "ask_keigan_investigation"
INVESTIGATION_CITATION_PREFIXES = frozenset({"T", "E", "R"})  # tool calls, evidence, runbooks
GLOBAL_PROMPT_KEY = "ask_keigan_global"
GLOBAL_CITATION_PREFIXES = frozenset({"T"})  # tool calls only: the global scope has no evidence or runbook codes of its own


@dataclass(frozen=True)
class ApplicationRef:
    id: str
    code: str
    name: str


@dataclass(frozen=True)
class ScopeProfile:
    scope: AskKeiganScope
    conversation_scope: ConversationScope  # stored on the run
    prompt_key: str
    feature_name: AskKeiganFeature  # usage accounting and the offline planner are keyed by it
    readable_applications: tuple[ApplicationRef, ...]  # already intersected with the conversation's scope
    offered_tools: tuple[ToolDefinition, ...]  # the registry's tools for the scope, minus withheld tools; none when nothing is readable
    bound_arguments: Mapping[str, str]  # arguments the scope fixes, so the model never chooses them
    context_sections: tuple[PromptSection, ...]  # untrusted context sent with every question (the investigation digest)
    operating_notes_text: str | None  # the application team's notes; the engine masks them and sends them as untrusted guidance
    accepted_citation_prefixes: frozenset[str]
    reference_citations: Mapping[str, AnswerCitation]  # records the context names (evidence and runbooks) that an answer may cite without a tool call
    budget_application_id: str | None  # one application: its token budget; several: the person's
    maximum_tool_calls: int
    prompt_variables: Mapping[str, str]  # trusted values rendered into the system prompt
    investigation_id: str | None = None
    withheld_tool_names: frozenset[str] = field(default_factory=frozenset)

    def application_named(self, application_code: str) -> ApplicationRef | None:
        return next((application for application in self.readable_applications if application.code == application_code), None)

    def snapshot(self) -> dict[str, Any]:
        """The point-in-time record stored with the run (``scope_snapshot_json``)."""
        return {
            "scope": self.scope.value, "applications": [{"id": application.id, "code": application.code, "name": application.name} for application in self.readable_applications],
            "boundArguments": dict(self.bound_arguments), "withheldTools": sorted(self.withheld_tool_names),
        }


def bound_argument_names(tool: ToolDefinition, bound_arguments: Mapping[str, str]) -> tuple[str, ...]:
    """The arguments of ``tool`` that the scope fixed (so the screen can show them as set by the scope and the model never chose them)."""
    return tuple(sorted(tool.bindable_arguments & bound_arguments.keys()))


def offered_tools_for(scope: AskKeiganScope, readable_applications: Sequence[ApplicationRef], withheld_tool_names: frozenset[str]) -> tuple[ToolDefinition, ...]:
    """A person who can read no application gets no tools at all (and the engine answers without calling a model)."""
    if not readable_applications:
        return ()
    return tuple(tool for tool in tool_registry.tools_for(scope) if tool.name not in withheld_tool_names)


async def build_investigation_profile(
    session: AsyncSession, current_user: CurrentUser, investigation_id: str, withheld_tool_names: frozenset[str] = frozenset(),
) -> ScopeProfile:
    """The profile for questions about one investigation. Raises ``NotFoundException`` or ``ForbiddenException`` when the person may not read it, before any model call.

    ``withheld_tool_names`` are tools the caller does not offer in this answer (the Teams room withholds ``query_logs`` from people who are not application admins)."""
    investigation = await InvestigationService(session).load_readable_investigation(current_user, investigation_id)
    context = await load_investigation_context(session, investigation)
    application = ApplicationRef(context.application.application_id, context.application.application_code, context.application.application_name)
    return ScopeProfile(
        scope=AskKeiganScope.INVESTIGATION, conversation_scope=ConversationScope.INVESTIGATION, prompt_key=INVESTIGATION_PROMPT_KEY, feature_name=AskKeiganFeature.INVESTIGATION,
        readable_applications=(application,), offered_tools=offered_tools_for(AskKeiganScope.INVESTIGATION, (application,), withheld_tool_names),
        bound_arguments={"application_code": application.code, "investigation_id": investigation.investigation_id},
        context_sections=(PromptSection("Investigation context", context.digest_markdown, is_untrusted=True, source_label=f"investigation:{investigation.investigation_id}"),),
        operating_notes_text=context.application.operating_notes_text, accepted_citation_prefixes=INVESTIGATION_CITATION_PREFIXES,
        reference_citations={**context.evidence_citations, **context.runbook_citations}, budget_application_id=application.id,
        maximum_tool_calls=get_settings().ask_keigan_max_tool_calls_investigation, prompt_variables={"application_name": application.name}, investigation_id=investigation.investigation_id,
        withheld_tool_names=withheld_tool_names,
    )


async def build_global_profile(session: AsyncSession, current_user: CurrentUser, conversation_application_ids: Sequence[str]) -> ScopeProfile:
    """The profile for questions on the Keigan AI chat page: the applications the person can read now, narrowed to the conversation's applications when it names some.

    A conversation whose applications the person can no longer read gets none (never everything else they can read): the engine then answers that there is nothing to look at,
    without calling a model.
    """
    authorization = AuthorizationService(session)
    roles_by_application_id = await authorization.application_roles(current_user)
    scoped_application_ids = await authorization.scoped_application_ids(current_user, list(conversation_application_ids))
    applications = tuple(sorted(
        (ApplicationRef(role.application_id, role.application_code, role.application_name) for role in (roles_by_application_id[application_id] for application_id in scoped_application_ids)),
        key=lambda application: application.code,
    ))
    return ScopeProfile(
        scope=AskKeiganScope.GLOBAL, conversation_scope=ConversationScope.KEIGAN_AI_CHAT, prompt_key=GLOBAL_PROMPT_KEY, feature_name=AskKeiganFeature.GLOBAL,
        readable_applications=applications, offered_tools=offered_tools_for(AskKeiganScope.GLOBAL, applications, frozenset()), bound_arguments={}, context_sections=(),
        operating_notes_text=None, accepted_citation_prefixes=GLOBAL_CITATION_PREFIXES, reference_citations={}, budget_application_id=applications[0].id if len(applications) == 1 else None,
        maximum_tool_calls=get_settings().ask_keigan_max_tool_calls_global,
        prompt_variables={"application_list": _application_list(applications), "current_date": utc_now().date().isoformat()},
    )


def _application_list(applications: Sequence[ApplicationRef]) -> str:
    """One ``code — name`` line per application, cleaned like every user-chosen name that is rendered into a system prompt."""
    return "\n".join(f"{sanitize_prompt_value(application.code)} — {sanitize_prompt_value(application.name)}" for application in applications)
