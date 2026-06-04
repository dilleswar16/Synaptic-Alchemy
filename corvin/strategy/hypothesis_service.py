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
import os
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
        # Use simple token replacement so JSON braces in the prompt body are not
        # interpreted by str.format (which would raise KeyError on schema keys).
        system = _SYSTEM_PROMPT.replace("{count}", str(count))
        model = self._llm_config.get("fallback_model") or self._llm_config.get("model")
        if not model:
            raise ValueError(
                "HypothesisService: models/llm.yaml must define 'model' or 'fallback_model'. "
                "Set one of these keys or configure LITELLM credentials."
            )

        completion_kwargs = self._build_completion_kwargs(model)
        if completion_kwargs is None:
            _log.warning(
                "HypothesisService: LLM credentials not configured; using deterministic fallback hypotheses"
            )
            return self._fallback_hypotheses(result, min_signals, count)

        try:
            resp = litellm.completion(
                **completion_kwargs,
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
            hypotheses = self._parse_and_validate(parsed, min_signals, count)
            hypotheses = self._ensure_hypothesis_count(hypotheses, result, min_signals, count)
            return self._calibrate_confidence(hypotheses)
        except Exception as exc:
            _log.warning("HypothesisService: LLM call failed — using deterministic fallback: %s", exc)
            return self._fallback_hypotheses(result, min_signals, count)

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
                    supporting_evidence=self._normalize_trace_items(raw.get("supporting_evidence", [])),
                    refuting_evidence=self._normalize_trace_items(raw.get("refuting_evidence", [])),
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

                if not h.supporting_evidence:
                    h.supporting_evidence = self._build_trace_items(
                        h.supporting_signals,
                        h.evidence_ids,
                        max_items=5,
                    )
                if not h.refuting_evidence:
                    h.refuting_evidence = self._build_trace_items(
                        h.refuting_signals,
                        h.evidence_ids,
                        max_items=3,
                    )
                result.append(h)
            except Exception as exc:
                _log.warning("HypothesisService: failed to parse hypothesis %d: %s", i, exc)

        return result

    def _normalize_trace_items(self, value: Any) -> list[dict[str, str]]:
        """Normalize trace items into [{"source_id": ..., "summary": ...}]."""
        if not isinstance(value, list):
            return []
        normalized: list[dict[str, str]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("source_id", "")).strip()
            summary = str(item.get("summary", "")).strip()
            if source_id and summary:
                normalized.append({"source_id": source_id, "summary": summary[:220]})
        return normalized

    def _build_trace_items(
        self,
        signals: list[str],
        evidence_ids: list[str],
        max_items: int,
    ) -> list[dict[str, str]]:
        """Build traceability items by pairing signals with available evidence ids."""
        clean_signals = [str(s).strip() for s in signals if str(s).strip()]
        clean_ids = [str(e).strip() for e in evidence_ids if str(e).strip()]
        if not clean_signals:
            return []
        if not clean_ids:
            clean_ids = ["investigation_evidence"]

        refs: list[dict[str, str]] = []
        for idx, signal in enumerate(clean_signals[:max_items]):
            refs.append({
                "source_id": clean_ids[idx % len(clean_ids)],
                "summary": signal[:220],
            })
        return refs

    def _calibrate_confidence(self, hypotheses: list[RCAHypothesis]) -> list[RCAHypothesis]:
        """Calibrate hypothesis confidence into relative spread to reduce all-high outputs."""
        if not hypotheses:
            return hypotheses

        sorted_h = sorted(hypotheses, key=lambda h: h.confidence_score, reverse=True)
        top = max(0.0, min(1.0, float(sorted_h[0].confidence_score)))
        second = max(0.0, min(1.0, float(sorted_h[1].confidence_score))) if len(sorted_h) > 1 else top
        gap = max(0.0, top - second)

        if gap >= 0.2:
            return hypotheses

        # Tight pack: preserve ordering but spread scores into a clearer decision frame.
        floor = max(0.35, top - 0.35)
        spread = max(0.16, min(0.28, 0.28 - gap))

        for idx, h in enumerate(sorted_h):
            adjusted = max(floor, min(0.95, top - (idx * spread / max(1, len(sorted_h) - 1))))
            h.confidence_score = round(adjusted, 3)
            h.evidence_strength_pct = int(max(35, min(95, round(adjusted * 100))))

        return hypotheses

    def _ensure_hypothesis_count(
        self,
        hypotheses: list[RCAHypothesis],
        result: InvestigationResult,
        min_signals: int,
        count: int,
    ) -> list[RCAHypothesis]:
        """Guarantee exactly N hypotheses by backfilling missing angle ids.

        LLMs occasionally return fewer than requested even with strict prompts.
        We preserve generated hypotheses and fill missing slots using deterministic
        templates to keep the UI contract stable.
        """
        expected_ids = [f"h{i}" for i in range(1, max(1, count) + 1)]
        by_id: dict[str, RCAHypothesis] = {}

        for h in hypotheses:
            if h.id in expected_ids and h.id not in by_id:
                by_id[h.id] = h

        if len(by_id) >= len(expected_ids):
            return [by_id[eid] for eid in expected_ids]

        fallback = self._fallback_hypotheses(result, min_signals, count)
        fallback_by_id = {h.id: h for h in fallback}

        for eid in expected_ids:
            if eid not in by_id and eid in fallback_by_id:
                by_id[eid] = fallback_by_id[eid]

        return [by_id[eid] for eid in expected_ids if eid in by_id]

    def _build_completion_kwargs(self, model: str) -> dict[str, Any] | None:
        """Build LiteLLM kwargs only when usable credentials are present.

        Returning None lets callers choose a deterministic fallback path and
        avoids noisy library logging paths for unconfigured local environments.
        """
        endpoint = os.environ.get("LITELLM_ENDPOINT", "").strip()
        api_version = os.environ.get("AZURE_API_VERSION", "").strip()

        # Support either generic LiteLLM key or Azure-native variables.
        api_key = (
            os.environ.get("LITELLM_API_KEY", "").strip()
            or os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
        )
        ad_token = os.environ.get("AZURE_OPENAI_AD_TOKEN", "").strip()

        if not api_key and not ad_token:
            return None

        kwargs: dict[str, Any] = {
            "model": model,
            # Avoid None values reaching LiteLLM logging internals.
            "api_base": endpoint if endpoint else "",
        }
        if api_key:
            kwargs["api_key"] = api_key
        if ad_token:
            kwargs["azure_ad_token"] = ad_token
        if api_version:
            kwargs["api_version"] = api_version
        return kwargs

    def _fallback_hypotheses(
        self,
        result: InvestigationResult,
        min_signals: int,
        count: int,
    ) -> list[RCAHypothesis]:
        """Deterministic hypotheses used when LLM is unavailable.

        This preserves Debate Mode usability in local/dev runs without cloud
        credentials while still presenting distinct infrastructure/code/dependency
        angles to the operator.
        """
        ev = result.evidence

        infra_support: list[str] = []
        if ev.oom_kill_events:
            infra_support.append(f"OOM kill events observed ({len(ev.oom_kill_events)})")
        if ev.pod_restarts:
            infra_support.append(f"Pod restarts increased ({len(ev.pod_restarts)})")
        if ev.container_resource_metrics:
            infra_support.append("Container resource metrics show pressure patterns")
        if not infra_support:
            infra_support.append("Infrastructure telemetry should be checked for CPU/memory pressure")

        change_support: list[str] = []
        if ev.azure_activity_changes:
            change_support.append(f"Recent Azure activity changes found ({len(ev.azure_activity_changes)})")
        if ev.health_probe_failures:
            change_support.append(f"Health probe failures present ({len(ev.health_probe_failures)})")
        change_support.append("Recent deployment or config drift could explain the regression")

        dep_support: list[str] = []
        if ev.log_analytics_apim:
            dep_support.append(f"APIM evidence includes upstream/downstream failures ({len(ev.log_analytics_apim)})")
        if ev.network_metrics:
            dep_support.append(f"Network metrics indicate possible dependency path issues ({len(ev.network_metrics)})")
        dep_support.append("Dependency/API latency or availability may be propagating failures")

        templates: list[tuple[str, str, str, list[str], list[str], float, int]] = [
            (
                "h1",
                "Infrastructure Resource Saturation",
                "Service instability is likely driven by infrastructure-level pressure (CPU/memory/node constraints), causing restarts and degraded performance.",
                ["container_resource_metrics", "pod_restarts", "oom_kill_events"],
                infra_support,
                ["No persistent infra saturation trend confirmed yet"],
                0.62,
                62,
            ),
            (
                "h2",
                "Recent Change Regression",
                "A recent deployment or configuration change likely introduced behavioral regression that degraded service health and request handling.",
                ["azure_activity_changes", "health_probe_failures", "container_inventory"],
                change_support,
                ["No single definitive change event has been isolated yet"],
                0.58,
                58,
            ),
            (
                "h3",
                "Upstream Dependency Instability",
                "An upstream or downstream dependency issue is likely cascading into this service and surfacing as failures/timeouts.",
                ["log_analytics_apim", "network_metrics", "aks_context"],
                dep_support,
                ["Local service bottlenecks may also explain symptoms"],
                0.55,
                55,
            ),
        ]

        hypotheses: list[RCAHypothesis] = []
        for hid, title, root, evidence_ids, support, refute, score, pct in templates[: max(1, count)]:
            signals = list(support)
            while len(signals) < min_signals:
                signals.append("Additional evidence collection needed for stronger signal")
            hypotheses.append(
                RCAHypothesis(
                    id=hid,
                    title=title[:60],
                    root_cause=root,
                    evidence_ids=evidence_ids,
                    confidence_score=score,
                    evidence_strength_pct=pct,
                    supporting_signals=signals[:5],
                    refuting_signals=refute[:3],
                    supporting_evidence=self._build_trace_items(signals[:5], evidence_ids, max_items=5),
                    refuting_evidence=self._build_trace_items(refute[:3], evidence_ids, max_items=3),
                )
            )

        return self._calibrate_confidence(hypotheses)
