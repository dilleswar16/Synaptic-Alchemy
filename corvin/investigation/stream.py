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
import time
from collections.abc import Generator
from typing import Any

from corvin.core.contracts import InvestigationRequest, InvestigationResult
from corvin.enrich.enrichment_service import EnrichmentService
from corvin.investigation.prompt_builder import PromptBuilder
from corvin.strategy.fix_strategy_generator import FixStrategyGenerator
from corvin.strategy.rca_generator import RCAGenerator
from corvin.delivery.rca_notification import send_rca_email_if_enabled, publish_wiki_page_if_enabled

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
        self._prompt_builder = prompt_builder or PromptBuilder(repository=repository)
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
        t_evidence = time.monotonic()
        sources: list[dict] = []
        evidence = None
        for progress, bundle in self._enrichment.enrich_streaming(request):
            if bundle is not None:
                evidence = bundle
            else:
                yield _stage_event("evidence", "fetching", "", **progress)
                if progress.get("source_status") == "done":
                    sources.append(progress)
        assert evidence is not None
        yield _stage_event(
            "evidence",
            "complete",
            "Evidence collected.",
            sources=sources,
            total_elapsed_ms=int((time.monotonic() - t_evidence) * 1000),
        )

        # ── Stage 2: RCA generation ───────────────────────────────────────────
        yield _stage_event("rca", "started", "Generating root cause analysis…")
        system_prompt = self._prompt_builder.build(request)
        rca = None
        for token, result in self._rca.generate_stream(request, evidence, system_prompt=system_prompt):
            if token is not None:
                if token.startswith("__thinking__:"):
                    yield _stage_event("rca_thinking", "token", token[len("__thinking__:"):])
                else:
                    yield _stage_event("rca", "token", token)
            else:
                rca = result
        assert rca is not None  # generate_stream always yields a (None, result) at the end
        # Surface RCA generator's degradation status (ok / insufficient_evidence /
        # degraded_non_streaming / degraded_unparseable / degraded_failed) so the
        # UI can show a banner when an RCA was produced via the fallback path
        # rather than silently treating a degraded result as healthy.
        rca_status = getattr(self._rca, "last_stream_status", None) or "ok"
        rca_degraded = rca_status not in ("ok", "insufficient_evidence")
        yield _stage_event(
            "rca",
            "complete",
            "Root cause analysis complete."
            if not rca_degraded
            else f"Root cause analysis complete (degraded path: {rca_status}).",
            summary=rca.summary,
            root_cause=rca.root_cause,
            contributing_factors=rca.contributing_factors,
            confidence=rca.confidence.value,
            confidence_reasoning=rca.confidence_reasoning,
            evidence_references=rca.evidence_references,
            generation_status=rca_status,
            degraded=rca_degraded,
        )

        # ── Stage 3: Fix strategy generation ─────────────────────────────────
        yield _stage_event("fix_strategy", "started", "Generating fix strategy…")
        fix_strategy = None
        for token, result in self._fix_strategy.generate_stream(request, rca):
            if token is not None:
                if token.startswith("__thinking__:"):
                    yield _stage_event("fix_thinking", "token", token[len("__thinking__:"):])
                else:
                    yield _stage_event("fix_strategy", "token", token)
            else:
                fix_strategy = result
        assert fix_strategy is not None
        # Surface FixStrategyGenerator's degradation status (ok /
        # degraded_non_streaming / degraded_unparseable / degraded_failed) so
        # the UI can show a banner when the fix strategy was produced via the
        # fallback path rather than silently treating it as healthy.
        fix_status = getattr(self._fix_strategy, "last_stream_status", None) or "ok"
        fix_degraded = fix_status != "ok"
        yield _stage_event(
            "fix_strategy",
            "complete",
            "Fix strategy ready."
            if not fix_degraded
            else f"Fix strategy ready (degraded path: {fix_status}).",
            summary=fix_strategy.summary,
            action_count=len(fix_strategy.actions),
            action_summaries=[a.description for a in fix_strategy.actions],
            generation_status=fix_status,
            degraded=fix_degraded,
        )

        # ── Stage 4: Complete ─────────────────────────────────────────────────
        result = InvestigationResult(
            request_id=request.id,
            request=request,
            evidence=evidence,
            rca=rca,
            fix_strategy=fix_strategy,
        )

        ado_url: str | None = None
        ado_work_item_id: str | None = None
        email_sent: bool = False

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

            # Auto-create Azure Boards work item and send email (both non-fatal).
            ado_url: str | None = None
            ado_work_item_id: str | None = None
            try:
                from corvin.core.config_loader import get_env, load_config
                from corvin.delivery.azure_devops_adapter import AzureDevOpsAdapter

                ado_cfg = load_config("integrations/azure_devops", get_env())
                if ado_cfg.get("enabled", False):
                    ado_adapter = AzureDevOpsAdapter(ado_cfg)
                    ado_work_item_id = ado_adapter.create_incident(result)
                    if ado_work_item_id:
                        self._repository.set_ado_work_item_id(result.request_id, ado_work_item_id)
                        org = str(ado_cfg.get("org_name", "")).strip()
                        proj = str(ado_cfg.get("project_name", "")).strip()
                        if org and proj and not org.startswith("${") and not proj.startswith("${"):
                            ado_url = f"https://dev.azure.com/{org}/{proj}/_workitems/edit/{ado_work_item_id}"
            except Exception as ado_exc:  # noqa: BLE001
                import traceback
                _log.warning(
                    "InvestigationStreamer: AzDO auto-sync failed (non-fatal): %s\n%s",
                    ado_exc, traceback.format_exc()
                )

            email_sent = send_rca_email_if_enabled(result, ado_work_item_url=ado_url)
            publish_wiki_page_if_enabled(result)

        yield _stage_event(
            "complete",
            "complete",
            "Investigation complete.",
            request_id=result.request_id,
            ado_work_item_id=ado_work_item_id,
            ado_url=ado_url,
            email_sent=email_sent,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────


