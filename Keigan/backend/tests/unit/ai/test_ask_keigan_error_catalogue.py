"""keigan/ai/ask_keigan_errors.py: every Ask Keigan failure says what failed, in every locale, and never shows upstream text (D6, AC-40 to AC-43)."""

from __future__ import annotations

import json
import string

import pytest

from keigan.ai.ask_keigan_errors import AnswerFailure, AskKeiganErrorCatalogue, AskKeiganUserAction
from keigan.ai.user_facing_errors import generic_failure_message
from keigan.config.settings import RESOURCES_DIRECTORY
from keigan.exceptions.keigan_exceptions import (
    AccessLostMidRunException, AgentToolProtocolException, AnswerInProgressException, AnswerRunConflictException, ConflictException, AgentToolsUnsupportedException, BusinessValidationException, ForbiddenException, IntegrationException, KeiganException, LlmRateLimitedException, LlmTimeoutException, NotFoundException,
    TokenBudgetExceededException,
)
from keigan.services import chat_data_query_service  # noqa: F401 — defines QueryNotAnswerableError, a KeiganException subclass

# The 23 rows of spec section 4.10, in table order ("forbidden / access_denied" is one row with two codes), then the codes added for exceptions the table does not name.
SPECIFIED_CODES = [
    "ai_timeout", "ai_rate_limited", "ai_authentication_failed", "ai_unavailable", "ai_tools_unsupported", "ai_tool_protocol_failed", "token_budget_exceeded",
    "rate_limited", "answer_in_progress", "duplicate_request", "forbidden", "access_lost_mid_run", "tool_failed_source_unavailable", "tool_failed_timeout",
    "tool_failed_not_found", "tool_failed_invalid_arguments", "tool_query_not_answerable", "tool_output_invalid", "tool_limit_reached", "answer_interrupted",
    "stream_interrupted", "validation_failed", "internal_error",
]
ADDED_CODES = ["not_found", "authentication_required", "ai_output_invalid", "ai_request_rejected", "tool_not_available", "cancelled", "answer_not_running"]
CODES_WITHOUT_A_REFERENCE = {"duplicate_request", "tool_limit_reached", "stream_interrupted", "cancelled", "answer_not_running"}  # not failures: nothing for an admin to look up
LANGUAGES = ["en", "ja"]
FULL_PARAMETERS = {
    "modelTier": "deep", "seconds": 60, "retryAfterSeconds": 12, "budgetOwner": "Claims Processing (JP)", "resetTime": "00:00 UTC", "applicationName": "Claims Processing (JP)",
    "toolLabel": "Checked SLO status", "sourceName": "the Azure Activity Log", "recordKind": "evidence item", "fieldMessage": "query: String should have at least 2 characters",
    "reason": "I can't answer that from the logs of claims-api.", "reference": "corr-0123", "maximum": 6, "stepDescription": "writing the answer",
}


def template_fields(template: str) -> set[str]:
    return {field_name for _, field_name, _, _ in string.Formatter().parse(template) if field_name}


def error_table(language: str) -> dict:
    return json.loads((RESOURCES_DIRECTORY / "i18n" / f"{language}.json").read_text(encoding="utf-8"))["ask_keigan_errors"]


def all_subclasses(cls: type) -> set[type]:
    return {cls} | {nested for child in cls.__subclasses__() for nested in all_subclasses(child)}


def test_the_catalogue_has_every_row_of_the_specified_table() -> None:
    assert set(SPECIFIED_CODES) <= AskKeiganErrorCatalogue.error_codes()
    assert AskKeiganErrorCatalogue.error_codes() == set(SPECIFIED_CODES) | set(ADDED_CODES)


def test_access_denied_is_the_same_row_as_forbidden() -> None:
    assert AskKeiganErrorCatalogue.describe("access_denied", {"applicationName": "Payments"}).detail == AskKeiganErrorCatalogue.describe("forbidden", {"applicationName": "Payments"}).detail


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_code_has_a_title_and_a_detail_in_every_locale(language: str) -> None:
    table = error_table(language)
    for error_code in AskKeiganErrorCatalogue.error_codes():
        assert table[error_code]["title"].strip(), (language, error_code)
        assert table[error_code]["detail"].strip(), (language, error_code)


