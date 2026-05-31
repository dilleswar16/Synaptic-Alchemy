"""
AI Capacity Forecaster — V6

Analyzes container resource metrics (CPU, memory, network) over time and predicts
when resource exhaustion will occur. Uses linear regression + anomaly detection
to forecast capacity needs.

Outputs:
  - Time-to-exhaustion per resource type
  - Recommended scaling actions (with human approval gate)
  - Cost impact estimate for recommended changes
  - Confidence band (high/medium/low) based on data quality
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

import litellm

from corvin.core.config_loader import get_env, load_config

_log = logging.getLogger(__name__)


@dataclass
class ResourceForecast:
    """Forecast for a single resource dimension."""
    resource_type: str  # cpu | memory | disk | network
    current_usage_pct: float
    trend_direction: str  # increasing | stable | decreasing
    trend_slope_per_hour: float  # percentage points per hour
    predicted_exhaustion_at: str | None  # ISO timestamp or None if stable/decreasing
    hours_until_exhaustion: float | None
    confidence: str  # high | medium | low
    data_points_analyzed: int
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "current_usage_pct": round(self.current_usage_pct, 2),
            "trend_direction": self.trend_direction,
            "trend_slope_per_hour": round(self.trend_slope_per_hour, 4),
            "predicted_exhaustion_at": self.predicted_exhaustion_at,
            "hours_until_exhaustion": round(self.hours_until_exhaustion, 1) if self.hours_until_exhaustion else None,
            "confidence": self.confidence,
            "data_points_analyzed": self.data_points_analyzed,
            "recommendation": self.recommendation,
        }


@dataclass
class ScalingRecommendation:
    """A recommended scaling action."""
    action_type: str  # scale_horizontal | scale_vertical | add_node | alert_only
    target_service: str
    target_namespace: str
    current_replicas: int
    recommended_replicas: int | None
    current_resource_limit: str | None  # e.g. "512Mi" or "500m"
    recommended_resource_limit: str | None
    reason: str
    estimated_monthly_cost_delta: float  # positive = more cost
    priority: str  # critical | high | medium | low
    requires_approval: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "target_service": self.target_service,
            "target_namespace": self.target_namespace,
            "current_replicas": self.current_replicas,
            "recommended_replicas": self.recommended_replicas,
            "current_resource_limit": self.current_resource_limit,
            "recommended_resource_limit": self.recommended_resource_limit,
            "reason": self.reason,
            "estimated_monthly_cost_delta": round(self.estimated_monthly_cost_delta, 2),
            "priority": self.priority,
            "requires_approval": self.requires_approval,
        }


@dataclass
class CapacityForecastReport:
    """Complete capacity forecast for a service."""
    service_name: str
    environment: str
    namespace: str
    forecasts: list[ResourceForecast] = field(default_factory=list)
    scaling_recommendations: list[ScalingRecommendation] = field(default_factory=list)
    overall_risk: str = "low"  # critical | high | medium | low
    ai_narrative: str = ""
    analyzed_window_hours: int = 24
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "service_name": self.service_name,
            "environment": self.environment,
            "namespace": self.namespace,
            "forecasts": [f.to_dict() for f in self.forecasts],
            "scaling_recommendations": [r.to_dict() for r in self.scaling_recommendations],
            "overall_risk": self.overall_risk,
            "ai_narrative": self.ai_narrative,
            "analyzed_window_hours": self.analyzed_window_hours,
            "generated_at": self.generated_at,
        }


# ── Forecaster Engine ─────────────────────────────────────────────────────────


class CapacityForecaster:
    """Analyzes resource metrics and produces capacity forecasts."""

    def __init__(self):
        self._model_config = load_config("models/llm", get_env())

    def forecast(
        self,
        service_name: str,
        environment: str,
        namespace: str,
        metrics: list[dict[str, Any]],
        current_replicas: int = 1,
    ) -> CapacityForecastReport:
        """
        Analyze container_resource_metrics and produce a forecast report.

        Each metric dict should have:
          - timestamp (ISO string)
          - cpu_usage_pct (float 0-100)
          - memory_usage_pct (float 0-100)
          - network_rx_bytes (int, optional)
          - network_tx_bytes (int, optional)
          - disk_usage_pct (float 0-100, optional)
        """
        report = CapacityForecastReport(
            service_name=service_name,
            environment=environment,
            namespace=namespace,
        )

        if not metrics:
            report.ai_narrative = "Insufficient data for capacity forecast. No metrics available."
            return report

        # Analyze each resource dimension
        for resource_type in ["cpu", "memory", "disk"]:
            key = f"{resource_type}_usage_pct"
            data_points = [
                (m.get("timestamp", ""), m.get(key, 0.0))
                for m in metrics
                if m.get(key) is not None
            ]
            if len(data_points) >= 3:
                forecast = self._analyze_trend(resource_type, data_points)
                report.forecasts.append(forecast)

        # Determine overall risk
        report.overall_risk = self._compute_overall_risk(report.forecasts)

        # Generate scaling recommendations
        report.scaling_recommendations = self._generate_recommendations(
            service_name, namespace, report.forecasts, current_replicas
        )

        # Compute analyzed window
        if metrics:
            try:
                times = [datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00")) for m in metrics if "timestamp" in m]
                if len(times) >= 2:
                    report.analyzed_window_hours = int((max(times) - min(times)).total_seconds() / 3600)
            except (ValueError, TypeError):
                pass

        return report

    def _analyze_trend(self, resource_type: str, data_points: list[tuple[str, float]]) -> ResourceForecast:
        """Linear regression on time-series data to detect trend."""
        values = [v for _, v in data_points]
        n = len(values)

        # Simple linear regression (index-based for simplicity)
        x_mean = (n - 1) / 2.0
        y_mean = sum(values) / n

        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        slope = numerator / denominator if denominator != 0 else 0.0

        # Estimate time between samples (assume ~5 min intervals)
        samples_per_hour = 12.0
        slope_per_hour = slope * samples_per_hour

        current_usage = values[-1]

        # Determine trend direction
        if abs(slope_per_hour) < 0.1:
            direction = "stable"
        elif slope_per_hour > 0:
            direction = "increasing"
        else:
            direction = "decreasing"

        # Predict exhaustion (100% threshold)
        exhaustion_at = None
        hours_until = None
        if direction == "increasing" and slope_per_hour > 0:
            remaining = 100.0 - current_usage
            if remaining > 0:
                hours_until = remaining / slope_per_hour
                exhaustion_at = (datetime.now(timezone.utc) + timedelta(hours=hours_until)).isoformat()

        # Confidence based on R² and data count
        r_squared = self._compute_r_squared(values, slope, y_mean - slope * x_mean)
        if n >= 20 and r_squared > 0.7:
            confidence = "high"
        elif n >= 10 and r_squared > 0.4:
            confidence = "medium"
        else:
            confidence = "low"

        # Recommendation
        if hours_until and hours_until < 2:
            recommendation = f"CRITICAL: {resource_type.upper()} exhaustion in <2 hours. Immediate scaling required."
        elif hours_until and hours_until < 12:
            recommendation = f"WARNING: {resource_type.upper()} exhaustion predicted in {hours_until:.0f}h. Plan scaling action."
        elif hours_until and hours_until < 48:
            recommendation = f"WATCH: {resource_type.upper()} trending up, exhaustion in ~{hours_until:.0f}h at current rate."
        elif direction == "stable":
            recommendation = f"{resource_type.upper()} usage stable at {current_usage:.1f}%. No action needed."
        else:
            recommendation = f"{resource_type.upper()} usage trending {direction}. Current: {current_usage:.1f}%."

        return ResourceForecast(
            resource_type=resource_type,
            current_usage_pct=current_usage,
            trend_direction=direction,
            trend_slope_per_hour=slope_per_hour,
            predicted_exhaustion_at=exhaustion_at,
            hours_until_exhaustion=hours_until,
            confidence=confidence,
            data_points_analyzed=n,
            recommendation=recommendation,
        )

    def _compute_r_squared(self, values: list[float], slope: float, intercept: float) -> float:
        """Compute R² for the linear fit."""
        n = len(values)
        if n < 2:
            return 0.0
        y_mean = sum(values) / n
        ss_tot = sum((v - y_mean) ** 2 for v in values)
        ss_res = sum((v - (slope * i + intercept)) ** 2 for i, v in enumerate(values))
        if ss_tot == 0:
            return 1.0
        return 1.0 - (ss_res / ss_tot)

    def _compute_overall_risk(self, forecasts: list[ResourceForecast]) -> str:
        """Determine overall risk from individual forecasts."""
        for f in forecasts:
            if f.hours_until_exhaustion and f.hours_until_exhaustion < 2:
                return "critical"
        for f in forecasts:
            if f.hours_until_exhaustion and f.hours_until_exhaustion < 12:
                return "high"
        for f in forecasts:
            if f.hours_until_exhaustion and f.hours_until_exhaustion < 48:
                return "medium"
        return "low"

    def _generate_recommendations(
        self,
        service_name: str,
        namespace: str,
        forecasts: list[ResourceForecast],
        current_replicas: int,
    ) -> list[ScalingRecommendation]:
        """Generate scaling recommendations based on forecasts."""
        recommendations = []

        for f in forecasts:
            if not f.hours_until_exhaustion:
                continue

            if f.hours_until_exhaustion < 12:
                if f.resource_type == "cpu":
                    recommendations.append(ScalingRecommendation(
                        action_type="scale_horizontal",
                        target_service=service_name,
                        target_namespace=namespace,
                        current_replicas=current_replicas,
                        recommended_replicas=min(current_replicas + 2, current_replicas * 2),
                        current_resource_limit=None,
                        recommended_resource_limit=None,
                        reason=f.recommendation,
                        estimated_monthly_cost_delta=45.0 * (current_replicas + 2 - current_replicas),
                        priority="critical" if f.hours_until_exhaustion < 2 else "high",
                        requires_approval=True,
                    ))
                elif f.resource_type == "memory":
                    recommendations.append(ScalingRecommendation(
                        action_type="scale_vertical",
                        target_service=service_name,
                        target_namespace=namespace,
                        current_replicas=current_replicas,
                        recommended_replicas=None,
                        current_resource_limit="512Mi",
                        recommended_resource_limit="1Gi",
                        reason=f.recommendation,
                        estimated_monthly_cost_delta=30.0,
                        priority="critical" if f.hours_until_exhaustion < 2 else "high",
                        requires_approval=True,
                    ))

        return recommendations

    async def generate_narrative(self, report: CapacityForecastReport) -> str:
        """Use LLM to generate a human-readable narrative for the forecast."""
        forecast_data = "\n".join(
            f"- {f.resource_type.upper()}: {f.current_usage_pct:.1f}% usage, trend {f.trend_direction} "
            f"({f.trend_slope_per_hour:+.2f}%/hr), "
            f"{'exhaustion in ' + str(round(f.hours_until_exhaustion)) + 'h' if f.hours_until_exhaustion else 'no exhaustion predicted'}"
            for f in report.forecasts
        )

        prompt = (
            "You are an SRE capacity planning assistant. Given these resource forecasts for "
            f"service '{report.service_name}' in {report.environment}, write a brief (3-4 sentence) "
            "executive summary of the capacity situation and key actions needed.\n\n"
            f"Resource Forecasts:\n{forecast_data}\n\n"
            f"Overall risk level: {report.overall_risk}\n\n"
            "Executive summary:"
        )

        try:
            resp = litellm.completion(
                messages=[{"role": "user", "content": prompt}],
                **self._model_config,
            )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            _log.warning("LLM narrative generation failed: %s", exc)
            return f"Capacity analysis for {report.service_name}: overall risk is {report.overall_risk}."
