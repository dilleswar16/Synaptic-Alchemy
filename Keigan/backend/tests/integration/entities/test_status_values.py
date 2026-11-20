"""keigan/entities/status_values.py (H13): every fixed-value column has one definition, the database enforces it, and the code only writes allowed values."""

from __future__ import annotations

import ast
import sqlite3
import typing
from enum import StrEnum
from pathlib import Path

import pytest
from sqlalchemy import Boolean, CheckConstraint, Float, Integer, String, create_engine
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.types import JSON

from keigan.entities import all_entities  # noqa: F401  (registers every table)
from keigan.entities import status_values as values
from keigan.entities.base_entity import EntityBase

KEIGAN_DIRECTORY = Path(values.__file__).resolve().parents[1]

# (table, column, the enum that is the one definition of the column's values). Typed out here on purpose: a new CHECK must be added to this list too.
CONSTRAINED_COLUMNS: list[tuple[str, str, type[StrEnum]]] = [
    ("alert_source", "source_tool", values.AlertSourceTool), ("alert_source", "source_status", values.AlertSourceStatus), ("alert_event", "processing_status", values.AlertEventProcessingStatus),
    ("alert", "alert_status", values.AlertStatus), ("alert", "final_disposition", values.AlertFinalDisposition), ("alert_decision", "pipeline_stage", values.AlertPipelineStage),
    ("alert_group", "group_status", values.AlertGroupStatus), ("alert_group", "user_feedback_verdict", values.AlertGroupFeedbackVerdict), ("noise_reduction_policy", "policy_mode", values.NoisePolicyMode),
    ("servicenow_assignment_group", "verification_status", values.AssignmentGroupVerificationStatus), ("incident", "incident_source", values.IncidentSource), ("incident", "incident_status", values.IncidentStatus),
    ("incident", "keigan_priority", values.Priority), ("investigation", "investigation_trigger", values.InvestigationTrigger), ("investigation", "investigation_status", values.InvestigationStatus),
    ("investigation", "current_stage_name", values.InvestigationStage), ("investigation", "user_feedback_verdict", values.InvestigationFeedbackVerdict),
    ("investigation_hypothesis", "analysis_perspective", values.AnalysisPerspective), ("investigation_hypothesis", "fix_risk_level", values.RiskLevel), ("investigation_evidence", "signal_strength", values.RiskLevel),
    ("incident_communication", "communication_status", values.CommunicationStatus), ("postmortem_report", "report_status", values.PostmortemStatus),
    ("conversation", "conversation_scope", values.ConversationScope), ("conversation_message", "author_role", values.MessageAuthorRole),
    ("application", "lifecycle_status", values.ApplicationLifecycleStatus), ("application", "criticality_tier", values.CriticalityTier), ("monitored_service", "criticality_tier", values.CriticalityTier),
    ("application_component", "component_type", values.ComponentType), ("application_component", "access_verification_status", values.AccessVerificationStatus),
    ("log_tool_connection", "connection_status", values.LogToolConnectionStatus), ("service_log_source", "last_read_test_status", values.ReadTestStatus),
    ("external_integration", "integration_status", values.IntegrationStatus), ("knowledge_document", "ai_digest_status", values.DocumentDigestStatus),
    ("application_topology", "generation_status", values.TopologyGenerationStatus), ("application_topology", "review_status", values.TopologyReviewStatus),
    ("topology_review_comment", "review_verdict", values.TopologyReviewVerdict), ("stakeholder", "recipient_type", values.StakeholderRecipientType),
    ("stakeholder", "stakeholder_role", values.StakeholderRole), ("stakeholder", "minimum_priority", values.Priority), ("notification_delivery", "delivery_channel", values.DeliveryChannel),
    ("notification_delivery", "delivery_status", values.DeliveryStatus), ("teams_incident_chat", "chat_status", values.TeamsChatStatus), ("background_job", "job_status", values.JobStatus),
    ("predictive_signal", "signal_status", values.SignalStatus), ("predictive_signal", "signal_severity", values.SignalSeverity), ("slo_burn_alert", "burn_alert_severity", values.BurnAlertSeverity),
    ("intelligence_report", "report_type", values.IntelligenceReportType),
]


