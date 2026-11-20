"""A tiny in-database stand-in for the ServiceNow incident table (``SERVICENOW_MODE=simulated``).

Records use ServiceNow's field names so ``servicenow_client`` maps live and simulated data identically.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from keigan.config.database_config import open_session
from keigan.entities.platform_entities import PlatformSetting

SERVICENOW_SIMULATION_SETTING_KEY = "simulation_servicenow_incidents"


def _servicenow_timestamp(timestamp: datetime) -> str:
    return timestamp.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


class ServiceNowSimulator:
    async def _load_incidents(self) -> list[dict[str, Any]]:
        async with open_session() as session:
            stored_setting = await session.get(PlatformSetting, SERVICENOW_SIMULATION_SETTING_KEY)
            return list(((stored_setting.setting_value_json if stored_setting else None) or {}).get("incidents", []))

    async def _save_incidents(self, incidents: list[dict[str, Any]]) -> None:
        async with open_session() as session:
            stored_setting = await session.get(PlatformSetting, SERVICENOW_SIMULATION_SETTING_KEY)
            if stored_setting is None:
                session.add(PlatformSetting(setting_key=SERVICENOW_SIMULATION_SETTING_KEY, setting_value_json={"incidents": incidents}, setting_description="Simulated ServiceNow incidents"))
            else:
                stored_setting.setting_value_json = {"incidents": incidents}

    async def list_incidents(self, assignment_group_names: list[str], updated_since: datetime | None) -> list[dict[str, Any]]:
        lowercase_group_names = {group_name.lower() for group_name in assignment_group_names}
        matching_incidents: list[dict[str, Any]] = []
        for incident_record in await self._load_incidents():
            group_name = (incident_record.get("assignment_group") or {}).get("display_value", "")
            if group_name.lower() not in lowercase_group_names:
                continue
            if updated_since and incident_record.get("sys_updated_on", "") <= _servicenow_timestamp(updated_since):
                continue
            matching_incidents.append(incident_record)
        return matching_incidents

    async def create_incident(self, incident_fields: dict[str, Any]) -> dict[str, Any]:
        incidents = await self._load_incidents()
        now = datetime.now(UTC)
        next_number = 4_100_000 + len(incidents) + 1
        incident_record = {
            "sys_id": uuid.uuid4().hex,
            "number": f"INC{next_number:07d}",
            "short_description": incident_fields.get("short_description", "Incident"),
            "description": incident_fields.get("description", ""),
            "priority": str(incident_fields.get("priority", "3")),
            "impact": str(incident_fields.get("impact", "2")),
            "urgency": str(incident_fields.get("urgency", "2")),
            "state": "New",
            "assignment_group": {"display_value": incident_fields.get("assignment_group", "")},
            "cmdb_ci": {"display_value": incident_fields.get("cmdb_ci", "")},
            "opened_at": _servicenow_timestamp(incident_fields.get("opened_at") or now),
            "sys_updated_on": _servicenow_timestamp(now),
            "caller_id": {"display_value": incident_fields.get("caller", "Service Desk")},
        }
        incidents.append(incident_record)
        await self._save_incidents(incidents)
        return incident_record

    async def update_incident(self, system_identifier: str, changed_fields: dict[str, Any]) -> dict[str, Any] | None:
        incidents = await self._load_incidents()
        for incident_record in incidents:
            if incident_record["sys_id"] == system_identifier:
                incident_record.update(changed_fields)
                incident_record["sys_updated_on"] = _servicenow_timestamp(datetime.now(UTC))
                await self._save_incidents(incidents)
                return incident_record
        return None
