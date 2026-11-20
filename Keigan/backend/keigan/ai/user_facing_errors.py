"""Messages about failures that end users may read (V19).

Upstream error text can reveal internal hostnames, index names and gateway details. Only the exception types whose messages Keigan
wrote for users are shown as they are; everything else becomes a generic sentence with the correlation id, and the technical
detail stays in the log.
"""

from __future__ import annotations

import logging

from keigan.config.logging_config import current_correlation_id
from keigan.exceptions.keigan_exceptions import (
    BusinessValidationException,
    ConflictException,
    ForbiddenException,
    KeiganException,
    LlmUnavailableException,
    NotFoundException,
    TokenBudgetExceededException,
)

logger = logging.getLogger(__name__)
# Their messages are written for end users (the integration and internal errors are not).
_USER_READABLE_EXCEPTIONS = (BusinessValidationException, ConflictException, ForbiddenException, NotFoundException, TokenBudgetExceededException, LlmUnavailableException)


def generic_failure_message() -> str:
    return f"Something went wrong on Keigan's side. Try again in a few minutes. If it keeps failing, quote reference {current_correlation_id() or 'none'} to a Keigan admin."


def describe_failure_for_user(failure: Exception) -> str:
    """The text a user may see for ``failure``; the technical detail is logged, never returned."""
    if isinstance(failure, _USER_READABLE_EXCEPTIONS):
        return failure.detail if isinstance(failure, KeiganException) else str(failure)
    logger.warning("A failure was hidden from the user: %s: %s", type(failure).__name__, str(failure)[:500])
    return generic_failure_message()
