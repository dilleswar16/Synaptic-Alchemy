"""Structured outputs of the knowledge features: document digest and topology builder."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from keigan.ai.llm_gateway import register_mock_response

TopologyNodeType = Literal["service", "data_store", "external", "hardware", "queue", "client", "mainframe", "saas"]


class DocumentDigestResult(BaseModel):
    """Structured summary of one knowledge document (shown beside the file and used for grounding)."""

    purpose_summary: str = Field(description="Two or three sentences: what the described system or document is for.")
    key_facts: list[str] = Field(default_factory=list, description="Short factual statements an on-call engineer needs (hosting, entry points, data stores).")
    outbound_dependencies: list[str] = Field(default_factory=list, description="Systems the described component calls, with timeouts or retries when stated.")
    known_failure_modes: list[str] = Field(default_factory=list, description="Failure modes and their symptoms, only when the document states them.")
    operational_commands: list[str] = Field(default_factory=list, description="Operational commands or procedures mentioned in the document.")
    mentioned_service_names: list[str] = Field(default_factory=list, description="Names of services or systems mentioned.")
    log_and_telemetry_hints: list[str] = Field(default_factory=list, description="Log fields, correlation ids, role names or tables to search.")


class TopologyNodeResult(BaseModel):
    node_key: str = Field(description="Stable lower-case key, unique in the graph.")
    label: str
    node_type: TopologyNodeType = "service"
    service_id: str | None = Field(default=None, description="Keigan service id when the node is one of the listed services, otherwise null.")
    technology: str = ""
    description: str = ""
    criticality: str = "tier_2"


class TopologyEdgeResult(BaseModel):
    source_node_key: str
    target_node_key: str
    relationship: str = Field(default="calls", description="calls | reads_from | writes_to | publishes_to | hosts | depends_on")
    protocol: str = ""
    description: str = ""


class TopologyResult(BaseModel):
    nodes: list[TopologyNodeResult] = Field(default_factory=list)
    edges: list[TopologyEdgeResult] = Field(default_factory=list)
    narrative_markdown: str = Field(default="", description="Keigan's written understanding of the application (Markdown, under 300 words).")
    uncertainties: list[str] = Field(default_factory=list, description="Things Keigan could not confirm and a reviewer should check.")


# ── Offline (LLM_PROVIDER=mock) responses ──────────────────────────────────────
def _markdown_section_items(markdown_text: str, heading_keywords: tuple[str, ...], maximum_items: int = 6) -> list[str]:
    """Bullet lines or table rows under the first heading that contains one of the keywords."""
    collected_items: list[str] = []
    is_inside_section = False
    for line in markdown_text.splitlines():
        stripped_line = line.strip()
        if stripped_line.startswith("#"):
            is_inside_section = any(keyword in stripped_line.lower() for keyword in heading_keywords)
            continue
        if not is_inside_section or not stripped_line:
            continue
        if stripped_line.startswith(("-", "*")):
            collected_items.append(stripped_line.lstrip("-* ").strip())
        elif stripped_line.startswith("|") and not set(stripped_line) <= set("|- :"):
            cells = [cell.strip() for cell in stripped_line.strip("|").split("|")]
            if cells and cells[0].lower() not in ("name", "endpoint", "system", "setting", "symptom", "dependency", "method"):
                collected_items.append(" — ".join(cell for cell in cells[:3] if cell))
        if len(collected_items) >= maximum_items:
            break
    return collected_items


def _build_mock_document_digest(_output_schema: type[BaseModel], prompt_sections: list) -> DocumentDigestResult:  # noqa: ANN001
    document_text = next((section.content for section in prompt_sections if getattr(section, "is_untrusted", False)), "")
    purpose_items = _markdown_section_items(document_text, ("purpose",), 3)
    first_paragraph = next((line.strip() for line in document_text.splitlines() if line.strip() and not line.strip().startswith(("#", "|", "-", "`", ">"))), "")
    return DocumentDigestResult(
        purpose_summary=" ".join(purpose_items) or first_paragraph[:400] or "Simulated digest (LLM_PROVIDER=mock): the document describes how the component runs.",
        key_facts=_markdown_section_items(document_text, ("runtime", "hosting", "entry points", "data stores")),
        outbound_dependencies=_markdown_section_items(document_text, ("outbound dependencies", "dependencies")),
        known_failure_modes=_markdown_section_items(document_text, ("failure",)),
        operational_commands=_markdown_section_items(document_text, ("operational commands", "commands")),
        mentioned_service_names=[],
        log_and_telemetry_hints=_markdown_section_items(document_text, ("logging", "telemetry")),
    )


register_mock_response("knowledge_document_digest", _build_mock_document_digest)
