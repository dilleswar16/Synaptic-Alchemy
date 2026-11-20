"""keigan/services/alert_rules.py: masking of free text in incoming alerts (V12)."""

from __future__ import annotations

from keigan.services.alert_rules import CanonicalAlert, mask_alert_text


def _alert(**overrides: object) -> CanonicalAlert:
    values: dict[str, object] = {"external_id": "1", "rule_id": "rule-1", "rule_name": "Errors for taro@example.com", "status": "firing", "severity": 2}
    values.update(overrides)
    return CanonicalAlert(**values)  # type: ignore[arg-type]


def test_rule_name_is_masked() -> None:
    alert = _alert()
    mask_alert_text(alert)
    assert "taro@example.com" not in alert.rule_name
    assert alert.rule_name.startswith("Errors for ")


def test_rule_identifier_is_left_alone_because_fingerprints_and_mute_rules_match_on_it() -> None:
    alert = _alert(rule_id="rule-1")
    mask_alert_text(alert)
    assert alert.rule_id == "rule-1"
