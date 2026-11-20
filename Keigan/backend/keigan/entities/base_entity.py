"""Entity base class, shared column types and audit mixin (the JPA ``@MappedSuperclass`` equivalent).

Portable across SQLite (local), PostgreSQL and Azure SQL (SQL Server):
- text columns render as NVARCHAR on SQL Server (Japanese and other non-Latin text must survive);
- timestamps are always UTC: DATETIMEOFFSET-free DATETIME2 on SQL Server, timezone-aware elsewhere;
- tables live in ``DATABASE_SCHEMA`` (for example ``keigan``) when set; SQLite ignores schemas.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, MetaData, String, Text, TypeDecorator
from sqlalchemy.dialects import mssql
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from keigan.config.settings import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def new_identifier() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


@compiles(String, "mssql")
def _compile_string_as_unicode(string_type: String, compiler: Any, **compile_options: Any) -> str:
    return f"NVARCHAR({string_type.length})" if string_type.length else "NVARCHAR(max)"


@compiles(Text, "mssql")
def _compile_text_as_unicode(text_type: Text, compiler: Any, **compile_options: Any) -> str:
    return "NVARCHAR(max)"


class UtcDateTime(TypeDecorator[datetime]):
    """Stores timestamps in UTC and always returns timezone-aware values.

    SQL Server stores naive UTC in DATETIME2(6) (portable across ODBC drivers); other databases keep the time zone."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "mssql":
            return dialect.type_descriptor(mssql.DATETIME2(precision=6))
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        utc_value = (value.replace(tzinfo=UTC) if value.tzinfo is None else value).astimezone(UTC)
        return utc_value.replace(tzinfo=None) if dialect.name == "mssql" else utc_value

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class EntityBase(DeclarativeBase):
    metadata = MetaData(schema=get_settings().database_schema_or_none, naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        datetime: UtcDateTime,
        dict[str, Any]: JSON,
        list[Any]: JSON,
        list[str]: JSON,
    }

    def to_dictionary(self) -> dict[str, Any]:
        return {column.key: getattr(self, column.key) for column in self.__mapper__.column_attrs}


def identifier_column(**column_options: Any) -> Mapped[str]:
    """Primary key column holding a UUID string generated in Python."""
    return mapped_column(String(36), primary_key=True, default=new_identifier, **column_options)


class AuditColumnsMixin:
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now, nullable=False)
    created_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))
    updated_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))