def test_both_locales_use_the_same_parameters_for_every_code() -> None:
    english, japanese = error_table("en"), error_table("ja")
    for error_code in AskKeiganErrorCatalogue.error_codes():
        for part in ("title", "detail"):
            assert template_fields(english[error_code][part]) == template_fields(japanese[error_code][part]), (error_code, part)


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_parameter_a_template_uses_has_a_fallback_so_a_missing_value_never_leaves_braces(language: str) -> None:
    table = error_table(language)
    used_fields = {field for error_code in AskKeiganErrorCatalogue.error_codes() for part in ("title", "detail") for field in template_fields(table[error_code][part])}
    assert used_fields - {"reference"} <= set(table["fallbacks"])
    assert set(FULL_PARAMETERS) >= used_fields


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("error_code", sorted(AskKeiganErrorCatalogue.error_codes()))
def test_no_classified_failure_shows_the_catch_all_sentence_and_each_carries_its_reference(error_code: str, language: str) -> None:
    failure = AskKeiganErrorCatalogue.describe(error_code, FULL_PARAMETERS, language)
    assert failure.detail != generic_failure_message()
    assert "{" not in failure.title + failure.detail
    if error_code in CODES_WITHOUT_A_REFERENCE:
        assert "corr-0123" not in failure.detail
    else:
        assert "corr-0123" in failure.detail


def test_a_message_names_the_failed_part_the_cause_and_what_to_do() -> None:
    failure = AskKeiganErrorCatalogue.describe("tool_failed_source_unavailable", {"toolLabel": "Checked recent changes", "sourceName": "the Azure Activity Log", "reference": "corr-1"})
    assert failure == AnswerFailure(
        error_code="tool_failed_source_unavailable", title='Couldn\'t complete "Checked recent changes"',
        detail='Couldn\'t complete "Checked recent changes": the Azure Activity Log could not be reached. This result is missing from the answer. Reference corr-1.',
        parameters={"toolLabel": "Checked recent changes", "sourceName": "the Azure Activity Log", "reference": "corr-1"}, is_retryable=True, user_action=AskKeiganUserAction.TRY_AGAIN,
    )


def test_a_timeout_message_names_the_model_tier_and_the_wait() -> None:
    failure = AskKeiganErrorCatalogue.describe("ai_timeout", {"modelTier": "deep", "seconds": 60, "reference": "corr-2"})
    assert failure.detail == "The AI model (deep) did not answer in 60 seconds. Nothing was changed. If this repeats, ask an admin to check the AI endpoint. Reference corr-2."


def test_an_unreadable_application_is_never_named_when_no_name_is_given() -> None:
    assert AskKeiganErrorCatalogue.describe("forbidden", {"reference": "corr-3"}).detail == "You can't read that application. Ask its admin for access. Reference corr-3."


def test_the_reference_defaults_to_the_current_correlation_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keigan.ai.ask_keigan_errors.current_correlation_id", lambda: "from-the-request")
    assert AskKeiganErrorCatalogue.describe("ai_unavailable").detail == "The AI model could not be reached. Try again shortly. Reference from-the-request."


def test_without_a_reference_the_message_has_no_reference_sentence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keigan.ai.ask_keigan_errors.current_correlation_id", lambda: "")
    assert AskKeiganErrorCatalogue.describe("ai_unavailable").detail == "The AI model could not be reached. Try again shortly."


def test_the_internal_error_names_the_step_that_failed() -> None:
    detail = AskKeiganErrorCatalogue.describe("internal_error", {"stepDescription": "running \"Checked SLO status\"", "reference": "corr-4"}).detail
    assert detail == "Keigan hit an unexpected error while running \"Checked SLO status\". Reference corr-4. It has been logged."


def test_the_japanese_message_is_japanese() -> None:
    assert "AI" in AskKeiganErrorCatalogue.describe("ai_unavailable", {"reference": "corr-5"}, "ja").detail
    assert AskKeiganErrorCatalogue.describe("ai_unavailable", {"reference": "corr-5"}, "ja").detail != AskKeiganErrorCatalogue.describe("ai_unavailable", {"reference": "corr-5"}, "en").detail
    assert AskKeiganErrorCatalogue.describe("ai_unavailable", {"reference": "corr-5"}, "fr").detail == AskKeiganErrorCatalogue.describe("ai_unavailable", {"reference": "corr-5"}, "en").detail


