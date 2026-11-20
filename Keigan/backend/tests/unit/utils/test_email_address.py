"""keigan/utils/email_address.py: one strict, readable rule for the addresses Keigan will mail."""

from __future__ import annotations

import pytest

from keigan.utils.email_address import EMAIL_ADDRESS_MESSAGE, normalize_email_address


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("rui@example.com", "rui@example.com"),
        ("  Rui.Reader@Example.COM  ", "rui.reader@example.com"),
        ("first+tag@sub.domain.example.org", "first+tag@sub.domain.example.org"),
        ("o'brien@example.com", "o'brien@example.com"),
    ],
)
def test_a_valid_address_is_trimmed_and_lower_cased(typed: str, stored: str) -> None:
    assert normalize_email_address(typed) == stored


@pytest.mark.parametrize(
    "typed",
    ["", "   ", "rui", "rui@", "@example.com", "rui@example", "rui@@example.com", "rui @example.com", "rui@exa mple.com", "rui@.com", "rui@example..com", ".rui@example.com", "rui.@example.com", "a" * 250 + "@example.com"],
)
def test_an_address_that_cannot_be_mailed_is_refused_with_one_clear_message(typed: str) -> None:
    with pytest.raises(ValueError, match=EMAIL_ADDRESS_MESSAGE):
        normalize_email_address(typed)
