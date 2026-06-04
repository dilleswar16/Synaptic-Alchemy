"""Predictive detection heuristics for V3.7."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from corvin.core.contracts import InvestigationResult
from corvin.core.config_loader import get_env, load_config
from corvin.evidence.container_logs_adapter import ContainerLogsAdapter
from corvin.storage.repository import InvestigationRepository

_log = logging.getLogger(__name__)


class PredictiveAlert(BaseModel):
    id: str
    service_name: str
    environment: str
    alert_type: str
    title: str
    summary: str
    severity: str
    confidence: str
    confidence_pct: float = 0.0
    signal_value: float
    threshold_value: float
    estimated_breach_at: datetime | None = None
    rationale: str
    source_request_id: str | None = None
    status: str = "open"
    investigation_request_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # --- New fields ---
    change_correlation: str | None = None  # e.g. "Alert triggered 7 min after deployment payments-api-deploy-v42"
    related_count: int = 1  # Number of deduplicated signals grouped into this alert
    blast_radius_users: int = 0  # Actual APIM request count (user-facing impact)
    blast_radius_requests: int = 0  # Total APIM requests in window


_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _coerce_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


class PredictiveMonitor:
    def __init__(
        self,
        repo: InvestigationRepository | None = None,
        policy: dict | None = None,
        container_logs: ContainerLogsAdapter | None = None,
    ) -> None:
        self._repo = repo or InvestigationRepository()
        if policy is not None:
            self._policy = dict(policy)
        else:
            try:
                self._policy = load_config("policies/investigation", get_env())
            except Exception:
                self._policy = {}
        self._container_logs = container_logs
        try:
            if self._container_logs is None:
                self._container_logs = ContainerLogsAdapter()
        except Exception as exc:
            _log.warning("ContainerLogsAdapter init failed (alerts will use partial data): %s", exc)
            self._container_logs = None

    def refresh_alerts(self, limit: int = 20) -> list[PredictiveAlert]:
        results = self._repo.list_recent_results(limit=limit)
        alerts: dict[str, PredictiveAlert] = {}
        for result in results:
            # Fetch live metrics for this service to ensure real current data
            live_metrics: list[dict] = []
            if self._container_logs is not None:
                try:
                    live_metrics = self._container_logs.get_resource_metrics(
                        service_name=result.request.service_name,
                        time_range_minutes=result.request.lookback_minutes or 60,
                    )
                except Exception as exc:
                    _log.warning(
                        "Failed to fetch live metrics for %s: %s",
                        result.request.service_name,
                        exc,
                    )
            for alert in _alerts_for_result(
                result,
                policy=self._policy,
                live_metrics=live_metrics,
            ):
                # --- Alert deduplication ---
                # Group by service_name + alert_type. Keep the highest-severity
                # instance and increment related_count.
                dedup_key = f"{alert.service_name}:{alert.alert_type}"
                existing = alerts.get(dedup_key)
                if existing is not None:
                    existing_rank = _SEVERITY_RANK.get(existing.severity.lower(), 0)
                    new_rank = _SEVERITY_RANK.get(alert.severity.lower(), 0)
                    if new_rank > existing_rank:
                        # Promote: keep the new alert but carry forward the count
                        alert.related_count = existing.related_count + 1
                        alerts[dedup_key] = alert
                    else:
                        existing.related_count += 1
                else:
                    alerts[dedup_key] = alert

        ordered = sorted(
            alerts.values(),
            key=lambda a: (_SEVERITY_RANK.get(a.severity.lower(), 0), a.created_at),
            reverse=True,
        )
        self._repo.replace_predictive_alerts([alert.model_dump(mode="json") for alert in ordered])

        # ── Notify application contacts via email ──
        if ordered:
            try:
                from corvin.delivery.prediction_notification import send_prediction_emails
                send_prediction_emails([a.model_dump(mode="json") for a in ordered])
            except Exception as exc:
                _log.warning("Prediction email notification failed (non-fatal): %s", exc)

        return ordered

    async def run_forever(self, interval_seconds: int = 300) -> None:
        while True:
            try:
                alerts = self.refresh_alerts()
                # ── Validation automation: trigger user journeys for matching policies ──
                if alerts:
                    try:
                        from corvin.triggers.validation_automation import evaluate_policies
                        await evaluate_policies(alerts)
                    except Exception as exc:
                        _log.warning("Validation automation evaluation failed: %s", exc)
            except Exception:
                pass
            await asyncio.sleep(interval_seconds)


def _calculate_confidence_pct(
    result: InvestigationResult,
    live_metrics: list[dict] | None = None,
    signal_value: float = 0.0,
    threshold_value: float = 100.0,
    slope_direction: float = 0.0,
) -> float:
    """Calculate numeric confidence 0-100% based on evidence quality AND signal context.

    The score is shaped by both evidence richness and how close the signal
    actually is to the threshold. A 24% signal vs an 85% threshold should
    NOT produce 100% confidence.
    """
    # ── Load scoring weights: DB-first, YAML fallback ────────────────────────
    _w: dict = {}
    try:
        service_name = result.request.service_name
        from sqlalchemy import or_
        from corvin.storage.db import get_session
        from corvin.storage.models import ApplicationServiceRow, ApplicationRow
        with get_session() as _sess:
            _svc = _sess.query(ApplicationServiceRow).filter(
                or_(ApplicationServiceRow.service_name == service_name,
                    ApplicationServiceRow.k8s_app_label == service_name)
            ).first()
            if _svc:
                _app: ApplicationRow | None = _sess.get(ApplicationRow, _svc.application_id)
                if _app and _app.scoring_config_json:
                    _w = (_app.scoring_config_json.get("predictive_confidence") or {})
    except Exception:
        pass
    if not _w:
        try:
            from corvin.core.config_loader import load_config, get_env
            _w = load_config("policies/scoring", get_env()).get("predictive_confidence", {})
        except Exception:
            _w = {}

    base_score = float(_w.get("base_score", 25.0))
    prox = _w.get("proximity", {})
    trend = _w.get("trend", {})
    evidence_diversity_max = float(_w.get("evidence_diversity_max", 12.0))
    evidence_diversity_types = int(_w.get("evidence_diversity_types", 5))
    live_metrics_bonus = float(_w.get("live_metrics_bonus", 8.0))
    reasoning_quality = _w.get("reasoning_quality", {})
    evidence_refs_max = float(_w.get("evidence_refs_max", 5.0))

    score = base_score

    # ── Signal proximity to threshold ──────────────────────────────────────────
    if threshold_value > 0:
        proximity = signal_value / threshold_value
        if proximity >= 1.0:
            score += float(prox.get("breached", 30.0))
        elif proximity >= 0.8:
            score += float(prox.get("imminent", 25.0))
        elif proximity >= 0.6:
            score += float(prox.get("approaching", 18.0))
        elif proximity >= 0.4:
            score += float(prox.get("moderate", 10.0))
        else:
            score += float(prox.get("distant", 3.0))

    # ── Trend direction ────────────────────────────────────────────────────────
    if slope_direction > 0:
        score += float(trend.get("rising", 15.0))
    elif slope_direction == 0:
        score += float(trend.get("flat", 5.0))
    # Negative slope: no bonus (declining is good)

    # ── Evidence diversity ─────────────────────────────────────────────────────
    evidence_types = 0
    if result.evidence.log_analytics_apim:
        evidence_types += 1
    if result.evidence.aks_context:
        evidence_types += 1
    if result.evidence.container_resource_metrics or result.evidence.container_inventory:
        evidence_types += 1
    if result.evidence.elastic_logs or result.evidence.elastic_metrics:
        evidence_types += 1
    if result.evidence.pod_restarts or result.evidence.oom_kill_events:
        evidence_types += 1
    score += (evidence_types / evidence_diversity_types) * evidence_diversity_max

    # ── Live metrics bonus ────────────────────────────────────────────────────
    if live_metrics:
        score += live_metrics_bonus

    # ── RCA reasoning quality ─────────────────────────────────────────────────
    reasoning_length = len(result.rca.confidence_reasoning or "")
    if reasoning_length > 100:
        score += float(reasoning_quality.get("rich", 5.0))
    elif reasoning_length > 50:
        score += float(reasoning_quality.get("brief", 3.0))

    # ── Evidence references ───────────────────────────────────────────────────
    refs = len(result.rca.evidence_references or [])
    score += min(evidence_refs_max, float(refs))

    return min(100.0, round(score, 1))


def _alerts_for_result(
    result: InvestigationResult,
    policy: dict,
    live_metrics: list[dict] | None = None,
) -> list[PredictiveAlert]:
    alerts: list[PredictiveAlert] = []
    haystack = " ".join(
        [
            result.request.description,
            result.rca.summary,
            result.rca.root_cause,
            " ".join(result.rca.contributing_factors),
        ]
    ).lower()

    apim_errors = _apim_error_count(result)
    apim_total = len(result.evidence.log_analytics_apim)
    error_ratio = apim_errors / max(apim_total, 1) if apim_total else 0.0
    error_ratio_pct = round(error_ratio * 100.0, 1)
    restart_count = _restart_count(result)

    # --- Change correlation ---
    change_correlation = _detect_change_correlation(result)

    # --- Dynamic blast radius from APIM ---
    blast_requests, blast_users = _apim_blast_radius(result)

    memory_threshold_pct = _coerce_float(policy.get("predictive_memory_threshold_pct")) or 85.0
    memory_soft_limit_mib = _coerce_float(policy.get("predictive_memory_soft_limit_mib")) or 320.0
    error_rate_threshold_pct = _coerce_float(policy.get("predictive_error_rate_threshold_pct")) or 15.0
    error_rate_critical_pct = _coerce_float(policy.get("predictive_error_rate_critical_pct")) or 30.0
    error_count_threshold = int(policy.get("predictive_error_count_threshold", 5) or 5)
    restart_threshold = int(policy.get("predictive_restart_threshold", 3) or 3)

    # Try live metrics first, then stored evidence, then fallback only if both missing
    memory_signal_pct, memory_rationale = _memory_pressure_signal_from_live_or_stored(
        live_metrics=live_metrics or [],
        result=result,
        soft_limit_mib=memory_soft_limit_mib,
    )

    memory_keywords = any(word in haystack for word in ["memory", "heap", "oom"])
    # Only use synthetic fallback if we have no live metrics and no stored metrics
    fallback_pressure = None
    if memory_signal_pct is None and not (live_metrics or []):
        fallback_pressure = min(100.0, (apim_errors * 8.0) + (restart_count * 7.0) + (20.0 if memory_keywords else 0.0))
    memory_signal = round(memory_signal_pct if memory_signal_pct is not None else fallback_pressure or 0.0, 1)
    memory_is_breaching = memory_signal >= memory_threshold_pct

    if memory_keywords or memory_is_breaching:
        # Use linear regression for ETA if we have time-series data
        breach_hours, slope_dir = _estimate_breach_from_trend(
            metric_rows=live_metrics or result.evidence.container_resource_metrics or [],
            counter_name_match="memoryWorkingSetBytes",
            current_signal=memory_signal,
            threshold=memory_threshold_pct,
            base_hours=8,
            is_percentage=True,
        )

        # Calculate confidence WITH signal context
        confidence_pct = _calculate_confidence_pct(
            result, live_metrics,
            signal_value=memory_signal,
            threshold_value=memory_threshold_pct,
            slope_direction=slope_dir,
        )

        # Severity: keyword-only alerts far below threshold get downgraded
        if memory_signal >= memory_threshold_pct + 10:
            sev = "critical"
        elif memory_is_breaching:
            sev = "high"
        elif memory_signal >= memory_threshold_pct * 0.6:
            sev = "high"
        elif memory_signal >= memory_threshold_pct * 0.35:
            sev = "medium"
        else:
            sev = "low"  # keyword-only, signal far from threshold (e.g. 24% vs 85%)

        # Honest ETA summary
        if breach_hours is None:
            eta_note = "No breach projected — trend is flat or declining."
        else:
            eta_note = f"Investigate before the next restart wave."

        alerts.append(
            _make_alert(
                result,
                alert_type="memory_pressure",
                title="Memory trend indicates likely OOM" if memory_is_breaching else "Memory keywords detected in RCA",
                summary=(
                    f"Memory pressure signal is {memory_signal:.1f}% against a {memory_threshold_pct:.1f}% threshold. "
                    f"{eta_note}"
                ),
                severity=sev,
                confidence=result.rca.confidence.value,
                confidence_pct=confidence_pct,
                signal_value=memory_signal,
                threshold_value=round(memory_threshold_pct, 1),
                breach_in_hours=breach_hours,
                rationale=(
                    f"{memory_rationale} "
                    f"Keyword/context match: {'yes' if memory_keywords else 'no'}. "
                    f"Trend: {'rising' if slope_dir > 0 else 'declining' if slope_dir < 0 else 'flat/unknown'}."
                ),
                change_correlation=change_correlation,
                blast_radius_requests=blast_requests,
                blast_radius_users=blast_users,
            )
        )

    if error_ratio_pct >= error_rate_threshold_pct or apim_errors >= error_count_threshold:
        breach_hours, slope_dir = _estimate_breach_from_trend(
            metric_rows=result.evidence.log_analytics_apim,
            counter_name_match=None,
            current_signal=error_ratio_pct,
            threshold=error_rate_threshold_pct,
            base_hours=6,
            is_percentage=True,
        )
        err_confidence = _calculate_confidence_pct(
            result, live_metrics,
            signal_value=error_ratio_pct,
            threshold_value=error_rate_threshold_pct,
            slope_direction=slope_dir,
        )
        alerts.append(
            _make_alert(
                result,
                alert_type="error_rate",
                title="Error rate trend is climbing toward customer-visible impact",
                summary="5xx volume is high enough to justify an investigation before the service crosses the next reliability threshold.",
                severity="critical" if error_ratio_pct >= error_rate_critical_pct else "high",
                confidence=result.rca.confidence.value,
                confidence_pct=err_confidence,
                signal_value=error_ratio_pct,
                threshold_value=round(error_rate_threshold_pct, 1),
                breach_in_hours=breach_hours,
                rationale=(
                    f"Observed {apim_errors} 5xx-like APIM events across {apim_total} requests "
                    f"({error_ratio_pct:.1f}% error ratio)."
                ),
                change_correlation=change_correlation,
                blast_radius_requests=blast_requests,
                blast_radius_users=blast_users,
            )
        )

    if restart_count >= restart_threshold:
        restart_hours, restart_slope = _estimate_breach_from_trend(
            metric_rows=[],
            counter_name_match=None,
            current_signal=float(restart_count),
            threshold=float(restart_threshold),
            base_hours=10,
            is_percentage=False,
        )
        restart_confidence = _calculate_confidence_pct(
            result, live_metrics,
            signal_value=float(restart_count),
            threshold_value=float(restart_threshold),
            slope_direction=restart_slope,
        )
        alerts.append(
            _make_alert(
                result,
                alert_type="restart_acceleration",
                title="Pod restart acceleration suggests unstable deployment",
                summary="The restart cadence indicates the service may enter a noisier failure cycle without intervention.",
                severity="medium",
                confidence=result.rca.confidence.value,
                confidence_pct=restart_confidence,
                signal_value=float(restart_count),
                threshold_value=float(restart_threshold),
                breach_in_hours=restart_hours,
                rationale=f"AKS context shows {restart_count} recent pod restarts (threshold={restart_threshold}).",
                change_correlation=change_correlation,
                blast_radius_requests=blast_requests,
                blast_radius_users=blast_users,
            )
        )

    return alerts


def _estimate_breach_from_trend(
    metric_rows: list[dict],
    counter_name_match: str | None,
    current_signal: float,
    threshold: float,
    base_hours: int,
    *,
    is_percentage: bool = True,
) -> tuple[int | None, float]:
    """Estimate hours to breach using linear regression on time-series data.

    Returns (hours_to_breach | None, slope_direction):
      - hours_to_breach: integer hours until threshold crossed, or None if
        no breach is projected (flat/declining trend below threshold)
      - slope_direction: positive, negative, or 0.0 for unknown
    """
    # Try to extract timestamped values for regression
    points: list[tuple[float, float]] = []  # (epoch_seconds, value)
    for row in metric_rows:
        if not isinstance(row, dict):
            continue

        # Match counter name if specified (container metrics)
        if counter_name_match is not None:
            counter = str(
                row.get("CounterName")
                or row.get("counter_name")
                or row.get("countername")
                or ""
            )
            if counter_name_match not in counter:
                continue

        # Extract timestamp
        ts = _parse_timestamp(row)
        if ts is None:
            continue

        # Extract numeric value
        value = (
            _coerce_float(row.get("AvgValue"))
            or _coerce_float(row.get("avg_value"))
            or _coerce_float(row.get("CounterValue"))
            or _coerce_float(row.get("counter_value"))
            or _coerce_float(row.get("MaxValue"))
            or _coerce_float(row.get("max_value"))
        )
        if value is None:
            continue

        points.append((ts, value))

    # Need at least 3 points for a meaningful regression
    if len(points) >= 3:
        points.sort(key=lambda p: p[0])

        # Simple least-squares linear regression (no numpy dependency)
        n = len(points)
        sum_x = sum(p[0] for p in points)
        sum_y = sum(p[1] for p in points)
        sum_xy = sum(p[0] * p[1] for p in points)
        sum_xx = sum(p[0] * p[0] for p in points)

        denom = n * sum_xx - sum_x * sum_x
        if abs(denom) > 1e-12:
            slope_per_sec = (n * sum_xy - sum_x * sum_y) / denom  # units/sec

            if slope_per_sec > 0:
                # Project when threshold is breached from current signal
                remaining = threshold - current_signal
                if remaining <= 0:
                    return 1, slope_per_sec  # Already breached — imminent
                seconds_to_breach = remaining / slope_per_sec
                hours = max(1, int(math.ceil(seconds_to_breach / 3600.0)))
                return min(hours, base_hours * 2), slope_per_sec
            else:
                # Slope is flat or declining — no breach projected
                if current_signal >= threshold:
                    # Already above threshold but declining
                    return _estimate_breach_hours_heuristic(current_signal, threshold, base_hours), slope_per_sec
                return None, slope_per_sec  # Honestly: no breach coming

    # Fallback: no time-series data at all
    if current_signal >= threshold:
        return _estimate_breach_hours_heuristic(current_signal, threshold, base_hours), 0.0
    return None, 0.0  # No data + below threshold = no breach projected


def _estimate_breach_hours_heuristic(signal_value: float, threshold_value: float, base_hours: int) -> int:
    """Heuristic fallback when insufficient time-series data for regression."""
    if signal_value >= threshold_value + 15:
        return max(1, base_hours // 4)
    if signal_value >= threshold_value + 5:
        return max(2, base_hours // 3)
    if signal_value >= threshold_value:
        return max(3, base_hours // 2)
    return base_hours


def _parse_timestamp(row: dict) -> float | None:
    """Extract epoch seconds from a metric row's timestamp field."""
    for key in ("TimeGenerated", "time_generated", "timestamp", "Timestamp", "time", "created_at"):
        raw = row.get(key)
        if raw is None:
            continue
        if isinstance(raw, (int, float)):
            return float(raw)
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            return dt.timestamp()
        except (ValueError, TypeError):
            continue
    return None


