"""
Slice 6 – LiteLLM RCA and fix strategy generation tests.

These tests mock LiteLLM so RCA and fix strategy generation can be validated
without real model calls.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from corvin.core.contracts import (
    EvidenceBundle,
    FixAction,
    FixStrategyOutput,
    InvestigationRequest,
    RCAConfidence,
    RCAOutput,
    RiskLevel,
    TriggerSource,
)
from corvin.investigation.engine import InvestigationEngine
from corvin.strategy.fix_strategy_generator import FixStrategyGenerator
from corvin.strategy.rca_generator import RCAGenerator


def _make_request() -> InvestigationRequest:
    return InvestigationRequest(
        trigger_source=TriggerSource.AZURE_ALERT,
        service_name="order-service",
        environment="production",
        description="APIM gateway 5xx spike",
    )


def _make_evidence(request_id: str) -> EvidenceBundle:
    return EvidenceBundle(
        request_id=request_id,
        elastic_logs=[{"message": "NullPointerException in checkout flow"}],
    )


def _completion_response(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(payload))
            )
        ]
    )


def _structured_completion_response(parsed_obj) -> SimpleNamespace:
    """Simulate a LiteLLM structured output response with a .parsed attribute."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=None, parsed=parsed_obj)
            )
        ]
    )


def test_rca_success_path(monkeypatch):
    request = _make_request()
    evidence = _make_evidence(request.id)
    captured: dict[str, object] = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _completion_response(
            {
                "request_id": request.id,
                "summary": "Backend exceptions caused elevated 5xx responses.",
                "root_cause": "The order-service returned unhandled exceptions.",
                "contributing_factors": ["traffic spike"],
                "confidence": "high",
                "evidence_references": ["elastic_logs[0]"],
            }
        )

    monkeypatch.setattr("corvin.strategy.rca_generator.litellm.completion", fake_completion)

    generator = RCAGenerator(
        config={
            "model": "primary-model",
            "fallback_model": "fallback-model",
            "temperature": 0.1,
            "max_tokens": 512,
        },
        policy_config={"require_evidence_before_rca": True},
    )
    result = generator.generate(request, evidence, system_prompt="system knowledge")

    assert result.root_cause == "The order-service returned unhandled exceptions."
    assert result.confidence == RCAConfidence.HIGH
    assert captured["model"] == "primary-model"
    assert captured["messages"][0] == {"role": "system", "content": "system knowledge"}


def test_rca_normalizes_bare_evidence_reference_keys(monkeypatch):
    request = _make_request()
    evidence = _make_evidence(request.id)

    def fake_completion(**kwargs):
        return _completion_response(
            {
                "request_id": request.id,
                "summary": "Healthy check completed.",
                "root_cause": "No active issue detected.",
                "contributing_factors": [],
                "confidence": "high",
                "evidence_references": ["elastic_logs"],
            }
        )

    monkeypatch.setattr("corvin.strategy.rca_generator.litellm.completion", fake_completion)

    generator = RCAGenerator(
        config={
            "model": "primary-model",
            "fallback_model": "fallback-model",
            "temperature": 0.1,
            "max_tokens": 512,
        },
        policy_config={"require_evidence_before_rca": True},
    )
    result = generator.generate(request, evidence, system_prompt="system knowledge")

    assert result.evidence_references == ["elastic_logs: 1 record found"]


def test_rca_fallback_model_path_after_primary_failure(monkeypatch):
    request = _make_request()
    evidence = _make_evidence(request.id)
    calls: list[str] = []

    def fake_completion(**kwargs):
        calls.append(str(kwargs["model"]))
        if kwargs["model"] == "primary-model":
            raise RuntimeError("primary unavailable")
        return _completion_response(
            {
                "request_id": request.id,
                "summary": "Fallback RCA generated.",
                "root_cause": "Fallback model succeeded.",
                "contributing_factors": [],
                "confidence": "medium",
                "evidence_references": [],
            }
        )

    monkeypatch.setattr("corvin.strategy.rca_generator.litellm.completion", fake_completion)

    generator = RCAGenerator(
        config={
            "model": "primary-model",
            "fallback_model": "fallback-model",
            "temperature": 0.1,
            "max_tokens": 512,
        },
        policy_config={"require_evidence_before_rca": True},
    )
    result = generator.generate(request, evidence, system_prompt="system knowledge")

    assert result.root_cause == "Fallback model succeeded."
    assert calls == ["primary-model", "fallback-model"]


