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

from corvin.core.contracts import (
    InvestigationRequest,
    InvestigationResult,
)
from corvin.enrich.enrichment_service import EnrichmentService
from corvin.investigation.prompt_builder import PromptBuilder
from corvin.strategy.fix_strategy_generator import FixStrategyGenerator
from corvin.strategy.rca_generator import RCAGenerator


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
    ) -> None:
        self._enrichment = enrichment or EnrichmentService()
        self._rca = rca or RCAGenerator()
        self._fix_strategy = fix_strategy or FixStrategyGenerator()
        self._prompt_builder = prompt_builder or PromptBuilder()

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
        system_prompt = self._prompt_builder.build(request)
        rca = self._rca.generate(request, evidence, system_prompt=system_prompt)
        fix_strategy = self._fix_strategy.generate(request, rca)

        return InvestigationResult(
            request_id=request.id,
            request=request,
            evidence=evidence,
            rca=rca,
            fix_strategy=fix_strategy,
        )
