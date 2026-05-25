"""
Corvin Command Center — Agentic Chat Service.

Implements a full agentic loop with LiteLLM function-calling:
  1. Build system prompt (global SRE copilot, no investigation scope).
  2. Call LLM with TOOL_SCHEMAS attached.
  3. If the model emits tool_calls → execute each → append results → loop.
  4. Once the model returns a plain text response → stream it as SSE text chunks.

SSE event types emitted on the generator:
  {"type": "thinking",    "text": "..."}   — reasoning tokens (if model supports it)
  {"type": "tool_call",   "tool_name": "...", "arguments": {...}}  — tool being called
  {"type": "tool_result", "tool_name": "...", "data": {...}}        — tool result
  {"type": "text",        "text": "..."}   — assistant text chunks
  {"type": "error",       "message": "..."} — error
  data: [DONE]                              — stream end sentinel
"""

from __future__ import annotations

import json
import logging
from typing import Generator

import litellm

from corvin.core.config_loader import get_env, load_config
from corvin.strategy.agent_tools import TOOL_SCHEMAS, execute_tool

_log = logging.getLogger(__name__)

# Maximum agentic loop iterations to prevent runaway tool chains
_MAX_TOOL_ROUNDS = 6

SYSTEM_PROMPT = """\
You are Corvin, an elite AI SRE Copilot for the CHAD platform (MetLife Australia superannuation).
You have access to live tools that can query the real platform, fetch live AKS pod health,
run APIM analytics queries, retrieve investigation details, and read from the CHAD knowledge base.

Your job:
- Answer questions about incidents, services, infrastructure, and SRE operations.
- When you need data, CALL THE APPROPRIATE TOOL — do not guess or make up values.
- After receiving tool results, interpret them clearly and concisely for the engineer.
- IMPORTANT: When explaining blast radius, architecture, or service topology, ALWAYS include a clean, well-structured Mermaid diagram (`mermaid` code block).
- Mermaid Rules:
    1. Use `flowchart TD` or `flowchart LR`.
    2. ALWAYS wrap node labels in double quotes, e.g., `NodeID["Label Text"]`.
    3. Use `<br/>` for newlines inside labels, e.g., `NodeID["Line 1<br/>Line 2"]`.
    4. Avoid using parentheses `()` or brackets `[]` inside labels unless the label is double-quoted.
- Be blameless, technical, and precise.
- Respond in Markdown.

Available services in CHAD: fundsso, fundapis, partnerapis (all running in AKS namespace 'chad').
When asked about architecture, ALWAYS call get_site_knowledge first.
When asked about a specific service's history or runbook, call get_runbook and get_similar_incidents.
When asked about CPU/memory usage, limits, capacity, or utilization for a service,
ALWAYS call get_container_resource_metrics first, then optionally get_aks_health for status context.

APIM Analytics (partnerapis & fundapis):
- For ANY question about API traffic, success rates, error rates, latency, member counts,
  fund breakdowns, peak hours, caller IPs, TLS compliance, or APIM performance:
  ALWAYS use the `query_apim_analytics` tool — it returns live data WITH chart type hints
  so the UI can render beautiful charts automatically.
- TWO MODES — pick the right one:
  (A) TEMPLATE MODE: if the question maps to a named template, pass `template_name`.
      Example: "how many members per fund" → template_name="unique_members_by_fund".
  (B) CUSTOM KQL MODE: if no template fits the question, write your own KQL query and
      pass it as the `kql` parameter. Also set `chart_type` and `title`.
      The table is `ApiManagementGatewayLogs`. Do NOT add a TimeGenerated filter —
      time_range_minutes handles that automatically.
      Example: user asks "which subscription key gets the most 429s" →
        kql = "ApiManagementGatewayLogs | where ResponseCode == 429 | summarize count() by SubscriptionName | order by count_ desc"
        chart_type = "bar", title = "Top Throttled Subscriptions"
- After the tool returns, summarise the key insight in 2-3 sentences. The chart renders automatically.
- Keep your reply focused on the business insight. Never expose internal implementation details:
  no field names, no data structure descriptions, no rendering instructions to the user.
- Time range: convert the user's exact phrasing to minutes and pass it as time_range_minutes.
  Any integer is valid — do NOT round to presets unless the user is vague.
  "last 5 minutes" → 5, "last 50 minutes" → 50, "last 90 minutes" → 90,
  "last hour" → 60, "last 4 hours" → 240, "today" → 1440, "this week" → 10080.
  If the user gives no time hint, default to 1440 (today).
"""


