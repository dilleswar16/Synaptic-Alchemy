"""
F9 — Multi-Agent Investigation Orchestrator.

Implements the SelectorGroupChat pattern (Microsoft Agent Framework / AutoGen 0.4)
for Corvin investigations.  Instead of a rigid linear pipeline, an LLM-based
orchestrator dynamically routes turns to specialist agents:

  • EvidenceCollectorAgent — wraps EnrichmentService
  • RCAAnalystAgent — wraps RCAGenerator
  • FixStrategyAgent — wraps FixStrategyGenerator

Each agent operates within a shared thread (message list), reads context
contributed by prior agents, and appends structured output.  The orchestrator
selects the next agent based on thread state until a termination signal
(FIX_STRATEGY_COMPLETE) or max turns is reached.

This implementation is framework-agnostic — it mirrors the SelectorGroupChat
protocol without requiring the autogen-agentchat package, making it zero-dep.
If AutoGen 0.4 is installed, it can be swapped in trivially.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import litellm

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import (
    EvidenceBundle,
    InvestigationRequest,
    InvestigationResult,
    RCAOutput,
    FixStrategyOutput,
)
from corvin.enrich.enrichment_service import EnrichmentService
from corvin.strategy.rca_generator import RCAGenerator
from corvin.strategy.fix_strategy_generator import FixStrategyGenerator

_log = logging.getLogger(__name__)

_MAX_TURNS = 12
_TERMINATION_SIGNAL = "FIX_STRATEGY_COMPLETE"


class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    EVIDENCE_COLLECTOR = "evidence_collector"
    RCA_ANALYST = "rca_analyst"
    FIX_STRATEGIST = "fix_strategist"


@dataclass
class AgentMessage:
    """Single message in the multi-agent thread."""
    role: AgentRole
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MultiAgentTrace:
    """Observability trace for the multi-agent run."""
    request_id: str
    turns: list[dict[str, Any]] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None
    terminal_signal: str | None = None
    total_elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "turns": self.turns,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "terminal_signal": self.terminal_signal,
            "total_elapsed_ms": self.total_elapsed_ms,
            "turn_count": len(self.turns),
        }


class MultiAgentOrchestrator:
    """
    Coordinates specialist agents in a dynamic group chat for investigations.

    Uses LLM-based selector to pick the next agent per turn, mimicking
    AutoGen 0.4's SelectorGroupChat without the framework dependency.
    """

    def __init__(
        self,
        enrichment: EnrichmentService | None = None,
        rca_generator: RCAGenerator | None = None,
        fix_strategy_generator: FixStrategyGenerator | None = None,
    ) -> None:
        self._enrichment = enrichment or EnrichmentService()
        self._rca = rca_generator or RCAGenerator()
        self._fix_strategy = fix_strategy_generator or FixStrategyGenerator()
        self._config = load_config("models/llm", get_env())

    def _get_model(self) -> str:
        model = self._config.get("fallback_model") or self._config.get("model")
        if not model:
            raise ValueError("models/llm.yaml must define 'model' or 'fallback_model'")
        return model

    def _select_next_agent(self, thread: list[AgentMessage], request: InvestigationRequest) -> AgentRole:
        """Use LLM to decide which specialist agent should act next."""
        if not thread:
            return AgentRole.EVIDENCE_COLLECTOR

        last_role = thread[-1].role

        # Deterministic fast-path when context is clear
        if last_role == AgentRole.ORCHESTRATOR:
            return AgentRole.EVIDENCE_COLLECTOR
        if last_role == AgentRole.EVIDENCE_COLLECTOR:
            return AgentRole.RCA_ANALYST
        if last_role == AgentRole.RCA_ANALYST:
            return AgentRole.FIX_STRATEGIST

        # LLM-based selection for complex/looping cases
        selection_prompt = f"""You are the orchestrator for an incident investigation multi-agent system.
The investigation is for service '{request.service_name}' with alert: {request.alert_summary}.

Current thread state (last 3 messages):
{self._summarize_thread(thread[-3:])}

Available agents:
- evidence_collector: Gathers logs, metrics, pod health, activity changes
- rca_analyst: Analyzes evidence to determine root cause
- fix_strategist: Proposes remediation actions based on RCA

