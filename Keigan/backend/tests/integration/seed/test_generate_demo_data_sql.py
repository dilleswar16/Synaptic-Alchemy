"""Demo data SQL for the DBA (database/azure_sql/demo_data), generated from the demo seed by scripts/generate_demo_data_sql.py.

WHAT THESE TESTS COVER: the generator really runs the seed; the files are reproducible; the committed files and MANIFEST.json match a fresh
generation (including the large on-demand file, by row count and SHA-256); the text has the right order, guards and exclusions.
WHAT THEY DO NOT COVER: T-SQL cannot run on SQLite and there is no real Azure SQL here, so no generated statement has ever been executed
against SQL Server. The text is checked, not run; the DBA's first run on a non-production database is the real verification.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from keigan.entities import all_entities  # noqa: F401  (registers every table)
from keigan.entities.base_entity import EntityBase
from keigan.seed.alert_and_slo_seed import DEMO_FINE_GRAINED_HISTORY_DAYS

BACKEND_DIRECTORY = Path(__file__).resolve().parents[3]
AZURE_SQL_DIRECTORY = BACKEND_DIRECTORY.parent / "database" / "azure_sql"
DEMO_DATA_DIRECTORY = AZURE_SQL_DIRECTORY / "demo_data"
REMOVAL_FILE_NAME = "99_remove_demo_data.sql"
INSERT_TARGET = re.compile(r"^INSERT INTO \[keigan\]\.\[(\w+)\] \(", re.MULTILINE)


def load_manifest(directory: Path) -> dict:
    return json.loads((directory / "MANIFEST.json").read_text(encoding="utf-8"))


def step_file_names(manifest: dict) -> list[str]:
    """Step files in run order (the manifest keeps the declared order)."""
    return [name for name in manifest["files"] if name[:2].isdigit() and not name.startswith("99")]


def inserted_tables_in_run_order(directory: Path, manifest: dict) -> list[str]:
    ordered: list[str] = []
    for file_name in step_file_names(manifest):
        for table_name in INSERT_TARGET.findall((directory / file_name).read_text(encoding="utf-8")):
            if table_name not in ordered:
                ordered.append(table_name)
    return ordered


def test_two_runs_with_different_hash_seeds_produce_byte_identical_files(generated_demo_data_runs: tuple[Path, Path]) -> None:
    first, second = generated_demo_data_runs
    first_files = sorted(path.name for path in first.iterdir())
    assert first_files == sorted(path.name for path in second.iterdir())
    for file_name in first_files:
        assert (first / file_name).read_bytes() == (second / file_name).read_bytes(), f"{file_name} differs between two generator runs: the seed is not reproducible"


def test_the_committed_manifest_matches_a_fresh_generation_including_the_on_demand_file(generated_demo_data_directory: Path) -> None:
    assert load_manifest(DEMO_DATA_DIRECTORY) == load_manifest(generated_demo_data_directory), (
        "database/azure_sql/demo_data/MANIFEST.json has drifted from the seed: run backend/scripts/generate_demo_data_sql.py and commit the result"
    )


def test_committed_script_files_match_the_manifest_and_a_fresh_generation_and_no_unlisted_sql_file_exists(generated_demo_data_directory: Path) -> None:
    manifest = load_manifest(DEMO_DATA_DIRECTORY)
    unlisted = sorted(path.name for path in DEMO_DATA_DIRECTORY.glob("*.sql") if path.name not in manifest["files"])
    assert unlisted == [], f"SQL files in demo_data that the generator does not produce: {unlisted}"
    for file_name, entry in manifest["files"].items():
        if not entry["committed"]:
            continue
        committed_text = (DEMO_DATA_DIRECTORY / file_name).read_text(encoding="utf-8")  # reading as text normalises line endings, so a CRLF checkout cannot fail the comparison
        assert hashlib.sha256(committed_text.encode("utf-8")).hexdigest() == entry["sha256"], f"{file_name} was edited by hand; regenerate it"
        assert committed_text == (generated_demo_data_directory / file_name).read_text(encoding="utf-8"), f"{file_name} has drifted from the seed; regenerate it"


def test_the_large_measurement_file_is_not_committed_but_a_fresh_one_matches_its_recorded_hash_and_row_count(generated_demo_data_directory: Path) -> None:
    manifest = load_manifest(DEMO_DATA_DIRECTORY)
    entry = manifest["files"]["04_sli_measurements.sql"]
    assert entry["committed"] is False
    assert "04_sli_measurements.sql" in (DEMO_DATA_DIRECTORY / ".gitignore").read_text(encoding="utf-8").splitlines()
    fresh_bytes = (generated_demo_data_directory / "04_sli_measurements.sql").read_bytes()
    assert hashlib.sha256(fresh_bytes).hexdigest() == entry["sha256"]
    # Thinned: 5-minute rows for the newest days, one row per hour before them (424,512 rows at 5-minute grain before the thinning).
    assert 50_000 < entry["rows"]["sli_measurement"] < 100_000


DEMO_REFERENCE_TIME = datetime(2026, 11, 20, 12, 0)  # the fixed "now" of the demo seed (the file header says so too)


def test_demo_sli_history_has_every_five_minute_window_for_the_newest_days_and_one_row_per_hour_before_them(generated_demo_data_directory: Path) -> None:
    text = (generated_demo_data_directory / "04_sli_measurements.sql").read_text(encoding="utf-8")
    windows = [datetime.fromisoformat(value) for value in re.findall(r"\(N'[0-9a-f-]{36}', '(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d{6}'", text)]
    boundary = DEMO_REFERENCE_TIME - timedelta(days=DEMO_FINE_GRAINED_HISTORY_DAYS)
    older = [window for window in windows if window < boundary]
    newer = [window for window in windows if window >= boundary]
    assert older and newer
    assert all(window.minute == 0 and window.second == 0 for window in older)
    assert all(window.minute % 5 == 0 and window.second == 0 for window in newer)


def test_every_table_is_accounted_for_exactly_once_as_demo_data_excluded_or_empty(generated_demo_data_directory: Path) -> None:
    manifest = load_manifest(generated_demo_data_directory)
    in_files = [table for name, entry in manifest["files"].items() if name[:2].isdigit() and not name.startswith("99") for table in entry["rows"]]
    accounted_for = in_files + list(manifest["excluded_tables"]) + manifest["tables_without_seeded_rows"]
    all_tables = sorted(table.name for table in EntityBase.metadata.sorted_tables)
    assert sorted(accounted_for) == all_tables, (
        f"Tables not accounted for: {sorted(set(all_tables) - set(accounted_for))}; counted twice: {sorted({t for t in accounted_for if accounted_for.count(t) > 1})}. "
        "Assign a new table in backend/scripts/demo_data_sql/demo_data_plan.py"
    )


def test_every_foreign_key_parent_is_inserted_before_its_child(generated_demo_data_directory: Path) -> None:
    manifest = load_manifest(generated_demo_data_directory)
    run_order = inserted_tables_in_run_order(generated_demo_data_directory, manifest)
    assert run_order, "the generated files insert nothing"
    for table in EntityBase.metadata.sorted_tables:
        if table.name not in run_order:
            continue
        for foreign_key in table.foreign_keys:
            parent_name = foreign_key.column.table.name
            if parent_name != table.name:
                assert parent_name in run_order, f"{table.name} has demo rows but its parent {parent_name} has none"
                assert run_order.index(parent_name) < run_order.index(table.name), f"{parent_name} must be inserted before {table.name}"


def test_every_insert_batch_guards_each_row_by_its_key(generated_demo_data_directory: Path) -> None:
    manifest = load_manifest(generated_demo_data_directory)
    for file_name in step_file_names(manifest):
        batches = re.split(r"^GO$", (generated_demo_data_directory / file_name).read_text(encoding="utf-8"), flags=re.MULTILINE)
        for batch in batches:
            if "INSERT INTO [keigan]." in batch and "#demo_rows" in batch:
                assert batch.count("WHERE NOT EXISTS") == 1, f"{file_name}: a batch inserts without a per-row key guard"
                assert not re.search(r"INSERT INTO \[keigan\]\.\[\w+\] \([^)]*\)\s+VALUES", batch), f"{file_name}: rows must reach the real table only through the guarded SELECT"
            else:
                assert "INSERT INTO [keigan]." not in batch, f"{file_name}: an insert that does not go through the guarded staging table"


def test_measurements_get_their_ids_from_sql_server_and_are_matched_by_sli_and_window(generated_demo_data_directory: Path) -> None:
    text = (generated_demo_data_directory / "04_sli_measurements.sql").read_text(encoding="utf-8")
    assert "IDENTITY_INSERT" not in text and "sli_measurement_id" not in text
    assert "WHERE [existing].[sli_id] = [source].[sli_id] AND [existing].[measurement_window_start] = [source].[measurement_window_start]" in text


def test_the_removal_script_deletes_only_seeded_tables_by_key_in_exact_reverse_insert_order(generated_demo_data_directory: Path) -> None:
    manifest = load_manifest(generated_demo_data_directory)
    removal_text = (generated_demo_data_directory / REMOVAL_FILE_NAME).read_text(encoding="utf-8")
    deleted_tables = re.findall(r"^DELETE FROM \[keigan\]\.\[(\w+)\] WHERE ", removal_text, flags=re.MULTILINE)
    deleted_in_order = list(dict.fromkeys(deleted_tables))
    assert deleted_in_order == list(reversed(inserted_tables_in_run_order(generated_demo_data_directory, manifest)))
    assert sorted(deleted_in_order) == sorted(manifest["files"][REMOVAL_FILE_NAME]["rows"]), "the removal script must name exactly the tables that have seeded rows"
    for line in removal_text.splitlines():
        if line.startswith("DELETE"):
            assert " WHERE " in line, f"a DELETE without WHERE would remove real data: {line[:80]}"
    assert "TRUNCATE" not in removal_text and "DBCC" not in removal_text


def test_the_removal_script_stays_small_because_measurements_are_removed_by_sli_not_by_row(generated_demo_data_directory: Path) -> None:
    removal_text = (generated_demo_data_directory / REMOVAL_FILE_NAME).read_text(encoding="utf-8")
    measurement_deletes = re.findall(r"^DELETE FROM \[keigan\]\.\[sli_measurement\] WHERE \[sli_id\] IN \(([^)]*)\);$", removal_text, flags=re.MULTILINE)
    assert len(measurement_deletes) >= 1
    assert sum(delete.count("N'") for delete in measurement_deletes) < 300, "one literal per measurement row would make the script huge"
    assert len(removal_text) < 150_000


def test_runtime_and_secret_tables_never_appear_in_any_generated_script(generated_demo_data_directory: Path) -> None:
    manifest = load_manifest(generated_demo_data_directory)
    assert manifest["excluded_tables"]["background_job"]["seeded_rows"] > 0, "this test is only meaningful while the seed writes a queued job"
    for file_name in manifest["files"]:
        text = (generated_demo_data_directory / file_name).read_text(encoding="utf-8")
        for excluded_table in manifest["excluded_tables"]:
            assert f"[{excluded_table}]" not in text, f"{file_name} touches excluded table {excluded_table}"
    assert "simulate_alerts_for_scenario" not in "".join((generated_demo_data_directory / name).read_text(encoding="utf-8") for name in step_file_names(manifest) if name != "04_sli_measurements.sql")


def test_the_schema_marker_row_written_by_the_reference_data_script_is_never_part_of_the_demo_data(generated_demo_data_directory: Path) -> None:
    manifest = load_manifest(generated_demo_data_directory)
    for file_name in manifest["files"]:
        assert "N'database_schema'" not in (generated_demo_data_directory / file_name).read_text(encoding="utf-8"), f"{file_name} would touch the reference data marker"


def test_demo_data_is_never_referenced_from_the_production_run_all_script() -> None:
    run_all_text = (AZURE_SQL_DIRECTORY / "run_all.sql").read_text(encoding="utf-8")
    assert "demo_data" not in run_all_text
    for demo_file in load_manifest(DEMO_DATA_DIRECTORY)["files"]:
        assert demo_file not in run_all_text


def test_the_demo_runner_runs_committed_steps_in_order_and_never_the_removal_script() -> None:
    manifest = load_manifest(DEMO_DATA_DIRECTORY)
    runner_lines = (DEMO_DATA_DIRECTORY / "run_all_demo_data.sql").read_text(encoding="utf-8").splitlines()
    included = [line.removeprefix(":r ") for line in runner_lines if line.startswith(":r ")]
    assert included == [name for name in step_file_names(manifest) if manifest["files"][name]["committed"]]
    assert REMOVAL_FILE_NAME not in "\n".join(runner_lines)


def test_every_generated_file_is_utf_8_without_byte_order_mark_with_unix_line_endings_and_keeps_japanese_text(generated_demo_data_directory: Path) -> None:
    for path in generated_demo_data_directory.iterdir():
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"{path.name} starts with a byte order mark"
        assert b"\r" not in raw, f"{path.name} has Windows line endings"
        raw.decode("utf-8")  # strict: raises on bad bytes
    seeded_text = (generated_demo_data_directory / "05_incidents_and_investigations.sql").read_text(encoding="utf-8")
    assert re.search("[぀-ヿ一-鿿]", seeded_text), "the seed has Japanese text; it must survive in the scripts"


def test_the_readme_names_every_excluded_table_and_its_reason_and_the_ways_to_run_and_remove() -> None:
    readme = (DEMO_DATA_DIRECTORY / "README.md").read_text(encoding="utf-8")
    for excluded_table, details in load_manifest(DEMO_DATA_DIRECTORY)["excluded_tables"].items():
        assert excluded_table in readme, f"README.md must list excluded table {excluded_table}"
        assert details["reason"] in readme, f"README.md must give the reason for excluding {excluded_table}"
    for required in ("run_all_demo_data.sql", "99_remove_demo_data.sql", "-f 65001", "ConfirmDemoData=yes", "04_sli_measurements.sql", "generate_demo_data_sql.py", "never", "not secrets"):
        assert required in readme, f"README.md must mention {required}"


def test_the_azure_sql_readme_points_to_the_demo_data_folder() -> None:
    assert "demo_data" in (AZURE_SQL_DIRECTORY / "README.md").read_text(encoding="utf-8")
