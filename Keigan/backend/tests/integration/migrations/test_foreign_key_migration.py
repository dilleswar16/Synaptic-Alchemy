"""H12 migration: rows that name a parent that no longer exists are repaired (deleted or detached, never given an invented parent) before the foreign keys are added."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from support.schema_revisions import database_at, insert_row, run_alembic, sql_server_script

PREVIOUS_REVISION = "b7d2e9a4c6f1"
FOREIGN_KEY_REVISION = "c9e4f1b8d3a7"


@pytest.fixture(scope="module")
def old_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A database where every kind of dangling reference exists next to a healthy row of the same table."""
    database_file = database_at(tmp_path_factory.mktemp("old"), PREVIOUS_REVISION)
    with sqlite3.connect(database_file) as connection:
        insert_row(connection, "application", application_id="app-1", application_code="APP1")
        insert_row(connection, "monitored_service", service_id="svc-1", application_id="app-1")
        insert_row(connection, "incident", incident_id="inc-1", application_id="app-1")
        insert_row(connection, "investigation", investigation_id="inv-1", application_id="app-1", incident_id="inc-1")
        insert_row(connection, "service_level_indicator", sli_id="sli-1", application_id="app-1")
        insert_row(connection, "alert_source", alert_source_id="src-1", application_id="app-1")
        insert_row(connection, "knowledge_document", knowledge_document_id="doc-1", application_id="app-1", service_id="svc-gone")
        # parent is gone: the row belongs to it and is deleted
        for table, key, values in (
            ("alert", "alert_id", {"application_id": "app-gone"}), ("alert_event", "alert_event_id", {"application_id": "app-gone", "alert_source_id": "src-1"}),
            ("alert_group", "alert_group_id", {"application_id": "app-gone"}), ("service_level_objective", "slo_id", {"application_id": "app-gone", "sli_id": "sli-1"}),
            ("predictive_signal", "predictive_signal_id", {"application_id": "app-gone"}), ("intelligence_report", "intelligence_report_id", {"application_id": "app-gone"}),
            ("notification_delivery", "notification_delivery_id", {"application_id": "app-gone"}), ("external_integration", "external_integration_id", {"application_id": "app-gone"}),
            ("teams_incident_chat", "teams_incident_chat_id", {"application_id": "app-1", "incident_id": "inc-gone"}),
            ("investigation_timeline_event", "timeline_event_id", {"incident_id": "inc-gone"}), ("incident_communication", "communication_id", {"incident_id": "inc-1", "investigation_id": "inv-gone"}),
            ("postmortem_report", "postmortem_id", {"incident_id": "inc-gone"}), ("conversation", "conversation_id", {"incident_id": "inc-gone"}),
            ("knowledge_chunk", "knowledge_chunk_id", {"application_id": "app-gone", "knowledge_document_id": "doc-1"}),
            ("service_dependency", "service_dependency_id", {"application_id": "app-gone", "upstream_service_id": "svc-1", "downstream_service_id": "svc-1"}),
        ):
            insert_row(connection, table, **{key: f"{table}-dangling", **values})
        insert_row(connection, "slo_burn_alert", slo_burn_alert_id="burn-dangling", slo_id="slo-orphan", application_id="app-gone")
        insert_row(connection, "service_level_objective", slo_id="slo-orphan", application_id="app-gone", sli_id="sli-1")
        insert_row(connection, "sli_measurement", sli_id="sli-gone")
        insert_row(connection, "sli_measurement", sli_id="sli-1", measurement_window_start="2026-01-01 00:00:00.000000")
        # a healthy row of each parent-owned table must survive
        insert_row(connection, "alert", alert_id="alert-healthy", application_id="app-1", service_id="svc-1")
        # an optional reference that dangles is detached, the row stays
        insert_row(connection, "alert", alert_id="alert-service-gone", application_id="app-1", service_id="svc-gone", alert_fingerprint="other")
        insert_row(connection, "alert_group", alert_group_id="group-refs-gone", application_id="app-1", primary_service_id="svc-gone", investigation_id="inv-gone", incident_id="inc-gone")
        insert_row(connection, "service_level_indicator", sli_id="sli-service-gone", application_id="app-1", service_id="svc-gone")
        insert_row(connection, "predictive_signal", predictive_signal_id="signal-refs-gone", application_id="app-1", service_id="svc-gone", sli_id="sli-gone")
        insert_row(connection, "notification_delivery", notification_delivery_id="delivery-refs-gone", application_id="app-1", incident_id="inc-gone", investigation_id="inv-gone")
        insert_row(connection, "notification_delivery", notification_delivery_id="delivery-platform", application_id=None)
        insert_row(connection, "external_integration", external_integration_id="integration-platform", application_id=None)
        insert_row(connection, "knowledge_chunk", knowledge_chunk_id="chunk-service-gone", application_id="app-1", knowledge_document_id="doc-1", service_id="svc-gone")
        insert_row(connection, "investigation_evidence", evidence_id="evidence-service-gone", investigation_id="inv-1", service_id="svc-gone")
    return database_file


def surviving_ids(database_file: Path, table: str, key: str) -> set[str]:
    with sqlite3.connect(database_file) as connection:
        return {row[0] for row in connection.execute(f"SELECT {key} FROM {table}")}


def value_of(database_file: Path, table: str, key: str, key_value: str, column: str) -> object:
    with sqlite3.connect(database_file) as connection:
        return connection.execute(f"SELECT {column} FROM {table} WHERE {key} = ?", (key_value,)).fetchone()[0]


@pytest.fixture(scope="module")
def upgraded_database(old_database: Path) -> Path:
    run_alembic("upgrade", FOREIGN_KEY_REVISION, database_file=old_database)
    return old_database