Which agent should act next? Reply with ONLY the agent name."""

        try:
            resp = litellm.completion(
                model=self._get_model(),
                messages=[{"role": "user", "content": selection_prompt}],
                max_tokens=20,
                temperature=0,
            )
            choice = resp.choices[0].message.content.strip().lower()
            mapping = {
                "evidence_collector": AgentRole.EVIDENCE_COLLECTOR,
                "rca_analyst": AgentRole.RCA_ANALYST,
                "fix_strategist": AgentRole.FIX_STRATEGIST,
            }
            return mapping.get(choice, AgentRole.FIX_STRATEGIST)
        except Exception:
            # Fallback: advance linearly
            return AgentRole.FIX_STRATEGIST

    def _summarize_thread(self, messages: list[AgentMessage]) -> str:
        lines = []
        for m in messages:
            content_preview = m.content[:200] + "..." if len(m.content) > 200 else m.content
            lines.append(f"[{m.role.value}] {content_preview}")
        return "\n".join(lines)

    def _run_evidence_collector(self, request: InvestigationRequest) -> tuple[AgentMessage, EvidenceBundle]:
        """EvidenceCollectorAgent: wraps EnrichmentService."""
        _log.info("[MultiAgent] EvidenceCollectorAgent running for %s", request.id)
        evidence = self._enrichment.enrich(request)
        summary = {
            "adapters_used": list(evidence.evidence.keys()) if evidence.evidence else [],
            "total_items": sum(len(v) if isinstance(v, list) else 1 for v in (evidence.evidence or {}).values()),
            "service": request.service_name,
        }
        msg = AgentMessage(
            role=AgentRole.EVIDENCE_COLLECTOR,
            content=json.dumps(summary, default=str),
            metadata={"status": "EVIDENCE_COLLECTED"},
        )
        return msg, evidence

    def _run_rca_analyst(self, request: InvestigationRequest, evidence: EvidenceBundle) -> tuple[AgentMessage, RCAOutput]:
        """RCAAnalystAgent: wraps RCAGenerator."""
        _log.info("[MultiAgent] RCAAnalystAgent running for %s", request.id)
        rca = self._rca.generate(request, evidence)
        msg = AgentMessage(
            role=AgentRole.RCA_ANALYST,
            content=json.dumps({
                "root_cause": rca.root_cause,
                "confidence": rca.confidence.value,
                "contributing_factors": rca.contributing_factors,
            }, default=str),
            metadata={"status": "RCA_COMPLETE", "confidence": rca.confidence.value},
        )
        return msg, rca

    def _run_fix_strategist(self, request: InvestigationRequest, rca: RCAOutput) -> tuple[AgentMessage, FixStrategyOutput]:
        """FixStrategyAgent: wraps FixStrategyGenerator."""
        _log.info("[MultiAgent] FixStrategyAgent running for %s", request.id)
        fix = self._fix_strategy.generate(request, rca)
        msg = AgentMessage(
            role=AgentRole.FIX_STRATEGIST,
            content=json.dumps({
                "actions_count": len(fix.actions) if fix.actions else 0,
                "has_rollback": bool(fix.rollback_steps),
                "signal": _TERMINATION_SIGNAL,
            }, default=str),
            metadata={"status": _TERMINATION_SIGNAL},
        )
        return msg, fix

    def run(self, request: InvestigationRequest) -> tuple[InvestigationResult, MultiAgentTrace]:
        """
        Execute multi-agent investigation pipeline.

        Returns:
            Tuple of (InvestigationResult, MultiAgentTrace) for persistence + observability.
        """
        trace = MultiAgentTrace(request_id=request.id)
        thread: list[AgentMessage] = []
        t0 = time.perf_counter()

        evidence: EvidenceBundle | None = None
        rca: RCAOutput | None = None
        fix: FixStrategyOutput | None = None

        # Initial orchestrator message
        thread.append(AgentMessage(
            role=AgentRole.ORCHESTRATOR,
            content=f"Investigation started for service={request.service_name}, alert={request.alert_summary}",
        ))

        for turn_idx in range(_MAX_TURNS):
            next_agent = self._select_next_agent(thread, request)
            turn_start = time.perf_counter()

            try:
                if next_agent == AgentRole.EVIDENCE_COLLECTOR and evidence is None:
                    msg, evidence = self._run_evidence_collector(request)
                elif next_agent == AgentRole.RCA_ANALYST and evidence is not None and rca is None:
                    msg, rca = self._run_rca_analyst(request, evidence)
                elif next_agent == AgentRole.FIX_STRATEGIST and rca is not None:
                    msg, fix = self._run_fix_strategist(request, rca)
                else:
                    # Skip invalid selection
                    _log.debug("[MultiAgent] Skipping invalid agent selection: %s (turn %d)", next_agent, turn_idx)
                    continue

                thread.append(msg)
                turn_elapsed = (time.perf_counter() - turn_start) * 1000

                trace.turns.append({
                    "turn": turn_idx,
                    "agent": next_agent.value,
                    "elapsed_ms": round(turn_elapsed, 1),
                    "status": msg.metadata.get("status", "ok"),
                })

                # Check termination
                if msg.metadata.get("status") == _TERMINATION_SIGNAL:
                    trace.terminal_signal = _TERMINATION_SIGNAL
                    break

            except Exception as exc:
                _log.exception("[MultiAgent] Agent %s failed on turn %d: %s", next_agent, turn_idx, exc)
                trace.turns.append({
                    "turn": turn_idx,
                    "agent": next_agent.value,
                    "elapsed_ms": (time.perf_counter() - turn_start) * 1000,
                    "status": "error",
                    "error": str(exc),
                })
                break

        trace.total_elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        trace.completed_at = datetime.now(timezone.utc).isoformat()

        # Build result even if partially complete
        if evidence is None:
            evidence = EvidenceBundle(evidence={})
        if rca is None:
            from corvin.core.contracts import RCAConfidence
            rca = RCAOutput(
                root_cause="Multi-agent pipeline incomplete — evidence insufficient",
                confidence=RCAConfidence.LOW,
                contributing_factors=[],
            )
        if fix is None:
            fix = FixStrategyOutput(actions=[], rollback_steps=[])

        result = InvestigationResult(
            request_id=request.id,
            request=request,
            evidence=evidence,
            rca=rca,
            fix_strategy=fix,
        )

        return result, trace
