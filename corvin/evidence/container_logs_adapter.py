"""
Container Insights evidence adapter.

Queries the CHAD Log Analytics workspace for AKS container logs and pod
inventory using Azure Monitor Container Insights tables:

  - ContainerLogV2    : pod stdout/stderr application logs
  - KubePodInventory  : pod state, restarts, phases
  - KubeEvents        : OOMKill, BackOff, scheduling failures

This adapter replaces Elastic for application and Kubernetes metrics when
Elastic is unavailable (e.g. org SSO restrictions).

Config is loaded from config/integrations/container_logs.yaml.
Auth uses DefaultAzureCredential (AzureCliCredential for local dev,
service principal via AZURE_CLIENT_ID/SECRET/TENANT for production).
"""

from __future__ import annotations

import logging
import os
import re
from datetime import timedelta
from typing import Any

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass  # truststore is optional; required in corporate proxy environments

from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus

from corvin.core.config_loader import get_env, load_config

logger = logging.getLogger(__name__)

_ENV_PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")


def _expand(value: str) -> str:
    """Expand ${VAR_NAME} placeholders using os.environ."""
    return _ENV_PLACEHOLDER.sub(lambda m: os.environ.get(m.group(1), ""), str(value))


def _to_dicts(table: Any) -> list[dict[str, Any]]:
    """Convert a LogsQueryResult table to a list of plain dicts, serializing datetimes."""
    columns = [c.name if hasattr(c, "name") else c for c in table.columns]
    return [
        {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in zip(columns, row)}
        for row in table.rows
    ]


