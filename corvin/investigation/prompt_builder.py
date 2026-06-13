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

from typing import TYPE_CHECKING

from corvin.core.contracts import InvestigationRequest
from corvin.core.knowledge_loader import KnowledgeLoader

if TYPE_CHECKING:
    from corvin.storage.repository import InvestigationRepository


class PromptBuilder:
    """Builds the LLM system prompt for an investigation from knowledge layer sources."""

    def __init__(
        self,
        knowledge_loader: KnowledgeLoader | None = None,
        repository: InvestigationRepository | None = None,
    ) -> None:
        self._loader = knowledge_loader or KnowledgeLoader()
        self._repository = repository

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
        site_knowledge = self._loader.load_site_knowledge(service_name=request.service_name)
        if site_knowledge.strip():
            sections.append(f"## Site Knowledge\n\n{site_knowledge.strip()}")

        # ── Runbook matching ──────────────────────────────────────────────────
        alert_text = self._build_alert_text(request)
        runbooks = self._loader.load_matching_runbooks(alert_text, service_name=request.service_name)
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

        # ── Predictive penalties (feedback loop) ──────────────────────────────
        try:
            from corvin.triggers.prediction_penalty import (
                is_penalty_feature_enabled,
                load_penalties_for_service,
            )
            penalties = (
                load_penalties_for_service(request.service_name, limit=5)
                if is_penalty_feature_enabled()
                else []
            )
            if penalties:
                penalty_lines: list[str] = []
                for p in penalties:
                    penalty_lines.append(
                        f"- **{p['penalty_type'].upper()}** ({p['alert_type']}): "
                        f"{p['pattern_description'][:200]}"
                    )
                sections.append(
                    "## Predictive Analysis Penalties\n\n"
                    "The following patterns were previously MISSED or INSUFFICIENTLY predicted. "
                    "Pay special attention to these failure modes — ensure your RCA addresses "
                    "whether this incident matches a known missed pattern.\n\n"
                    + "\n".join(penalty_lines)
                )
        except Exception:
            pass  # Non-fatal: penalties are optional context

        # ── Operator context (human-provided description) ─────────────────────
        _defaults = {"manual investigation", "streaming investigation", ""}
        desc = (request.description or "").strip()
        if desc.lower() not in _defaults:
            sections.append(
                "## Operator Context\n\n"
                "**The operator has provided the following context about what they are observing. "
                "Use this as your primary anchor for the investigation — it represents what the human "
                "on-call engineer is actually seeing right now.**\n\n"
                f"{desc}"
            )

        # ── Past incidents (incident memory) ──────────────────────────────────
        if self._repository is not None:
            past = self._repository.get_similar_incidents(
                service_name=request.service_name,
                environment=request.environment,
                n=3,
            )
            if past:
                lines: list[str] = []
                for inc in past:
                    date_str = inc["completed_at"][:10]
                    confidence = inc["confidence"].upper()
                    root_cause = inc["root_cause"].strip()
                    lines.append(
                        f"- [{date_str}] {inc['service_name']} — {confidence} confidence\n"
                        f"  Root cause: {root_cause}"
                    )
                sections.append(
                    "## Similar Past Incidents (same service)\n\n"
                    "Use these historical findings to identify recurrences or patterns. "
                    "If the current evidence points to the same root cause, say so explicitly.\n\n"
                    + "\n\n".join(lines)
                )

        return "\n\n".join(sections)