def test_text_parameters_are_cut_to_one_sanitised_line() -> None:
    failure = AskKeiganErrorCatalogue.describe("tool_failed_invalid_arguments", {"toolLabel": "Opened evidence", "fieldMessage": "bad\n[click](http://evil.example/x)\n<script>", "reference": "corr-6"})
    assert "\n" not in failure.detail
    assert "](" not in failure.detail  # the link is defanged by the shared sanitiser
    assert "http://" not in failure.detail


def test_an_unknown_code_is_reported_as_an_internal_error_instead_of_raising() -> None:
    failure = AskKeiganErrorCatalogue.describe("code_nobody_declared", {"stepDescription": "writing the answer", "reference": "corr-7"})
    assert failure.error_code == "internal_error"
    assert "writing the answer" in failure.detail


@pytest.mark.parametrize(("error_code", "is_retryable"), [
    ("ai_timeout", True), ("ai_rate_limited", True), ("ai_authentication_failed", False), ("ai_tools_unsupported", False), ("token_budget_exceeded", False),
    ("rate_limited", True), ("answer_in_progress", False), ("forbidden", False), ("access_lost_mid_run", False), ("tool_failed_source_unavailable", True),
    ("tool_failed_timeout", True), ("tool_failed_not_found", False), ("tool_query_not_answerable", False), ("tool_output_invalid", False), ("tool_limit_reached", False),
    ("answer_interrupted", True), ("validation_failed", False), ("internal_error", True),
])
def test_the_retryable_flag_follows_the_catalogue(error_code: str, is_retryable: bool) -> None:
    assert AskKeiganErrorCatalogue.is_retryable(error_code) is is_retryable
    assert AskKeiganErrorCatalogue.describe(error_code, FULL_PARAMETERS).is_retryable is is_retryable


# Bases that no code raises for a failure of Ask Keigan itself: each concrete class below them has its own row (a generic conflict is unclassified, not "an answer is running").
GENERIC_BASES = {KeiganException, ConflictException, AnswerRunConflictException}


def test_every_keigan_exception_class_maps_to_a_catalogue_entry() -> None:
    mapped = {}
    for exception_class in all_subclasses(KeiganException) - GENERIC_BASES:
        error_code = AskKeiganErrorCatalogue.code_for_exception(exception_class.__new__(exception_class))  # only the class matters: constructors differ (some take a typed name)
        assert error_code in AskKeiganErrorCatalogue.error_codes(), exception_class
        assert error_code != "internal_error", f"{exception_class.__name__} has no mapping of its own"
        mapped[exception_class.__name__] = error_code
    assert mapped["LlmTimeoutException"] == "ai_timeout"
    assert mapped["QueryNotAnswerableError"] == "tool_query_not_answerable"
    assert mapped["ReaderNotAvailableException"] == "tool_failed_source_unavailable"
    assert mapped["AnswerInProgressException"] == "answer_in_progress"
    assert mapped["DuplicateRequestException"] == "duplicate_request"
    assert mapped["AnswerNotRunningException"] == "answer_not_running"


def test_a_conflict_that_is_not_about_an_answer_is_not_reported_as_an_answer_in_progress() -> None:
    assert AskKeiganErrorCatalogue.code_for_exception(ConflictException("This record is already linked.")) == "internal_error"
    assert AskKeiganErrorCatalogue.code_for_exception(AnswerInProgressException("busy")) == "answer_in_progress"


def test_an_exception_outside_the_hierarchy_is_an_internal_error() -> None:
    assert AskKeiganErrorCatalogue.code_for_exception(RuntimeError("boom")) == "internal_error"
    assert AskKeiganErrorCatalogue.code_for_exception(KeiganException("base")) == "internal_error"


