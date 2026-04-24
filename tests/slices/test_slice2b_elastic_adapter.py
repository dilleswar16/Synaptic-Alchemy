"""
Slice 2b – Elastic adapter wire-up tests.

Uses unittest.mock.patch to mock the Elasticsearch client so no live cluster
is required.  Tests cover:
  - Successful log query returns list of _source dicts.
  - Successful metrics query returns aggregation bucket dicts.
  - Connection error on get_logs returns empty list (graceful degradation).
  - Connection error on get_metrics returns empty list (graceful degradation).
  - environment filter is omitted when not provided (no extra must clause).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from corvin.evidence.elastic_adapter import ElasticAdapter

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

_CONFIG = {
    "host": "http://localhost:9200",
    "api_key": "test-api-key",
    "log_index_pattern": "logs-*",
    "metrics_index_pattern": "metrics-*",
    "default_time_range_minutes": 30,
    "max_log_hits": 50,
}

_LOG_RESPONSE = {
    "hits": {
        "hits": [
            {"_source": {"message": "NullPointerException in OrderService", "level": "ERROR"}},
            {"_source": {"message": "Request received", "level": "INFO"}},
        ]
    }
}

_METRICS_RESPONSE = {
    "aggregations": {
        "by_time": {
            "buckets": [
                {
                    "key_as_string": "2026-04-04T00:00:00.000Z",
                    "avg_value": {"value": 42.5},
                    "max_value": {"value": 95.0},
                },
                {
                    "key_as_string": "2026-04-04T00:01:00.000Z",
                    "avg_value": {"value": 38.1},
                    "max_value": {"value": 88.3},
                },
            ]
        }
    }
}


# ---------------------------------------------------------------------------
# get_logs tests
# ---------------------------------------------------------------------------


def test_get_logs_returns_list_of_dicts():
    """Successful log query returns each hit's _source as a plain dict."""
    with patch("corvin.evidence.elastic_adapter.Elasticsearch") as MockES:
        MockES.return_value.search.return_value = _LOG_RESPONSE
        adapter = ElasticAdapter(config=_CONFIG)
        result = adapter.get_logs("order-service", environment="production")

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0] == {"message": "NullPointerException in OrderService", "level": "ERROR"}
    assert result[1] == {"message": "Request received", "level": "INFO"}


def test_get_logs_without_environment_still_works():
    """Omitting environment should not raise; environment filter simply absent."""
    with patch("corvin.evidence.elastic_adapter.Elasticsearch") as MockES:
        MockES.return_value.search.return_value = _LOG_RESPONSE
        adapter = ElasticAdapter(config=_CONFIG)
        result = adapter.get_logs("order-service")

    assert isinstance(result, list)
    assert len(result) == 2

    # Verify the search call did NOT include a service.environment clause
    call_kwargs = MockES.return_value.search.call_args.kwargs
    must_clauses = call_kwargs["query"]["bool"]["must"]
    environment_clauses = [c for c in must_clauses if "service.environment" in str(c)]
    assert environment_clauses == [], "environment filter should be absent when not provided"


def test_get_logs_connection_error_returns_empty_list():
    """If Elasticsearch raises an exception, get_logs returns [] without re-raising."""
    with patch("corvin.evidence.elastic_adapter.Elasticsearch") as MockES:
        MockES.return_value.search.side_effect = Exception("Connection refused")
        adapter = ElasticAdapter(config=_CONFIG)
        result = adapter.get_logs("order-service", environment="production")

    assert result == []


# ---------------------------------------------------------------------------
# get_metrics tests
# ---------------------------------------------------------------------------


def test_get_metrics_returns_aggregation_buckets():
    """Successful metrics query returns the date histogram bucket list."""
    with patch("corvin.evidence.elastic_adapter.Elasticsearch") as MockES:
        MockES.return_value.search.return_value = _METRICS_RESPONSE
        adapter = ElasticAdapter(config=_CONFIG)
        result = adapter.get_metrics("order-service", environment="production")

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["avg_value"]["value"] == 42.5
    assert result[1]["max_value"]["value"] == 88.3


def test_get_metrics_connection_error_returns_empty_list():
    """If Elasticsearch raises an exception, get_metrics returns [] without re-raising."""
    with patch("corvin.evidence.elastic_adapter.Elasticsearch") as MockES:
        MockES.return_value.search.side_effect = ConnectionError("Timeout")
        adapter = ElasticAdapter(config=_CONFIG)
        result = adapter.get_metrics("order-service", environment="production")

    assert result == []


# ---------------------------------------------------------------------------
# Client construction tests
# ---------------------------------------------------------------------------


def test_api_key_passed_to_elasticsearch_constructor():
    """When api_key is configured, it is forwarded to the Elasticsearch client."""
    with patch("corvin.evidence.elastic_adapter.Elasticsearch") as MockES:
        MockES.return_value.search.return_value = _LOG_RESPONSE
        adapter = ElasticAdapter(config=_CONFIG)
        adapter.get_logs("svc")

    MockES.assert_called_once_with("http://localhost:9200", api_key="test-api-key")


def test_env_placeholder_expanded_from_os_environ(monkeypatch):
    """${ELASTIC_HOST} in config is resolved from os.environ at call time."""
    monkeypatch.setenv("ELASTIC_HOST", "http://elastic.example.com:9200")
    monkeypatch.setenv("ELASTIC_API_KEY", "env-key")
    config_with_placeholders = {
        "host": "${ELASTIC_HOST}",
        "api_key": "${ELASTIC_API_KEY}",
        "log_index_pattern": "logs-*",
        "metrics_index_pattern": "metrics-*",
        "default_time_range_minutes": 30,
        "max_log_hits": 50,
    }
    with patch("corvin.evidence.elastic_adapter.Elasticsearch") as MockES:
        MockES.return_value.search.return_value = _LOG_RESPONSE
        adapter = ElasticAdapter(config=config_with_placeholders)
        adapter.get_logs("svc")

    MockES.assert_called_once_with("http://elastic.example.com:9200", api_key="env-key")
