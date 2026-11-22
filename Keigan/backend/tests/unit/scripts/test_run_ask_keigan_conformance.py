"""scripts/run_ask_keigan_conformance.py: the live conformance script's arguments and the environment it forces (spec 23, 4.6.6). The script itself was never run against a real model."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from support import scripts_path  # noqa: F401  (puts backend/scripts on sys.path)

import run_ask_keigan_conformance as script  # noqa: E402  (import after the path helper)


def test_the_script_refuses_to_run_without_the_flag_that_says_the_provider_comes_from_the_environment() -> None:
    with pytest.raises(SystemExit):
        script._parse_arguments([])
    options = script._parse_arguments(["--provider-from-env", "--scenario", "C3", "--report", "out.json"])
    assert options.scenario == "C3" and options.report == Path("out.json")
    assert script._parse_arguments(["--provider-from-env"]).report == script.DEFAULT_REPORT_PATH


def test_the_scripts_default_report_path_is_the_one_the_administration_page_reads() -> None:
    from keigan.config.settings import Settings

    assert script.DEFAULT_REPORT_PATH == Settings.model_fields["ask_keigan_conformance_report_path"].default


def test_the_environment_it_forces_is_a_throw_away_database_with_simulated_sources_and_leaves_the_model_settings_alone(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(os, "environ", {"LLM_PROVIDER": "azure_openai", "LLM_API_KEY": "k", "DATABASE_URL": "sqlserver://production"})
    script._configure_environment_for_conformance_run(tmp_path)
    assert os.environ["DATABASE_URL"] == f"sqlite+aiosqlite:///{(tmp_path / 'conformance.db').as_posix()}" and os.environ["DATA_DIRECTORY"].startswith(str(tmp_path))
    assert {os.environ[name] for name in ("TELEMETRY_MODE", "SERVICENOW_MODE", "TEAMS_MODE", "EMAIL_MODE")} == {"simulated"}
    assert os.environ["LLM_PROVIDER"] == "azure_openai" and os.environ["LLM_API_KEY"] == "k"
