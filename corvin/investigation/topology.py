"""Topology builder for V3.7 dependency visualization."""

from __future__ import annotations

from pydantic import BaseModel, Field

from corvin.core.contracts import InvestigationResult


class TopologyNode(BaseModel):
    id: str
    label: str
    kind: str
    status: str


class TopologyEdge(BaseModel):
    source: str
    target: str
    label: str | None = None


class ServiceTopology(BaseModel):
    nodes: list[TopologyNode] = Field(default_factory=list)
    edges: list[TopologyEdge] = Field(default_factory=list)


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
    """Inject the APIM gateway and known API routes in front of the AKS services."""
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
        nodes[service_id] = TopologyNode(
            id=service_id,
            label=result.request.service_name,
            kind="service",
            status=_service_status(result),
        )

        for pod in result.evidence.aks_context.get("pods", []):
            if not isinstance(pod, dict):
                continue
            name = str(pod.get("name") or pod.get("pod") or "pod")
            pod_id = f"pod:{name}"
            nodes.setdefault(pod_id, TopologyNode(id=pod_id, label=name, kind="pod", status="supporting"))
            edges[(service_id, pod_id, "runs")] = TopologyEdge(source=service_id, target=pod_id, label="runs")

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
    return result.rca.confidence.value