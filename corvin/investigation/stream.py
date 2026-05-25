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
from corvin.delivery.rca_notification import (
    send_rca_email_if_enabled,
    publish_wiki_page_if_enabled,
    publish_sharepoint_if_enabled,
)

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
        action_risk_levels = [
            a.risk_level.value if hasattr(a.risk_level, "value") else str(a.risk_level)
            for a in fix_strategy.actions
        ]
        informational_only = (
            len(fix_strategy.actions) == 0
            or all(level == "low" for level in action_risk_levels)
        )
        yield _stage_event(
            "fix_strategy",
            "complete",
            "Fix strategy ready."
            if not fix_degraded
            else f"Fix strategy ready (degraded path: {fix_status}).",
            summary=fix_strategy.summary,
            action_count=len(fix_strategy.actions),
            action_summaries=[a.description for a in fix_strategy.actions],
            action_risk_levels=action_risk_levels,
            informational_only=informational_only,
            generation_status=fix_status,
            degraded=fix_degraded,
        )

        # ── Stage 4: Delivery ─────────────────────────────────────────────────
        result = InvestigationResult(
            request_id=request.id,
            request=request,
            evidence=evidence,
            rca=rca,
            fix_strategy=fix_strategy,
        )

        yield _stage_event("delivery", "started", "Delivering results…")

        ado_url: str | None = None
        ado_work_item_id: str | None = None
        email_sent: bool = False
        wiki_url: str | None = None
        sharepoint_url: str | None = None
        db_saved: bool = False

        # Persist if a repository was provided (mirrors POST /investigations/ behaviour).
        if self._repository is not None:
            yield _stage_event("delivery", "fetching", "",
                               source="database", table="Postgres", source_status="running", count=0, elapsed_ms=0)
            t_db = time.monotonic()
            try:
                self._repository.save_investigation_result(result)
                db_saved = True
            except Exception as persist_exc:  # noqa: BLE001
                _log.warning(
                    "InvestigationStreamer: persistence failed for request_id=%s: %s",
                    request.id,
                    persist_exc,
                )
            yield _stage_event("delivery", "fetching", "",
                               source="database", table="Postgres",
                               source_status="done",
                               count=1 if db_saved else 0,
                               elapsed_ms=int((time.monotonic() - t_db) * 1000),
                               detail="Saved" if db_saved else "Failed")

            # Auto-create Azure Boards work item (non-fatal).
            yield _stage_event("delivery", "fetching", "",
                               source="azure_boards", table="Azure Boards", source_status="running", count=0, elapsed_ms=0)
            t_ado = time.monotonic()
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
            ado_detail = f"Created #{ado_work_item_id}" if ado_work_item_id else "Skipped"
            yield _stage_event("delivery", "fetching", "",
                               source="azure_boards", table="Azure Boards",
                               source_status="done",
                               count=1 if ado_work_item_id else 0,
                               elapsed_ms=int((time.monotonic() - t_ado) * 1000),
                               detail=ado_detail, url=ado_url)

            # Send RCA email (non-fatal).
            # Pre-check config so we can distinguish "Skipped" (disabled) from "Failed" (error).
            try:
                email_cfg = load_config("integrations/email", get_env())
                email_configured = email_cfg.get("enabled", False) and email_cfg.get("auto_send_on_rca", True)
            except Exception:
                email_configured = False

            yield _stage_event("delivery", "fetching", "",
                               source="email", table="Azure Communication Services", source_status="running", count=0, elapsed_ms=0)
            t_email = time.monotonic()
            if email_configured:
                retry_events: list[tuple[int, float]] = []
                email_sent = send_rca_email_if_enabled(
                    result, ado_work_item_url=ado_url,
                    on_retry=lambda attempt, wait: retry_events.append((attempt, wait)),
                )
                for attempt, wait in retry_events:
                    yield _stage_event("delivery", "fetching", "",
                                       source="email", table="Azure Communication Services",
                                       source_status="retrying",
                                       count=0,
                                       elapsed_ms=int((time.monotonic() - t_email) * 1000),
                                       detail=f"Throttled, retry #{attempt} after {wait:.0f}s")
                email_detail = "Sent" if email_sent else "Failed"
            else:
                email_detail = "Skipped"
            yield _stage_event("delivery", "fetching", "",
                               source="email", table="Azure Communication Services",
                               source_status="done",
                               count=1 if email_sent else 0,
                               elapsed_ms=int((time.monotonic() - t_email) * 1000),
                               detail=email_detail)

            # Publish wiki page (non-fatal).
            # Pre-check config so we can distinguish "Skipped" from "Failed".
            try:
                _wiki_cfg = load_config("integrations/azure_devops", get_env())
                wiki_configured = _wiki_cfg.get("wiki_enabled", False)
            except Exception:
                wiki_configured = False

            yield _stage_event("delivery", "fetching", "",
                               source="wiki", table="ADO Wiki", source_status="running", count=0, elapsed_ms=0)
            t_wiki = time.monotonic()
            if wiki_configured:
                wiki_url = publish_wiki_page_if_enabled(result)
                wiki_detail = "Published" if wiki_url else "Failed"
            else:
                wiki_detail = "Skipped"
            yield _stage_event("delivery", "fetching", "",
                               source="wiki", table="ADO Wiki",
                               source_status="done",
                               count=1 if wiki_url else 0,
                               elapsed_ms=int((time.monotonic() - t_wiki) * 1000),
                               detail=wiki_detail, url=wiki_url)

            # Upload to SharePoint (non-fatal).
            try:
                _sp_cfg = load_config("integrations/sharepoint", get_env())
                sp_configured = _sp_cfg.get("enabled", False)
            except Exception:
                sp_configured = False

            if sp_configured:
                yield _stage_event("delivery", "fetching", "",
                                   source="sharepoint", table="SharePoint", source_status="running", count=0, elapsed_ms=0)
                t_sp = time.monotonic()
                try:
                    from corvin.delivery.rca_pdf import build_rca_pdf
                    sp_pdf = build_rca_pdf(result)
                except Exception:
                    sp_pdf = None
                sharepoint_url = publish_sharepoint_if_enabled(result, pdf_bytes=sp_pdf)
                sp_detail = "Uploaded" if sharepoint_url else "Failed"
                yield _stage_event("delivery", "fetching", "",
                                   source="sharepoint", table="SharePoint",
                                   source_status="done",
                                   count=1 if sharepoint_url else 0,
                                   elapsed_ms=int((time.monotonic() - t_sp) * 1000),
                                   detail=sp_detail, url=sharepoint_url)

            # Persist wiki/sharepoint URLs back to DB
            if self._repository is not None and (wiki_url or sharepoint_url):
                try:
                    self._repository.set_delivery_urls(
                        result.request_id,
                        wiki_url=wiki_url,
                        sharepoint_url=sharepoint_url,
                    )
                except Exception as url_exc:  # noqa: BLE001
                    _log.warning("Failed to persist delivery URLs: %s", url_exc)
        else:
            yield _stage_event("delivery", "fetching", "",
                               source="database", table="Postgres",
                               source_status="done", count=0, elapsed_ms=0,
                               detail="Skipped (no repository)")

        yield _stage_event(
            "delivery",
            "complete",
            "Delivery complete.",
            ado_work_item_id=ado_work_item_id,
            ado_url=ado_url,
            email_sent=email_sent,
            wiki_url=wiki_url,
            sharepoint_url=sharepoint_url,
            db_saved=db_saved,
        )

        # ── Stage 5: Complete ─────────────────────────────────────────────────
        yield _stage_event(
            "complete",
            "complete",
            "Investigation complete.",
            request_id=result.request_id,
            ado_work_item_id=ado_work_item_id,
            ado_url=ado_url,
            email_sent=email_sent,
            wiki_url=wiki_url,
            sharepoint_url=sharepoint_url,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────


