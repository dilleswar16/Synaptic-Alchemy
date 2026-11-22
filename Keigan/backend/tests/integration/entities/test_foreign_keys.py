"""Foreign keys on every reference to an application, incident, investigation, SLI or service (H12), and the SQL Server cascade rule."""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from keigan.config.database_config import open_session
from keigan.entities import all_entities  # noqa: F401  (registers every table)
from keigan.entities.alert_entities import Alert
from keigan.entities.base_entity import EntityBase
from keigan.entities.slo_entities import PredictiveSignal
from keigan.security.current_user import CurrentUser
from keigan.services.application_service import ApplicationService
from support.application_graph import create_application_graph

REFERENCE_COLUMN_NAMES = ("application_id", "incident_id", "investigation_id", "sli_id", "service_id", "primary_service_id")
# History is kept on purpose after an application is deleted: the audit trail, the AI usage records and the steps of Ask Keigan answers name the application without a key, and a coverage gap names the service it could not check (a recorded fact that outlives the service).
HISTORY_COLUMNS = {("audit_event", "application_id"), ("llm_usage_record", "application_id"), ("llm_usage_record", "investigation_id"), ("chat_run_step", "application_id"), ("investigation_coverage_gap", "service_id")}
ADMIN = CurrentUser(user_principal_name="admin@example.com", display_name="Admin", email_address=None, group_names=frozenset(), group_object_ids=frozenset(), is_keigan_admin=True)


def test_every_reference_to_an_application_incident_investigation_sli_or_service_is_a_foreign_key() -> None:
    unprotected = sorted(
        f"{table.name}.{column.name}"
        for table in EntityBase.metadata.sorted_tables
        for column in table.columns
        if column.name in REFERENCE_COLUMN_NAMES and not column.foreign_keys and not column.primary_key and (table.name, column.name) not in HISTORY_COLUMNS
    )
    assert unprotected == [], f"These columns name another row but the database cannot check it: {unprotected}"


def test_no_table_can_be_reached_by_two_cascading_paths_from_the_same_table() -> None:
    """SQL Server rejects a foreign key that would make a delete reach one table twice (CASCADE and SET NULL both count)."""
    cascading_targets: dict[str, list[str]] = {table.name: [] for table in EntityBase.metadata.sorted_tables}
    for table in EntityBase.metadata.sorted_tables:
        for foreign_key in table.foreign_key_constraints:
            if foreign_key.ondelete in ("CASCADE", "SET NULL", "SET DEFAULT"):
                cascading_targets[foreign_key.referred_table.name].append(table.name)

    def paths_to_each_table(start: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        pending = list(cascading_targets[start])
        while pending:
            reached = pending.pop()
            counts[reached] = counts.get(reached, 0) + 1
            pending.extend(cascading_targets[reached])
        return counts

    violations = [f"{start} reaches {table} {count} times" for start in cascading_targets for table, count in paths_to_each_table(start).items() if count > 1]
    assert violations == []


async def test_the_database_rejects_an_alert_for_an_application_that_does_not_exist(seed_context) -> None:
    with pytest.raises(IntegrityError):
        async with open_session() as session:
            session.add(Alert(application_id="no-such-application", alert_fingerprint="f", rule_name="rule"))


async def test_the_database_rejects_a_signal_for_a_service_that_does_not_exist(seed_context) -> None:
    graph = await create_application_graph()
    with pytest.raises(IntegrityError):
        async with open_session() as session:
            session.add(PredictiveSignal(application_id=graph.application_id, service_id="no-such-service", detector_name="trend", signal_title="signal"))


async def test_deleting_an_application_leaves_no_row_that_references_it(seed_context) -> None:
    graph = await create_application_graph()
    async with open_session() as session:
        await ApplicationService(session).delete_application(ADMIN, graph.application_id)
    identifiers_by_column = {
        "application_id": [graph.application_id], "incident_id": [graph.incident_id], "investigation_id": [graph.investigation_id], "sli_id": [graph.sli_id],
        "service_id": [graph.first_service_id, graph.second_service_id], "primary_service_id": [graph.first_service_id], "alert_group_id": [graph.alert_group_id],
        "runbook_id": [graph.runbook_id], "knowledge_document_id": [graph.knowledge_document_id],
    }
    leftovers: list[str] = []
    async with open_session() as session:
        for table in EntityBase.metadata.sorted_tables:
            for column in table.columns:
                if column.name in identifiers_by_column and (table.name, column.name) not in HISTORY_COLUMNS:
                    remaining = (await session.execute(select(column).where(column.in_(identifiers_by_column[column.name])).limit(1))).first()
                    if remaining:
                        leftovers.append(f"{table.name}.{column.name}")
        foreign_key_violations = (await session.execute(text("PRAGMA foreign_key_check"))).all()
    assert leftovers == [] and foreign_key_violations == []
