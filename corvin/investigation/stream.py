"""
InvestigationStreamer — wraps InvestigationEngine to emit SSE stage events.

Yields newline-delimited ``data: <json>\\n\\n`` strings suitable for a FastAPI
``StreamingResponse`` with media_type ``text/event-stream``.

Stage events
------------
Each event is a JSON object with at minimum:

    { "stage": "<stage_name>", "status": "started" | "complete" | "error",
      "message": "<human-readable line>" }

Stage names (in order):
    evidence       - evidence collection (EnrichmentService)
    rca            - root cause analysis (RCAGenerator)
    fix_strategy   - fix strategy generation (FixStrategyGenerator)
    complete       - entire pipeline done; includes serialised result payload
    error          - unrecoverable error; includes "detail" field

Wire-up
-------
The streamer is intentionally separate from InvestigationEngine so the
synchronous engine can keep working for the CLI / non-streaming API path.
The streamer calls the same underlying services stage-by-stage.

Persistence
-----------
When ``repository`` is supplied, ``save_investigation_result`` is called after
the ``complete`` event is emitted.  This mirrors what the blocking
``POST /investigations/`` route does — the same result lands in Postgres.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Generator
from typing import Any

from corvin.core.contracts import InvestigationRequest, InvestigationResult
from corvin.enrich.enrichment_service import EnrichmentService
from corvin.investigation.prompt_builder import PromptBuilder
from corvin.strategy.fix_strategy_generator import FixStrategyGenerator
from corvin.strategy.rca_generator import RCAGenerator

_log = logging.getLogger(__name__)


# ── SSE helpers ───────────────────────────────────────────────────────────────


def _event(data: dict[str, Any]) -> str:
    """Encode *data* as an SSE ``data:`` line with double newline terminator."""
    return f"data: {json.dumps(data)}\n\n"


def _stage_event(stage: str, status: str, message: str, **extra: Any) -> str:
    payload: dict[str, Any] = {"stage": stage, "status": status, "message": message}
    payload.update(extra)
    return _event(payload)


# ── Streamer ──────────────────────────────────────────────────────────────────


class InvestigationStreamer:
    """
    Runs the investigation pipeline stage-by-stage and yields SSE events.

    Parameters
    ----------
    enrichment:     EnrichmentService instance (injectable for tests).
    rca:            RCAGenerator instance (injectable for tests).
    fix_strategy:   FixStrategyGenerator instance (injectable for tests).
    prompt_builder: PromptBuilder instance (injectable for tests).
    repository:     Optional repository for persisting the result on completion.
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
        self._prompt_builder = prompt_builder or PromptBuilder()
        self._repository = repository

    # ── Public interface ──────────────────────────────────────────────────────

    def stream(self, request: InvestigationRequest) -> Generator[str, None, None]:
        """Run the pipeline for *request* and yield SSE strings for each stage.

        Yields
        ------
        Strings of the form ``data: {json}\\n\\n``.

        Stage sequence
        --------------
        1. evidence started  → evidence complete
        2. rca started       → rca complete
        3. fix_strategy started → fix_strategy complete
        4. complete  (full result payload in ``result`` key)

        On any exception an ``error`` event is yielded and the generator ends.
        The caller (FastAPI route) simply iterates this generator — no try/catch
        needed in the route itself.
        """
        try:
            yield from self._run(request)
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "InvestigationStreamer: unhandled error for request_id=%s: %s",
                request.id,
                exc,
            )
            yield _stage_event(
                "error",
                "error",
                f"Investigation failed: {exc}",
                detail=str(exc),
            )

    # ── Private pipeline ──────────────────────────────────────────────────────

    def _run(self, request: InvestigationRequest) -> Generator[str, None, None]:
        # ── Stage 1: Evidence collection ──────────────────────────────────────
        yield _stage_event(
            "evidence",
            "started",
            f"Collecting evidence for {request.service_name} in {request.environment}…",
        )
        evidence = self._enrichment.enrich(request)
        yield _stage_event(
            "evidence",
            "complete",
            "Evidence collected.",
            sources=list(self._evidence_sources(evidence)),
        )

        # ── Stage 2: RCA generation ───────────────────────────────────────────
        yield _stage_event("rca", "started", "Generating root cause analysis…")
        system_prompt = self._prompt_builder.build(request)
        rca = None
        for token, result in self._rca.generate_stream(request, evidence, system_prompt=system_prompt):
            if token is not None:
                yield _stage_event("rca", "token", token)
            else:
                rca = result
        assert rca is not None  # generate_stream always yields a (None, result) at the end
        yield _stage_event(
            "rca",
            "complete",
            "Root cause analysis complete.",
            summary=rca.summary,
            root_cause=rca.root_cause,
            contributing_factors=rca.contributing_factors,
            confidence=rca.confidence.value,
        )

        # ── Stage 3: Fix strategy generation ─────────────────────────────────
        yield _stage_event("fix_strategy", "started", "Generating fix strategy…")
        fix_strategy = None
        for token, result in self._fix_strategy.generate_stream(request, rca):
            if token is not None:
                yield _stage_event("fix_strategy", "token", token)
            else:
                fix_strategy = result
        assert fix_strategy is not None
        yield _stage_event(
            "fix_strategy",
            "complete",
            "Fix strategy ready.",
            summary=fix_strategy.summary,
            action_count=len(fix_strategy.actions),
            action_summaries=[a.description for a in fix_strategy.actions],
        )

        # ── Stage 4: Complete ─────────────────────────────────────────────────
        result = InvestigationResult(
            request_id=request.id,
            request=request,
            evidence=evidence,
            rca=rca,
            fix_strategy=fix_strategy,
        )

        # Persist if a repository was provided (mirrors POST /investigations/ behaviour).
        if self._repository is not None:
            try:
                self._repository.save_investigation_result(result)
            except Exception as persist_exc:  # noqa: BLE001
                _log.warning(
                    "InvestigationStreamer: persistence failed for request_id=%s: %s",
                    request.id,
                    persist_exc,
                )

        yield _stage_event(
            "complete",
            "complete",
            "Investigation complete.",
            request_id=result.request_id,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _evidence_sources(evidence: Any) -> list[str]:
        """Return a human-readable list of evidence sources that returned data."""
        sources = []
        if evidence.elastic_logs:
            sources.append("elastic_logs")
        if evidence.elastic_metrics:
            sources.append("elastic_metrics")
        if evidence.log_analytics_apim:
            sources.append("log_analytics_apim")
        if evidence.aks_context:
            sources.append("aks_context")
        if evidence.azure_activity_changes:
            sources.append("azure_activity_changes")
        return sources