def test_no_evidence_policy_path_returns_deterministic_rca_without_calling_litellm(monkeypatch):
    request = _make_request()
    evidence = EvidenceBundle(request_id=request.id)
    call_count = 0

    def fake_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        return _completion_response({})

    monkeypatch.setattr("corvin.strategy.rca_generator.litellm.completion", fake_completion)

    generator = RCAGenerator(
        config={"model": "primary-model", "fallback_model": "fallback-model"},
        policy_config={"require_evidence_before_rca": True},
    )
    result = generator.generate(request, evidence)

    assert result.request_id == request.id
    assert result.confidence == RCAConfidence.LOW
    assert result.evidence_references == []
    assert "Insufficient evidence" in result.summary
    assert call_count == 0


def test_fix_strategy_success_path(monkeypatch):
    request = _make_request()
    rca = RCAOutput(
        request_id=request.id,
        summary="Backend errors detected",
        root_cause="Unhandled exception in order-service",
    )
    captured: dict[str, object] = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _completion_response(
            {
                "request_id": request.id,
                "summary": "Roll back and inspect the failing code path.",
                "justification": "The RCA points to a recent backend regression.",
                "actions": [
                    {
                        "title": "Roll back the deployment",
                        "description": "Return to the previous stable version.",
                        "risk_level": "medium",
                        "estimated_impact": "Restores service health quickly.",
                        "requires_approval": True,
                    }
                ],
            }
        )

    monkeypatch.setattr(
        "corvin.strategy.fix_strategy_generator.litellm.completion", fake_completion
    )

    generator = FixStrategyGenerator(
        model_config={"model": "primary-model", "temperature": 0.1, "max_tokens": 512},
        policy_config={"fix_strategy_max_actions": 5, "fix_execution_mode": "review_only"},
    )
    result = generator.generate(request, rca)

    assert result.summary == "Roll back and inspect the failing code path."
    assert len(result.actions) == 1
    assert captured["model"] == "primary-model"
    assert "FixStrategyOutput" in captured["messages"][1]["content"]


def test_action_truncation_to_fix_strategy_max_actions(monkeypatch):
    request = _make_request()
    rca = RCAOutput(
        request_id=request.id,
        summary="Backend errors detected",
        root_cause="Unhandled exception in order-service",
    )

    def fake_completion(**kwargs):
        return _completion_response(
            {
                "request_id": request.id,
                "summary": "Three possible actions.",
                "justification": "Multiple remediation options exist.",
                "actions": [
                    {
                        "title": "Action 1",
                        "description": "First action",
                        "risk_level": "low",
                        "estimated_impact": "Low impact",
                        "requires_approval": True,
                    },
                    {
                        "title": "Action 2",
                        "description": "Second action",
                        "risk_level": "medium",
                        "estimated_impact": "Medium impact",
                        "requires_approval": True,
                    },
                    {
                        "title": "Action 3",
                        "description": "Third action",
                        "risk_level": "high",
                        "estimated_impact": "High impact",
                        "requires_approval": True,
                    },
                ],
            }
        )

    monkeypatch.setattr(
        "corvin.strategy.fix_strategy_generator.litellm.completion", fake_completion
    )

    generator = FixStrategyGenerator(
        model_config={"model": "primary-model", "temperature": 0.1, "max_tokens": 512},
        policy_config={"fix_strategy_max_actions": 2, "fix_execution_mode": "review_only"},
    )
    result = generator.generate(request, rca)

    assert [action.title for action in result.actions] == ["Action 1", "Action 2"]


