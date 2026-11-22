"""What the person is told when part of Ask Keigan fails (spec 23, section 4.10, decision D6).

Every message names the part that failed, the kind of cause and what the person can do, and carries a reference id. The text comes from the
string tables (``ask_keigan_errors`` in ``resources/i18n/en.json`` and ``ja.json``), never from exception text, so an upstream hostname, key or
stack trace cannot reach the screen (V19). The engine, the tool registry and the controller all classify through this one class.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from keigan.ai.output_sanitizer import sanitize_ai_line
from keigan.config.logging_config import current_correlation_id
from keigan.exceptions.keigan_exceptions import (
    AccessLostMidRunException, AgentToolProtocolException, AgentToolsUnsupportedException, AnswerNotRunningException, AuthenticationException, BusinessValidationException,
    AnswerInProgressException, DuplicateRequestException, ForbiddenException, IntegrationException, LlmAuthenticationException, LlmOutputValidationException, LlmRateLimitedException,
    LlmRequestRejectedException, LlmTimeoutException, LlmUnavailableException, NotAcceptableException, NotFoundException, RateLimitedException, TokenBudgetExceededException,
)
from keigan.utils.string_table import FALLBACK_LANGUAGE_CODE, find_string, string_table

_ERROR_TABLE = "ask_keigan_errors"
_MAXIMUM_PARAMETER_CHARACTERS = 300
_NO_REFERENCE = "none"
INTERNAL_ERROR = "internal_error"


class AskKeiganUserAction(StrEnum):
    """What the person can do about a failure; the message says it in words, the UI uses this to choose its button."""

    TRY_AGAIN = "try_again"
    TRY_AGAIN_AFTER_DELAY = "try_again_after_delay"
    ASK_ADMIN = "ask_admin"
    ASK_FOR_ACCESS = "ask_for_access"
    REPHRASE = "rephrase"
    CHECK_NAME = "check_name"
    WAIT_OR_STOP = "wait_or_stop"
    REPORT = "report"
    ASK_FOLLOW_UP = "ask_follow_up"
    EDIT_QUESTION = "edit_question"
    SIGN_IN = "sign_in"
    RECONNECTS_AUTOMATICALLY = "reconnects_automatically"
    MODEL_RETRIES = "model_retries"
    NONE = "none"


@dataclass(frozen=True)
class AnswerFailure:
    error_code: str
    title: str
    detail: str
    parameters: Mapping[str, str | int]
    is_retryable: bool
    user_action: AskKeiganUserAction


@dataclass(frozen=True)
class _CatalogueEntry:
    is_retryable: bool
    user_action: AskKeiganUserAction
    shows_reference: bool = True  # False for the rows that are not failures (nothing for an admin to look up)


_ENTRIES: dict[str, _CatalogueEntry] = {
    "ai_timeout": _CatalogueEntry(True, AskKeiganUserAction.TRY_AGAIN),
    "ai_rate_limited": _CatalogueEntry(True, AskKeiganUserAction.TRY_AGAIN_AFTER_DELAY),
    "ai_authentication_failed": _CatalogueEntry(False, AskKeiganUserAction.ASK_ADMIN),
    "ai_unavailable": _CatalogueEntry(True, AskKeiganUserAction.TRY_AGAIN),
    "ai_tools_unsupported": _CatalogueEntry(False, AskKeiganUserAction.ASK_ADMIN),
    "ai_tool_protocol_failed": _CatalogueEntry(True, AskKeiganUserAction.TRY_AGAIN),
    "ai_output_invalid": _CatalogueEntry(True, AskKeiganUserAction.TRY_AGAIN),
    "ai_request_rejected": _CatalogueEntry(True, AskKeiganUserAction.TRY_AGAIN),
    "token_budget_exceeded": _CatalogueEntry(False, AskKeiganUserAction.ASK_ADMIN),
    "rate_limited": _CatalogueEntry(True, AskKeiganUserAction.TRY_AGAIN_AFTER_DELAY),
    "answer_in_progress": _CatalogueEntry(False, AskKeiganUserAction.WAIT_OR_STOP),
    "duplicate_request": _CatalogueEntry(False, AskKeiganUserAction.NONE, shows_reference=False),
    "forbidden": _CatalogueEntry(False, AskKeiganUserAction.ASK_FOR_ACCESS),
    "access_lost_mid_run": _CatalogueEntry(False, AskKeiganUserAction.ASK_FOR_ACCESS),
    "tool_failed_source_unavailable": _CatalogueEntry(True, AskKeiganUserAction.TRY_AGAIN),
    "tool_failed_timeout": _CatalogueEntry(True, AskKeiganUserAction.REPHRASE),
    "tool_failed_not_found": _CatalogueEntry(False, AskKeiganUserAction.CHECK_NAME),
    "tool_failed_invalid_arguments": _CatalogueEntry(True, AskKeiganUserAction.MODEL_RETRIES),
    "tool_query_not_answerable": _CatalogueEntry(False, AskKeiganUserAction.REPHRASE),
    "tool_output_invalid": _CatalogueEntry(False, AskKeiganUserAction.REPORT),
    "tool_limit_reached": _CatalogueEntry(False, AskKeiganUserAction.ASK_FOLLOW_UP, shows_reference=False),
    "answer_interrupted": _CatalogueEntry(True, AskKeiganUserAction.TRY_AGAIN),
    "stream_interrupted": _CatalogueEntry(True, AskKeiganUserAction.RECONNECTS_AUTOMATICALLY, shows_reference=False),
    "validation_failed": _CatalogueEntry(False, AskKeiganUserAction.EDIT_QUESTION),
    INTERNAL_ERROR: _CatalogueEntry(True, AskKeiganUserAction.REPORT),
    "tool_not_available": _CatalogueEntry(False, AskKeiganUserAction.MODEL_RETRIES),
    "not_found": _CatalogueEntry(False, AskKeiganUserAction.CHECK_NAME),
    "authentication_required": _CatalogueEntry(False, AskKeiganUserAction.SIGN_IN),
    "cancelled": _CatalogueEntry(False, AskKeiganUserAction.NONE, shows_reference=False),  # the person stopped the answer: not a failure
    "answer_not_running": _CatalogueEntry(False, AskKeiganUserAction.NONE, shows_reference=False),  # Stop was asked for an answer that had already finished
}
_CODE_ALIASES = {"access_denied": "forbidden"}  # one row in the spec table, two names in the code
# Exceptions whose own error_code decides the row, ahead of the class (a QueryNotAnswerableError is a validation exception, but its text is the row).
_CODE_BY_EXCEPTION_ERROR_CODE = {"query_not_answerable": "tool_query_not_answerable"}
# Most specific class first: the first isinstance match wins.
_CODE_BY_EXCEPTION_CLASS: tuple[tuple[type[Exception], str], ...] = (
    (AgentToolsUnsupportedException, "ai_tools_unsupported"),
    (AgentToolProtocolException, "ai_tool_protocol_failed"),
    (LlmTimeoutException, "ai_timeout"),
    (LlmRateLimitedException, "ai_rate_limited"),
    (LlmAuthenticationException, "ai_authentication_failed"),
    (LlmRequestRejectedException, "ai_request_rejected"),
    (LlmUnavailableException, "ai_unavailable"),
    (LlmOutputValidationException, "ai_output_invalid"),
    (TokenBudgetExceededException, "token_budget_exceeded"),
    (RateLimitedException, "rate_limited"),
    (AccessLostMidRunException, "access_lost_mid_run"),
    (ForbiddenException, "forbidden"),
    (NotFoundException, "not_found"),
    (AuthenticationException, "authentication_required"),
    (DuplicateRequestException, "duplicate_request"),
    (AnswerNotRunningException, "answer_not_running"),
    (AnswerInProgressException, "answer_in_progress"),  # not ConflictException: another conflict (a duplicate upload, a linked record) is not "an answer is running"
    (IntegrationException, "tool_failed_source_unavailable"),
    (BusinessValidationException, "validation_failed"),
    (NotAcceptableException, "validation_failed"),
)
# The exception's own user-facing text (written by Keigan, see user_facing_errors) is the parameter of these rows.
_PARAMETER_FOR_EXCEPTION_TEXT = {"validation_failed": "fieldMessage", "tool_query_not_answerable": "reason"}

logger = logging.getLogger(__name__)


class AskKeiganErrorCatalogue:
    @staticmethod
    def error_codes() -> set[str]:
        return set(_ENTRIES)

    @staticmethod
    def is_retryable(error_code: str) -> bool:
        return _entry_for(error_code)[1].is_retryable

    @staticmethod
    def code_for_exception(exception: Exception) -> str:
        """The row an exception belongs to; anything the table does not name (and the bare ``KeiganException``) is ``internal_error``."""
        mapped_by_error_code = _CODE_BY_EXCEPTION_ERROR_CODE.get(getattr(exception, "error_code", ""))
        if mapped_by_error_code:
            return mapped_by_error_code
        return next((error_code for exception_class, error_code in _CODE_BY_EXCEPTION_CLASS if isinstance(exception, exception_class)), INTERNAL_ERROR)

    @classmethod
    def describe_exception(cls, exception: Exception, parameters: Mapping[str, Any] | None = None, language_code: str | None = None) -> AnswerFailure:
        """Classify ``exception`` and render its row. Only the text Keigan wrote for the person is used; upstream text never is."""
        error_code = cls.code_for_exception(exception)
        parameters_for_row = dict(parameters or {})
        text_parameter = _PARAMETER_FOR_EXCEPTION_TEXT.get(error_code)
        if text_parameter and text_parameter not in parameters_for_row:
            parameters_for_row[text_parameter] = getattr(exception, "detail", "")
        if isinstance(exception, LlmRateLimitedException) and exception.retry_after_seconds is not None:
            parameters_for_row.setdefault("retryAfterSeconds", exception.retry_after_seconds)  # the provider's own delay: the caller does not have to know it
        return cls.describe(error_code, parameters_for_row, language_code)

    @staticmethod
    def describe(error_code: str, parameters: Mapping[str, Any] | None = None, language_code: str | None = None) -> AnswerFailure:
        """The message for ``error_code`` in the person's language. A code the table does not know is reported as ``internal_error``, never raised."""
        resolved_code, entry = _entry_for(error_code)
        clean_parameters = {name: _clean_parameter(value) for name, value in (parameters or {}).items() if value is not None}
        reference = clean_parameters.get("reference") or current_correlation_id()
        if reference:
            clean_parameters["reference"] = reference
        fallbacks = {name: find_string(language_code, f"{_ERROR_TABLE}.fallbacks.{name}") or "" for name in string_table(FALLBACK_LANGUAGE_CODE)[_ERROR_TABLE]["fallbacks"]}
        values = {**fallbacks, "reference": _NO_REFERENCE, **clean_parameters}
        title = _render(language_code, f"{_ERROR_TABLE}.{resolved_code}.title", values)
        detail = _render(language_code, f"{_ERROR_TABLE}.{resolved_code}.detail", values)
        if reference and entry.shows_reference and "{reference}" not in (find_string(language_code, f"{_ERROR_TABLE}.{resolved_code}.detail") or ""):
            detail = f"{detail} {_render(language_code, f'{_ERROR_TABLE}.reference_suffix', values)}"
        return AnswerFailure(
            error_code=resolved_code, title=title, detail=detail, parameters=clean_parameters, is_retryable=entry.is_retryable, user_action=entry.user_action,
        )


def _entry_for(error_code: str) -> tuple[str, _CatalogueEntry]:
    resolved_code = _CODE_ALIASES.get(error_code, error_code)
    if resolved_code not in _ENTRIES:
        logger.error("Ask Keigan error code %s has no catalogue entry; reporting an internal error instead.", error_code)
        resolved_code = INTERNAL_ERROR
    return resolved_code, _ENTRIES[resolved_code]


def _clean_parameter(value: Any) -> str | int:
    """Numbers stay numbers; text becomes one sanitised, bounded line (no markup, links or line breaks reach the message)."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return value
    return sanitize_ai_line(str(value), maximum_characters=_MAXIMUM_PARAMETER_CHARACTERS)


def _render(language_code: str | None, dotted_path: str, values: Mapping[str, Any]) -> str:
    template = find_string(language_code, dotted_path) or dotted_path
    return template.format_map(values)
