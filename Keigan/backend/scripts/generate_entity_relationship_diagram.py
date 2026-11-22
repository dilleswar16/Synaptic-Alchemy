"""Generates My Plans/architecture/15_ENTITY_RELATIONSHIP_DIAGRAM.md (Mermaid) from Keigan's entities — re-run after any entity change.

Usage (from backend/):  .\\.venv\\Scripts\\python.exe scripts\\generate_entity_relationship_diagram.py
Solid lines are real foreign keys. Dotted lines are ID references kept without a foreign key on purpose (history that must
survive deletes, cross-domain links, or SQL Server's one-cascade-path rule); the column name ends in the target's key name.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("DATABASE_SCHEMA", "")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import JSON, BigInteger, Boolean, Column, Float, Integer, String, Table, Text, UniqueConstraint  # noqa: E402

from keigan.entities import all_entities  # noqa: E402, F401
from keigan.entities.base_entity import EntityBase, UtcDateTime  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "My Plans" / "architecture" / "15_ENTITY_RELATIONSHIP_DIAGRAM.md"
DOMAIN_TITLES = {
    "application_entities": "Applications and onboarding",
    "topology_entities": "Topology review",
    "stakeholder_entities": "Stakeholders, runbooks and ServiceNow groups",
    "knowledge_entities": "Knowledge base",
    "incident_entities": "Incidents and investigations",
    "alert_entities": "Alerts and noise reduction",
    "slo_entities": "SLIs and SLOs",
    "intelligence_entities": "Predictive intelligence",
    "notification_entities": "Notifications and incident chats",
    "chat_entities": "Keigan AI chat",
    "platform_entities": "Platform (users, settings, jobs, audit, AI usage)",
}


def column_type_label(column: Column) -> str:
    column_type = column.type
    if isinstance(column_type, UtcDateTime):
        return "datetime2"
    if isinstance(column_type, JSON):
        return "json"
    if isinstance(column_type, Text) or (isinstance(column_type, String) and column_type.length is None):
        return "nvarchar(max)"
    if isinstance(column_type, String):
        return f"nvarchar({column_type.length})"
    if isinstance(column_type, Boolean):
        return "bit"
    if isinstance(column_type, BigInteger):
        return "bigint"
    if isinstance(column_type, Integer):
        return "int"
    if isinstance(column_type, Float):
        return "float"
    return column_type.__class__.__name__.lower()


def unique_column_names(table: Table) -> set[str]:
    single_column_uniques = {constraint.columns.keys()[0] for constraint in table.constraints if isinstance(constraint, UniqueConstraint) and len(constraint.columns) == 1}
    return single_column_uniques | {column.name for column in table.columns if column.unique}


def relationship_lines(tables: list[Table]) -> list[tuple[str, str, str, bool, bool]]:
    """(parent, child, column, is_foreign_key, is_nullable) for every foreign key and every logical ID reference."""
    # Which table an "<x>_id" column points to: the table named <x> first, then real foreign key targets, then any primary key.
    single_key_tables = [table for table in tables if len(table.primary_key.columns) == 1]
    table_by_primary_key_name = {table.primary_key.columns.keys()[0]: table.name for table in single_key_tables if table.primary_key.columns.keys()[0] == f"{table.name}_id"}
    for table in tables:
        for foreign_key in table.foreign_keys:
            if foreign_key.parent.name == foreign_key.column.name:
                table_by_primary_key_name.setdefault(foreign_key.column.name, foreign_key.column.table.name)
    for table in single_key_tables:
        table_by_primary_key_name.setdefault(table.primary_key.columns.keys()[0], table.name)
    relationships = []
    for table in tables:
        foreign_key_columns = set()
        for foreign_key in table.foreign_keys:
            foreign_key_columns.add(foreign_key.parent.name)
            relationships.append((foreign_key.column.table.name, table.name, foreign_key.parent.name, True, foreign_key.parent.nullable))
        for column in table.columns:
            if column.primary_key or column.name in foreign_key_columns or not column.name.endswith("_id"):
                continue
            parent_table_name = table_by_primary_key_name.get(column.name)
            if parent_table_name and parent_table_name != table.name:
                relationships.append((parent_table_name, table.name, column.name, False, bool(column.nullable)))
    return relationships


def render_relationship(parent: str, child: str, column_name: str, is_foreign_key: bool, is_nullable: bool) -> str:
    parent_side = "|o" if is_nullable else "||"
    line = "--" if is_foreign_key else ".."
    return f'    {parent} {parent_side}{line}o{{ {child} : "{column_name}"'


def render_entity(table: Table) -> list[str]:
    unique_columns = unique_column_names(table)
    foreign_key_columns = {foreign_key.parent.name for foreign_key in table.foreign_keys}
    lines = [f"    {table.name} {{"]
    for column in table.columns:
        keys = [key for key, applies in (("PK", column.primary_key), ("FK", column.name in foreign_key_columns), ("UK", column.name in unique_columns)) if applies]
        nullable_note = ' "nullable"' if column.nullable and not column.primary_key else ""
        lines.append(f"        {column_type_label(column)} {column.name}{(' ' + ', '.join(keys)) if keys else ''}{nullable_note}")
    lines.append("    }")
    return lines


def main() -> None:
    tables = list(EntityBase.metadata.sorted_tables)
    module_by_table_name = {mapper.local_table.name: mapper.class_.__module__.rsplit(".", 1)[-1] for mapper in EntityBase.registry.mappers}
    docstring_by_table_name = {mapper.local_table.name: (mapper.class_.__doc__ or "").strip().splitlines()[0] if mapper.class_.__doc__ else "" for mapper in EntityBase.registry.mappers}
    tables_by_domain: dict[str, list[Table]] = defaultdict(list)
    for table in tables:
        tables_by_domain[module_by_table_name.get(table.name, "other")].append(table)
    all_relationships = relationship_lines(tables)
    foreign_key_count = sum(1 for relationship in all_relationships if relationship[3])

    document = [
        "# 15 · Entity relationship diagram",
        "",
        "> Generated by `backend/scripts/generate_entity_relationship_diagram.py` from the SQLAlchemy entities (the same source as",
        "> the Azure SQL scripts in `database/azure_sql/`). Do not edit by hand — change the entity and regenerate.",
        "",
        f"**{len(tables)} tables · {foreign_key_count} foreign keys · {len(all_relationships) - foreign_key_count} ID references without a foreign key.**",
        "",
        "How to read it:",
        "",
        "- **Solid line** = foreign key enforced by the database. **Dotted line** = the child stores the parent's ID without a",
        "  foreign key, on purpose: audit and AI-usage history must survive deletes, alerts and incidents link across domains,",
        "  and SQL Server allows only one cascade path to a table.",
        "- `||` exactly one parent · `|o` zero or one parent (nullable column) · `o{` zero or more children.",
        "- Every table also has the columns shown in its domain diagram; times are UTC `DATETIME2(6)`, JSON is stored as `NVARCHAR(max)`.",
        "- In Azure SQL every table lives in the `keigan` schema (`keigan.application`, …).",
        "",
        "## Overview — how the tables connect",
        "",
        f"`application` is the parent of {sum(1 for relationship in all_relationships if relationship[0] == 'application')} tables through `application_id`.",
        "Those lines are left out here so the rest stays readable; each domain diagram below shows them.",
        "",
        "```mermaid",
        "erDiagram",
        *[render_relationship(*relationship) for relationship in all_relationships if relationship[0] != "application"],
        "```",
        "",
    ]
    for domain_module, domain_title in DOMAIN_TITLES.items():
        domain_tables = tables_by_domain.pop(domain_module, [])
        if domain_tables:
            document.extend(render_domain(domain_title, domain_module, domain_tables, tables, all_relationships, docstring_by_table_name))
    for domain_module, domain_tables in tables_by_domain.items():
        document.extend(render_domain(domain_module.replace("_", " ").title(), domain_module, domain_tables, tables, all_relationships, docstring_by_table_name))

    OUTPUT_PATH.write_text("\n".join(document) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT_PATH.name}: {len(tables)} tables, {len(all_relationships)} relationships ({foreign_key_count} foreign keys)")


def render_domain(title: str, module_name: str, domain_tables: list[Table], all_tables: list[Table], all_relationships: list[tuple[str, str, str, bool, bool]], docstrings: dict[str, str]) -> list[str]:
    domain_table_names = {table.name for table in domain_tables}
    domain_relationships = [relationship for relationship in all_relationships if relationship[1] in domain_table_names or (relationship[0] in domain_table_names and relationship[1] in domain_table_names)]
    referenced_outside = sorted({relationship[0] for relationship in domain_relationships if relationship[0] not in domain_table_names})
    table_by_name = {table.name: table for table in all_tables}
    lines = [f"## {title}", "", f"Entity module: `backend/keigan/entities/{module_name}.py`", ""]
    described_tables = [(table.name, docstrings.get(table.name, "")) for table in domain_tables if docstrings.get(table.name)]
    if described_tables:
        lines.extend(["| Table | Purpose |", "|---|---|", *[f"| `{name}` | {purpose} |" for name, purpose in described_tables], ""])
    lines.extend(["```mermaid", "erDiagram"])
    for table in domain_tables:
        lines.extend(render_entity(table))
    for outside_table_name in referenced_outside:
        outside_table = table_by_name[outside_table_name]
        primary_key_column = outside_table.primary_key.columns.values()[0]
        lines.extend([f"    {outside_table_name} {{", f"        {column_type_label(primary_key_column)} {primary_key_column.name} PK \"other domain\"", "    }"])
    lines.extend(render_relationship(*relationship) for relationship in domain_relationships)
    lines.extend(["```", ""])
    return lines


if __name__ == "__main__":
    main()
