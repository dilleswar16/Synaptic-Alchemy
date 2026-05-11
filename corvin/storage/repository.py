"""
Investigation persistence repository.

Saves and loads complete InvestigationResult objects to and from Postgres
via SQLAlchemy.

Public interface
----------------
Use the ``InvestigationRepository`` class directly when you need to inject a
custom session factory (e.g. in tests).  Use the module-level convenience
functions for production call sites that want the default ``get_session()``.

    from corvin.storage.repository import InvestigationRepository

    repo = InvestigationRepository()
    repo.save_investigation_result(result)
    loaded = repo.get_investigation_result(request_id)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select


def _as_utc(dt: datetime) -> datetime:
    """Return *dt* with UTC tzinfo attached if it is naive.

    SQLite does not preserve tzinfo in DateTime columns, so datetimes read
    back from the test database are naive even though they were stored as UTC.
    Postgres correctly returns tz-aware datetimes.  Normalising here means
    round-trip equality checks work in both environments without changing
    production behaviour.
    """
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

from corvin.core.contracts import (
    ApprovalStatus,
    EvidenceBundle,
    FixStrategyOutput,
    InvestigationRequest,
    InvestigationResult,
    PostMortemOutput,
    RCAOutput,
)
from corvin.storage.db import get_session
from corvin.storage.models import (
    EvidenceBundleRow,
    FixStrategyOutputRow,
    InvestigationRequestRow,
    PostMortemRow,
    RCAOutputRow,
)


class InvestigationRepository:
    """
    Persists and retrieves InvestigationResult objects.

    Accepts an optional ``session_factory`` for dependency injection and
    testing.  When omitted the production ``get_session()`` context manager
    from ``corvin.storage.db`` is used.
    """

    def __init__(self, session_factory: Any = None) -> None:
        self._session_factory = session_factory if session_factory is not None else get_session

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _upsert_by_request_id(
        self,
        session: Any,
        Model: Any,
        request_id: str,
        **fields: Any,
    ) -> None:
        """
        Insert or update a row that carries a unique ``request_id`` column but
        uses an auto-increment integer as its primary key.

        Used for RCAOutputRow and FixStrategyOutputRow.
        """
        existing = session.execute(
            select(Model).where(Model.request_id == request_id)
        ).scalar_one_or_none()

        if existing is None:
            session.add(Model(request_id=request_id, **fields))
        else:
            for key, value in fields.items():
                setattr(existing, key, value)

    # ── Public interface ──────────────────────────────────────────────────────

    def save_investigation_result(self, result: InvestigationResult) -> None:
        """
        Persist all four domain objects for one investigation.

        Existing rows are updated in-place (upsert behaviour); calling this
        method again for the same request_id is safe and idempotent.

        Raises ValueError if the nested objects carry inconsistent request ids.
        """
        expected = result.request_id
        mismatches = [
            f"request.id={result.request.id!r}"
            for _ in [None]
            if result.request.id != expected
        ] + [
            f"evidence.request_id={result.evidence.request_id!r}"
            for _ in [None]
            if result.evidence.request_id != expected
        ] + [
            f"rca.request_id={result.rca.request_id!r}"
            for _ in [None]
            if result.rca.request_id != expected
        ] + [
            f"fix_strategy.request_id={result.fix_strategy.request_id!r}"
            for _ in [None]
            if result.fix_strategy.request_id != expected
        ]
        if mismatches:
            raise ValueError(
                f"InvestigationResult request_id mismatch (expected {expected!r}): "
                + ", ".join(mismatches)
            )

        with self._session_factory() as session:
            # InvestigationRequest – PK is the string UUID so merge() is correct.
            session.merge(
                InvestigationRequestRow(
                    id=result.request.id,
                    trigger_source=result.request.trigger_source.value,
                    service_name=result.request.service_name,
                    environment=result.request.environment,
                    description=result.request.description,
                    raw_payload=result.request.raw_payload,
                    created_at=result.request.created_at,
                    completed_at=result.completed_at,
                )
            )

            # EvidenceBundle – PK is request_id so merge() is correct.
            session.merge(
                EvidenceBundleRow(
                    request_id=result.evidence.request_id,
                    elastic_logs=result.evidence.elastic_logs,
                    elastic_metrics=result.evidence.elastic_metrics,
                    log_analytics_apim=result.evidence.log_analytics_apim,
                    aks_context=result.evidence.aks_context,
                    azure_activity_changes=result.evidence.azure_activity_changes,
                    collected_at=result.evidence.collected_at,
                )
            )

            # RCA – auto-increment PK; upsert via request_id unique constraint.
            self._upsert_by_request_id(
                session,
                RCAOutputRow,
                result.rca.request_id,
                summary=result.rca.summary,
                root_cause=result.rca.root_cause,
                contributing_factors=result.rca.contributing_factors,
                confidence=result.rca.confidence.value,
                confidence_reasoning=result.rca.confidence_reasoning,
                evidence_references=result.rca.evidence_references,
                generated_at=result.rca.generated_at,
            )

            # Fix strategy – auto-increment PK; upsert via request_id unique constraint.
            self._upsert_by_request_id(
                session,
                FixStrategyOutputRow,
                result.fix_strategy.request_id,
                summary=result.fix_strategy.summary,
                actions=[action.model_dump(mode="json") for action in result.fix_strategy.actions],
                justification=result.fix_strategy.justification,
                generated_at=result.fix_strategy.generated_at,
            )

            # Explicit commit so data is visible in the same transaction-less in-memory
            # SQLite sessions used by tests.  In production get_session() also commits
            # after yield — a second commit on a clean session is a harmless no-op.
            session.commit()

    def get_investigation_result(self, request_id: str) -> InvestigationResult | None:
        """
        Load a complete InvestigationResult from all four tables.

        Returns ``None`` if the request_id is not found or the investigation
        is incomplete (missing evidence bundle, RCA, or fix strategy).
        """
        with self._session_factory() as session:
            req_row = session.get(InvestigationRequestRow, request_id)
            if req_row is None:
                return None

            ev_row = session.execute(
                select(EvidenceBundleRow).where(EvidenceBundleRow.request_id == request_id)
            ).scalar_one_or_none()

            rca_row = session.execute(
                select(RCAOutputRow).where(RCAOutputRow.request_id == request_id)
            ).scalar_one_or_none()

            fix_row = session.execute(
                select(FixStrategyOutputRow).where(FixStrategyOutputRow.request_id == request_id)
            ).scalar_one_or_none()

            if ev_row is None or rca_row is None or fix_row is None:
                return None

            # ── Reconstruct Pydantic contracts from ORM rows ──────────────────
            # _as_utc normalises naive datetimes returned by SQLite in tests;
            # Postgres always returns tz-aware values so this is a no-op there.
            completed_at = _as_utc(req_row.completed_at)

            request = InvestigationRequest.model_validate(
                {
                    "id": req_row.id,
                    "trigger_source": req_row.trigger_source,
                    "service_name": req_row.service_name,
                    "environment": req_row.environment,
                    "description": req_row.description,
                    "raw_payload": req_row.raw_payload,
                    "created_at": _as_utc(req_row.created_at),
                }
            )

            evidence = EvidenceBundle.model_validate(
                {
                    "request_id": ev_row.request_id,
                    "elastic_logs": ev_row.elastic_logs,
                    "elastic_metrics": ev_row.elastic_metrics,
                    "log_analytics_apim": ev_row.log_analytics_apim,
                    "aks_context": ev_row.aks_context,
                    "azure_activity_changes": ev_row.azure_activity_changes,
                    "collected_at": _as_utc(ev_row.collected_at),
                }
            )

            rca = RCAOutput.model_validate(
                {
                    "request_id": rca_row.request_id,
                    "summary": rca_row.summary,
                    "root_cause": rca_row.root_cause,
                    "contributing_factors": rca_row.contributing_factors,
                    "confidence": rca_row.confidence,
                    "confidence_reasoning": getattr(rca_row, "confidence_reasoning", "") or "",
                    "evidence_references": rca_row.evidence_references,
                    "generated_at": _as_utc(rca_row.generated_at),
                }
            )

            fix_strategy = FixStrategyOutput.model_validate(
                {
                    "request_id": fix_row.request_id,
                    "summary": fix_row.summary,
                    "actions": fix_row.actions,
                    "justification": fix_row.justification,
                    "generated_at": _as_utc(fix_row.generated_at),
                }
            )

            return InvestigationResult(
                request_id=request_id,
                request=request,
                evidence=evidence,
                rca=rca,
                fix_strategy=fix_strategy,
                completed_at=completed_at,
            )

    def get_approval_status(self, request_id: str) -> str | None:
        """
        Return the current approval_status string for an investigation, or None
        if the request_id does not exist.
        """
        with self._session_factory() as session:
            row = session.get(InvestigationRequestRow, request_id)
            if row is None:
                return None
            return row.approval_status

    def update_approval_status(
        self,
        request_id: str,
        new_status: ApprovalStatus,
        approved_by: str | None = None,
    ) -> InvestigationRequestRow | None:
        """
        Update approval_status for an existing investigation.

        When *approved_by* is provided (e.g. an SRE's Teams display name or
        email), it is stored alongside the timestamp of the transition for
        a full audit trail.

        Returns the updated ORM row, or None if the request_id does not exist.
        The caller is responsible for enforcing transition guards (e.g. 409 on
        already-executed) before calling this method.
        """
        with self._session_factory() as session:
            row = session.get(InvestigationRequestRow, request_id)
            if row is None:
                return None
            row.approval_status = new_status.value
            if approved_by is not None:
                row.approved_by = approved_by
                row.approved_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(row)
            return row

    def get_similar_incidents(
        self,
        service_name: str,
        environment: str,
        exclude_request_id: str | None = None,
        n: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Return up to *n* completed past investigations for the same service
        and environment, ordered newest-first.

        Each dict contains the fields needed to build a prompt context section
        and to render a UI card:

          request_id, service_name, environment, completed_at,
          rca_summary, root_cause, confidence

        The *exclude_request_id* parameter lets the caller skip the current
        investigation (which would not have been persisted yet anyway, but is
        provided for safety in the API use-case where the investigation is
        already in the DB).

        Only investigations that have a matching rca_outputs row are included
        (partial saves are silently skipped).
        """
        with self._session_factory() as session:
            stmt = (
                select(InvestigationRequestRow, RCAOutputRow)
                .join(
                    RCAOutputRow,
                    RCAOutputRow.request_id == InvestigationRequestRow.id,
                )
                .where(InvestigationRequestRow.service_name == service_name)
                .where(InvestigationRequestRow.environment == environment)
                .order_by(InvestigationRequestRow.completed_at.desc())
                .limit(n)
            )
            if exclude_request_id:
                stmt = stmt.where(InvestigationRequestRow.id != exclude_request_id)

            rows = session.execute(stmt).all()

            results: list[dict[str, Any]] = []
            for req_row, rca_row in rows:
                results.append(
                    {
                        "request_id": req_row.id,
                        "service_name": req_row.service_name,
                        "environment": req_row.environment,
                        "completed_at": _as_utc(req_row.completed_at).isoformat(),
                        "rca_summary": rca_row.summary,
                        "root_cause": rca_row.root_cause,
                        "confidence": rca_row.confidence,
                    }
                )
        return results

    def list_investigations(self) -> list[dict[str, Any]]:
        """
        Return lightweight summary rows for all investigations.

        Each dict contains: request_id, service_name, environment,
        trigger_source, approval_status, completed_at, created_at.

        Only queries ``investigation_requests`` — no joins required.
        """
        with self._session_factory() as session:
            rows = session.execute(
                select(InvestigationRequestRow).order_by(
                    InvestigationRequestRow.completed_at.desc()
                )
            ).scalars().all()
            return [
                {
                    "request_id": r.id,
                    "service_name": r.service_name,
                    "environment": r.environment,
                    "trigger_source": r.trigger_source,
                    "approval_status": r.approval_status,
                    "approved_by": r.approved_by,
                    "approved_at": _as_utc(r.approved_at).isoformat() if r.approved_at else None,
                    "completed_at": _as_utc(r.completed_at).isoformat(),
                    "created_at": _as_utc(r.created_at).isoformat(),
                }
                for r in rows
            ]

    def get_investigation_replay(
        self, request_id: str
    ) -> dict[str, Any] | None:
        """
        Return a transparency payload for a completed investigation.

        Includes the full InvestigationRequest (what triggered it),
        the EvidenceBundle summary (what data was gathered), and
        the RCA + FixStrategy with all their fields exposed.

        Returns None if the investigation is not found or incomplete.
        This is the V2.5 Replay / Explainability endpoint.
        """
        result = self.get_investigation_result(request_id)
        if result is None:
            return None

        with self._session_factory() as session:
            req_row = session.get(InvestigationRequestRow, request_id)

        evidence_summary = {
            "elastic_log_count": len(result.evidence.elastic_logs),
            "elastic_metric_count": len(result.evidence.elastic_metrics),
            "log_analytics_apim_count": len(result.evidence.log_analytics_apim),
            "aks_context_keys": list(result.evidence.aks_context.keys()),
            "azure_activity_count": len(result.evidence.azure_activity_changes),
            "collected_at": result.evidence.collected_at.isoformat(),
        }

        return {
            "request_id": request_id,
            "trigger": {
                "service_name": result.request.service_name,
                "environment": result.request.environment,
                "trigger_source": result.request.trigger_source.value,
                "description": result.request.description,
                "lookback_minutes": result.request.lookback_minutes,
                "created_at": result.request.created_at.isoformat(),
            },
            "approval": {
                "status": req_row.approval_status if req_row else None,
                "approved_by": req_row.approved_by if req_row else None,
                "approved_at": (
                    _as_utc(req_row.approved_at).isoformat()
                    if req_row and req_row.approved_at
                    else None
                ),
            },
            "evidence_summary": evidence_summary,
            "rca": {
                "summary": result.rca.summary,
                "root_cause": result.rca.root_cause,
                "confidence": result.rca.confidence.value,
                "contributing_factors": result.rca.contributing_factors,
                "evidence_references": result.rca.evidence_references,
                "generated_at": result.rca.generated_at.isoformat(),
            },
            "fix_strategy": {
                "summary": result.fix_strategy.summary,
                "justification": result.fix_strategy.justification,
                "action_count": len(result.fix_strategy.actions),
                "actions": [
                    {
                        "title": a.title,
                        "risk_level": a.risk_level.value,
                        "requires_approval": a.requires_approval,
                        "estimated_impact": a.estimated_impact,
                    }
                    for a in result.fix_strategy.actions
                ],
                "generated_at": result.fix_strategy.generated_at.isoformat(),
            },
            "completed_at": result.completed_at.isoformat(),
        }

    # ── Post-Mortem ───────────────────────────────────────────────────────────

    def save_post_mortem(self, pm: PostMortemOutput) -> None:
        """Persist (or replace) a PostMortemOutput row for the given request_id."""
        with self._session_factory() as session:
            existing = session.get(PostMortemRow, pm.request_id)
            if existing is not None:
                # Replace in-place — re-generating is allowed
                existing.incident_summary = pm.incident_summary
                existing.detection_timeline = pm.detection_timeline
                existing.investigation_findings = pm.investigation_findings
                existing.actions_taken = pm.actions_taken
                existing.prevention_recommendations = pm.prevention_recommendations
                existing.approved_by = pm.approved_by
                existing.markdown = pm.markdown
                existing.generated_at = pm.generated_at
                existing.service_name = pm.service_name
                existing.environment = pm.environment
            else:
                session.add(
                    PostMortemRow(
                        request_id=pm.request_id,
                        service_name=pm.service_name,
                        environment=pm.environment,
                        incident_summary=pm.incident_summary,
                        detection_timeline=pm.detection_timeline,
                        investigation_findings=pm.investigation_findings,
                        actions_taken=pm.actions_taken,
                        prevention_recommendations=pm.prevention_recommendations,
                        approved_by=pm.approved_by,
                        markdown=pm.markdown,
                        generated_at=pm.generated_at,
                    )
                )
            session.commit()

    def get_post_mortem(self, request_id: str) -> PostMortemOutput | None:
        """Return a cached PostMortemOutput, or None if not yet generated."""
        with self._session_factory() as session:
            row = session.get(PostMortemRow, request_id)
            if row is None:
                return None
            return PostMortemOutput(
                request_id=row.request_id,
                service_name=row.service_name,
                environment=row.environment,
                incident_summary=row.incident_summary,
                detection_timeline=row.detection_timeline,
                investigation_findings=row.investigation_findings,
                actions_taken=row.actions_taken,
                prevention_recommendations=row.prevention_recommendations,
                approved_by=row.approved_by,
                markdown=row.markdown,
                generated_at=_as_utc(row.generated_at),
            )

    def get_investigation_stats(self) -> dict:
        """
        Aggregate SRE health metrics from real Postgres data.

        Returns
        -------
        dict with:
          total_investigations: int
          today_count: int          — investigations started today (UTC)
          confidence_distribution:  dict[str, int]  (high/medium/low counts)
          approval_distribution:    dict[str, int]  (pending/approved/rejected/executed)
          avg_mttr_minutes: float | None  — mean time from created_at to completed_at
          auto_resolved_rate: float       — fraction that reached 'executed' state
          recent_services: list[str]      — last 5 unique service names investigated
        """
        from datetime import date

        from sqlalchemy import func, text

        with self._session_factory() as session:
            rows = session.execute(
                select(InvestigationRequestRow)
            ).scalars().all()

            if not rows:
                return {
                    "total_investigations": 0,
                    "today_count": 0,
                    "confidence_distribution": {"high": 0, "medium": 0, "low": 0},
                    "approval_distribution": {
                        "pending": 0, "approved": 0, "rejected": 0, "executed": 0
                    },
                    "avg_mttr_minutes": None,
                    "auto_resolved_rate": 0.0,
                    "recent_services": [],
                }

            today = datetime.now(timezone.utc).date()
            today_count = sum(
                1 for r in rows
                if r.created_at and _as_utc(r.created_at).date() == today
            )

            approval_dist: dict[str, int] = {
                "pending": 0, "approved": 0, "rejected": 0, "executed": 0
            }
            for r in rows:
                key = r.approval_status or "pending"
                approval_dist[key] = approval_dist.get(key, 0) + 1

            # MTTR: mean minutes from created_at to completed_at
            mttr_values = []
            for r in rows:
                if r.created_at and r.completed_at:
                    delta = _as_utc(r.completed_at) - _as_utc(r.created_at)
                    mttr_values.append(delta.total_seconds() / 60.0)
            avg_mttr = (sum(mttr_values) / len(mttr_values)) if mttr_values else None

            auto_resolved_rate = (
                approval_dist.get("executed", 0) / len(rows)
            ) if rows else 0.0

            # Confidence from rca_outputs table
            rca_rows = session.execute(select(RCAOutputRow)).scalars().all()
            conf_dist: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
            for r in rca_rows:
                key = (r.confidence or "medium").lower()
                conf_dist[key] = conf_dist.get(key, 0) + 1

            # Last 5 unique services (ordered by most recent)
            seen: list[str] = []
            for r in sorted(rows, key=lambda x: _as_utc(x.created_at), reverse=True):
                if r.service_name not in seen:
                    seen.append(r.service_name)
                if len(seen) >= 5:
                    break

            return {
                "total_investigations": len(rows),
                "today_count": today_count,
                "confidence_distribution": conf_dist,
                "approval_distribution": approval_dist,
                "avg_mttr_minutes": round(avg_mttr, 1) if avg_mttr is not None else None,
                "auto_resolved_rate": round(auto_resolved_rate, 3),
                "recent_services": seen,
            }

    def get_briefing(self, hours: int = 24) -> dict:
        """Return an AI-style SRE briefing payload for the dashboard Morning Briefing widget.

        Covers the last *hours* window and includes a Jarvis-style narrative summary,
        confidence breakdown, pending approval counts, and top active services.
        """
        from collections import Counter
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        with self._session_factory() as session:
            recent_rows = session.execute(
                select(InvestigationRequestRow).where(
                    InvestigationRequestRow.created_at >= cutoff
                )
            ).scalars().all()

            total = len(recent_rows)
            pending = sum(1 for r in recent_rows if r.approval_status == "pending")
            approved = sum(1 for r in recent_rows if r.approval_status == "approved")
            executed = sum(1 for r in recent_rows if r.approval_status == "executed")
            rejected = sum(1 for r in recent_rows if r.approval_status == "rejected")

            # High-confidence investigations currently pending approval
            high_conf_pending = 0
            conf_map: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
            if recent_rows:
                recent_ids = {r.id for r in recent_rows}
                rca_rows = session.execute(
                    select(RCAOutputRow).where(
                        RCAOutputRow.request_id.in_(recent_ids)
                    )
                ).scalars().all()
                rca_by_id = {r.request_id: r for r in rca_rows}
                for r in rca_rows:
                    key = (r.confidence or "medium").lower()
                    conf_map[key] = conf_map.get(key, 0) + 1
                high_conf_pending = sum(
                    1 for r in recent_rows
                    if r.approval_status == "pending"
                    and rca_by_id.get(r.id) is not None
                    and (rca_by_id[r.id].confidence or "").lower() == "high"
                )

            # Top 3 services by investigation volume in the window
            service_counts: Counter = Counter(
                (r.service_name, r.environment) for r in recent_rows
            )
            top_services = [
                {"service": svc, "environment": env, "count": cnt}
                for (svc, env), cnt in service_counts.most_common(3)
            ]

            narrative = _build_briefing_narrative(
                total=total,
                pending=pending,
                high_conf_pending=high_conf_pending,
                top_services=top_services,
                conf_map=conf_map,
                hours=hours,
            )

            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "period_hours": hours,
                "total_investigations": total,
                "pending_approval": pending,
                "approved": approved,
                "executed": executed,
                "rejected": rejected,
                "high_confidence_pending": high_conf_pending,
                "confidence_breakdown": conf_map,
                "top_services": top_services,
                "narrative": narrative,
            }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_briefing_narrative(
    total: int,
    pending: int,
    high_conf_pending: int,
    top_services: list[dict],
    conf_map: dict[str, int],
    hours: int,
) -> str:
    """Build a Jarvis-style narrative sentence for the Morning Briefing widget."""
    if total == 0:
        return (
            f"No incidents investigated in the last {hours} hours. "
            "Systems appear stable — no active investigations on record."
        )

    parts: list[str] = []

    # Total count
    if total == 1:
        parts.append(f"1 incident was investigated in the last {hours} hours.")
    else:
        parts.append(f"{total} incidents were investigated in the last {hours} hours.")

    # Confidence headline
    high = conf_map.get("high", 0)
    if high > 0 and total > 0:
        pct = round((high / total) * 100)
        parts.append(f"{pct}% of root causes were identified with high confidence.")

    # Pending approval — most operationally important
    if high_conf_pending > 0:
        noun = "investigation requires" if high_conf_pending == 1 else "investigations require"
        parts.append(f"{high_conf_pending} high-confidence {noun} your approval.")
    elif pending > 0:
        noun = "investigation is" if pending == 1 else "investigations are"
        parts.append(f"{pending} {noun} awaiting review.")
    else:
        parts.append("All investigations have been reviewed — no pending approvals.")

    # Service spotlight
    if top_services:
        top = top_services[0]
        inv_noun = "investigation" if top["count"] == 1 else "investigations"
        parts.append(
            f"{top['service']} ({top['environment']}) is the most active service "
            f"with {top['count']} {inv_noun} this window."
        )

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------


def save_investigation_result(result: InvestigationResult) -> None:
    """Persist all domain objects for one investigation using the default session."""
    InvestigationRepository().save_investigation_result(result)


def get_investigation_result(request_id: str) -> InvestigationResult | None:
    """Load a complete InvestigationResult by request_id using the default session."""
    return InvestigationRepository().get_investigation_result(request_id)