@pytest.fixture(scope="module")
def schema_connection(tmp_path_factory: pytest.TempPathFactory):
    """A fresh SQLite database created from the entities (what local development and the tests use): the constraints come from create_all."""
    database_file = tmp_path_factory.mktemp("status_values") / "fresh.db"
    engine = create_engine(f"sqlite:///{database_file.as_posix()}")
    EntityBase.metadata.create_all(engine)
    engine.dispose()
    connection = sqlite3.connect(database_file)
    yield connection
    connection.close()


def constrained_columns_in_the_entities() -> set[tuple[str, str]]:
    return {
        (table.name, constraint.name.removeprefix(f"ck_{table.name}_").removesuffix("_values"))
        for table in EntityBase.metadata.sorted_tables
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name and constraint.name.endswith("_values")
    }


def required_row(table_name: str) -> dict[str, object]:
    """Values for every NOT NULL column without a database default; checked columns get their first allowed value so only the column under test can fail."""
    first_allowed = {(table, column): next(iter(enum_class)).value for table, column, enum_class in CONSTRAINED_COLUMNS}
    row: dict[str, object] = {}
    for column in EntityBase.metadata.tables[table_name].columns:
        if column.nullable or column.server_default is not None:
            continue
        if (table_name, column.name) in first_allowed:
            row[column.name] = first_allowed[(table_name, column.name)]
        elif isinstance(column.type, (Integer,)) and column.primary_key:
            continue
        elif isinstance(column.type, (Integer, Boolean, Float)) or column.type.__class__.__name__ == "BigInteger":
            row[column.name] = 0
        elif isinstance(column.type, JSON):
            row[column.name] = "{}"
        elif isinstance(column.type, (String, SqlEnum)):
            row[column.name] = "x"
        else:
            row[column.name] = "2026-01-01 00:00:00.000000"
    return row


def insert(connection: sqlite3.Connection, table_name: str, column_name: str, value: str) -> None:
    row = {**required_row(table_name), column_name: value}
    connection.execute(f"INSERT INTO {table_name} ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})", list(row.values()))


def test_the_entities_constrain_exactly_the_columns_listed_here() -> None:
    assert constrained_columns_in_the_entities() == {(table, column) for table, column, _ in CONSTRAINED_COLUMNS}


@pytest.mark.parametrize(("table", "column", "enum_class"), CONSTRAINED_COLUMNS, ids=[f"{table}.{column}" for table, column, _ in CONSTRAINED_COLUMNS])
def test_the_database_rejects_a_value_outside_the_enum_and_accepts_every_member(schema_connection: sqlite3.Connection, table: str, column: str, enum_class: type[StrEnum]) -> None:
    with pytest.raises(sqlite3.IntegrityError) as rejection:
        insert(schema_connection, table, column, "not_a_real_value")
    assert f"ck_{table}_{column}_values" in str(rejection.value)
    for member in enum_class:
        schema_connection.execute("SAVEPOINT member")
        insert(schema_connection, table, column, member.value)
        schema_connection.execute("ROLLBACK TO member")


def test_a_database_with_no_value_in_the_column_is_still_allowed_where_the_column_is_nullable(schema_connection: sqlite3.Connection) -> None:
    schema_connection.execute("SAVEPOINT nullable")
    row = required_row("alert")
    schema_connection.execute(f"INSERT INTO alert ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})", list(row.values()))  # final_disposition stays NULL
    schema_connection.execute("ROLLBACK TO nullable")


COLUMN_NAMES = {column for _, column, _ in CONSTRAINED_COLUMNS}
ALLOWED_BY_COLUMN: dict[str, set[str]] = {}
for _table, _column, _enum in CONSTRAINED_COLUMNS:
    ALLOWED_BY_COLUMN.setdefault(_column, set()).update(member.value for member in _enum)


