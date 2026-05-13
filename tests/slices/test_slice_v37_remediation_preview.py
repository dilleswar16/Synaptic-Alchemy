from __future__ import annotations

from corvin.core.contracts import (
    ActionType,
    EvidenceBundle,
    FixAction,
    FixStrategyOutput,
    InvestigationRequest,
    InvestigationResult,
    RCAOutput,
    RiskLevel,
    TriggerSource,
)
from corvin.execution.preview import build_remediation_preview


def _result_for(*, description: str, action_type: ActionType = ActionType.SCALE_DEPLOYMENT) -> InvestigationResult:
    request = InvestigationRequest(
        id="11111111-1111-1111-1111-111111111111",
        trigger_source=TriggerSource.MANUAL_API,
        service_name="fundapis",
        environment="dev",
        description="Preview test",
    )
    evidence = EvidenceBundle(
        request_id=request.id,
        aks_context={
            "pods": [
                {"name": "fundapis-0", "restart_count": 2},
                {"name": "fundapis-1", "restart_count": 1},
            ],
            "events": [
                {"reason": "CPUThrottlingHigh", "message": "CPU throttling above threshold"},
                {"reason": "CPUThrottlingHigh", "message": "throttling again"},
            ],
        },
    )
    rca = RCAOutput(
        request_id=request.id,
        summary="summary",
        root_cause="root cause",
    )
    fix_strategy = FixStrategyOutput(
        request_id=request.id,
        summary="fix",
        justification="because",
        actions=[
            FixAction(
                title="Scale deployment",
                description=description,
                action_type=action_type,
                risk_level=RiskLevel.MEDIUM,
                estimated_impact="Should restore headroom.",
            )
        ],
    )
    return InvestigationResult(
        request_id=request.id,
        request=request,
        evidence=evidence,
        rca=rca,
        fix_strategy=fix_strategy,
    )


def test_scale_preview_extracts_command_and_after_state():
    preview = build_remediation_preview(_result_for(description="Scale fundapis to 5 replicas=5 immediately"))

    assert preview.current_replica_count == 2
    assert preview.cpu_throttle_events_per_min == 2
    assert preview.restart_count == 3
    assert preview.items[0].proposed_command == "kubectl scale deployment/fundapis --replicas=5 -n chad"
    assert "5 replicas" in preview.items[0].predicted_after_state


def test_restart_preview_uses_rollout_restart_command():
    preview = build_remediation_preview(
        _result_for(description="Restart the unhealthy pods", action_type=ActionType.RESTART_POD)
    )

    assert preview.items[0].proposed_command == "kubectl rollout restart deployment/fundapis -n chad"
    assert "pods recycled" in preview.items[0].predicted_after_state


def test_manual_preview_stays_operator_only():
    preview = build_remediation_preview(
        _result_for(description="Manual drain and inspect", action_type=ActionType.MANUAL)
    )

    assert preview.items[0].proposed_command == "Manual operator action required"
    assert "not execute" in preview.items[0].operator_notes[0]


def test_missing_replica_target_adds_operator_note():
    preview = build_remediation_preview(_result_for(description="Scale deployment now"))

    assert "<target>" in preview.items[0].proposed_command
    assert "explicit" in preview.items[0].operator_notes[0]