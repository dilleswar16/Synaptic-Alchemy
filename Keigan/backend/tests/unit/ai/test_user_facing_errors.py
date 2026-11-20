"""keigan/ai/user_facing_errors.py: what a user may read about a failure (V19)."""

from __future__ import annotations

from keigan.ai.user_facing_errors import describe_failure_for_user
from keigan.config.logging_config import set_correlation_id
from keigan.exceptions.keigan_exceptions import BusinessValidationException, IntegrationException, TokenBudgetExceededException


def test_messages_written_for_users_are_shown_as_they_are() -> None:
    assert describe_failure_for_user(BusinessValidationException("Pick a shorter time range.")) == "Pick a shorter time range."
    assert describe_failure_for_user(TokenBudgetExceededException("Today's budget is used up.")) == "Today's budget is used up."


def test_integration_errors_are_replaced_by_a_generic_message_with_the_correlation_id() -> None:
    set_correlation_id("corr-777")
    message = describe_failure_for_user(IntegrationException("Elastic at es-prod.internal:9200 returned 500: index claims-2026 missing"))
    assert "es-prod.internal" not in message and "claims-2026" not in message
    assert "corr-777" in message


def test_unexpected_exceptions_are_replaced_by_a_generic_message() -> None:
    assert "KeyError" not in describe_failure_for_user(KeyError("secret_table"))
    assert "secret_table" not in describe_failure_for_user(KeyError("secret_table"))
