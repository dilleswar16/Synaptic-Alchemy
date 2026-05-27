"""Deterministic remediation preview helpers for V3.7.

Builds a before/after operator preview for each FixAction using the current
InvestigationResult evidence. This is intentionally deterministic and does not
call the LLM.
"""

from __future__ import annotations

import re
from pydantic import BaseModel, Field

from corvin.core.contracts import ActionType, InvestigationResult


class RemediationPreviewItem(BaseModel):
    title: str
    action_type: str
    target_service: str | None = None
    target_namespace: str | None = None
    risk_level: str
    requires_approval: bool
    current_state: str
    proposed_command: str
    predicted_after_state: str
    operator_notes: list[str] = Field(default_factory=list)


class RemediationPreview(BaseModel):
    request_id: str
    service_name: str
    environment: str
    current_replica_count: int
    cpu_throttle_events_per_min: int
    restart_count: int
    items: list[RemediationPreviewItem] = Field(default_factory=list)


def build_remediation_preview(result: InvestigationResult) -> RemediationPreview:
    pods = _pods(result)
    replica_count = len(pods)
    throttle_events = _cpu_throttle_events(result)
    restart_count = _restart_count(pods)

    items: list[RemediationPreviewItem] = []
    for action in result.fix_strategy.actions:
        items.append(
            _build_item(
                result.request.service_name,
                action=action,
                replica_count=replica_count,
                throttle_events=throttle_events,
                restart_count=restart_count,
            )
        )

    return RemediationPreview(
        request_id=result.request_id,
        service_name=result.request.service_name,
        environment=result.request.environment,
        current_replica_count=replica_count,
        cpu_throttle_events_per_min=throttle_events,
        restart_count=restart_count,
        items=items,
    )


def _build_item(
    service_name: str,
    *,
    action,
    replica_count: int,
    throttle_events: int,
    restart_count: int,
) -> RemediationPreviewItem:
    # Use action-level target if provided, else fall back to investigation service
    effective_svc = action.target_service or service_name
    effective_ns = action.target_namespace or "chad"
    current_state = (
        f"{effective_svc}: {replica_count} replicas / CPU throttle events: {throttle_events}/min / "
        f"recent restarts: {restart_count}"
    )
    notes: list[str] = []

    if action.action_type == ActionType.SCALE_DEPLOYMENT:
        desired = _parse_replicas(action.description)
        proposed_command = (
            f"kubectl scale deployment/{effective_svc} --replicas={desired} -n {effective_ns}"
            if desired is not None
            else f"kubectl scale deployment/{effective_svc} --replicas=<target> -n {effective_ns}"
        )
        if desired is None:
            notes.append("Replica target was not explicit in the action description.")
            predicted = "Replica target must be confirmed before execution."
        else:
            reduction = _percent_reduction(replica_count, desired)
            predicted = (
                f"{effective_svc}: {desired} replicas / estimated CPU throttle reduction: ~{reduction}% / "
                f"higher headroom for burst traffic"
            )
        return RemediationPreviewItem(
            title=action.title,
            action_type=action.action_type.value,
            target_service=action.target_service,
            target_namespace=action.target_namespace,
            risk_level=action.risk_level.value,
            requires_approval=action.requires_approval,
            current_state=current_state,
            proposed_command=proposed_command,
            predicted_after_state=predicted,
            operator_notes=notes,
        )

    if action.action_type == ActionType.RESTART_POD:
        proposed_command = f"kubectl rollout restart deployment/{effective_svc} -n {effective_ns}"
        predicted = (
            f"{effective_svc}: pods recycled / transient errors may spike briefly / "
            f"restart count should normalize within one rollout window"
        )
        notes.append("Use during active traffic only if the deployment has healthy surplus replicas.")
        return RemediationPreviewItem(
            title=action.title,
            action_type=action.action_type.value,
            target_service=action.target_service,
            target_namespace=action.target_namespace,
            risk_level=action.risk_level.value,
            requires_approval=action.requires_approval,
            current_state=current_state,
            proposed_command=proposed_command,
            predicted_after_state=predicted,
            operator_notes=notes,
        )

    if action.action_type == ActionType.ROLLBACK_DEPLOYMENT:
        proposed_command = f"kubectl rollout undo deployment/{effective_svc} -n {effective_ns}"
        predicted = (
            f"{effective_svc}: deployment reverted to previous ReplicaSet / "
            f"error rate should fall if the latest rollout introduced the fault"
        )
        notes.append("Validate config drift and schema compatibility before rollback.")
        return RemediationPreviewItem(
            title=action.title,
            action_type=action.action_type.value,
            target_service=action.target_service,
            target_namespace=action.target_namespace,
            risk_level=action.risk_level.value,
            requires_approval=action.requires_approval,
            current_state=current_state,
            proposed_command=proposed_command,
            predicted_after_state=predicted,
            operator_notes=notes,
        )

    proposed_command = "Manual operator action required"
    predicted = action.estimated_impact or "Manual remediation path to be executed by the operator."
    notes.append("Corvin will not execute this action automatically.")
    return RemediationPreviewItem(
        title=action.title,
        action_type=action.action_type.value,
        target_service=action.target_service,
        target_namespace=action.target_namespace,
        risk_level=action.risk_level.value,
        requires_approval=action.requires_approval,
        current_state=current_state,
        proposed_command=proposed_command,
        predicted_after_state=predicted,
        operator_notes=notes,
    )


def _pods(result: InvestigationResult) -> list[dict]:
    pods = result.evidence.aks_context.get("pods", [])
    return [pod for pod in pods if isinstance(pod, dict)]


def _restart_count(pods: list[dict]) -> int:
    total = 0
    for pod in pods:
        value = pod.get("restart_count", pod.get("restarts", 0))
        try:
            total += int(value)
        except (TypeError, ValueError):
            continue
    return total


def _cpu_throttle_events(result: InvestigationResult) -> int:
    events = result.evidence.aks_context.get("events", [])
    count = 0
    for event in events:
        text = " ".join(str(v) for v in event.values()) if isinstance(event, dict) else str(event)
        if "throttl" in text.lower() or "cpu" in text.lower():
            count += 1
    return count


def _parse_replicas(description: str) -> int | None:
    match = re.search(r"\breplicas\s*=\s*(\d+)", description, re.IGNORECASE)
    if match:
        return int(match.group(1))

    match = re.search(r"\bscale\s+(?:to\s+)?(\d+)\b", description, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _percent_reduction(current_replicas: int, desired_replicas: int) -> int:
    if desired_replicas <= current_replicas:
        return 10
    improvement = min(desired_replicas - current_replicas, max(current_replicas, 1))
    return min(80, max(15, improvement * 20))