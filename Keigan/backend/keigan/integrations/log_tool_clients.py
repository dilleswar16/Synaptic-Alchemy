"""Readers for non-Azure log tools: Elastic, Splunk, Datadog (live) and placeholders (SolarWinds, IBM Z, vendor APIs).

Every reader implements :class:`LogToolClient`: ``search(query, query_scope)`` and ``test_connection()``.
Placeholder readers keep their configuration in Keigan and answer clearly that reading is not available yet.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from keigan.entities.application_entities import LogToolConnection
from keigan.exceptions.keigan_exceptions import IntegrationException, ReaderNotAvailableException
from keigan.integrations.secret_store import SecretStore
from keigan.integrations.telemetry_gateway import ConnectionTestResult, LogQueryResult, TelemetryQuery
from keigan.utils.query_safety import QueryRejectedError, configured_splunk_index, validate_elastic_index_pattern, validate_elastic_query, validate_spl

logger = logging.getLogger(__name__)

READABLE_TOOL_TYPES = frozenset({"elastic", "splunk", "datadog"})
PLACEHOLDER_TOOL_TYPES = frozenset({"solarwinds", "ibm_z_log_analytics", "vendor_api", "other"})


def _failure_for_response(tool_name: str, response: httpx.Response) -> IntegrationException:
    """The reply body can name internal hosts and indices, so it goes to the log; the user gets the status code only."""
    logger.warning("%s returned %s: %s", tool_name, response.status_code, response.text[:500])
    return IntegrationException(f"{tool_name} returned an error ({response.status_code}). Check the connection settings, or ask your {tool_name} administrator.")


def _failure_for_transport(tool_name: str, error: Exception) -> IntegrationException:
    logger.warning("Could not read from %s: %s", tool_name, error)
    return IntegrationException(f"Keigan could not read from {tool_name}. Check that the connection endpoint is reachable.")


def _json_body(tool_name: str, response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as parse_error:
        logger.warning("%s sent a reply that is not JSON: %s", tool_name, response.text[:300])
        raise IntegrationException(f"{tool_name} sent a reply Keigan could not read. Check the connection endpoint.") from parse_error
    if not isinstance(body, dict):
        raise IntegrationException(f"{tool_name} sent a reply Keigan could not read. Check the connection endpoint.")
    return body


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

    def _index_pattern(self, query_scope: dict[str, Any]) -> str:
        """The index pattern goes into the URL path, so it is checked before it is used."""
        index_pattern = query_scope.get("index_pattern") or self.configuration.get("index_pattern") or "logs-*"
        try:
            return validate_elastic_index_pattern(index_pattern)
        except QueryRejectedError as rejection:
            logger.warning("Elastic index pattern refused for %s: %r", self.connection.connection_name, index_pattern)
            raise IntegrationException("The Elastic index pattern on this log source is not valid. Ask an application admin to correct it.") from rejection

    async def search(self, telemetry_query: TelemetryQuery, query_scope: dict[str, Any]) -> LogQueryResult:
        index_pattern = self._index_pattern(query_scope)
        raw_query = telemetry_query.query_text if telemetry_query.query_text.strip().startswith("{") else json.dumps({"query": {"query_string": {"query": telemetry_query.query_text}}})
        hardened_query = validate_elastic_query(
            raw_query, telemetry_query.time_range_start, telemetry_query.time_range_end, self.configuration.get("time_field") or "@timestamp"
        )
        query_body = json.loads(hardened_query.query_text)
        query_body["size"] = min(query_body["size"], telemetry_query.maximum_rows)
        try:
            async with httpx.AsyncClient(timeout=60, auth=self._basic_authentication()) as http_client:
                response = await http_client.post(f"{self._endpoint()}/{index_pattern}/_search", headers=self._headers(), json=query_body)
        except httpx.HTTPError as transport_error:
            raise _failure_for_transport("Elastic", transport_error) from transport_error
        if response.status_code >= 400:
            raise _failure_for_response("Elastic", response)
        response_body = _json_body("Elastic", response)
        rows = [_flatten_document(hit.get("_source", {})) for hit in response_body.get("hits", {}).get("hits", [])]
        for aggregation_name, aggregation_body in (response_body.get("aggregations") or {}).items():
            for bucket in aggregation_body.get("buckets", []):
                rows.append({"aggregation": aggregation_name, "key": bucket.get("key_as_string", bucket.get("key")), "count_": bucket.get("doc_count")})
        column_names = sorted({column_name for row in rows for column_name in row})
        return LogQueryResult(column_names, rows, json.dumps(query_body), "elastic_dsl")

    async def test_connection(self) -> ConnectionTestResult:
        time_field = self.configuration.get("time_field") or "@timestamp"
        try:
            index_pattern = self._index_pattern({})
        except IntegrationException as invalid_pattern:
            return ConnectionTestResult(False, invalid_pattern.detail)
        try:
            async with httpx.AsyncClient(timeout=20, auth=self._basic_authentication()) as http_client:
                response = await http_client.post(
                    f"{self._endpoint()}/{index_pattern}/_search",
                    headers=self._headers(),
                    json={"size": 1, "sort": [{time_field: "desc"}], "_source": [time_field]},
                )
        except httpx.HTTPError as connection_error:
            return ConnectionTestResult(False, "Could not reach Elastic. Check the endpoint address and that Keigan can reach it over the network.")
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
        hardened_query = validate_spl(
            telemetry_query.query_text, telemetry_query.time_range_start, telemetry_query.time_range_end, required_index=configured_splunk_index(query_scope)
        )
        request_form = {
            "search": hardened_query.query_text, "output_mode": "json", "count": str(telemetry_query.maximum_rows),
            "earliest_time": str(int(telemetry_query.time_range_start.timestamp())), "latest_time": str(int(telemetry_query.time_range_end.timestamp())),
        }
        try:
            async with httpx.AsyncClient(timeout=90) as http_client:
                response = await http_client.post(f"{self._endpoint()}/services/search/jobs/export", headers=self._headers(), data=request_form)
        except httpx.HTTPError as transport_error:
            raise _failure_for_transport("Splunk", transport_error) from transport_error
        if response.status_code >= 400:
            raise _failure_for_response("Splunk", response)
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
        return LogQueryResult(column_names, rows[: telemetry_query.maximum_rows], hardened_query.query_text, "spl")

    async def test_connection(self) -> ConnectionTestResult:
        try:
            async with httpx.AsyncClient(timeout=20) as http_client:
                response = await http_client.get(f"{self._endpoint()}/services/server/info?output_mode=json", headers=self._headers())
        except httpx.HTTPError as connection_error:
            return ConnectionTestResult(False, "Could not reach Splunk. Check the endpoint address and that Keigan can reach it over the network.")
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
        try:
            async with httpx.AsyncClient(timeout=60) as http_client:
                response = await http_client.post(f"{self._base_url()}/api/v2/logs/events/search", headers=self._headers(), json=request_body)
        except httpx.HTTPError as transport_error:
            raise _failure_for_transport("Datadog", transport_error) from transport_error
        if response.status_code >= 400:
            raise _failure_for_response("Datadog", response)
        rows = [_flatten_document(log_event.get("attributes", {})) for log_event in _json_body("Datadog", response).get("data", [])]
        column_names = sorted({column_name for row in rows for column_name in row})
        return LogQueryResult(column_names, rows, telemetry_query.query_text, "datadog")

    async def test_connection(self) -> ConnectionTestResult:
        try:
            async with httpx.AsyncClient(timeout=20) as http_client:
                response = await http_client.get(f"{self._base_url()}/api/v1/validate", headers=self._headers())
        except httpx.HTTPError as connection_error:
            return ConnectionTestResult(False, "Could not reach Datadog. Check the endpoint address and that Keigan can reach it over the network.")
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
