"""
Elastic evidence adapter.

Queries Elastic for application logs and metrics for a named service.

Runtime config is env/bootstrap-driven by default (ELASTIC_HOST,
ELASTIC_API_KEY, index and limit env vars), with adapter-level overrides
supported via the constructor.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from elasticsearch import Elasticsearch

logger = logging.getLogger(__name__)

_ENV_PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")


def _expand(value: str) -> str:
    """Expand ${VAR_NAME} placeholders using os.environ."""
    return _ENV_PLACEHOLDER.sub(lambda m: os.environ.get(m.group(1), ""), str(value))


def _build_client(config: dict[str, Any]) -> Elasticsearch:
    host = _expand(config.get("host", "http://localhost:9200"))
    api_key_raw = _expand(config.get("api_key", ""))
    if api_key_raw:
        return Elasticsearch(host, api_key=api_key_raw)
    return Elasticsearch(host)


class ElasticAdapter:
    """Adapter for querying Elastic logs and metrics."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config if config is not None else _default_config()
        # Build the client once so the internal connection pool is reused across calls.
        self._client: Elasticsearch | None = None
        try:
            host = str(self._config.get("host", "")).strip()
            if host:
                self._client = _build_client(self._config)
            else:
                logger.warning("ElasticAdapter: ELASTIC_HOST is not configured; adapter will return empty results")
        except Exception as exc:  # noqa: BLE001
            logger.warning("ElasticAdapter: failed to initialize client: %s", exc)
            self._client = None

    def get_logs(
        self,
        service_name: str,
        environment: str | None = None,
        time_range_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query Elastic for recent application logs for the given service.

        Args:
            service_name:       Service to query.
            environment:        Optional deployment environment filter (e.g. "production").
            time_range_minutes: Lookback window; defaults to config default_time_range_minutes.

        Returns:
            List of log document _source dicts, newest first. Empty list on error.
        """
        if self._client is None:
            return []

        minutes = time_range_minutes or self._config.get("default_time_range_minutes", 30)
        max_hits = self._config.get("max_log_hits", 50)
        index = self._config.get("log_index_pattern", "logs-*")

        must_clauses: list[dict[str, Any]] = [
            {"match": {"service.name": service_name}},
        ]
        if environment:
            must_clauses.append({"match": {"service.environment": environment}})

        query = {
            "bool": {
                "must": must_clauses,
                "filter": [{"range": {"@timestamp": {"gte": f"now-{minutes}m"}}}],
            }
        }

        try:
            response = self._client.search(
                index=index,
                query=query,
                size=max_hits,
                sort=[{"@timestamp": {"order": "desc"}}],
            )
            return [hit["_source"] for hit in response["hits"]["hits"]]
        except Exception as exc:
            logger.warning("ElasticAdapter.get_logs failed for service=%s: %s", service_name, exc)
            return []

    def get_metrics(
        self,
        service_name: str,
        environment: str | None = None,
        time_range_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query Elastic for recent metrics for the given service using a date histogram
        aggregation. Returns average and max values per 1-minute bucket.

        Args:
            service_name:       Service to query.
            environment:        Optional deployment environment filter.
            time_range_minutes: Lookback window; defaults to config default_time_range_minutes.

        Returns:
            List of aggregation bucket dicts. Empty list on error.
        """
        if self._client is None:
            return []

        minutes = time_range_minutes or self._config.get("default_time_range_minutes", 30)
        index = self._config.get("metrics_index_pattern", "metrics-*")

        must_clauses: list[dict[str, Any]] = [
            {"match": {"service.name": service_name}},
        ]
        if environment:
            must_clauses.append({"match": {"service.environment": environment}})

        query = {
            "bool": {
                "must": must_clauses,
                "filter": [{"range": {"@timestamp": {"gte": f"now-{minutes}m"}}}],
            }
        }
        aggs = {
            "by_time": {
                "date_histogram": {
                    "field": "@timestamp",
                    "fixed_interval": "1m",
                },
                "aggs": {
                    "avg_value": {"avg": {"field": "value"}},
                    "max_value": {"max": {"field": "value"}},
                },
            }
        }

        try:
            response = self._client.search(
                index=index,
                query=query,
                aggregations=aggs,
                size=0,
            )
            return response["aggregations"]["by_time"]["buckets"]
        except Exception as exc:
            logger.warning("ElasticAdapter.get_metrics failed for service=%s: %s", service_name, exc)
            return []


def _default_config() -> dict[str, Any]:
    return {
        "host": os.environ.get("ELASTIC_HOST", ""),
        "api_key": os.environ.get("ELASTIC_API_KEY", ""),
        "default_time_range_minutes": int(os.environ.get("ELASTIC_DEFAULT_TIME_RANGE_MINUTES", "30")),
        "max_log_hits": int(os.environ.get("ELASTIC_MAX_LOG_HITS", "50")),
        "log_index_pattern": os.environ.get("ELASTIC_LOG_INDEX_PATTERN", "logs-*"),
        "metrics_index_pattern": os.environ.get("ELASTIC_METRICS_INDEX_PATTERN", "metrics-*"),
    }
