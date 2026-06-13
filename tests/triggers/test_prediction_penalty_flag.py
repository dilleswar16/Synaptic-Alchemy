"""
Prediction penalty feature flag (prediction_penalty_enabled).

The penalty feedback loop is disabled by default — it fired on nearly every
investigation, appended one learnings file per incident with no deduplication,
and polluted RCA prompts with noise. These tests pin the off-by-default
behaviour and the policy-flag plumbing on both the write path
(penalize_prediction) and the read path (prompt injection).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from corvin.triggers.prediction_penalty import (
    is_penalty_feature_enabled,
    penalize_prediction,
)


def test_feature_disabled_by_default_policy() -> None:
    """Shipped investigation.yaml sets prediction_penalty_enabled: false."""
    assert is_penalty_feature_enabled() is False


def test_flag_reads_policy_value() -> None:
    with patch(
        "corvin.core.config_loader.load_config",
        return_value={"prediction_penalty_enabled": True},
    ):
        assert is_penalty_feature_enabled() is True


def test_flag_defaults_false_when_key_absent() -> None:
    with patch("corvin.core.config_loader.load_config", return_value={}):
        assert is_penalty_feature_enabled() is False


def test_penalize_prediction_is_noop_when_disabled() -> None:
    """With the flag off, no DB session is opened and None is returned."""
    result = MagicMock()
    with patch(
        "corvin.triggers.prediction_penalty.is_penalty_feature_enabled",
        return_value=False,
    ), patch("corvin.triggers.prediction_penalty.get_session") as fake_session:
        assert penalize_prediction(result) is None
    fake_session.assert_not_called()
