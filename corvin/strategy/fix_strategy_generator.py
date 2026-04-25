"""
Fix strategy generator.

Produces a FixStrategyOutput from a completed RCAOutput.  In the full
implementation this module calls LiteLLM with a structured-output prompt and
the serialized RCA.

V1 boundary: this module produces a strategy only.  It does not execute,
approve, or schedule any remediation actions.
"""

from __future__ import annotations

import json
import os
from typing import Any

import litellm

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import FixStrategyOutput, InvestigationRequest, RCAOutput


class FixStrategyGenerator:
    """Generates a structured fix strategy from a completed RCA."""

    def __init__(
        self,
        model_config: dict[str, Any] | None = None,
        policy_config: dict[str, Any] | None = None,
    ) -> None:
        self._model_config = (
            model_config if model_config is not None else load_config("models/llm", get_env())
        )
        self._policy_config = (
            policy_config
            if policy_config is not None
            else load_config("policies/investigation", get_env())
        )

    def _build_messages(
        self,
        request: InvestigationRequest,
        rca: RCAOutput,
    ) -> list[dict[str, str]]:
        request_json = json.dumps(request.model_dump(mode="json"), indent=2, sort_keys=True)
        rca_json = json.dumps(rca.model_dump(mode="json"), indent=2, sort_keys=True)
        schema_json = json.dumps(FixStrategyOutput.model_json_schema(), indent=2, sort_keys=True)

        user_message = (
            "Generate a V1 fix strategy for this investigation. Return only a JSON object that "
            "matches the FixStrategyOutput schema exactly. Do not include markdown fences or any "
            "extra commentary. Do not include autonomous execution behavior.\n\n"
            f"InvestigationRequest:\n{request_json}\n\n"
            f"RCAOutput:\n{rca_json}\n\n"
            f"FixStrategyOutput schema:\n{schema_json}\n\n"
            f"Set request_id to {request.id}."
        )

        return [
            {
                "role": "system",
                "content": (
                    "You are Corvin. Produce only valid JSON matching the FixStrategyOutput "
                    "schema for a review-only remediation strategy."
                ),
            },
            {"role": "user", "content": user_message},
        ]

    def _build_completion_kwargs(self) -> dict[str, Any]:
        """
        Build the common litellm.completion kwargs.

        Includes temperature, max_tokens, response_format (JSON schema constraining
        the model to the FixStrategyOutput shape), and optional proxy settings read
        from LITELLM_ENDPOINT (-> api_base) and LITELLM_API_KEY (-> api_key)
        environment variables as documented in config/models/llm.yaml.
        """
        kwargs: dict[str, Any] = {
            "temperature": self._model_config.get("temperature", 0.1),
            "max_tokens": self._model_config.get("max_tokens", 4096),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "FixStrategyOutput",
                    "strict": True,
                    "schema": FixStrategyOutput.model_json_schema(),
                },
            },
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

    def _apply_policy(self, output: FixStrategyOutput) -> FixStrategyOutput:
        max_actions = int(self._policy_config.get("fix_strategy_max_actions", len(output.actions)))
        actions = output.actions[:max_actions]

        if self._policy_config.get("fix_execution_mode") == "review_only":
            actions = [action.model_copy(update={"requires_approval": True}) for action in actions]

        return output.model_copy(update={"actions": actions})

    def generate(
        self,
        request: InvestigationRequest,
        rca: RCAOutput,
    ) -> FixStrategyOutput:
        """
        Produce a structured FixStrategyOutput.
        """
        kwargs = self._build_completion_kwargs()
        kwargs["messages"] = self._build_messages(request, rca)

        response = litellm.completion(model=self._model_config["model"], **kwargs)

        output = FixStrategyOutput.model_validate(self._parse_response(response))
        return self._apply_policy(output)
