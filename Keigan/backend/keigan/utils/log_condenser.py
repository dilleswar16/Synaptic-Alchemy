"""Turns thousands of log lines into a few dozen *patterns* with counts — the biggest accuracy and token win.

Each line is normalised into a template (numbers, ids, GUIDs, hex, timestamps, URLs, quoted values replaced by
typed tokens). Templates are counted, compared with the same query over a baseline window, and ranked so that
*new* or *sharply increased* error patterns come first.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from keigan.entities.status_values import RiskLevel

_NORMALIZATION_RULES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(rule_pattern, re.IGNORECASE), replacement_token)
    for rule_pattern, replacement_token in (
        (r"<[A-Z_]+(?:_\d+)?>", "<MASKED>"),
        (r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b", "<TIMESTAMP>"),
        (r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<GUID>"),
        (r"https?://[^\s\"'<>]+", "<URL>"),
        (r"\b(?:\d{1,3}\.){3}(?:\d{1,3}|x)\.?(?:x)?\b", "<IP>"),
        (r"\b0x[0-9a-f]+\b", "<HEX>"),
        (r"\b[0-9a-f]{16,}\b", "<HEX>"),
        (r"(?<=[=:])\s*\"[^\"]{1,200}\"", " <VALUE>"),
        (r"'[^']{1,200}'", "<VALUE>"),
        (r"\b\d+(?:\.\d+)?\s?(?:ms|s|sec|seconds|minutes|mb|kb|gb|%)\b", "<QUANTITY>"),
        (r"\b\d+(?:\.\d+)?\b", "<NUMBER>"),
        (r"\s+", " "),
    )
)

LEVEL_SEVERITY_ORDER = {"critical": 0, "fatal": 0, "error": 1, "err": 1, "warning": 2, "warn": 2, "information": 3, "info": 3, "debug": 4, "verbose": 4, "trace": 4}


def normalize_log_message(message_text: str, maximum_length: int = 400) -> str:
    template_text = message_text[:2000]
    for rule_pattern, replacement_token in _NORMALIZATION_RULES:
        template_text = rule_pattern.sub(replacement_token, template_text)
    return template_text.strip()[:maximum_length]


@dataclass
class LogPattern:
    template: str
    level: str
    count: int = 0
    baseline_count: int = 0
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    sample_lines: list[str] = field(default_factory=list)
    dimension_values: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def is_new_pattern(self) -> bool:
        return self.count > 0 and self.baseline_count == 0

    @property
    def change_ratio(self) -> float | None:
        if self.baseline_count == 0:
            return None
        return round(self.count / self.baseline_count, 2)

    def to_dictionary(self) -> dict[str, Any]:
        return {
            "template": self.template,
            "level": self.level,
            "count": self.count,
            "baselineCount": self.baseline_count,
            "firstSeenAt": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "lastSeenAt": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "isNewPattern": self.is_new_pattern,
            "changeRatio": self.change_ratio,
            "sampleLinesMasked": self.sample_lines,
            "topDimensionValues": {
                dimension_name: dict(sorted(value_counts.items(), key=lambda item: -item[1])[:5])
                for dimension_name, value_counts in self.dimension_values.items()
            },
        }


@dataclass
class CondensedLogs:
    patterns: list[LogPattern]
    total_record_count: int
    baseline_record_count: int

    @property
    def strongest_signal(self) -> str:
        for log_pattern in self.patterns:
            severity_rank = LEVEL_SEVERITY_ORDER.get(log_pattern.level.lower(), 3)
            if severity_rank <= 1 and log_pattern.count >= 5 and (log_pattern.is_new_pattern or (log_pattern.change_ratio or 0) >= 5):
                return RiskLevel.HIGH
        for log_pattern in self.patterns:
            if LEVEL_SEVERITY_ORDER.get(log_pattern.level.lower(), 3) <= 2 and (log_pattern.is_new_pattern or (log_pattern.change_ratio or 0) >= 2):
                return RiskLevel.MEDIUM
        return RiskLevel.LOW


def _record_message(record: dict[str, Any], message_fields: tuple[str, ...]) -> str:
    for message_field in message_fields:
        field_value = record.get(message_field)
        if field_value:
            return str(field_value)
    return " ".join(f"{key}={value}" for key, value in record.items() if value not in (None, ""))[:2000]


def _record_level(record: dict[str, Any], level_fields: tuple[str, ...]) -> str:
    for level_field in level_fields:
        field_value = record.get(level_field)
        if field_value not in (None, ""):
            if isinstance(field_value, (int, float)):
                return {0: "verbose", 1: "information", 2: "warning", 3: "error", 4: "critical"}.get(int(field_value), "information")
            return str(field_value).lower()
    return "information"


def _record_timestamp(record: dict[str, Any], time_fields: tuple[str, ...]) -> datetime | None:
    for time_field in time_fields:
        field_value = record.get(time_field)
        if isinstance(field_value, datetime):
            return field_value
        if isinstance(field_value, str):
            try:
                return datetime.fromisoformat(field_value.replace("Z", "+00:00"))
            except ValueError:
                continue
    return None


def condense_log_records(
    records: list[dict[str, Any]],
    baseline_records: list[dict[str, Any]] | None = None,
    *,
    message_fields: tuple[str, ...] = ("Message", "message", "OuterMessage", "outerMessage", "LogMessage", "log", "msg", "ResultDescription", "_raw", "Reason"),
    level_fields: tuple[str, ...] = ("SeverityLevel", "Level", "level", "log.level", "LogLevel", "severity", "Type"),
    time_fields: tuple[str, ...] = ("TimeGenerated", "timestamp", "@timestamp", "_time", "time"),
    dimension_fields: tuple[str, ...] = ("PodName", "ContainerName", "OperationName", "ResultCode", "Target", "cloud_RoleName", "AppRoleName", "host", "Computer"),
    maximum_patterns: int = 25,
    maximum_samples_per_pattern: int = 2,
) -> CondensedLogs:
    patterns_by_key: dict[tuple[str, str], LogPattern] = {}
    for record in records:
        message_text = _record_message(record, message_fields)
        level_text = _record_level(record, level_fields)
        pattern_key = (normalize_log_message(message_text), level_text)
        log_pattern = patterns_by_key.get(pattern_key)
        if log_pattern is None:
            log_pattern = LogPattern(template=pattern_key[0], level=level_text)
            patterns_by_key[pattern_key] = log_pattern
        log_pattern.count += int(record.get("count_", 1) or 1) if isinstance(record.get("count_"), (int, float)) else 1
        record_time = _record_timestamp(record, time_fields)
        if record_time:
            log_pattern.first_seen_at = min(filter(None, [log_pattern.first_seen_at, record_time]))
            log_pattern.last_seen_at = max(filter(None, [log_pattern.last_seen_at, record_time]))
        if len(log_pattern.sample_lines) < maximum_samples_per_pattern and message_text[:500] not in log_pattern.sample_lines:
            log_pattern.sample_lines.append(message_text[:500])
        for dimension_field in dimension_fields:
            dimension_value = record.get(dimension_field)
            if dimension_value not in (None, ""):
                dimension_counts = log_pattern.dimension_values.setdefault(dimension_field, defaultdict(int))
                dimension_counts[str(dimension_value)[:120]] += 1

    baseline_counts_by_key: dict[tuple[str, str], int] = defaultdict(int)
    for baseline_record in baseline_records or []:
        baseline_key = (normalize_log_message(_record_message(baseline_record, message_fields)), _record_level(baseline_record, level_fields))
        baseline_counts_by_key[baseline_key] += 1
    for pattern_key, log_pattern in patterns_by_key.items():
        log_pattern.baseline_count = baseline_counts_by_key.get(pattern_key, 0)
        log_pattern.dimension_values = {name: dict(counts) for name, counts in log_pattern.dimension_values.items()}

    def ranking_key(log_pattern: LogPattern) -> tuple[int, int, float, int]:
        severity_rank = LEVEL_SEVERITY_ORDER.get(log_pattern.level.lower(), 3)
        novelty_rank = 0 if log_pattern.is_new_pattern else 1
        increase_ratio = -(log_pattern.change_ratio or 0.0)
        return (severity_rank, novelty_rank, increase_ratio, -log_pattern.count)

    ranked_patterns = sorted(patterns_by_key.values(), key=ranking_key)[:maximum_patterns]
    return CondensedLogs(patterns=ranked_patterns, total_record_count=len(records), baseline_record_count=len(baseline_records or []))
