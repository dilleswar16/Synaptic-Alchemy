"""
Investigation engine system prompt builder.

Assembles the LLM system prompt for a Corvin investigation by layering:

  1. ## Site Knowledge       — static infra facts from knowledge/site.md
  2. ## Relevant Runbook     — keyword-matched runbook(s) for the alert type
  3. ## Learnings from Past Incidents — accumulated incident patterns

Empty sections are skipped entirely (no header emitted for empty content).
The assembled prompt is deterministic and can be tested without an LLM.

Usage:
    from corvin.investigation.prompt_builder import PromptBuilder
    from corvin.core.contracts import InvestigationRequest

    builder = PromptBuilder()
    system_prompt = builder.build(request)
"""

from __future__ import annotations

from corvin.core.contracts import InvestigationRequest
from corvin.core.knowledge_loader import KnowledgeLoader


class PromptBuilder:
    """Builds the LLM system prompt for an investigation from knowledge layer sources."""

    def __init__(self, knowledge_loader: KnowledgeLoader | None = None) -> None:
        self._loader = knowledge_loader or KnowledgeLoader()

    def _build_alert_text(self, request: InvestigationRequest) -> str:
        """Combine normalized and raw alert fields for runbook matching."""
        parts: list[str] = [request.service_name, request.description]

        raw_payload = request.raw_payload if isinstance(request.raw_payload, dict) else {}
        data = raw_payload.get("data", {}) if isinstance(raw_payload.get("data", {}), dict) else {}
        essentials = data.get("essentials", {}) if isinstance(data.get("essentials", {}), dict) else {}

        for value in (
            essentials.get("alertRule"),
            essentials.get("description"),
            essentials.get("alertName"),
            data.get("title"),
            raw_payload.get("title"),
        ):
            if isinstance(value, str):
                parts.append(value)

        unique_parts: list[str] = []
        seen: set[str] = set()
        for part in parts:
            normalised = part.strip()
            if not normalised:
                continue
            key = normalised.lower()
            if key in seen:
                continue
            seen.add(key)
            unique_parts.append(normalised)

        return " ".join(unique_parts)

    def build(self, request: InvestigationRequest) -> str:
        """
        Assemble and return the full system prompt string for the given request.

        Sections are only included when they contain non-empty content.

        Args:
            request: The normalized InvestigationRequest driving the investigation.

        Returns:
            A string suitable for use as an LLM system prompt.
        """
        sections: list[str] = []

        # ── Site knowledge ────────────────────────────────────────────────────
        site_knowledge = self._loader.load_site_knowledge()
        if site_knowledge.strip():
            sections.append(f"## Site Knowledge\n\n{site_knowledge.strip()}")

        # ── Runbook matching ──────────────────────────────────────────────────
        alert_text = self._build_alert_text(request)
        runbooks = self._loader.load_matching_runbooks(alert_text)
        if runbooks:
            runbook_content = "\n\n---\n\n".join(rb.strip() for rb in runbooks)
            runbook_section = (
                "## Relevant Runbook\n\n"
                "**Note: The following runbook takes precedence over generic investigation "
                "steps.  Follow it as the primary investigation guide.**\n\n"
                f"{runbook_content}"
            )
            sections.append(runbook_section)

        # ── Learnings ─────────────────────────────────────────────────────────
        learnings = self._loader.load_learnings()
        if learnings.strip():
            sections.append(f"## Learnings from Past Incidents\n\n{learnings.strip()}")

        return "\n\n".join(sections)
