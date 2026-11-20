"""Controls the simulated world (local / test only): scenario windows, slow conditions and simulated incidents.

``trigger_scenario`` reproduces a real incident end to end: telemetry starts failing, a ServiceNow incident appears
for the application's assignment group (picked up by the normal poller) and alerts are fired into alert intake.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config import application_context
from keigan.config.settings import get_settings
from keigan.entities.application_entities import Application, MonitoredService
from keigan.entities.incident_entities import ServiceNowAssignmentGroup
from keigan.entities.platform_entities import PlatformSetting
from keigan.exceptions.keigan_exceptions import BusinessValidationException, ForbiddenException, NotFoundException
from keigan.integrations.simulation.servicenow_simulator import ServiceNowSimulator
from keigan.integrations.simulation.simulation_scenarios import SCENARIO_CATALOG
from keigan.integrations.simulation.telemetry_simulator import SIMULATION_SETTING_KEY, ScenarioWindow
from keigan.workers.job_queue import JobQueue


class SimulationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def ensure_simulation_allowed() -> None:
        if not get_settings().is_local_environment and get_settings().environment != "test":
            raise ForbiddenException("Simulation is only available in local, dev and test environments.")

    async def read_configuration(self) -> dict[str, Any]:
        stored_setting = await self.session.get(PlatformSetting, SIMULATION_SETTING_KEY)
        return dict((stored_setting.setting_value_json if stored_setting else None) or {"scenario_windows": [], "conditions": []})

    async def write_configuration(self, configuration: dict[str, Any]) -> None:
        stored_setting = await self.session.get(PlatformSetting, SIMULATION_SETTING_KEY)
        if stored_setting is None:
            self.session.add(PlatformSetting(setting_key=SIMULATION_SETTING_KEY, setting_value_json=configuration, setting_description="Simulated telemetry scenarios"))
        else:
            stored_setting.setting_value_json = configuration
        await self.session.flush()
        application_context.telemetry_simulator().invalidate()

    async def add_scenario_window(self, scenario_window: ScenarioWindow) -> None:
        configuration = await self.read_configuration()
        configuration.setdefault("scenario_windows", []).append(scenario_window.to_dictionary())
        configuration["scenario_windows"] = configuration["scenario_windows"][-60:]
        await self.write_configuration(configuration)

    async def add_condition(self, condition: dict[str, Any]) -> None:
        configuration = await self.read_configuration()
        configuration.setdefault("conditions", []).append(condition)
        await self.write_configuration(configuration)

    async def select_services_for_scenario(self, application_id: str, scenario_key: str) -> tuple[list[MonitoredService], list[MonitoredService]]:
        scenario = SCENARIO_CATALOG[scenario_key]
        services = list(
            (await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id == application_id, MonitoredService.is_monitoring_enabled.is_(True)))).all()
        )
        primary_services = [service for service in services if service.service_type in scenario.primary_service_types][:1]
        dependency_services = [service for service in services if service.service_type in scenario.dependency_service_types][:1]
        return primary_services, dependency_services

    async def trigger_scenario(self, application_id: str, scenario_key: str, duration_minutes: int = 60, create_servicenow_incident: bool = True, fire_alerts: bool = True) -> dict[str, Any]:
        self.ensure_simulation_allowed()
        if scenario_key not in SCENARIO_CATALOG:
            raise NotFoundException(f"Unknown scenario {scenario_key}. Available: {', '.join(SCENARIO_CATALOG)}")
        application = await self.session.get(Application, application_id)
        if application is None:
            raise NotFoundException("The application was not found.")
        scenario = SCENARIO_CATALOG[scenario_key]
        primary_services, dependency_services = await self.select_services_for_scenario(application_id, scenario_key)
        if not primary_services:
            raise BusinessValidationException(f"{application.application_name} has no service of type {', '.join(scenario.primary_service_types)} for this scenario.")

        started_at = datetime.now(UTC) - timedelta(minutes=12)
        scenario_window = ScenarioWindow(
            scenario_key=scenario_key,
            application_id=application_id,
            primary_service_ids=[service.service_id for service in primary_services],
            dependency_service_ids=[service.service_id for service in dependency_services],
            started_at=started_at,
            ended_at=started_at + timedelta(minutes=duration_minutes),
        )
        servicenow_incident_number = None
        if create_servicenow_incident:
            assignment_group = await self.session.scalar(
                select(ServiceNowAssignmentGroup).where(ServiceNowAssignmentGroup.application_id == application_id).limit(1)
            )
            if assignment_group is not None:
                servicenow_record = await ServiceNowSimulator().create_incident(
                    {
                        "short_description": scenario.servicenow_short_description.format(application_name=application.application_name, service_name=primary_services[0].service_name),
                        "description": scenario.servicenow_description.format(started_at_local=started_at.strftime("%H:%M UTC")),
                        "priority": scenario.servicenow_priority,
                        "impact": "2",
                        "urgency": "1" if scenario.servicenow_priority in ("1", "2") else "2",
                        "assignment_group": assignment_group.group_name,
                        "cmdb_ci": primary_services[0].service_name,
                        "opened_at": started_at + timedelta(minutes=random.randint(4, 9)),
                    }
                )
                servicenow_incident_number = servicenow_record["number"]
        scenario_window.external_incident_number = servicenow_incident_number
        await self.add_scenario_window(scenario_window)

        if fire_alerts and scenario.alert_rule_names:
            await JobQueue(self.session).enqueue(
                "simulate_alerts_for_scenario",
                {"application_id": application_id, "scenario_window": scenario_window.to_dictionary()},
                deduplication_key=f"simulate-alerts:{application_id}:{started_at.isoformat()}",
            )
        return {
            "scenarioKey": scenario_key,
            "title": scenario.title,
            "primaryServices": [service.service_name for service in primary_services],
            "dependencyServices": [service.service_name for service in dependency_services],
            "startedAt": started_at.isoformat(),
            "endsAt": scenario_window.ended_at.isoformat() if scenario_window.ended_at else None,
            "servicenowIncidentNumber": servicenow_incident_number,
        }

    @staticmethod
    def list_scenarios() -> list[dict[str, str]]:
        return [
            {"scenarioKey": scenario.scenario_key, "title": scenario.title, "category": scenario.incident_category, "serviceTypes": ", ".join(scenario.primary_service_types)}
            for scenario in SCENARIO_CATALOG.values()
        ]