def test_requires_approval_forced_true_in_review_only_mode(monkeypatch):
    """Non-trivial (non-low-risk) actions must be forced to require approval.

    Since the acknowledgment-option change, purely informational all-low-risk
    strategies are exempt so the UI can offer "Acknowledge & Close" — the
    forcing applies as soon as any action is medium/high risk.
    """
    request = _make_request()
    rca = RCAOutput(
        request_id=request.id,
        summary="Backend errors detected",
        root_cause="Unhandled exception in order-service",
    )

    def fake_completion(**kwargs):
        return _completion_response(
            {
                "request_id": request.id,
                "summary": "Review-only fix strategy.",
                "justification": "V1 requires human approval.",
                "actions": [
                    {
                        "title": "Restart deployment",
                        "description": "Rolling restart of the latest rollout.",
                        "risk_level": "medium",
                        "estimated_impact": "Brief pod churn",
                        "requires_approval": False,
                    },
                    {
                        "title": "Investigate deployment",
                        "description": "Check the latest rollout.",
                        "risk_level": "low",
                        "estimated_impact": "Low impact",
                        "requires_approval": False,
                    },
                ],
            }
        )

    monkeypatch.setattr(
        "corvin.strategy.fix_strategy_generator.litellm.completion", fake_completion
    )

    generator = FixStrategyGenerator(
        model_config={"model": "primary-model", "temperature": 0.1, "max_tokens": 512},
        policy_config={"fix_strategy_max_actions": 5, "fix_execution_mode": "review_only"},
    )
    result = generator.generate(request, rca)

    assert all(action.requires_approval for action in result.actions)


def test_requires_approval_not_forced_for_all_informational_actions(monkeypatch):
    """All-low-risk strategies keep requires_approval=False (Acknowledge & Close path)."""
    request = _make_request()
    rca = RCAOutput(
        request_id=request.id,
        summary="Backend errors detected",
        root_cause="Transient upstream blip — no action needed",
    )

    def fake_completion(**kwargs):
        return _completion_response(
            {
                "request_id": request.id,
                "summary": "Informational only.",
                "justification": "No cluster changes required.",
                "actions": [
                    {
                        "title": "Monitor error rate",
                        "description": "Watch dashboards for 30 minutes.",
                        "risk_level": "low",
                        "estimated_impact": "None",
                        "requires_approval": False,
                    }
                ],
            }
        )

    monkeypatch.setattr(
        "corvin.strategy.fix_strategy_generator.litellm.completion", fake_completion
    )

    generator = FixStrategyGenerator(
        model_config={"model": "primary-model", "temperature": 0.1, "max_tokens": 512},
        policy_config={"fix_strategy_max_actions": 5, "fix_execution_mode": "review_only"},
    )
    result = generator.generate(request, rca)

    assert all(not action.requires_approval for action in result.actions)


def test_engine_passes_built_system_prompt_into_rca_generation():
    request = _make_request()
    evidence = _make_evidence(request.id)
    rca = RCAOutput(
        request_id=request.id,
        summary="Backend errors detected",
        root_cause="Unhandled exception in order-service",
    )
    fix_strategy = FixStrategyOutput(
        request_id=request.id,
        summary="Review the deployment and roll back if needed.",
        justification="Matches the RCA.",
        actions=[
            FixAction(
                title="Review deployment",
                description="Inspect rollout changes.",
                risk_level=RiskLevel.LOW,
                estimated_impact="Minimal",
                requires_approval=True,
            )
        ],
    )

    mock_enrichment = MagicMock()
    mock_enrichment.enrich.return_value = evidence
    mock_prompt_builder = MagicMock()
    mock_prompt_builder.build.return_value = "built system prompt"
    mock_rca = MagicMock()
    mock_rca.generate.return_value = rca
    mock_fix = MagicMock()
    mock_fix.generate.return_value = fix_strategy

    engine = InvestigationEngine(
        enrichment=mock_enrichment,
        rca=mock_rca,
        fix_strategy=mock_fix,
        prompt_builder=mock_prompt_builder,
    )
    engine.run(request)

    mock_rca.generate.assert_called_once_with(
        request,
        evidence,
        system_prompt="built system prompt",
    )


# ---------------------------------------------------------------------------
# Proxy settings forwarding
# ---------------------------------------------------------------------------


def test_rca_proxy_settings_passed_to_litellm(monkeypatch):
    """LITELLM_ENDPOINT and LITELLM_API_KEY env vars must flow into api_base / api_key."""
    request = _make_request()
    evidence = _make_evidence(request.id)
    captured: dict[str, object] = {}

    monkeypatch.setenv("LITELLM_ENDPOINT", "https://my-proxy.example.com:4000")
    monkeypatch.setenv("LITELLM_API_KEY", "proxy-test-key")

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _completion_response(
            {
                "request_id": request.id,
                "summary": "RCA summary.",
                "root_cause": "Root cause.",
                "contributing_factors": [],
                "confidence": "medium",
                "evidence_references": [],
            }
        )

    monkeypatch.setattr("corvin.strategy.rca_generator.litellm.completion", fake_completion)

    generator = RCAGenerator(
        config={"model": "primary-model", "temperature": 0.1, "max_tokens": 512},
        policy_config={"require_evidence_before_rca": True},
    )
    generator.generate(request, evidence)

    assert captured.get("api_base") == "https://my-proxy.example.com:4000"
    assert captured.get("api_key") == "proxy-test-key"


