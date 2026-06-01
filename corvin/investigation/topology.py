"""Topology builder for V3.7 dependency visualization."""

from __future__ import annotations

from pydantic import BaseModel, Field

from corvin.core.contracts import InvestigationResult


class TopologyNode(BaseModel):
    id: str
    label: str
    kind: str
    status: str
    cpu_mcores: float | None = None
    cpu_request_mcores: float | None = None
    cpu_limit_mcores: float | None = None
    cpu_utilization_pct: float | None = None
    memory_mib: float | None = None
    memory_request_mib: float | None = None
    memory_limit_mib: float | None = None
    memory_utilization_pct: float | None = None
    phase: str | None = None
    ready_containers: int | None = None
    total_containers: int | None = None
    restart_count: int | None = None
    unhealthy_containers: int | None = None


class TopologyEdge(BaseModel):
    source: str
    target: str
    label: str | None = None


class ServiceTopology(BaseModel):
    nodes: list[TopologyNode] = Field(default_factory=list)
    edges: list[TopologyEdge] = Field(default_factory=list)


def _pod_health_metrics(pod: dict) -> dict[str, int | str | None]:
    """Compute pod health signals used by topology UI and API payloads."""
    phase_raw = pod.get("phase")
    phase = str(phase_raw).strip() if phase_raw not in (None, "") else None
    containers = pod.get("containers") if isinstance(pod.get("containers"), list) else []

    total_containers = len(containers)
    ready_containers = sum(1 for c in containers if isinstance(c, dict) and c.get("ready", False))
    unhealthy_containers = max(total_containers - ready_containers, 0)

    explicit_restart = pod.get("restart_count")
    if isinstance(explicit_restart, int):
        restart_count = explicit_restart
    else:
        restart_count = sum(
            int(c.get("restart_count", 0))
            for c in containers
            if isinstance(c, dict)
        )

    has_phase_issue = phase is not None and phase not in ("Running", "Succeeded")
    has_readiness_issue = unhealthy_containers > 0

    if has_phase_issue or has_readiness_issue:
        status = "hot"
    elif restart_count >= 3:
        status = "recovering"
    else:
        status = "high"

    return {
        "status": status,
        "phase": phase or "Unknown",
        "ready_containers": ready_containers,
        "total_containers": total_containers,
        "restart_count": restart_count,
        "unhealthy_containers": unhealthy_containers,
    }


def _coerce_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _safe_pct(used: float | None, limit: float | None) -> float | None:
    if used is None or limit is None or limit <= 0:
        return None
    return round((used / limit) * 100.0, 1)


def _resource_summary(rows: list[dict]) -> dict[str, float | None]:
    """Return usage, request, limit, and utilization summaries for cpu/memory."""
    cpu_usage_values: list[float] = []
    cpu_request_values: list[float] = []
    cpu_limit_values: list[float] = []
    memory_usage_values: list[float] = []
    memory_request_values: list[float] = []
    memory_limit_values: list[float] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        counter = str(
            row.get("CounterName")
            or row.get("counter_name")
            or row.get("countername")
            or ""
        )
        value = (
            _coerce_float(row.get("AvgValue"))
            or _coerce_float(row.get("avg_value"))
            or _coerce_float(row.get("CounterValue"))
            or _coerce_float(row.get("counter_value"))
            or _coerce_float(row.get("MaxValue"))
            or _coerce_float(row.get("max_value"))
        )
        if value is None:
            continue

        if "cpuUsageNanoCores" in counter:
            cpu_usage_values.append(value / 1_000_000.0)
        elif "cpuRequestNanoCores" in counter:
            cpu_request_values.append(value / 1_000_000.0)
        elif "cpuLimitNanoCores" in counter:
            cpu_limit_values.append(value / 1_000_000.0)
        elif "memoryWorkingSetBytes" in counter or "memoryRssBytes" in counter:
            memory_usage_values.append(value / (1024.0 * 1024.0))
        elif "memoryRequestBytes" in counter:
            memory_request_values.append(value / (1024.0 * 1024.0))
        elif "memoryLimitBytes" in counter:
            memory_limit_values.append(value / (1024.0 * 1024.0))

    cpu_mcores = round(sum(cpu_usage_values) / len(cpu_usage_values), 1) if cpu_usage_values else None
    cpu_request_mcores = round(sum(cpu_request_values) / len(cpu_request_values), 1) if cpu_request_values else None
    cpu_limit_mcores = round(sum(cpu_limit_values) / len(cpu_limit_values), 1) if cpu_limit_values else None
    memory_mib = round(sum(memory_usage_values) / len(memory_usage_values), 1) if memory_usage_values else None
    memory_request_mib = round(sum(memory_request_values) / len(memory_request_values), 1) if memory_request_values else None
    memory_limit_mib = round(sum(memory_limit_values) / len(memory_limit_values), 1) if memory_limit_values else None

    return {
        "cpu_mcores": cpu_mcores,
        "cpu_request_mcores": cpu_request_mcores,
        "cpu_limit_mcores": cpu_limit_mcores,
        "cpu_utilization_pct": _safe_pct(cpu_mcores, cpu_limit_mcores),
        "memory_mib": memory_mib,
        "memory_request_mib": memory_request_mib,
        "memory_limit_mib": memory_limit_mib,
        "memory_utilization_pct": _safe_pct(memory_mib, memory_limit_mib),
    }


