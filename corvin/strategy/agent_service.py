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
from corvin.core.prompt_registry import get_prompt_registry
from corvin.strategy.agent_tools import TOOL_SCHEMAS, execute_tool

_log = logging.getLogger(__name__)

# Maximum agentic loop iterations to prevent runaway tool chains
_MAX_TOOL_ROUNDS = 6


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
        model_name = llm_cfg.get("model")
        if not model_name:
            raise ValueError("models/llm.yaml must define 'model'")

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
        messages: list[dict] = [{"role": "system", "content": get_prompt_registry().get("autonomous_agent_system")}]
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
        Tool-calling rounds are also streamed so reasoning/thinking tokens
        appear instantly — no dead silence while the model decides which tool
        to call.
        """
        import os

        llm_cfg = load_config("models/llm", get_env())
        model_name = llm_cfg.get("model")
        if not model_name:
            raise ValueError("models/llm.yaml must define 'model'")

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

        messages: list[dict] = [{"role": "system", "content": get_prompt_registry().get("autonomous_agent_system")}]
        for msg in session_history:
            if msg.get("role") in ("user", "assistant", "tool"):
                messages.append({"role": msg["role"], "content": msg.get("content", "")})

        # ── Agentic loop — all rounds are streamed for instant TTFT ───────────
        for _round in range(_MAX_TOOL_ROUNDS):
            try:
                stream_resp = litellm.completion(
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    tool_choice="auto",
                    stream=True,
                    **base_kwargs,
                )
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Accumulate the streamed response to detect tool calls vs final text
            text_chunks: list[str] = []
            tool_calls_by_idx: dict[int, dict] = {}
            finish_reason: str | None = None
            is_streaming_text = False

            for chunk in stream_resp:
                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason or finish_reason

                # Stream reasoning/thinking tokens immediately
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    yield f"data: {json.dumps({'type': 'thinking', 'text': reasoning})}\n\n"

                # Accumulate tool call fragments
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index if hasattr(tc_delta, "index") else 0
                        if idx not in tool_calls_by_idx:
                            tool_calls_by_idx[idx] = {
                                "id": getattr(tc_delta, "id", None) or "",
                                "name": "",
                                "arguments": "",
                            }
                        entry = tool_calls_by_idx[idx]
                        if tc_delta.id:
                            entry["id"] = tc_delta.id
                        if hasattr(tc_delta, "function") and tc_delta.function:
                            if tc_delta.function.name:
                                entry["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                entry["arguments"] += tc_delta.function.arguments

                # Stream text content live (only when no tool calls detected yet)
                content = getattr(delta, "content", None)
                if content:
                    text_chunks.append(content)
                    if not tool_calls_by_idx:
                        is_streaming_text = True
                        yield f"data: {json.dumps({'type': 'text', 'text': content})}\n\n"

            # ── Decide: tool calls or final text ──────────────────────────────
            if finish_reason == "tool_calls" or tool_calls_by_idx:
                # Build the assistant message with tool_calls for history
                tc_list = []
                for idx in sorted(tool_calls_by_idx):
                    tc = tool_calls_by_idx[idx]
                    tc_list.append({
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    })
                messages.append({
                    "role": "assistant",
                    "content": "".join(text_chunks) or None,
                    "tool_calls": tc_list,
                })

                # Execute each tool and emit events
                for tc_entry in tc_list:
                    tool_name = tc_entry["function"]["name"]
                    try:
                        arguments = json.loads(tc_entry["function"]["arguments"] or "{}")
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
                        "tool_call_id": tc_entry["id"],
                        "content": result_content[:8000],
                    })
                continue

            # ── Final text response — already streamed live above ────────────
            break

        else:
            # Exhausted tool rounds
            yield f"data: {json.dumps({'type': 'text', 'text': 'I have gathered the data above. Here is my summary based on what was retrieved.'})}\n\n"

        yield "data: [DONE]\n\n"
