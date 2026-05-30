"""
Debate Orchestrator for Corvin War Room.

Spawns multiple specialised LLM agents in parallel threads to debate an incident.
Yields tokens from both agents as they stream, and then produces a final consensus.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import asyncio
from collections.abc import Generator, AsyncGenerator
from typing import Any

import litellm

litellm.drop_params = True

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import EvidenceBundle, InvestigationRequest, RCAOutput
from corvin.strategy.rca_generator import RCAGenerator

_log = logging.getLogger(__name__)


class DebateOrchestrator:
    """Orchestrates a multi-agent debate over an investigation."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config if config is not None else load_config("models/llm", get_env())
        # We reuse RCAGenerator for evidence formatting helpers
        self._rca_gen = RCAGenerator(config=self._config)

    def _build_agent_messages(
        self,
        agent_role: str,
        request: InvestigationRequest,
        evidence: EvidenceBundle,
        original_rca: RCAOutput,
    ) -> list[dict[str, str]]:
        
        request_json = json.dumps(request.model_dump(mode="json"), indent=2, sort_keys=True)
        evidence_json = json.dumps(evidence.model_dump(mode="json"), indent=2, sort_keys=True)
        rca_json = json.dumps(original_rca.model_dump(mode="json"), indent=2, sort_keys=True)
        source_summary = self._rca_gen._build_evidence_source_summary(evidence)

        if agent_role == "alpha":
            specialty = "Infrastructure Specialist (focuses on CPU, Memory, Pod Crashes, Limits, and Node Pressure)"
        else:
            specialty = "Network & App Specialist (focuses on 5xx errors, APIM timeouts, Deployments, and Latency)"

        system = (
            f"You are Agent {agent_role.title()}, a {specialty}. "
            "You are debating root cause with another specialist agent. "
            "Respond in well-structured Markdown. Use **bold** for key findings, "
            "`code` for technical terms, and bullet points (- ) for listing evidence. "
            "Do NOT produce JSON."
        )
        user = (
            "Review the evidence and the Original RCA below.\n"
            "Formulate a strong, 2-3 paragraph hypothesis for the root cause based on your specialty.\n"
            "If the Original RCA is wrong or missed something in your domain, call it out aggressively.\n"
            "If the Original RCA is correct, provide additional supporting evidence from your domain.\n\n"
            f"EVIDENCE COVERAGE:\n{source_summary}\n\n"
            f"Original RCA:\n{rca_json}\n\n"
            f"EvidenceBundle:\n{evidence_json}\n\n"
            f"InvestigationRequest:\n{request_json}\n\n"
            "Write 2-3 paragraphs using Markdown formatting. Bold key conclusions. "
            "Use bullet points for specific evidence. Do not output JSON."
        )

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def _build_judge_messages(
        self,
        request: InvestigationRequest,
        alpha_text: str,
        beta_text: str,
    ) -> list[dict[str, str]]:
        system = (
            "You are the Judge Agent for a multi-agent SRE debate. "
            "Produce only valid JSON matching the RCAOutput schema. "
            "IMPORTANT: The 'root_cause' and 'summary' fields MUST be written in rich Markdown. "
            "Use **bold** for key technical terms, `backticks` for service names and ports, "
            "and bullet lists (- ) where appropriate. "
            "Do NOT wrap text fields in code fences — they go directly inside the JSON string value."
        )
        schema_json = json.dumps(RCAOutput.model_json_schema(), indent=2, sort_keys=True)
        user = (
            "Review the debate between Agent Alpha and Agent Beta regarding this investigation.\n"
            "Synthesize their arguments and produce the final, definitive RCA as a JSON object.\n\n"
            f"Agent Alpha (Infra) Hypothesis:\n{alpha_text}\n\n"
            f"Agent Beta (Network) Hypothesis:\n{beta_text}\n\n"
            f"RCAOutput schema:\n{schema_json}\n\n"
            f"Set request_id to {request.id}. "
            "Write 'root_cause' and 'summary' as Markdown strings (bold key terms, use bullet points). "
            "Return only the JSON object."
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    async def _astream_agent(
        self,
        agent_id: str,
        messages: list[dict[str, str]],
        q: asyncio.Queue,
    ) -> None:
        import os
        from openai import AsyncAzureOpenAI
        
        endpoint = os.environ.get("LITELLM_ENDPOINT", "").strip()
        api_key = os.environ.get("LITELLM_API_KEY", "").strip()
        api_version = os.environ.get("AZURE_API_VERSION", "").strip()
        
        client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )

        model_name = self._config["model"].replace("azure/", "").replace("responses/", "")
        
        kwargs = {
            "model": model_name,
            "messages": messages,
            "stream": True,
            "max_completion_tokens": self._config.get("max_tokens", 4096),
        }
        
        # o1/o3 and some modern models reject temperature unless it is exactly 1
        if "o1" not in model_name.lower() and "o3" not in model_name.lower():
            kwargs["temperature"] = self._config.get("temperature", 0.1)
        
        try:
            response = await client.chat.completions.create(**kwargs)
            async for chunk in response:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        await q.put((agent_id, delta.content))
        except Exception as exc:
            _log.warning("Debate agent %s failed: %s", agent_id, exc)
            await q.put((agent_id, f"[Error running agent: {exc}]"))
        finally:
            await q.put((agent_id, None))

    async def generate_debate_stream_async(
        self,
        request: InvestigationRequest,
        evidence: EvidenceBundle,
        original_rca: RCAOutput,
    ) -> AsyncGenerator[tuple[str, str | None, RCAOutput | None], None]:
        """
        Yields (agent_id, token, None) for streaming tokens from 'alpha' and 'beta'.
        When both are done, the judge runs, and yields ('judge', None, Final_RCAOutput).
        """
        q: asyncio.Queue = asyncio.Queue()
        
        alpha_messages = self._build_agent_messages("alpha", request, evidence, original_rca)
        beta_messages = self._build_agent_messages("beta", request, evidence, original_rca)

        task_alpha = asyncio.create_task(self._astream_agent("alpha", alpha_messages, q))
        task_beta = asyncio.create_task(self._astream_agent("beta", beta_messages, q))
        
        active_agents = 2
        alpha_full = ""
        beta_full = ""

        while active_agents > 0:
            agent_id, token = await q.get()
            if token is None:
                active_agents -= 1
            else:
                if agent_id == "alpha":
                    alpha_full += token
                elif agent_id == "beta":
                    beta_full += token
                yield (agent_id, token, None)

        await asyncio.gather(task_alpha, task_beta)

        # Run Judge (async for the final schema)
        judge_messages = self._build_judge_messages(request, alpha_full, beta_full)
        kwargs = self._rca_gen._build_completion_kwargs()
        kwargs["messages"] = judge_messages
        
        try:
            response = await litellm.acompletion(model=self._config["model"], **kwargs)
            final_rca = RCAOutput.model_validate(self._rca_gen._parse_response(response))
            final_rca = self._rca_gen._normalize_evidence_references(final_rca, evidence)
        except Exception as exc:
            _log.warning("Debate Judge failed: %s", exc)
            # Fallback to original RCA if judge fails
            final_rca = original_rca

        yield ("judge", None, final_rca)
