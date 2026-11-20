"""keigan/integrations/log_tool_clients.py: what the Elastic and Splunk readers send and what they tell the user when the tool fails."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from keigan.entities.application_entities import LogToolConnection
from keigan.exceptions.keigan_exceptions import IntegrationException
from keigan.integrations.log_tool_clients import DatadogClient, ElasticClient, SplunkClient
from keigan.integrations.telemetry_gateway import TelemetryQuery
from keigan.utils.query_safety import QueryRejectedError

WINDOW_END = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
WINDOW_START = WINDOW_END - timedelta(hours=1)
EPOCH_START, EPOCH_END = 1795172400, 1795176000
UPSTREAM_SECRET_TEXT = "index_not_found_exception internal-host-7.corp.example secret-index-name"


class FakeLogTool:
    """Stands in for the remote tool: records every request the reader sends and answers with ``responder``."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.responder: Callable[[httpx.Request], httpx.Response] = lambda request: httpx.Response(200, json={"hits": {"hits": []}})

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responder(request)


@pytest.fixture
def log_tool(monkeypatch: pytest.MonkeyPatch) -> FakeLogTool:
    fake_tool = FakeLogTool()
    real_client = httpx.AsyncClient

    def build_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(fake_tool.handle)
        return real_client(*args, **kwargs)

    monkeypatch.setattr("keigan.integrations.log_tool_clients.httpx.AsyncClient", build_client)
    return fake_tool


def _connection(tool_type: str, configuration: dict[str, Any] | None = None) -> LogToolConnection:
    return LogToolConnection(
        tool_type=tool_type, connection_name=f"Pytest {tool_type}", endpoint_url=f"https://{tool_type}.example.test", authentication_method="api_key",
        connection_configuration_json=configuration or {},
    )


def _query(query_text: str, query_language: str) -> TelemetryQuery:
    return TelemetryQuery(query_language, query_text, WINDOW_START, WINDOW_END)


class TestElasticIndexPatternInTheRequestPath:
    async def test_searches_the_configured_index_pattern(self, log_tool: FakeLogTool) -> None:
        await ElasticClient(_connection("elastic"), "key").search(_query('{"size": 0}', "elastic_dsl"), {"index_pattern": "logs-chad-*"})
        assert log_tool.requests[0].url.path == "/logs-chad-*/_search"

    @pytest.mark.parametrize("index_pattern", ["logs-*/_delete_by_query#", "logs-*?x=1", "..", "logs *", "logs-*/../_all"])
    async def test_refuses_an_index_pattern_that_could_change_the_request_path(self, log_tool: FakeLogTool, index_pattern: str) -> None:
        with pytest.raises(IntegrationException) as failure:
            await ElasticClient(_connection("elastic"), "key").search(_query('{"size": 0}', "elastic_dsl"), {"index_pattern": index_pattern})
        assert log_tool.requests == []
        assert "index pattern" in failure.value.detail
        assert index_pattern not in failure.value.detail

    async def test_refuses_a_bad_index_pattern_from_the_connection_configuration(self, log_tool: FakeLogTool) -> None:
        client = ElasticClient(_connection("elastic", {"index_pattern": "logs-*/_delete_by_query#"}), "key")
        with pytest.raises(IntegrationException):
            await client.search(_query('{"size": 0}', "elastic_dsl"), {})
        assert log_tool.requests == []

    async def test_connection_test_refuses_a_bad_index_pattern(self, log_tool: FakeLogTool) -> None:
        result = await ElasticClient(_connection("elastic", {"index_pattern": "logs-*/_delete_by_query#"}), "key").test_connection()
        assert result.succeeded is False
        assert log_tool.requests == []


class TestElasticRequestBody:
    async def test_bounds_every_query_to_the_time_window(self, log_tool: FakeLogTool) -> None:
        client = ElasticClient(_connection("elastic", {"time_field": "event.created"}), "key")
        await client.search(_query('{"size": 5, "query": {"match": {"log.level": "error"}}}', "elastic_dsl"), {"index_pattern": "logs-*"})
        sent = json.loads(log_tool.requests[0].content)
        assert sent["query"]["bool"]["filter"] == [{"range": {"event.created": {"gte": "2026-11-20T11:00:00+00:00", "lte": "2026-11-20T12:00:00+00:00"}}}]
        assert sent["size"] == 5

    async def test_refuses_a_query_with_a_script(self, log_tool: FakeLogTool) -> None:
        with pytest.raises(QueryRejectedError):
            await ElasticClient(_connection("elastic"), "key").search(_query('{"query": {"script": {"script": "1"}}}', "elastic_dsl"), {"index_pattern": "logs-*"})
        assert log_tool.requests == []

    async def test_wraps_plain_text_in_a_query_string(self, log_tool: FakeLogTool) -> None:
        await ElasticClient(_connection("elastic"), "key").search(_query("level:error", "elastic_dsl"), {"index_pattern": "logs-*"})
        assert json.loads(log_tool.requests[0].content)["query"]["bool"]["must"] == [{"query_string": {"query": "level:error"}}]