def _detect_change_correlation(result: InvestigationResult) -> str | None:
    """Cross-reference azure_activity_changes with alert timing.

    Returns a human-readable correlation string if a change was detected
    within a relevant window, else None.
    """
    changes = result.evidence.azure_activity_changes
    if not changes:
        return None

    alert_time = result.completed_at or datetime.now(timezone.utc)
    best_change: dict | None = None
    best_delta_minutes: float = float("inf")

    for change in changes:
        if not isinstance(change, dict):
            continue
        # Try to parse the change timestamp
        ts_raw = (
            change.get("eventTimestamp")
            or change.get("timestamp")
            or change.get("TimeGenerated")
            or change.get("time")
        )
        if ts_raw is None:
            continue
        try:
            if isinstance(ts_raw, (int, float)):
                change_dt = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
            else:
                change_dt = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue

        delta = abs((alert_time - change_dt).total_seconds()) / 60.0
        if delta < best_delta_minutes:
            best_delta_minutes = delta
            best_change = change

    if best_change is None or best_delta_minutes > 120:
        return None

    # Build human-readable label
    operation = (
        best_change.get("operationName")
        or best_change.get("operation")
        or best_change.get("action")
        or "change"
    )
    caller = best_change.get("caller") or best_change.get("initiatedBy") or ""
    delta_label = (
        f"{int(best_delta_minutes)} min" if best_delta_minutes >= 1
        else f"{int(best_delta_minutes * 60)} sec"
    )

    parts = [f"Alert triggered {delta_label} after {operation}"]
    if caller:
        parts.append(f"by {caller}")
    return " ".join(parts)


