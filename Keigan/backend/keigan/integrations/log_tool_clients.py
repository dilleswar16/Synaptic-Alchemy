"""Readers for non-Azure log tools: Elastic, Splunk, Datadog (live) and placeholders (SolarWinds, IBM Z, vendor APIs).

Every reader implements :class:`LogToolClient`: ``search(query, query_scope)`` and ``test_connection()``.
Placeholder readers keep their configuration in Keigan and answer clearly that reading is not available yet.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from keigan.entities.application_entities import LogToolConnection
from keigan.exceptions.keigan_exceptions import IntegrationException, ReaderNotAvailableException
from keigan.integrations.secret_store import SecretStore
from keigan.integrations.telemetry_gateway import ConnectionTestResult, LogQueryResult, TelemetryQuery

READABLE_TOOL_TYPES = frozenset({"elastic", "splunk", "datadog"})
PLACEHOLDER_TOOL_TYPES = frozenset({"solarwinds", "ibm_z_log_analytics", "vendor_api", "other"})


def _flatten_document(document: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened_fields: dict[str, Any] = {}
    for field_name, field_value in document.items():
        flattened_name = f"{prefix}{field_name}"
        if isinstance(field_value, dict):
            flattened_fields.update(_flatten_document(field_value, f"{flattened_name}."))
        else:
            flattened_fields[flattened_name] = field_value
    return flattened_fields


class LogToolClient(ABC):
    def __init__(self, connection: LogToolConnection, credential_value: str | None):
        self.connection = connection
        self.credential_value = credential_value
        self.configuration: dict[str, Any] = connection.connection_configuration_json or {}

    @abstractmethod
    async def search(self, telemetry_query: TelemetryQuery, query_scope: dict[str, Any]) -> LogQueryResult: ...

    @abstractmethod
    async def test_connection(self) -> ConnectionTestResult: ...

    def _endpoint(self) -> str:
        if not self.connection.endpoint_url or not self.connection.endpoint_url.startswith("https://"):
            raise IntegrationException(f"{self.connection.connection_name} needs an HTTPS endpoint URL.")
        return self.connection.endpoint_url.rstrip("/")


class ElasticClient(LogToolClient):
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.connection.authentication_method == "api_key" and self.credential_value:
            headers["Authorization"] = f"ApiKey {self.credential_value}"
        elif self.connection.authentication_method == "bearer_token" and self.credential_value:
            headers["Authorization"] = f"Bearer {self.credential_value}"
        return headers

    def _basic_authentication(self) -> tuple[str, str] | None:
        if self.connection.authentication_method == "basic" and self.credential_value and ":" in self.credential_value:
            username, password = self.credential_value.split(":", 1)
            return username, password
        return None

    async def search(self, telemetry_query: TelemetryQuery, query_scope: dict[str, Any]) -> LogQueryResult:
        index_pattern = query_scope.get("index_pattern") or self.configuration.get("index_pattern") or "logs-*"
        query_body = json.loads(telemetry_query.query_text) if telemetry_query.query_text.strip().startswith("{") else {
            "query": {"query_string": {"query": telemetry_query.query_text}}
        }
        query_body.setdefault("size", min(telemetry_query.maximum_rows, 500))
        async with httpx.AsyncClient(timeout=60, auth=self._basic_authentication()) as http_client:
            response = await http_client.post(f"{self._endpoint()}/{index_pattern}/_search", headers=self._headers(), json=query_body)
        if response.status_code >= 400:
            raise IntegrationException(f"Elastic returned {response.status_code}: {response.text[:300]}")
        response_body = response.json()
        rows = [_flatten_document(hit.get("_source", {})) for hit in response_body.get("hits", {}).get("hits", [])]
        for aggregation_name, aggregation_body in (response_body.get("aggregations") or {}).items():
            for bucket in aggregation_body.get("buckets", []):
                rows.append({"aggregation": aggregation_name, "key": bucket.get("key_as_string", bucket.get("key")), "count_": bucket.get("doc_count")})
        column_names = sorted({column_name for row in rows for column_name in row})
        return LogQueryResult(column_names, rows, json.dumps(query_body), "elastic_dsl")

    async def test_connection(self) -> ConnectionTestResult:
        index_pattern = self.configuration.get("index_pattern") or "logs-*"
        time_field = self.configuration.get("time_field") or "@timestamp"
        try:
            async with httpx.AsyncClient(timeout=20, auth=self._basic_authentication()) as http_client:
                response = await http_client.post(
                    f"{self._endpoint()}/{index_pattern}/_search",
                    headers=self._headers(),
                    json={"size": 1, "sort": [{time_field: "desc"}], "_source": [time_field]},
                )
        except httpx.HTTPError as connection_error:
            return ConnectionTestResult(False, f"Could not reach Elastic: {type(connection_error).__name__}")
        if response.status_code >= 400:
            return ConnectionTestResult(False, f"Elastic returned {response.status_code}.")
        hits = response.json().get("hits", {}).get("hits", [])
        newest_timestamp_text = (_flatten_document(hits[0].get("_source", {})).get(time_field) if hits else None)
        newest_timestamp = datetime.fromisoformat(str(newest_timestamp_text).replace("Z", "+00:00")) if newest_timestamp_text else None
        return ConnectionTestResult(True, "Connected to Elastic.", newest_log_timestamp=newest_timestamp)


class SplunkClient(LogToolClient):
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.credential_value}"} if self.credential_value else {}

    async def search(self, telemetry_query: TelemetryQuery, query_scope: dict[str, Any]) -> LogQueryResult:
        async with httpx.AsyncClient(timeout=90) as http_client:
            response = await http_client.post(
                f"{self._endpoint()}/services/search/jobs/export",
                headers=self._headers(),
                data={"search": telemetry_query.query_text, "output_mode": "json", "count": str(telemetry_query.maximum_rows)},
            )
        if response.status_code >= 400:
            raise IntegrationException(f"Splunk returned {response.status_code}: {response.text[:300]}")
        rows: list[dict[str, Any]] = []
        for response_line in response.text.splitlines():
            if not response_line.strip():
                continue
            try:
                result_entry = json.loads(response_line).get("result")
            except json.JSONDecodeError:
                continue
            if result_entry:
                rows.append(result_entry)
        column_names = sorted({column_name for row in rows for column_name in row})
        return LogQueryResult(column_names, rows[: telemetry_query.maximum_rows], telemetry_query.query_text, "spl")

    async def test_connection(self) -> ConnectionTestResult:
        try:
            async with httpx.AsyncClient(timeout=20) as http_client:
                response = await http_client.get(f"{self._endpoint()}/services/server/info?output_mode=json", headers=self._headers())
        except httpx.HTTPError as connection_error:
            return ConnectionTestResult(False, f"Could not reach Splunk: {type(connection_error).__name__}")
        return ConnectionTestResult(response.status_code < 400, "Connected to Splunk." if response.status_code < 400 else f"Splunk returned {response.status_code}.")


class DatadogClient(LogToolClient):
    def _base_url(self) -> str:
        return f"https://api.{self.configuration.get('site', 'datadoghq.com')}"

    def _headers(self) -> dict[str, str]:
        api_key, _, application_key = (self.credential_value or "").partition(":")
        return {"DD-API-KEY": api_key, "DD-APPLICATION-KEY": application_key, "Content-Type": "application/json"}

    async def search(self, telemetry_query: TelemetryQuery, query_scope: dict[str, Any]) -> LogQueryResult:
        request_body = {
            "filter": {
                "query": telemetry_query.query_text,
                "from": telemetry_query.time_range_start.astimezone(UTC).isoformat(),
                "to": telemetry_query.time_range_end.astimezone(UTC).isoformat(),
            },
            "page": {"limit": min(telemetry_query.maximum_rows, 500)},
            "sort": "-timestamp",
        }
        async with httpx.AsyncClient(timeout=60) as http_client:
            response = await http_client.post(f"{self._base_url()}/api/v2/logs/events/search", headers=self._headers(), json=request_body)
        if response.status_code >= 400:
            raise IntegrationException(f"Datadog returned {response.status_code}: {response.text[:300]}")
        rows = [_flatten_document(log_event.get("attributes", {})) for log_event in response.json().get("data", [])]
        column_names = sorted({column_name for row in rows for column_name in row})
        return LogQueryResult(column_names, rows, telemetry_query.query_text, "datadog")

    async def test_connection(self) -> ConnectionTestResult:
        try:
            async with httpx.AsyncClient(timeout=20) as http_client:
                response = await http_client.get(f"{self._base_url()}/api/v1/validate", headers=self._headers())
        except httpx.HTTPError as connection_error:
            return ConnectionTestResult(False, f"Could not reach Datadog: {type(connection_error).__name__}")
        return ConnectionTestResult(response.status_code < 400, "Connected to Datadog." if response.status_code < 400 else f"Datadog returned {response.status_code}.")


class PlaceholderReader(LogToolClient):
    """Stores configuration so the picture is truthful, and says plainly that Keigan cannot read the tool yet."""

    async def search(self, telemetry_query: TelemetryQuery, query_scope: dict[str, Any]) -> LogQueryResult:
        raise ReaderNotAvailableException(f"Keigan cannot read {self.connection.tool_type} yet; its configuration is saved for when it can.")

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(False, "Reader in development — details saved.", details={"readerNotAvailable": True})


class LogToolClientFactory:
    def __init__(self, secret_store: SecretStore):
        self.secret_store = secret_store

    async def client_for(self, connection: LogToolConnection) -> LogToolClient:
        credential_value = await self.secret_store.get_secret_or_none(connection.credential_secret_name)
        client_class: type[LogToolClient] = {
            "elastic": ElasticClient,
            "splunk": SplunkClient,
            "datadog": DatadogClient,
        }.get(connection.tool_type, PlaceholderReader)
        return client_class(connection, credential_value)


def default_lookback_window(hours: int = 1) -> tuple[datetime, datetime]:
    end_time = datetime.now(UTC)
    return end_time - timedelta(hours=hours), end_time
