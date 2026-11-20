"""One rule for the email addresses Keigan stores and mails (team members, stakeholders).

Strict on purpose: an address that passes is one a mail server will accept; the pattern does not try to cover every
form RFC 5322 allows (quoted names, comments, IP literals), because nobody on a company team has one.
"""

from __future__ import annotations

import re

MAXIMUM_EMAIL_ADDRESS_LENGTH = 320  # the column width; also the RFC limit
EMAIL_ADDRESS_MESSAGE = "Enter an email address like name@company.com."
# local part: letters, digits and . _ % + - ' separated by single dots; domain: labels of letters/digits/hyphens, at least one dot, a letter-only last label of 2+ characters.
_EMAIL_ADDRESS_PATTERN = re.compile(
    r"^[a-z0-9_%+'\-]+(\.[a-z0-9_%+'\-]+)*@([a-z0-9]([a-z0-9\-]*[a-z0-9])?\.)+[a-z]{2,}$"
)
MAXIMUM_LOCAL_PART_LENGTH = 64


def normalize_email_address(typed_address: str) -> str:
    """The address trimmed and lower-cased, ready to store and compare. Raises ``ValueError`` with a message fit to show next to the field."""
    address = (typed_address or "").strip().lower()
    local_part = address.split("@", 1)[0]
    if len(address) > MAXIMUM_EMAIL_ADDRESS_LENGTH or len(local_part) > MAXIMUM_LOCAL_PART_LENGTH or not _EMAIL_ADDRESS_PATTERN.match(address):
        raise ValueError(EMAIL_ADDRESS_MESSAGE)
    return address