def test_messages_carry_no_upstream_text() -> None:
    upstream = "connect to loganalytics-prod.internal.example:443 failed with key sk-12345"
    for exception in (IntegrationException(upstream), RuntimeError(upstream), LlmTimeoutException(upstream), ForbiddenException(upstream), NotFoundException(upstream), TokenBudgetExceededException(upstream)):
        failure = AskKeiganErrorCatalogue.describe_exception(exception, {"toolLabel": "Queried the logs", "reference": "corr-8"})
        assert "loganalytics-prod" not in failure.title + failure.detail
        assert "sk-12345" not in failure.title + failure.detail


def test_a_validation_failure_shows_its_own_user_facing_reason() -> None:
    failure = AskKeiganErrorCatalogue.describe_exception(BusinessValidationException("The question cannot be empty."), {"reference": "corr-9"})
    assert failure.error_code == "validation_failed"
    assert failure.detail == "The question cannot be empty. Reference corr-9."


def test_a_rate_limit_keeps_its_retry_delay() -> None:
    failure = AskKeiganErrorCatalogue.describe_exception(LlmRateLimitedException("busy"), {"retryAfterSeconds": 30, "reference": "corr-10"})
    assert failure.error_code == "ai_rate_limited"
    assert failure.detail == "The AI model is busy right now. Try again in 30 seconds. Reference corr-10."
    assert failure.user_action is AskKeiganUserAction.TRY_AGAIN_AFTER_DELAY


def test_a_rate_limit_that_carries_the_providers_delay_names_it_without_the_caller_passing_it() -> None:
    failure = AskKeiganErrorCatalogue.describe_exception(LlmRateLimitedException("busy", retry_after_seconds=12), {"reference": "corr-12"})
    assert failure.detail == "The AI model is busy right now. Try again in 12 seconds. Reference corr-12." and failure.parameters["retryAfterSeconds"] == 12
    without_delay = AskKeiganErrorCatalogue.describe_exception(LlmRateLimitedException("busy"), {"reference": "corr-12"})
    assert "retryAfterSeconds" not in without_delay.parameters and "Try again in a few seconds" in without_delay.detail


def test_an_exhausted_budget_names_the_owner_it_is_given_and_otherwise_the_person() -> None:
    named = AskKeiganErrorCatalogue.describe_exception(TokenBudgetExceededException("used up", application_id="app-1"), {"budgetOwner": "Claims Processing (JP)", "reference": "corr-13"})
    assert "Claims Processing (JP)" in named.detail and "your account" not in named.detail
    personal = AskKeiganErrorCatalogue.describe_exception(TokenBudgetExceededException("used up"), {"reference": "corr-13"})
    assert "your account" in personal.detail


def test_a_model_that_cannot_use_tools_is_reported_as_such_and_not_as_an_unreachable_model() -> None:
    failure = AskKeiganErrorCatalogue.describe_exception(AgentToolsUnsupportedException("internal detail"), {"modelTier": "deep", "reference": "corr-11"})
    assert failure.error_code == "ai_tools_unsupported"
    assert failure.is_retryable is False and failure.user_action is AskKeiganUserAction.ASK_ADMIN
    assert "(deep)" in failure.detail


def test_a_model_that_broke_the_tool_format_twice_has_its_own_message() -> None:
    failure = AskKeiganErrorCatalogue.describe_exception(AgentToolProtocolException("internal detail"), {"modelTier": "deep", "reference": "corr-12"})
    assert failure.error_code == "ai_tool_protocol_failed" and failure.is_retryable is True


def test_access_removed_while_answering_is_not_reported_as_a_plain_refusal() -> None:
    failure = AskKeiganErrorCatalogue.describe_exception(AccessLostMidRunException("internal detail"), {"reference": "corr-13"})
    assert failure.error_code == "access_lost_mid_run"
    assert failure.detail.startswith("Your access to that application changed while Keigan was answering")


def test_stopping_an_answer_has_a_calm_message_that_is_not_an_error() -> None:
    failure = AskKeiganErrorCatalogue.describe("cancelled", {"reference": "corr-14"})
    assert failure.detail == "You stopped this answer. The steps Keigan finished are shown above."
    assert failure.is_retryable is False and failure.user_action is AskKeiganUserAction.NONE
