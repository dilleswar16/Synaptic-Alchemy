"""Which table goes into which demo data file, in what order, and which tables never become demo data.

The ORDER comes from the entity metadata (foreign keys), never from a hand-typed list. The only hand-written parts are the two
declarations below. ``build_demo_data_plan`` checks them against the entities and the rows the seed really wrote, so a table that
was added later and nobody assigned makes the generator (and its test) fail with the table named.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from sqlalchemy import MetaData, Table

from demo_data_sql.demo_data_errors import DemoDataSqlError

PLAN_MODULE_HINT = (
    "Assign it to a file in DEMO_DATA_FILE_DECLARATIONS or give it a reason in EXCLUDED_TABLE_REASONS (both in "
    "backend/scripts/demo_data_sql/demo_data_plan.py)."
)


@dataclass(frozen=True)
class DemoDataFileDeclaration:
    """One generated step file. ``committed=False`` means it is written on demand and listed in ``demo_data/.gitignore`` (too large to commit)."""

    file_name: str
    title: str
    table_names: tuple[str, ...]
    committed: bool = True


# The grouping is a business choice (what a DBA wants to run or skip together). Order inside a file is derived from foreign keys.
DEMO_DATA_FILE_DECLARATIONS: tuple[DemoDataFileDeclaration, ...] = (
    DemoDataFileDeclaration(
        "01_applications_and_topology.sql",
        "Demo data 1 of 6: applications, components, services, topology, stakeholders",
        ("application", "application_component", "log_tool_connection", "monitored_service", "service_dependency", "service_log_source", "discovered_resource", "servicenow_assignment_group", "stakeholder", "stakeholder_subscribed_service"),
    ),
    DemoDataFileDeclaration(
        "02_knowledge.sql",
        "Demo data 2 of 6: knowledge documents, runbooks, topology reviews, record links, integrations",
        ("knowledge_document", "knowledge_chunk", "runbook", "application_topology", "topology_review_comment", "application_record_link", "external_integration", "runbook_applies_to_service", "topology_source_document"),
    ),
    DemoDataFileDeclaration(
        "03_alerts_and_slos.sql",
        "Demo data 3 of 6: alert sources, noise policies, historical alerts, SLIs and SLOs",
        ("alert_source", "noise_reduction_policy", "maintenance_window", "alert_mute_rule", "alert", "alert_event", "alert_decision", "service_level_indicator", "service_level_objective", "slo_burn_alert", "maintenance_window_applies_to_service"),
    ),
    DemoDataFileDeclaration(
        "04_sli_measurements.sql",
        "Demo data 4 of 6: 30 days of SLI measurements (5-minute rows for the newest days, one row per hour before them; large, generated on demand, optional)",
        ("sli_measurement",),
        committed=False,
    ),
    DemoDataFileDeclaration(
        "05_incidents_and_investigations.sql",
        "Demo data 5 of 6: incidents, investigations, evidence, postmortems, alert groups (alert groups point at incidents and investigations, so they load after them)",
        ("incident", "incident_communication", "investigation", "investigation_hypothesis", "investigation_evidence", "investigation_coverage_gap", "investigation_trace_step", "action_item", "investigation_timeline_event", "postmortem_report", "incident_affected_service", "investigation_investigated_service", "investigation_matched_runbook", "alert_group", "alert_group_affected_service", "incident_memory_entry", "incident_memory_key", "incident_memory_relevance_feedback", "investigation_memory_reference"),
    ),
    DemoDataFileDeclaration(
        "06_intelligence_and_collaboration.sql",
        "Demo data 6 of 6: predictive signals, reports, incident chat, notification history, simulation settings",
        ("predictive_signal", "intelligence_report", "teams_incident_chat", "conversation", "conversation_application", "conversation_message", "notification_delivery", "platform_setting"),
    ),
)

# Runtime or secret state is NOT demo data: loading it into a live database would change how the platform behaves or weaken it.
EXCLUDED_TABLE_REASONS: dict[str, str] = {
    "background_job": "Job queue rows are picked up and run by the workers (for example a queued simulate_alerts_for_scenario); seeded jobs would run in Azure.",
    "stored_secret": "Holds secret values; secrets are created through the Keigan UI or Key Vault, never from a script in the repository.",
    "platform_user": "Real people sign in and are created on first sign-in; a seeded identity row could grant or block access to a real person.",
    "llm_usage_record": "Records of real model calls and their cost; demo rows would distort usage reporting and budgets.",
    "audit_event": "The audit trail is append-only evidence of what really happened; seeded or deleted audit rows would make it untrustworthy.",
}


@dataclass(frozen=True)
class PlannedFile:
    declaration: DemoDataFileDeclaration
    tables: tuple[Table, ...]  # only tables with seeded rows, parents before children


@dataclass(frozen=True)
class DemoDataPlan:
    files: tuple[PlannedFile, ...]
    excluded_table_reasons: Mapping[str, str]

    @property
    def tables_in_insert_order(self) -> tuple[Table, ...]:
        return tuple(table for planned_file in self.files for table in planned_file.tables)


def _declared_file_by_table(declarations: Iterable[DemoDataFileDeclaration], tables_by_name: Mapping[str, Table], excluded: Mapping[str, str]) -> dict[str, str]:
    file_by_table: dict[str, str] = {}
    for excluded_name in excluded:
        if excluded_name not in tables_by_name:
            raise DemoDataSqlError(f"EXCLUDED_TABLE_REASONS names table '{excluded_name}', which no entity defines. Remove it or fix the name in demo_data_plan.py.")
    for declaration in declarations:
        for table_name in declaration.table_names:
            if table_name not in tables_by_name:
                raise DemoDataSqlError(f"{declaration.file_name} lists table '{table_name}', which no entity defines. Remove or rename it in DEMO_DATA_FILE_DECLARATIONS (demo_data_plan.py).")
            if table_name in excluded:
                raise DemoDataSqlError(f"Table '{table_name}' is both excluded (EXCLUDED_TABLE_REASONS) and listed in {declaration.file_name}. Keep it in only one of them.")
            if table_name in file_by_table:
                raise DemoDataSqlError(f"Table '{table_name}' is listed in both {file_by_table[table_name]} and {declaration.file_name}. A table belongs in exactly one file.")
            file_by_table[table_name] = declaration.file_name
    return file_by_table


def _check_every_seeded_table_is_assigned(seeded_row_counts: Mapping[str, int], file_by_table: Mapping[str, str], excluded: Mapping[str, str]) -> None:
    unassigned = sorted(name for name, row_count in seeded_row_counts.items() if row_count > 0 and name not in file_by_table and name not in excluded)
    if unassigned:
        raise DemoDataSqlError(f"The seed wrote rows into table(s) {', '.join(unassigned)} and nobody decided what happens to them. {PLAN_MODULE_HINT}")


def _check_parents_come_first(tables: Iterable[Table], file_by_table: Mapping[str, str], file_position: Mapping[str, int], excluded: Mapping[str, str]) -> None:
    for table in tables:
        for foreign_key in table.foreign_keys:
            parent_name = foreign_key.column.table.name
            if parent_name == table.name:
                continue
            if parent_name in excluded:
                raise DemoDataSqlError(f"Demo table '{table.name}' has a foreign key to '{parent_name}', which is excluded from demo data ({excluded[parent_name]}). Exclude '{table.name}' too or stop seeding rows that need it.")
            if parent_name in file_by_table and file_position[file_by_table[parent_name]] > file_position[file_by_table[table.name]]:
                raise DemoDataSqlError(
                    f"Table '{table.name}' is in {file_by_table[table.name]} but its parent '{parent_name}' is in {file_by_table[parent_name]}, which runs later. Move '{parent_name}' to an earlier file."
                )


def build_demo_data_plan(
    metadata: MetaData,
    seeded_row_counts: Mapping[str, int],
    file_declarations: Iterable[DemoDataFileDeclaration] = DEMO_DATA_FILE_DECLARATIONS,
    excluded_table_reasons: Mapping[str, str] = EXCLUDED_TABLE_REASONS,
) -> DemoDataPlan:
    """Check the declarations against the entities and the seeded rows, and order the tables by foreign keys."""
    declarations = tuple(file_declarations)
    tables_in_foreign_key_order = metadata.sorted_tables
    tables_by_name = {table.name: table for table in tables_in_foreign_key_order}
    file_by_table = _declared_file_by_table(declarations, tables_by_name, excluded_table_reasons)
    _check_every_seeded_table_is_assigned(seeded_row_counts, file_by_table, excluded_table_reasons)
    file_position = {declaration.file_name: position for position, declaration in enumerate(declarations)}
    seeded_tables = [table for table in tables_in_foreign_key_order if table.name in file_by_table and seeded_row_counts.get(table.name, 0) > 0]
    _check_parents_come_first(seeded_tables, file_by_table, file_position, excluded_table_reasons)
    planned_files = tuple(
        PlannedFile(declaration, tuple(table for table in seeded_tables if file_by_table[table.name] == declaration.file_name)) for declaration in declarations
    )
    return DemoDataPlan(planned_files, dict(excluded_table_reasons))
