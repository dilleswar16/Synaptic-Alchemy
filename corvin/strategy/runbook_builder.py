"""
Conversational Runbook Builder — V6

Upgrades the one-shot runbook generation to a multi-turn conversational experience.
The operator can iteratively refine runbook steps through natural conversation:

  1. Initial draft is generated from investigation context
  2. User can ask to expand, simplify, add caveats, add rollback steps, etc.
  3. Each revision shows a diff preview
  4. Final version requires explicit "save" approval before persisting

All saves require human approval — no auto-writing to knowledge base.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import litellm

from corvin.core.config_loader import get_env, load_config

_log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an expert SRE runbook author for the Corvin incident response platform.

Your job is to help operators build high-quality runbook steps through conversation.
You ALWAYS output runbook content in Markdown format.

Rules:
- Start runbook steps with ## heading
- Use bullet points for procedural steps
- Include rollback instructions when relevant
- Include "When to apply" context
- Keep each step under 300 words
- Be specific: include actual commands, service names, thresholds
- When asked to revise, output the FULL updated runbook step (not just the diff)

You have context from the investigation that generated this runbook entry.
Use it to provide specific, actionable steps."""


@dataclass
class RunbookDraft:
    """Current draft of the runbook being built."""
    content: str
    version: int
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "version": self.version,
            "generated_at": self.generated_at,
        }


@dataclass
class RunbookSession:
    """A conversational runbook building session."""
    session_id: str
    request_id: str  # investigation that triggered this
    service_name: str
    environment: str
    messages: list[dict[str, str]] = field(default_factory=list)
    current_draft: RunbookDraft | None = None
    status: str = "drafting"  # drafting | approved | saved
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "request_id": self.request_id,
            "service_name": self.service_name,
            "environment": self.environment,
            "message_count": len(self.messages),
            "current_draft": self.current_draft.to_dict() if self.current_draft else None,
            "status": self.status,
            "created_at": self.created_at,
        }


class RunbookBuilder:
    """Conversational runbook builder with multi-turn editing."""

    def __init__(self):
        self._model_config = load_config("models/llm", get_env())
        self._sessions: dict[str, RunbookSession] = {}

    def start_session(
        self,
        request_id: str,
        service_name: str,
        environment: str,
        investigation_context: str,
    ) -> RunbookSession:
        """Start a new runbook building session with investigation context."""
        session_id = str(uuid.uuid4())

        # Build initial system context
        system_msg = (
            f"{_SYSTEM_PROMPT}\n\n"
            f"## Investigation Context\n"
            f"Service: {service_name}\n"
            f"Environment: {environment}\n"
            f"Investigation ID: {request_id}\n\n"
            f"{investigation_context}"
        )

        session = RunbookSession(
            session_id=session_id,
            request_id=request_id,
            service_name=service_name,
            environment=environment,
            messages=[{"role": "system", "content": system_msg}],
        )

        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> RunbookSession | None:
        """Retrieve an active session."""
        return self._sessions.get(session_id)

    async def chat(self, session_id: str, user_message: str) -> dict[str, Any]:
        """
        Send a message in the runbook building conversation.
        Returns the assistant response and updated draft.
        """
        session = self._sessions.get(session_id)
        if not session:
            return {"error": "Session not found", "session_id": session_id}

        if session.status == "saved":
            return {"error": "Session already saved. Start a new session to make changes."}

        # Add user message
        session.messages.append({"role": "user", "content": user_message})

        # Call LLM
        try:
            resp = litellm.completion(
                messages=session.messages,
                **self._model_config,
            )
            assistant_content = resp.choices[0].message.content.strip()
        except Exception as exc:
            _log.warning("Runbook builder LLM call failed: %s", exc)
            session.messages.pop()  # Remove failed user message
            return {"error": f"LLM call failed: {str(exc)}"}

        # Add assistant response
        session.messages.append({"role": "assistant", "content": assistant_content})

        # Extract markdown content as the draft
        draft_content = self._extract_runbook_content(assistant_content)
        if draft_content:
            version = (session.current_draft.version + 1) if session.current_draft else 1
            session.current_draft = RunbookDraft(content=draft_content, version=version)

        return {
            "session_id": session_id,
            "response": assistant_content,
            "draft": session.current_draft.to_dict() if session.current_draft else None,
            "message_count": len([m for m in session.messages if m["role"] != "system"]),
        }

    async def generate_initial_draft(self, session_id: str) -> dict[str, Any]:
        """Generate the first draft without user input."""
        return await self.chat(
            session_id,
            "Generate an initial runbook step based on the investigation context. "
            "Include: heading, when to apply, procedural steps, rollback, and verification."
        )

    def approve_draft(self, session_id: str, approved_by: str) -> dict[str, Any]:
        """Mark the current draft as approved (ready to save)."""
        session = self._sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}
        if not session.current_draft:
            return {"error": "No draft to approve"}

        session.status = "approved"
        return {
            "session_id": session_id,
            "status": "approved",
            "approved_by": approved_by,
            "draft": session.current_draft.to_dict(),
        }

    def get_final_content(self, session_id: str) -> str | None:
        """Get the approved draft content for saving."""
        session = self._sessions.get(session_id)
        if not session or session.status != "approved" or not session.current_draft:
            return None
        session.status = "saved"
        return session.current_draft.content

    def _extract_runbook_content(self, text: str) -> str | None:
        """Extract the runbook markdown from assistant response."""
        # Look for content starting with ## heading
        lines = text.split("\n")
        start_idx = None
        for i, line in enumerate(lines):
            if line.strip().startswith("##"):
                start_idx = i
                break

        if start_idx is not None:
            return "\n".join(lines[start_idx:]).strip()

        # If no ## heading, check if the whole response looks like a runbook
        if any(line.strip().startswith("- ") for line in lines):
            return text.strip()

        return None
