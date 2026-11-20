"""Pure (database-free) alert rules: policy defaults, payload normalisation, fingerprints, maintenance and mute matching.

Shared by the live pipeline and by the in-memory policy preview so both always agree (sample plan 7A.3 to 7A.5).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from keigan.utils.json_path_utils import read_json_path
from keigan.utils.pii_masker import PiiMasker

DEFAULT_NOISE_POLICY: dict[str, Any] = {
    "min_severity": 2,
    "investigate_environments": ["prod"],
    "settle_delay_minutes": 3,
    "no_delay_severities": [0, 1],
    "reopen_window_minutes": 30,
    "group_window_minutes": 10,
    "flap_count": 4,
    "flap_window_minutes": 30,
    "max_investigations_per_hour": 10,
    "investigate_score_threshold": 6.0,
}

SEVERITY_WEIGHTS = {0: 5.0, 1: 4.0, 2: 3.0, 3: 2.0, 4: 1.0}
CRITICALITY_WEIGHTS = {"tier_1": 3.0, "tier_2": 2.0, "tier_3": 1.0}
ENVIRONMENT_WEIGHTS = {"prod": 3.0, "uat": 1.5, "test": 1.0, "dev": 1.0}
SLO_BURN_BOOST = 1.5
RARE_RULE_BOOST = 1.3
RARE_RULE_FIRING_COUNT = 3

SEVERITY_WORDS = {"critical": 0, "fatal": 0, "emergency": 0, "sev0": 0, "p1": 1, "high": 1, "major": 1, "sev1": 1, "error": 2, "sev2": 2, "p2": 2,
                  "medium": 2, "moderate": 3, "warning": 3, "warn": 3, "sev3": 3, "p3": 3, "low": 4, "minor": 4, "info": 4, "informational": 4, "sev4": 4, "p4": 4}
CANONICAL_FIELDS = ("externalId", "ruleId", "ruleName", "status", "severity", "resourceRef", "serviceHint", "environment", "startedAt", "resolvedAt", "summary", "description", "link", "labels")

DEFAULT_GENERIC_FIELD_MAPPING = {name: f"$.{name}" for name in CANONICAL_FIELDS if name != "serviceHint"} | {"serviceHint": "$.service"}
ELASTIC_FALLBACK_PATHS = {
    "externalId": ["$.externalId", "$.alertId", "$.alert.id", "$.kibana.alert.uuid"],
    "ruleId": ["$.ruleId", "$.rule.id", "$.kibana.alert.rule.uuid"],
    "ruleName": ["$.ruleName", "$.rule.name", "$.kibana.alert.rule.name"],
    "status": ["$.status", "$.alert.actionGroup", "$.kibana.alert.status", "$.alert.status"],
    "severity": ["$.severity", "$.kibana.alert.severity"],
    "resourceRef": ["$.resourceRef", "$.host.name", "$.kibana.alert.rule.parameters.index"],
    "serviceHint": ["$.service.name", "$.serviceName", "$.kubernetes.namespace", "$.context.service"],
    "environment": ["$.environment", "$.labels.environment"],
    "startedAt": ["$.startedAt", "$.date", "$.@timestamp", "$.kibana.alert.start"],
    "resolvedAt": ["$.resolvedAt"],
    "summary": ["$.summary", "$.reason", "$.kibana.alert.reason", "$.context.reason"],
    "description": ["$.description", "$.rule.description"],
    "link": ["$.link", "$.kibanaBaseUrl", "$.alert.url"],
    "labels": ["$.labels", "$.tags"],
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def merge_policy(stored_settings: dict[str, Any] | None) -> dict[str, Any]:
    merged = {**DEFAULT_NOISE_POLICY, **{key: value for key, value in (stored_settings or {}).items() if key in DEFAULT_NOISE_POLICY}}
    merged["min_severity"] = int(merged["min_severity"])
    merged["no_delay_severities"] = sorted({int(value) for value in merged["no_delay_severities"]})
    merged["investigate_environments"] = [str(value).lower() for value in merged["investigate_environments"]]
    return merged


def policy_sentences(policy: dict[str, Any]) -> list[str]:
    """Plain-language statement of the policy, shown in logs and in decision reasons."""
    return [
        f"Investigate alerts of severity Sev {policy['min_severity']} or more severe.",
        f"Only investigate alerts from {', '.join(policy['investigate_environments']) or 'no'} environments. Others are recorded.",
        f"Wait {policy['settle_delay_minutes']} min before investigating; skip the wait for " + ", ".join(f"Sev {value}" for value in policy["no_delay_severities"]) + ".",
        f"Treat a repeat of the same alert as one alert, and for {policy['reopen_window_minutes']} min after it clears.",
        f"Treat alerts on the same or dependent services within {policy['group_window_minutes']} min as one problem.",
        f"If an alert changes state {policy['flap_count']} times in {policy['flap_window_minutes']} min, treat it as flapping.",
        f"Start at most {policy['max_investigations_per_hour']} investigations per hour for this application.",
    ]


@dataclass
class CanonicalAlert:
    external_id: str
    rule_id: str
    rule_name: str
    status: str  # firing | resolved
    severity: int
    resource_ref: str | None = None
    service_hint: str | None = None
    environment: str | None = None
    started_at: datetime | None = None
    resolved_at: datetime | None = None
    summary: str = ""
    description: str | None = None
    link: str | None = None
    labels: dict[str, str] = field(default_factory=dict)

    def to_dictionary(self) -> dict[str, Any]:
        return {
            "externalId": self.external_id, "ruleId": self.rule_id, "ruleName": self.rule_name, "status": self.status, "severity": self.severity,
            "resourceRef": self.resource_ref, "serviceHint": self.service_hint, "environment": self.environment,
            "startedAt": self.started_at.isoformat() if self.started_at else None, "resolvedAt": self.resolved_at.isoformat() if self.resolved_at else None,
            "summary": self.summary, "description": self.description, "link": self.link, "labels": self.labels,
        }


def parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, tz=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def parse_severity(value: Any, severity_mapping: dict[str, Any] | None = None, default: int = 3) -> int:
    if value is None:
        return default
    text = str(value).strip().lower()
    for mapped_key, mapped_value in (severity_mapping or {}).items():
        if str(mapped_key).strip().lower() == text:
            return max(0, min(4, int(mapped_value)))
    if text in SEVERITY_WORDS:
        return SEVERITY_WORDS[text]
    digits = re.search(r"\d", text)
    if digits:
        return max(0, min(4, int(digits.group())))
    return default


def parse_status(value: Any) -> str:
    return "resolved" if str(value or "").strip().lower() in ("resolved", "recovered", "ok", "closed", "cleared", "normal", "inactive", "recover") else "firing"


def _first_value(payload: Any, paths: list[str]) -> Any:
    for path in paths:
        found = read_json_path(payload, path)
        if found not in (None, "", []):
            return found
    return None


def _label_dictionary(raw_labels: Any) -> dict[str, str]:
    if isinstance(raw_labels, dict):
        return {str(key): str(value)[:200] for key, value in raw_labels.items() if isinstance(value, (str, int, float, bool))}
    if isinstance(raw_labels, list):
        return {f"tag{index}": str(value)[:200] for index, value in enumerate(raw_labels[:20])}
    return {}


def normalise_payload(source_tool: str, payload: dict[str, Any], field_mapping: dict[str, Any] | None = None, severity_mapping: dict[str, Any] | None = None) -> CanonicalAlert:
    """Turn one raw payload into a :class:`CanonicalAlert`. Raises ``ValueError`` with a readable message when it cannot."""
    if not isinstance(payload, dict):
        raise ValueError("The payload is not a JSON object.")
    if source_tool == "azure_monitor":
        return _normalise_azure_common_schema(payload)
    if source_tool == "elastic":
        extracted = {name: _first_value(payload, paths) for name, paths in ELASTIC_FALLBACK_PATHS.items()}
        extracted.update({name: read_json_path(payload, path) for name, path in (field_mapping or {}).items() if path and name in CANONICAL_FIELDS})
    else:  # generic and keigan_slo
        mapping = {**DEFAULT_GENERIC_FIELD_MAPPING, **{name: path for name, path in (field_mapping or {}).items() if path}}
        extracted = {name: read_json_path(payload, mapping.get(name)) for name in CANONICAL_FIELDS}
    rule_name = str(extracted.get("ruleName") or extracted.get("ruleId") or "").strip()
    if not rule_name:
        raise ValueError("No rule name found: map the rule name field (for example $.ruleName).")
    external_id = str(extracted.get("externalId") or hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:24])
    started_at = parse_timestamp(extracted.get("startedAt"))
    status = parse_status(extracted.get("status"))
    return CanonicalAlert(
        external_id=external_id, rule_id=str(extracted.get("ruleId") or rule_name), rule_name=rule_name[:400], status=status,
        severity=parse_severity(extracted.get("severity"), severity_mapping), resource_ref=_text_or_none(extracted.get("resourceRef")),
        service_hint=_text_or_none(extracted.get("serviceHint")), environment=_text_or_none(extracted.get("environment")),
        started_at=started_at, resolved_at=parse_timestamp(extracted.get("resolvedAt")) or (started_at if status == "resolved" else None),
        summary=str(extracted.get("summary") or rule_name)[:1000], description=_text_or_none(extracted.get("description")), link=_text_or_none(extracted.get("link")),
        labels=_label_dictionary(extracted.get("labels")),
    )


def _text_or_none(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


def _normalise_azure_common_schema(payload: dict[str, Any]) -> CanonicalAlert:
    essentials = read_json_path(payload, "$.data.essentials")
    if not isinstance(essentials, dict):
        raise ValueError("Not an Azure common alert schema payload: data.essentials is missing. Enable the common alert schema on the action group webhook.")
    target_ids = essentials.get("alertTargetIDs") or []
    resource_ref = str(target_ids[0]) if target_ids else None
    condition_description = ""
    condition_all_of = read_json_path(payload, "$.data.alertContext.condition.allOf")
    if isinstance(condition_all_of, list) and condition_all_of and isinstance(condition_all_of[0], dict):
        first_condition = condition_all_of[0]
        condition_description = f"{first_condition.get('metricName', '')} {first_condition.get('operator', '')} {first_condition.get('threshold', '')} (observed {first_condition.get('metricValue', '')})".strip()
    monitor_condition = str(essentials.get("monitorCondition", "Fired"))
    rule_name = str(essentials.get("alertRule") or "Unnamed Azure alert rule")
    labels = {
        key: str(value)[:200] for key, value in {
            "monitoringService": essentials.get("monitoringService"), "signalType": essentials.get("signalType"),
            "targetResourceType": (essentials.get("targetResourceTypes") or [None])[0], "targetResourceName": (resource_ref or "").rsplit("/", 1)[-1] or None,
            "targetResourceGroup": (essentials.get("targetResourceGroup")),
        }.items() if value
    }
    resolved_at = parse_timestamp(essentials.get("resolvedDateTime"))
    return CanonicalAlert(
        external_id=str(essentials.get("alertId") or ""), rule_id=str(essentials.get("alertRule") or rule_name), rule_name=rule_name[:400],
        status="resolved" if monitor_condition.lower() == "resolved" else "firing", severity=parse_severity(essentials.get("severity")),
        resource_ref=resource_ref, started_at=parse_timestamp(essentials.get("firedDateTime")), resolved_at=resolved_at,
        summary=(f"{rule_name}: {condition_description}" if condition_description else str(essentials.get("description") or rule_name))[:1000],
        description=_text_or_none(essentials.get("description")),
        link=f"https://portal.azure.com/#@/resource{resource_ref}/alerts" if resource_ref else None, labels=labels,
    ) if essentials.get("alertId") else _raise_missing_alert_id()


def _raise_missing_alert_id() -> CanonicalAlert:
    raise ValueError("Azure payload has no data.essentials.alertId.")


def mask_alert_text(alert: CanonicalAlert) -> None:
    masker = PiiMasker()
    alert.rule_name = masker.mask_text(alert.rule_name)
    alert.summary = masker.mask_text(alert.summary)
    alert.description = masker.mask_text(alert.description) if alert.description else None
    alert.labels = {key: masker.mask_text(value) for key, value in alert.labels.items()}


def compute_fingerprint(source_identifier: str, rule_identifier: str, resource_or_service: str | None, labels: dict[str, str]) -> str:
    """Stable across label order (sorted), insensitive to case of the resource reference."""
    identifying_labels = "&".join(f"{key}={value}" for key, value in sorted(labels.items()))
    return hashlib.sha256(f"{source_identifier}|{rule_identifier}|{(resource_or_service or '').lower()}|{identifying_labels}".encode()).hexdigest()


def maintenance_window_is_active(window_start: datetime, window_end: datetime, repeats_weekly: bool, reference_time: datetime) -> bool:
    if window_start <= reference_time <= window_end:
        return True
    if repeats_weekly and reference_time > window_end:
        weeks_elapsed = (reference_time - window_start).days // 7
        shifted_start = window_start + timedelta(weeks=weeks_elapsed)
        return shifted_start <= reference_time <= shifted_start + (window_end - window_start)
    return False


def maintenance_window_applies(window: Any, service_id: str | None, environment_name: str | None, reference_time: datetime) -> bool:
    if not maintenance_window_is_active(window.starts_at, window.ends_at, window.repeats_weekly, reference_time):
        return False
    service_ids = window.applies_to_service_ids_json or []
    environments = [value.lower() for value in (window.applies_to_environments_json or [])]
    return (not service_ids or (service_id in service_ids)) and (not environments or (environment_name or "prod").lower() in environments)


def mute_rule_matches(mute_rule: Any, rule_name: str, service_id: str | None, severity: int, source_id: str | None, labels: dict[str, str], reference_time: datetime) -> bool:
    if mute_rule.expires_at <= reference_time:
        return False
    matcher = mute_rule.matcher_json or {}
    contains_text = str(matcher.get("rule_name_contains") or "").strip().lower()
    if contains_text and contains_text not in rule_name.lower():
        return False
    if matcher.get("service_id") and matcher["service_id"] != service_id:
        return False
    if matcher.get("alert_source_id") and matcher["alert_source_id"] != source_id:
        return False
    if matcher.get("severity") is not None and int(matcher["severity"]) != severity:
        return False
    if matcher.get("label_key") and labels.get(str(matcher["label_key"])) != str(matcher.get("label_value", "")):
        return False
    return any(matcher.get(key) not in (None, "") for key in ("rule_name_contains", "service_id", "alert_source_id", "severity", "label_key"))


def severity_label(severity: int) -> str:
    return f"Sev {severity}"


def calculate_priority_score(severity: int, criticality_tier: str, environment_name: str | None, slo_is_burning: bool, rule_is_rare: bool) -> float:
    score = SEVERITY_WEIGHTS.get(severity, 1.0) * CRITICALITY_WEIGHTS.get(criticality_tier, 2.0) * ENVIRONMENT_WEIGHTS.get((environment_name or "prod").lower(), 1.0)
    if slo_is_burning:
        score *= SLO_BURN_BOOST
    if rule_is_rare:
        score *= RARE_RULE_BOOST
    return round(score, 2)


def seconds_text(total_seconds: float) -> str:
    total_seconds = int(max(0, total_seconds))
    return f"{total_seconds} s" if total_seconds < 120 else f"{total_seconds // 60} min"
