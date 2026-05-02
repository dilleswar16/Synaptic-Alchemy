"""H-6 regression: corvin.storage.db._build_pool_kwargs honors the
pool settings declared in config/integrations/postgres.yaml instead of
silently dropping them."""

from __future__ import annotations

import corvin.storage.db as db


def test_build_pool_kwargs_reads_yaml_values(monkeypatch):
    fake_cfg = {
        "host": "h",
        "port": 5432,
        "database": "d",
        "user": "u",
        "password": "p",
        "pool_size": 7,
        "max_overflow": 13,
        "pool_timeout_seconds": 45,
    }
    monkeypatch.setattr(db, "load_config", lambda *a, **kw: fake_cfg)

    kwargs = db._build_pool_kwargs()

    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_size"] == 7
    assert kwargs["max_overflow"] == 13
    assert kwargs["pool_timeout"] == 45


def test_build_pool_kwargs_falls_back_to_defaults_on_missing_keys(monkeypatch):
    monkeypatch.setattr(db, "load_config", lambda *a, **kw: {})
    kwargs = db._build_pool_kwargs()
    assert kwargs == {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
        "pool_timeout": 30,
    }


def test_build_pool_kwargs_coerces_string_values(monkeypatch):
    monkeypatch.setattr(
        db,
        "load_config",
        lambda *a, **kw: {"pool_size": "3", "max_overflow": "7", "pool_timeout_seconds": "20"},
    )
    kwargs = db._build_pool_kwargs()
    assert kwargs["pool_size"] == 3
    assert kwargs["max_overflow"] == 7
    assert kwargs["pool_timeout"] == 20


def test_build_pool_kwargs_defaults_on_invalid_values(monkeypatch):
    monkeypatch.setattr(
        db,
        "load_config",
        lambda *a, **kw: {"pool_size": "not-an-int", "max_overflow": None, "pool_timeout_seconds": "x"},
    )
    kwargs = db._build_pool_kwargs()
    assert kwargs["pool_size"] == 5
    assert kwargs["max_overflow"] == 10
    assert kwargs["pool_timeout"] == 30