class TestUpstreamErrorsAreNotShownToUsers:
    async def test_elastic_error_body_stays_in_the_log(self, log_tool: FakeLogTool, caplog: pytest.LogCaptureFixture) -> None:
        log_tool.responder = lambda request: httpx.Response(404, text=UPSTREAM_SECRET_TEXT)
        with caplog.at_level("WARNING"), pytest.raises(IntegrationException) as failure:
            await ElasticClient(_connection("elastic"), "key").search(_query('{"size": 0}', "elastic_dsl"), {"index_pattern": "logs-*"})
        assert "internal-host-7" not in failure.value.detail
        assert "404" in failure.value.detail
        assert "internal-host-7" in caplog.text

    async def test_splunk_error_body_stays_in_the_log(self, log_tool: FakeLogTool, caplog: pytest.LogCaptureFixture) -> None:
        log_tool.responder = lambda request: httpx.Response(400, text=UPSTREAM_SECRET_TEXT)
        with caplog.at_level("WARNING"), pytest.raises(IntegrationException) as failure:
            await SplunkClient(_connection("splunk"), "token").search(_query("error", "spl"), {"index": "main"})
        assert "internal-host-7" not in failure.value.detail
        assert "400" in failure.value.detail
        assert "internal-host-7" in caplog.text

    async def test_datadog_error_body_stays_in_the_log(self, log_tool: FakeLogTool, caplog: pytest.LogCaptureFixture) -> None:
        log_tool.responder = lambda request: httpx.Response(403, text=UPSTREAM_SECRET_TEXT)
        with caplog.at_level("WARNING"), pytest.raises(IntegrationException) as failure:
            await DatadogClient(_connection("datadog"), "a:b").search(_query("status:error", "datadog"), {})
        assert "internal-host-7" not in failure.value.detail
        assert "403" in failure.value.detail
        assert "internal-host-7" in caplog.text

    async def test_a_reply_that_is_not_json_is_a_clean_integration_error(self, log_tool: FakeLogTool) -> None:
        log_tool.responder = lambda request: httpx.Response(200, text="<html>proxy login</html>")
        with pytest.raises(IntegrationException) as failure:
            await ElasticClient(_connection("elastic"), "key").search(_query('{"size": 0}', "elastic_dsl"), {"index_pattern": "logs-*"})
        assert "proxy login" not in failure.value.detail

    async def test_an_unreachable_tool_is_a_clean_integration_error(self, log_tool: FakeLogTool) -> None:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused by 10.1.2.3")

        log_tool.responder = refuse
        with pytest.raises(IntegrationException) as failure:
            await SplunkClient(_connection("splunk"), "token").search(_query("error", "spl"), {"index": "main"})
        assert "10.1.2.3" not in failure.value.detail


class TestSplunkRequest:
    async def test_sends_the_time_window_as_api_parameters(self, log_tool: FakeLogTool) -> None:
        log_tool.responder = lambda request: httpx.Response(200, text="")
        await SplunkClient(_connection("splunk"), "token").search(_query("search index=main error | stats count", "spl"), {"index": "main"})
        form = parse_qs(log_tool.requests[0].content.decode())
        assert form["earliest_time"] == [str(EPOCH_START)]
        assert form["latest_time"] == [str(EPOCH_END)]

    async def test_forces_the_configured_index_in_the_search(self, log_tool: FakeLogTool) -> None:
        log_tool.responder = lambda request: httpx.Response(200, text="")
        await SplunkClient(_connection("splunk"), "token").search(_query("search index=* error | stats count", "spl"), {"index": "zos_syslog"})
        search = parse_qs(log_tool.requests[0].content.decode())["search"][0]
        assert search.startswith("search index=zos_syslog earliest=")
        assert "index=*" not in search

    async def test_refuses_a_search_when_the_source_has_no_index(self, log_tool: FakeLogTool) -> None:
        with pytest.raises(QueryRejectedError):
            await SplunkClient(_connection("splunk"), "token").search(_query("search index=* error", "spl"), {})
        assert log_tool.requests == []

    async def test_refuses_a_command_that_is_not_allowed(self, log_tool: FakeLogTool) -> None:
        with pytest.raises(QueryRejectedError):
            await SplunkClient(_connection("splunk"), "token").search(_query("search error | outputlookup x", "spl"), {"index": "main"})
        assert log_tool.requests == []
