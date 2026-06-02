"""
Enrichment service.

Orchestrates evidence collection from all configured adapters for a single
InvestigationRequest.  Adapters that are not yet wired (NotImplementedError)
are silently skipped so that partial enrichment still produces a usable bundle.

Inject custom adapter instances in tests or when swapping implementations.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Generator
from typing import Any

from corvin.core.contracts import EvidenceBundle, InvestigationRequest
from corvin.evidence.aks_adapter import AKSAdapter
from corvin.evidence.container_logs_adapter import ContainerLogsAdapter
from corvin.evidence.elastic_adapter import ElasticAdapter
from corvin.evidence.log_analytics_adapter import LogAnalyticsAdapter


_log = logging.getLogger(__name__)


def _timed_step(
    source_name: str,
    table: str,
    fn: Callable[[], Any],
) -> Generator[tuple[dict, None], None, Any]:
    """
    Sub-generator used by EnrichmentService.enrich_streaming().

    Yields a "running" progress tuple, calls *fn* (timing it), then yields a
    "done" progress tuple.  The adapter return value is available to the caller
    via ``result = yield from _timed_step(...)`` (PEP 380 StopIteration.value).

    Each progress tuple: ``({ source, table, source_status, count, elapsed_ms }, None)``
    """
    yield {"source": source_name, "table": table, "source_status": "running", "count": 0, "elapsed_ms": 0}, None
    t0 = time.monotonic()
    try:
        result = fn()
    except NotImplementedError:
        result = []
    except Exception as exc:
        _log.warning("Adapter %s failed: %s", source_name, exc)
        result = []
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    count = len(result) if isinstance(result, list) else (1 if result else 0)
    yield {"source": source_name, "table": table, "source_status": "done", "count": count, "elapsed_ms": elapsed_ms}, None
    return result


class EnrichmentService:
    """Collects deterministic pre-investigation evidence from all adapters."""

    def __init__(
        self,
        elastic: ElasticAdapter | None = None,
        log_analytics: LogAnalyticsAdapter | None = None,
        aks: AKSAdapter | None = None,
        container_logs: ContainerLogsAdapter | None = None,
    ) -> None:
        self._elastic = elastic if elastic is not None else ElasticAdapter()
        self._log_analytics = log_analytics or LogAnalyticsAdapter()
        self._aks = aks or AKSAdapter()
        self._container_logs = container_logs or ContainerLogsAdapter()

    def enrich(self, request: InvestigationRequest) -> EvidenceBundle:
        """
        Collect all available evidence for the given request.

        Adapters that raise NotImplementedError are skipped (graceful
        degradation while adapters are being wired up slice by slice).
        Real adapter errors should be allowed to propagate.
        """
        bundle = EvidenceBundle(request_id=request.id)

        if self._elastic is not None:
            try:
                bundle.elastic_logs = self._elastic.get_logs(
                    request.service_name, time_range_minutes=request.lookback_minutes
                )
            except NotImplementedError:
                pass
            except Exception as exc:
                _log.warning("ElasticAdapter.get_logs failed: %s", exc)

            try:
                bundle.elastic_metrics = self._elastic.get_metrics(
                    request.service_name, time_range_minutes=request.lookback_minutes
                )
            except NotImplementedError:
                pass
            except Exception as exc:
                _log.warning("ElasticAdapter.get_metrics failed: %s", exc)

        if not bundle.elastic_logs:
            try:
                bundle.elastic_logs = self._container_logs.get_container_logs(
                    request.service_name, time_range_minutes=request.lookback_minutes
                )
            except NotImplementedError:
                pass
            except Exception as exc:
                _log.warning("ContainerLogsAdapter.get_container_logs failed: %s", exc)

        try:
            bundle.log_analytics_apim = self._log_analytics.get_apim_logs(
                request.service_name, time_range_minutes=request.lookback_minutes
            )
        except NotImplementedError:
            pass
        except Exception as exc:
            _log.warning("LogAnalyticsAdapter.get_apim_logs failed: %s", exc)

        try:
            bundle.aks_context = self._aks.get_pod_context(
                request.service_name, environment=request.environment
            )
        except NotImplementedError:
            pass
        except Exception as exc:
            _log.warning("AKSAdapter.get_pod_context failed: %s", exc)

        try:
            bundle.container_resource_metrics = self._container_logs.get_resource_metrics(
                request.service_name, time_range_minutes=request.lookback_minutes
            )
        except NotImplementedError:
            pass
        except Exception as exc:
            _log.warning("ContainerLogsAdapter.get_resource_metrics failed: %s", exc)

        try:
            bundle.container_inventory = self._container_logs.get_container_inventory(
                request.service_name, time_range_minutes=request.lookback_minutes
            )
        except NotImplementedError:
            pass
        except Exception as exc:
            _log.warning("ContainerLogsAdapter.get_container_inventory failed: %s", exc)

        try:
            bundle.node_inventory = self._container_logs.get_node_inventory(
                request.service_name, time_range_minutes=request.lookback_minutes
            )
        except NotImplementedError:
            pass
        except Exception as exc:
            _log.warning("ContainerLogsAdapter.get_node_inventory failed: %s", exc)

        try:
            bundle.network_metrics = self._container_logs.get_network_metrics(
                request.service_name, time_range_minutes=request.lookback_minutes
            )
        except NotImplementedError:
            pass
        except Exception as exc:
            _log.warning("ContainerLogsAdapter.get_network_metrics failed: %s", exc)

        try:
            bundle.pod_restarts = self._container_logs.get_pod_restarts(
                request.service_name, time_range_minutes=request.lookback_minutes
            )
        except NotImplementedError:
            pass
        except Exception as exc:
            _log.warning("ContainerLogsAdapter.get_pod_restarts failed: %s", exc)

        try:
            bundle.oom_kill_events = self._container_logs.get_oom_kill_events(
                request.service_name, time_range_minutes=request.lookback_minutes
            )
        except NotImplementedError:
            pass
        except Exception as exc:
            _log.warning("ContainerLogsAdapter.get_oom_kill_events failed: %s", exc)

        try:
            bundle.autoscaler_events = self._container_logs.get_autoscaler_events(
                request.service_name, time_range_minutes=request.lookback_minutes
            )
        except NotImplementedError:
            pass
        except Exception as exc:
            _log.warning("ContainerLogsAdapter.get_autoscaler_events failed: %s", exc)

        try:
            bundle.health_probe_failures = self._container_logs.get_health_probe_failures(
                request.service_name, time_range_minutes=request.lookback_minutes
            )
        except NotImplementedError:
            pass
        except Exception as exc:
            _log.warning("ContainerLogsAdapter.get_health_probe_failures failed: %s", exc)

        return bundle

    def enrich_streaming(
        self,
        request: InvestigationRequest,
    ) -> Generator[tuple[dict, None] | tuple[None, EvidenceBundle], None, None]:
        """
        Streaming variant of enrich().

        Yields ``(progress_dict, None)`` before and after each adapter call so
        the caller can emit real-time SSE events, then yields
        ``(None, EvidenceBundle)`` as the terminal item.

        Each progress dict:
            { source, table, source_status ("running"|"done"), count, elapsed_ms }

        Usage in the streamer::

            for progress, bundle in self._enrichment.enrich_streaming(request):
                if bundle is not None:
                    evidence = bundle
                else:
                    emit_sse(progress)
        """
        b = EvidenceBundle(request_id=request.id)

        if self._elastic is not None:
            b.elastic_logs = (yield from _timed_step(
                "elastic_logs", "Elastic logs-*",
                lambda: self._elastic.get_logs(  # type: ignore[union-attr]
                    request.service_name, time_range_minutes=request.lookback_minutes
                ),
            )) or []
            b.elastic_metrics = (yield from _timed_step(
                "elastic_metrics", "Elastic metrics-*",
                lambda: self._elastic.get_metrics(  # type: ignore[union-attr]
                    request.service_name, time_range_minutes=request.lookback_minutes
                ),
            )) or []

        if not b.elastic_logs:
            b.elastic_logs = (yield from _timed_step(
                "container_logs", "ContainerLog",
                lambda: self._container_logs.get_container_logs(
                    request.service_name, time_range_minutes=request.lookback_minutes
                ),
            )) or []

        b.log_analytics_apim = (yield from _timed_step(
            "apim_logs", "ApiManagementGatewayLogs",
            lambda: self._log_analytics.get_apim_logs(
                request.service_name, time_range_minutes=request.lookback_minutes
            ),
        )) or []

        b.aks_context = (yield from _timed_step(
            "aks_context", "KubePodInventory · KubeEvents",
            lambda: self._aks.get_pod_context(
                request.service_name, environment=request.environment
            ),
        )) or {}

        b.container_resource_metrics = (yield from _timed_step(
            "resource_metrics", "Perf · K8SContainer",
            lambda: self._container_logs.get_resource_metrics(
                request.service_name, time_range_minutes=request.lookback_minutes
            ),
        )) or []

        b.container_inventory = (yield from _timed_step(
            "container_inventory", "ContainerInventory",
            lambda: self._container_logs.get_container_inventory(
                request.service_name, time_range_minutes=request.lookback_minutes
            ),
        )) or []

        b.node_inventory = (yield from _timed_step(
            "node_inventory", "KubeNodeInventory",
            lambda: self._container_logs.get_node_inventory(
                request.service_name, time_range_minutes=request.lookback_minutes
            ),
        )) or []

        b.network_metrics = (yield from _timed_step(
            "network_metrics", "InsightsMetrics · tx, rx",
            lambda: self._container_logs.get_network_metrics(
                request.service_name, time_range_minutes=request.lookback_minutes
            ),
        )) or []

        b.pod_restarts = (yield from _timed_step(
            "pod_restarts", "KubePodInventory · restarts",
            lambda: self._container_logs.get_pod_restarts(
                request.service_name, time_range_minutes=request.lookback_minutes
            ),
        )) or []

        b.oom_kill_events = (yield from _timed_step(
            "oom_kill_events", "KubeEvents · OOMKill",
            lambda: self._container_logs.get_oom_kill_events(
                request.service_name, time_range_minutes=request.lookback_minutes
            ),
        )) or []

        b.autoscaler_events = (yield from _timed_step(
            "autoscaler_events", "KubeEvents · HPA",
            lambda: self._container_logs.get_autoscaler_events(
                request.service_name, time_range_minutes=request.lookback_minutes
            ),
        )) or []

        b.health_probe_failures = (yield from _timed_step(
            "health_probe_failures", "KubeEvents · probes",
            lambda: self._container_logs.get_health_probe_failures(
                request.service_name, time_range_minutes=request.lookback_minutes
            ),
        )) or []

        yield None, b
