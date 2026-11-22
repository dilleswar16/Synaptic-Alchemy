"""The registry of read-only tools Ask Keigan offers a model (spec 23, section 4.5).

Pure declarations and protocols: nothing here imports a service, a provider or the gateway, so a new tool (or a tool source such as an MCP server
or a code repository) is one registration and the engine, the trace and the chat screen do not change. ``execute`` is the single place that
binds arguments, validates them, checks that the person may read the target, runs the tool inside the read-only guard under a time limit,
turns every failure into a specific outcome, masks the output and builds the text the model sees. It never raises.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from itertools import chain
from typing import TYPE_CHECKING, Any, Literal, Protocol

from pydantic import BaseModel, PydanticUserError, ValidationError
from pydantic.errors import PydanticInvalidForJsonSchema
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import ORMExecuteState, Session

from keigan.ai.ask_keigan_errors import AskKeiganErrorCatalogue
from keigan.ai.output_sanitizer import sanitize_ai_line
from keigan.ai.prompt_safety import assess_prompt_injection, spotlight
from keigan.config.settings import get_settings
from keigan.entities.platform_entities import AuditEvent
from keigan.entities.status_values import ChatRunStepStatus
from keigan.exceptions.keigan_exceptions import IntegrationException, KeiganException, NotFoundException, TokenBudgetExceededException
from keigan.utils.pii_masker import PiiMasker
from keigan.utils.string_table import find_string, translate

if TYPE_CHECKING:
    from keigan.ai.llm_gateway import LlmUsageContext
    from keigan.security.current_user import CurrentUser

logger = logging.getLogger(__name__)

MAXIMUM_TOOL_NAME_CHARACTERS = 64  # the longest legal tool name; a name the model made up is shown cut to this length
TOOL_NAME_PATTERN = re.compile(rf"^[a-z][a-z0-9_]{{2,{MAXIMUM_TOOL_NAME_CHARACTERS - 1}}}$")
MAXIMUM_DESCRIPTION_CHARACTERS = 1024
# The only business rows a tool may add (add, never change or delete): the audit row of a log query (``ai.query.execute``). Model usage rows are written by the gateway in its own session.
READ_ONLY_GUARD_PERMITTED_ENTITIES: frozenset[type] = frozenset({AuditEvent})
_MODEL_VIEW_TRUNCATION_MARKER = "[truncated: {omitted_characters} more characters]"


class AskKeiganScope(StrEnum):
    GLOBAL = "global"
    INVESTIGATION = "investigation"


class ToolOutcomeCode(StrEnum):
    """The low-cardinality ``outcome_code`` of a call the registry ended without an output (stored on the step and sent to the screen). A failure of the model call inside a tool
    keeps its own catalogue code instead."""

    ACCESS_DENIED = "access_denied"
    INVALID_ARGUMENTS = "invalid_arguments"
    NOT_FOUND = "not_found"
    SOURCE_UNAVAILABLE = "source_unavailable"
    TIMEOUT = "timeout"
    QUERY_NOT_ANSWERABLE = "query_not_answerable"
    OUTPUT_INVALID = "output_invalid"
    INTERNAL_ERROR = "internal_error"
    TOOL_NOT_AVAILABLE = "tool_not_available"


class ToolProgressStage(StrEnum):
    """The ``stage`` of a ``tool.progress`` event; the screen words each one in ``chat:tool.progress.<stage>``."""

    QUERY_GENERATED = "query_generated"


class ToolAccess(StrEnum):
    READ = "read"  # the only member, on purpose: a write tool cannot be declared (spec 9.1)


class ToolPresentation(StrEnum):
    """How the generic UI renders the output; no per-tool UI code is needed."""

    RECORD_LIST = "record_list"
    RECORD = "record"
    METRICS = "metrics"
    SERIES = "series"
    QUERY_RESULT = "query_result"
    PASSAGES = "passages"
    GRAPH = "graph"


class ToolAuthorization(StrEnum):
    APPLICATION_READER = "application_reader"  # the tool names one application; execute() checks the person may read it
    SCOPED_APPLICATIONS = "scoped_applications"  # list tool: the service method intersects with the person's applications
    RECORD_OWNER_APPLICATION = "record_owner_application"  # the tool loads a record; the service checks reader access on its application


class ToolMasking(StrEnum):
    MASK_ALL = "mask_all"
    MASK_ALL_AND_ALIAS_PEOPLE = "mask_all_and_alias_people"  # masked like MASK_ALL; the tool's executor also replaces display names with role aliases (spec D2)


class ToolRegistrationError(Exception):
    """A tool declaration breaks a rule of spec 4.5.2. Raised at import time so a bad tool never ships."""


class ReadOnlyViolation(Exception):
    """A tool tried to create, change or delete a business row. This is a bug in the tool, never a user error."""


class SourceName(StrEnum):
    """The systems a tool can fail to read; the person sees each one in plain words in their language (``ask_keigan_tools.sources.<value>`` in the string tables)."""

    ACTIVITY_LOG = "activity_log"
    LOG_SOURCE = "log_source"  # needs a ``subject``: the service whose logs they are


class RecordKindName(StrEnum):
    """The records a tool can fail to find; shown in plain words in the person's language (``ask_keigan_tools.record_kinds.<value>``)."""

    INVESTIGATION = "investigation"
    EVIDENCE_ITEM = "evidence_item"
    SERVICE = "service"
    INCIDENT = "incident"
    ALERT_GROUP = "alert_group"
    SLO = "slo"


