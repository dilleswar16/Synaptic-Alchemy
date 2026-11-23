"""investigation memory reference: which remembered incidents were given to an investigation's AI

Spec 34 (phase 4). One ordered row per remembered incident that was handed to the hypotheses as a hint, so the investigation page can say so and a later review can see exactly what the
AI was shown. Nothing is backfilled: an investigation that ran before this revision was given the older "recurring issues" text and has no rows.

Revision ID: f7c3e9a1b5d2
Revises: e6b2d8f4a0c3
Create Date: 2026-11-24 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from keigan.config.settings import get_settings

# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
SCHEMA = get_settings().database_schema_or_none
SCHEMA_PREFIX = f"{SCHEMA}." if SCHEMA else ""

revision: str = 'f7c3e9a1b5d2'
down_revision: str | None = 'e6b2d8f4a0c3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "investigation_memory_reference",
        sa.Column("investigation_id", sa.String(36), nullable=False),
        sa.Column("incident_memory_entry_id", sa.String(36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("investigation_id", "incident_memory_entry_id", name=op.f("pk_investigation_memory_reference")),
        sa.ForeignKeyConstraint(["investigation_id"], [f"{SCHEMA_PREFIX}investigation.investigation_id"], name=op.f("fk_investigation_memory_reference_investigation_id_investigation"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["incident_memory_entry_id"], [f"{SCHEMA_PREFIX}incident_memory_entry.incident_memory_entry_id"],
            name=op.f("fk_investigation_memory_reference_incident_memory_entry_id_incident_memory_entry"),
        ),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_investigation_memory_reference_incident_memory_entry_id"), "investigation_memory_reference", ["incident_memory_entry_id"], unique=False, schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("investigation_memory_reference", schema=SCHEMA)
