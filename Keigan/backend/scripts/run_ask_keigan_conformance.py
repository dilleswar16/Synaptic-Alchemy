"""Runs the Ask Keigan conformance scenarios against the AI model configured in ``backend/.env`` and writes a JSON report (spec 23, 4.6.6 and 12.4, check M6).

Usage (from backend/):  .\\.venv\\Scripts\\python.exe scripts\\run_ask_keigan_conformance.py --provider-from-env --report conformance_report.json [--scenario C3]

THIS COSTS MONEY: every scenario is a real conversation with the configured model (a few model calls each), so it is run on demand, never by the test suite. The model comes from
the environment (``LLM_PROVIDER``, ``LLM_API_KEY``, ``LLM_BASE_URL``, ``LLM_DEEP_MODEL``, ``LLM_MODEL_CAPABILITIES_JSON`` ...); everything else is forced to be harmless: a throw-away SQLite
database seeded with the demo data, simulated telemetry, ServiceNow, Teams and email. Nothing is read from or written to a real environment. With ``LLM_PROVIDER=mock`` it runs
the offline planner instead (a quick check that the script itself works).

The report has, per scenario, pass or fail with the reasons, the tools called with their arguments, tokens, latency and the answer, and what the run showed of the model's
capabilities (parallel tool calls, streamed text, token usage reported while streaming). Compare them with ``configuredCapabilities`` and copy what differs into
``LLM_MODEL_CAPABILITIES_JSON``. The exit code is 0 when every scenario passed and 1 otherwise.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_PATH = Path("ask_keigan_conformance_report.json")


def _configure_environment_for_conformance_run(temporary_directory: Path) -> None:
    """Set before any Keigan import (settings and the engine are cached on first use). The model settings are deliberately left alone: they are what is being tested."""
    os.environ.update(
        {
            "DATABASE_URL": f"sqlite+aiosqlite:///{(temporary_directory / 'conformance.db').as_posix()}",
            "DATA_DIRECTORY": str(temporary_directory / "data"),
            "ENVIRONMENT": "test",
            "AUTH_MODE": "local",
            "TELEMETRY_MODE": "simulated",
            "SERVICENOW_MODE": "simulated",
            "TEAMS_MODE": "simulated",
            "EMAIL_MODE": "simulated",
            "RUN_WORKERS_IN_PROCESS": "false",
            "AUTO_CREATE_SCHEMA": "false",
            "LOG_LEVEL": "WARNING",
        }
    )
    sys.path.insert(0, str(BACKEND_DIRECTORY))


def _parse_arguments(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Ask Keigan conformance scenarios against the configured AI model.")
    parser.add_argument("--provider-from-env", action="store_true", required=True, help="use the model configured in backend/.env and the environment (required: a real run costs money)")
    parser.add_argument("--scenario", help="run only this scenario, for example C3")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH, help=f"where to write the JSON report (default {DEFAULT_REPORT_PATH})")
    return parser.parse_args(arguments)


async def _run(scenario_id: str | None, report_path: Path) -> int:
    from keigan.ai.llm_gateway import ModelTier
    from keigan.config import application_context
    from keigan.config.database_config import get_database_engine
    from keigan.seed_main import run_seed
    from keigan.services.ask_keigan_conformance_report import write_report
    from keigan.services.ask_keigan_conformance_scenarios import ScenarioMode, scenarios_for
    from keigan.services.ask_keigan_conformance_suite import run_suite

    scenarios = scenarios_for(ScenarioMode.LIVE, scenario_id)
    if not scenarios:
        print(f"No live scenario matches {scenario_id!r}.", file=sys.stderr)
        return 2
    gateway = application_context.llm_gateway()
    try:
        print(f"Seeding the throw-away demo database, then running {len(scenarios)} scenario(s) against {gateway.provider_name} / {gateway.model_name_for(ModelTier.DEEP)} ...")
        await run_seed()
        report = await run_suite(gateway, ScenarioMode.LIVE, scenarios)
        write_report(report, report_path)
    finally:
        await gateway.aclose()
        await get_database_engine().dispose()
    for scenario in report.scenarios:
        print(f"  {scenario.scenario_id} {'PASS' if scenario.passed else 'FAIL'}  {scenario.title}" + "".join(f"\n      - {failure}" for failure in scenario.failures))
    print(f"{sum(scenario.passed for scenario in report.scenarios)} of {len(report.scenarios)} passed. Report: {report_path}")
    return 0 if report.passed else 1


def main(arguments: list[str] | None = None) -> int:
    options = _parse_arguments(sys.argv[1:] if arguments is None else arguments)
    with tempfile.TemporaryDirectory(prefix="keigan-conformance-") as temporary_name:
        _configure_environment_for_conformance_run(Path(temporary_name))
        return asyncio.run(_run(options.scenario, options.report))


if __name__ == "__main__":
    raise SystemExit(main())