def _apim_blast_radius(result: InvestigationResult) -> tuple[int, int]:
    """Compute dynamic blast radius from APIM evidence.

    Returns (total_requests, user_facing_errors):
      - total_requests: all APIM requests in the evidence window
      - user_facing_errors: only 5xx responses on external-facing API calls
        (excludes internal health probes, elastic queries, trace endpoints)

    This replaces the hardcoded "N users per replica" with real traffic data.
    """
    apim_rows = result.evidence.log_analytics_apim
    if not apim_rows:
        return 0, 0

    # Patterns that indicate internal/non-user-facing traffic
    _INTERNAL_PATTERNS = {
        "health", "healthz", "readyz", "livez", "ready", "alive",
        "elastic", "kibana", "trace", "metrics", "prometheus",
        "actuator", "internal", "diag", "ping", "warmup",
    }

    total_requests = len(apim_rows)
    user_facing_errors = 0

    for row in apim_rows:
        if not isinstance(row, dict):
            continue

        # Check if this is a user-affecting 5xx error
        status = row.get("StatusCode", row.get("status_code", row.get("status")))
        try:
            status_int = int(status)
        except (TypeError, ValueError):
            continue

        if status_int < 500:
            continue

        # Filter out internal/non-user-facing endpoints
        url = str(
            row.get("Url", row.get("url", row.get("RequestUrl", row.get("request_url", ""))))
        ).lower()
        api_id = str(row.get("ApiId", row.get("api_id", ""))).lower()
        operation = str(
            row.get("OperationId", row.get("operation_id", row.get("OperationName", "")))
        ).lower()

        combined = f"{url} {api_id} {operation}"
        is_internal = any(pattern in combined for pattern in _INTERNAL_PATTERNS)

        if not is_internal:
            user_facing_errors += 1

    return total_requests, user_facing_errors


