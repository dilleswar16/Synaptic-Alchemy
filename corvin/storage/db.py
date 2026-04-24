"""
Database engine and session factory.

Reads connection settings from config/integrations/postgres.yaml (with env
overlay) and from METGUARD_DB_* environment variables as fallback.

Usage:
    from corvin.storage.db import get_session

    with get_session() as session:
        session.add(...)
        session.commit()
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from corvin.core.config_loader import get_env, load_config


def _build_url() -> str:
    """
    Build the Postgres DSN from config, with environment variable fallback.

    Config file takes the shape set in config/integrations/postgres.yaml.
    Each value can be a literal or a ${ENV_VAR} reference — both are
    resolved here so that the yaml stays as the single source of truth.
    """
    cfg = load_config("integrations/postgres", get_env())

    def _resolve(key: str, env_var: str, default: str = "") -> str:
        val = str(cfg.get(key, ""))
        if val.startswith("${") and val.endswith("}"):
            env_key = val[2:-1]
            return os.environ.get(env_key, default)
        return val or os.environ.get(env_var, default)

    host     = _resolve("host",     "METGUARD_DB_HOST",     "localhost")
    port     = _resolve("port",     "METGUARD_DB_PORT",     "5432")
    database = _resolve("database", "METGUARD_DB_NAME",     "corvin")
    user     = _resolve("user",     "METGUARD_DB_USER",     "corvin")
    password = _resolve("password", "METGUARD_DB_PASSWORD", "changeme")

    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}?sslmode=require"


_engine = None
_SessionLocal: sessionmaker | None = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(_build_url(), pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager that yields a SQLAlchemy Session and handles commit/rollback."""
    factory = get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
