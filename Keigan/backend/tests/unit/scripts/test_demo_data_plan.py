"""The plan says which table goes into which demo data file and in what order; it fails loudly when a table was forgotten."""

from __future__ import annotations

import pytest
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table

from keigan.entities import all_entities  # noqa: F401  (registers every table)
from keigan.entities.base_entity import EntityBase
from support import scripts_path  # noqa: F401  (puts backend/scripts on sys.path)

from demo_data_sql.demo_data_errors import DemoDataSqlError  # noqa: E402
from demo_data_sql.demo_data_plan import (  # noqa: E402
    DEMO_DATA_FILE_DECLARATIONS,
    EXCLUDED_TABLE_REASONS,
    DemoDataFileDeclaration,
    build_demo_data_plan,
)


def build_metadata() -> MetaData:
    """parent <- child <- grandchild, plus an unrelated table and a runtime queue table."""
    metadata = MetaData()
    Table("parent", metadata, Column("parent_id", String(36), primary_key=True))
    Table("child", metadata, Column("child_id", String(36), primary_key=True), Column("parent_id", ForeignKey("parent.parent_id")))
    Table("grandchild", metadata, Column("grandchild_id", String(36), primary_key=True), Column("child_id", ForeignKey("child.child_id")))
    Table("unrelated", metadata, Column("unrelated_id", Integer, primary_key=True))
    Table("job_queue", metadata, Column("job_id", String(36), primary_key=True))
    return metadata


def declaration(file_name: str, *table_names: str, committed: bool = True) -> DemoDataFileDeclaration:
    return DemoDataFileDeclaration(file_name=file_name, title=f"Title of {file_name}", table_names=table_names, committed=committed)


ONE_ROW_EACH = {"parent": 1, "child": 1, "grandchild": 1, "unrelated": 1, "job_queue": 1}
QUEUE_EXCLUDED = {"job_queue": "Queue rows would be run by the workers."}


def test_tables_inside_a_file_are_sorted_parent_before_child_even_when_declared_the_other_way_round() -> None:
    plan = build_demo_data_plan(build_metadata(), ONE_ROW_EACH, (declaration("01.sql", "grandchild", "child", "parent", "unrelated"),), QUEUE_EXCLUDED)
    assert [table.name for table in plan.files[0].tables] == ["parent", "unrelated", "child", "grandchild"]


def test_tables_without_seeded_rows_are_left_out_of_the_plan() -> None:
    plan = build_demo_data_plan(build_metadata(), {"parent": 2, "child": 0}, (declaration("01.sql", "parent", "child", "grandchild", "unrelated"),), QUEUE_EXCLUDED)
    assert [table.name for table in plan.tables_in_insert_order] == ["parent"]


def test_files_keep_their_declared_order_in_the_insert_order() -> None:
    plan = build_demo_data_plan(build_metadata(), ONE_ROW_EACH, (declaration("01.sql", "parent", "unrelated"), declaration("02.sql", "child", "grandchild")), QUEUE_EXCLUDED)
    assert [table.name for table in plan.tables_in_insert_order][-2:] == ["child", "grandchild"]


def test_a_table_with_seeded_rows_that_nobody_assigned_fails_and_names_the_table() -> None:
    with pytest.raises(DemoDataSqlError) as problem:
        build_demo_data_plan(build_metadata(), ONE_ROW_EACH, (declaration("01.sql", "parent", "child", "unrelated"),), QUEUE_EXCLUDED)
    message = str(problem.value)
    assert "grandchild" in message
    assert "demo_data_plan.py" in message
    assert "DEMO_DATA_FILE_DECLARATIONS" in message and "EXCLUDED_TABLE_REASONS" in message


def test_an_unassigned_table_without_seeded_rows_is_not_a_problem() -> None:
    build_demo_data_plan(build_metadata(), {"parent": 1}, (declaration("01.sql", "parent"),), QUEUE_EXCLUDED)


def test_a_table_assigned_to_two_files_fails() -> None:
    with pytest.raises(DemoDataSqlError, match=r"parent.*01\.sql.*02\.sql"):
        build_demo_data_plan(build_metadata(), {"parent": 1}, (declaration("01.sql", "parent"), declaration("02.sql", "parent")), QUEUE_EXCLUDED)


def test_a_declared_table_that_does_not_exist_in_the_entities_fails_and_names_it() -> None:
    with pytest.raises(DemoDataSqlError, match=r"01\.sql.*renamed_table"):
        build_demo_data_plan(build_metadata(), {"parent": 1}, (declaration("01.sql", "parent", "renamed_table"),), QUEUE_EXCLUDED)


def test_an_excluded_table_that_does_not_exist_in_the_entities_fails_and_names_it() -> None:
    with pytest.raises(DemoDataSqlError, match=r"gone_table"):
        build_demo_data_plan(build_metadata(), {"parent": 1}, (declaration("01.sql", "parent"),), {"gone_table": "reason"})


def test_a_table_cannot_be_both_declared_and_excluded() -> None:
    with pytest.raises(DemoDataSqlError, match=r"job_queue.*both"):
        build_demo_data_plan(build_metadata(), ONE_ROW_EACH, (declaration("01.sql", "parent", "child", "grandchild", "unrelated", "job_queue"),), QUEUE_EXCLUDED)


def test_a_child_declared_in_an_earlier_file_than_its_parent_fails() -> None:
    with pytest.raises(DemoDataSqlError, match=r"child.*01\.sql.*parent.*02\.sql"):
        build_demo_data_plan(build_metadata(), {"parent": 1, "child": 1}, (declaration("01.sql", "child"), declaration("02.sql", "parent")), QUEUE_EXCLUDED)


def test_a_demo_table_that_points_at_an_excluded_table_fails() -> None:
    with pytest.raises(DemoDataSqlError, match=r"child.*parent.*excluded"):
        build_demo_data_plan(build_metadata(), {"parent": 1, "child": 1}, (declaration("01.sql", "child"),), {"parent": "reason", "job_queue": "reason"})


def test_every_excluded_table_in_the_real_declarations_has_a_reason_and_exists() -> None:
    table_names = {table.name for table in EntityBase.metadata.sorted_tables}
    for excluded_table_name, reason in EXCLUDED_TABLE_REASONS.items():
        assert excluded_table_name in table_names
        assert len(reason) > 20, f"{excluded_table_name} needs a real reason"


def test_real_declarations_only_name_tables_the_entities_define() -> None:
    table_names = {table.name for table in EntityBase.metadata.sorted_tables}
    declared = [name for file_declaration in DEMO_DATA_FILE_DECLARATIONS for name in file_declaration.table_names]
    assert set(declared) <= table_names
    assert len(declared) == len(set(declared))