def string_constants_in(expression: ast.expr) -> list[str]:
    """Literals a value expression can evaluate to directly: the constant itself or either branch of ``a if cond else b``."""
    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        return [expression.value]
    if isinstance(expression, ast.IfExp):
        return [*string_constants_in(expression.body), *string_constants_in(expression.orelse)]
    return []


def literals_written_to_constrained_columns() -> list[tuple[str, int, str, str]]:
    found: list[tuple[str, int, str, str]] = []
    for path in sorted(KEIGAN_DIRECTORY.rglob("*.py")):
        if path.parts[-2:] == ("entities", "status_values.py") or "dtos" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.keyword) and node.arg in COLUMN_NAMES:
                written = [(node.arg, literal) for literal in string_constants_in(node.value)]
            elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Attribute) and node.targets[0].attr in COLUMN_NAMES:
                written = [(node.targets[0].attr, literal) for literal in string_constants_in(node.value)]
            else:
                continue
            found.extend((str(path.relative_to(KEIGAN_DIRECTORY)), node.lineno, column, literal) for column, literal in written)
    return found


def test_every_literal_the_code_writes_to_a_constrained_column_is_an_allowed_value() -> None:
    not_allowed = [f"{file}:{line} {column}={literal!r}" for file, line, column, literal in literals_written_to_constrained_columns() if literal not in ALLOWED_BY_COLUMN[column]]
    assert not_allowed == []


def test_the_scan_sees_the_known_writers() -> None:
    """Guards the scan itself: it must find ordinary writers, or the test above proves nothing."""
    written = {(column, literal) for _, _, column, literal in literals_written_to_constrained_columns()}
    assert {("alert_status", "resolved"), ("group_status", "queued"), ("job_status", "dead_lettered"), ("investigation_status", "cancelled"), ("delivery_status", "simulated")} <= written


def literal_values(annotation: object) -> set[str]:
    """The values of a ``Literal[...]`` annotation, also inside ``X | None``."""
    arguments = typing.get_args(annotation)
    if typing.get_origin(annotation) is typing.Literal:
        return set(arguments)
    return {value for argument in arguments for value in literal_values(argument)}


def test_the_api_request_types_only_offer_values_the_database_accepts() -> None:
    """The DTO Literals stay as they are (the OpenAPI shape does not change); this keeps them inside the enums."""
    from keigan.dtos import alert_dtos, application_dtos, intelligence_dtos, knowledge_dtos, notification_dtos, onboarding_dtos

    pairs = [
        (alert_dtos.AlertSourceCreateRequest.model_fields["source_tool"].annotation, values.AlertSourceTool),
        (alert_dtos.NoisePolicyUpdateRequest.model_fields["policy_mode"].annotation, values.NoisePolicyMode),
        (alert_dtos.AlertGroupFeedbackRequest.model_fields["verdict"].annotation, values.AlertGroupFeedbackVerdict),
        (application_dtos.ApplicationCreateRequest.model_fields["lifecycle_status"].annotation, values.ApplicationLifecycleStatus),
        (application_dtos.ApplicationUpdateRequest.model_fields["lifecycle_status"].annotation, values.ApplicationLifecycleStatus),
        (application_dtos.CriticalityTier, values.CriticalityTier), (onboarding_dtos.ComponentType, values.ComponentType),
        (notification_dtos.RecipientType, values.StakeholderRecipientType), (notification_dtos.StakeholderRole, values.StakeholderRole), (notification_dtos.PriorityCode, values.Priority),
        (knowledge_dtos.TopologyReviewRequest.model_fields["review_verdict"].annotation, values.TopologyReviewVerdict), (intelligence_dtos.SignalStatus, values.SignalStatus),
    ]
    for annotation, enum_class in pairs:
        assert literal_values(annotation) <= {member.value for member in enum_class}, annotation
    assert set(notification_dtos.NOTIFICATION_CHANNEL_VALUES) == {member.value for member in values.DeliveryChannel}
