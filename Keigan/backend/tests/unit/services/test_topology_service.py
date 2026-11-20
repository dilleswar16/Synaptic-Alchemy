"""keigan/services/topology_service.py: the AI-built graph is validated and its text sanitised (V8)."""

from __future__ import annotations

from types import SimpleNamespace

from keigan.ai.knowledge_ai_schemas import TopologyEdgeResult, TopologyNodeResult, TopologyResult
from keigan.services.topology_service import TopologyService

HOSTILE = "[docs](https://evil.example/d) ![p](https://evil.example/p.png)"


def test_node_edge_and_uncertainty_text_from_the_model_is_sanitised() -> None:
    service = SimpleNamespace(service_id="s1", service_name="claims-api", service_type="api", service_description="", criticality_tier="tier_1")
    result = TopologyResult(
        nodes=[TopologyNodeResult(node_key="claims-api", label="claims-api", service_id="s1"), TopologyNodeResult(node_key="ext", label=f"Partner {HOSTILE}", node_type="external", description=HOSTILE, technology=HOSTILE)],
        edges=[TopologyEdgeResult(source_node_key="claims-api", target_node_key="ext", description=HOSTILE, protocol="HTTPS")],
        narrative_markdown=HOSTILE, uncertainties=[HOSTILE],
    )
    graph = TopologyService._validated_graph(result, [service])  # type: ignore[arg-type]
    assert "evil.example/" not in str(graph).replace("`", "") or "](https://evil.example" not in str(graph)
    assert "](https://evil.example" not in str(graph) and "![" not in str(graph)


def test_the_narrative_is_sanitised_by_the_same_step() -> None:
    cleaned = TopologyService._sanitized_result(TopologyResult(narrative_markdown=HOSTILE))  # type: ignore[attr-defined]
    assert "](https://evil.example" not in cleaned.narrative_markdown and "![" not in cleaned.narrative_markdown
