"""
Hypothesis Service — Feature 8: Root Cause Debate Mode.

Generates N competing root-cause hypotheses from the evidence bundle collected
for a completed investigation.  Each hypothesis is distinct by design:
  - h1: infrastructure angle (resource pressure, node, OOM)
  - h2: code / config change angle (deployment, env variable, schema)
  - h3: upstream dependency angle (downstream service, 3rd-party API, DNS)

The SRE reviews all three and selects the winner via
POST /investigations/{id}/select-hypothesis.
The winner's root_cause drives a fresh fix strategy generation.

All thresholds and feature flags are read from
config/policies/investigation.yaml under the ``debate_mode`` key.
No customer-specific strings appear anywhere in this module.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import litellm

litellm.drop_params = True

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import EvidenceBundle, InvestigationResult, RCAHypothesis

_log = logging.getLogger(__name__)


_SYSTEM_PROMPT = """\
You are Corvin's hypothesis generation engine.

Given an incident investigation result (service, evidence, initial RCA), produce
EXACTLY {count} distinct, competing root-cause hypotheses.

Rules:
- Each hypothesis MUST take a genuinely different angle:
  * h1: infrastructure angle (CPU/memory pressure, node failure, OOM, resource limits)
  * h2: code/config change angle (recent deployment, env variable change, schema migration)
  * h3: upstream/dependency angle (downstream service outage, 3rd-party API, DNS, network)
- Do NOT converge hypotheses. If the evidence strongly favours one angle, still
  generate plausible alternatives for the others.
- confidence_score: float 0.0–1.0 reflecting how much the evidence supports this hypothesis
- evidence_strength_pct: int 0–100 for UI progress bar (may differ from confidence_score)
- supporting_signals: 2–5 concise bullet strings each ≤80 chars
- refuting_signals: 1–3 concise bullet strings each ≤80 chars

Output ONLY valid JSON matching this schema (no fences, no commentary):
{
  "hypotheses": [
    {
      "id": "h1",
      "title": "Short label ≤60 chars",
      "root_cause": "Full technical explanation of this hypothesis",
      "evidence_ids": ["log_analytics_apim", "aks_context"],
      "confidence_score": 0.75,
      "evidence_strength_pct": 75,
      "supporting_signals": ["Signal 1", "Signal 2"],
      "refuting_signals": ["Counter-signal 1"]
    }
  ]
}
"""


class HypothesisService:
    """Generates competing RCA hypotheses for Debate Mode (Feature 8).

    Usage:
        svc = HypothesisService()
        hypotheses = svc.generate(result)   # returns list[RCAHypothesis]
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._llm_config = config if config is not None else load_config("models/llm", get_env())
        self._policy = load_config("policies/investigation", get_env())

    # ── Public API ──────────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        """Return True when debate_mode.enabled=true in investigation.yaml."""
        return bool(self._policy.get("debate_mode", {}).get("enabled", True))

    def generate(self, result: InvestigationResult) -> list[RCAHypothesis]:
        """Generate N competing hypotheses from an InvestigationResult.

        Returns an empty list when the feature is disabled or LLM fails.
        Never raises.
        """
        if not self.is_enabled():
            _log.debug("HypothesisService: debate_mode.enabled=false — skipping")
            return []

        count: int = int(self._policy.get("debate_mode", {}).get("hypothesis_count", 3))
        min_signals: int = int(self._policy.get("debate_mode", {}).get("min_evidence_signals", 2))

        context = self._build_context(result)
        system = _SYSTEM_PROMPT.format(count=count)
        model = self._llm_config.get("fallback_model") or self._llm_config.get("model", "azure/gpt-4.1-mini")

        try:
            resp = litellm.completion(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": context},
                ],
                temperature=0.4,  # slightly creative so hypotheses genuinely differ
                max_tokens=3000,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or ""
            parsed = json.loads(raw)
            return self._parse_and_validate(parsed, min_signals, count)
        except Exception as exc:
            _log.warning("HypothesisService: LLM call failed — returning empty list: %s", exc)
            return []

    # ── Private helpers ─────────────────────────────────────────────────────

    def _build_context(self, result: InvestigationResult) -> str:
        ev = result.evidence
        parts = [
            f"Service: {result.request.service_name}",
            f"Environment: {result.request.environment}",
            f"Alert / Description: {result.request.description}",
            "",
            "=== Initial RCA (challenge this, don't just repeat it) ===",
            f"Root Cause: {result.rca.root_cause}",
            f"Summary: {result.rca.summary}",
            f"Confidence: {result.rca.confidence.value}",
            f"Contributing Factors: {json.dumps(result.rca.contributing_factors)}",
            f"Evidence References: {json.dumps(result.rca.evidence_references)}",
            "",
            "=== Evidence Counts ===",
            f"APIM logs: {len(ev.log_analytics_apim)}",
            f"Container resource metrics: {len(ev.container_resource_metrics)}",
            f"Container inventory: {len(ev.container_inventory)}",
            f"Pod restarts: {len(ev.pod_restarts)}",
            f"OOM kill events: {len(ev.oom_kill_events)}",
            f"Autoscaler events: {len(ev.autoscaler_events)}",
            f"Health probe failures: {len(ev.health_probe_failures)}",
            f"AKS context keys: {list((ev.aks_context or {}).keys())[:10]}",
        ]
        # Include a small evidence sample so the LLM has something concrete
        if ev.log_analytics_apim:
            parts.append(f"\nAPIM sample (first 3): {json.dumps(ev.log_analytics_apim[:3], default=str)[:800]}")
        if ev.container_resource_metrics:
            parts.append(f"\nResource metric sample (first 2): {json.dumps(ev.container_resource_metrics[:2], default=str)[:600]}")
        return "\n".join(parts)

    def _parse_and_validate(
        self,
        parsed: dict[str, Any],
        min_signals: int,
        expected_count: int,
    ) -> list[RCAHypothesis]:
        raw_list = parsed.get("hypotheses", [])
        if not isinstance(raw_list, list):
            _log.warning("HypothesisService: LLM returned non-list hypotheses field")
            return []

        result: list[RCAHypothesis] = []
        expected_ids = [f"h{i}" for i in range(1, expected_count + 1)]

        for i, raw in enumerate(raw_list[:expected_count]):
            try:
                h = RCAHypothesis(
                    id=raw.get("id", expected_ids[i] if i < len(expected_ids) else f"h{i+1}"),
                    title=str(raw.get("title", "Unknown"))[:60],
                    root_cause=str(raw.get("root_cause", "")),
                    evidence_ids=raw.get("evidence_ids", []),
                    confidence_score=float(raw.get("confidence_score", 0.5)),
                    evidence_strength_pct=int(raw.get("evidence_strength_pct", 50)),
                    supporting_signals=raw.get("supporting_signals", []),
                    refuting_signals=raw.get("refuting_signals", []),
                )
                # Apply min_evidence_signals gate
                if len(h.supporting_signals) < min_signals:
                    _log.debug(
                        "HypothesisService: hypothesis %s has only %d supporting signals (min=%d), padding",
                        h.id, len(h.supporting_signals), min_signals,
                    )
                    # Pad with a placeholder so the hypothesis is still surfaced
                    while len(h.supporting_signals) < min_signals:
                        h.supporting_signals.append("(insufficient specific signals from evidence)")
                result.append(h)
            except Exception as exc:
                _log.warning("HypothesisService: failed to parse hypothesis %d: %s", i, exc)

        return result