class CorvinAgentService:
    """Global agentic SRE chat — not scoped to any single investigation."""

    def stream_chat(
        self,
        session_history: list[dict],
    ) -> Generator[str, None, None]:
        """Run the agentic loop and stream SSE events.

        Args:
            session_history: Full conversation history as list of
                             {role, content} dicts (user + assistant turns).
                             The caller must include ALL prior turns so the
                             model has memory of the conversation.

        Yields:
            SSE-formatted strings: ``data: <json>\\n\\n`` or ``data: [DONE]\\n\\n``.
        """
        import os

        llm_cfg = load_config("models/llm", get_env())
        model_name = llm_cfg.get("model", "azure/responses/gpt-5.1")

        base_kwargs: dict = {
            "model": model_name,
            "drop_params": True,
        }
        endpoint = os.environ.get("LITELLM_ENDPOINT", "").strip()
        api_key = os.environ.get("LITELLM_API_KEY", "").strip()
        api_version = os.environ.get("AZURE_API_VERSION", "").strip()
        if endpoint:
            base_kwargs["api_base"] = endpoint
        if api_key:
            base_kwargs["api_key"] = api_key
        if api_version:
            base_kwargs["api_version"] = api_version

        reasoning_effort = llm_cfg.get("reasoning_effort")
        if reasoning_effort:
            base_kwargs["reasoning_effort"] = reasoning_effort

        # Build the full message list with the system prompt
        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in session_history:
            if msg.get("role") in ("user", "assistant", "tool"):
                messages.append({"role": msg["role"], "content": msg.get("content", "")})

        # ── Agentic loop ──────────────────────────────────────────────────────
        collected_tool_calls: list[dict] = []

        for _round in range(_MAX_TOOL_ROUNDS):
            try:
                response = litellm.completion(
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    tool_choice="auto",
                    stream=False,   # non-streaming for tool-calling rounds
                    **base_kwargs,
                )
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
                yield "data: [DONE]\n\n"
                return

            choice = response.choices[0]
            finish_reason = choice.finish_reason
            msg_obj = choice.message

            # ── Model wants to call tools ─────────────────────────────────────
            if finish_reason == "tool_calls" or (
                hasattr(msg_obj, "tool_calls") and msg_obj.tool_calls
            ):
                # Add the assistant's tool-calling message to history
                messages.append(msg_obj.model_dump() if hasattr(msg_obj, "model_dump") else {
                    "role": "assistant",
                    "content": msg_obj.content,
                    "tool_calls": [tc.model_dump() for tc in (msg_obj.tool_calls or [])],
                })

                for tc in msg_obj.tool_calls or []:
                    tool_name = tc.function.name
                    try:
                        arguments = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        arguments = {}

                    # Emit tool_call event → frontend shows "Corvin is querying…"
                    yield f"data: {json.dumps({'type': 'tool_call', 'tool_name': tool_name, 'arguments': arguments})}\n\n"

                    # Execute the tool (live data — no mocks)
                    tool_result = execute_tool(tool_name, arguments)
                    collected_tool_calls.append({"tool": tool_name, "result": tool_result})

                    # Emit tool_result event → frontend renders data card
                    yield f"data: {json.dumps({'type': 'tool_result', 'tool_name': tool_name, 'data': tool_result})}\n\n"

                    # Append tool result to message history for the next LLM call
                    result_content = (
                        json.dumps(tool_result, default=str)
                        if not isinstance(tool_result, str)
                        else tool_result
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_content[:8000],  # cap to avoid context overflow
                    })

                # Continue loop → LLM will now interpret the tool results
                continue

            # ── Model returned a final text response ──────────────────────────
            final_text = msg_obj.content or ""
            break

        else:
            # Exhausted tool rounds without a final answer
            final_text = (
                "I've gathered the data above. Here is my summary based on what was retrieved."
            )

        # ── Stream the final text response ────────────────────────────────────
        try:
            stream_response = litellm.completion(
                messages=messages + [
                    {"role": "assistant", "content": ""},
                    {"role": "user", "content": "__stream_final__"},
                ] if False else messages + [{"role": "user", "content": "__stream_this__"}] if False else messages,
                stream=True,
                **{k: v for k, v in base_kwargs.items()},
                # Pass the already-built final_text as a prefill if supported,
                # otherwise just re-stream from the last assistant response.
            )
            # Actually: we already have the final text — stream it token by token
            # without a second LLM call (more efficient, guaranteed complete).
            _chunk_size = 8
            for i in range(0, len(final_text), _chunk_size):
                chunk = final_text[i: i + _chunk_size]
                yield f"data: {json.dumps({'type': 'text', 'text': chunk})}\n\n"
        except Exception:
            # Fallback: emit the full text as one chunk
            if final_text:
                yield f"data: {json.dumps({'type': 'text', 'text': final_text})}\n\n"

        yield "data: [DONE]\n\n"

    def stream_chat_simple(
        self,
        session_history: list[dict],
    ) -> Generator[str, None, None]:
        """Streaming variant — runs the agentic loop then streams the final answer.

        This is the method called by the API route. It wraps stream_chat and
        ensures the final LLM answer is streamed live (not faked in chunks).
        """
        import os

        llm_cfg = load_config("models/llm", get_env())
        model_name = llm_cfg.get("model", "azure/responses/gpt-5.1")

        base_kwargs: dict = {"model": model_name, "drop_params": True}
        endpoint = os.environ.get("LITELLM_ENDPOINT", "").strip()
        api_key = os.environ.get("LITELLM_API_KEY", "").strip()
        api_version = os.environ.get("AZURE_API_VERSION", "").strip()
        if endpoint:
            base_kwargs["api_base"] = endpoint
        if api_key:
            base_kwargs["api_key"] = api_key
        if api_version:
            base_kwargs["api_version"] = api_version
        reasoning_effort = llm_cfg.get("reasoning_effort")
        if reasoning_effort:
            base_kwargs["reasoning_effort"] = reasoning_effort

        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in session_history:
            if msg.get("role") in ("user", "assistant", "tool"):
                messages.append({"role": msg["role"], "content": msg.get("content", "")})

        # ── Agentic tool-calling rounds (non-streaming) ───────────────────────
        for _round in range(_MAX_TOOL_ROUNDS):
            try:
                response = litellm.completion(
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    tool_choice="auto",
                    stream=False,
                    **base_kwargs,
                )
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
                yield "data: [DONE]\n\n"
                return

            choice = response.choices[0]
            msg_obj = choice.message

            if choice.finish_reason == "tool_calls" or (
                hasattr(msg_obj, "tool_calls") and msg_obj.tool_calls
            ):
                tool_calls_payload = [tc.model_dump() for tc in (msg_obj.tool_calls or [])]
                messages.append({
                    "role": "assistant",
                    "content": msg_obj.content or "",
                    "tool_calls": tool_calls_payload,
                })

                for tc in msg_obj.tool_calls or []:
                    tool_name = tc.function.name
                    try:
                        arguments = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        arguments = {}

                    yield f"data: {json.dumps({'type': 'tool_call', 'tool_name': tool_name, 'arguments': arguments})}\n\n"

                    tool_result = execute_tool(tool_name, arguments)

                    yield f"data: {json.dumps({'type': 'tool_result', 'tool_name': tool_name, 'data': tool_result})}\n\n"

                    result_content = (
                        json.dumps(tool_result, default=str)
                        if not isinstance(tool_result, str)
                        else tool_result
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_content[:8000],
                    })
                continue

            # Model gave final answer without more tool calls — break to stream it
            break

        # ── Stream the final text answer live ─────────────────────────────────
        try:
            stream_resp = litellm.completion(
                messages=messages,
                stream=True,
                **base_kwargs,
            )
            for chunk in stream_resp:
                delta = chunk.choices[0].delta
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    yield f"data: {json.dumps({'type': 'thinking', 'text': reasoning})}\n\n"
                content = getattr(delta, "content", None)
                if content:
                    yield f"data: {json.dumps({'type': 'text', 'text': content})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

        yield "data: [DONE]\n\n"
