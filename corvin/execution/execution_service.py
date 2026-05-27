"""
ExecutionService — V2 Human-in-the-Loop fix execution.

Dispatches approved FixAction items to the appropriate AKS adapter methods.
The approval gate is enforced BOTH here (defensive) and at the API route layer
(primary gate).  Execution only proceeds when approval_status == APPROVED.

Supported action types
----------------------
ActionType.RESTART_POD         → AKSAdapter.restart_pods()
ActionType.ROLLBACK_DEPLOYMENT → AKSAdapter.rollback_deployment()
ActionType.SCALE_DEPLOYMENT    → AKSAdapter.scale_deployment()
ActionType.MANUAL              → Logged and skipped (human-only step)

ExecutionResult
---------------
Each dispatched action produces an ``ActionOutcome`` with:
  - action_type: the ActionType dispatched
  - title:       the FixAction title (human-readable label)
  - success:     True / False
  - detail:      summary of what happened (pod names, error message, etc.)

The combined ``ExecutionResult`` carries all outcomes plus a top-level
``all_succeeded`` flag and the final ``approval_status`` (always EXECUTED
when at least one automatable action was dispatched, regardless of per-action
success).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from corvin.core.contracts import ActionType, ApprovalStatus, FixAction, InvestigationResult
from corvin.evidence.aks_adapter import AKSAdapter


def _ts() -> str:
    """Return a compact UTC timestamp for execution logs."""
    return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]

_log = logging.getLogger(__name__)


# ── Result types ──────────────────────────────────────────────────────────────


@dataclass
class ActionOutcome:
    """Result of executing a single FixAction."""

    action_type: ActionType
    title: str
    success: bool
    detail: str
    logs: list[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """Aggregated result of executing all automatable actions for a request."""

    request_id: str
    outcomes: list[ActionOutcome] = field(default_factory=list)
    approval_status: str = ApprovalStatus.EXECUTED.value

    @property
    def all_succeeded(self) -> bool:
        """True if every dispatched action reported success."""
        return all(o.success for o in self.outcomes)

    @property
    def automatable_count(self) -> int:
        """Number of actions that were dispatched (excludes MANUAL actions)."""
        return sum(1 for o in self.outcomes if o.action_type != ActionType.MANUAL)


# ── Service ───────────────────────────────────────────────────────────────────


class ExecutionService:
    """
    Dispatches approved fix actions to the appropriate AKS adapter methods.

    The *aks* parameter is injectable for testing.  When omitted a real
    ``AKSAdapter`` is constructed from the default config.
    """

    def __init__(self, aks: AKSAdapter | None = None) -> None:
        self._aks: AKSAdapter = aks if aks is not None else AKSAdapter()

    # ── Public API ────────────────────────────────────────────────────────────

    def execute(
        self,
        result: InvestigationResult,
        approval_status: str,
        namespace: str | None = None,
    ) -> ExecutionResult:
        """
        Execute all automatable FixActions in *result.fix_strategy*.

        Gate
        ----
        Raises ``PermissionError`` if *approval_status* is not
        ``ApprovalStatus.APPROVED``.  This is a defensive check — the
        primary gate lives at the API route level.

        Parameters
        ----------
        result:           The completed InvestigationResult whose fix strategy to execute.
        approval_status:  The current approval_status string from Postgres.
        namespace:        Optional Kubernetes namespace override.  Falls back to the
                          AKS adapter's ``default_namespace`` config value.

        Returns
        -------
        ``ExecutionResult`` with one ``ActionOutcome`` per FixAction.
        """
        if approval_status != ApprovalStatus.APPROVED.value:
            raise PermissionError(
                f"ExecutionService: cannot execute request_id={result.request_id!r} — "
                f"approval_status is {approval_status!r}, expected 'approved'."
            )

        service_name = result.request.service_name
        outcomes: list[ActionOutcome] = []

        for action in result.fix_strategy.actions:
            outcome = self._dispatch(action, service_name, namespace)
            outcomes.append(outcome)
            _log.info(
                "ExecutionService: request_id=%s action=%s success=%s detail=%s",
                result.request_id,
                action.action_type.value,
                outcome.success,
                outcome.detail,
            )

        return ExecutionResult(request_id=result.request_id, outcomes=outcomes)

    def execute_single(
        self,
        result: InvestigationResult,
        action_index: int,
        approval_status: str,
        namespace: str | None = None,
    ) -> ActionOutcome:
        """Execute a single FixAction by its index in the fix strategy.

        Gate
        ----
        Raises ``PermissionError`` if *approval_status* is not APPROVED or EXECUTED.
        Raises ``IndexError`` if *action_index* is out of range.
        """
        if approval_status not in (ApprovalStatus.APPROVED.value, ApprovalStatus.EXECUTED.value):
            raise PermissionError(
                f"ExecutionService: cannot execute action — "
                f"approval_status is {approval_status!r}, expected 'approved' or 'executed'."
            )

        actions = result.fix_strategy.actions
        if action_index < 0 or action_index >= len(actions):
            raise IndexError(
                f"action_index {action_index} out of range (0–{len(actions) - 1})."
            )

        action = actions[action_index]
        service_name = result.request.service_name
        outcome = self._dispatch(action, service_name, namespace)
        _log.info(
            "ExecutionService: request_id=%s action[%d]=%s success=%s detail=%s",
            result.request_id,
            action_index,
            action.action_type.value,
            outcome.success,
            outcome.detail,
        )
        return outcome

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def _dispatch(
        self,
        action: FixAction,
        service_name: str,
        namespace: str | None,
    ) -> ActionOutcome:
        """Route a single FixAction to the appropriate AKSAdapter method.

        If the action specifies ``target_service`` or ``target_namespace``,
        those override the investigation-level ``service_name`` / ``namespace``
        so that cross-service remediation (e.g. restarting an Elastic Agent
        when investigating a different app) targets the correct workload.
        """
        effective_service = action.target_service or service_name
        effective_ns = action.target_namespace or namespace

        atype = action.action_type

        if atype == ActionType.RESTART_POD:
            return self._restart(action, effective_service, effective_ns)

        if atype == ActionType.ROLLBACK_DEPLOYMENT:
            return self._rollback(action, effective_service, effective_ns)

        if atype == ActionType.SCALE_DEPLOYMENT:
            return self._scale(action, effective_service, effective_ns)

        # ActionType.MANUAL — human-only step, skip silently
        _log.info(
            "ExecutionService: skipping MANUAL action '%s' for service=%s",
            action.title,
            effective_service,
        )
        return ActionOutcome(
            action_type=ActionType.MANUAL,
            title=action.title,
            success=True,
            detail="Manual action — skipped by ExecutionService (human-only step).",
            logs=[
                f"[{_ts()}] action_type=MANUAL — requires human intervention",
                f"[{_ts()}] skipped automatic execution for '{action.title}'",
                f"[{_ts()}] status=COMPLETE (no-op)",
            ],
        )

    def _restart(
        self, action: FixAction, service_name: str, namespace: str | None
    ) -> ActionOutcome:
        logs = [
            f"[{_ts()}] RESTART_POD initiated for service={service_name}",
            f"[{_ts()}] namespace={namespace or 'default'}",
            f"[{_ts()}] triggering rollout restart…",
        ]
        restarted = self._aks.restart_pods(service_name, namespace=namespace)
        if restarted:
            for item in restarted:
                logs.append(f"[{_ts()}] restarted {item}")
            logs.append(f"[{_ts()}] ✓ rollout restart triggered — new pods scheduling")
            return ActionOutcome(
                action_type=ActionType.RESTART_POD,
                title=action.title,
                success=True,
                detail=f"Restarted: {', '.join(restarted)}",
                logs=logs,
            )
        logs.append(f"[{_ts()}] ✗ no matching deployment or pods found")
        return ActionOutcome(
            action_type=ActionType.RESTART_POD,
            title=action.title,
            success=False,
            detail="No deployment or pods were restarted (not found or adapter error).",
            logs=logs,
        )

    def _rollback(
        self, action: FixAction, service_name: str, namespace: str | None
    ) -> ActionOutcome:
        logs = [
            f"[{_ts()}] ROLLBACK_DEPLOYMENT initiated for deploy/{service_name}",
            f"[{_ts()}] namespace={namespace or 'default'}",
            f"[{_ts()}] fetching deployment revision history…",
        ]
        ok = self._aks.rollback_deployment(service_name, namespace=namespace)
        if ok:
            logs.append(f"[{_ts()}] ✓ rollback to previous revision triggered")
            logs.append(f"[{_ts()}] deployment/{service_name} rollout status: progressing")
        else:
            logs.append(f"[{_ts()}] ✗ rollback failed — check AKS adapter logs")
        return ActionOutcome(
            action_type=ActionType.ROLLBACK_DEPLOYMENT,
            title=action.title,
            success=ok,
            detail="Rollback triggered successfully." if ok else "Rollback failed — see logs.",
            logs=logs,
        )

    def _scale(
        self, action: FixAction, service_name: str, namespace: str | None
    ) -> ActionOutcome:
        # Extract desired replica count from description heuristic ("replicas=N")
        replicas = _parse_replicas(action.description)
        if replicas is None:
            return ActionOutcome(
                action_type=ActionType.SCALE_DEPLOYMENT,
                title=action.title,
                success=False,
                detail=(
                    "Could not determine replica count from action description. "
                    "Include 'replicas=N' in the description."
                ),
            )
        logs = [
            f"[{_ts()}] SCALE_DEPLOYMENT initiated for deploy/{service_name}",
            f"[{_ts()}] namespace={namespace or 'default'}",
            f"[{_ts()}] target replicas={replicas}",
        ]
        ok = self._aks.scale_deployment(service_name, replicas=replicas, namespace=namespace)
        if ok:
            logs.append(f"[{_ts()}] ✓ deployment/{service_name} scaled to {replicas} replica(s)")
            logs.append(f"[{_ts()}] waiting for rollout to complete…")
        else:
            logs.append(f"[{_ts()}] ✗ scale operation failed — check AKS adapter logs")
        return ActionOutcome(
            action_type=ActionType.SCALE_DEPLOYMENT,
            title=action.title,
            success=ok,
            detail=f"Scaled to {replicas} replica(s)." if ok else f"Scale to {replicas} failed — see logs.",
            logs=logs,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_replicas(description: str) -> int | None:
    """Extract ``replicas=N`` from a FixAction description string.

    Returns the integer value of N, or ``None`` if not found / not parseable.
    """
    import re

    match = re.search(r"\breplicas\s*=\s*(\d+)", description, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None
