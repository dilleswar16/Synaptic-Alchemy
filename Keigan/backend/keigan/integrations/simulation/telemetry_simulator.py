"""Deterministic, scenario-driven telemetry for local development and demos.

Background traffic, errors and metrics follow daily seasonality with stable pseudo-randomness (same inputs → same
outputs). Active *scenario windows* (stored in ``platform_setting['simulation_configuration']``) inject realistic
failures into the affected services; *conditions* add slow trends (memory leaks, budget burn) for predictive demos.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from keigan.integrations.simulation.simulation_scenarios import BACKGROUND_ERROR_TEMPLATES, SCENARIO_CATALOG, SimulationScenario
from keigan.integrations.telemetry_gateway import (
    ChangeEvent,
    LogQueryResult,
    MetricQueryResult,
    MetricSeries,
    ProbeResult,
    TelemetryQuery,
    TelemetryTarget,
)

SIMULATION_SETTING_KEY = "simulation_configuration"
CONFIGURATION_REFRESH_SECONDS = 15

BASE_REQUESTS_PER_FIVE_MINUTES = {
    "api_management": 3200, "app_service": 1500, "aks": 2600, "function_app": 900, "logic_app": 60, "data_factory": 2,
    "sql_database": 4000, "saas_service": 1, "mainframe_subsystem": 12, "batch_job_stream": 1, "server": 1, "network_appliance": 1,
}
BASELINE_ERROR_RATIO = 0.0007
LOW_VOLUME_SERVICE_TYPES = ("saas_service", "batch_job_stream", "server", "network_appliance", "data_factory")
LOW_VOLUME_BASELINE_FAILURE_PROBABILITY = 0.0002
BASELINE_LATENCY_MILLISECONDS = 185.0


@dataclass
class ScenarioWindow:
    scenario_key: str
    application_id: str
    primary_service_ids: list[str]
    dependency_service_ids: list[str]
    started_at: datetime
    ended_at: datetime | None
    external_incident_number: str | None = None

    @property
    def scenario(self) -> SimulationScenario:
        return SCENARIO_CATALOG[self.scenario_key]

    def overlaps(self, range_start: datetime, range_end: datetime) -> bool:
        return self.started_at < range_end and (self.ended_at is None or self.ended_at > range_start)

    def intensity_at(self, timestamp: datetime) -> float:
        if timestamp < self.started_at or (self.ended_at and timestamp >= self.ended_at):
            return 0.0
        return min(1.0, (timestamp - self.started_at).total_seconds() / 300.0 + 0.2)

    @classmethod
    def from_dictionary(cls, window_entry: dict[str, Any]) -> "ScenarioWindow":
        return cls(
            scenario_key=window_entry["scenario_key"],
            application_id=window_entry["application_id"],
            primary_service_ids=list(window_entry.get("primary_service_ids", [])),
            dependency_service_ids=list(window_entry.get("dependency_service_ids", [])),
            started_at=datetime.fromisoformat(window_entry["started_at"]),
            ended_at=datetime.fromisoformat(window_entry["ended_at"]) if window_entry.get("ended_at") else None,
            external_incident_number=window_entry.get("external_incident_number"),
        )

    def to_dictionary(self) -> dict[str, Any]:
        return {
            "scenario_key": self.scenario_key,
            "application_id": self.application_id,
            "primary_service_ids": self.primary_service_ids,
            "dependency_service_ids": self.dependency_service_ids,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "external_incident_number": self.external_incident_number,
        }


def _stable_random(*seed_parts: object) -> random.Random:
    seed_digest = hashlib.sha256("|".join(str(seed_part) for seed_part in seed_parts).encode("utf-8")).hexdigest()
    return random.Random(int(seed_digest[:16], 16))


def _daily_traffic_factor(timestamp: datetime) -> float:
    """Business-hours curve peaking around 03:00 UTC (12:00 in Tokyo), never below 25 %."""
    hour_angle = ((timestamp.hour + timestamp.minute / 60.0) - 3.0) / 24.0 * 2 * math.pi
    weekday_factor = 0.55 if timestamp.weekday() >= 5 else 1.0
    return max(0.25, (0.62 + 0.38 * math.cos(hour_angle)) * weekday_factor)


def _floor_to_minutes(timestamp: datetime, minutes: int) -> datetime:
    floored_minute = timestamp.minute - timestamp.minute % minutes
    return timestamp.replace(minute=floored_minute, second=0, microsecond=0)


class TelemetrySimulator:
    def __init__(self) -> None:
        self._scenario_windows: list[ScenarioWindow] = []
        self._conditions: list[dict[str, Any]] = []
        self._configuration_loaded_at = 0.0

    # ── Configuration ──────────────────────────────────────────────────────────
    async def refresh_configuration(self, force: bool = False) -> None:
        if not force and time.monotonic() - self._configuration_loaded_at < CONFIGURATION_REFRESH_SECONDS:
            return
        from keigan.config.database_config import open_session
        from keigan.entities.platform_entities import PlatformSetting

        async with open_session() as session:
            simulation_setting = await session.get(PlatformSetting, SIMULATION_SETTING_KEY)
        configuration = (simulation_setting.setting_value_json if simulation_setting else None) or {}
        self._scenario_windows = [ScenarioWindow.from_dictionary(window_entry) for window_entry in configuration.get("scenario_windows", [])]
        self._conditions = list(configuration.get("conditions", []))
        self._configuration_loaded_at = time.monotonic()

    def invalidate(self) -> None:
        self._configuration_loaded_at = 0.0

    def _windows_for_service(self, service_id: str | None, range_start: datetime, range_end: datetime) -> list[tuple[ScenarioWindow, str]]:
        matching_windows: list[tuple[ScenarioWindow, str]] = []
        for scenario_window in self._scenario_windows:
            if not scenario_window.overlaps(range_start, range_end):
                continue
            if service_id in scenario_window.primary_service_ids:
                matching_windows.append((scenario_window, "primary"))
            elif service_id in scenario_window.dependency_service_ids:
                matching_windows.append((scenario_window, "dependency"))
        return matching_windows

    def _condition_value(self, service_id: str | None, condition_kind: str, timestamp: datetime) -> float:
        total_effect = 0.0
        for condition in self._conditions:
            if condition.get("service_id") != service_id or condition.get("condition_kind") != condition_kind:
                continue
            condition_started_at = datetime.fromisoformat(condition["started_at"])
            if timestamp < condition_started_at:
                continue
            elapsed_days = (timestamp - condition_started_at).total_seconds() / 86400
            if condition_kind == "memory_leak":
                total_effect += float(condition.get("percent_per_day", 3.0)) * elapsed_days
            elif condition_kind == "error_budget_burn":
                total_effect += float(condition.get("extra_error_ratio", 0.003))
            elif condition_kind == "latency_creep":
                total_effect += float(condition.get("milliseconds_per_day", 8.0)) * elapsed_days
        return total_effect

    # ── Traffic model ──────────────────────────────────────────────────────────
    def _traffic_for_window(self, telemetry_target: TelemetryTarget, window_start: datetime, interval_minutes: int) -> tuple[int, int, float]:
        """(total requests, failed requests, p95 latency ms) for one service and window."""
        pseudo_random = _stable_random(telemetry_target.service_id, window_start.isoformat(), interval_minutes)
        base_requests = BASE_REQUESTS_PER_FIVE_MINUTES.get(telemetry_target.service_type, 800) * interval_minutes / 5.0
        total_requests = max(0, int(base_requests * _daily_traffic_factor(window_start) * pseudo_random.uniform(0.85, 1.15)))
        error_ratio = BASELINE_ERROR_RATIO * pseudo_random.uniform(0.3, 1.8) + self._condition_value(telemetry_target.service_id, "error_budget_burn", window_start)
        latency_milliseconds = BASELINE_LATENCY_MILLISECONDS * pseudo_random.uniform(0.85, 1.25) + self._condition_value(
            telemetry_target.service_id, "latency_creep", window_start
        )
        for scenario_window, service_role in self._windows_for_service(telemetry_target.service_id, window_start, window_start + timedelta(minutes=interval_minutes)):
            intensity = scenario_window.intensity_at(window_start + timedelta(minutes=interval_minutes / 2))
            role_factor = 1.0 if service_role == "primary" else 0.35
            error_ratio += scenario_window.scenario.error_ratio_during_scenario * intensity * role_factor
            latency_milliseconds *= 1 + (scenario_window.scenario.latency_multiplier - 1) * intensity * role_factor
        failed_requests = min(total_requests, int(round(total_requests * min(error_ratio, 1.0))))
        if telemetry_target.service_type in LOW_VOLUME_SERVICE_TYPES:
            # One check per window (probe, device poll, batch run): healthy kit fails ~1 in 5 000 checks; scenarios raise error_ratio.
            total_requests = max(total_requests, 1)
            baseline_failure_probability = error_ratio - BASELINE_ERROR_RATIO * 1.05 if error_ratio > BASELINE_ERROR_RATIO * 1.8 else LOW_VOLUME_BASELINE_FAILURE_PROBABILITY
            failed_requests = 1 if pseudo_random.random() < min(max(baseline_failure_probability, LOW_VOLUME_BASELINE_FAILURE_PROBABILITY), 1.0) else 0
        return total_requests, failed_requests, latency_milliseconds

    # ── Logs ───────────────────────────────────────────────────────────────────
    async def query_logs(self, telemetry_target: TelemetryTarget, telemetry_query: TelemetryQuery) -> LogQueryResult:
        await self.refresh_configuration()
        signal_kind = telemetry_query.signal_kind
        if signal_kind == "generic":
            signal_kind = self._infer_signal_kind(telemetry_query.query_text)
        row_builders = {
            "error_logs": self._build_error_log_rows,
            "batch_failures": self._build_error_log_rows,
            "exceptions": self._build_exception_rows,
            "failed_requests": self._build_failed_request_rows,
            "slow_requests": self._build_slow_request_rows,
            "failed_dependencies": self._build_failed_dependency_rows,
            "kube_events": self._build_kubernetes_event_rows,
            "pod_restarts": self._build_pod_restart_rows,
            "sli_counts": self._build_sli_count_rows,
            "count": self._build_count_rows,
            "time_series": self._build_time_series_rows,
        }
        rows = row_builders.get(signal_kind, self._build_error_log_rows)(telemetry_target, telemetry_query)
        column_names = sorted({column_name for row in rows for column_name in row}) if rows else []
        return LogQueryResult(
            columns=column_names,
            rows=rows[: telemetry_query.maximum_rows if signal_kind != "sli_counts" else None],
            executed_query_text=telemetry_query.query_text,
            query_language=telemetry_query.query_language,
            is_simulated=True,
            is_truncated=len(rows) > telemetry_query.maximum_rows and signal_kind != "sli_counts",
        )

    @staticmethod
    def _infer_signal_kind(query_text: str) -> str:
        lowercase_query = query_text.lower()
        if "bin(" in lowercase_query or "timechart" in lowercase_query or "date_histogram" in lowercase_query or "make-series" in lowercase_query:
            return "time_series"
        if re.search(r"\bcount\s*\(", lowercase_query) or "| count" in lowercase_query or "stats count" in lowercase_query:
            return "count"
        if "exception" in lowercase_query:
            return "exceptions"
        if "kubeevents" in lowercase_query:
            return "kube_events"
        return "error_logs"

    @staticmethod
    def _query_targets_failures(query_text: str) -> bool:
        lowercase_query = query_text.lower()
        return any(marker in lowercase_query for marker in ("success == false", "success==false", "resultcode >= 500", "fail", "error", "5xx", "exception", "status:error"))

    def _fill_template(self, template_text: str, pseudo_random: random.Random, telemetry_target: TelemetryTarget) -> str:
        replacement_values = {
            "claim_id": f"CLM-{pseudo_random.randint(10_000_000, 99_999_999)}",
            "policy_id": f"POL-{pseudo_random.randint(10_000_000, 99_999_999)}",
            "payment_id": f"PAY-{pseudo_random.randint(1_000_000, 9_999_999)}",
            "customer_email": f"customer{pseudo_random.randint(100, 999)}@example.jp",
            "duration_ms": str(pseudo_random.randint(2_000, 30_500)),
            "attempt": str(pseudo_random.randint(1, 5)),
            "pod_name": f"{telemetry_target.service_name}-{pseudo_random.randint(100000, 999999):x}-{pseudo_random.choice('abcdfghjk')}{pseudo_random.randint(1000, 9999)}",
            "ip_address": f"10.{pseudo_random.randint(1, 250)}.{pseudo_random.randint(1, 250)}.{pseudo_random.randint(1, 250)}",
            "session_count": str(pseudo_random.randint(395, 400)),
            "seconds": str(pseudo_random.randint(5, 60)),
            "subscription_key_hint": f"…{pseudo_random.randint(1000, 9999)}",
            "date": "2026-11-19",
            "probe_host": "benefits.vendor.example",
            "hex_value": f"{pseudo_random.getrandbits(48):x}",
            "operation": "GET /api/status",
        }
        return re.sub(r"\{(\w+)\}", lambda match: replacement_values.get(match.group(1), match.group(0)), template_text)

    def _scenario_minutes(self, telemetry_target: TelemetryTarget, range_start: datetime, range_end: datetime) -> list[tuple[datetime, ScenarioWindow, str]]:
        """Minute-level timestamps where a scenario affects this service (used to place error lines)."""
        affected_minutes: list[tuple[datetime, ScenarioWindow, str]] = []
        for scenario_window, service_role in self._windows_for_service(telemetry_target.service_id, range_start, range_end):
            current_minute = max(range_start, scenario_window.started_at).replace(second=0, microsecond=0)
            last_minute = min(range_end, scenario_window.ended_at or range_end)
            while current_minute < last_minute:
                affected_minutes.append((current_minute, scenario_window, service_role))
                current_minute += timedelta(minutes=1)
        return affected_minutes

    def _build_error_log_rows(self, telemetry_target: TelemetryTarget, telemetry_query: TelemetryQuery) -> list[dict[str, Any]]:
        range_start, range_end = telemetry_query.time_range_start, telemetry_query.time_range_end
        rows: list[dict[str, Any]] = []
        background_templates = BACKGROUND_ERROR_TEMPLATES.get(telemetry_target.service_type, BACKGROUND_ERROR_TEMPLATES["default"])
        range_hours = max(1, int((range_end - range_start).total_seconds() // 3600))
        for hour_index in range(range_hours):
            pseudo_random = _stable_random("background", telemetry_target.service_id, _floor_to_minutes(range_start, 60) + timedelta(hours=hour_index))
            for _ in range(pseudo_random.randint(0, 3)):
                rows.append(
                    {
                        "TimeGenerated": (range_start + timedelta(hours=hour_index, minutes=pseudo_random.randint(0, 59))).isoformat(),
                        "Level": pseudo_random.choice(["warning", "warning", "error"]),
                        "Message": self._fill_template(pseudo_random.choice(background_templates), pseudo_random, telemetry_target),
                        "PodName": f"{telemetry_target.service_name}-7d9f8c-{pseudo_random.randint(1000, 9999)}",
                        "cloud_RoleName": telemetry_target.service_name,
                    }
                )
        for affected_minute, scenario_window, service_role in self._scenario_minutes(telemetry_target, range_start, range_end):
            scenario = scenario_window.scenario
            templates = scenario.primary_error_templates if service_role == "primary" else scenario.dependency_error_templates
            if not templates:
                continue
            pseudo_random = _stable_random(scenario_window.scenario_key, telemetry_target.service_id, affected_minute.isoformat())
            lines_this_minute = int(pseudo_random.randint(3, 9) * scenario_window.intensity_at(affected_minute) * (1 if service_role == "primary" else 0.4))
            for _ in range(lines_this_minute):
                rows.append(
                    {
                        "TimeGenerated": (affected_minute + timedelta(seconds=pseudo_random.randint(0, 59))).isoformat(),
                        "Level": "error",
                        "Message": self._fill_template(pseudo_random.choice(templates), pseudo_random, telemetry_target),
                        "PodName": self._fill_template("{pod_name}", pseudo_random, telemetry_target),
                        "cloud_RoleName": telemetry_target.service_name,
                    }
                )
        return sorted(rows, key=lambda row: row["TimeGenerated"], reverse=True)

    def _aggregate_scenario_counts(self, telemetry_target: TelemetryTarget, telemetry_query: TelemetryQuery) -> tuple[int, int, list[tuple[ScenarioWindow, str]]]:
        total_requests = failed_requests = 0
        current_window_start = _floor_to_minutes(telemetry_query.time_range_start, 5)
        while current_window_start < telemetry_query.time_range_end:
            window_total, window_failed, _ = self._traffic_for_window(telemetry_target, current_window_start, 5)
            total_requests += window_total
            failed_requests += window_failed
            current_window_start += timedelta(minutes=5)
        return total_requests, failed_requests, self._windows_for_service(telemetry_target.service_id, telemetry_query.time_range_start, telemetry_query.time_range_end)

    def _build_exception_rows(self, telemetry_target: TelemetryTarget, telemetry_query: TelemetryQuery) -> list[dict[str, Any]]:
        _, failed_requests, scenario_windows = self._aggregate_scenario_counts(telemetry_target, telemetry_query)
        pseudo_random = _stable_random("exceptions", telemetry_target.service_id, telemetry_query.time_range_start.date())
        rows = [
            {"ExceptionType": "System.TimeoutException", "OuterMessage": "The operation has timed out.", "count_": pseudo_random.randint(1, 4), "cloud_RoleName": telemetry_target.service_name}
        ]
        for scenario_window, service_role in scenario_windows:
            for exception_type in scenario_window.scenario.exception_types:
                rows.append(
                    {
                        "ExceptionType": exception_type,
                        "OuterMessage": self._fill_template((scenario_window.scenario.primary_error_templates or ("",))[0], pseudo_random, telemetry_target),
                        "count_": max(1, int(failed_requests * (0.8 if service_role == "primary" else 0.2) / max(1, len(scenario_window.scenario.exception_types)))),
                        "cloud_RoleName": telemetry_target.service_name,
                        "TimeGenerated": scenario_window.started_at.isoformat(),
                    }
                )
        return rows

    def _build_failed_request_rows(self, telemetry_target: TelemetryTarget, telemetry_query: TelemetryQuery) -> list[dict[str, Any]]:
        total_requests, failed_requests, scenario_windows = self._aggregate_scenario_counts(telemetry_target, telemetry_query)
        rows: list[dict[str, Any]] = []
        scenario_failures = sum(1 for _ in scenario_windows)
        background_failures = failed_requests if not scenario_failures else max(1, int(failed_requests * 0.05))
        rows.append({"OperationName": "GET /health/dependencies", "ResultCode": "503", "count_": background_failures, "TotalRequests": total_requests})
        for scenario_window, service_role in scenario_windows:
            for operation_name in scenario_window.scenario.failing_operations or ("POST /api/requests",):
                rows.append(
                    {
                        "OperationName": operation_name,
                        "ResultCode": "429" if "throttling" in scenario_window.scenario_key else "500",
                        "count_": max(1, int((failed_requests - background_failures) / max(1, len(scenario_window.scenario.failing_operations or ("x",))))),
                        "TotalRequests": total_requests,
                    }
                )
        return rows

    def _build_slow_request_rows(self, telemetry_target: TelemetryTarget, telemetry_query: TelemetryQuery) -> list[dict[str, Any]]:
        _, _, latency_milliseconds = self._traffic_for_window(telemetry_target, _floor_to_minutes(telemetry_query.time_range_end - timedelta(minutes=10), 5), 5)
        scenario_windows = self._windows_for_service(telemetry_target.service_id, telemetry_query.time_range_start, telemetry_query.time_range_end)
        operations = [operation for scenario_window, _ in scenario_windows for operation in scenario_window.scenario.failing_operations] or ["GET /api/status"]
        return [{"OperationName": operation, "P95DurationMs": round(latency_milliseconds * 1.4, 1), "RequestCount": 100 + index * 37} for index, operation in enumerate(operations)]

    def _build_failed_dependency_rows(self, telemetry_target: TelemetryTarget, telemetry_query: TelemetryQuery) -> list[dict[str, Any]]:
        _, failed_requests, scenario_windows = self._aggregate_scenario_counts(telemetry_target, telemetry_query)
        rows: list[dict[str, Any]] = []
        for scenario_window, _ in scenario_windows:
            if scenario_window.scenario.failing_dependency_target:
                rows.append(
                    {
                        "Target": scenario_window.scenario.failing_dependency_target,
                        "DependencyType": "SQL" if "database" in scenario_window.scenario.failing_dependency_target else "HTTP",
                        "ResultCode": "Timeout" if scenario_window.scenario.latency_multiplier > 3 else "500",
                        "count_": max(1, int(failed_requests * 0.9)),
                        "AverageDurationMs": round(BASELINE_LATENCY_MILLISECONDS * scenario_window.scenario.latency_multiplier, 1),
                    }
                )
        if not rows:
            rows.append({"Target": "login.microsoftonline.com", "DependencyType": "HTTP", "ResultCode": "429", "count_": 1, "AverageDurationMs": 240.0})
        return rows

    def _build_kubernetes_event_rows(self, telemetry_target: TelemetryTarget, telemetry_query: TelemetryQuery) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for scenario_window, _ in self._windows_for_service(telemetry_target.service_id, telemetry_query.time_range_start, telemetry_query.time_range_end):
            pseudo_random = _stable_random("kube", scenario_window.scenario_key, telemetry_target.service_id)
            for reason_index, event_reason in enumerate(scenario_window.scenario.kubernetes_event_reasons):
                rows.append(
                    {
                        "TimeGenerated": (scenario_window.started_at + timedelta(minutes=3 + reason_index * 4)).isoformat(),
                        "Reason": event_reason,
                        "Message": self._fill_template(scenario_window.scenario.primary_error_templates[reason_index % len(scenario_window.scenario.primary_error_templates)], pseudo_random, telemetry_target),
                        "Name": self._fill_template("{pod_name}", pseudo_random, telemetry_target),
                        "Namespace": telemetry_target.aks_namespace_filter or "default",
                        "count_": pseudo_random.randint(4, 30),
                    }
                )
        return rows

    def _build_pod_restart_rows(self, telemetry_target: TelemetryTarget, telemetry_query: TelemetryQuery) -> list[dict[str, Any]]:
        scenario_windows = self._windows_for_service(telemetry_target.service_id, telemetry_query.time_range_start, telemetry_query.time_range_end)
        restart_count = sum(12 for scenario_window, _ in scenario_windows if scenario_window.scenario.kubernetes_event_reasons)
        pseudo_random = _stable_random("restarts", telemetry_target.service_id)
        return [{"PodName": self._fill_template("{pod_name}", pseudo_random, telemetry_target), "RestartCount": restart_count, "Namespace": telemetry_target.aks_namespace_filter or "default"}]

    def _build_sli_count_rows(self, telemetry_target: TelemetryTarget, telemetry_query: TelemetryQuery) -> list[dict[str, Any]]:
        interval_minutes = int(telemetry_query.purpose_parameters.get("interval_minutes", 5))
        sli_kind = str(telemetry_query.purpose_parameters.get("sli_kind", "availability"))
        latency_threshold = float(telemetry_query.purpose_parameters.get("latency_threshold_milliseconds") or 500)
        rows: list[dict[str, Any]] = []
        current_window_start = _floor_to_minutes(telemetry_query.time_range_start, interval_minutes)
        while current_window_start < telemetry_query.time_range_end:
            total_requests, failed_requests, latency_milliseconds = self._traffic_for_window(telemetry_target, current_window_start, interval_minutes)
            if sli_kind == "supporting_signal":
                rows.append({"window_start": current_window_start.isoformat(), "value": round(latency_milliseconds, 2)})
            elif sli_kind == "latency":
                slow_ratio = min(1.0, max(0.0, (latency_milliseconds - latency_threshold * 0.6) / (latency_threshold * 2)))
                if total_requests <= 5:  # single probes or device polls: slow or not, drawn from the slow ratio
                    slow_requests = int(_stable_random("latency", telemetry_target.service_id, current_window_start.isoformat()).random() < slow_ratio * 0.5) * total_requests
                else:
                    slow_requests = round(total_requests * slow_ratio * 0.5)
                rows.append({"window_start": current_window_start.isoformat(), "good": total_requests - slow_requests, "total": total_requests})
            else:
                rows.append({"window_start": current_window_start.isoformat(), "good": total_requests - failed_requests, "total": total_requests})
            current_window_start += timedelta(minutes=interval_minutes)
        return rows

    def _build_count_rows(self, telemetry_target: TelemetryTarget, telemetry_query: TelemetryQuery) -> list[dict[str, Any]]:
        total_requests, failed_requests, _ = self._aggregate_scenario_counts(telemetry_target, telemetry_query)
        return [{"count_": failed_requests if self._query_targets_failures(telemetry_query.query_text) else total_requests}]

    def _build_time_series_rows(self, telemetry_target: TelemetryTarget, telemetry_query: TelemetryQuery) -> list[dict[str, Any]]:
        bin_match = re.search(r"bin\(\s*\w+\s*,\s*(\d+)\s*([mhd])\s*\)", telemetry_query.query_text, re.IGNORECASE)
        range_minutes = (telemetry_query.time_range_end - telemetry_query.time_range_start).total_seconds() / 60
        bucket_minutes = (
            int(bin_match.group(1)) * {"m": 1, "h": 60, "d": 1440}[bin_match.group(2).lower()]
            if bin_match else (60 if range_minutes > 360 else 15 if range_minutes > 60 else 5)
        )
        bucket_minutes = max(5, bucket_minutes)
        counts_failures = self._query_targets_failures(telemetry_query.query_text)
        rows: list[dict[str, Any]] = []
        bucket_start = _floor_to_minutes(telemetry_query.time_range_start, 5)
        while bucket_start < telemetry_query.time_range_end:
            bucket_total = bucket_failed = 0
            window_start = bucket_start
            while window_start < bucket_start + timedelta(minutes=bucket_minutes):
                window_total, window_failed, _ = self._traffic_for_window(telemetry_target, window_start, 5)
                bucket_total += window_total
                bucket_failed += window_failed
                window_start += timedelta(minutes=5)
            rows.append({"TimeGenerated": bucket_start.isoformat(), "count_": bucket_failed if counts_failures else bucket_total})
            bucket_start += timedelta(minutes=bucket_minutes)
        return rows

    # ── Metrics ────────────────────────────────────────────────────────────────
    async def query_metrics(
        self,
        telemetry_target: TelemetryTarget,
        metric_names: list[str],
        time_range_start: datetime,
        time_range_end: datetime,
        interval_minutes: int = 5,
        aggregation: str = "Average",
    ) -> MetricQueryResult:
        await self.refresh_configuration()
        metric_series_list: list[MetricSeries] = []
        for metric_name in metric_names:
            lowercase_metric_name = metric_name.lower().replace("_", "")
            data_points: list[tuple[datetime, float | None]] = []
            unit = "Percent" if any(marker in lowercase_metric_name for marker in ("cpu", "memory", "percent", "dtu", "sessions", "capacity")) else "Count"
            window_start = _floor_to_minutes(time_range_start, interval_minutes)
            while window_start < time_range_end:
                pseudo_random = _stable_random("metric", telemetry_target.service_id, metric_name, window_start.isoformat())
                total_requests, failed_requests, latency_milliseconds = self._traffic_for_window(telemetry_target, window_start, interval_minutes)
                traffic_factor = _daily_traffic_factor(window_start)
                if "cpu" in lowercase_metric_name:
                    metric_value = 18 + 30 * traffic_factor + pseudo_random.uniform(-4, 4)
                elif "memory" in lowercase_metric_name:
                    metric_value = 52 + 6 * traffic_factor + pseudo_random.uniform(-2, 2) + self._condition_value(telemetry_target.service_id, "memory_leak", window_start)
                elif any(marker in lowercase_metric_name for marker in ("5xx", "failed", "error", "abend")):
                    metric_value = float(failed_requests)
                elif any(marker in lowercase_metric_name for marker in ("responsetime", "duration", "latency")):
                    metric_value = latency_milliseconds
                    unit = "Milliseconds"
                elif any(marker in lowercase_metric_name for marker in ("dtu", "sessions", "connection", "capacity")):
                    metric_value = 25 + 25 * traffic_factor + pseudo_random.uniform(-3, 3)
                elif "restart" in lowercase_metric_name:
                    metric_value = 0.0
                else:
                    metric_value = float(total_requests)
                for scenario_window, service_role in self._windows_for_service(telemetry_target.service_id, window_start, window_start + timedelta(minutes=interval_minutes)):
                    intensity = scenario_window.intensity_at(window_start) * (1.0 if service_role == "primary" else 0.5)
                    for multiplier_key, multiplier_value in scenario_window.scenario.metric_multipliers.items():
                        if multiplier_key in lowercase_metric_name:
                            metric_value = metric_value * (1 + (multiplier_value - 1) * intensity) if multiplier_value >= 1 else metric_value
                            if multiplier_key == "restart":
                                metric_value = multiplier_value * intensity
                if unit == "Percent":
                    metric_value = max(0.0, min(100.0, metric_value))
                data_points.append((window_start, round(metric_value, 3)))
                window_start += timedelta(minutes=interval_minutes)
            metric_series_list.append(MetricSeries(metric_name, unit, aggregation, data_points))
        return MetricQueryResult(series=metric_series_list, is_simulated=True)

    # ── Changes and probes ─────────────────────────────────────────────────────
    async def query_activity_changes(self, application_id: str, time_range_start: datetime, time_range_end: datetime) -> list[ChangeEvent]:
        await self.refresh_configuration()
        change_events: list[ChangeEvent] = []
        for scenario_window in self._scenario_windows:
            scenario = scenario_window.scenario
            change_time = scenario_window.started_at - timedelta(minutes=7)
            if scenario_window.application_id == application_id and scenario.change_event_kind and time_range_start <= change_time <= time_range_end:
                change_events.append(
                    ChangeEvent(
                        occurred_at=change_time,
                        change_kind=scenario.change_event_kind,
                        operation_name="Microsoft.Web/sites/config/write" if scenario.change_event_kind == "configuration_change" else "Microsoft.Web/sites/deployments/write",
                        resource_identifier=",".join(scenario_window.primary_service_ids[:1]),
                        description=scenario.change_event_description or scenario.title,
                        caller="azure-pipelines-release@metlife.example",
                    )
                )
        routine_day = time_range_start.replace(hour=1, minute=10, second=0, microsecond=0)
        while routine_day <= time_range_end:
            if _stable_random("routine-release", application_id, routine_day.date()).random() < 0.35 and routine_day >= time_range_start:
                change_events.append(
                    ChangeEvent(
                        occurred_at=routine_day,
                        change_kind="deployment",
                        operation_name="Microsoft.Resources/deployments/write",
                        resource_identifier=application_id,
                        description=f"Routine release {routine_day.strftime('%Y.%m.%d')}.1 deployed",
                        caller="azure-pipelines-release@metlife.example",
                    )
                )
            routine_day += timedelta(days=1)
        return sorted(change_events, key=lambda change_event: change_event.occurred_at)

    async def probe_endpoint(self, probe_url: str, application_id: str | None = None) -> ProbeResult:
        await self.refresh_configuration()
        now = datetime.now(UTC)
        pseudo_random = _stable_random("probe", probe_url, _floor_to_minutes(now, 5).isoformat())
        for scenario_window in self._scenario_windows:
            if scenario_window.scenario_key == "saas_vendor_outage" and scenario_window.application_id == application_id and scenario_window.intensity_at(now) > 0:
                if pseudo_random.random() < scenario_window.scenario.error_ratio_during_scenario:
                    return ProbeResult(False, 503, pseudo_random.randint(2_000, 9_000), "HTTP 503 Service Unavailable")
        return ProbeResult(True, 200, pseudo_random.randint(180, 420), "HTTP 200")

    # ── Helpers for seeding and the scenario trigger ───────────────────────────
    def active_scenario_windows(self) -> list[ScenarioWindow]:
        return list(self._scenario_windows)