class ToolSourceUnavailableError(IntegrationException):
    """The system behind a tool could not be read. The message the person sees is built from ``source`` (and ``subject``) in their language, never from this text."""

    def __init__(self, source: SourceName, subject: str | None = None):
        super().__init__(f"The source {source.value} could not be read.")
        self.source = source
        self.subject = subject


class ToolRecordNotFoundError(NotFoundException):
    """The record the tool was asked for does not exist. The message the person sees is built from ``record_kind`` in their language, never from this text."""

    def __init__(self, record_kind: RecordKindName):
        super().__init__(f"The {record_kind.value} was not found.")
        self.record_kind = record_kind


RecordKind = Literal["incident", "investigation", "evidence", "alert_group", "slo", "signal", "runbook", "knowledge_document", "application", "service", "topology", "team"]


class RecordReference(BaseModel):
    """A record a tool result is about; it drives "Open in Keigan" and the audit trail."""

    kind: RecordKind
    id: str
    label: str
    application_id: str


class ApplicationReference(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def code(self) -> str: ...
    @property
    def name(self) -> str: ...


class ToolScopeProfile(Protocol):
    """What the registry needs from a scope profile (``ScopeProfile`` in ``services/ask_keigan_scopes.py`` satisfies it)."""

    @property
    def scope(self) -> AskKeiganScope: ...
    @property
    def readable_applications(self) -> Sequence[ApplicationReference]: ...
    @property
    def offered_tools(self) -> Sequence["ToolDefinition"]: ...
    @property
    def bound_arguments(self) -> Mapping[str, Any]: ...


@dataclass
class ToolContext:
    """Built by the engine for each tool call."""

    current_user: "CurrentUser"
    profile: ToolScopeProfile
    session: AsyncSession  # a fresh session per tool call; execute() wraps it in the read-only guard
    masker: PiiMasker  # one per answer run, so <EMAIL_1> is the same person in every step
    usage_context: "LlmUsageContext"  # for tools that call the model (query_logs)
    report_progress: Callable[[str, dict[str, Any]], Awaitable[None]]  # emits tool.progress (for example the generated query)
    ensure_application_reader: Callable[[str], Awaitable[None]]  # raises ForbiddenException unless the person may read the application (AuthorizationService, supplied by the engine)
    citation_code: str = "T0"  # the T<n> of this call, used in the untrusted-data label
    language_code: str | None = None  # the person's language: every message of the outcome is worded in it (English when the server has no table for it)
    resolved_application_id: str | None = None  # set by execute() when the tool names an application
    read_application_ids: set[str] = field(default_factory=set)  # the applications whose data the call read: execute() adds the one the tool names, a tool that covers several adds each of them
    deadline: float = 0.0  # monotonic time by which the tool must finish; set by execute()


ToolExecutor = Callable[[ToolContext, Any], Awaitable[BaseModel]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str  # model-facing, snake_case, unique
    version: int  # bump when the input or output meaning changes (stored per step; replay uses it)
    source: str  # "keigan" today; "mcp:<server>" or "code_repository" later
    label: str  # plain-words label in the past tense ("Opened evidence"); the screen falls back to it
    label_key: str  # frontend string key "chat:tools.<name>.label"
    description: str  # what the model reads: when to use it, what it returns, its limits
    access: ToolAccess
    scopes: frozenset[AskKeiganScope]
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    presentation: ToolPresentation
    authorization: ToolAuthorization
    bindable_arguments: frozenset[str]  # arguments a scope may bind (removed from the model-facing schema when bound)
    application_argument: str | None  # the argument naming the application ("application_code"), if any
    output_model_characters: int | None  # per-tool cap on text sent to the model; None = ASK_KEIGAN_TOOL_OUTPUT_MODEL_CHARACTERS
    list_item_limit: int | None  # per-tool cap on list items; None = ASK_KEIGAN_TOOL_LIST_ITEM_LIMIT
    masking: ToolMasking
    executor: ToolExecutor


class ToolSource(Protocol):
    """In-process Keigan services today; an MCP server or a code repository later (spec 4.5.5)."""

    source_name: str

    def definitions(self) -> Sequence[ToolDefinition]: ...


@dataclass
class ToolOutcome:
    """What ``execute`` returns; the engine never sees provider or service types."""

    status: ChatRunStepStatus
    output: BaseModel | None  # the validated, masked output_model instance
    application_id: str | None
    records: list[RecordReference]
    outcome_code: str | None  # a ToolOutcomeCode, or the catalogue code of a failure of the model call inside the tool
    outcome_message: str | None  # user-safe sentence from the error catalogue; never upstream text
    model_view_text: str | None = None  # masked compact JSON sent to the model, without the untrusted-data wrapper (stored with its SHA-256)
    model_view_sha256: str | None = None
    model_message: str = ""  # exactly what the model receives: the wrapped model view, or a one-line outcome for a failed call
    injection_flagged: bool = False
    applications_read: frozenset[str] = frozenset()  # every application whose data reached the model through this call (a call that gave no data read none): who may see the answer follows from it


# The list field of each list-like presentation; the registry caps it and keeps item_count and is_truncated honest.
_LIST_FIELD_BY_PRESENTATION = {ToolPresentation.RECORD_LIST: "items", ToolPresentation.PASSAGES: "passages"}
_LIST_COUNT_FIELDS = ("item_count", "total_count", "is_truncated")
# How a failure the executor raised becomes a step status, an outcome code and the catalogue row that words it.
_OUTCOME_BY_CATALOGUE_CODE: dict[str, tuple[ChatRunStepStatus, ToolOutcomeCode, str]] = {
    "forbidden": (ChatRunStepStatus.REFUSED, ToolOutcomeCode.ACCESS_DENIED, "forbidden"),
    "not_found": (ChatRunStepStatus.FAILED, ToolOutcomeCode.NOT_FOUND, "tool_failed_not_found"),
    "tool_query_not_answerable": (ChatRunStepStatus.FAILED, ToolOutcomeCode.QUERY_NOT_ANSWERABLE, "tool_query_not_answerable"),
    "tool_failed_source_unavailable": (ChatRunStepStatus.FAILED, ToolOutcomeCode.SOURCE_UNAVAILABLE, "tool_failed_source_unavailable"),
    "validation_failed": (ChatRunStepStatus.FAILED, ToolOutcomeCode.INVALID_ARGUMENTS, "tool_failed_invalid_arguments"),
}
_TOOL_LABEL_TABLE = "ask_keigan_tools"  # string tables: ask_keigan_tools.<tool name>.label, for the languages the server has tables for
_RUNNING_TOOL_STEP = "ask_keigan_answers.steps.running_tool"


def exhausted_budget_owner(failure: Exception, applications: Sequence[ApplicationReference]) -> str | None:
    """The name of the application whose daily AI budget ran out, for the message. None for the person's own budget (the message then says "your account"), and for an
    application the scope does not list."""
    if not isinstance(failure, TokenBudgetExceededException) or failure.application_id is None:
        return None
    return next((application.name for application in applications if application.id == failure.application_id), None)


def tool_label_in(definition: ToolDefinition, language_code: str | None) -> str:
    """The label of a tool in the person's language; the (English) label of its declaration when the string tables have none, as for a tool added later."""
    return find_string(language_code, f"{_TOOL_LABEL_TABLE}.{definition.name}.label") or definition.label


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}

    # ── Declaration ───────────────────────────────────────────────────────────────────────────────────────────────────
    def register(self, definition: ToolDefinition) -> None:
        problems = _registration_problems(definition)
        if definition.name in self._definitions:
            problems.append(f"a tool named {definition.name} is already registered")
        if problems:
            raise ToolRegistrationError(f"Tool {definition.name!r} cannot be registered: " + "; ".join(problems))
        self._definitions[definition.name] = definition

    def register_source(self, source: ToolSource) -> None:
        for definition in source.definitions():
            self.register(definition)

    def all_tools(self) -> list[ToolDefinition]:
        return list(self._definitions.values())

    def definition_named(self, tool_name: str) -> ToolDefinition | None:
        return self._definitions.get(tool_name)

    def tools_for(self, scope: AskKeiganScope) -> list[ToolDefinition]:
        return [definition for definition in self._definitions.values() if scope in definition.scopes]

    def model_schema(self, definition: ToolDefinition, profile: ToolScopeProfile) -> dict[str, Any]:
        """The JSON Schema the model sees: arguments the scope binds are removed, and the application argument lists exactly the readable codes."""
        schema = definition.input_model.model_json_schema()
        schema.pop("title", None)
        properties = schema.get("properties", {})
        bound_names = _bound_names(definition, profile)
        for bound_name in bound_names:
            properties.pop(bound_name, None)
        schema["required"] = [name for name in schema.get("required", []) if name not in bound_names]
        if not schema["required"]:
            del schema["required"]
        if definition.application_argument and definition.application_argument in properties:
            properties[definition.application_argument] = {**properties[definition.application_argument], "enum": [application.code for application in profile.readable_applications]}
        return schema

    def catalog_hash(self, definitions: Sequence[ToolDefinition]) -> str:
        """SHA-256 of the names, versions and model schemas of ``definitions`` (order does not matter), stored with each answer so a replay knows what the model was offered."""
        catalog = [{"name": definition.name, "version": definition.version, "schema": definition.input_model.model_json_schema()} for definition in sorted(definitions, key=lambda item: item.name)]
        return hashlib.sha256(json.dumps(catalog, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    # ── Execution ─────────────────────────────────────────────────────────────────────────────────────────────────────
    async def execute_by_name(self, tool_name: str, context: ToolContext, raw_arguments: Mapping[str, Any]) -> ToolOutcome:
        """Run the tool the model asked for by name. A name that is not among the tools this answer was offered is refused, never run."""
        offered = {definition.name: definition for definition in context.profile.offered_tools}
        definition = offered.get(tool_name)
        if definition is None:
            return _refused_outcome(sanitize_ai_line(tool_name, maximum_characters=MAXIMUM_TOOL_NAME_CHARACTERS), tool_name, context.language_code)
        return await self.execute(definition, context, raw_arguments)

    async def execute(self, definition: ToolDefinition, context: ToolContext, raw_arguments: Mapping[str, Any]) -> ToolOutcome:
        if definition.name not in {offered.name for offered in context.profile.offered_tools}:
            return _refused_outcome(tool_label_in(definition, context.language_code), definition.name, context.language_code)
        try:
            return await self._run(definition, context, raw_arguments)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — a tool failure ends that step, never the answer
            logger.exception("Tool %s failed unexpectedly while running", definition.name)
            return _internal_error_outcome(definition, context.language_code)

    async def _run(self, definition: ToolDefinition, context: ToolContext, raw_arguments: Mapping[str, Any]) -> ToolOutcome:
        # 1. The scope decides the bound arguments: whatever the model sent for them is overwritten.
        arguments = {**raw_arguments, **{name: context.profile.bound_arguments[name] for name in _bound_names(definition, context.profile)}}
        # 2. Validate. The first message goes back to the model so it can correct itself.
        try:
            validated_arguments = definition.input_model.model_validate(arguments)
        except ValidationError as validation_error:
            return _failed_outcome(definition, ChatRunStepStatus.REFUSED, ToolOutcomeCode.INVALID_ARGUMENTS, _invalid_arguments_message(definition, validation_error, context.language_code))
        # 3. The application the tool names must be one the person may read; the check is repeated here, whatever the model-facing schema listed.
        context.resolved_application_id = None
        context.read_application_ids = set()
        if definition.application_argument:
            application_code = getattr(validated_arguments, definition.application_argument, None)
            application = next((candidate for candidate in context.profile.readable_applications if candidate.code == application_code), None)
            if application is None:
                return _failed_outcome(definition, ChatRunStepStatus.REFUSED, ToolOutcomeCode.ACCESS_DENIED, AskKeiganErrorCatalogue.describe("forbidden", language_code=context.language_code).detail)
            try:
                await context.ensure_application_reader(application.id)
            except KeiganException as denial:  # ForbiddenException when access was removed; classified like any other failure of the tool
                return _outcome_for_failure(definition, denial, context)
            context.resolved_application_id = application.id
            context.read_application_ids.add(application.id)
        # 4. Run it inside the read-only guard, under the per-call time limit (this stops one hung call, never a long answer).
        timeout_seconds = get_settings().ask_keigan_tool_timeout_seconds
        context.deadline = asyncio.get_running_loop().time() + timeout_seconds
        try:
            async with read_only_session_guard(context.session):
                output = await asyncio.wait_for(definition.executor(context, validated_arguments), timeout=timeout_seconds)
        except TimeoutError:
            timeout_message = AskKeiganErrorCatalogue.describe(
                "tool_failed_timeout", {"toolLabel": tool_label_in(definition, context.language_code), "seconds": timeout_seconds}, context.language_code,
            ).detail
            return _failed_outcome(definition, ChatRunStepStatus.FAILED, ToolOutcomeCode.TIMEOUT, timeout_message)
        except ReadOnlyViolation:
            logger.error("Tool %s tried to write to the database; the call was stopped (this is a bug in the tool)", definition.name, exc_info=True)
            return _internal_error_outcome(definition, context.language_code)
        except Exception as failure:  # noqa: BLE001
            return _outcome_for_failure(definition, failure, context)
        # 5. Validate, mask and cap the output, then build the model view.
        return _successful_outcome(definition, context, output)


tool_registry = ToolRegistry()


# ── The read-only guard (spec 9.1, layer 2) ───────────────────────────────────────────────────────────────────────────────
def _forbidden_instances(session: Session) -> list[object]:
    """Pending changes a read-only tool may not make: any change to any row, except adding a row of a permitted entity (an audit row is added, never rewritten or deleted)."""
    modified_instances = [instance for instance in session.dirty if session.is_modified(instance)]
    added_but_not_permitted = [instance for instance in session.new if type(instance) not in READ_ONLY_GUARD_PERMITTED_ENTITIES]
    return [*added_but_not_permitted, *modified_instances, *session.deleted]


def _permitted_insert_pattern() -> re.Pattern[str]:
    """``INSERT INTO [schema.]table`` for a permitted entity's table, however the dialect quotes it."""
    table_names = "|".join(re.escape(entity.__table__.name) for entity in READ_ONLY_GUARD_PERMITTED_ENTITIES)  # type: ignore[attr-defined]
    return re.compile(rf'^\s*INSERT\s+INTO\s+(?:[\w\[\]"`]+\.)?[\["`]?(?:{table_names})[\]"`]?[\s(]', re.IGNORECASE)


_PERMITTED_INSERT = _permitted_insert_pattern()
_LEADING_COMMENTS = re.compile(r"^\s*(?:--[^\n]*\n\s*|/\*.*?\*/\s*)*", re.DOTALL)


def _is_permitted_statement(statement: str) -> bool:
    """A tool's statements are SELECTs, and the INSERT of one permitted audit row: nothing else reaches the database, whatever API issued it (ORM, ``text``, the connection)."""
    statement_without_comments = _LEADING_COMMENTS.sub("", statement, count=1)
    return statement_without_comments[:6].upper() == "SELECT" or _PERMITTED_INSERT.match(statement_without_comments) is not None


@asynccontextmanager
async def read_only_session_guard(session: AsyncSession) -> AsyncIterator[None]:
    """Fail the call when it changes or deletes any row, or adds one that is not an audit row, however it is done.

    Three layers, because a tool is code and any one of them can be sidestepped: ``before_flush`` catches ORM changes at every flush; ``do_orm_execute`` catches ORM write
    statements early with a clear message; ``before_cursor_execute`` on the session's connection is the one that cannot be bypassed from the session: it lets through only a
    SELECT and the INSERT of an audit row, so ``session.execute(text("UPDATE ..."))``, ``(await session.connection()).execute(...)`` and an ORM ``delete(AuditEvent)`` are
    stopped before they reach the database. Leaving the block checks once more, because a tool may leave changes pending that the caller would flush later (also after the
    tool failed for another reason). On a violation the session is rolled back, so the change can never be committed.
    """
    sync_session = session.sync_session
    permitted_tables = {entity.__table__ for entity in READ_ONLY_GUARD_PERMITTED_ENTITIES}  # type: ignore[attr-defined]
    connection = (await session.connection()).sync_connection  # the transaction of this session: its statements all go through this connection

    def stop_changed_rows(flushing_session: Session, _flush_context: object, _instances: object) -> None:
        forbidden_instances = _forbidden_instances(flushing_session)
        if forbidden_instances:
            raise ReadOnlyViolation(f"A read-only tool changed {type(forbidden_instances[0]).__name__} rows.")

    def stop_write_statements(execute_state: ORMExecuteState) -> None:
        if execute_state.is_update or execute_state.is_delete or (execute_state.is_insert and getattr(execute_state.statement, "table", None) not in permitted_tables):
            raise ReadOnlyViolation("A read-only tool executed a write statement.")

    def stop_other_statements(_connection: object, _cursor: object, statement: str, _parameters: object, _context: object, _executemany: bool) -> None:
        if not _is_permitted_statement(statement):
            raise ReadOnlyViolation("A read-only tool executed a statement that is neither a SELECT nor the insert of an audit row.")

    event.listen(sync_session, "before_flush", stop_changed_rows)
    event.listen(sync_session, "do_orm_execute", stop_write_statements)
    event.listen(connection, "before_cursor_execute", stop_other_statements)
    try:
        try:
            yield
        except ReadOnlyViolation:
            await session.rollback()
            raise
        except Exception:
            if _forbidden_instances(sync_session):
                await session.rollback()
                raise ReadOnlyViolation("A read-only tool left changed rows pending.") from None
            raise
        if _forbidden_instances(sync_session):
            await session.rollback()
            raise ReadOnlyViolation("A read-only tool left changed rows pending.")
    finally:
        event.remove(sync_session, "before_flush", stop_changed_rows)
        event.remove(sync_session, "do_orm_execute", stop_write_statements)
        event.remove(connection, "before_cursor_execute", stop_other_statements)


# ── Registration checks (spec 4.5.2) ──────────────────────────────────────────────────────────────────────────────────────
def _registration_problems(definition: ToolDefinition) -> list[str]:
    problems: list[str] = []
    if definition.access is not ToolAccess.READ:
        problems.append("only read-only tools can be registered")
    if not TOOL_NAME_PATTERN.match(definition.name):
        problems.append("the name must be snake_case, 3 to 64 characters, starting with a letter")
    if definition.version < 1:
        problems.append("the version must be at least 1")
    if not definition.label.strip():
        problems.append("the label is empty")
    if not definition.description.strip():
        problems.append("the description is empty")
    elif len(definition.description) > MAXIMUM_DESCRIPTION_CHARACTERS:
        problems.append(f"the description is longer than {MAXIMUM_DESCRIPTION_CHARACTERS} characters")
    if not definition.scopes:
        problems.append("the tool is offered in no scope")
    problems += _input_model_problems(definition.input_model)
    if definition.application_argument is not None:
        if definition.application_argument not in definition.input_model.model_fields:
            problems.append(f"application_argument {definition.application_argument!r} is not a field of the input model")
        if definition.application_argument not in definition.bindable_arguments:
            problems.append(f"application_argument {definition.application_argument!r} must be listed in bindable_arguments")
    if definition.authorization is ToolAuthorization.APPLICATION_READER and definition.application_argument is None:
        problems.append("authorization application_reader needs an application_argument")
    problems += [f"bindable argument {name!r} is not a field of the input model" for name in sorted(definition.bindable_arguments - set(definition.input_model.model_fields))]
    problems += _output_model_problems(definition)
    return problems


def _input_model_problems(input_model: type[BaseModel]) -> list[str]:
    if input_model.model_config.get("extra") != "forbid":
        return ["the input model must set extra=\"forbid\""]
    schema = input_model.model_json_schema()
    definitions = schema.get("$defs", {})
    problems: list[str] = []
    for field_name, property_schema in schema.get("properties", {}).items():
        if not property_schema.get("description"):
            problems.append(f"input field {field_name!r} has no description")
        problems += [f"input field {field_name!r}: {problem}" for problem in _unbounded_schema_problems(property_schema, definitions)]
    return problems


def _unbounded_schema_problems(schema: Mapping[str, Any], definitions: Mapping[str, Any]) -> list[str]:
    """Free text and lists the model fills in must have a length limit."""
    if "$ref" in schema:
        return _unbounded_schema_problems(definitions.get(schema["$ref"].rsplit("/", 1)[-1], {}), definitions)
    problems: list[str] = []
    for alternative in chain(schema.get("anyOf", []), schema.get("allOf", [])):
        problems += _unbounded_schema_problems(alternative, definitions)
    schema_type = schema.get("type")
    if schema_type == "string" and not schema.get("enum") and "const" not in schema and "maxLength" not in schema:
        problems.append("a text value has no max_length")
    if schema_type == "array":
        if "maxItems" not in schema:
            problems.append("a list has no max_length")
        problems += _unbounded_schema_problems(schema.get("items", {}), definitions)
    return problems


def _output_model_problems(definition: ToolDefinition) -> list[str]:
    output_fields = definition.output_model.model_fields
    problems: list[str] = []
    try:
        definition.output_model.model_json_schema()
    except (PydanticInvalidForJsonSchema, PydanticUserError):
        problems.append("the output model is not JSON-serialisable")
    if "summary" not in output_fields or output_fields["summary"].annotation is not str:
        problems.append("the output model needs a summary: str field")
    if "records" not in output_fields:
        problems.append("the output model needs a records field (the records the result is about)")
    list_field = _LIST_FIELD_BY_PRESENTATION.get(definition.presentation)
    if list_field:
        problems += [f"a {definition.presentation.value} output needs a {name} field" for name in (list_field, *_LIST_COUNT_FIELDS) if name not in output_fields]
    return problems


# ── Execution helpers ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _bound_names(definition: ToolDefinition, profile: ToolScopeProfile) -> set[str]:
    return set(definition.bindable_arguments) & set(profile.bound_arguments)


def _invalid_arguments_message(definition: ToolDefinition, validation_error: ValidationError, language_code: str | None) -> str:
    first_error = validation_error.errors(include_url=False, include_context=False, include_input=False)[0]
    field_name = ".".join(str(part) for part in first_error["loc"])
    field_message = f"{field_name}: {first_error['msg']}" if field_name else str(first_error["msg"])
    return AskKeiganErrorCatalogue.describe("tool_failed_invalid_arguments", {"toolLabel": tool_label_in(definition, language_code), "fieldMessage": field_message}, language_code).detail


def _failed_outcome(definition: ToolDefinition, status: ChatRunStepStatus, outcome_code: str, outcome_message: str) -> ToolOutcome:
    return ToolOutcome(
        status=status, output=None, application_id=None, records=[], outcome_code=outcome_code, outcome_message=outcome_message,
        model_message=f"{definition.name} {status.value} ({outcome_code}): {outcome_message}",
    )


def _internal_error_outcome(definition: ToolDefinition, language_code: str | None) -> ToolOutcome:
    step_description = translate(language_code, _RUNNING_TOOL_STEP, toolLabel=tool_label_in(definition, language_code))
    message = AskKeiganErrorCatalogue.describe("internal_error", {"stepDescription": step_description}, language_code).detail
    return _failed_outcome(definition, ChatRunStepStatus.FAILED, ToolOutcomeCode.INTERNAL_ERROR, message)


def _outcome_for_failure(definition: ToolDefinition, failure: Exception, context: ToolContext) -> ToolOutcome:
    language_code = context.language_code
    catalogue_code = AskKeiganErrorCatalogue.code_for_exception(failure)
    parameters: dict[str, Any] = {"toolLabel": tool_label_in(definition, language_code), "budgetOwner": exhausted_budget_owner(failure, context.profile.readable_applications)}
    text_parameter = {"validation_failed": "fieldMessage", "tool_query_not_answerable": "reason"}.get(catalogue_code)
    if text_parameter:
        parameters[text_parameter] = getattr(failure, "detail", "")
    if isinstance(failure, ToolSourceUnavailableError):
        parameters["sourceName"] = translate(language_code, f"{_TOOL_LABEL_TABLE}.sources.{failure.source.value}", subject=failure.subject or "")
    if isinstance(failure, ToolRecordNotFoundError):
        parameters["recordKind"] = translate(language_code, f"{_TOOL_LABEL_TABLE}.record_kinds.{failure.record_kind.value}")
    if catalogue_code in _OUTCOME_BY_CATALOGUE_CODE:
        status, outcome_code, message_code = _OUTCOME_BY_CATALOGUE_CODE[catalogue_code]
        return _failed_outcome(definition, status, outcome_code, AskKeiganErrorCatalogue.describe(message_code, parameters, language_code).detail)
    if catalogue_code == "internal_error":
        logger.error("Tool %s failed with an unclassified %s", definition.name, type(failure).__name__, exc_info=failure)
        return _internal_error_outcome(definition, language_code)
    # A failure the model call inside a tool raised (timeout, busy, budget used up) keeps its own row, so the person is told which part failed.
    return _failed_outcome(definition, ChatRunStepStatus.FAILED, catalogue_code, AskKeiganErrorCatalogue.describe(catalogue_code, parameters, language_code).detail)


def _refused_outcome(tool_label: str, tool_name: str, language_code: str | None) -> ToolOutcome:
    message = AskKeiganErrorCatalogue.describe("tool_not_available", {"toolLabel": tool_label}, language_code).detail
    return ToolOutcome(
        status=ChatRunStepStatus.REFUSED, output=None, application_id=None, records=[], outcome_code=ToolOutcomeCode.TOOL_NOT_AVAILABLE, outcome_message=message,
        model_message=f"{sanitize_ai_line(tool_name, maximum_characters=MAXIMUM_TOOL_NAME_CHARACTERS)} refused ({ToolOutcomeCode.TOOL_NOT_AVAILABLE}): {message}",
    )


def _successful_outcome(definition: ToolDefinition, context: ToolContext, output: BaseModel) -> ToolOutcome:
    settings = get_settings()
    try:
        output_values = definition.output_model.model_validate(output).model_dump(mode="json")
        output_values = _cap_list(definition, output_values, definition.list_item_limit or settings.ask_keigan_tool_list_item_limit)
        masked_values = context.masker.mask_value(output_values)
        masked_output = definition.output_model.model_validate(masked_values)
    except ValidationError as validation_error:
        # Only where the mismatch is, never the values: they are customer data.
        logger.error("Tool %s returned data that does not match its output model: %s", definition.name, [error["loc"] for error in validation_error.errors(include_input=False)])
        output_invalid_message = AskKeiganErrorCatalogue.describe("tool_output_invalid", {"toolLabel": tool_label_in(definition, context.language_code)}, context.language_code).detail
        return _failed_outcome(definition, ChatRunStepStatus.FAILED, ToolOutcomeCode.OUTPUT_INVALID, output_invalid_message)
    model_view = json.dumps(masked_values, ensure_ascii=False, separators=(",", ":"), default=str)
    character_limit = definition.output_model_characters or settings.ask_keigan_tool_output_model_characters
    if len(model_view) > character_limit:
        model_view = model_view[:character_limit] + _MODEL_VIEW_TRUNCATION_MARKER.format(omitted_characters=len(model_view) - character_limit)
    is_flagged = assess_prompt_injection(model_view).is_suspicious or bool(masked_values.get("contains_flagged_content")) or bool(masked_values.get("possible_prompt_injection"))
    records = [RecordReference.model_validate(record) for record in masked_values.get("records", [])]
    return ToolOutcome(
        status=ChatRunStepStatus.SUCCEEDED, output=masked_output, application_id=context.resolved_application_id or (records[0].application_id if records else None), records=records,
        outcome_code=None, outcome_message=None, model_view_text=model_view, model_view_sha256=hashlib.sha256(model_view.encode("utf-8")).hexdigest(),
        model_message=spotlight(model_view, f"tool:{definition.name}:{context.citation_code}", maximum_characters=len(model_view) + 1, force_warning=is_flagged), injection_flagged=is_flagged,
        applications_read=frozenset(context.read_application_ids | {record.application_id for record in records}),
    )


def _cap_list(definition: ToolDefinition, output_values: dict[str, Any], item_limit: int) -> dict[str, Any]:
    list_field = _LIST_FIELD_BY_PRESENTATION.get(definition.presentation)
    if list_field is None or len(output_values[list_field]) <= item_limit:
        return output_values
    output_values[list_field] = output_values[list_field][:item_limit]
    output_values["item_count"] = item_limit
    output_values["is_truncated"] = True
    return output_values