def test_fix_strategy_proxy_settings_passed_to_litellm(monkeypatch):
    """LITELLM_ENDPOINT and LITELLM_API_KEY env vars must flow into fix strategy calls."""
    request = _make_request()
    rca = RCAOutput(
        request_id=request.id,
        summary="Backend errors detected",
        root_cause="Unhandled exception",
    )
    captured: dict[str, object] = {}

    monkeypatch.setenv("LITELLM_ENDPOINT", "https://my-proxy.example.com:4000")
    monkeypatch.setenv("LITELLM_API_KEY", "proxy-test-key")

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _completion_response(
            {
                "request_id": request.id,
                "summary": "Fix strategy summary.",
                "justification": "Based on RCA.",
                "actions": [],
            }
        )

    monkeypatch.setattr(
        "corvin.strategy.fix_strategy_generator.litellm.completion", fake_completion
    )

    generator = FixStrategyGenerator(
        model_config={"model": "primary-model", "temperature": 0.1, "max_tokens": 512},
        policy_config={"fix_strategy_max_actions": 5, "fix_execution_mode": "review_only"},
    )
    generator.generate(request, rca)

    assert captured.get("api_base") == "https://my-proxy.example.com:4000"
    assert captured.get("api_key") == "proxy-test-key"


# ---------------------------------------------------------------------------
# Structured output mode
# ---------------------------------------------------------------------------


def test_rca_structured_output_mode_enabled(monkeypatch):
    """RCA completion call must include response_format with json_schema type."""
    request = _make_request()
    evidence = _make_evidence(request.id)
    captured: dict[str, object] = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _completion_response(
            {
                "request_id": request.id,
                "summary": "RCA summary.",
                "root_cause": "Root cause.",
                "contributing_factors": [],
                "confidence": "medium",
                "evidence_references": [],
            }
        )

    monkeypatch.setattr("corvin.strategy.rca_generator.litellm.completion", fake_completion)

    generator = RCAGenerator(
        config={"model": "primary-model", "temperature": 0.1, "max_tokens": 512},
        policy_config={"require_evidence_before_rca": True},
    )
    generator.generate(request, evidence)

    assert "response_format" in captured
    rf = captured["response_format"]
    assert isinstance(rf, dict)
    assert rf["type"] == "json_object"


def test_fix_strategy_structured_output_mode_enabled(monkeypatch):
    """Fix strategy completion call must include response_format with json_schema type."""
    request = _make_request()
    rca = RCAOutput(
        request_id=request.id,
        summary="Backend errors detected",
        root_cause="Unhandled exception",
    )
    captured: dict[str, object] = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _completion_response(
            {
                "request_id": request.id,
                "summary": "Fix strategy summary.",
                "justification": "Based on RCA.",
                "actions": [],
            }
        )

    monkeypatch.setattr(
        "corvin.strategy.fix_strategy_generator.litellm.completion", fake_completion
    )

    generator = FixStrategyGenerator(
        model_config={"model": "primary-model", "temperature": 0.1, "max_tokens": 512},
        policy_config={"fix_strategy_max_actions": 5, "fix_execution_mode": "review_only"},
    )
    generator.generate(request, rca)

    assert "response_format" in captured
    rf = captured["response_format"]
    assert isinstance(rf, dict)
    assert rf["type"] == "json_object"


# ---------------------------------------------------------------------------
# Parsed structured output path
# ---------------------------------------------------------------------------


