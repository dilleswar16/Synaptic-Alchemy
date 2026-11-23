"""Action items as ServiceNow tasks (spec 29, 4.7; roadmap D1): builds the task from an item's snapshot, and reads task states back."""

from __future__ import annotations

import re

from keigan.config.settings import Settings
from keigan.entities.status_values import ActionItemPriority
from keigan.exceptions.keigan_exceptions import IntegrationException
from keigan.integrations.action_item_tracker import ActionItemSnapshot, ExternalTaskReference, ExternalTaskState
from keigan.integrations.servicenow_client import ServiceNowClient
from keigan.services.action_item_external_rules import outcome_of_state
from keigan.utils.action_item_priority_map import parse_priority_map

SERVICENOW_SHORT_DESCRIPTION_MAXIMUM = 160  # the column's length in ServiceNow
_SERVICENOW_IDENTIFIER = re.compile(r"^[0-9a-f]{32}$")


class ServiceNowTaskTracker:
    system_name = "servicenow"

    def __init__(self, settings: Settings, client: ServiceNowClient):
        self.settings = settings
        self.client = client

    def _fields(self, item: ActionItemSnapshot) -> dict[str, str]:
        priorities = parse_priority_map(self.settings.action_items_servicenow_priorities)
        lines = [item.details.strip()] if item.details and item.details.strip() else []
        lines.append(f"Type: {item.action_type}")
        if item.incident_reference:
            lines.append(f"Follow-up of incident {item.incident_reference}")
        lines.append("Created by Keigan from an action item.")
        fields = {
            "short_description": item.title[:SERVICENOW_SHORT_DESCRIPTION_MAXIMUM], "description": "\n\n".join(lines), "priority": priorities[ActionItemPriority(item.priority)],
        }
        if item.due_on is not None:
            fields["due_date"] = f"{item.due_on.isoformat()} 00:00:00"
        return fields

    async def create_task(self, item: ActionItemSnapshot) -> ExternalTaskReference:
        table = self.settings.action_items_servicenow_table
        record = await self.client.create_task(table, self._fields(item))
        number, identifier = str(record.get("number") or ""), str(record.get("sys_id") or "")
        if not number or not identifier:
            raise IntegrationException("ServiceNow did not return the new task's number and id.")
        return ExternalTaskReference(number=number, record_identifier=identifier, url=self.client.task_url(table, number))

    async def read_task_states(self, record_identifiers: list[str]) -> dict[str, ExternalTaskState]:
        if not record_identifiers:
            return {}
        if any(not _SERVICENOW_IDENTIFIER.match(identifier) for identifier in record_identifiers):
            raise IntegrationException("A task identifier is not a ServiceNow id; nothing was asked.")
        records = await self.client.read_tasks(self.settings.action_items_servicenow_table, record_identifiers)
        return {
            str(record["sys_id"]): ExternalTaskState(status_text=str(record.get("state") or ""), outcome=outcome_of_state(str(record.get("state") or "")))
            for record in records if record.get("sys_id")
        }
