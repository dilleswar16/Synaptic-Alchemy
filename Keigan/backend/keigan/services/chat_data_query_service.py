"""Safe natural-language → log query pipeline shared by Keigan AI chat and the investigation chat agent.

Generate (deep model) → validate and harden → execute through the telemetry gateway → mask rows. Every executed query
is audited as ``ai.query.execute``. Nothing here writes to a monitored system.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.chat_ai_schemas import ChatQueryResult
from keigan.ai.llm_gateway import LlmUsageContext, ModelTier, PromptSection
from keigan.ai.output_sanitizer import sanitize_ai_line
from keigan.config import application_context
from keigan.entities.all_entities import (
    ApplicationComponent, LogToolConnection, MonitoredService, ServiceLogSource,
)
from keigan.exceptions.keigan_exceptions import BusinessValidationException, ReaderNotAvailableException
from keigan.integrations.telemetry_gateway import TelemetryQuery, TelemetryTarget
from keigan.services.audit_service import AuditService
from keigan.utils.pii_masker import PiiMasker
from keigan.utils.query_safety import describe_query_limits, validate_generated_query

_TIME_KEYS = ("TimeGenerated", "timestamp", "@timestamp", "window_start", "key_as_string", "_time")
_LOG_TOOL_LANGUAGES = {"elastic": "elastic_dsl", "splunk": "spl"}


class QueryNotAnswerableError(BusinessValidationException):
    """The model could not write a query for this question on this log source; the message is the explanation shown to the user."""

    error_code = "query_not_answerable"
    title = "Keigan cannot answer this from the logs"


@dataclass
class DataQueryOutcome:
    service_name: str
    source_kind: str
    query_language: str
    query_text: str
    time_range_start: datetime
    time_range_end: datetime
    rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    is_simulated: bool = False

    @property
    def series(self) -> list[tuple[str, float]]:
        """(time label, value) pairs when the rows look like a time series, else an empty list."""
        if not self.rows:
            return []
        time_key = next((key for key in _TIME_KEYS if key in self.rows[0]), None)
        value_key = self._value_key(time_key)
        if time_key is None or value_key is None:
            return []
        return [(str(row[time_key]), float(row.get(value_key) or 0)) for row in self.rows]

    @property
    def total(self) -> int:
        if not self.rows:
            return 0
        time_key = next((key for key in _TIME_KEYS if key in self.rows[0]), None)
        value_key = self._value_key(time_key)
        if value_key is None:
            return self.row_count
        return int(sum(float(row.get(value_key) or 0) for row in self.rows))

    def _value_key(self, time_key: str | None) -> str | None:
        first_row = self.rows[0]
        if "count_" in first_row:
            return "count_"
        return next((key for key, value in first_row.items() if key != time_key and isinstance(value, (int, float)) and not isinstance(value, bool)), None)


class ChatDataQueryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.gateway = application_context.llm_gateway()

    async def run(
        self,
        *,
        service: MonitoredService,
        question_text: str,
        wants_failures: bool,
        wants_pattern: bool,
        time_range_start: datetime,
        time_range_end: datetime,
        requested_by: str,
        usage_context: LlmUsageContext,
        on_query_generated: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> DataQueryOutcome:
        # Same rule the gateway enforces, checked first so a refused question costs no LLM call and the user gets the reason.
        await application_context.telemetry_access_policy().ensure_application_approved(service.application_id, self.session)
        target, query_language = await self._resolve_target(service)
        await application_context.telemetry_access_policy().ensure_can_read_source(target, self.session)
        range_minutes = max(1, int((time_range_end - time_range_start).total_seconds() // 60))
        generated = await self.gateway.generate_structured(
            feature_name="ai_chat_query_generation",
            model_tier=ModelTier.DEEP,
            system_prompt=application_context.prompt_library().render("ai_chat_query_generation"),
            prompt_sections=[
                PromptSection("Query request", json.dumps({
                    "serviceName": service.service_name, "serviceType": service.service_type, "queryLanguage": query_language,
                    "wantsFailures": wants_failures, "wantsPattern": wants_pattern, "rangeMinutes": range_minutes,
                    "bucketSuggestion": f"{max(5, range_minutes // 24)}m",
                })),
                PromptSection("Query limits", json.dumps(self._query_limits(target, query_language))),
                PromptSection("Question", PiiMasker().mask_text(question_text), is_untrusted=True, source_label="chat:user-question"),
            ],
            output_schema=ChatQueryResult,
            usage_context=usage_context,
        )
        self._ensure_query_was_written(generated, service.service_name)
        hardened_query = validate_generated_query(query_language, generated.query_text, time_range_start, time_range_end, query_scope=target.query_scope)
        if on_query_generated is not None:  # lets the caller show the query while it still runs (Ask Keigan's tool.progress event)
            await on_query_generated(hardened_query.query_language, hardened_query.query_text)
        query_result = await application_context.telemetry_gateway().query_logs(
            target,
            TelemetryQuery(
                query_language=hardened_query.query_language, query_text=hardened_query.query_text,
                time_range_start=time_range_start, time_range_end=time_range_end, query_purpose="ad_hoc",
                purpose_parameters={"signal_kind": "generic"},
            ),
        )
        await AuditService(self.session).record(
            requested_by, "ai.query.execute", target_entity_type="monitored_service", target_entity_id=service.service_id, application_id=service.application_id,
            action_details={"queryLanguage": hardened_query.query_language, "queryText": hardened_query.query_text, "rowCount": query_result.row_count, "source": "chat"},
        )
        return DataQueryOutcome(
            service_name=service.service_name, source_kind=target.source_kind, query_language=hardened_query.query_language, query_text=hardened_query.query_text,
            time_range_start=time_range_start, time_range_end=time_range_end, rows=PiiMasker().mask_rows(query_result.rows), row_count=query_result.row_count,
            is_simulated=query_result.is_simulated,
        )

    @staticmethod
    def _ensure_query_was_written(generated: ChatQueryResult, service_name: str) -> None:
        """The prompt lets the model return an empty query with an explanation when the question is outside the log source; that is an answer, not a rejection."""
        if generated.query_text.strip():
            return
        reason = sanitize_ai_line(generated.explanation) or "Try asking about the requests, errors or latency of this service."
        raise QueryNotAnswerableError(f"I can't answer that from the logs of {service_name}. {reason}")

    @staticmethod
    def _query_limits(target: TelemetryTarget, query_language: str) -> dict[str, object]:
        """What the model may use on this log source (index, fields, tables), from the same rules the validator enforces."""
        connection_configuration = target.log_tool_connection.connection_configuration_json if target.log_tool_connection else None
        return describe_query_limits(query_language, target.query_scope, connection_configuration)

    async def _resolve_target(self, service: MonitoredService) -> tuple[TelemetryTarget, str]:
        log_source = (await self.session.scalars(
            select(ServiceLogSource).where(ServiceLogSource.service_id == service.service_id).order_by(ServiceLogSource.is_primary_source.desc()).limit(1)
        )).first()
        if log_source is None:
            raise ReaderNotAvailableException(f"{service.service_name} has no log source connected yet, so Keigan cannot query its logs.")
        component = await self.session.get(ApplicationComponent, service.component_id) if service.component_id else None
        connection = await self.session.get(LogToolConnection, log_source.log_tool_connection_id) if log_source.log_tool_connection_id else None
        if log_source.source_kind in ("log_analytics", "application_insights"):
            query_language = "kql"
        elif connection is not None and connection.tool_type in _LOG_TOOL_LANGUAGES:
            query_language = _LOG_TOOL_LANGUAGES[connection.tool_type]
        else:
            raise ReaderNotAvailableException(f"Keigan cannot write queries for the {log_source.source_kind} source of {service.service_name} yet.")
        return TelemetryTarget.from_entities(service, log_source, component, connection), query_language
