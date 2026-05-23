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
    memory_mib: float | None = None
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


def _resource_summary(rows: list[dict]) -> tuple[float | None, float | None]:
    """Return service-level cpu(mcores), memory(MiB) summary from metric rows."""
    cpu_values: list[float] = []
    memory_values: list[float] = []

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
            cpu_values.append(value / 1_000_000.0)
        elif "memoryWorkingSetBytes" in counter or "memoryRssBytes" in counter:
            memory_values.append(value / (1024.0 * 1024.0))

    cpu_mcores = round(sum(cpu_values) / len(cpu_values), 1) if cpu_values else None
    memory_mib = round(sum(memory_values) / len(memory_values), 1) if memory_values else None
    return cpu_mcores, memory_mib


def _resource_summary_by_pod(rows: list[dict]) -> dict[str, tuple[float | None, float | None]]:
    """Return per-pod cpu(mcores), memory(MiB) summary keyed by pod name."""
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
        memory_mib=_coerce_float(pod.get("memory_mib")),
        phase=str(metrics["phase"]),
        ready_containers=int(metrics["ready_containers"]),
        total_containers=int(metrics["total_containers"]),
        restart_count=int(metrics["restart_count"]),
        unhealthy_containers=int(metrics["unhealthy_containers"]),
    )


# ── Static APIM knowledge (from site.md / config) ─────────────────────────────
# Maps APIM ApiId → AKS service name. Kept here so the topology is always
# complete even when a particular investigation had no APIM log data.

_APIM_ROUTES: dict[str, str] = {
    "fundapis":    "fundapis",
    "partnerapis": "partnerapis",
    # fundsso is SSO and routes directly — no APIM front-door
}
def _inject_apim_topology(
    nodes: dict[str, TopologyNode],
    edges: dict[tuple[str, str, str | None], TopologyEdge],
) -> None:
    """Inject the APIM gateway, known API routes, and PingFederate into the topology.

    APIM front-door:
        APIM Gateway → fundapis API → svc:fundapis
        APIM Gateway → partnerapis API → svc:partnerapis

    fundsso routes DIRECT (no APIM) but depends on PingFederate for SSO federation:
        svc:fundsso → backend:pingfederate
    """
    if not any(k.startswith("svc:") for k in nodes):
        return

    gateway_id = "gateway:apim"
    nodes[gateway_id] = TopologyNode(
        id=gateway_id, label="APIM Gateway", kind="gateway", status="supporting"
    )

    for api_id, svc_name in _APIM_ROUTES.items():
        service_id = f"svc:{svc_name}"
        if service_id not in nodes:
            continue
        api_node_id = f"api:{api_id}"
        nodes.setdefault(
            api_node_id,
            TopologyNode(id=api_node_id, label=api_id, kind="api", status="observed"),
        )
        edges[(gateway_id, api_node_id, "routes")] = TopologyEdge(
            source=gateway_id, target=api_node_id, label="routes"
        )
        edges[(api_node_id, service_id, "routes")] = TopologyEdge(
            source=api_node_id, target=service_id, label="routes"
        )

    # PingFederate — external IdP for fundsso
    fundsso_id = "svc:fundsso"
    if fundsso_id in nodes:
        pf_id = "backend:pingfederate"
        nodes.setdefault(
            pf_id,
            TopologyNode(id=pf_id, label="PingFederate SSO", kind="backend", status="supporting"),
        )
        edges[(fundsso_id, pf_id, "depends-on")] = TopologyEdge(
            source=fundsso_id, target=pf_id, label="depends-on"
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
        cpu_mcores, memory_mib = _resource_summary(result.evidence.container_resource_metrics)
        pod_resource_map = _resource_summary_by_pod(result.evidence.container_resource_metrics)
        nodes[service_id] = TopologyNode(
            id=service_id,
            label=result.request.service_name,
            kind="service",
            status=_service_status(result),
            cpu_mcores=cpu_mcores,
            memory_mib=memory_mib,
        )

        for pod in result.evidence.aks_context.get("pods", []):
            if not isinstance(pod, dict):
                continue
            pod_copy = dict(pod)
            pod_name = str(pod_copy.get("name") or pod_copy.get("pod") or "").strip()
            pod_cpu, pod_mem = pod_resource_map.get(pod_name, (None, None))
            if pod_cpu is not None:
                pod_copy["cpu_mcores"] = pod_cpu
            if pod_mem is not None:
                pod_copy["memory_mib"] = pod_mem
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
