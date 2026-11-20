"""keigan/utils/pii_masker.py: PII and secret masking before storage and before any AI call."""

from __future__ import annotations

import pytest

from keigan.utils.pii_masker import PiiMasker


def build_masker(ip_address_mode: str = "partial") -> PiiMasker:
    return PiiMasker(enabled=True, ip_address_mode=ip_address_mode)


class TestFullWidthText:
    def test_full_width_email_and_phone_are_masked_after_unicode_normalization(self) -> None:
        masked_text = build_masker().mask_text("連絡先 ｔａｒｏ．ｙａｍａｄａ＠ｍｅｔｌｉｆｅ．ｃｏ．ｊｐ 電話 ０９０－１２３４－５６７８")
        assert masked_text == "連絡先 <EMAIL_1> 電話 <PHONE_1>"


class TestPhoneNumbers:
    @pytest.mark.parametrize(
        "phone_text",
        [
            pytest.param("090-1234-5678", id="japan-mobile-with-hyphens"),
            pytest.param("+81 90 1234 5678", id="international-japan-with-spaces"),
            pytest.param("09012345678", id="japan-mobile-contiguous"),
            pytest.param("+81-3-1234-5678", id="international-japan-with-hyphens"),
            pytest.param("(03)1234-5678", id="japan-parenthesized-area-code"),
            pytest.param("(415) 555-2671", id="us-parenthesized-area-code"),
            pytest.param("+61 2 9876 5432", id="international-australia"),
        ],
    )
    def test_phone_number_is_replaced_by_placeholder(self, phone_text: str) -> None:
        assert build_masker().mask_text(phone_text) == "<PHONE_1>"


class TestIpAddresses:
    def test_partial_mode_masks_ipv6_keeping_the_first_two_groups(self) -> None:
        masked_text = build_masker().mask_text("Client 2001:db8:85a3::8a2e:370:7334 connected")
        assert masked_text == "Client 2001:0db8:x:x connected"

    def test_partial_mode_masks_ipv4_keeping_the_first_two_octets(self) -> None:
        assert build_masker().mask_text("from 10.20.30.40") == "from 10.20.x.x"


class TestSecrets:
    @pytest.mark.parametrize(
        ("secret_text", "expected_text"),
        [
            pytest.param("Using ghp_16C7e42F292c6912E7710c838347Ae178B4a for CI", "Using <SECRET> for CI", id="github-token"),
            pytest.param("xoxb-1234-5678-abcdef", "<SECRET>", id="slack-token"),
            pytest.param("sk-proj-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN", "<SECRET>", id="openai-style-key"),
            pytest.param("Authorization: Basic dXNlcjpwYXNzd29yZDEyMw==", "Authorization: <SECRET>", id="basic-auth"),
            pytest.param("aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "<SECRET>", id="snake-case-aws-secret"),
            pytest.param("password: hunter2", "<SECRET>", id="short-password"),
        ],
    )
    def test_secret_value_is_replaced_by_secret_placeholder(self, secret_text: str, expected_text: str) -> None:
        assert build_masker().mask_text(secret_text) == expected_text

    def test_jwt_is_replaced_by_jwt_placeholder(self) -> None:
        jwt_text = "Session eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        assert build_masker().mask_text(jwt_text) == "Session <JWT>"

    def test_bearer_token_is_replaced_by_secret_placeholder(self) -> None:
        assert build_masker().mask_text("Authorization: Bearer abcdefghijklmnop") == "Authorization: <SECRET>"

    def test_connection_string_password_value_is_replaced(self) -> None:
        assert build_masker().mask_text("Server=db01;Password=Sup3rSecret;") == "Server=db01;<SECRET>;"

    def test_storage_account_key_in_connection_string_is_replaced(self) -> None:
        connection_text = "DefaultEndpointsProtocol=https;AccountName=acct;AccountKey=abc123def456ghi789=="
        assert build_masker().mask_text(connection_text) == "DefaultEndpointsProtocol=https;AccountName=acct;<SECRET>"

    def test_sas_signature_is_replaced(self) -> None:
        sas_url = "https://acct.blob.core.windows.net/c?sv=2020&sig=abcdefghijklmnop0123%2Bxyz%3D"
        assert build_masker().mask_text(sas_url) == "https://acct.blob.core.windows.net/c?sv=2020&<SECRET>"


class TestIdentifiers:
    def test_email_address_is_replaced(self) -> None:
        assert build_masker().mask_text("Contact taro@example.com today") == "Contact <EMAIL_1> today"

    def test_luhn_valid_card_number_is_replaced(self) -> None:
        assert build_masker().mask_text("Card 4111 1111 1111 1111 declined") == "Card <CARD_1> declined"

    def test_us_social_security_number_is_replaced(self) -> None:
        assert build_masker().mask_text("SSN 123-45-6789") == "SSN <SSN_1>"

    def test_my_number_with_valid_check_digit_is_replaced(self) -> None:
        assert build_masker().mask_text("My Number 1234 5678 9018") == "My Number <MYNUMBER_1>"

    def test_four_four_four_identifier_with_invalid_my_number_check_digit_is_not_masked(self) -> None:
        assert build_masker().mask_text("trace 1234-5678-9012") == "trace 1234-5678-9012"


class TestJsonKeys:
    def test_snake_case_sensitive_keys_are_masked_in_embedded_json(self) -> None:
        json_text = '{"client_secret": "abc123", "first_name": "Taro", "phone_number": "09012345678", "access_token": "tok_123"}'
        assert build_masker().mask_text(json_text) == '{"client_secret": "<SECRET>", "first_name": "<NAME_1>", "phone_number": "<PHONE_1>", "access_token": "<SECRET>"}'

    def test_mask_rows_replaces_values_under_sensitive_keys(self) -> None:
        rows = [{"client_secret": "abc123", "first_name": "Taro", "phone_number": "09012345678", "access_token": "tok_123"}]
        assert build_masker().mask_rows(rows) == [
            {"client_secret": "<SECRET>", "first_name": "<NAME_1>", "phone_number": "<PHONE_1>", "access_token": "<SECRET>"}
        ]

    def test_key_matching_ignores_case_and_separators(self) -> None:
        rows = [{"Client-Secret": "abc123", "FIRST_NAME": "Taro"}]
        assert build_masker().mask_rows(rows) == [{"Client-Secret": "<SECRET>", "FIRST_NAME": "<NAME_1>"}]

    def test_key_matching_normalizes_full_width_key_names(self) -> None:
        masked_row = build_masker().mask_rows([{"ｐｈｏｎｅ＿ｎｕｍｂｅｒ": "09012345678"}])[0]
        assert list(masked_row.values()) == ["<PHONE_1>"]


class TestOrdinaryLogText:
    @pytest.mark.parametrize(
        "log_text",
        [
            pytest.param("2026-11-20T10:00:00Z", id="iso-timestamp"),
            pytest.param("finished at 10:00:00 UTC", id="clock-time"),
            pytest.param("GET /api/v1/items status 500", id="http-status"),
            pytest.param("took 1234 ms", id="duration"),
            pytest.param("version 1.2.3", id="semantic-version"),
            pytest.param("trace 3f2504e0-4f89-11d3-9a0c-0305e82c3301", id="guid"),
        ],
    )
    def test_ordinary_log_text_is_unchanged(self, log_text: str) -> None:
        assert build_masker().mask_text(log_text) == log_text
