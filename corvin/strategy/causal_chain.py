"""
Causal Chain Generator — F4 Agentic Feature

Produces a directed cause-effect chain from a completed InvestigationResult.
The LLM analyzes the RCA and evidence to identify the sequence of events
that led to the incident, outputting a structured DAG suitable for rendering
as a Mermaid flowchart on the frontend.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import litellm

litellm.drop_params = True

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import InvestigationResult

_log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are Corvin's causal reasoning engine. Given an incident investigation result,
produce a directed causal chain showing the sequence of events from root cause
to customer-visible impact.

Rules:
- Output ONLY valid JSON matching the schema below. No fences, no commentary.
- Each node has: id (string), label (short ≤60 chars), category (one of: trigger, failure, cascade, impact)
- Each edge has: from_id, to_id, label (optional short description of causal link)
- The chain should be 4-8 nodes (not too granular, not too abstract)
- Start from the root cause and flow toward business/user impact
- Use evidence references where possible

Output schema:
{
  "nodes": [{"id": "n1", "label": "...", "category": "trigger|failure|cascade|impact"}],
  "edges": [{"from_id": "n1", "to_id": "n2", "label": "..."}],
  "summary": "One-line narrative of the causal chain"
}
"""


class CausalChainGenerator:
    """Generates a causal reasoning graph from a completed investigation."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config if config is not None else load_config("models/llm", get_env())

    def generate(self, result: InvestigationResult) -> dict[str, Any]:
        """Produce causal chain JSON from an InvestigationResult."""
        context = self._build_context(result)
        model = self._config.get("model", "azure/gpt-4.1-mini")
        fallback = self._config.get("fallback_model", "azure/gpt-4.1-mini")

        for attempt_model in (model, fallback):
            try:
                response = litellm.completion(
                    model=attempt_model,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": context},
                    ],
                    temperature=0.1,
                    max_tokens=2048,
                    reasoning_effort=self._config.get("reasoning_effort", "medium"),
                )
                raw = response.choices[0].message.content.strip()
                # Strip markdown fences if model wraps output
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                chain = json.loads(raw)
                self._validate(chain)
                return chain
            except Exception as exc:
                _log.warning("Causal chain generation failed with %s: %s", attempt_model, exc)
                continue

        # Fallback: deterministic minimal chain from RCA
        return self._fallback_chain(result)

    def _build_context(self, result: InvestigationResult) -> str:
        parts = [
            f"Service: {result.request.service_name}",
            f"Environment: {result.request.environment}",
            f"Description: {result.request.description}",
            f"\nRoot Cause: {result.rca.root_cause}",
            f"Summary: {result.rca.summary}",
            f"Contributing Factors: {json.dumps(result.rca.contributing_factors)}",
            f"Confidence: {result.rca.confidence}",
            f"Evidence References: {json.dumps(result.rca.evidence_references)}",
        ]
        if result.fix_strategy.actions:
            parts.append(f"\nFix Actions: {json.dumps([a.title for a in result.fix_strategy.actions])}")
        return "\n".join(parts)

    def _validate(self, chain: dict[str, Any]) -> None:
        """Basic structural validation."""
        if "nodes" not in chain or "edges" not in chain:
            raise ValueError("Missing 'nodes' or 'edges' in causal chain output")
        node_ids = {n["id"] for n in chain["nodes"]}
        for edge in chain["edges"]:
            if edge["from_id"] not in node_ids or edge["to_id"] not in node_ids:
                raise ValueError(f"Edge references unknown node: {edge}")

    def _fallback_chain(self, result: InvestigationResult) -> dict[str, Any]:
        """Deterministic fallback when LLM fails."""
        return {
            "nodes": [
                {"id": "n1", "label": "Root Cause Detected", "category": "trigger"},
                {"id": "n2", "label": result.rca.root_cause[:60], "category": "failure"},
                {"id": "n3", "label": "Service Degradation", "category": "cascade"},
                {"id": "n4", "label": "User Impact", "category": "impact"},
            ],
            "edges": [
                {"from_id": "n1", "to_id": "n2", "label": "triggered"},
                {"from_id": "n2", "to_id": "n3", "label": "caused"},
                {"from_id": "n3", "to_id": "n4", "label": "resulted in"},
            ],
            "summary": result.rca.summary,
        }