@pytest.mark.parametrize(("table", "key"), [
    ("alert", "alert_id"), ("alert_event", "alert_event_id"), ("alert_group", "alert_group_id"), ("service_level_objective", "slo_id"), ("predictive_signal", "predictive_signal_id"),
    ("intelligence_report", "intelligence_report_id"), ("notification_delivery", "notification_delivery_id"), ("external_integration", "external_integration_id"),
    ("teams_incident_chat", "teams_incident_chat_id"), ("investigation_timeline_event", "timeline_event_id"), ("incident_communication", "communication_id"),
    ("postmortem_report", "postmortem_id"), ("conversation", "conversation_id"), ("knowledge_chunk", "knowledge_chunk_id"), ("service_dependency", "service_dependency_id"),
])
def test_a_row_whose_parent_no_longer_exists_is_deleted(upgraded_database: Path, table: str, key: str) -> None:
    assert f"{table}-dangling" not in surviving_ids(upgraded_database, table, key)


def test_children_of_a_deleted_row_go_with_it_and_dangling_measurements_are_removed(upgraded_database: Path) -> None:
    assert "burn-dangling" not in surviving_ids(upgraded_database, "slo_burn_alert", "slo_burn_alert_id")
    assert surviving_ids(upgraded_database, "sli_measurement", "sli_id") == {"sli-1"}


def test_healthy_rows_and_rows_without_an_application_by_design_survive(upgraded_database: Path) -> None:
    assert "alert-healthy" in surviving_ids(upgraded_database, "alert", "alert_id")
    assert "delivery-platform" in surviving_ids(upgraded_database, "notification_delivery", "notification_delivery_id")
    assert "integration-platform" in surviving_ids(upgraded_database, "external_integration", "external_integration_id")


def test_an_optional_reference_to_a_missing_row_is_set_to_null_and_the_row_stays(upgraded_database: Path) -> None:
    assert value_of(upgraded_database, "alert", "alert_id", "alert-service-gone", "service_id") is None
    for column in ("primary_service_id", "investigation_id", "incident_id"):
        assert value_of(upgraded_database, "alert_group", "alert_group_id", "group-refs-gone", column) is None
    assert value_of(upgraded_database, "service_level_indicator", "sli_id", "sli-service-gone", "service_id") is None
    assert value_of(upgraded_database, "predictive_signal", "predictive_signal_id", "signal-refs-gone", "service_id") is None
    assert value_of(upgraded_database, "predictive_signal", "predictive_signal_id", "signal-refs-gone", "sli_id") is None
    assert value_of(upgraded_database, "notification_delivery", "notification_delivery_id", "delivery-refs-gone", "incident_id") is None
    assert value_of(upgraded_database, "knowledge_document", "knowledge_document_id", "doc-1", "service_id") is None
    assert value_of(upgraded_database, "knowledge_chunk", "knowledge_chunk_id", "chunk-service-gone", "service_id") is None
    assert value_of(upgraded_database, "investigation_evidence", "evidence_id", "evidence-service-gone", "service_id") is None


def test_no_application_service_or_other_parent_was_invented(upgraded_database: Path) -> None:
    assert surviving_ids(upgraded_database, "application", "application_id") == {"app-1"}
    assert surviving_ids(upgraded_database, "monitored_service", "service_id") == {"svc-1"}
    assert surviving_ids(upgraded_database, "incident", "incident_id") == {"inc-1"}
    with sqlite3.connect(upgraded_database) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_sqlite_databases_are_not_rebuilt_so_no_child_row_is_cascade_deleted(upgraded_database: Path) -> None:
    """SQLite cannot add a foreign key to an existing table without a rebuild (which cascade-deletes rows), so the revision leaves the keys to recreated databases."""
    with sqlite3.connect(upgraded_database) as connection:
        keys = connection.execute("PRAGMA foreign_key_list(alert)").fetchall()
    assert keys == []
    assert "alert-healthy" in surviving_ids(upgraded_database, "alert", "alert_id")


def test_the_sql_server_script_repairs_first_and_adds_every_foreign_key_with_the_right_delete_rule() -> None:
    """Rendered with Alembic offline mode; the T-SQL was not executed (no SQL Server available)."""
    script = sql_server_script(PREVIOUS_REVISION, FOREIGN_KEY_REVISION)
    first_alter = script.index("ALTER TABLE")
    for repair in ("DELETE FROM keigan.alert WHERE", "UPDATE keigan.alert SET service_id=NULL", "DELETE FROM keigan.sli_measurement WHERE", "UPDATE keigan.alert_group SET primary_service_id=NULL"):
        assert repair in script and script.index(repair) < first_alter, repair
    assert "ALTER TABLE keigan.alert ADD CONSTRAINT fk_alert_application_id_application FOREIGN KEY(application_id) REFERENCES keigan.application (application_id) ON DELETE CASCADE" in script
    assert "ALTER TABLE keigan.alert ADD CONSTRAINT fk_alert_service_id_monitored_service FOREIGN KEY(service_id) REFERENCES keigan.monitored_service (service_id);" in script
    assert "ALTER TABLE keigan.alert_event ADD CONSTRAINT fk_alert_event_application_id_application FOREIGN KEY(application_id) REFERENCES keigan.application (application_id);" in script
    assert "ALTER TABLE keigan.sli_measurement ADD CONSTRAINT fk_sli_measurement_sli_id_service_level_indicator FOREIGN KEY(sli_id) REFERENCES keigan.service_level_indicator (sli_id) ON DELETE CASCADE" in script
