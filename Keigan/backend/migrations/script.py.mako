"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import keigan.entities.base_entity
from keigan.config.settings import get_settings
${imports if imports else ""}
# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
# Autogenerate against SQLite writes schema=None: change it to schema=SCHEMA in every operation, and prefix
# foreign key targets with SCHEMA_PREFIX, e.g. [f'{SCHEMA_PREFIX}application.application_id'].
SCHEMA = get_settings().database_schema_or_none
SCHEMA_PREFIX = f"{SCHEMA}." if SCHEMA else ""

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
