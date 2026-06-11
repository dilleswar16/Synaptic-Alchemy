"""
Incident Communication Drafts — F7 Agentic Feature

Generates audience-appropriate incident communication drafts at three levels:
- executive: High-level business impact summary for C-suite / VP stakeholders
- internal: Technical status update for engineering teams
- public: Customer-facing status page update

Each draft is tone-calibrated and context-aware, drawing from the investigation
result to produce accurate, timely communication without manual drafting.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

import litellm

litellm.drop_params = True

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import InvestigationResult
from corvin.core.prompt_registry import get_prompt_registry

_log = logging.getLogger(__name__)

AudienceLevel = Literal["executive", "internal", "public"]


class CommsDraftGenerator:
    """Generates audience-calibrated incident communications."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config if config is not None else load_config("models/llm", get_env())

    def generate(
        self,
        result: InvestigationResult,
        audience: AudienceLevel = "internal",
    ) -> dict[str, Any]:
        """Generate a communication draft for the given audience level."""
        context = self._build_context(result)
        model = self._config.get("fallback_model") or self._config.get("model")
        if not model:
            raise ValueError("models/llm.yaml must define 'model' or 'fallback_model'")

        try:
            response = litellm.completion(
                model=model,
                messages=[
                    {"role": "system", "content": get_prompt_registry().get(f"comms_draft_{audience}")},
                    {"role": "user", "content": context},
                ],
                temperature=0.3,
                max_tokens=1024,
            )
            draft = response.choices[0].message.content.strip()
            return {
                "audience": audience,
                "draft": draft,
                "service_name": result.request.service_name,
                "environment": result.request.environment,
                "generated_from": result.request_id,
            }
        except Exception as exc:
            _log.error("Comms draft generation failed: %s", exc)
            return {
                "audience": audience,
                "draft": self._fallback_draft(result, audience),
                "service_name": result.request.service_name,
                "environment": result.request.environment,
                "generated_from": result.request_id,
                "fallback": True,
            }

    def generate_all(self, result: InvestigationResult) -> list[dict[str, Any]]:
        """Generate drafts for all three audience levels."""
        return [self.generate(result, level) for level in ("executive", "internal", "public")]

    def _build_context(self, result: InvestigationResult) -> str:
        parts = [
            f"Service: {result.request.service_name}",
            f"Environment: {result.request.environment}",
            f"Incident Priority: {result.request.incident_priority}",
            f"Trigger: {result.request.trigger_source}",
            f"Description: {result.request.description}",
            f"\nRoot Cause: {result.rca.root_cause}",
            f"RCA Summary: {result.rca.summary}",
            f"Confidence: {result.rca.confidence}",
            f"Contributing Factors: {json.dumps(result.rca.contributing_factors)}",
            f"\nFix Strategy: {result.fix_strategy.summary}",
        ]
        if result.fix_strategy.actions:
            actions = [f"- {a.title} ({a.action_type})" for a in result.fix_strategy.actions]
            parts.append("Actions:\n" + "\n".join(actions))
        return "\n".join(parts)

    def _fallback_draft(self, result: InvestigationResult, audience: AudienceLevel) -> str:
        svc = result.request.service_name
        env = result.request.environment
        if audience == "executive":
            return f"[{env.upper()}] {svc} — Incident under investigation. Root cause identified: {result.rca.root_cause[:100]}. Team is implementing remediation."
        elif audience == "public":
            return f"We are aware of an issue affecting some services. Our team is actively working on a resolution. We will provide an update shortly."
        else:
            return f"[{env}] {svc} — RCA: {result.rca.root_cause[:200]}. Fix: {result.fix_strategy.summary[:200]}."