def _memory_pressure_signal_from_live_or_stored(
    live_metrics: list[dict],
    result: InvestigationResult,
    soft_limit_mib: float,
) -> tuple[float | None, str]:
    """Return memory pressure signal from live metrics first, then stored evidence, then None.

    Preference order:
      1) Live metrics from container_logs adapter (current real data)
      2) Stored evidence in investigation result
      3) None (fallback will be synthetic if needed)
    """
    # Try live metrics first (current real data)
    if live_metrics:
        signal, rationale = _extract_memory_signal_from_rows(
            live_metrics,
            soft_limit_mib=soft_limit_mib,
            source="live",
        )
        if signal is not None:
            return signal, rationale

    # Fall back to stored evidence
    signal, rationale = _memory_pressure_signal_from_stored(
        result,
        soft_limit_mib=soft_limit_mib,
    )
    return signal, rationale


def _extract_memory_signal_from_rows(
    rows: list[dict],
    soft_limit_mib: float,
    source: str = "stored",
) -> tuple[float | None, str]:
    """Extract memory signal from a list of metric rows (live or stored)."""
    usage_mib_values: list[float] = []
    limit_mib_values: list[float] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        counter = str(
            row.get("CounterName")
            or row.get("counter_name")
            or row.get("countername")
            or ""
        )
        value = (
            _coerce_float(row.get("AvgValue"))
            or _coerce_float(row.get("avg_value"))
            or _coerce_float(row.get("CounterValue"))
            or _coerce_float(row.get("counter_value"))
            or _coerce_float(row.get("MaxValue"))
            or _coerce_float(row.get("max_value"))
        )
        if value is None:
            continue

        if "memoryWorkingSetBytes" in counter or "memoryRssBytes" in counter:
            usage_mib_values.append(value / (1024.0 * 1024.0))
        elif "memoryLimitBytes" in counter:
            limit_mib_values.append(value / (1024.0 * 1024.0))

    if not usage_mib_values:
        source_label = "live container metrics" if source == "live" else "stored evidence"
        return None, f"No memory usage metrics available in {source_label}."

    avg_usage = sum(usage_mib_values) / len(usage_mib_values)
    if limit_mib_values:
        avg_limit = max(sum(limit_mib_values) / len(limit_mib_values), 1.0)
        signal = round(min((avg_usage / avg_limit) * 100.0, 100.0), 1)
        source_label = "live" if source == "live" else "investigation evidence"
        return signal, (
            f"({source_label}) Avg memory working set is {avg_usage:.1f} MiB across pods "
            f"vs memory limit {avg_limit:.1f} MiB."
        )

    baseline = max(soft_limit_mib, 1.0)
    signal = round(min((avg_usage / baseline) * 100.0, 100.0), 1)
    source_label = "live" if source == "live" else "investigation evidence"
    return signal, (
        f"({source_label}) Avg memory working set is {avg_usage:.1f} MiB across pods. "
        f"No memory limit found, using soft baseline {baseline:.1f} MiB."
    )


