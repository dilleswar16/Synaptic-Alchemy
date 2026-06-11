"""
Natural Language to KQL — F6 Agentic Feature

Translates natural language questions into valid Kusto Query Language (KQL)
queries targeting the configured Log Analytics workspace. Includes guardrails
to prevent destructive operations and validates query structure.

Used by:
- Command Center agent tool (run_kql enhancement)
- Dedicated API endpoint for ad-hoc exploration
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import litellm

litellm.drop_params = True

from corvin.core.config_loader import get_env, load_config
from corvin.core.prompt_registry import get_prompt_registry

_log = logging.getLogger(__name__)

# Patterns that indicate destructive/management commands
_BLOCKED_PATTERNS = re.compile(
    r"\.(drop|set|delete|purge|create|alter|append|move|replace|rename)\s",
    re.IGNORECASE,
)


class NLToKQLService:
    """Translates natural language to KQL with safety guardrails."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config if config is not None else load_config("models/llm", get_env())

    def translate(self, question: str, time_range: str | None = None) -> dict[str, Any]:
        """Convert a natural language question to KQL.
        
        Returns:
            {"query": "<kql>", "explanation": "<brief explanation>", "safe": True/False}
        """
        model = self._config.get("fallback_model") or self._config.get("model")
        if not model:
            raise ValueError("models/llm.yaml must define 'model' or 'fallback_model'")
        user_msg = question
        if time_range:
            user_msg += f"\n(Time range: {time_range})"

        try:
            response = litellm.completion(
                model=model,
                messages=[
                    {"role": "system", "content": get_prompt_registry().get("nl_to_kql")},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.0,
                max_tokens=1024,
            )
            query = response.choices[0].message.content.strip()
            # Strip markdown fences if present
            if query.startswith("```"):
                query = query.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            safe = not bool(_BLOCKED_PATTERNS.search(query))
            if not safe:
                _log.warning("NL-to-KQL produced blocked query: %s", query)
                return {
                    "query": None,
                    "explanation": "Query contains blocked management commands and was rejected.",
                    "safe": False,
                    "original_question": question,
                }

            return {
                "query": query,
                "explanation": f"KQL translation of: {question}",
                "safe": True,
                "original_question": question,
            }
        except Exception as exc:
            _log.error("NL-to-KQL translation failed: %s", exc)
            return {
                "query": None,
                "explanation": f"Translation failed: {exc}",
                "safe": False,
                "original_question": question,
            }
