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
    RCAOutput,
)
from corvin.storage.db import get_session
from corvin.storage.models import (
    EvidenceBundleRow,
    FixStrategyOutputRow,
    InvestigationRequestRow,
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


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------


def save_investigation_result(result: InvestigationResult) -> None:
    """Persist all domain objects for one investigation using the default session."""
    InvestigationRepository().save_investigation_result(result)


def get_investigation_result(request_id: str) -> InvestigationResult | None:
    """Load a complete InvestigationResult by request_id using the default session."""
    return InvestigationRepository().get_investigation_result(request_id)
