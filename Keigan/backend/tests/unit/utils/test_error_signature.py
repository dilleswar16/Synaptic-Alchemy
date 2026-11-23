"""keigan/utils/error_signature.py: two error templates that differ only in numbers, ids and masked values are the same problem (spec 34, 4.3; AC-15)."""

from __future__ import annotations

import pytest

from keigan.utils.error_signature import MAXIMUM_SIGNATURE_CHARACTERS, hash_key_value, normalize_error_template


def test_numbers_guids_and_hex_ids_do_not_make_a_new_signature() -> None:
    first = "Timeout expired after 30000 ms on connection 7f3a9c2e-1b4d-4e6f-8a0b-3c5d7e9f1a2b to host 10.0.4.17 (request 0x7ffd1234)"
    second = "Timeout expired after 15000 ms on connection 11111111-2222-3333-4444-555555555555 to host 10.9.8.2 (request 0xdeadbee1)"
    assert normalize_error_template(first) == normalize_error_template(second) == "timeout expired after # ms on connection <id> to host # (request <id>)"
    assert hash_key_value(normalize_error_template(first)) == hash_key_value(normalize_error_template(second))


def test_masked_values_become_their_category_whatever_their_number() -> None:
    assert normalize_error_template("Login failed for <EMAIL_1> from <IP_ADDRESS_14>") == normalize_error_template("Login failed for <EMAIL_9> from <IP_ADDRESS_2>") == "login failed for <email> from <ip_address>"


def test_case_spacing_and_full_width_characters_do_not_matter() -> None:
    assert normalize_error_template("  HikariPool-1 -  Connection   is NOT available ") == "hikaripool-# - connection is not available"
    assert normalize_error_template("エラー　１２３件") == normalize_error_template("エラー 123件") == "エラー #件"


def test_different_problems_have_different_signatures() -> None:
    assert hash_key_value(normalize_error_template("Connection pool exhausted")) != hash_key_value(normalize_error_template("Certificate has expired"))


def test_a_long_template_is_cut_to_the_maximum() -> None:
    assert len(normalize_error_template("word " * 500)) <= MAXIMUM_SIGNATURE_CHARACTERS


@pytest.mark.parametrize("text", ["", "   ", None])
def test_nothing_in_gives_nothing_out(text: str | None) -> None:
    assert normalize_error_template(text) == ""


def test_a_word_made_of_hex_letters_is_kept_and_a_hex_token_with_a_digit_is_an_id() -> None:
    assert normalize_error_template("feedback deadbeef cafe") == "feedback deadbeef cafe"
    assert normalize_error_template("commit 8f3c2ab9 failed") == "commit <id> failed"


def test_the_hash_is_sha256_hex_and_stable() -> None:
    assert hash_key_value("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad" and len(hash_key_value("x")) == 64
