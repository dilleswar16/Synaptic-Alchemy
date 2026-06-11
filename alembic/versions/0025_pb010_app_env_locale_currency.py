"""PB-010: add currency_code, locale, tts_voice_name to application_environments

Revision ID: 0025_pb010_app_env_locale_currency
Revises: 0024
Create Date: 2026-06-11
"""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "0025_pb010_app_env_locale_currency"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("application_environments", sa.Column("currency_code", sa.String(3), nullable=True, server_default=None))
    op.add_column("application_environments", sa.Column("locale", sa.String(20), nullable=True, server_default=None))
    op.add_column("application_environments", sa.Column("tts_voice_name", sa.String(100), nullable=True, server_default=None))


def downgrade() -> None:
    op.drop_column("application_environments", "tts_voice_name")
    op.drop_column("application_environments", "locale")
    op.drop_column("application_environments", "currency_code")
