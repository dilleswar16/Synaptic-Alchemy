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

# gpt-5 and o-series models do not support temperature/other params that
# standard GPT-4 models accept.  Instruct LiteLLM to silently drop any
# parameter the target model does not support rather than raising an error.
litellm.drop_params = True

# Automatically inject summary="detailed" into reasoning_effort when using
# Responses API models (azure/responses/* or openai/responses/*) so that
# the model's chain-of-thought reasoning is surfaced in delta.reasoning_content.
litellm.reasoning_auto_summary = True

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import EvidenceBundle, InvestigationRequest, RCAOutput
from corvin.core.prompt_registry import get_prompt_registry


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
                evidence.container_resource_metrics,
                evidence.container_inventory,
                evidence.node_inventory,
                evidence.network_metrics,
                evidence.pod_restarts,
                evidence.oom_kill_events,
                evidence.autoscaler_events,
                evidence.health_probe_failures,
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
            confidence_reasoning="Confidence is low because no evidence was collected from any adapter. Without logs, metrics, or platform context, any root cause would be a guess.",
            evidence_references=[],
        )

    def _build_evidence_source_summary(self, evidence: EvidenceBundle) -> str:
        """Build a human-readable summary of which sources Corvin queried and what was found.

        Dynamically iterates over all EvidenceBundle fields (except metadata)
        so the summary stays in sync when new adapters are added.

        Each line includes the human-readable label followed by the JSON field
        name in brackets so the LLM can reference evidence consistently using
        the field name that appears in the EvidenceBundle JSON.
        """
        # Fields that aren't evidence sources — skip entirely
        skip_fields = {"request_id", "collected_at"}
        # Deprecated fields — no longer collected, suppress from prompt
        deprecated_fields = {"azure_activity_changes"}
        # Human-readable names for known fields; unknown fields get auto-formatted
        friendly_names = {
            "elastic_logs": "Application Logs (Elastic)",
            "elastic_metrics": "Application Metrics (Elastic)",
            "log_analytics_apim": "API Gateway Logs (Log Analytics)",
            "aks_context": "Kubernetes Cluster Health (K8s API)",
            "container_resource_metrics": "Kubernetes Resource Usage (CPU/Memory with limits)",
            "container_inventory": "Container Images (image, state, restarts)",
            "node_inventory": "Kubernetes Node Health (status, pressure conditions)",
            "network_metrics": "Network Traffic (TX/RX bytes, errors)",
            "pod_restarts": "Kubernetes Pod Restarts (restart trends)",
            "oom_kill_events": "Kubernetes OOM Kill Events (out-of-memory kills)",
            "autoscaler_events": "Kubernetes Autoscaler Events (HPA scale decisions)",
            "health_probe_failures": "Kubernetes Health Probes (readiness/liveness failures)",
        }

        lines = []
        for field_name, field_info in EvidenceBundle.model_fields.items():
            if field_name in skip_fields or field_name in deprecated_fields:
                continue
            data = getattr(evidence, field_name)
            if isinstance(data, dict):
                count = len(data) if data else 0
            elif isinstance(data, list):
                count = len(data)
            else:
                continue
            label = friendly_names.get(field_name, field_name.replace("_", " ").title())
            status = f"{count} records found" if count > 0 else "0 results (checked, nothing found)"
            lines.append(f"- {label} [{field_name}]: {status}")
        return "\n".join(lines)

    def _evidence_reference_details(self, evidence: EvidenceBundle) -> dict[str, str]:
        """Build deterministic summary text for each evidence field."""
        details: dict[str, str] = {}
        skip_fields = {"request_id", "collected_at", "azure_activity_changes"}

        for field_name in EvidenceBundle.model_fields:
            if field_name in skip_fields:
                continue
            value = getattr(evidence, field_name)
            if isinstance(value, dict):
                count = len(value) if value else 0
            elif isinstance(value, list):
                count = len(value)
            else:
                continue
            noun = "record" if count == 1 else "records"
            status = f"{count} {noun} found" if count > 0 else "0 results (checked, nothing found)"
            details[field_name] = f"{field_name}: {status}"
        return details

    def _normalize_evidence_references(self, output: RCAOutput, evidence: EvidenceBundle) -> RCAOutput:
        """Normalize model references so UI shows actionable context, not bare keys."""
        if not output.evidence_references:
            return output

        detail_map = self._evidence_reference_details(evidence)
        normalized: list[str] = []
        seen: set[str] = set()

        for ref in output.evidence_references:
            text = str(ref).strip()
            if not text:
                continue
            lower = text.lower()
            if lower in detail_map:
                text = detail_map[lower]
            elif lower in {k.replace("_", " ") for k in detail_map}:
                canonical = next(k for k in detail_map if k.replace("_", " ") == lower)
                text = detail_map[canonical]

            if text not in seen:
                normalized.append(text)
                seen.add(text)

        return output.model_copy(update={"evidence_references": normalized})

    def _build_messages(
        self,
        request: InvestigationRequest,
        evidence: EvidenceBundle,
        system_prompt: str | None,
    ) -> list[dict[str, str]]:
        request_json = json.dumps(request.model_dump(mode="json"), indent=2, sort_keys=True)
        evidence_json = json.dumps(evidence.model_dump(mode="json"), indent=2, sort_keys=True)
        schema_json = json.dumps(RCAOutput.model_json_schema(), indent=2, sort_keys=True)

        # Build a summary of which data sources Corvin queried and what came back.
        # This prevents the LLM from suggesting the human manually check things
        # that Corvin already checked and found empty.
        source_summary = self._build_evidence_source_summary(evidence)

        user_message = (
            "Generate a root-cause analysis for this investigation. Return only a JSON object "
            "that matches the RCAOutput schema exactly. Do not include markdown fences or any "
            "extra commentary.\n\n"
            "ANALYSIS PRINCIPLES:\n"
            "1. Base your conclusion ONLY on the evidence provided. Do not assume a problem "
            "exists just because the user reported one — verify it against the data.\n"
            "2. If the evidence contradicts the reported issue (e.g. all metrics are normal, "
            "pods are healthy, no errors in logs), state that clearly. A finding of 'no issue "
            "detected' is a valid and useful RCA conclusion.\n"
            "3. Never suggest the operator manually check a data source that Corvin already "
            "queried. The evidence coverage summary below shows exactly what was checked. "
            "If a source returned 0 results, Corvin already checked — state that fact instead "
            "of asking the operator to re-check.\n\n"
            "CONFIDENCE RULES:\n"
            "Confidence reflects how certain you are about your conclusion, regardless of "
            "whether the conclusion is 'problem found' or 'no problem detected.'\n"
            "- 'high': strong evidence supports your conclusion. This applies equally to "
            "confirming a problem (clear error logs, abnormal metrics) AND to ruling one out "
            "(multiple sources checked, all healthy).\n"
            "- 'medium': evidence is mixed or incomplete — some indicators suggest an issue "
            "but others are inconclusive, making it hard to fully confirm or rule out.\n"
            "- 'low': insufficient evidence was collected (most sources returned errors or "
            "were unavailable), making any conclusion unreliable.\n\n"
            "For 'confidence_reasoning': write 1-2 plain-English sentences citing specific "
            "evidence that supports your confidence level.\n\n"
            "EVIDENCE REFERENCE RULES:\n"
            "Each evidence reference must include BOTH the exact field name and a concise "
            "observation/value. Example: 'pod_restarts: 0 results (checked, nothing found)' "
            "or 'elastic_logs: 42 records found with timeout traces'.\n"
            "Use only field names shown in square brackets in the coverage summary below "
            "(e.g. 'aks_context', 'container_resource_metrics', 'pod_restarts'). "
            "Do NOT invent field names that don't appear below. "
            "Do NOT reference 'azure_activity_changes' — that source is deprecated and no "
            "longer collected.\n\n"
            "EVIDENCE COVERAGE (what Corvin already queried):\n"
            f"{source_summary}\n\n"
            f"InvestigationRequest:\n{request_json}\n\n"
            f"EvidenceBundle:\n{evidence_json}\n\n"
            f"RCAOutput schema:\n{schema_json}\n\n"
            f"Set request_id to {request.id}. Use evidence_references to cite the evidence you used."
        )

        return [
            {
                "role": "system",
                "content": system_prompt or get_prompt_registry().get("rca_system"),
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

        # Pass reasoning_effort when configured (Responses API / o-series models).
        # Accepts either a plain string ("medium") or a dict
        # ({"effort": "medium", "summary": "detailed"}) — both are forwarded
        # directly to LiteLLM.  drop_params=True silently drops it for models
        # that don't support it so this is safe for all model paths.
        reasoning_effort = self._config.get("reasoning_effort")
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort

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

        output = RCAOutput.model_validate(self._parse_response(response))
        return self._normalize_evidence_references(output, evidence)

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
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    # Capture reasoning/thinking tokens (gpt-5, o-series models)
                    reasoning = getattr(delta, 'reasoning_content', None)
                    if reasoning:
                        yield (f"__thinking__:{reasoning}", None)
                    # Regular content tokens
                    if delta.content:
                        accumulated += delta.content
                        yield (delta.content, None)

        except Exception as exc:
            _log = logging.getLogger(__name__)
            _log.warning("RCAGenerator.generate_stream fell back to non-streaming: %s", exc)
            try:
                response = litellm.completion(model=self._config["model"], **kwargs)
                self.last_stream_status = "degraded_non_streaming"
                output = RCAOutput.model_validate(self._parse_response(response))
                yield (None, self._normalize_evidence_references(output, evidence))
                return
            except Exception:
                self.last_stream_status = "degraded_failed"
                yield (None, self._insufficient_evidence_output(request))
                return

        output = self._parse_accumulated_rca(accumulated, request)
        yield (None, self._normalize_evidence_references(output, evidence))

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