def _memory_pressure_signal_from_stored(
    result: InvestigationResult,
    soft_limit_mib: float,
) -> tuple[float | None, str]:
    """Extract memory signal from stored investigation evidence."""
    rows = result.evidence.container_resource_metrics or []
    return _extract_memory_signal_from_rows(rows, soft_limit_mib=soft_limit_mib, source="stored")


def _make_alert(
    result: InvestigationResult,
    *,
    alert_type: str,
    title: str,
    summary: str,
    severity: str,
    confidence: str,
    confidence_pct: float = 0.0,
    signal_value: float,
    threshold_value: float,
    breach_in_hours: int | None,
    rationale: str,
    change_correlation: str | None = None,
    blast_radius_requests: int = 0,
    blast_radius_users: int = 0,
) -> PredictiveAlert:
    key = f"{result.request.service_name}:{result.request.environment}:{alert_type}"
    alert_id = hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]

    # Set categorical confidence based on numeric confidence_pct
    if confidence_pct > 70:
        final_confidence = "high"
    elif confidence_pct > 40:
        final_confidence = "medium"
    else:
        final_confidence = "low"

    # ETA: None means no breach projected
    breach_at = (
        datetime.now(timezone.utc) + timedelta(hours=breach_in_hours)
        if breach_in_hours is not None
        else None
    )

    return PredictiveAlert(
        id=alert_id,
        service_name=result.request.service_name,
        environment=result.request.environment,
        alert_type=alert_type,
        title=title,
        summary=summary,
        severity=severity,
        confidence=final_confidence,
        confidence_pct=round(confidence_pct, 1),
        signal_value=signal_value,
        threshold_value=threshold_value,
        estimated_breach_at=breach_at,
        rationale=rationale,
        source_request_id=result.request_id,
        created_at=result.completed_at,
        change_correlation=change_correlation,
        blast_radius_requests=blast_radius_requests,
        blast_radius_users=blast_radius_users,
    )


def _apim_error_count(result: InvestigationResult) -> int:
    total = 0
    for row in result.evidence.log_analytics_apim:
        status = row.get("StatusCode", row.get("status_code", row.get("status")))
        try:
            if int(status) >= 500:
                total += 1
        except (TypeError, ValueError):
            if str(status).startswith("5"):
                total += 1
    return total


def _restart_count(result: InvestigationResult) -> int:
    total = 0
    for pod in result.evidence.aks_context.get("pods", []):
        if not isinstance(pod, dict):
            continue
        try:
            total += int(pod.get("restart_count", pod.get("restarts", 0)))
        except (TypeError, ValueError):
            continue
    return total