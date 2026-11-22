"""Runs conformance scenarios one after another against one gateway and collects the report (spec 23, 4.6.6). The live script and the offline tests of the report both use it."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from keigan.ai.llm_gateway import ModelTier
from keigan.config.settings import get_settings
from keigan.services.ask_keigan_conformance_checks import ObservedRun
from keigan.services.ask_keigan_conformance_report import ConformanceReport, observe_capabilities, unrunnable_scenario_report
from keigan.services.ask_keigan_conformance_runner import run_scenario
from keigan.services.ask_keigan_conformance_scenarios import Scenario, ScenarioMode
from keigan.services.ask_keigan_prepared_run import AgentGateway

logger = logging.getLogger(__name__)


async def run_suite(gateway: AgentGateway, mode: ScenarioMode, scenarios: Sequence[Scenario]) -> ConformanceReport:
    """One report for ``scenarios`` run in ``mode`` with the model behind ``gateway``. A scenario that cannot be set up is a failed scenario, not the end of the run."""
    report = ConformanceReport(
        provider_name=get_settings().llm_provider.value, model_name=gateway.model_name_for(ModelTier.DEEP),
        configured_capabilities=gateway.agent_capabilities(ModelTier.DEEP).model_dump(mode="json"),
    )
    observed_runs: list[ObservedRun] = []
    for scenario in scenarios:
        try:
            scenario_report, observed = await run_scenario(scenario, lambda _scenario: gateway, mode)
        except Exception as problem:  # noqa: BLE001 — one scenario that cannot be set up must not hide the results of the others
            logger.exception("Conformance scenario %s could not be run", scenario.id)
            report.scenarios.append(unrunnable_scenario_report(scenario.id, scenario.title, mode.value, f"{type(problem).__name__}: {problem}"))
            continue
        report.scenarios.append(scenario_report)
        observed_runs.append(observed)
    report.observations = observe_capabilities(observed_runs)
    if observed_runs:  # what the runs recorded (the mock planner is "mock", whatever model name is configured)
        report.tool_calling_mode, report.model_name = observed_runs[0].tool_calling_mode, observed_runs[0].model_name
    return report
