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

_log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a KQL (Kusto Query Language) expert for Azure Log Analytics.
Convert the user's natural language question into a valid KQL query.

Available tables (use ONLY these):
- ApiManagementGatewayLogs: APIM request logs (BackendId, ResponseCode, TotalTime, Url, CallerIpAddress, ApiId, OperationId)
- ContainerLogV2: Kubernetes container stdout/stderr (ContainerName, PodName, LogMessage, TimeGenerated)
- KubePodInventory: Pod status (Name, Namespace, PodStatus, ContainerCount, RestartCount)
- KubeNodeInventory: Node status (Computer, Status, KubeletVersion)
- Perf: Performance counters (ObjectName, CounterName, CounterValue, Computer, InstanceName)
- AzureMetrics: Azure resource metrics (MetricName, Average, Maximum, ResourceId)
- AppExceptions: Application Insights exceptions (ExceptionType, OuterMessage, InnermostMessage)

Rules:
- Output ONLY the KQL query. No explanation, no markdown fences.
- Always include a time filter: | where TimeGenerated > ago(1h) (or user-specified range)
- Limit results: add | take 50 unless user requests aggregation
- NEVER use .drop, .set, .delete, .purge or any management commands
- Use summarize for aggregation questions
- Use project to select relevant columns
- Use render for visualization hints when appropriate

Examples:
Q: "Show me 503 errors in the last hour"
A: ApiManagementGatewayLogs | where TimeGenerated > ago(1h) | where ResponseCode == 503 | project TimeGenerated, BackendId, Url, TotalTime | take 50

Q: "Which pods restarted the most today?"
A: KubePodInventory | where TimeGenerated > ago(24h) | summarize TotalRestarts=max(RestartCount) by Name, Namespace | top 10 by TotalRestarts desc
"""

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
        model = self._config.get("fallback_model", "azure/gpt-4.1-mini")
        user_msg = question
        if time_range:
            user_msg += f"\n(Time range: {time_range})"

        try:
            response = litellm.completion(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
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
