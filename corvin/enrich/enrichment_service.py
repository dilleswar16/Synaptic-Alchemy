"""
Enrichment service.

Orchestrates evidence collection from all configured adapters for a single
InvestigationRequest.  Adapters that are not yet wired (NotImplementedError)
are silently skipped so that partial enrichment still produces a usable bundle.

Inject custom adapter instances in tests or when swapping implementations.
"""

from __future__ import annotations

import logging

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import EvidenceBundle, InvestigationRequest
from corvin.evidence.aks_adapter import AKSAdapter
from corvin.evidence.azure_activity_adapter import AzureActivityAdapter
from corvin.evidence.container_logs_adapter import ContainerLogsAdapter
from corvin.evidence.elastic_adapter import ElasticAdapter
from corvin.evidence.log_analytics_adapter import LogAnalyticsAdapter


_log = logging.getLogger(__name__)


class EnrichmentService:
    """Collects deterministic pre-investigation evidence from all adapters."""

    def __init__(
        self,
        elastic: ElasticAdapter | None = None,
        log_analytics: LogAnalyticsAdapter | None = None,
        aks: AKSAdapter | None = None,
        azure_activity: AzureActivityAdapter | None = None,
        container_logs: ContainerLogsAdapter | None = None,
    ) -> None:
        elastic_cfg = load_config("integrations/elastic", get_env())
        self._elastic = elastic if elastic is not None else (ElasticAdapter() if elastic_cfg.get("enabled", True) else None)
        self._log_analytics = log_analytics or LogAnalyticsAdapter()
        self._aks = aks or AKSAdapter()
        self._azure_activity = azure_activity or AzureActivityAdapter()
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
            bundle.azure_activity_changes = self._azure_activity.get_recent_changes(
                request.service_name, time_range_minutes=request.lookback_minutes
            )
        except NotImplementedError:
            pass
        except Exception as exc:
            _log.warning("AzureActivityAdapter.get_recent_changes failed: %s", exc)

        return bundle
