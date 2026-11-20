"""Provider-neutral access to large language models.

This is the ONLY module that knows which AI vendor is used. Everything else calls :class:`LlmGateway` with a
feature name, a model tier, a system prompt, prompt sections and (optionally) a Pydantic output schema.
Switch providers with ``LLM_PROVIDER`` in ``backend/.env``: gemini | azure_openai | openai_compatible | anthropic | mock.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import random
import time
import types
import typing
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum, StrEnum
from typing import Any, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select

from keigan.ai.ai_safety_settings import get_ai_safety_settings
from keigan.ai.prompt_safety import UNTRUSTED_DATA_POLICY, generate_boundary, spotlight
from keigan.config.database_config import open_session
from keigan.config.logging_config import current_correlation_id
from keigan.config.settings import LlmProviderName, Settings
from keigan.entities.platform_entities import LlmUsageRecord
from keigan.exceptions.keigan_exceptions import (
    LlmAuthenticationException,
    LlmOutputValidationException,
    LlmRateLimitedException,
    LlmRequestRejectedException,
    LlmTimeoutException,
    LlmUnavailableException,
    TokenBudgetExceededException,
)

logger = logging.getLogger(__name__)

OutputSchemaType = TypeVar("OutputSchemaType", bound=BaseModel)
BUDGET_CACHE_SECONDS = 60
USAGE_FLUSH_DELAY_SECONDS = 2.0
USAGE_FLUSH_MAXIMUM_ATTEMPTS = 30


class LlmFailureKind(StrEnum):
    """Why an AI call failed, in the terms of what the person reading the error can do about it."""

    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION = "authentication"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


# What the user is told per kind. The provider's own text is never shown (it can carry hosts, index names and keys); it goes to the log.
LLM_FAILURE_RESPONSES: dict[LlmFailureKind, tuple[type[LlmUnavailableException], str]] = {
    LlmFailureKind.TIMEOUT: (LlmTimeoutException, "The AI service took too long to answer. Try again; a smaller time window or a shorter question is answered faster."),
    LlmFailureKind.RATE_LIMITED: (LlmRateLimitedException, "The AI service is busy and asked Keigan to slow down. Try again in a minute."),
    LlmFailureKind.AUTHENTICATION: (
        LlmAuthenticationException, "The AI service rejected Keigan's credentials. This is a setup problem that waiting will not fix: ask a Keigan admin to check the AI provider key.",
    ),
    LlmFailureKind.REJECTED: (
        LlmRequestRejectedException, "The AI service rejected this request (for example an unknown model name or too much text). Ask a Keigan admin to check the AI model settings.",
    ),
    LlmFailureKind.UNAVAILABLE: (LlmUnavailableException, "The AI service is not responding. Try again in a few minutes."),
}
_AUTHENTICATION_MARKERS = ("api key", "api_key", "unauthenticated", "unauthorized", "permission denied", "invalid_api_key", "authentication")
_RATE_LIMIT_MARKERS = ("rate limit", "resource exhausted", "resource has been exhausted", "quota", "too many requests")
_REJECTED_MARKERS = ("does not exist", "model not found", "context length", "maximum context", "too many tokens", "invalid request")


def classify_llm_failure(invocation_error: BaseException) -> LlmFailureKind:
    """Sort a provider SDK error into the kind that decides the advice. Works on the status code first, then on the message, because SDKs differ."""
    if isinstance(invocation_error, TimeoutError) or "timeout" in type(invocation_error).__name__.lower():
        return LlmFailureKind.TIMEOUT
    status_code = (
        getattr(invocation_error, "status_code", None)
        or getattr(getattr(invocation_error, "response", None), "status_code", None)
        or (code if isinstance(code := getattr(invocation_error, "code", None), int) else None)
    )
    error_text = str(invocation_error).lower()
    if isinstance(status_code, int) and status_code >= 500:
        return LlmFailureKind.UNAVAILABLE  # an outage, whatever the text says
    if status_code in (401, 403) or (status_code in (400, None) and any(marker in error_text for marker in _AUTHENTICATION_MARKERS)):
        return LlmFailureKind.AUTHENTICATION
    if status_code == 429 or (status_code is None and any(marker in error_text for marker in _RATE_LIMIT_MARKERS)):
        return LlmFailureKind.RATE_LIMITED
    if status_code in (400, 404, 413, 422) or (status_code is None and any(marker in error_text for marker in _REJECTED_MARKERS)):
        return LlmFailureKind.REJECTED
    return LlmFailureKind.UNAVAILABLE


class ModelTier(StrEnum):
    FAST = "fast"
    DEEP = "deep"
    VISION = "vision"


@dataclass
class PromptSection:
    """One block of the user message. ``is_untrusted`` content is spotlighted and never treated as instructions."""

    title: str
    content: str
    is_untrusted: bool = False
    source_label: str = ""
    maximum_characters: int = 20_000
    is_flagged: bool = False  # the source is already known to look like a prompt-injection attempt; mark its block with a warning


@dataclass
class LlmUsageContext:
    application_id: str | None = None
    investigation_id: str | None = None
    conversation_id: str | None = None
    requested_by_user_principal_name: str | None = None
    enforce_token_budget: bool = True


@dataclass
class LlmCallResult:
    text: str
    input_token_count: int = 0
    output_token_count: int = 0
    model_name: str = ""


@dataclass
class _BudgetCacheEntry:
    used_token_count: int
    read_at: float


MockFactory = Callable[[type[BaseModel], list[PromptSection]], BaseModel]
_mock_response_factories: dict[str, MockFactory] = {}


def register_mock_response(feature_name: str, factory: MockFactory) -> None:
    """Slices register realistic offline responses for LLM_PROVIDER=mock (used for UI work without an API key)."""
    _mock_response_factories[feature_name] = factory


def estimate_token_count(text: str | None) -> int:
    """Cheap estimate: ~4 characters per token for Latin text, ~1 per character for CJK."""
    if not text:
        return 0
    non_ascii_character_count = sum(1 for character in text if ord(character) > 0x2E7F)
    return (len(text) - non_ascii_character_count) // 4 + non_ascii_character_count + 1


class LlmGateway:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._concurrency_limiter = asyncio.Semaphore(settings.llm_max_concurrent_requests)
        self._chat_models_by_tier: dict[ModelTier, BaseChatModel] = {}
        self._budget_cache_by_application: dict[str, _BudgetCacheEntry] = {}
        self._pending_usage_records: list[dict[str, Any]] = []
        self._usage_flush_task: asyncio.Task[None] | None = None

    # ── Introspection ──────────────────────────────────────────────────────────
    @property
    def provider_name(self) -> str:
        return str(self.settings.llm_provider)

    @property
    def is_mock(self) -> bool:
        return self.settings.llm_provider == LlmProviderName.MOCK

    def model_name_for(self, model_tier: ModelTier) -> str:
        return {
            ModelTier.FAST: self.settings.llm_fast_model,
            ModelTier.DEEP: self.settings.llm_deep_model,
            ModelTier.VISION: self.settings.llm_vision_model,
        }[model_tier]

    # ── Chat model construction (the only vendor-specific code) ────────────────
    def chat_model(self, model_tier: ModelTier) -> BaseChatModel:
        """LangChain chat model for tool-calling agents (LangGraph). Not available in mock mode."""
        if self.is_mock:
            raise LlmUnavailableException("LLM_PROVIDER=mock has no chat model; use generate_text / generate_structured.")
        if model_tier not in self._chat_models_by_tier:
            self._chat_models_by_tier[model_tier] = self._create_chat_model(self.model_name_for(model_tier))
        return self._chat_models_by_tier[model_tier]

    def _create_chat_model(self, model_name: str) -> BaseChatModel:
        settings = self.settings
        common_options: dict[str, Any] = {"timeout": settings.llm_request_timeout_seconds, "max_retries": 0}
        if settings.llm_temperature >= 0:
            common_options["temperature"] = settings.llm_temperature

        if settings.llm_provider == LlmProviderName.GEMINI:
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(model=model_name, google_api_key=settings.llm_api_key, **common_options)

        if settings.llm_provider == LlmProviderName.AZURE_OPENAI:
            from langchain_openai import AzureChatOpenAI

            azure_options: dict[str, Any] = {
                "azure_endpoint": settings.llm_base_url,
                "api_version": settings.llm_api_version,
                "azure_deployment": model_name,
                "default_headers": settings.llm_extra_headers or None,
            }
            if settings.llm_use_managed_identity:
                from azure.identity import ManagedIdentityCredential, get_bearer_token_provider

                azure_options["azure_ad_token_provider"] = get_bearer_token_provider(
                    ManagedIdentityCredential(client_id=settings.azure_client_id or None),
                    "https://cognitiveservices.azure.com/.default",
                )
            else:
                azure_options["api_key"] = settings.llm_api_key
            return AzureChatOpenAI(**azure_options, **common_options)

        if settings.llm_provider == LlmProviderName.OPENAI_COMPATIBLE:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=model_name,
                base_url=settings.llm_base_url or None,
                api_key=settings.llm_api_key or "not-required",
                default_headers=settings.llm_extra_headers or None,
                **common_options,
            )

        if settings.llm_provider == LlmProviderName.ANTHROPIC:
            from langchain_anthropic import ChatAnthropic  # optional dependency: pip install -e .[anthropic]

            return ChatAnthropic(model=model_name, api_key=settings.llm_api_key, **common_options)

        raise LlmUnavailableException(f"Unsupported LLM_PROVIDER {settings.llm_provider}.")

    # ── Public API ─────────────────────────────────────────────────────────────
    async def generate_structured(
        self,
        *,
        feature_name: str,
        model_tier: ModelTier,
        system_prompt: str,
        prompt_sections: list[PromptSection],
        output_schema: type[OutputSchemaType],
        usage_context: LlmUsageContext,
    ) -> OutputSchemaType:
        """Ask the model for an answer that must validate against ``output_schema`` (one repair retry)."""
        await self._ensure_budget_available(usage_context)
        if self.is_mock:
            return self._build_mock_structured_response(feature_name, output_schema, prompt_sections)

        messages = self._build_messages(system_prompt, prompt_sections)
        model_name = self.model_name_for(model_tier)
        structured_model = self.chat_model(model_tier).with_structured_output(
            output_schema, include_raw=True, method=self.settings.llm_structured_output_method  # type: ignore[arg-type]
        )
        validation_problem: str | None = None
        for attempt_number in (1, 2):
            attempt_messages = list(messages)
            if validation_problem:
                attempt_messages.append(
                    HumanMessage(
                        content=f"Your previous answer did not match the required schema: {validation_problem[:1500]}\n"
                        "Answer again and follow the schema exactly."
                    )
                )
            started_at = time.monotonic()
            try:
                structured_response = await self._invoke_with_resilience(structured_model, attempt_messages)
            except Exception as invocation_error:
                await self._record_usage(feature_name, model_tier, model_name, 0, 0, started_at, "failed", usage_context, str(invocation_error))
                raise
            raw_message = structured_response.get("raw") if isinstance(structured_response, dict) else None
            input_tokens, output_tokens = self._extract_token_usage(raw_message)
            parsed_output = structured_response.get("parsed") if isinstance(structured_response, dict) else structured_response
            parsing_error = structured_response.get("parsing_error") if isinstance(structured_response, dict) else None
            if parsed_output is not None and parsing_error is None:
                if isinstance(parsed_output, dict):
                    try:
                        parsed_output = output_schema.model_validate(parsed_output)
                    except ValidationError as schema_error:
                        parsing_error = schema_error
                if parsing_error is None:
                    await self._record_usage(feature_name, model_tier, model_name, input_tokens, output_tokens, started_at, "succeeded", usage_context)
                    return parsed_output  # type: ignore[return-value]
            validation_problem = str(parsing_error or "empty response")
            await self._record_usage(
                feature_name, model_tier, model_name, input_tokens, output_tokens, started_at, "validation_retry", usage_context, validation_problem
            )
            logger.warning("Structured output for %s failed validation (attempt %s): %s", feature_name, attempt_number, validation_problem[:300])
        raise LlmOutputValidationException(f"The AI answer for {feature_name} could not be validated.")

    async def generate_text(
        self,
        *,
        feature_name: str,
        model_tier: ModelTier,
        system_prompt: str,
        prompt_sections: list[PromptSection],
        usage_context: LlmUsageContext,
    ) -> LlmCallResult:
        await self._ensure_budget_available(usage_context)
        if self.is_mock:
            return LlmCallResult(text=self._mock_text_response(feature_name, prompt_sections), model_name="mock")
        model_name = self.model_name_for(model_tier)
        started_at = time.monotonic()
        try:
            response_message = await self._invoke_with_resilience(self.chat_model(model_tier), self._build_messages(system_prompt, prompt_sections))
        except Exception as invocation_error:
            await self._record_usage(feature_name, model_tier, model_name, 0, 0, started_at, "failed", usage_context, str(invocation_error))
            raise
        input_tokens, output_tokens = self._extract_token_usage(response_message)
        await self._record_usage(feature_name, model_tier, model_name, input_tokens, output_tokens, started_at, "succeeded", usage_context)
        return LlmCallResult(
            text=self._message_text(response_message), input_token_count=input_tokens, output_token_count=output_tokens, model_name=model_name
        )

    async def describe_image(
        self, *, image_bytes: bytes, content_type: str, instruction: str, usage_context: LlmUsageContext, feature_name: str = "architecture_image_description"
    ) -> LlmCallResult:
        await self._ensure_budget_available(usage_context)
        if self.is_mock:
            return LlmCallResult(
                text="Simulated description (LLM_PROVIDER=mock): an architecture diagram showing clients calling an API gateway, "
                "which routes to application services on AKS backed by a SQL database and a message queue.",
                model_name="mock",
            )
        model_name = self.model_name_for(ModelTier.VISION)
        encoded_image = base64.b64encode(image_bytes).decode("ascii")
        image_message = HumanMessage(
            content=[
                {"type": "text", "text": instruction},
                {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{encoded_image}"}},
            ]
        )
        started_at = time.monotonic()
        try:
            response_message = await self._invoke_with_resilience(
                self.chat_model(ModelTier.VISION), [SystemMessage(content=UNTRUSTED_DATA_POLICY), image_message]
            )
        except Exception as invocation_error:
            await self._record_usage(feature_name, ModelTier.VISION, model_name, 0, 0, started_at, "failed", usage_context, str(invocation_error))
            raise
        input_tokens, output_tokens = self._extract_token_usage(response_message)
        await self._record_usage(feature_name, ModelTier.VISION, model_name, input_tokens, output_tokens, started_at, "succeeded", usage_context)
        return LlmCallResult(text=self._message_text(response_message), input_token_count=input_tokens, output_token_count=output_tokens, model_name=model_name)

    async def record_external_usage(
        self, *, feature_name: str, model_tier: ModelTier, input_token_count: int, output_token_count: int, usage_context: LlmUsageContext, latency_milliseconds: int = 0
    ) -> None:
        """For callers that drive ``chat_model()`` directly (LangGraph agents) and want their tokens accounted."""
        await self._record_usage(
            feature_name, model_tier, self.model_name_for(model_tier), input_token_count, output_token_count,
            time.monotonic() - latency_milliseconds / 1000, "succeeded", usage_context,
        )

    async def ensure_budget_available(self, usage_context: LlmUsageContext) -> None:
        await self._ensure_budget_available(usage_context)

    # ── Internals ──────────────────────────────────────────────────────────────
    def _build_messages(self, system_prompt: str, prompt_sections: list[PromptSection]) -> list[BaseMessage]:
        boundary = generate_boundary()
        rendered_sections: list[str] = []
        for prompt_section in prompt_sections:
            section_body = (
                spotlight(prompt_section.content, prompt_section.source_label or prompt_section.title, boundary, prompt_section.maximum_characters, prompt_section.is_flagged)
                if prompt_section.is_untrusted
                else prompt_section.content
            )
            rendered_sections.append(f"## {prompt_section.title}\n{section_body}")
        return [
            SystemMessage(content=f"{system_prompt.strip()}\n\n{UNTRUSTED_DATA_POLICY}"),
            HumanMessage(content="\n\n".join(rendered_sections)),
        ]

    async def _invoke_with_resilience(self, runnable: Any, messages: list[BaseMessage]) -> Any:
        last_error: Exception | None = None
        self._log_prompt(messages)
        for attempt_index in range(self.settings.llm_maximum_retries + 1):
            try:
                async with self._concurrency_limiter:
                    return await asyncio.wait_for(runnable.ainvoke(messages), timeout=self.settings.llm_request_timeout_seconds + 5)
            except Exception as invocation_error:  # noqa: BLE001
                last_error = invocation_error
                if not self._is_retryable(invocation_error) or attempt_index == self.settings.llm_maximum_retries:
                    break
                back_off_seconds = min(30.0, (2**attempt_index) + random.uniform(0, 1))
                logger.warning("LLM call failed (%s); retrying in %.1fs", type(invocation_error).__name__, back_off_seconds)
                await asyncio.sleep(back_off_seconds)
        assert last_error is not None  # the loop only leaves without a result after an error
        failure_kind = classify_llm_failure(last_error)
        logger.warning("LLM call failed (%s) after %s attempt(s): %s: %s", failure_kind, self.settings.llm_maximum_retries + 1, type(last_error).__name__, str(last_error)[:500])
        exception_class, advice = LLM_FAILURE_RESPONSES[failure_kind]
        raise exception_class(f"{advice} If it keeps failing, quote reference {current_correlation_id() or 'none'} to a Keigan admin.") from last_error

    def _log_prompt(self, messages: list[BaseMessage]) -> None:
        """Prompts hold customer telemetry, so they are logged as a hash (enough to tell two calls apart); the text only on a developer machine that switched it on."""
        prompt_text = "\n\n".join(self._message_text(message) for message in messages)
        logger.debug("LLM prompt sha256=%s characters=%s", hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(), len(prompt_text))
        if self.settings.log_prompts_for_debugging:
            logger.info("LLM prompt text (LOG_PROMPTS_FOR_DEBUGGING is on):\n%s", prompt_text)

    @staticmethod
    def _is_retryable(invocation_error: Exception) -> bool:
        if isinstance(invocation_error, asyncio.TimeoutError):
            return True
        status_code = getattr(invocation_error, "status_code", None) or getattr(getattr(invocation_error, "response", None), "status_code", None)
        if status_code in (401, 403, 400, 404, 422):
            return False
        if status_code in (408, 409, 429) or (isinstance(status_code, int) and status_code >= 500):
            return True
        error_text = str(invocation_error).lower()
        return any(marker in error_text for marker in ("rate limit", "resource exhausted", "429", "timeout", "temporarily", "unavailable", "overloaded"))

    @staticmethod
    def _extract_token_usage(response_message: Any) -> tuple[int, int]:
        usage_metadata = getattr(response_message, "usage_metadata", None) or {}
        return int(usage_metadata.get("input_tokens", 0) or 0), int(usage_metadata.get("output_tokens", 0) or 0)

    @staticmethod
    def _message_text(response_message: Any) -> str:
        message_content = getattr(response_message, "content", response_message)
        if isinstance(message_content, list):
            return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in message_content)
        return str(message_content or "")

    @staticmethod
    def _budget_key(usage_context: LlmUsageContext) -> str | None:
        """Calls of one application share the application's budget; calls that belong to no application (chat across several
        applications) are charged to the asking user instead, so they cannot bypass the budget."""
        if usage_context.application_id:
            return usage_context.application_id
        if usage_context.requested_by_user_principal_name:
            return f"user:{usage_context.requested_by_user_principal_name}"
        return None

    async def _ensure_budget_available(self, usage_context: LlmUsageContext) -> None:
        budget_key = self._budget_key(usage_context)
        if not usage_context.enforce_token_budget or budget_key is None:
            return
        cache_entry = self._budget_cache_by_application.get(budget_key)
        if cache_entry is None or time.monotonic() - cache_entry.read_at > BUDGET_CACHE_SECONDS:
            start_of_day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            owner_condition = (
                LlmUsageRecord.application_id == usage_context.application_id
                if usage_context.application_id
                else (LlmUsageRecord.application_id.is_(None) & (LlmUsageRecord.requested_by_user_principal_name == usage_context.requested_by_user_principal_name))
            )
            async with open_session() as session:
                used_token_count = await session.scalar(
                    select(func.coalesce(func.sum(LlmUsageRecord.input_token_count + LlmUsageRecord.output_token_count), 0)).where(owner_condition, LlmUsageRecord.created_at >= start_of_day)
                )
            cache_entry = _BudgetCacheEntry(int(used_token_count or 0), time.monotonic())
            self._budget_cache_by_application[budget_key] = cache_entry
        if usage_context.application_id:
            if cache_entry.used_token_count >= self.settings.llm_daily_token_budget_per_application:
                raise TokenBudgetExceededException(f"Today's AI token budget ({self.settings.llm_daily_token_budget_per_application:,}) for this application is used up.")
        elif cache_entry.used_token_count >= get_ai_safety_settings().llm_daily_token_budget_per_user:
            raise TokenBudgetExceededException(
                f"Your AI token budget for today ({get_ai_safety_settings().llm_daily_token_budget_per_user:,}) for questions across several applications is used up. Ask about one application, or try again tomorrow."
            )

    async def _record_usage(
        self,
        feature_name: str,
        model_tier: ModelTier,
        model_name: str,
        input_token_count: int,
        output_token_count: int,
        started_at: float,
        outcome_status: str,
        usage_context: LlmUsageContext,
        error_message: str | None = None,
    ) -> None:
        budget_key = self._budget_key(usage_context)
        if budget_key and budget_key in self._budget_cache_by_application:
            self._budget_cache_by_application[budget_key].used_token_count += input_token_count + output_token_count
        self._pending_usage_records.append(
            {
                "application_id": usage_context.application_id,
                "investigation_id": usage_context.investigation_id,
                "conversation_id": usage_context.conversation_id,
                "feature_name": feature_name,
                "provider_name": self.provider_name,
                "model_name": model_name,
                "model_tier": str(model_tier),
                "input_token_count": input_token_count,
                "output_token_count": output_token_count,
                "latency_milliseconds": int((time.monotonic() - started_at) * 1000),
                "outcome_status": outcome_status,
                "error_message": (error_message or "")[:2000] or None,
                "requested_by_user_principal_name": usage_context.requested_by_user_principal_name,
            }
        )
        if self._usage_flush_task is None or self._usage_flush_task.done():
            self._usage_flush_task = asyncio.create_task(self._flush_usage_records())

    async def _flush_usage_records(self) -> None:
        """Write usage rows in the background so an AI call never waits on another transaction's database lock (SQLite)."""
        for attempt_index in range(USAGE_FLUSH_MAXIMUM_ATTEMPTS):
            await asyncio.sleep(USAGE_FLUSH_DELAY_SECONDS)
            records_to_write, self._pending_usage_records = self._pending_usage_records, []
            if not records_to_write:
                return
            try:
                async with open_session() as session:
                    session.add_all(LlmUsageRecord(**record_values) for record_values in records_to_write)
                return
            except Exception as recording_error:  # noqa: BLE001 — accounting must never break the feature
                self._pending_usage_records = records_to_write + self._pending_usage_records
                logger.warning("Could not record LLM usage yet (attempt %s): %s", attempt_index + 1, recording_error)

    # ── Mock provider ──────────────────────────────────────────────────────────
    def _build_mock_structured_response(
        self, feature_name: str, output_schema: type[OutputSchemaType], prompt_sections: list[PromptSection]
    ) -> OutputSchemaType:
        registered_factory = _mock_response_factories.get(feature_name)
        if registered_factory is not None:
            return output_schema.model_validate(registered_factory(output_schema, prompt_sections).model_dump())
        return output_schema.model_validate(_build_placeholder_value(output_schema, feature_name))

    @staticmethod
    def _mock_text_response(feature_name: str, prompt_sections: list[PromptSection]) -> str:
        return (
            "This is a simulated answer because Keigan is running with `LLM_PROVIDER=mock`. "
            "Set `LLM_PROVIDER=gemini` (or another provider) and `LLM_API_KEY` in `backend/.env` to get real analysis."
        )


