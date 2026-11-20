"""Database engine, session factory and the generic service provider used for dependency injection."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any, TypeVar

from fastapi import Depends
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from keigan.config.settings import get_settings

ServiceType = TypeVar("ServiceType")


@lru_cache
def get_database_engine() -> AsyncEngine:
    settings = get_settings()
    engine_options: dict[str, Any] = {"echo": settings.database_echo_statements, "pool_pre_ping": True}
    if settings.uses_sqlite:
        engine_options["connect_args"] = {"timeout": 30}
    else:
        engine_options["pool_size"] = settings.database_pool_size
        engine_options["max_overflow"] = settings.database_pool_size
        engine_options["pool_recycle"] = 1800  # Azure SQL and PostgreSQL gateways drop idle connections
    database_engine = create_async_engine(settings.database_url, **engine_options)

    if settings.uses_sql_server and settings.database_authentication == "managed_identity":
        _use_entra_token_for_sql_server(database_engine, settings)

    if settings.uses_sqlite:

        @event.listens_for(database_engine.sync_engine, "connect")
        def configure_sqlite_connection(database_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = database_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    return database_engine


SQL_SERVER_ACCESS_TOKEN_ATTRIBUTE = 1256  # SQL_COPT_SS_ACCESS_TOKEN (ODBC Driver 17/18)
AZURE_SQL_SCOPE = "https://database.windows.net/.default"


def _use_entra_token_for_sql_server(database_engine: AsyncEngine, settings: Any) -> None:
    """Authenticate to Azure SQL with Keigan's own Entra identity (no password): a fresh access token per new connection.

    DATABASE_URL then carries no credentials, e.g.
    mssql+aioodbc://@<server>.database.windows.net:1433/keigan?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes"""
    import struct

    from azure.identity import AzureCliCredential, ManagedIdentityCredential, WorkloadIdentityCredential

    identity_mode = str(settings.azure_identity_mode)
    if identity_mode == "workload_identity":
        credential: Any = WorkloadIdentityCredential(client_id=settings.azure_client_id or None, tenant_id=settings.azure_tenant_id or None)
    elif identity_mode == "azure_cli":
        credential = AzureCliCredential()
    else:
        credential = ManagedIdentityCredential(client_id=settings.azure_client_id or None)

    @event.listens_for(database_engine.sync_engine, "do_connect")
    def provide_access_token(_dialect, _connection_record, _connection_arguments, connection_parameters) -> None:  # type: ignore[no-untyped-def]
        token_bytes = credential.get_token(AZURE_SQL_SCOPE).token.encode("utf-16-le")
        connection_parameters["attrs_before"] = {SQL_SERVER_ACCESS_TOKEN_ATTRIBUTE: struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)}


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_database_engine(), expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def open_session() -> AsyncIterator[AsyncSession]:
    """Session for workers and scripts. Commits on success, rolls back on error."""
    session = get_session_factory()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_database_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, committed when the endpoint returns normally."""
    async with open_session() as session:
        yield session


# scope="function" commits before the response is sent. FastAPI's default ("request") commits afterwards, so a client could
# read stale data right after a successful write, and a failed commit would already have been reported as a success.
DatabaseSession = Depends(get_database_session, scope="function")


def provide(service_class: Callable[[AsyncSession], ServiceType]) -> Callable[..., ServiceType]:
    """Build a FastAPI dependency that constructs ``service_class(session)`` for the current request.

    Usage in a controller::

        investigation_service: InvestigationService = Depends(provide(InvestigationService))
    """

    def construct_service(session: AsyncSession = DatabaseSession) -> ServiceType:
        return service_class(session)

    construct_service.__name__ = f"provide_{getattr(service_class, '__name__', 'service')}"
    return construct_service


async def create_database_schema() -> None:
    """Create all tables (local development and first boot). Production uses migrations (Phase 6)."""
    from keigan.entities import all_entities  # noqa: F401  (registers every entity with the metadata)
    from keigan.entities.base_entity import EntityBase

    async with get_database_engine().begin() as connection:
        await connection.run_sync(EntityBase.metadata.create_all)