def _resource_summary_by_pod(rows: list[dict]) -> dict[str, dict[str, float | None]]:
    """Return per-pod resource summaries keyed by pod name."""
    by_pod: dict[str, list[dict]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        pod_name = str(row.get("Name") or row.get("pod_name") or row.get("PodName") or "").strip()
        if not pod_name:
            continue
        by_pod.setdefault(pod_name, []).append(row)

    return {pod_name: _resource_summary(pod_rows) for pod_name, pod_rows in by_pod.items()}


def build_pod_topology_node(pod: dict) -> TopologyNode:
    """Build a pod topology node with status and judge-friendly metrics."""
    name = str(pod.get("name") or pod.get("pod") or "pod")
    metrics = _pod_health_metrics(pod)
    return TopologyNode(
        id=f"pod:{name}",
        label=name,
        kind="pod",
        status=str(metrics["status"]),
        cpu_mcores=_coerce_float(pod.get("cpu_mcores")),
        cpu_request_mcores=_coerce_float(pod.get("cpu_request_mcores")),
        cpu_limit_mcores=_coerce_float(pod.get("cpu_limit_mcores")),
        cpu_utilization_pct=_coerce_float(pod.get("cpu_utilization_pct")),
        memory_mib=_coerce_float(pod.get("memory_mib")),
        memory_request_mib=_coerce_float(pod.get("memory_request_mib")),
        memory_limit_mib=_coerce_float(pod.get("memory_limit_mib")),
        memory_utilization_pct=_coerce_float(pod.get("memory_utilization_pct")),
        phase=str(metrics["phase"]),
        ready_containers=int(metrics["ready_containers"]),
        total_containers=int(metrics["total_containers"]),
        restart_count=int(metrics["restart_count"]),
        unhealthy_containers=int(metrics["unhealthy_containers"]),
    )


def _inject_apim_topology(
    nodes: dict[str, TopologyNode],
    edges: dict[tuple[str, str, str | None], TopologyEdge],
) -> None:
    """Inject APIM gateway edges for any observed API nodes.

    This is generic: API nodes are inferred from evidence, then linked through a
    gateway node so topology visuals remain consistent across tenants.
    """
    api_nodes = [node_id for node_id, node in nodes.items() if node.kind == "api"]
    if not api_nodes:
        return

    gateway_id = "gateway:apim"
    nodes.setdefault(gateway_id, TopologyNode(
        id=gateway_id, label="APIM Gateway", kind="gateway", status="supporting"
    ))
    for api_node_id in api_nodes:
        edges[(gateway_id, api_node_id, "routes")] = TopologyEdge(
            source=gateway_id, target=api_node_id, label="routes"
        )


def build_service_topology(results: list[InvestigationResult]) -> ServiceTopology:
    # results arrive newest-first — keep only the most recent investigation per
    # service so pods reflect current AKS state, not a union of historical pods
    latest_by_service: dict[str, InvestigationResult] = {}
    for result in results:
        svc = result.request.service_name
        if svc not in latest_by_service:
            latest_by_service[svc] = result

    nodes: dict[str, TopologyNode] = {}
    edges: dict[tuple[str, str, str | None], TopologyEdge] = {}

    for result in latest_by_service.values():
        service_id = f"svc:{result.request.service_name}"
        service_resource = _resource_summary(result.evidence.container_resource_metrics)
        pod_resource_map = _resource_summary_by_pod(result.evidence.container_resource_metrics)
        nodes[service_id] = TopologyNode(
            id=service_id,
            label=result.request.service_name,
            kind="service",
            status=_service_status(result),
            cpu_mcores=service_resource["cpu_mcores"],
            cpu_request_mcores=service_resource["cpu_request_mcores"],
            cpu_limit_mcores=service_resource["cpu_limit_mcores"],
            cpu_utilization_pct=service_resource["cpu_utilization_pct"],
            memory_mib=service_resource["memory_mib"],
            memory_request_mib=service_resource["memory_request_mib"],
            memory_limit_mib=service_resource["memory_limit_mib"],
            memory_utilization_pct=service_resource["memory_utilization_pct"],
        )

        for pod in result.evidence.aks_context.get("pods", []):
            if not isinstance(pod, dict):
                continue
            pod_copy = dict(pod)
            pod_name = str(pod_copy.get("name") or pod_copy.get("pod") or "").strip()
            pod_resource = pod_resource_map.get(pod_name, {})
            for key, value in pod_resource.items():
                if value is not None:
                    pod_copy[key] = value
            pod_node = build_pod_topology_node(pod_copy)
            nodes[pod_node.id] = pod_node
            edges[(service_id, pod_node.id, "runs")] = TopologyEdge(source=service_id, target=pod_node.id, label="runs")

        for row in result.evidence.log_analytics_apim:
            api_id = str(row.get("ApiId") or row.get("api_id") or "").strip()
            if api_id:
                api_node = f"api:{api_id}"
                nodes.setdefault(api_node, TopologyNode(id=api_node, label=api_id, kind="api", status="observed"))
                edges[(api_node, service_id, "routes")] = TopologyEdge(source=api_node, target=service_id, label="routes")

    _inject_apim_topology(nodes, edges)
    return ServiceTopology(nodes=list(nodes.values()), edges=list(edges.values()))


def _service_status(result: InvestigationResult) -> str:
    if result.request.approval_status.value in {"approved", "pending"}:
        return "hot"
    if result.request.approval_status.value == "executed":
        return "recovering"
    if result.request.approval_status.value == "acknowledged":
        return "observed"
    return result.rca.confidence.value