def _build_placeholder_value(annotation: Any, field_name: str, depth: int = 0) -> Any:
    """Schema-valid placeholder data for the mock provider (used when no feature-specific mock is registered)."""
    origin = typing.get_origin(annotation)
    arguments = typing.get_args(annotation)
    if depth > 6:
        return None
    if origin in (typing.Union, types.UnionType):
        non_none_arguments = [argument for argument in arguments if argument is not type(None)]
        return _build_placeholder_value(non_none_arguments[0], field_name, depth + 1) if non_none_arguments else None
    if origin is typing.Literal:
        return arguments[0]
    if origin in (list, tuple, set):
        return [_build_placeholder_value(arguments[0] if arguments else str, field_name, depth + 1)]
    if origin is dict:
        return {}
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return {
            model_field_name: (
                model_field.default
                if model_field.default is not None and not callable(model_field.default) and model_field.default is not ...
                else _build_placeholder_value(model_field.annotation, model_field_name, depth + 1)
            )
            for model_field_name, model_field in annotation.model_fields.items()
        }
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return next(iter(annotation)).value
    if annotation is bool:
        return False
    if annotation is int:
        return 1
    if annotation is float:
        return 0.6
    if annotation is datetime:
        return datetime.now(UTC) - timedelta(minutes=30)
    readable_field_name = field_name.replace("_", " ")
    return f"Simulated {readable_field_name} (LLM_PROVIDER=mock)"
