"""
RCA generator.

Produces a structured RCAOutput from an InvestigationRequest plus its
EvidenceBundle.  In the full implementation this module calls LiteLLM with
a structured-output prompt and the serialized evidence.

Config is loaded from config/models/llm.yaml.  All model IDs, endpoints,
and API keys live in config – not here.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Generator
from typing import Any

import litellm

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import EvidenceBundle, InvestigationRequest, RCAOutput


class RCAGenerator:
    """Generates structured RCA from a pre-enriched investigation request."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        policy_config: dict[str, Any] | None = None,
    ) -> None:
        self._config = config if config is not None else load_config("models/llm", get_env())
        self._policy_config = (
            policy_config
            if policy_config is not None
            else load_config("policies/investigation", get_env())
        )
        # Status of the last generate_stream() call.  One of:
        #   'ok'                    - streaming + parsing succeeded
        #   'insufficient_evidence' - evidence-gate rejected before any LLM call
        #   'degraded_non_streaming'- streaming failed, non-streaming retry succeeded
        #   'degraded_unparseable'  - streaming output was not valid JSON
        #   'degraded_failed'       - both streaming and non-streaming retry failed
        self.last_stream_status: str | None = None

    def _is_empty_value(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, dict):
            return not value or all(self._is_empty_value(item) for item in value.values())
        if isinstance(value, (list, tuple, set)):
            return not value
        if isinstance(value, str):
            return not value.strip()
        return False

    def _has_evidence(self, evidence: EvidenceBundle) -> bool:
        return any(
            not self._is_empty_value(source)
            for source in (
                evidence.elastic_logs,
                evidence.elastic_metrics,
                evidence.log_analytics_apim,
                evidence.aks_context,
                evidence.azure_activity_changes,
            )
        )

    def _insufficient_evidence_output(self, request: InvestigationRequest) -> RCAOutput:
        return RCAOutput(
            request_id=request.id,
            summary="Insufficient evidence collected to produce a trustworthy RCA.",
            root_cause=(
                "Corvin did not collect logs, metrics, platform context, or change "
                "evidence for this investigation."
            ),
            contributing_factors=["No evidence was available from the configured evidence sources."],
            confidence="low",
            evidence_references=[],
        )

    def _build_messages(
        self,
        request: InvestigationRequest,
        evidence: EvidenceBundle,
        system_prompt: str | None,
    ) -> list[dict[str, str]]:
        request_json = json.dumps(request.model_dump(mode="json"), indent=2, sort_keys=True)
        evidence_json = json.dumps(evidence.model_dump(mode="json"), indent=2, sort_keys=True)
        schema_json = json.dumps(RCAOutput.model_json_schema(), indent=2, sort_keys=True)

        user_message = (
            "Generate a root-cause analysis for this investigation. Return only a JSON object "
            "that matches the RCAOutput schema exactly. Do not include markdown fences or any "
            "extra commentary.\n\n"
            f"InvestigationRequest:\n{request_json}\n\n"
            f"EvidenceBundle:\n{evidence_json}\n\n"
            f"RCAOutput schema:\n{schema_json}\n\n"
            f"Set request_id to {request.id}. Use evidence_references to cite the evidence you used."
        )

        return [
            {
                "role": "system",
                "content": system_prompt
                or "You are Corvin. Produce only valid JSON matching the RCAOutput schema.",
            },
            {"role": "user", "content": user_message},
        ]

    def _build_completion_kwargs(self) -> dict[str, Any]:
        """
        Build the common litellm.completion kwargs.

        Includes temperature, max_tokens, response_format (JSON schema constraining
        the model to the RCAOutput shape), and optional proxy settings read from
        LITELLM_ENDPOINT (-> api_base) and LITELLM_API_KEY (-> api_key) environment
        variables as documented in config/models/llm.yaml.
        """
        kwargs: dict[str, Any] = {
            "temperature": self._config.get("temperature", 0.1),
            "max_tokens": self._config.get("max_tokens", 4096),
            "response_format": {"type": "json_object"},
        }

        endpoint = os.environ.get("LITELLM_ENDPOINT", "").strip()
        api_key = os.environ.get("LITELLM_API_KEY", "").strip()
        api_version = os.environ.get("AZURE_API_VERSION", "").strip()

        if endpoint:
            kwargs["api_base"] = endpoint
        if api_key:
            kwargs["api_key"] = api_key
        if api_version:
            kwargs["api_version"] = api_version

        return kwargs

    def _parse_response(self, response: Any) -> dict[str, Any]:
        """
        Extract and parse the model output from a LiteLLM response.

        Handles two paths:
          1. Structured output path: response.choices[0].message.parsed contains a
             Pydantic object or dict (LiteLLM native / OpenAI structured outputs).
          2. Text path: response.choices[0].message.content is a JSON string
             (standard chat completion or proxy text response).
        """
        if isinstance(response, dict):
            msg = response["choices"][0]["message"]
            parsed = msg.get("parsed") if isinstance(msg, dict) else None
            if parsed is not None:
                return parsed if isinstance(parsed, dict) else parsed.model_dump(mode="json")
            content = str(msg["content"])
        else:
            msg = response.choices[0].message
            if hasattr(msg, "parsed") and msg.parsed is not None:
                parsed = msg.parsed
                return parsed if isinstance(parsed, dict) else parsed.model_dump(mode="json")
            content = str(msg.content)

        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].lstrip()
        return json.loads(cleaned)

    def generate(
        self,
        request: InvestigationRequest,
        evidence: EvidenceBundle,
        system_prompt: str | None = None,
    ) -> RCAOutput:
        """
        Produce a structured RCAOutput.
        """
        if self._policy_config.get("require_evidence_before_rca", True) and not self._has_evidence(evidence):
            return self._insufficient_evidence_output(request)

        kwargs = self._build_completion_kwargs()
        kwargs["messages"] = self._build_messages(request, evidence, system_prompt)

        try:
            response = litellm.completion(model=self._config["model"], **kwargs)
        except Exception:
            fallback_model = self._config.get("fallback_model")
            if not fallback_model:
                raise
            response = litellm.completion(model=fallback_model, **kwargs)

        return RCAOutput.model_validate(self._parse_response(response))

    def generate_stream(
        self,
        request: InvestigationRequest,
        evidence: EvidenceBundle,
        system_prompt: str | None = None,
    ) -> Generator[tuple[str | None, RCAOutput | None], None, None]:
        """Like generate() but yields (token_text, None) for each chunk, then (None, RCAOutput).

        Callers iterate this generator: when the first element is a str it is a
        raw token from the LLM; when it is None the second element holds the
        fully-parsed RCAOutput.
        """
        # Reset status — set to a terminal value before each yield-of-result path.
        self.last_stream_status = None

        if self._policy_config.get("require_evidence_before_rca", True) and not self._has_evidence(evidence):
            self.last_stream_status = "insufficient_evidence"
            yield (None, self._insufficient_evidence_output(request))
            return

        kwargs = self._build_completion_kwargs()
        # json_object response_format causes Azure OpenAI to buffer the entire
        # response before sending any tokens — drop it on the streaming path
        # and rely on the prompt's JSON instruction instead.
        kwargs.pop("response_format", None)
        kwargs["messages"] = self._build_messages(request, evidence, system_prompt)
        accumulated = ""

        try:
            kwargs_stream = {**kwargs, "stream": True}
            try:
                response = litellm.completion(model=self._config["model"], **kwargs_stream)
            except Exception:
                fallback_model = self._config.get("fallback_model")
                if not fallback_model:
                    raise
                response = litellm.completion(model=fallback_model, **kwargs_stream)

            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    accumulated += text
                    yield (text, None)

        except Exception as exc:
            _log = logging.getLogger(__name__)
            _log.warning("RCAGenerator.generate_stream fell back to non-streaming: %s", exc)
            try:
                response = litellm.completion(model=self._config["model"], **kwargs)
                self.last_stream_status = "degraded_non_streaming"
                yield (None, RCAOutput.model_validate(self._parse_response(response)))
                return
            except Exception:
                self.last_stream_status = "degraded_failed"
                yield (None, self._insufficient_evidence_output(request))
                return

        yield (None, self._parse_accumulated_rca(accumulated, request))

    def _parse_accumulated_rca(self, text: str, request: InvestigationRequest) -> RCAOutput:
        """Parse a raw accumulated LLM text response into an RCAOutput."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].lstrip()
        try:
            output = RCAOutput.model_validate(json.loads(cleaned))
            self.last_stream_status = "ok"
            return output
        except Exception:
            self.last_stream_status = "degraded_unparseable"
            return self._insufficient_evidence_output(request)
