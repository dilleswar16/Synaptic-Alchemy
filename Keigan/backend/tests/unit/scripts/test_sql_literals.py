"""Rendering a Python value as a T-SQL literal, decided by the COLUMN TYPE from the entity metadata, never by guessing from the value."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import JSON, BigInteger, Boolean, Column, Date, DateTime, Float, Integer, LargeBinary, MetaData, String, Table, Text

from keigan.entities.base_entity import UtcDateTime
from support import scripts_path  # noqa: F401  (puts backend/scripts on sys.path)

from demo_data_sql.demo_data_errors import DemoDataSqlError  # noqa: E402  (import after the path helper)
from demo_data_sql.sql_literals import render_literal  # noqa: E402


def column_of(column_type: Any, column_name: str = "sample_column") -> Column:
    table = Table("sample_table", MetaData(), Column(column_name, column_type))
    return table.c[column_name]


def test_text_is_unicode_quoted_and_single_quotes_are_doubled() -> None:
    assert render_literal("O'Brien said 'hi'", column_of(String(50))) == "N'O''Brien said ''hi'''"


def test_japanese_text_is_kept_as_is_inside_a_unicode_literal() -> None:
    assert render_literal("請求処理の遅延", column_of(Text())) == "N'請求処理の遅延'"


def test_text_with_line_breaks_and_tabs_is_kept() -> None:
    assert render_literal("first\r\nsecond\tthird", column_of(Text())) == "N'first\r\nsecond\tthird'"


def test_null_is_rendered_for_every_column_type() -> None:
    for column_type in (String(5), Text(), Integer(), BigInteger(), Boolean(), Float(), UtcDateTime(), Date(), JSON()):
        assert render_literal(None, column_of(column_type)) == "NULL"


def test_json_is_rendered_as_unicode_json_text_with_japanese_unescaped() -> None:
    value = {"assignment_group": "JP-L2", "note": "it's 慧眼", "scores": [1, 2.5, None, True]}
    assert render_literal(value, column_of(JSON())) == '''N'{"assignment_group": "JP-L2", "note": "it''s 慧眼", "scores": [1, 2.5, null, true]}\''''


def test_json_column_holding_a_plain_list_is_rendered_as_json() -> None:
    assert render_literal(["a", "b"], column_of(JSON())) == '''N'["a", "b"]\''''


def test_json_with_not_a_number_is_rejected_with_the_column_named() -> None:
    with pytest.raises(DemoDataSqlError, match=r"sample_table\.sample_column.*JSON"):
        render_literal({"ratio": float("nan")}, column_of(JSON()))


def test_boolean_column_renders_bit_values() -> None:
    boolean_column = column_of(Boolean())
    assert (render_literal(True, boolean_column), render_literal(False, boolean_column)) == ("1", "0")


def test_integer_column_that_holds_a_bool_renders_a_number_not_the_word_true() -> None:
    assert render_literal(True, column_of(Integer())) == "1"
    assert render_literal(False, column_of(BigInteger())) == "0"


def test_integers_are_rendered_without_quotes() -> None:
    assert render_literal(-42, column_of(Integer())) == "-42"
    assert render_literal(9_000_000_000, column_of(BigInteger())) == "9000000000"


def test_integer_column_rejects_text_and_names_the_column_and_value_type() -> None:
    with pytest.raises(DemoDataSqlError, match=r"sample_table\.sample_column.*str"):
        render_literal("12", column_of(Integer()))


def test_boolean_column_rejects_other_numbers() -> None:
    with pytest.raises(DemoDataSqlError, match=r"sample_table\.sample_column"):
        render_literal(2, column_of(Boolean()))


def test_floats_use_their_shortest_exact_text() -> None:
    float_column = column_of(Float())
    assert render_literal(99.95, float_column) == "99.95"
    assert render_literal(1e-05, float_column) == "1e-05"
    assert render_literal(100.0, float_column) == "100.0"
    assert render_literal(3, float_column) == "3"


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_not_a_number_and_infinity_are_rejected_because_sql_server_cannot_store_them(bad_value: float) -> None:
    with pytest.raises(DemoDataSqlError, match=r"sample_table\.sample_column.*cannot store"):
        render_literal(bad_value, column_of(Float()))


def test_timezone_aware_datetime_is_converted_to_naive_utc() -> None:
    tokyo = timezone(timedelta(hours=9))
    assert render_literal(datetime(2026, 11, 20, 21, 30, 5, 123456, tzinfo=tokyo), column_of(UtcDateTime())) == "'2026-11-20 12:30:05.123456'"


def test_naive_datetime_is_taken_as_utc() -> None:
    assert render_literal(datetime(2026, 1, 2, 3, 4, 5), column_of(DateTime())) == "'2026-01-02 03:04:05.000000'"


def test_utc_datetime_keeps_microseconds() -> None:
    assert render_literal(datetime(2026, 11, 20, 12, 0, tzinfo=UTC), column_of(UtcDateTime())) == "'2026-11-20 12:00:00.000000'"


def test_date_column_renders_an_iso_date() -> None:
    assert render_literal(date(2026, 11, 20), column_of(Date())) == "'2026-11-20'"


def test_date_column_rejects_a_datetime() -> None:
    with pytest.raises(DemoDataSqlError, match=r"sample_table\.sample_column"):
        render_literal(datetime(2026, 11, 20, 12, 0), column_of(Date()))


def test_datetime_column_rejects_text() -> None:
    with pytest.raises(DemoDataSqlError, match=r"sample_table\.sample_column.*datetime"):
        render_literal("2026-11-20", column_of(UtcDateTime()))


def test_binary_column_type_is_rejected_as_unsupported_with_the_column_named() -> None:
    with pytest.raises(DemoDataSqlError, match=r"sample_table\.sample_column.*LargeBinary.*not supported"):
        render_literal(b"\x00\x01", column_of(LargeBinary()))


def test_bytes_in_a_text_column_are_rejected() -> None:
    with pytest.raises(DemoDataSqlError, match=r"sample_table\.sample_column.*bytes"):
        render_literal(b"abc", column_of(String(10)))


@pytest.mark.parametrize(
    "dangerous_text",
    ["line one\nGO\nline three", "  go  ", "before\n:r other.sql\nafter", "price is $(KeiganIdentityName)", "nul\x00byte"],
)
def test_text_that_sqlcmd_would_interpret_is_rejected_instead_of_corrupting_the_script(dangerous_text: str) -> None:
    with pytest.raises(DemoDataSqlError, match=r"sample_table\.sample_column.*sqlcmd"):
        render_literal(dangerous_text, column_of(Text()))


def test_text_that_only_mentions_go_inside_a_sentence_is_fine() -> None:
    assert render_literal("let's go home\nand then GO ahead", column_of(Text())) == "N'let''s go home\nand then GO ahead'"
