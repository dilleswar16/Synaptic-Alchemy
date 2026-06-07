"""Connector package — pluggable log/metrics data source adapters."""
from corvin.connectors.base import BaseConnector, TestResult
from corvin.connectors.registry import ConnectorRegistry

__all__ = ["BaseConnector", "TestResult", "ConnectorRegistry"]