class ContainerLogsAdapter:
    """Adapter for querying AKS container logs via Azure Monitor Container Insights."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = (
            config if config is not None
            else load_config("integrations/container_logs", get_env())
        )
        self._client: LogsQueryClient | None = None
        try:
            credential = DefaultAzureCredential()
            self._client = LogsQueryClient(credential)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ContainerLogsAdapter: could not build client (will return empty results): %s", exc
            )
        self._workspace_id = _expand(self._config.get("workspace_id", ""))

    # ── Public methods ────────────────────────────────────────────────────────

    def get_container_logs(
        self,
        service_name: str,
        namespace: str | None = None,
        time_range_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch recent stdout/stderr logs for a service from ContainerLogV2.

        Args:
            service_name:       Pod name prefix or container name to filter on.
            namespace:          Kubernetes namespace. Defaults to config default_namespace.
            time_range_minutes: Lookback window. Defaults to config value.

        Returns:
            List of log row dicts. Empty list on error or no results.
        """
        if self._client is None:
            return []

        minutes = time_range_minutes or self._config.get("default_time_range_minutes", 60)
        ns = namespace or self._config.get("default_namespace", "chad")
        max_rows = self._config.get("max_log_rows", 200)

        query = (
            f"let pods = KubePodInventory"
            f"| where TimeGenerated >= ago({minutes}m)"
            f'| where Namespace == "{ns}"'
            f'| where Name contains "{service_name}"'
            f"| distinct ContainerID;"
            f"ContainerLog"
            f"| where TimeGenerated >= ago({minutes}m)"
            f"| where ContainerID in (pods)"
            f"| project TimeGenerated, Name, LogEntry, LogEntrySource, ContainerID"
            f"| order by TimeGenerated desc"
            f"| take {max_rows}"
        )

        return self._run_query(query, minutes, f"get_container_logs(service={service_name})")

    def get_pod_inventory(
        self,
        service_name: str,
        namespace: str | None = None,
        time_range_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch pod state and restart counts from KubePodInventory.

        Args:
            service_name:       Deployment or pod name prefix to filter on.
            namespace:          Kubernetes namespace. Defaults to config default_namespace.
            time_range_minutes: Lookback window. Defaults to config value.

        Returns:
            List of pod inventory row dicts. Empty list on error or no results.
        """
        if self._client is None:
            return []

        minutes = time_range_minutes or self._config.get("default_time_range_minutes", 60)
        ns = namespace or self._config.get("default_namespace", "chad")

        query = (
            f"KubePodInventory\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f'| where Namespace == "{ns}"\n'
            f'| where Name contains "{service_name}"\n'
            f"| project TimeGenerated, Name, Namespace, PodStatus, ContainerStatus,"
            f" ContainerStatusReason, ContainerRestartCount, PodRestartCount, ControllerName, ControllerKind\n"
            f"| summarize arg_max(TimeGenerated, *) by Name"
        )

        return self._run_query(query, minutes, f"get_pod_inventory(service={service_name})")

    def get_kube_events(
        self,
        service_name: str,
        namespace: str | None = None,
        time_range_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch Kubernetes warning events for a service from KubeEvents.

        Args:
            service_name:       Object name prefix to filter events on.
            namespace:          Kubernetes namespace. Defaults to config default_namespace.
            time_range_minutes: Lookback window. Defaults to config value.

        Returns:
            List of event row dicts. Empty list on error or no results.
        """
        if self._client is None:
            return []

        minutes = time_range_minutes or self._config.get("default_time_range_minutes", 60)
        ns = namespace or self._config.get("default_namespace", "chad")

        query = (
            f"KubeEvents\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f'| where Namespace == "{ns}"\n'
            f'| where Name contains "{service_name}"\n'
            f"| where KubeEventType == 'Warning'\n"
            f"| project TimeGenerated, Name, Namespace, Reason, Message, KubeEventType, Count\n"
            f"| order by TimeGenerated desc\n"
            f"| take 50"
        )

        return self._run_query(query, minutes, f"get_kube_events(service={service_name})")

    def get_resource_metrics(
        self,
        service_name: str,
        namespace: str | None = None,
        time_range_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch CPU and memory metrics for containers running a service.

        Queries the Perf table (Container Insights standard) for container-level
        counters, joined through KubePodInventory PodUid to scope to the target
        service's pods. Perf InstanceName is a full resource path where the
        penultimate segment is PodUid and the last segment is ContainerName.
        """
        if self._client is None:
            return []

        minutes = time_range_minutes or self._config.get("default_time_range_minutes", 60)
        ns = namespace or self._config.get("default_namespace", "chad")

        query = (
            f"let podUids = KubePodInventory\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f'| where Namespace == "{ns}"\n'
            f'| where Name contains "{service_name}"\n'
            f"| summarize arg_max(TimeGenerated, Name) by PodUid;\n"
            f"Perf\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f"| where ObjectName == 'K8SContainer'\n"
            f"| where CounterName in ('cpuUsageNanoCores', 'cpuLimitNanoCores', 'cpuRequestNanoCores',"
            f" 'memoryWorkingSetBytes', 'memoryRssBytes', 'memoryLimitBytes', 'memoryRequestBytes')\n"
            f"| where InstanceName has_any (podUids)\n"
            f"| extend parts = split(InstanceName, '/')\n"
            f"| extend PodUid = tostring(parts[array_length(parts) - 2])\n"
            f"| lookup kind=leftouter podUids on PodUid\n"
            f"| extend ContainerName = tostring(parts[array_length(parts) - 1])\n"
            f"| summarize AvgValue=avg(CounterValue), MaxValue=max(CounterValue)"
            f" by bin(TimeGenerated, 5m), Name, ContainerName, CounterName\n"
            f"| order by TimeGenerated desc, Name asc, ContainerName asc\n"
            f"| take 200"
        )

        return self._run_query(query, minutes, f"get_resource_metrics(service={service_name})")

    def get_container_inventory(
        self,
        service_name: str,
        namespace: str | None = None,
        time_range_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch container image details from ContainerInventory.

        Returns image name, tag, creation time, and state for each container
        matching the service. Useful for detecting bad deployments or
        recent image changes.
        """
        if self._client is None:
            return []

        minutes = time_range_minutes or self._config.get("default_time_range_minutes", 60)
        ns = namespace or self._config.get("default_namespace", "chad")

        query = (
            f"let pods = KubePodInventory\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f'| where Namespace == "{ns}"\n'
            f'| where Name contains "{service_name}"\n'
            f"| distinct ContainerID;\n"
            f"ContainerInventory\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f"| where ContainerID in (pods)\n"
            f"| project TimeGenerated, Name, Image, ImageTag, ContainerState,"
            f" CreatedTime, StartedTime, FinishedTime, ExitCode\n"
            f"| summarize arg_max(TimeGenerated, *) by Name\n"
            f"| order by TimeGenerated desc"
        )

        return self._run_query(query, minutes, f"get_container_inventory(service={service_name})")

    def get_node_inventory(
        self,
        service_name: str,
        namespace: str | None = None,
        time_range_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch node status and conditions from KubeNodeInventory.

        Returns node name, status, allocatable CPU/memory, and conditions
        (MemoryPressure, DiskPressure, PIDPressure) for nodes hosting the
        service's pods. Detects node-level resource pressure causing evictions.
        """
        if self._client is None:
            return []

        minutes = time_range_minutes or self._config.get("default_time_range_minutes", 60)
        ns = namespace or self._config.get("default_namespace", "chad")

        query = (
            f"let nodes = KubePodInventory\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f'| where Namespace == "{ns}"\n'
            f'| where Name contains "{service_name}"\n'
            f"| distinct Computer;\n"
            f"KubeNodeInventory\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f"| where Computer in (nodes)\n"
            f"| summarize arg_max(TimeGenerated, *) by Computer\n"
            f"| project TimeGenerated, Computer, Status, KubeletVersion,"
            f" KubeProxyVersion, OperatingSystem, DockerVersion\n"
            f"| order by Computer asc"
        )

        return self._run_query(query, minutes, f"get_node_inventory(service={service_name})")

    def get_network_metrics(
        self,
        service_name: str,
        namespace: str | None = None,
        time_range_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch network TX/RX bytes from InsightsMetrics for a service.

        Returns bytes sent and received per pod, binned in 5-minute intervals.
        Detects network saturation or connection storms.
        """
        if self._client is None:
            return []

        minutes = time_range_minutes or self._config.get("default_time_range_minutes", 60)
        ns = namespace or self._config.get("default_namespace", "chad")

        query = (
            f"let nodes = KubePodInventory\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f'| where Namespace == "{ns}"\n'
            f'| where Name contains "{service_name}"\n'
            f"| distinct Computer;\n"
            f"InsightsMetrics\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f"| where Name in ('bytes_sent', 'bytes_recv')\n"
            f"| extend HostName = tostring(parse_json(Tags).hostName)\n"
            f"| where HostName in (nodes)\n"
            f"| summarize AvgValue=avg(Val), MaxValue=max(Val) by bin(TimeGenerated, 5m), HostName, Name\n"
            f"| order by TimeGenerated desc, HostName asc\n"
            f"| take 200"
        )

        return self._run_query(query, minutes, f"get_network_metrics(service={service_name})")

    def get_pod_restarts(
        self,
        service_name: str,
        namespace: str | None = None,
        time_range_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch Kubernetes pod restart count trends from KubePodInventory.

        Returns restart counts over time for each pod, enabling detection of
        crash-looping or recurring restarts.
        """
        if self._client is None:
            return []

        minutes = time_range_minutes or self._config.get("default_time_range_minutes", 60)
        ns = namespace or self._config.get("default_namespace", "chad")

        query = (
            f"KubePodInventory\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f'| where Namespace == "{ns}"\n'
            f'| where Name contains "{service_name}"\n'
            f"| project TimeGenerated, Name, PodStatus, ContainerStatus,"
            f" ContainerStatusReason, ContainerRestartCount, PodRestartCount\n"
            f"| summarize arg_max(TimeGenerated, *) by Name\n"
            f"| order by PodRestartCount desc"
        )

        return self._run_query(query, minutes, f"get_pod_restarts(service={service_name})")

    def get_oom_kill_events(
        self,
        service_name: str,
        namespace: str | None = None,
        time_range_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch OOMKilled events from KubeEvents.

        Returns out-of-memory container kill events with timestamps.
        Critical for confirming memory leak or resource exhaustion incidents.
        """
        if self._client is None:
            return []

        minutes = time_range_minutes or self._config.get("default_time_range_minutes", 60)
        ns = namespace or self._config.get("default_namespace", "chad")

        query = (
            f"KubeEvents\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f'| where Namespace == "{ns}"\n'
            f'| where Name contains "{service_name}"\n'
            f"| where Reason in ('OOMKilling', 'OOMKilled', 'Killing')\n"
            f"    or Message contains 'OOM' or Message contains 'out of memory'\n"
            f"| project TimeGenerated, Name, Reason, Message, KubeEventType, Count\n"
            f"| order by TimeGenerated desc\n"
            f"| take 50"
        )

        return self._run_query(query, minutes, f"get_oom_kill_events(service={service_name})")

    def get_autoscaler_events(
        self,
        service_name: str,
        namespace: str | None = None,
        time_range_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch Kubernetes HPA (Horizontal Pod Autoscaler) events from KubeEvents.

        Returns autoscaler failures, scale-up/down events, and metric
        computation errors. Detects scaling thrashing or inability to scale.
        """
        if self._client is None:
            return []

        minutes = time_range_minutes or self._config.get("default_time_range_minutes", 60)
        ns = namespace or self._config.get("default_namespace", "chad")

        query = (
            f"KubeEvents\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f'| where Namespace == "{ns}"\n'
            f"| where Reason in ('FailedComputeMetricsReplicas', 'FailedGetScale',"
            f" 'FailedRescale', 'SuccessfulRescale', 'ScalingLimited',"
            f" 'FailedGetResourceMetric', 'FailedGetExternalMetric')\n"
            f"    or ObjectKind == 'HorizontalPodAutoscaler'\n"
            f"| project TimeGenerated, Name, Reason, Message, KubeEventType, Count, ObjectKind\n"
            f"| order by TimeGenerated desc\n"
            f"| take 50"
        )

        return self._run_query(query, minutes, f"get_autoscaler_events(service={service_name})")

    def get_health_probe_failures(
        self,
        service_name: str,
        namespace: str | None = None,
        time_range_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch Kubernetes readiness/liveness probe failure events from KubeEvents.

        Returns health check failures that cause traffic to be diverted away
        from pods or pods to be restarted.
        """
        if self._client is None:
            return []

        minutes = time_range_minutes or self._config.get("default_time_range_minutes", 60)
        ns = namespace or self._config.get("default_namespace", "chad")

        query = (
            f"KubeEvents\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f'| where Namespace == "{ns}"\n'
            f'| where Name contains "{service_name}"\n'
            f"| where Reason in ('Unhealthy', 'FailedLiveness', 'FailedReadiness',"
            f" 'ProbeError', 'ContainerUnhealthy')\n"
            f"| project TimeGenerated, Name, Reason, Message, KubeEventType, Count\n"
            f"| order by TimeGenerated desc\n"
            f"| take 50"
        )

        return self._run_query(query, minutes, f"get_health_probe_failures(service={service_name})")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run_query(
        self, query: str, minutes: int, label: str
    ) -> list[dict[str, Any]]:
        try:
            result = self._client.query_workspace(  # type: ignore[union-attr]
                workspace_id=self._workspace_id,
                query=query,
                timespan=timedelta(minutes=minutes),
            )
            if result.status != LogsQueryStatus.SUCCESS or not result.tables:
                return []
            return _to_dicts(result.tables[0])
        except Exception as exc:
            logger.warning("ContainerLogsAdapter.%s failed: %s", label, exc)
            return []
