"""Elasticsearch connector — parametrised from DB config."""
from __future__ import annotations

import logging
import time
from typing import Any

from corvin.connectors.base import BaseConnector, TestResult

_log = logging.getLogger(__name__)

try:
    from elasticsearch import Elasticsearch  # type: ignore[import-untyped]
    _ES_AVAILABLE = True
except ImportError:
    _ES_AVAILABLE = False


class ElasticConnector(BaseConnector):
    """
    Connects to an Elasticsearch cluster.

    config keys:
        cluster_url (required): e.g. "https://my-cluster:9200"
        index_pattern_logs (optional, default "logs-*")
        index_pattern_metrics (optional, default "metrics-*")
    credential_value: Elasticsearch API key string
    """

    def __init__(self, config: dict[str, Any], credential_value: str | None = None) -> None:
        self._url: str = config.get("cluster_url", "")
        self._index_logs: str = config.get("index_pattern_logs", "logs-*")
        self._index_metrics: str = config.get("index_pattern_metrics", "metrics-*")
        self._client = None
        if _ES_AVAILABLE and self._url:
            try:
                self._client = Elasticsearch(
                    self._url,
                    api_key=credential_value or "",
                    verify_certs=False,
                )
            except Exception as exc:
                _log.warning("ElasticConnector init failed: %s", exc)

    def test_connection(self) -> TestResult:
        if not _ES_AVAILABLE:
            return TestResult(ok=False, message="elasticsearch-py not installed (pip install elasticsearch)")
        if self._client is None:
            return TestResult(ok=False, message="cluster_url is empty or client init failed")
        t0 = time.monotonic()
        try:
            info = self._client.info()
            ms = (time.monotonic() - t0) * 1000
            return TestResult(ok=True, message=f"Elasticsearch {info['version']['number']}", latency_ms=ms)
        except Exception as exc:
            ms = (time.monotonic() - t0) * 1000
            return TestResult(ok=False, message=str(exc), latency_ms=ms)

    def fetch_logs(self, service_name: str, time_range_minutes: int = 60) -> list[dict[str, Any]]:
        if self._client is None:
            return []
        try:
            resp = self._client.search(
                index=self._index_logs,
                body={
                    "query": {"bool": {"filter": [
                        {"range": {"@timestamp": {"gte": f"now-{time_range_minutes}m"}}},
                        {"match": {"service.name": service_name}},
                    ]}},
                    "size": 100,
                    "sort": [{"@timestamp": "desc"}],
                },
            )
            return [hit["_source"] for hit in resp["hits"]["hits"]]
        except Exception as exc:
            _log.debug("ElasticConnector.fetch_logs: %s", exc)
            return []

    def fetch_metrics(self, service_name: str, time_range_minutes: int = 60) -> list[dict[str, Any]]:
        if self._client is None:
            return []
        try:
            resp = self._client.search(
                index=self._index_metrics,
                body={
                    "query": {"bool": {"filter": [
                        {"range": {"@timestamp": {"gte": f"now-{time_range_minutes}m"}}},
                        {"match": {"service.name": service_name}},
                    ]}},
                    "size": 100,
                    "sort": [{"@timestamp": "desc"}],
                },
            )
            return [hit["_source"] for hit in resp["hits"]["hits"]]
        except Exception as exc:
            _log.debug("ElasticConnector.fetch_metrics: %s", exc)
            return []