def test_rca_handles_parsed_structured_response(monkeypatch):
    """RCA generator must handle a LiteLLM response where .parsed is set instead of .content."""
    request = _make_request()
    evidence = _make_evidence(request.id)
    parsed_dict = {
        "request_id": request.id,
        "summary": "Parsed-path RCA summary.",
        "root_cause": "Parsed-path root cause.",
        "contributing_factors": ["spike"],
        "confidence": "high",
        "evidence_references": ["elastic_logs[0]"],
    }

    def fake_completion(**kwargs):
        return _structured_completion_response(parsed_dict)

    monkeypatch.setattr("corvin.strategy.rca_generator.litellm.completion", fake_completion)

    generator = RCAGenerator(
        config={"model": "primary-model", "temperature": 0.1, "max_tokens": 512},
        policy_config={"require_evidence_before_rca": True},
    )
    result = generator.generate(request, evidence)

    assert result.summary == "Parsed-path RCA summary."
    assert result.confidence == RCAConfidence.HIGH


def test_fix_strategy_handles_parsed_structured_response(monkeypatch):
    """Fix strategy generator must handle a LiteLLM response where .parsed is set."""
    request = _make_request()
    rca = RCAOutput(
        request_id=request.id,
        summary="Backend errors detected",
        root_cause="Unhandled exception",
    )
    parsed_dict = {
        "request_id": request.id,
        "summary": "Parsed-path fix strategy.",
        "justification": "From parsed structured output.",
        "actions": [
            {
                "title": "Parsed action",
                "description": "Action from parsed path.",
                "risk_level": "medium",
                "estimated_impact": "Moderate impact.",
                "requires_approval": False,
            }
        ],
    }

    def fake_completion(**kwargs):
        return _structured_completion_response(parsed_dict)

    monkeypatch.setattr(
        "corvin.strategy.fix_strategy_generator.litellm.completion", fake_completion
    )

    generator = FixStrategyGenerator(
        model_config={"model": "primary-model", "temperature": 0.1, "max_tokens": 512},
        policy_config={"fix_strategy_max_actions": 5, "fix_execution_mode": "review_only"},
    )
    result = generator.generate(request, rca)

    assert result.summary == "Parsed-path fix strategy."
    # review_only policy must force requires_approval = True even on the parsed path
    assert all(action.requires_approval for action in result.actions)

def test_fix_strategy_generate_stream_fallback_includes_justification(monkeypatch):
    """H-2 regression: when both streaming and non-streaming completion fail,
    generate_stream must yield a valid FixStrategyOutput including the required
    justification field (FixStrategyOutput uses extra='forbid' and
    justification is mandatory).
    """
    request = _make_request()
    rca = RCAOutput(
        request_id=request.id,
        summary="Backend errors detected",
        root_cause="Unhandled exception in order-service",
    )

    def always_fail(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "corvin.strategy.fix_strategy_generator.litellm.completion", always_fail
    )

    generator = FixStrategyGenerator(
        model_config={"model": "primary-model", "temperature": 0.1, "max_tokens": 512},
        policy_config={"fix_strategy_max_actions": 5, "fix_execution_mode": "review_only"},
    )

    events = list(generator.generate_stream(request, rca))
    final = [out for (_, out) in events if out is not None]
    assert len(final) == 1
    fs = final[0]
    assert fs.actions == []
    assert fs.summary == "Could not generate fix strategy."
    assert fs.justification and "fallback" in fs.justification.lower()


def test_fix_strategy_generate_stream_unparseable_includes_justification(monkeypatch):
    """H-2 regression: when streaming succeeds but the accumulated payload is
    not valid JSON, generate_stream must yield a fallback FixStrategyOutput
    that includes the required justification field."""
    request = _make_request()
    rca = RCAOutput(
        request_id=request.id,
        summary="Backend errors detected",
        root_cause="Unhandled exception in order-service",
    )

    def fake_stream(**kwargs):
        # streaming path (kwargs has stream=True): yield chunks of garbage
        if kwargs.get("stream"):
            chunks = ["this ", "is ", "not json"]
            for c in chunks:
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=c))]
                )

    monkeypatch.setattr(
        "corvin.strategy.fix_strategy_generator.litellm.completion", fake_stream
    )

    generator = FixStrategyGenerator(
        model_config={"model": "primary-model", "temperature": 0.1, "max_tokens": 512},
        policy_config={"fix_strategy_max_actions": 5, "fix_execution_mode": "review_only"},
    )

    events = list(generator.generate_stream(request, rca))
    final = [out for (_, out) in events if out is not None]
    assert len(final) == 1
    fs = final[0]
    assert fs.summary == "Could not parse fix strategy."
    assert fs.justification and "json" in fs.justification.lower()
