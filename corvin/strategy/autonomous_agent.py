"""
Autonomous Incident Response Agent — F1 Agentic Feature

Event-driven autonomous investigation pipeline:
1. Webhook alert fires (Azure Monitor, Prometheus AlertManager, etc.)
2. Agent auto-investigates without human intervention
3. Generates RCA + causal chain + fix strategy
4. Sends Teams notification with proposed remediation + approval buttons
5. Waits for human approval before executing any fix actions

This is the "Corvin investigated the 3AM incident before your SRE woke up" feature.

The agent runs as a background task and emits structured events for
observability (investigation_started, evidence_collected, rca_generated,
fix_proposed, awaiting_approval).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import (
    ApprovalStatus,
    InvestigationRequest,
    InvestigationResult,
    TriggerSource,
)
from corvin.delivery.teams_adapter import TeamsAdapter
from corvin.investigation.engine import InvestigationEngine
from corvin.storage.repository import InvestigationRepository
from corvin.strategy.causal_chain import CausalChainGenerator
from corvin.strategy.comms_draft import CommsDraftGenerator

_log = logging.getLogger(__name__)


class AutonomousAgentEvent:
    """Structured event emitted during autonomous investigation."""

    def __init__(self, stage: str, request_id: str, detail: dict[str, Any] | None = None):
        self.stage = stage
        self.request_id = request_id
        self.detail = detail or {}
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "request_id": self.request_id,
            "detail": self.detail,
            "timestamp": self.timestamp.isoformat(),
        }


class AutonomousAgent:
    """
    Orchestrates fully autonomous incident response.

    Unlike the existing trigger pipeline which only runs Engine → Persist → Notify,
    this agent adds:
    - Causal chain generation
    - Communication drafts (auto-generated)
    - Structured event trail for audit
    - Priority-based escalation rules
    """

    def __init__(
        self,
        engine: InvestigationEngine | None = None,
        repo: InvestigationRepository | None = None,
        teams: TeamsAdapter | None = None,
    ) -> None:
        self._engine = engine or InvestigationEngine()
        self._repo = repo or InvestigationRepository()
        self._teams = teams or TeamsAdapter()
        self._causal = CausalChainGenerator()
        self._comms = CommsDraftGenerator()
        self._events: list[AutonomousAgentEvent] = []

    def _emit(self, stage: str, request_id: str, detail: dict[str, Any] | None = None) -> None:
        event = AutonomousAgentEvent(stage, request_id, detail)
        self._events.append(event)
        _log.info("AutonomousAgent [%s] %s: %s", request_id[:8], stage, detail or "")

    def run(self, request: InvestigationRequest) -> dict[str, Any]:
        """
        Execute the full autonomous pipeline. Returns a summary dict.
        
        This method is designed to be called from a BackgroundTask so the
        webhook endpoint returns 202 immediately.
        """
        request_id = request.id
        self._events = []
        self._emit("investigation_started", request_id, {
            "service": request.service_name,
            "environment": request.environment,
            "priority": request.incident_priority,
            "trigger": request.trigger_source,
        })

        # Phase 1: Run investigation engine
        try:
            result = self._engine.run(request)
            self._emit("rca_generated", request_id, {
                "confidence": result.rca.confidence,
                "root_cause_preview": result.rca.root_cause[:100],
            })
        except Exception as exc:
            self._emit("investigation_failed", request_id, {"error": str(exc)})
            _log.exception("Autonomous investigation failed for %s", request_id)
            return {"request_id": request_id, "status": "failed", "error": str(exc), "events": [e.to_dict() for e in self._events]}

        # Phase 2: Persist result
        try:
            self._repo.save_investigation_result(result)
            self._emit("result_persisted", request_id)
        except Exception as exc:
            _log.warning("Persistence failed (non-fatal): %s", exc)
            self._emit("persistence_failed", request_id, {"error": str(exc)})

        # Phase 3: Generate causal chain
        try:
            causal_chain = self._causal.generate(result)
            self._emit("causal_chain_generated", request_id, {
                "node_count": len(causal_chain.get("nodes", [])),
            })
        except Exception as exc:
            causal_chain = None
            _log.warning("Causal chain generation failed (non-fatal): %s", exc)

        # Phase 4: Generate comms drafts
        try:
            comms = self._comms.generate_all(result)
            self._emit("comms_drafted", request_id, {
                "audiences": [c["audience"] for c in comms],
            })
        except Exception as exc:
            comms = []
            _log.warning("Comms generation failed (non-fatal): %s", exc)

        # Phase 5: Teams notification with approval buttons
        try:
            self._teams.send_result(result)
            self._emit("teams_notified", request_id)
        except Exception as exc:
            _log.warning("Teams delivery failed (non-fatal): %s", exc)
            self._emit("teams_failed", request_id, {"error": str(exc)})

        # Phase 6: Escalation check
        if request.incident_priority in ("P1", "P2"):
            self._emit("escalation_triggered", request_id, {
                "priority": request.incident_priority,
                "reason": "High-priority incident requires immediate attention",
            })

        self._emit("awaiting_approval", request_id, {
            "fix_actions": len(result.fix_strategy.actions),
            "requires_approval": any(a.requires_approval for a in result.fix_strategy.actions),
        })

        return {
            "request_id": request_id,
            "status": "awaiting_approval",
            "rca_confidence": result.rca.confidence,
            "fix_action_count": len(result.fix_strategy.actions),
            "causal_chain": causal_chain,
            "comms_drafts": comms,
            "events": [e.to_dict() for e in self._events],
        }
