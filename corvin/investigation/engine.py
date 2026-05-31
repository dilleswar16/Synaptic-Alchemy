"""
Investigation engine.

Owns the stage transitions for a single investigation:
  Enrich → Investigate → RCA → Fix Strategy

In V1 the engine drives the flow from an enriched InvestigationRequest
through to a complete InvestigationResult.  It does not trigger approval,
execution, or verification — those belong to V2/V3.

The engine is the only place that calls the enrichment service, RCA
generator, and fix strategy generator in sequence.  Routes and CLI commands
call the engine; they do not call those modules directly.
"""

from __future__ import annotations

import logging
from typing import Any

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import (
    RCAConfidence,
    InvestigationRequest,
    InvestigationResult,
)
from corvin.enrich.enrichment_service import EnrichmentService
from corvin.investigation.prompt_builder import PromptBuilder
from corvin.investigation.code_enrichment import enrich_with_code_context
from corvin.strategy.fix_strategy_generator import FixStrategyGenerator
from corvin.strategy.rca_generator import RCAGenerator

_log = logging.getLogger(__name__)

# Confidence level ordering used for threshold comparison.
_CONFIDENCE_ORDER = [RCAConfidence.LOW, RCAConfidence.MEDIUM, RCAConfidence.HIGH]


def _confidence_below_threshold(actual: RCAConfidence, threshold: str) -> bool:
    """Return True if *actual* confidence is strictly below *threshold*."""
    try:
        threshold_level = RCAConfidence(threshold)
    except ValueError:
        _log.warning("Unknown confidence threshold %r; defaulting to 'medium'.", threshold)
        threshold_level = RCAConfidence.MEDIUM
    return _CONFIDENCE_ORDER.index(actual) < _CONFIDENCE_ORDER.index(threshold_level)


class InvestigationEngine:
    """
    Drives the V1 investigation pipeline:

        InvestigationRequest
            -> EnrichmentService.enrich()       -> EvidenceBundle
            -> RCAGenerator.generate()           -> RCAOutput
            -> FixStrategyGenerator.generate()   -> FixStrategyOutput
            -> InvestigationResult
    """

    def __init__(
        self,
        enrichment: EnrichmentService | None = None,
        rca: RCAGenerator | None = None,
        fix_strategy: FixStrategyGenerator | None = None,
        prompt_builder: PromptBuilder | None = None,
        repository: Any | None = None,
    ) -> None:
        self._enrichment = enrichment or EnrichmentService()
        self._rca = rca or RCAGenerator()
        self._fix_strategy = fix_strategy or FixStrategyGenerator()
        self._prompt_builder = prompt_builder or PromptBuilder(repository=repository)

    def run(self, request: InvestigationRequest) -> InvestigationResult:
        """
        Execute all investigation stages for the given request.

        Args:
            request: Normalized InvestigationRequest from any trigger adapter.

        Returns:
            InvestigationResult containing evidence, RCA, and fix strategy.

        Raises:
            NotImplementedError: Propagated from any stage that is not yet wired.
        """
        evidence = self._enrichment.enrich(request)

        # ── Code enrichment: auto-fetch source for stack traces ───────────────
        enrich_with_code_context(request.service_name, evidence)

        system_prompt = self._prompt_builder.build(request)
        rca = self._rca.generate(request, evidence, system_prompt=system_prompt)
        fix_strategy = self._fix_strategy.generate(request, rca)

        # ── Confidence threshold gate ─────────────────────────────────────────
        try:
            policy = load_config("policies/investigation", get_env())
            min_confidence = policy.get("min_confidence_to_suggest_action", "medium")
        except Exception:
            min_confidence = "medium"

        confidence_warning = _confidence_below_threshold(rca.confidence, min_confidence)
        if confidence_warning:
            _log.warning(
                "Low-confidence RCA for request_id=%s (confidence=%s < threshold=%s). "
                "All fix actions require human review.",
                request.id,
                rca.confidence.value,
                min_confidence,
            )

        return InvestigationResult(
            request_id=request.id,
            request=request,
            evidence=evidence,
            rca=rca,
            fix_strategy=fix_strategy,
            confidence_warning=confidence_warning,
        )
