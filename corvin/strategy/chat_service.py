"""
Chat Service — V3.95 Copilot Interaction
"""

import json
import logging
from typing import AsyncGenerator

import litellm

from corvin.core.contracts import InvestigationResult
from corvin.core.knowledge_loader import KnowledgeLoader
from corvin.core.config_loader import load_config, get_env

_log = logging.getLogger(__name__)

class ChatService:
    def __init__(self):
        self.knowledge = KnowledgeLoader()

    def stream_chat(self, result: InvestigationResult, messages: list[dict]) -> AsyncGenerator[str, None]:
        """
        Takes the investigation context and a list of OpenAI-style messages,
        injects the context as a system prompt, and yields SSE tokens.
        """
        # 1. Load CHAD knowledge — site architecture + any matching runbooks
        site_knowledge = self.knowledge.load_site_knowledge()
        runbook_list = self.knowledge.load_matching_runbooks(result.request.service_name)
        runbook = "\n".join(runbook_list)
        
        # 2. Build the System Prompt
        system_prompt = (
            "You are Corvin, an elite SRE AI Copilot. You are assisting a human operator "
            "with an active incident investigation. Your goal is to explain your reasoning, "
            "answer questions about the telemetry, and discuss fix strategies.\n\n"
            
            "=== INCIDENT CONTEXT ===\n"
            f"Investigation ID: {result.request.id}\n"
            f"Service: {result.request.service_name} ({result.request.environment})\n"
            f"Trigger: {result.request.trigger_source.value} - {result.request.description}\n\n"
            
            "=== ROOT CAUSE ANALYSIS (RCA) ===\n"
            f"Confidence: {result.rca.confidence.value}\n"
            f"Root Cause: {result.rca.root_cause}\n"
            f"Reasoning: {result.rca.confidence_reasoning}\n\n"
            
            "=== EVIDENCE ===\n"
            f"{json.dumps(result.evidence.model_dump(), indent=2, default=str)[:2000]}...\n\n"
            
            "=== FIX STRATEGY ===\n"
            f"Summary: {result.fix_strategy.summary if result.fix_strategy else 'None'}\n"
            f"Actions: {[a.title for a in result.fix_strategy.actions] if result.fix_strategy else 'None'}\n\n"
            
            "=== CHAD SITE KNOWLEDGE (Architecture & Conventions) ===\n"
            f"{site_knowledge[:3000] if site_knowledge else 'No site knowledge loaded.'}\n\n"

            "=== CHAD RUNBOOK FOR THIS SERVICE ===\n"
            f"{runbook[:2000] if runbook else 'No runbook exists yet for this service. You may help draft one.'}\n\n"

            "Be concise, technical, and blameless. Respond in Markdown. "
            "When greeting the user, introduce yourself as 'Corvin, your SRE copilot' and mention both the service name and the Investigation ID. "
            "Do not hallucinate data that is not present in the evidence or knowledge base."
        )

        llm_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            # only allow user and assistant roles
            if msg.get("role") in ("user", "assistant"):
                llm_messages.append({"role": msg["role"], "content": msg["content"]})

        llm_cfg = load_config("models/llm", get_env())
        model_name = llm_cfg.get("model", "azure/responses/gpt-5.1")

        # Build kwargs the same way rca_generator does — read from env vars so
        # this works out of the box in any environment where the RCA already works.
        import os
        completion_kwargs: dict = {
            "model": model_name,
            "messages": llm_messages,
            "stream": True,
            "drop_params": True,  # silently ignore unsupported params per model
        }
        endpoint = os.environ.get("LITELLM_ENDPOINT", "").strip()
        api_key  = os.environ.get("LITELLM_API_KEY", "").strip()
        api_version = os.environ.get("AZURE_API_VERSION", "").strip()
        if endpoint:
            completion_kwargs["api_base"] = endpoint
        if api_key:
            completion_kwargs["api_key"] = api_key
        if api_version:
            completion_kwargs["api_version"] = api_version

        # Forward reasoning_effort if the model supports it (e.g. gpt-5.1, o-series)
        reasoning_effort = llm_cfg.get("reasoning_effort")
        if reasoning_effort:
            completion_kwargs["reasoning_effort"] = reasoning_effort

        try:
            response = litellm.completion(**completion_kwargs)
            for chunk in response:
                delta = chunk.choices[0].delta

                # Emit thinking/reasoning tokens as a separate SSE type
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    yield f"data: {json.dumps({'type': 'thinking', 'text': reasoning})}\n\n"

                # Emit regular response tokens
                content = getattr(delta, "content", None)
                if content:
                    yield f"data: {json.dumps({'type': 'text', 'text': content})}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as exc:
            _log.error("Chat LLM failed: %s", exc)
            yield f"data: {json.dumps({'type': 'error', 'text': str(exc)})}\n\n"
            yield "data: [DONE]\n\n"
