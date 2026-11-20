"""ServiceNow access: live Table API (OAuth client credentials or basic) or the in-database simulator.

Both modes return records in ServiceNow's field names; helper functions normalise ``value`` / ``display_value`` shapes so
callers never care which mode produced a record.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import httpx

from keigan.config.settings import IntegrationMode, Settings
from keigan.exceptions.keigan_exceptions import IntegrationException
from keigan.integrations.secret_store import SecretStore
from keigan.integrations.simulation.servicenow_simulator import ServiceNowSimulator

SERVICENOW_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
SERVICENOW_STATE_NAMES = {"1": "new", "2": "in progress", "3": "on hold", "6": "resolved", "7": "closed", "8": "canceled"}


def read_field_value(record: dict[str, Any], field_name: str) -> str:
    field_value = record.get(field_name)
    if isinstance(field_value, dict):
        return str(field_value.get("value") or field_value.get("display_value") or "")
    return "" if field_value is None else str(field_value)


def read_field_display(record: dict[str, Any], field_name: str) -> str:
    field_value = record.get(field_name)
    if isinstance(field_value, dict):
        return str(field_value.get("display_value") or field_value.get("value") or "")
    return "" if field_value is None else str(field_value)


def normalized_state_name(record: dict[str, Any]) -> str:
    state_text = read_field_display(record, "state").strip().lower() or SERVICENOW_STATE_NAMES.get(read_field_value(record, "state"), "")
    return SERVICENOW_STATE_NAMES.get(state_text, state_text)


def parse_servicenow_timestamp(timestamp_text: str | None) -> datetime | None:
    if not timestamp_text:
        return None
    try:
        return datetime.strptime(timestamp_text[:19], SERVICENOW_TIMESTAMP_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


class ServiceNowClient:
    def __init__(self, settings: Settings, secret_store: SecretStore):
        self.settings = settings
        self.secret_store = secret_store
        self._simulator = ServiceNowSimulator()
        self._cached_access_token: tuple[str, float] | None = None

    @property
    def is_simulated(self) -> bool:
        return self.settings.servicenow_mode != IntegrationMode.LIVE

    def incident_url(self, incident_number: str | None) -> str | None:
        if not incident_number:
            return None
        base_url = self.settings.servicenow_instance_url.rstrip("/") or "https://metlife.service-now.com"
        return f"{base_url}/nav_to.do?uri=incident.do?sysparm_query=number={incident_number}"

    # ── Public operations ──────────────────────────────────────────────────────
    async def list_incidents(self, assignment_group_names: list[str], updated_since: datetime | None) -> list[dict[str, Any]]:
        if self.is_simulated:
            return await self._simulator.list_incidents(assignment_group_names, updated_since)
        query_parts = [f"assignment_group.nameIN{','.join(assignment_group_names)}"]
        if updated_since:
            query_parts.append(f"sys_updated_on>{updated_since.astimezone(UTC).strftime(SERVICENOW_TIMESTAMP_FORMAT)}")
        response_body = await self._send_request(
            "GET",
            "/api/now/table/incident",
            params={"sysparm_query": "^".join(query_parts) + "^ORDERBYsys_updated_on", "sysparm_display_value": "all", "sysparm_limit": "200"},
        )
        return list(response_body.get("result", []))

    async def create_incident(self, incident_fields: dict[str, Any]) -> dict[str, Any]:
        if self.is_simulated:
            return await self._simulator.create_incident(incident_fields)
        request_fields = {key: value for key, value in incident_fields.items() if key != "opened_at"}
        response_body = await self._send_request("POST", "/api/now/table/incident", json_body=request_fields, params={"sysparm_display_value": "all"})
        return dict(response_body.get("result", {}))

    async def update_incident(self, system_identifier: str, changed_fields: dict[str, Any]) -> dict[str, Any] | None:
        if self.is_simulated:
            return await self._simulator.update_incident(system_identifier, changed_fields)
        response_body = await self._send_request("PATCH", f"/api/now/table/incident/{system_identifier}", json_body=changed_fields)
        return dict(response_body.get("result", {}))

    # ── Live transport ─────────────────────────────────────────────────────────
    async def _authorization(self) -> tuple[dict[str, str], tuple[str, str] | None]:
        credential_value = await self.secret_store.get_secret(self.settings.servicenow_credential_secret_name)
        if self.settings.servicenow_auth_method == "basic":
            return {}, (self.settings.servicenow_username, credential_value)
        if self._cached_access_token and self._cached_access_token[1] > time.monotonic() + 60:
            return {"Authorization": f"Bearer {self._cached_access_token[0]}"}, None
        async with httpx.AsyncClient(timeout=30) as http_client:
            token_response = await http_client.post(
                f"{self.settings.servicenow_instance_url.rstrip('/')}/oauth_token.do",
                data={"grant_type": "client_credentials", "client_id": self.settings.servicenow_client_id, "client_secret": credential_value},
            )
        if token_response.status_code >= 400:
            raise IntegrationException(f"ServiceNow rejected the OAuth client credentials ({token_response.status_code}).")
        token_body = token_response.json()
        self._cached_access_token = (token_body["access_token"], time.monotonic() + float(token_body.get("expires_in", 1800)))
        return {"Authorization": f"Bearer {token_body['access_token']}"}, None

    async def _send_request(self, method: str, path: str, params: dict[str, str] | None = None, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.settings.servicenow_instance_url:
            raise IntegrationException("SERVICENOW_INSTANCE_URL is not configured.")
        headers, basic_authentication = await self._authorization()
        headers["Accept"] = "application/json"
        async with httpx.AsyncClient(timeout=45, auth=basic_authentication) as http_client:
            response = await http_client.request(method, f"{self.settings.servicenow_instance_url.rstrip('/')}{path}", params=params, json=json_body, headers=headers)
        if response.status_code >= 400:
            raise IntegrationException(f"ServiceNow returned {response.status_code}: {response.text[:300]}")
        return response.json() if response.content else {}
