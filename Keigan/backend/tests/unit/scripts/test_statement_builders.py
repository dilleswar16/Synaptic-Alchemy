"""The insert and removal T-SQL, checked as rendered text (T-SQL cannot run on SQLite, so the text itself is what we can verify)."""

from __future__ import annotations

import re

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, String, Table, UniqueConstraint

from support import scripts_path  # noqa: F401  (puts backend/scripts on sys.path)

from demo_data_sql.demo_data_errors import DemoDataSqlError  # noqa: E402
from demo_data_sql.statement_builders import build_insert_blocks, build_removal_blocks  # noqa: E402


def string_key_table(table_name: str = "sample_item") -> Table:
    return Table(table_name, MetaData(), Column("item_id", String(36), primary_key=True), Column("item_name", String(50)), Column("item_count", Integer))


def rows_for(count: int) -> list[dict[str, object]]:
    return [{"item_id": f"id-{number}", "item_name": f"name {number}", "item_count": None if number == 2 else number} for number in range(1, count + 1)]


def measurement_table() -> Table:
    return Table(
        "sample_measurement", MetaData(),
        Column("measurement_id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
        Column("series_id", String(36)), Column("window_start", String(30)), Column("measured_value", Integer),
        UniqueConstraint("series_id", "window_start", name="uq_sample_measurement_window"),
    )


def test_insert_block_stages_the_rows_and_inserts_only_those_whose_key_is_missing() -> None:
    (block,) = build_insert_blocks(string_key_table(), rows_for(2), "keigan")
    assert block == (
        "DROP TABLE IF EXISTS #demo_rows;\n"
        "SELECT TOP (0) [item_id], [item_name], [item_count] INTO #demo_rows FROM [keigan].[sample_item];\n"
        "INSERT INTO #demo_rows ([item_id], [item_name], [item_count]) VALUES\n"
        "    (N'id-1', N'name 1', 1),\n"
        "    (N'id-2', N'name 2', NULL);\n"
        "INSERT INTO [keigan].[sample_item] ([item_id], [item_name], [item_count])\n"
        "SELECT [source].[item_id], [source].[item_name], [source].[item_count] FROM #demo_rows AS [source]\n"
        "WHERE NOT EXISTS (SELECT 1 FROM [keigan].[sample_item] AS [existing] WHERE [existing].[item_id] = [source].[item_id]);\n"
        "DROP TABLE #demo_rows;"
    )


def test_every_row_of_a_chunked_insert_is_guarded_not_only_the_first_row_of_each_chunk() -> None:
    blocks = build_insert_blocks(string_key_table(), rows_for(5), "keigan", rows_per_block=2)
    assert len(blocks) == 3
    for block in blocks:
        assert block.count("WHERE NOT EXISTS") == 1
        assert "FROM #demo_rows AS [source]" in block
        assert not re.search(r"INSERT INTO \[keigan\]\.\[sample_item\] \([^)]*\)\s+VALUES", block), "rows must reach the real table only through the guarded SELECT"
    for number in range(1, 6):
        assert sum(f"N'id-{number}'" in block for block in blocks) == 1, f"row {number} must be in exactly one block"


def test_a_composite_primary_key_is_compared_on_every_column() -> None:
    table = Table("sample_link", MetaData(), Column("left_id", String(36), primary_key=True), Column("right_id", String(36), primary_key=True))
    (block,) = build_insert_blocks(table, [{"left_id": "a", "right_id": "b"}], "keigan")
    assert "WHERE [existing].[left_id] = [source].[left_id] AND [existing].[right_id] = [source].[right_id]" in block


def test_a_table_without_rows_produces_no_insert_blocks() -> None:
    assert build_insert_blocks(string_key_table(), [], "keigan") == []


def test_the_schema_name_is_applied_to_every_table_reference() -> None:
    (block,) = build_insert_blocks(string_key_table(), rows_for(1), "demo")
    assert "[demo].[sample_item]" in block
    assert "[keigan]" not in block


def test_identity_column_is_not_inserted_and_rows_are_matched_by_their_unique_key() -> None:
    rows = [{"measurement_id": 7, "series_id": "s1", "window_start": "2026-11-20 12:00", "measured_value": 99}]
    (block,) = build_insert_blocks(measurement_table(), rows, "keigan")
    assert "measurement_id" not in block
    assert "IDENTITY_INSERT" not in block
    assert "INSERT INTO #demo_rows ([series_id], [window_start], [measured_value]) VALUES\n    (N's1', N'2026-11-20 12:00', 99);" in block
    assert "WHERE [existing].[series_id] = [source].[series_id] AND [existing].[window_start] = [source].[window_start]" in block


def test_identity_table_without_a_unique_key_cannot_be_made_idempotent_and_says_so() -> None:
    table = Table("sample_counter", MetaData(), Column("counter_id", Integer, primary_key=True, autoincrement=True), Column("counter_value", Integer))
    with pytest.raises(DemoDataSqlError, match=r"sample_counter.*unique constraint"):
        build_insert_blocks(table, [{"counter_id": 1, "counter_value": 5}], "keigan")


def test_removal_deletes_by_primary_key_in_reverse_insert_order() -> None:
    parent, child = string_key_table("sample_parent"), string_key_table("sample_child")
    blocks = build_removal_blocks([parent, child], {"sample_parent": rows_for(2), "sample_child": rows_for(1)}, "keigan")
    deletes = [block for block in blocks if block.startswith("DELETE")]
    assert deletes == [
        "DELETE FROM [keigan].[sample_child] WHERE [item_id] IN (N'id-1');",
        "DELETE FROM [keigan].[sample_parent] WHERE [item_id] IN (N'id-1', N'id-2');",
    ]


def test_removal_runs_in_one_transaction_that_rolls_back_on_any_error() -> None:
    blocks = build_removal_blocks([string_key_table()], {"sample_item": rows_for(1)}, "keigan")
    assert blocks[0] == "SET XACT_ABORT ON;\nBEGIN TRANSACTION;"
    assert blocks[-1] == "COMMIT TRANSACTION;"


def test_removal_never_mentions_a_table_without_seeded_rows() -> None:
    blocks = build_removal_blocks([string_key_table("sample_a"), string_key_table("sample_b")], {"sample_a": rows_for(1), "sample_b": []}, "keigan")
    assert "sample_b" not in "\n".join(blocks)


def test_removal_splits_long_key_lists_into_several_deletes() -> None:
    blocks = build_removal_blocks([string_key_table()], {"sample_item": rows_for(5)}, "keigan", keys_per_delete=2)
    deletes = [block for block in blocks if block.startswith("DELETE")]
    assert len(deletes) == 3
    assert [delete.count("N'id-") for delete in deletes] == [2, 2, 1]


def test_removal_with_a_composite_key_matches_every_key_column() -> None:
    table = Table("sample_link", MetaData(), Column("left_id", String(36), primary_key=True), Column("right_id", String(36), primary_key=True))
    blocks = build_removal_blocks([table], {"sample_link": [{"left_id": "a", "right_id": "b"}, {"left_id": "a", "right_id": "c"}]}, "keigan")
    assert "DELETE FROM [keigan].[sample_link] WHERE ([left_id] = N'a' AND [right_id] = N'b') OR ([left_id] = N'a' AND [right_id] = N'c');" in blocks


def test_removal_of_an_identity_table_uses_the_short_list_of_distinct_parent_keys_not_one_literal_per_row() -> None:
    rows = [{"measurement_id": number, "series_id": f"s{number % 3}", "window_start": f"w{number}", "measured_value": number} for number in range(1, 301)]
    blocks = build_removal_blocks([measurement_table()], {"sample_measurement": rows}, "keigan")
    assert "DELETE FROM [keigan].[sample_measurement] WHERE [series_id] IN (N's0', N's1', N's2');" in blocks
    assert sum(len(block) for block in blocks) < 600


def test_removal_is_harmless_to_run_twice_because_it_only_deletes_by_key() -> None:
    blocks = build_removal_blocks([string_key_table()], {"sample_item": rows_for(1)}, "keigan")
    assert not any("TRUNCATE" in block or re.search(r"DELETE FROM \[[^\]]+\]\.\[[^\]]+\];", block) for block in blocks), "a DELETE without WHERE would remove real data"
