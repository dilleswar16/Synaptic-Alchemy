"""What the administration page shows about the AI models in use: their resolved capabilities and the last conformance report (spec 23, phase 4 row 4.5). Read only."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from keigan.ai.model_capabilities import resolve_model_capabilities
from keigan.config.settings import Settings
from keigan.dtos.administration_dtos import ConformanceReportSummaryResponse, ModelCapabilitiesResponse

logger = logging.getLogger(__name__)


def model_capability_views(settings: Settings) -> list[ModelCapabilitiesResponse]:
    """One entry per model tier (fast, deep, vision) with what Keigan resolved for it: the overrides in the settings win over the shipped catalogue."""
    configured_models = (("fast", settings.llm_fast_model), ("deep", settings.llm_deep_model), ("vision", settings.llm_vision_model))
    views: list[ModelCapabilitiesResponse] = []
    for model_tier, model_name in configured_models:
        capabilities = resolve_model_capabilities(settings.llm_provider, model_name, settings.llm_model_capabilities_json)
        views.append(ModelCapabilitiesResponse(
            model_tier=model_tier, model_name=model_name, tool_calling=capabilities.tool_calling.value, parallel_tool_calls=capabilities.parallel_tool_calls,
            streams_text=capabilities.streams_text, streams_tool_requests=capabilities.streams_tool_requests, supports_tool_choice_none=capabilities.supports_tool_choice_none,
            supports_temperature=capabilities.supports_temperature, reports_stream_usage=capabilities.reports_stream_usage, max_context_tokens=capabilities.max_context_tokens,
        ))
    return views


def last_conformance_report(report_path: Path) -> ConformanceReportSummaryResponse | None:
    """The summary of the report the conformance script wrote last, or None when there is none or the file is not a report (it is a file an operator produced, so it is never trusted to be well formed)."""
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        return ConformanceReportSummaryResponse(
            generated_at=datetime.fromisoformat(report["generatedAt"]), passed=bool(report["passed"]), provider_name=str(report["providerName"]), model_name=str(report["modelName"]),
            tool_calling_mode=str(report["toolCallingMode"]), scenario_count=int(report["summary"]["scenarioCount"]), passed_count=int(report["summary"]["passedCount"]),
        )
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError, ValidationError) as unreadable:
        logger.warning("The conformance report at %s could not be read (%s); the administration page shows none.", report_path, unreadable)
        return None
